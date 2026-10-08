#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""梦幻神域 —— 本地游戏服（阶段 9：登录 / 重连链路）。

协议（由 NetworkManager::Send / OnDataReceived 反汇编确认）：
  帧 = [总长:u32 LE] [msgid:u16 LE] [crc32:u32 LE] [serial:u16 LE] [body...]
  头部固定 12 字节；body 为 protobuf（protobuf-net）。
  客户端收到后只读 msgid 和 body（偏移 12 起），CRC/serial 不校验。

已确认的关键消息：
  1   C→S  INIT 握手        （CMSG_INIT_TOClient: SerialNumber int32 tag1）
  601 C→S  CCMsgReConnect   （account=1, sdkNo=2, pos=3, regionResID=4）
  901 S→C  CCMsgReConnect_Ret（result=1[1成功/2失败], player=2, svrCurTime=3）
  101 S→C  CSMsgAccountEnterRet

用法:
  python game_server.py [--host 0.0.0.0] [--port 9001]
                        [--init-body 0801] [--reconnect-result 1]
"""
import argparse
import binascii
import json
import os
import socket
import struct
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOGDIR = os.path.join(HERE, "logs")
os.makedirs(LOGDIR, exist_ok=True)
LOG = os.path.join(LOGDIR, "game_server.log")

import proto  # noqa: E402

MSG_NAMES = {
    1: "INIT握手",
    2: "服务器断开通知 CMsgErrorCode",
    3: "心跳",
    10: "C→S CCMsgCheckLogin",
    101: "CCMsgAccountEnter / CSMsgAccountEnterRet",
    201: "C→S CMsgRequestFormation / S→C CMsgFormation",
    202: "C→S CMsgFormation(提交布阵)",
    331: "C→S CCMsgResouceFBRequest(资源副本开战)",
    332: "C→S CCMsgResultFB(资源副本结算上报)",
    601: "C→S CCMsgReConnect (S→C: CCSMsgWuJiangAttriUpdate)",
    901: "S→C CCMsgReConnect_Ret",
}


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    try:
        print(line, flush=True)
    except (OSError, ValueError):
        # Detached SSH/console output is optional: never abort a packet handler
        # or skip the durable log merely because stdout was closed/lost.
        pass
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def hexdump(b, base=0):
    out = []
    for i in range(0, len(b), 16):
        chunk = b[i:i + 16]
        h = binascii.hexlify(chunk).decode()
        h = " ".join(h[j:j + 2] for j in range(0, len(h), 2))
        asc = "".join(chr(c) if 32 <= c < 127 else "." for c in chunk)
        out.append("%08x  %-47s  %s" % (base + i, h, asc))
    return "\n".join(out)


def make_frame(msgid, body=b"", serial=0, crc=None):
    """帧 = [总长 u32 LE][msgid u16 LE][crc32 u32 LE][serial u16 LE][body]

    CRC 校验点（ClientSession::OnDataReceived rva=0x291cec）：
        expected = BitConverter.ToUInt32(buf, offset + 6)      # 帧内偏移 6 = crc 字段
        actual   = Crc32.GetStreamCRC32(buf, offset+12, len-12)  # = 标准 zlib.crc32(body)
        不匹配 -> 报 Error 事件并 Close。因此 crc 必须填 zlib.crc32(body)。
    """
    import zlib
    total = 12 + len(body)
    if crc is None:
        crc = zlib.crc32(body) & 0xFFFFFFFF
    return struct.pack("<IHIH", total, msgid, crc, serial) + body


def parse_frame(buf):
    if len(buf) < 4:
        return None, buf
    total = struct.unpack("<I", buf[:4])[0]
    if total < 12 or total > 1 << 20 or len(buf) < total:
        return None, buf
    msgid, crc, serial = struct.unpack("<HIH", buf[4:12])
    body = buf[12:total]
    return (total, msgid, crc, serial, body), buf[total:]


def describe_body(body):
    out = []
    i = 0
    while i < len(body):
        tag = 0
        shift = 0
        while i < len(body):
            b = body[i]
            i += 1
            tag |= (b & 0x7F) << shift
            shift += 7
            if not (b & 0x80):
                break
        field, wt = tag >> 3, tag & 7
        if wt == 0:
            v = 0
            shift = 0
            while i < len(body):
                b = body[i]
                i += 1
                v |= (b & 0x7F) << shift
                shift += 7
                if not (b & 0x80):
                    break
            out.append("field %d varint = %d" % (field, v))
        elif wt == 2:
            ln = 0
            shift = 0
            while i < len(body):
                b = body[i]
                i += 1
                ln |= (b & 0x7F) << shift
                shift += 7
                if not (b & 0x80):
                    break
            data = body[i:i + ln]
            i += ln
            try:
                s = data.decode("utf-8")
                printable = all(32 <= ord(c) < 127 or c in "\n\r\t" for c in s)
            except Exception:
                printable = False
            out.append("field %d bytes(%d) = %s"
                       % (field, ln, repr(s) if printable else data.hex()))
        elif wt == 5:
            v = struct.unpack("<f", body[i:i + 4])[0]
            i += 4
            out.append("field %d float = %s" % (field, v))
        elif wt == 1:
            v = struct.unpack("<d", body[i:i + 8])[0]
            i += 8
            out.append("field %d double = %s" % (field, v))
        else:
            out.append("field %d wiretype %d (未解析)" % (field, wt))
            break
    return out


# ---------------------------------------------------------------- 应答构造

def build_init(serial_number=0):
    return proto.v_field(1, serial_number)


def build_wujiang(guid, index, level=30):
    """CMsgWuJiang 最小集：guid(1 str)/index(2)/level(3)/jieduan(4)/stars(6)/
    skillindex_1_level(11)/fightpower(15)。index 对应 WuJiangBaseAttri.ini 武将ID。
    练度调高以保证 90s 倒计时内可击杀副本 BOSS（命运之镰实测 1级 只能打到 40%）。"""
    b = proto.s_field(1, guid)
    b += proto.v_field(2, index)
    b += proto.v_field(3, level)
    b += proto.v_field(4, 1)      # jieduan
    b += proto.v_field(6, 5)      # stars
    b += proto.v_field(11, 10)    # 技能1等级
    b += proto.v_field(15, 3000)  # fightpower
    return b


def build_player(account="local", guid=1, level=None, main_role_index=1):
    """CMsgDetailPlayerInfo 的最小可解析版本。
    level=None -> 用 PLAYER_LEVEL。⚠ 102/901 两条路都要给同一个等级，
    否则重连后资源副本入口会按等级重新上锁（见 PLAYER_LEVEL 注释）。"""
    if level is None:
        level = PLAYER_LEVEL
    b = proto.v_field(1, guid)          # guid
    b += proto.s_field(2, account)      # account
    b += proto.v_field(3, level)        # level
    b += proto.v_field(5, 0)            # curexp
    b += proto.v_field(6, 0)            # curvp
    b += proto.v_field(7, 0)            # curRMB
    b += proto.v_field(8, 10000)        # jinbi
    # 主线通关进度（客户端打包值 = 章节*1000 + 关卡）：
    #   GlobalSetup_CH.txt「开启每日活动普通关卡通关限制 = 1010」
    #   TaskSystem.Open 里判定 GuanKaHasPassed(mOpenDailyTaskGuanKaLimit*10+1)
    #   -> 该函数 %10==1 分支返回 (limit/10 <= LastMainFBNormal)
    #   -> 等价于 1010 <= LastMainFBNormal，即"已通关第一章第十关(BOSS关)"。
    #   之前发 10（章节0关卡10，无效值）导致"每日活动/每日任务"恒为锁定并弹
    #   "通关1-10解锁"提示。
    b += proto.v_field(9, MAIN_FB_NORMAL)      # lastmainFBnormal 普通难度进度
    b += proto.v_field(10, MAIN_FB_DIFFICULT)  # lastmainFBdifficult 精英难度进度
    b += proto.v_field(11, 10)          # worldchatfreetimes
    b += proto.v_field(12, 10)          # skillpoints
    # mainRoleIndex(tag35)：角色序号从 1 开始（1=黑剑士 res18 2=闪光骑士 res19）。
    # ⚠ SecondLoginDay.Refresh 用 PrizeInfoItems[mainRoleIndex-1] 取奖励配置，
    #   发 0（或缺失=0）会索引 -1 抛异常 -> 弹窗停在 prefab 占位数据（假倒计时 08:50:15）。
    b += proto.v_field(35, main_role_index)
    # 次日登录奖励弹窗（SecondLoginDay）：
    #   tag36 leftTimeToSecondLoginDay(int32！属性签名 0x28 0x00 0x08 = I4，
    #   UnPackData 里 conv.r4 转 float 存入 mLeftTimeToSecondLoginDay)
    #   -> MainPlayer.Update 每帧 -= dt，弹窗用它显示 hh:mm:ss；
    #   归零后 GetButton 才可点（OnGetButtonClicked 要求 <=0.001 才发 C→S 2601）。
    #   ⚠ 必须发 varint，发 fixed32(wiretype5) 会 wiretype 不匹配中断解析。
    #   tag37 isDrawSecondDayLoginPrized(bool) = true 时不再递减/不再弹（已领）。
    if _SAVE.get("second_login_day_prized"):
        b += proto.v_field(37, 1)       # 已领：客户端不再递减、不再弹窗
    else:
        # 离线复活血脉：给一个短倒计时让玩家完整体验"倒计时归零→领取→获得狙击手"
        b += proto.v_field(36, int(SECOND_LOGIN_DAY_COUNTDOWN))
    # 关键：account_create_time(tag 48) 必须填 "yyyy-MM-dd HH:mm:ss"。
    # MainPlayer.UnPackData 无条件 DateTime.ParseExact(该字段, "yyyy-MM-dd HH:mm:ss")，
    # 空串会抛 FormatException -> 中断 UnPackData -> 中断 OnQuestFirstEnterRegionRet，
    # 导致类 .ᝁ 的静态主玩家实例(ᜀ#17854)始终为 null，
    # 后续进副本时事件75(FB分支)首行 ᜀ#17854.SetActive() 每帧 NullReferenceException，
    # 表现为主城正常但副本加载画面永久卡住。
    b += proto.s_field(48, ACCOUNT_CREATE_TIME)
    # resourceFBData(tag 115, repeated CCMsgResouceFBData) —— 阶段16d 根治主城 NRE。
    # MainPlayer.UnPackData 里 mResourceFBDataList = msg.resourceFBData（直接赋值）。
    # 缺该字段 -> 列表为空/null -> TiaoZhanNanDu.IsAvailable(type) 每帧调用
    #   MainPlayer.GetResourceFBData(type) = mResourceFBDataList.Find(...) 返回 null
    #   -> 紧接 .playTime 抛 NullReferenceException -> 中断 DaTingMainUISystem.Update
    #   -> 主城"挑战"图标、任务"前往"按钮全部点了没反应。
    # ⚠ 必须放在 102 CCMsgMainPlayer 里（450 只是增量更新，不能凭空造列表）。
    b += build_resource_fb_list()
    # vWuJiangs(tag 101, repeated CMsgWuJiang)：玩家拥有的武将。
    # 战斗场景需要 CreateWuJiangByGUID(guid) 从拥有列表创建出战武将；
    # 空列表 -> 事件75 副本分支 NRE（CreateWuJiangByGUID 返回 null -> GetPosition 崩）。
    # 18=黑剑士(主角) 19=闪光骑士（WuJiangBaseAttri.ini 实测存在）。
    b += proto.m_field(101, build_wujiang("hero18", 18))
    b += proto.m_field(101, build_wujiang("hero19", 19))
    # Varis(field 109, repeated CMsgPlayerVaris{VariName=1 str, VariValue=2 str})：
    # 引导系统 GuideLogic.checkCompleteState 读 MainPlayer:GetPlayerVaris("NG_xxx")，
    # 值=="1" 表示该引导步骤已完成 -> 跳过新手引导（否则引导遮罩锁死主城全部点击）。
    for addr in GUIDE_DONE_VARS:
        vb = proto.s_field(1, addr) + proto.s_field(2, "1")
        b += proto.m_field(109, vb)
    return b


# 资源副本类型（与 region 类型一致，见 GameData/ResourceFBData.txt）：
#   5=镜像挑战 6=死亡躲避(Untouchable) 8=致命游戏 9=圣诞堡垒 10=命运之镰
RESOURCE_FB_TYPES = (5, 6, 8, 9, 10)


def build_resource_fb_update():
    """S→C 450 CCMsgResouceFBDataUpdate{1: repeated CCMsgResouceFBData}
    CCMsgResouceFBData{1: regionType, 2: playTime(已用次数), 3: lastPlayTime(时间串)}

    为什么必须发：TiaoZhanNanDu.IsAvailable(type) 在主城
    DaTingMainUISystem.Update 里每帧对每种资源副本调用一次；它取
    MainPlayerAttribute.mResourceFBDataList 里对应 type 的记录，而
    MainPlayer.GetResourceFBData 用 List.Find 找不到就返回 null ->
    紧接着 .playTime 抛 NullReferenceException -> 中断主城 Update ->
    挑战/前往等按钮全部"点了没反应"。把 5/6/8/9/10 全部下发即可根治。
    playTime 置 0（未使用，次数充足）；lastPlayTime 给很久以前的时间（CD 已过）。
    """
    b = b""
    for t in RESOURCE_FB_TYPES:
        b += proto.m_field(1, proto.v_field(1, t)                       # regionType
                              + proto.v_field(2, 0)                     # playTime
                              + proto.s_field(3, "2020-01-01 00:00:00"))  # lastPlayTime
    return b


def build_resource_fb_list():
    """CMsgDetailPlayerInfo.resourceFBData (tag 115)：repeated CCMsgResouceFBData。
    这是主城资源副本数据的**唯一来源**（450 只是增量更新）。
    契约（Msg.dll 阶段16d 实锤）：
      CMsgDetailPlayerInfo.resourceFBData tag=115，元素 CCMsgResouceFBData：
        regionType   tag=1  DataFormat=2(TwosComplement) -> varint
        playTime     tag=2  DataFormat=2                 -> varint
        lastPlayTime tag=3  string "yyyy-MM-dd HH:mm:ss"
        starInfo     tag=4  string
    类型（GameData/ResourceFBData.txt）：5=镜像挑战 6=死亡躲避 8=致命游戏
      9=圣诞堡垒 10=命运之镰。playTime=0（未使用）；lastPlayTime 给很久以前
      的时间（CD 已过，IsAvailable 走"可用"分支）。
    """
    b = b""
    for t in RESOURCE_FB_TYPES:
        b += proto.m_field(115, proto.v_field(1, t)                        # regionType
                                + proto.v_field(2, 0)                      # playTime
                                + proto.s_field(3, "2020-01-01 00:00:00")) # lastPlayTime
    return b


def build_zbz_info(turn_on=None, turn_on_day=None):
    """S→C 4602 CCMsgZBZInfo（争霸赛信息）。

    契约（work/messages_full.json，Msg.dll）：
      CurState            tag=1  int32  varint
      CurTargetPlayerID   tag=2  int32  varint
      XingJi              tag=3  int32  varint
      JiFen               tag=4  int32  varint
      TrunOn              tag=5  bool   varint
      TrunOnDay           tag=6  int32  varint
      GambleInfo          tag=7  repeated
      playerinfo          tag=8  repeated
      DefenseWuJiangID    tag=9  repeated
      RankPlayerInfo      tag=10 repeated
      HadDefense          tag=11 bool   varint
      JueZhanStartTime    tag=12 string

    ⚠ **这条消息不发会直接卡死「挑战」面板**（阶段16e 实锤）：
      MainPlayerAttribute.mCCMsgZBZInfo 只由 ᝁ::OnCCMsgZBZInfo(4602) 赋值
      （唯一写入点，见 IL 扫描）。为空时：
        * ChallengeEntryUI.Open() 在争霸赛刷新块读
          Attribute.mCCMsgZBZInfo.TrunOn -> NullReferenceException
          -> Open() 中断 -> 其最后一条指令 `this.state = 2` 永不执行
        * 而 Close() 首句是 `if (state != 2) return;`
          => 关闭按钮/全屏遮罩全部静默失效 => 挑战面板无法返回（死界面）
        * 同时 OnZhengBaZhan 点击也 NRE
      处理器的写法是 `if (MainPlayer.Object == null) return;
                     Attribute.mCCMsgZBZInfo = Deserialize<CCMsgZBZInfo>(body);`
      -> 空 body 也能得到一个非 null 实例，但显式下发字段更稳。

    TrunOn=false 表示"争霸赛未开启"（原版非赛事日的正常状态），
    客户端会走"锁定/未开启"分支，不再抛异常。

    ⚠ body 必须**非空**（阶段16e 实证）：
      proto.v_field(f, 0) 返回 b""（protobuf 默认值不序列化），
      若 8 个字段全为 0，body 就是 0 字节 -> 帧长只有 10（纯帧头）。
      客户端 `GameManager.DeserializeProtobuf<CCMsgZBZInfo>(空, null)`
      -> `TypeModel.Deserialize` 对空流的行为不确定（可能返回 null）
      -> 后续 `ldfld mCCMsgZBZInfo` / `get_TrunOn()` 再 NRE。
      因此这里改用 v_field_raw，显式写出 TrunOn/TrunOnDay/HadDefense=0。
      IL 佐证（ChallengeEntryUI.Open，块只读 tag5/tag6）：
        IL_10fae1 MainPlayer.ᜀ.Attribute.mCCMsgZBZInfo
        IL_10faf0 callvirt Msg::get_TrunOn()
        IL_10faf5 brtrue  0x10FBFD      // TrunOn==true 才去读 TrunOnDay
        // false 分支：设 SpriteLock/"Label"=getStr(101030) 锁定样式，然后跳到块尾
      => TrunOn=false 时只有 tag5 被消费，其余字段取任意值都无副作用。
    """
    on = ZBZ_TURN_ON if turn_on is None else turn_on
    day = ZBZ_TURN_ON_DAY if turn_on_day is None else turn_on_day
    b = proto.v_field(1, 0)      # CurState
    b += proto.v_field(2, 0)     # CurTargetPlayerID
    b += proto.v_field(3, 0)     # XingJi
    b += proto.v_field(4, 0)     # JiFen
    b += proto.v_field_raw(5, 1 if on else 0)   # TrunOn（显式，保证 body 非空）
    b += proto.v_field_raw(6, day)              # TrunOnDay（显式）
    b += proto.v_field_raw(11, 0)               # HadDefense（显式）
    return b


def build_reconnect_ret(result=1, account="local", svr_time=None,
                        level=None, main_role_index=None):
    """CCMsgReConnect_Ret { result=1, player=2, svrCurTime=3 }

    ⚠ 901 的 player 会**整体重建**客户端 MainPlayerAttribute 中的玩家数据，
    因此等级(level)与角色序号(mainRoleIndex)必须与 102 路径一致：
      * level 不一致 -> 重连后 ResourceFB 等级门禁重新上锁（阶段16e 实测）
      * mainRoleIndex 不一致 -> 次日登录奖励 PrizeInfoItems[mainRoleIndex-1]
        取错角色、以及 res 相关的其他分支走错（见 build_main_player 注释）
    """
    t = svr_time or time.strftime("%Y-%m-%d %H:%M:%S")
    b = proto.v_field(1, result)
    if result == 1:
        b += proto.m_field(2, build_player(
            account,
            level=level,
            main_role_index=1 if main_role_index is None else main_role_index))
    b += proto.s_field(3, t)
    return b


# 默认出战布阵（主指挥官 + 先锋1/2 + 替补1/2）
DEFAULT_FORMATION = ("hero18", "hero19", "hero19", "hero18", "hero19")


def build_formation(type_=0, wj=None):
    """S→C 201 CMsgFormation{type=1(eFormationType), wj=2(repeated str)}。
    wj[0]=主指挥官 wj[1]=先锋1 wj[2]=先锋2 wj[3]=替补1 wj[4]=替补2。

    ⚠ type 必须回**客户端请求的那个值**（见 handle() 里 msgid 201 分支）：
    OnEmBattleUpdateFromServer 按 CMsgFormation.type 走 39 路 switch，
    把数据写进 mCompleteMember 的不同字段：
      0  FORMATION_TYPE_NORMAL              -> PVEEnBattle（事件75 副本分支用，无 null 检查）
      1  FORMATION_TYPE_JJC_DEFENSE         -> JJCDefenceEnBattle
      2  FORMATION_TYPE_JJC_ATTACK          -> JJCAttackEnBattle
      5  MIRROR_CHALLENGE                   -> MirrorEnBattle
      8  DEADLY_GAME                        -> DeadlyGameEnBattle
      10 FORMATION_TYPE_SCYTHE_OF_FATE      -> ScytheOfFateEnBattle（命运之镰）
      11 JJC_QIE_CUO                        -> QieCuoAttackBattle
    （枚举来自 Msg 程序集 NetProto.eFormationType，31 个成员）"""
    if wj is None:
        wj = DEFAULT_FORMATION
    b = proto.v_field(1, type_)
    for g in wj:
        b += proto.s_field(2, g)
    return b


def parse_formation(body):
    """解析 CMsgFormation / CMsgRequestFormation{type=1(varint), wj=2(repeated str)}。
    返回 (type, wj_list)。"""
    t = 0
    wj = []
    i = 0
    try:
        while i < len(body):
            tg = 0
            sh = 0
            while i < len(body):
                c = body[i]
                i += 1
                tg |= (c & 0x7F) << sh
                sh += 7
                if not (c & 0x80):
                    break
            f, wt = tg >> 3, tg & 7
            if wt == 0:
                v = 0
                sh = 0
                while i < len(body):
                    c = body[i]
                    i += 1
                    v |= (c & 0x7F) << sh
                    sh += 7
                    if not (c & 0x80):
                        break
                if f == 1:
                    t = v
            elif wt == 2:
                ln = 0
                sh = 0
                while i < len(body):
                    c = body[i]
                    i += 1
                    ln |= (c & 0x7F) << sh
                    sh += 7
                    if not (c & 0x80):
                        break
                chunk = body[i:i + ln]
                i += ln
                if f == 2:
                    wj.append(chunk.decode("utf-8", "replace"))
            elif wt == 5:
                i += 4
            elif wt == 1:
                i += 8
    except Exception:
        pass
    return t, wj


def parse_int_field(body, want_tag):
    """从 protobuf body 里取第一个 varint 字段 want_tag 的值；没有返回 None。"""
    i = 0
    try:
        while i < len(body):
            tg = 0
            sh = 0
            while i < len(body):
                c = body[i]
                i += 1
                tg |= (c & 0x7F) << sh
                sh += 7
                if not (c & 0x80):
                    break
            f, wt = tg >> 3, tg & 7
            if wt == 0:
                v = 0
                sh = 0
                while i < len(body):
                    c = body[i]
                    i += 1
                    v |= (c & 0x7F) << sh
                    sh += 7
                    if not (c & 0x80):
                        break
                if f == want_tag:
                    return v
            elif wt == 2:
                ln = 0
                sh = 0
                while i < len(body):
                    c = body[i]
                    i += 1
                    ln |= (c & 0x7F) << sh
                    sh += 7
                    if not (c & 0x80):
                        break
                i += ln
            elif wt == 5:
                i += 4
            elif wt == 1:
                i += 8
    except Exception:
        pass
    return None


# 资源副本（挑战面板 → 命运之镰）场景号。
# RegionList.txt 第25行：场景ID 60 / 场景名 命运之镰 / 场景类型 10 / 资源名 Scene_C_01
SCYTHE_OF_FATE_REGION = 60


FORMATION_TYPE_NAMES = {
    0: "NORMAL(副本)",
    1: "JJC_DEFENSE",
    2: "JJC_ATTACK",
    3: "QIANGKUANG_DEFENSE",
    4: "QIANGKUANG_ATTACK",
    5: "MIRROR_CHALLENGE",
    6: "UNTOUCHABLE",
    7: "TIAOZHANSAI",
    8: "DEADLY_GAME",
    9: "SANTA_FORT",
    10: "SCYTHE_OF_FATE(命运之镰)",
    11: "JJC_QIE_CUO",
    12: "UNION_ZUO_ZHAN_BOSS",
    23: "UNION_RAID_BIAO_CHE",
    24: "UNION_PVP_DEFENSE_1",
    25: "UNION_PVP_DEFENSE_2",
    26: "UNION_PVP_DEFENSE_3",
    27: "UNION_PVP_DEFENSE_4",
    28: "UNION_PVP_DEFENSE_5",
    29: "UNION_PVP_OFFENSE",
    30: "BCT",
}


def build_main_player(dyn_id=1, res_id=18, name="local", account="local", level=None):
    """S→C 102 CCMsgMainPlayer（= QuestFirstEnterRegionRet 处理器 .ᝁ::OnQuestFirstEnterRegionRet）
    { dynID=1, res_id=2, name=3, player=4(CMsgDetailPlayerInfo) }
    IL 证据：get_dynID / get_res_id / get_player / get_name，
    其中 res_id 进 UnitManager.CreateUnit，name 赋给 MainPlayerAttribute.mName，
    player 走 MainPlayer.UnPackData。
    """
    b = proto.v_field(1, dyn_id)
    b += proto.v_field(2, res_id)
    b += proto.s_field(3, name)
    # mainRoleIndex 与 res_id 保持一致：CreateRoleSetup 选择ID 0->18(黑剑士)->index 1
    mri = 1 if res_id == 18 else 2
    b += proto.m_field(4, build_player(account, level=level, main_role_index=mri))
    return b


def build_account_enter_ret(dyn_id=1, svr_time=None):
    """S→C 101 CSMsgAccountEnterRet（Write rva=0x5ad0c）：
        1 dynID int32 / 2 alreadyNewUserGuideFB bool / 3 debug bool
        4 mainRoleIndex int32 / 5 svrCurTime string
        6 isEnableHundredTower bool / 7 isEnableHundredTowerSDDH bool / 8 isEnableLP bool
    alreadyNewUserGuideFB=true -> mNewUserFBActive=false -> 客户端发 304 走正常主城流程，
    否则走新手引导 FB 分支（发 5401/5402/102）。
    """
    t = svr_time or time.strftime("%Y-%m-%d %H:%M:%S")
    return (proto.v_field(1, dyn_id)
            + b"\x10\x01"                    # alreadyNewUserGuideFB = true
            + proto.v_field(4, 1)            # mainRoleIndex = 1
            + proto.s_field(5, t))


# ---------------------------------------------------------------- 连接处理

# 客户端 MainPlayer.UnPackData 会用 DateTime.ParseExact(..., "yyyy-MM-dd HH:mm:ss") 解析，
# 必须是这个格式，空串会抛异常并中断整个主玩家初始化。
ACCOUNT_CREATE_TIME = "2020-01-01 00:00:00"

# 次日登录奖励倒计时（秒，float）。客户端 MainPlayer.Update 每帧本地递减，
# 归零后 SecondLoginDay 弹窗的"领取"按钮才可点（OnGetButtonClicked 检查 <=0.001）。
# 原版逻辑是"注册后次日 0 点可领"，离线服给 120 秒方便完整体验领奖流程。
SECOND_LOGIN_DAY_COUNTDOWN = 120.0

# 主线副本通关进度（客户端打包值 = 章节*1000 + 关卡；第 10 关为每章 BOSS 关）。
#   GlobalSetup_CH.txt：「开启每日活动普通关卡通关限制 = 1010」
#   TaskSystem.Open 判定 ChapterGuanKaCommonInfo.GuanKaHasPassed(cfg*10+1)，
#   而 GuanKaHasPassed(x) 在 x%10==1 时返回 (x/10 <= MainPlayerAttribute.LastMainFBNormal)
#   -> 实际门槛 = (1010 <= lastmainFBnormal)。故 1010 = 已通关"第一章第十关"，
#   是解锁"每日活动/每日任务"的必要条件。
MAIN_FB_NORMAL = 1010      # 普通难度：第一章第十关已通关
MAIN_FB_DIFFICULT = 1010   # 精英难度：同步给到同一进度（部分开启条件用它）

# 争霸赛（ZBZ）状态：S→C 4602 CCMsgZBZInfo。
# ⚠ 必须下发！否则 MainPlayerAttribute.mCCMsgZBZInfo 为 null，
#   导致 ChallengeEntryUI.Open() 抛 NRE -> 「挑战」面板无法关闭（详见 build_zbz_info）。
ZBZ_TURN_ON = False        # False = 未开启赛事（原版非赛事日状态，客户端显示"未开启"）
ZBZ_TURN_ON_DAY = 0        # 比赛日编号；TrunOn=True 时 >0 表示"今日为比赛日"

# 玩家等级（CMsgDetailPlayerInfo.level, tag=3）。
# ⚠ 102(登录) 与 901(重连) 两条路**必须发同一个等级**：阶段16e 实测，
#   重连路径当时走 build_player 默认 level=1，客户端回来后
#   ResourceFBData 的等级门禁（ResourceFBLevelData：致命游戏16/命运之镰17/
#   挑战赛20…）全部重新上锁，与登录时的表现不一致。
# 取 30 = "已解锁全部已测内容"（原版满级 100，这里只求可完整走通玩法）。
PLAYER_LEVEL = 30

# 新手引导步骤地址（GuideLogic.lua 全量提取）。全部置 "1" = 引导已完成。
GUIDE_DONE_VARS = (
    "NG_10011B", "NG_10011E", "NG_10021B", "NG_10031B", "NG_10031E",
    "NG_10041E", "NG_10051E", "NG_10061E", "NG_10071B", "NG_10071E",
    "NG_10091E", "NG_10101E", "NG_20031E", "NG_20041B", "NG_20081E",
    "NG_20091B", "NG_20101E", "NG_20101E2", "NG_20101P", "NG_3009E",
    "NG_30101B", "NG_30101E", "NG_40011E2", "NG_40091E", "NG_80091E",
    "NG_80101E", "NG_Func2", "NG_Func3", "NG_Func4", "NG_Func5",
    "NG_Func6", "NG_Func7", "NG_Func8", "NG_Func9", "NG_Func10",
    "NG_Func11", "NG_Func12", "NG_Func13", "NG_Func14", "NG_GUID",
)

INIT_BODY = b""
RECONNECT_RESULT = 1
RC_BODY = None
def build_account_enter_check_ret(code=1, account="local", server_id="1", extra=""):
    """S→C 108 CCSMsgAccountEnterCheckRet（Write rva=0x42bdc）：
        1 ResultInfoCode int32 / 2 account string / 3 serverId string / 4 extraParm string
    .ᜲ::OnAccountEnterCheckRet 中 code==1 分支：
        UserAccount=account; GameLoginSuccess(account, serverId, GetServerNameById(serverId), extraParm)
    这是登录链路的第二拍 —— 之前一直没发 108，客户端卡在加载画面。
    """
    return (proto.v_field(1, code)
            + proto.s_field(2, account)
            + proto.s_field(3, server_id)
            + proto.s_field(4, extra))


def build_qiandao_info():
    """S→C 1801 CCMsgQianDaoInfo（SignInInfo::Update 直接反序列化 body）。
    {1:CurYear, 2:CurMonth, 3:TotalQianDaoDays, 4:prizeStatus(repeated bool,每天一条)}"""
    b = proto.v_field(1, 2026) + proto.v_field(2, 10) + proto.v_field(3, 1)
    for _day in range(31):          # 全部未签 -> 每天都可领
        b += proto.v_field(4, 0)
    return b


# ---- 假对手池：直接采用官方 JJC_Robot.txt 机器人（原版名字/等级/资源ID/胜场）----
# 表列：Index 玩家名字 角色等级 角色资源ID 角色星级 角色阶段 ... 胜场次数 ...
def load_jjc_targets(count=3):
    out = []
    for r in JJC_ROBOTS:
        try:
            idx = int(r.get("Index", 0))
            out.append((1000 + idx,
                        r.get("玩家名字", "机器人"),
                        20000 - idx * 300,             # 战力按排名递减（表内无数值列）
                        idx,                            # RankIndex = 机器人排名
                        int(r.get("角色资源ID", 18)),
                        int(r.get("角色等级", 1)),
                        int(r.get("胜场次数", 0))))
        except (TypeError, ValueError):
            continue
        if len(out) >= count:
            break
    return out or [(1001, "正义诺曼", 18000, 1, 39, 30, 5000)]


def build_jjc_info(with_targets=True):
    """S→C 2001 CCMsgRequestJJCInfo_Ret。
    ⚠ 契约 CA blob 显示 tag1-4 带 DataFormat=2(FixedSize) -> 必须 fixed32 编码！
      发 varint 会 ProtoException: Invalid wire-type (StartSubItem)。
    {1:DefenseFightPower f32, 2:RankIndex f32, 3:ChallengeLeftTimes f32,
     4:PayResetChallengeTimes f32, 5:LastChallengeTime string,
     6:TargetBriefInfos message}  ← 阶段16b 修正：tag6 是
    CCMsgJJCChallengeTargetBriefInfo{1: repeated JJCChallengeTargetBriefInfo}，
    之前直接把 7 字段平铺进 tag6 属于少套一层 -> Read(BriefInfo) StartSubItem 异常。
    JJCChallengeTargetBriefInfo{1:TargetGuid,2:Name,3:FightPower,4:RankIndex,
                                5:ResID,6:Level,7:WinTimes}（数值字段同样 f32）"""
    b = (proto.f32_field(1, 1500)        # 我的防守战力（实测 fixed32 浮点可行）
         + proto.f32_field(2, 5)         # 我的排名（排在机器人之后）
         + proto.f32_field(3, 5)         # 剩余挑战次数
         + proto.f32_field(4, 0)
         + proto.s_field(5, "2020-01-01 00:00:00"))
    if with_targets:
        inner = b""
        for guid, name, fp, rank, res, lv, win in load_jjc_targets():
            t = (proto.f32_field(1, guid) + proto.s_field(2, name) + proto.f32_field(3, fp)
                 + proto.f32_field(4, rank) + proto.f32_field(5, res) + proto.f32_field(6, lv)
                 + proto.f32_field(7, win))
            inner += proto.m_field(1, t)     # repeated，套在 CCMsg wrapper 里
        b += proto.m_field(6, inner)
    return b


def build_set_main_city_born_pos(x=0.0, y=0.0, z=0.0):
    """S→C 103 CCMsgSetMainCityBornPos { x=1, y=2, z=3 }。

    字段类型由 IL 反推（OnSetMainCityBornPos rva=0x26ed7c）：
        get_x / get_y / get_z  -> newobj Vector3::.ctor(float,float,float)
    中间没有 conv.r4，说明三个字段本身就是 float，
    protobuf 编码为 fixed32（wire type 5），头字节 = (tag<<3)|5。
    """
    out = b""
    for tag, v in ((1, x), (2, y), (3, z)):
        out += bytes([(tag << 3) | 5]) + struct.pack("<f", float(v))
    return out


ACCOUNT_DYN_ID = 1

# 主城出生点坐标（103 CCMsgSetMainCityBornPos 的 x/y/z）
BORN_POS = (0.0, 0.0, 0.0)

# ---- 关卡出生点（RegionLogic/<id>_gk.xml 的 BornBos）----
# 进副本后客户端会把角色放到 103 下发的出生点；发 (0,0,0) 会打日志
# "this is a error born position" 并导致每帧 "Touch floor failed!!!"，
# 角色物理失效无法移动。所以收到 C→S 104(LevelLoadFinish) 时按关卡重发。
GAME_DATA_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "work",
    "apk", "luapack_extracted", "GameData"))


# ---- 阶段16b：GameData 配置表解析（主线任务 / 日常任务 / JJC 官方机器人）----
def load_gdata_table(name):
    """解析 GameData TSV 表 -> [dict(列名=值)]。
    格式：说明行若干；含"任务ID/Index"的行是表头；以 # 开头的行是数据行。
    数据行把行首 '#' 换成空串后按 \t 切分，与表头（去掉行首空列）对齐。"""
    path = os.path.join(GAME_DATA_DIR, name)
    try:
        lines = open(path, "r", encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return []
    header = None
    rows = []
    for ln in lines:
        if header is None:
            cells = [c.strip() for c in ln.split("\t")]
            if any(c in ("任务ID", "Index") for c in cells):
                while cells and not cells[0]:
                    cells.pop(0)
                header = cells
            continue
        if not ln.lstrip().startswith("#"):
            continue
        data = [c.strip() for c in ln.replace("#", "", 1).split("\t")]
        while data and not data[0]:
            data.pop(0)
        if not data:
            continue
        rows.append({header[i]: data[i] for i in range(min(len(header), len(data)))
                     if header[i]})
    return rows


ONCE_TASKS = load_gdata_table("OnceTaskConfig.txt")   # 主线（一次性）任务
DAILY_TASKS = load_gdata_table("DailyTaskConfig.txt")
JJC_ROBOTS = load_gdata_table("JJC_Robot.txt")


def build_task_info(entries):
    """repeated COnceTaskInfo{1:taskId,2:finishTimes,3:delete} / CDailyTaskInfo 同构。
    数值字段契约 DataFormat=2 -> fixed32（同 JJC Ret 规则）。"""
    b = b""
    for task_id, times, delete in entries:
        b += proto.m_field(1, proto.i32_field(1, task_id)
                           + proto.i32_field(2, times)
                           + (proto.v_field(3, 1) if delete else b""))
    return b


def first_tasks(table, count, done_times=0):
    """取前 count 个任务 (id, finishTimes, delete=False)。"""
    out = []
    for r in table:
        try:
            tid = int(r.get("任务ID", 0))
        except (TypeError, ValueError):
            continue
        if tid <= 0:
            continue
        out.append((tid, done_times, False))
        if len(out) >= count:
            break
    return out


def task_target_region(task_id):
    """主线任务的目标场景ID（任务类型1/2 的自定义参数列）。"""
    for r in ONCE_TASKS:
        try:
            if int(r.get("任务ID", 0)) == task_id:
                return int(r.get("任务类型自定义参数", 0))
        except (TypeError, ValueError):
            pass
    return 0


def build_goods_update(ori_name, count, shining=False):
    """S→C 301 OnUpdateGoodsCount = CCMsgShiningAwardItem
    {1:oriName string, 2:count fixed32, 3:isShining bool} -> MainPlayer.SetGoods"""
    return (proto.s_field(1, ori_name) + proto.f32_field(2, count)
            + (proto.v_field(3, 1) if shining else b""))


def build_fb_result(result, star_count):
    """S→C 1001 CCMsgResultFB{1:result,2:starCount}。
    实测（2026-10-02 阶段16g）：必须用 **varint** 编码——fixed32 版本客户端
    静默丢弃（不抛异常、不进 OnMsgResultFBRet）；varint 版本正常触发
    事件111 -> 结算窗（messages_full.json 里该类 DataFormat=2 的元数据是错的）。"""
    return (proto.v_field(1, result) + proto.v_field(2, star_count))


def get_region_born_pos(region_id):
    """从 RegionLogic/<id>_gk.xml 读 <BornBos PosX PosY PosZ>；没有则 None。"""
    path = os.path.join(GAME_DATA_DIR, "RegionLogic", "%d_gk.xml" % region_id)
    if not os.path.exists(path):
        return None
    try:
        import re as _re
        with open(path, "r", encoding="utf-8", errors="replace") as stream:
            txt = stream.read()
        # ⚠ 属性引号两种风格都要认！主城 1_gk.xml 用单引号 PosX='-1.12'，
        #   副本（如 3010_gk.xml）用双引号 PosX="24.0874"。
        #   369 个 gk 文件里 33 个是单引号。只认双引号 -> 主城出生点恒为 None
        #   -> 回退 (0,0,0) -> 角色悬空在主城地面(y≈301.5)下方 -> 每帧
        #   "Touch floor failed!!!" -> 物理失效、无法移动、挑战入口点了没反应。
        _Q = r"""["']"""
        m = _re.search(r"""<BornBos[^>]*PosX=["']([-\d.eE]+)["'][^>]*PosY=["']([-\d.eE]+)["']"""
                       r"""[^>]*PosZ=["']([-\d.eE]+)["']""", txt)
        if not m:
            # 属性顺序可能不同，逐属性抓
            def attr(name):
                mm = _re.search(r"""<BornBos[^>]*%s=["']([-\d.eE]+)["']""" % name, txt)
                return float(mm.group(1)) if mm else None
            x, y, z = attr("PosX"), attr("PosY"), attr("PosZ")
            if None in (x, y, z):
                return None
            return (x, y, z)
        return (float(m.group(1)), float(m.group(2)), float(m.group(3)))
    except Exception as e:
        log("   读 %s 出错: %s" % (path, e))
        return None


def parse_level_load_finish(body):
    """C→S 104 CMsgLevelLoadFinish { region_res_id=1 varint } -> int。

    注意先跳过 tag 字节（field1<<3|0 = 0x08），再读 varint value。
    """
    i = 0
    # 跳过 tag
    while i < len(body) and body[i] & 0x80:
        i += 1
    i += 1
    v = 0
    shift = 0
    while i < len(body):
        b = body[i]
        i += 1
        v |= (b & 0x7F) << shift
        shift += 7
        if not (b & 0x80):
            break
    return v

# ---- 流程开关（阶段 12 实测定论）----
# 1301 会把客户端带进建角 UI -> LoadScene(98) 卡加载死路；
# 不发 1301 客户端直接走 5401/5402/102 进主城。
SEND_CREATE_ROLE_NOTIFY = False   # 想走建角流程时改 True
# 5301 空 body 会让客户端 SetDaTingEffect("") -> Instantiate(null) 抛异常
SEND_DATINGS_EFFECT = False
SEND_KFHAPPY = False
# 16b/16c：登录后延迟推送 1103/1101 任务列表。
# ⚠ 不能在登录应答里"立即"推：客户端 OnFirstUpdateOnceTask 会访问尚未就绪的
#   MainPlayer 单例 -> NRE -> 中断 DaTingMainUISystem.Open -> 卡在加载条。
# ✅ 实测客户端从不主动请求任务（打开任务面板零网络请求），面板纯渲染
#   mAllOnceTaskInfo 且"只在打开时读取、不实时刷新"。因此必须在玩家进主城后
#   由服务端主动下发一次，用户之后打开面板即可看到列表。
PUSH_TASKS = True
# 延迟秒数：102(进场景) 后约 4s 客户端才开始在场景内上报坐标(103)，取 8s 稳妥。
TASK_PUSH_DELAY = 8.0

# ---- 存档（落本地电脑）----
SAVE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "save.json")


def load_save():
    """读取本地存档；没有则返回空 dict。"""
    try:
        with open(SAVE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def write_save(data):
    try:
        with open(SAVE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log("存档写入失败: %r" % e)


_SAVE = load_save()


class Client(threading.Thread):
    def __init__(self, conn, addr):
        super().__init__(daemon=True)
        self.conn = conn
        self.addr = addr
        self.buf = b""
        self.serial = 0
        self.last_peer_serial = 0
        self.account = _SAVE.get("account", "local")
        self.role_name = _SAVE.get("role_name", "")
        self.res_id = int(_SAVE.get("res_id", 18))
        # 等级：早期存档写入过 1（真值），但资源副本/日常活动的等级门禁需要更高等级。
        # 统一取 max(存档, PLAYER_LEVEL)，保证 102 与 901 两条路发同一个值。
        self.level = max(int(_SAVE.get("level", 0)), PLAYER_LEVEL)
        self.closed = False
        self.send_lock = threading.Lock()
        self.in_scene = False          # 是否已收到首个 103 坐标上报
        self.pending_task_push = False # 定时器到点但客户端未进场景时挂起

    @property
    def main_role_index(self):
        """mainRoleIndex 从 1 开始：1=黑剑士(res 18) 2=闪光骑士(res 19)。
        与 CreateRoleSetup.txt 的选择ID 0/1 对应（阶段14 实证）。"""
        return 1 if self.res_id == 18 else 2

    def save(self):
        """把角色数据落盘（阶段 12：存档保存在本机 server/save.json）。"""
        _SAVE.update({
            "account": self.account,
            "role_name": self.role_name,
            "res_id": self.res_id,
            "level": self.level,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        write_save(_SAVE)
        log("   存档已写入 %s" % SAVE_PATH)

    # ---- 阶段16g：按 eFormationType 分别保存出战布阵 ----
    def get_formation(self, type_):
        """取某类战斗的布阵；没有则用默认（保证主指挥官非空）。"""
        table = _SAVE.get("formations") or {}
        wj = table.get(str(type_))
        if wj and len(wj) >= 1 and wj[0]:
            return list(wj)
        return list(DEFAULT_FORMATION)

    def set_formation(self, type_, wj):
        if not wj:
            return
        table = _SAVE.setdefault("formations", {})
        table[str(type_)] = list(wj)
        write_save(_SAVE)

    def send(self, msgid, body=b""):
        # 加锁：延迟推送任务在独立线程执行，避免与主 recv 线程的心跳应答
        # 交错写入同一 socket 导致帧流损坏。
        with self.send_lock:
            self.serial += 1
            frame = make_frame(msgid, body, self.serial)
            log(">> 发送 msgid=%d(%s) 帧长=%d body=%s serial=%d"
                % (msgid, MSG_NAMES.get(msgid, "?"), len(frame), body.hex(), self.serial))
            self.conn.sendall(frame)

    # ---- 阶段16b：任务系统 ----
    def schedule_push_tasks(self, delay=TASK_PUSH_DELAY):
        """延迟推送任务：等客户端建好 MainPlayer 单例、主城加载完成后再发，
        绕开 OnFirstUpdateOnceTask 的 mCompleteMember NRE。"""
        def _run():
            try:
                if self.closed:
                    return
                if not self.in_scene:
                    # 客户端还没进场景（加载中）：挂起，等首个 103 再推，避免 NRE
                    self.pending_task_push = True
                    log("   任务推送定时器到点但客户端未进场景，挂起等待首次坐标上报")
                    return
                self.push_tasks()
                log("   延迟 %.1fs 推送任务完成（登录后自动下发）" % delay)
            except Exception as e:
                log("   延迟推送任务失败: %r" % e)
        t = threading.Timer(delay, _run)
        t.daemon = True
        t.start()

    def schedule_fb_result(self, delay=83.0):
        """命运之镰战斗中主动推送 1001 胜利结算（result=1, starCount=3）。
        必须赶在客户端 90s 倒计时归零之前：归零后事件111监听器已被拆卸，
        再发 1001 会被静默丢弃（阶段16g 实测）。"""
        def _run():
            try:
                if self.closed:
                    return
                self.send(1001, build_fb_result(1, 3))
                log("   倒计时结束前 %.0fs 主动推送 1001 胜利结算(result=1,star=3)" % delay)
            except Exception as e:
                log("   延迟推送 1001 失败: %r" % e)
        t = threading.Timer(delay, _run)
        t.daemon = True
        t.start()

    def push_tasks(self):
        """1103 FirstUpdateOnceTask(主线) + 1101 FirstUpdateDailyTask(日常)。
        推进度存 save.json（once_task_times: {taskId: times}）。"""
        done = _SAVE.get("once_task_times", {})
        entries = [(tid, int(done.get(str(tid), 0)), False)
                   for tid, _, _ in first_tasks(ONCE_TASKS, 5)]
        self.send(1103, build_task_info(entries))
        self.send(1101, build_task_info(first_tasks(DAILY_TASKS, 3)))
        log("   已推送任务：主线 %s / 日常 %s"
            % ([e[0] for e in entries], [e[0] for e in first_tasks(DAILY_TASKS, 3)]))

    def on_fb_victory(self):
        """副本胜利后续：推进主线任务（1104 UpdateOnceTask）+ 结算奖励。"""
        rid = getattr(self, "cur_region", 0)
        done = _SAVE.setdefault("once_task_times", {})
        for tid, _, _ in first_tasks(ONCE_TASKS, 5):
            if task_target_region(tid) == rid:
                done[str(tid)] = int(done.get(str(tid), 0)) + 1
                write_save(_SAVE)
                # delete=false 保持任务可见，finishTimes 满足后客户端亮出领奖按钮
                self.send(1104, build_task_info([(tid, done[str(tid)], False)]))
                # 奖励按 OnceTaskConfig：金币 + 钻石 + 物品（301 物品更新）
                self.send(301, build_goods_update("GOODS104", 1, shining=True))
                log("   主线任务 %d（目标场景 %s）进度 +1，已发奖励更新" % (tid, rid))
                return
        log("   场景 %s 无对应主线任务，仅发结算" % rid)

    def run(self):
        global CURRENT_CLIENT
        log("连接来自 %s:%d" % self.addr)
        CURRENT_CLIENT = self
        try:
            self.conn.settimeout(None)
            while True:
                data = self.conn.recv(65536)
                if not data:
                    log("客户端断开")
                    break
                self.buf += data
                while True:
                    frame, self.buf = parse_frame(self.buf)
                    if frame is None:
                        break
                    total, msgid, crc, serial, body = frame
                    self.last_peer_serial = serial
                    log("<< 收到 msgid=%d(%s) 总长=%d body=%d 字节 serial=%d"
                        % (msgid, MSG_NAMES.get(msgid, "?"), total, len(body), serial))
                    if body:
                        for line in describe_body(body):
                            log("     " + line)
                        log(hexdump(body))
                    self.handle(msgid, body)
        except Exception as e:
            log("异常: %r" % e)
        finally:
            self.closed = True
            try:
                self.conn.close()
            except Exception:
                pass
            log("连接结束 %s:%d" % self.addr)

    def handle(self, msgid, body):
        if msgid == 1:
            # C→S INIT：回 CMSG_INIT_TOClient{SerialNumber}。
            # 关键（NetworkManager::OnInitNetWork rva=0x241ac0）：
            #   IsCenterServer = (SerialNumber == 0)
            #   true  -> 事件 652 -> 发 msgid 10 CCMsgCheckLogin（走中心服）
            #   false -> 事件 652 -> AccountSubmit() -> 发 msgid 101 CCMsgAccountEnter
            self.serial = self.last_peer_serial
            self.send(1, INIT_BODY)
        elif msgid == 101:
            # C→S CCMsgAccountEnter {account,pwd,token,sdkNo,deviceId}
            acc, pwd, tok, sdk, dev = parse_account_enter(body)
            if acc:
                self.account = acc
            log("   账号进入 account=%r pwd=%r token=%r sdkNo=%s device=%r -> 回 101"
                % (acc, pwd, tok, sdk, dev))
            self.send(101, build_account_enter_ret(ACCOUNT_DYN_ID))
            # 第二拍：108 CheckRet code=1 -> 客户端调 GameLoginSuccess
            self.send(108, build_account_enter_check_ret(
                1, self.account or "local", "1"))
            # ⚠ 不要推 1301（NotifyCreateRole）！
            # 实测（server/logs 01:21:15 会话）：不发 1301 时客户端在收到 101 Ret 后
            # 直接发 5401 -> 5402 -> 102(QuestFirstEnterRegion) 进入主城加载；
            # 一旦推 1301，客户端切到建角 UI -> 1001 -> 1302 -> LoadScene(98)
            # 永远停在加载界面（12 秒后 ConnectDetectSystem 弹"网络异常"）。
            # 只有本地存档里还没有角色时才走建角流程。
            if SEND_CREATE_ROLE_NOTIFY or not self.role_name:
                self.send(1301, b"")
        elif msgid == 601:
            # C→S CCMsgReConnect：解析 account / sdkNo
            acc, sdk = parse_reconnect(body)
            if acc:
                self.account = acc
            log("   重连请求 account=%r sdkNo=%s -> 回 901 result=%d"
                % (acc, sdk, RECONNECT_RESULT))
            if RC_BODY is not None:
                self.send(901, RC_BODY)
            else:
                self.send(901, build_reconnect_ret(
                    RECONNECT_RESULT, self.account,
                    level=self.level, main_role_index=self.main_role_index))
                # ⚠ 重连通道必须补齐"登录态"推送（阶段16e 实证）：
                #   901 的 body 只带 player 本体，**不含** 450/4602/201 这些
                #   独立推送消息。少了它们，客户端虽然进了主城，但：
                #     * 缺 450 -> TiaoZhanNanDu 资源副本数据为 null -> 挑战/前往按钮异常
                #     * 缺 4602 -> MainPlayerAttribute.mCCMsgZBZInfo 为 null ->
                #        ChallengeEntryUI.Open() 抛 NRE -> state 永不置 2 ->
                #        「挑战」面板无法关闭（就是用户报的那个死界面）
                #     * 缺 201 -> PVEEnBattle 无主指挥官 -> 进副本 NRE
                #     * 缺 103 -> 重连后角色仍停在旧位置（若旧位置错误例如 (0,0,0)，
                #        会持续 "Touch floor failed!!!"，物理失效无法移动）
                #   顺序：901 先建好 MainPlayer.Object（OnCCMsgZBZInfo 首句要检查它）
                self.send(103, build_set_main_city_born_pos(*BORN_POS))
                self.send(201, build_formation())
                self.send(450, build_resource_fb_update())
                self.send(4602, build_zbz_info())
        elif msgid == 1001:
            # C→S 1001 CCMsgRequestCreateRole{roleName=1, selectID=2}
            # 应答 = 1302 CCMsgRequestCreateRole_Ret{retCode=1}
            # .᜕::OnRequestCreateRole_Ret: retCode==0 -> ShowEnterAni 进入游戏
            name = ""
            sel_id = 0
            try:
                i = 0
                while i < len(body):
                    tag = body[i]; i += 1
                    f, wt = tag >> 3, tag & 7
                    if wt == 2:
                        ln = body[i]; i += 1
                        if f == 1:
                            name = body[i:i + ln].decode("utf-8", "replace")
                        i += ln
                    elif wt == 0:
                        v = 0; sh = 0
                        while body[i] & 0x80:
                            v |= (body[i] & 0x7F) << sh; sh += 7; i += 1
                        v |= (body[i] & 0x7F) << sh; i += 1
                        if f == 2:
                            sel_id = v
            except Exception:
                pass
            log("   1001 创建角色 name=%r selectID=%s -> 回 1302 retCode=0" % (name, sel_id))
            self.role_name = name
            # CreateRoleSetup.txt：选择ID 0 -> 武将 18(黑剑士)，1 -> 19(闪光骑士)
            self.res_id = 18 if sel_id == 0 else 19
            self.save()      # 存档落本地
            self.send(1302, proto.v_field(1, 0))
        elif msgid == 3:
            self.send(3, body)
        elif msgid == 102:
            # C→S 102 QuestFirstEnterRegion。
            # ⚠ 应答号就是 102（S→C 102 注册到 .ᝁ::OnQuestFirstEnterRegionRet），
            #   103 只是"主城出生点"，必须先发（OnQuestFirstEnterRegionRet 读取它）。
            # 102 Ret = CCMsgMainPlayer{dynID,res_id,name,player}
            log("   102 -> 回 103 BornPos%s + 102 CCMsgMainPlayer" % ((BORN_POS,),))
            self.send(103, build_set_main_city_born_pos(*BORN_POS))
            self.send(102, build_main_player(
                ACCOUNT_DYN_ID, self.res_id,
                self.role_name or "冒险者", self.account or "local",
                level=self.level))
            self.send(201, build_formation())   # PVE 出战布阵（主指挥官必须有效）
            # 资源副本数据（450）：不发的后果见 build_resource_fb_update 注释
            # （主城每帧 TiaoZhanNanDu.IsAvailable NRE -> 挑战/前往按钮无响应）。
            self.send(450, build_resource_fb_update())
            # 争霸赛信息（4602）：⚠ 必须发！否则 ChallengeEntryUI.Open() 读
            #   Attribute.mCCMsgZBZInfo.TrunOn 时 NRE -> Open() 中断 ->
            #   state 永远到不了 2 -> Close() 静默返回 -> 「挑战」面板无法返回。
            # 必须在 102 之后发（OnCCMsgZBZInfo 首句检查 MainPlayer.Object != null）。
            self.send(4602, build_zbz_info())
            # 阶段16c：延迟下发任务列表（客户端从不主动请求，必须服务端推）。
            # 立即推会 NRE 卡加载；延后到主城就绪后再发。
            if PUSH_TASKS:
                self.schedule_push_tasks()
            if SEND_DATINGS_EFFECT:
                self.send(5301, b"")   # ⚠ 空 body 会 Instantiate(null) 崩溃
            if SEND_KFHAPPY:
                self.send(6201, b"")
        elif msgid == 201:
            # C→S 201 = CMsgRequestFormation{type}（**请求**，不是应答）。
            # 客户端在需要某类战斗的布阵数据时主动发（登录时 type=0，
            # 打开 JJC 预赛窗 type=1，进命运之镰 type=10 ...）。
            # ⚠ 之前不处理 => mCompleteMember.<对应 XXXEnBattle> 恒为 null
            #   => EmBattleSystem.Open() 里 ldsfld CurrentInfo / ldfld mType 抛 NRE
            #   => 出战阵容/布阵列表 Count=0（阶段16f 遗留问题）。
            # 应答号同为 201，body = CMsgFormation{type 原样回, wj[5]}。
            t, _ = parse_formation(body)
            wj = self.get_formation(t)
            log("   201 CMsgRequestFormation type=%d(%s) -> 回 201 CMsgFormation wj=%s"
                % (t, FORMATION_TYPE_NAMES.get(t, "?"), list(wj)))
            self.send(201, build_formation(t, wj))
        elif msgid == 202:
            # C→S 202 = CMsgFormation{type, wj[5], employ, employPos}
            # 客户端**提交/保存**某类战斗的出战布阵（点"开战"时把当前选择上传）。
            # 服务端存下来，下次该 type 的 201 请求原样返回 => 玩家的选择被记住。
            t, wj = parse_formation(body)
            log("   202 CMsgFormation 提交 type=%d(%s) wj=%s -> 存档"
                % (t, FORMATION_TYPE_NAMES.get(t, "?"), list(wj)))
            self.set_formation(t, wj)
        elif msgid == 331:
            # C→S 331 = CCMsgResouceFBRequest{level=1(难度)}
            # IL 证据（EmBattleSystem::ᜁ rva=0x12b918）：
            #   if (EmBattleSystem.CurrentInfo.mType == 10) {     // 命运之镰
            #       var req = new CCMsgResouceFBRequest();
            #       req.level = DIFFCULTY;                          // field#14016
            #       Send(331, req);  this.Close(); return;
            #   }
            # 即「开战」：客户端把选择上报后关闭布阵界面，等服务端把它送进战斗场景。
            # 应答 = S→C 107 ChangeRegionRet{region_res_id} -> 客户端 LoadScene 战斗场景。
            lv = parse_int_field(body, 1)
            log("   331 CCMsgResouceFBRequest level=%s -> 回 107 ChangeRegionRet region=%d(命运之镰)"
                % (lv, SCYTHE_OF_FATE_REGION))
            self.send(107, pb_int_field(1, SCYTHE_OF_FATE_REGION))
        elif msgid == 332:
            # C→S 332 CCMsgResultFB / CCMsgResultResouceFB{result=1胜 2败}
            # 资源副本类战斗的结算上报。
            # IL 证据（ScytheOfFateController rva=0x42b70 胜 / 0x42ad0 败）：
            #   if (mRegionType == 10) { var m = new CCMsgResultFB();
            #       m.result = 1|2; m.starCount = 3 - GetMemberDeadCount(); Send(332, m); }
            # ⚠ 客户端会把 332 每 ~3s 重发直到服务端应答；实测(S→C) 1001 可解锁
            #   （OnMsgResultFBRet -> 事件111 -> "挑战失败"结算窗）。与 302 走同一条 Ret。
            res = parse_int_field(body, 1)
            if res not in (1, 2):
                res = 2
            log("   332 资源副本结算 result=%d -> 回 1001 结算(varint)" % res)
            self.send(1001, build_fb_result(res, 3 if res == 1 else 0))
            if res == 1:
                self.on_fb_victory()
        elif msgid == 2001:
            # C→S 2001 RequestJJCInfo（登录即发）。回 2001 竞技场面板数据+假对手池。
            # 之前不应答 -> BOB 面板拿空数据 -> SetIcon 空 atlas 名 -> "can not find : Atlas" 异常。
            log("   2001 RequestJJCInfo -> 回 %d 个官方机器人（fixed32+嵌套 BriefInfo）"
                % len(load_jjc_targets()))
            self.send(2001, build_jjc_info(with_targets=True))
        elif msgid == 1801:
            # C→S 1801 RequestQianDaoInfo（登录即发）。回签到面板数据。
            log("   1801 RequestQianDaoInfo -> 回 1801 签到信息")
            self.send(1801, build_qiandao_info())
        elif msgid == 1101 or msgid == 1103:
            # C→S 任务请求（任务 UI 打开时发，与 S→C 同号，双向惯例同 2001/1801）
            self.push_tasks()
        elif msgid == 302:
            # C→S 302 ResultFB{result=1}：副本结束上报（1=胜利 2=失败，如倒计时归零）。
            # 应答 S→C 1001 CCMsgResultFB -> OnMsgResultFBRet -> 事件111（Lua 结算 UI）。
            # 契约 DataFormat=2 -> fixed32。胜利时顺带推进主线任务 + 发奖励。
            res = parse_level_load_finish(body)   # 同样的 {1: varint} 布局
            log("   302 ResultFB result=%s -> 回 1001 结算(fixed32)" % res)
            self.send(1001, build_fb_result(res, 3 if res == 1 else 0))
            if res == 1:
                self.on_fb_victory()
        elif msgid == 104:
            # C→S 104 LevelLoadFinish{region_res_id}：客户端关卡场景加载完成。
            # 必须回 103 BornPos（该关 RegionLogic/<id>_gk.xml 的 BornBos），
            # 否则角色被放在 (0,0,0) -> Touch floor failed -> 无法移动/不刷怪。
            rid = parse_level_load_finish(body)
            self.cur_region = rid
            born = get_region_born_pos(rid) or BORN_POS
            log("   104 LevelLoadFinish region=%s -> 回 103 BornPos%s" % (rid, born))
            self.send(103, build_set_main_city_born_pos(*born))
            # 命运之镰(60)等资源副本：战斗时长 90s 由客户端倒计时控制。
            # 实测（阶段16g）1001 结算必须在倒计时"未归零"时到达客户端——
            # 归零后客户端自己会上报 332 并拆卸事件111监听器，届时再补发 1001
            # 会被静默丢弃（不弹结算窗）。故在 83s 处主动推送胜利结算，
            # 客户端会在倒计时归零瞬间弹出「挑战成功」窗（星级=3-阵亡数）。
            if rid == SCYTHE_OF_FATE_REGION:
                self.schedule_fb_result()
        elif msgid == 2601:
            # C→S 2601 PrizeSecondLoginDayWJ（次日登录奖励领取，空 body）。
            # 客户端 OnGetButtonClicked 仅在 mLeftTimeToSecondLoginDay<=0.001 时发出。
            # 应答 = S→C 3001 -> .ᝁ::OnSecondLoginDayGetPrizeRet：
            #   suiPianCount(1)==0 -> 走"直接获得整卡"分支：
            #   事件347 展示武将（数据用客户端本地 SecondLoginDayPrize.txt：
            #   武将ID 26 狙击手，星级3）+ mIsDrawSecondDayLoginPrized=true + Close。
            log("   2601 次日登录领奖 -> 回 3001 suiPianCount=0（直接给整卡狙击手）")
            self.send(3001, proto.v_field(1, 0))
            # 记录已领，下次登录不再下发倒计时（客户端 tag37 也由存档体现）
            _SAVE["second_login_day_prized"] = True
            write_save(_SAVE)
        elif msgid == 103:
            # C→S 103：客户端每秒上报坐标（主城/副本内）。
            # 首个 103 = 玩家实体已进入场景，作为"主城就绪"的可靠信号；
            # 定时器到点时若客户端尚未进场景，就在这里补推任务。
            if not self.in_scene:
                self.in_scene = True
                if self.pending_task_push:
                    self.pending_task_push = False
                    log("   检测到首个坐标上报，客户端已进场景 -> 2s 后补推任务")
                    self.schedule_push_tasks(2.0)
            # 坐标上报无需应答
        elif msgid == 5401:
            # 5401 双向：C# 注册了 OnNET_CCMsgRequestEquipTransform_Ret，回同号空 body
            log("   5401 -> 回 5401 空 body")
            self.send(5401, b"")
        elif msgid == 5402:
            # 5402 无 C# handler（Lua 报 never process），观察不回应的行为
            log("   5402（无注册 handler）不回应")
        else:
            log("   （尚未实现 msgid=%d 的应答，仅记录）" % msgid)


def parse_account_enter(body):
    """解析 CCMsgAccountEnter{account=1,pwd=2,token=3,sdkNo=4,deviceId=5}。"""
    acc = pwd = tok = dev = ""
    sdk = None
    i = 0
    while i < len(body):
        tag = 0
        shift = 0
        while i < len(body):
            b = body[i]
            i += 1
            tag |= (b & 0x7F) << shift
            shift += 7
            if not (b & 0x80):
                break
        field, wt = tag >> 3, tag & 7
        if wt == 0:
            v = 0
            shift = 0
            while i < len(body):
                b = body[i]
                i += 1
                v |= (b & 0x7F) << shift
                shift += 7
                if not (b & 0x80):
                    break
            if field == 4:
                sdk = v
        elif wt == 2:
            ln = 0
            shift = 0
            while i < len(body):
                b = body[i]
                i += 1
                ln |= (b & 0x7F) << shift
                shift += 7
                if not (b & 0x80):
                    break
            data = body[i:i + ln]
            i += ln
            try:
                s = data.decode("utf-8")
            except Exception:
                s = ""
            if field == 1:
                acc = s
            elif field == 2:
                pwd = s
            elif field == 3:
                tok = s
            elif field == 5:
                dev = s
        else:
            break
    return acc, pwd, tok, sdk, dev


def parse_reconnect(body):
    """解析 CCMsgReConnect，返回 (account, sdkNo)。"""
    acc, sdk = "", None
    i = 0
    while i < len(body):
        tag = 0
        shift = 0
        while i < len(body):
            b = body[i]
            i += 1
            tag |= (b & 0x7F) << shift
            shift += 7
            if not (b & 0x80):
                break
        field, wt = tag >> 3, tag & 7
        if wt == 0:
            v = 0
            shift = 0
            while i < len(body):
                b = body[i]
                i += 1
                v |= (b & 0x7F) << shift
                shift += 7
                if not (b & 0x80):
                    break
            if field == 2:
                sdk = v
        elif wt == 2:
            ln = 0
            shift = 0
            while i < len(body):
                b = body[i]
                i += 1
                ln |= (b & 0x7F) << shift
                shift += 7
                if not (b & 0x80):
                    break
            data = body[i:i + ln]
            i += ln
            if field == 1:
                try:
                    acc = data.decode("utf-8")
                except Exception:
                    acc = ""
        else:
            break
    return acc, sdk


# ---- 阶段13：UDP 控制通道（向当前客户端注入任意 S→C 消息）----
CURRENT_CLIENT = None

def varint(n):
    out = b""
    while True:
        b7 = n & 0x7F
        n >>= 7
        out += bytes([b7 | (0x80 if n else 0)])
        if not n:
            return out

def pb_int_field(tag, value):
    """int32/varint 字段，wire type 0"""
    return varint(tag << 3) + varint(value)

def udp_console(port):
    """UDP 命令行：
       107 <region_id>          发 S2C 107 ChangeRegionRet{region_res_id}
       401 <region_id>          发 S2C 401 FBInfo 结算（空掉落）
       raw <msgid> <hexbody>   发任意帧
       who                      查看当前客户端
    """
    global CURRENT_CLIENT
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    u.bind(("127.0.0.1", port))
    log("UDP 控制通道就绪 127.0.0.1:%d (107 <region_id> / raw <msgid> <hex>)" % port)
    while True:
        try:
            cmd, _ = u.recvfrom(4096)
            parts = cmd.decode("utf-8", "ignore").strip().split()
            if not parts:
                continue
            if parts[0] == "who":
                log("[控制] 当前客户端: %r" % (CURRENT_CLIENT,))
                continue
            if parts[0] == "mp":
                # 重发出生点 + 主玩家数据（进入区域完成包）
                x, y, z = BORN_POS
                CURRENT_CLIENT.send(103, build_set_main_city_born_pos(x, y, z))
                CURRENT_CLIENT.send(102, build_main_player(
                    dyn_id=ACCOUNT_DYN_ID, res_id=CURRENT_CLIENT.res_id,
                    name=CURRENT_CLIENT.role_name or "local",
                    account=CURRENT_CLIENT.account, level=CURRENT_CLIENT.level))
                CURRENT_CLIENT.send(201, build_formation())
                CURRENT_CLIENT.send(450, build_resource_fb_update())
                CURRENT_CLIENT.send(4602, build_zbz_info())
                continue
            if CURRENT_CLIENT is None:
                log("[控制] 无客户端连接，忽略: %r" % (cmd,))
                continue
            if parts[0] == "107" and len(parts) >= 2:
                rid = int(parts[1])
                CURRENT_CLIENT.send(107, pb_int_field(1, rid))
            elif parts[0] == "tasks":
                # 重发任务列表（调试任务 UI）
                CURRENT_CLIENT.push_tasks()
            elif parts[0] == "win" or parts[0] == "lose":
                # 直接注入副本结算（测结算 UI；1001 双编码切换在 fbenc）
                res = 1 if parts[0] == "win" else 2
                enc = parts[1] if len(parts) >= 2 else "f32"
                if enc == "v":
                    body = (proto.v_field(1, res)
                            + proto.v_field(2, 3 if res == 1 else 0))
                else:
                    body = build_fb_result(res, 3 if res == 1 else 0)
                log("[控制] 注入 1001 结算 result=%d 编码=%s" % (res, enc))
                CURRENT_CLIENT.send(1001, body)
            elif parts[0] == "401" and len(parts) >= 2:
                rid = int(parts[1])
                body = pb_int_field(1, rid) + pb_int_field(2, 100) + pb_int_field(3, 50)
                CURRENT_CLIENT.send(401, body)
            elif parts[0] == "raw" and len(parts) >= 2:
                msgid = int(parts[1])
                body = bytes.fromhex(parts[2]) if len(parts) >= 3 else b""
                CURRENT_CLIENT.send(msgid, body)
            else:
                log("[控制] 未知命令: %r" % (cmd,))
        except Exception as e:
            log("[控制] 异常: %r" % e)


def main():
    global INIT_BODY, RECONNECT_RESULT, RC_BODY, ACCOUNT_DYN_ID, BORN_POS
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=9001)
    ap.add_argument("--serial", type=int, default=1,
                    help="INIT 应答的 SerialNumber；0 会让客户端走中心服分支")
    ap.add_argument("--init-body", default="", help="INIT 应答 body 的 hex，如 0801")
    ap.add_argument("--dyn-id", type=int, default=1, help="CSMsgAccountEnterRet.dynID")
    ap.add_argument("--born-pos", default="auto",
                    help="103 主城出生点 x,y,z（float）；auto=自动读 "
                         "GameData/RegionLogic/1_gk.xml 的 <BornBos>（原版真值）")
    ap.add_argument("--rc-body", default="",
                    help="覆盖 901 body 的 hex；传 empty 表示空 body")
    ap.add_argument("--reconnect-result", type=int, default=1,
                    help="901 CCMsgReConnect_Ret 的 result（1=成功 2=失败）")
    ap.add_argument("--console-port", type=int, default=9002,
                    help="UDP 控制通道端口，0=关闭")
    args = ap.parse_args()
    ACCOUNT_DYN_ID = args.dyn_id
    if args.born_pos.strip().lower() == "auto":
        # 主城 = region 1。出生点必须用 1_gk.xml 的 <BornBos>（原版真值），
        # 否则角色被放在 (0,0,0)，而主城地面在 y≈301.5 -> 每帧
        # "Touch floor failed!!!" -> 物理失效 -> 无法移动 / 挑战入口点了没反应。
        BORN_POS = get_region_born_pos(1) or (0.0, 0.0, 0.0)
        log("主城出生点（auto，来自 1_gk.xml BornBos）= %s" % (BORN_POS,))
    else:
        BORN_POS = tuple(float(v) for v in args.born_pos.split(","))
        log("主城出生点（命令行 --born-pos）= %s" % (BORN_POS,))
    if args.init_body:
        INIT_BODY = bytes.fromhex(args.init_body.replace(" ", ""))
    else:
        INIT_BODY = build_init(args.serial)
    RC_BODY = None
    if args.rc_body:
        RC_BODY = b"" if args.rc_body == "empty" else bytes.fromhex(
            args.rc_body.replace(" ", ""))
    RECONNECT_RESULT = args.reconnect_result
    if args.console_port:
        threading.Thread(target=udp_console, args=(args.console_port,),
                         daemon=True).start()
    log("INIT 应答 body = %s" % (INIT_BODY.hex() or "(空)"))
    log("901 result = %d, rc_body=%s" % (RECONNECT_RESULT, RC_BODY.hex() if RC_BODY is not None else "(自动)"))

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((args.host, args.port))
    s.listen(16)
    log("=" * 60)
    log("游戏服监听 %s:%d" % (args.host, args.port))
    log("=" * 60)
    while True:
        conn, addr = s.accept()
        Client(conn, addr).start()


if __name__ == "__main__":
    main()
