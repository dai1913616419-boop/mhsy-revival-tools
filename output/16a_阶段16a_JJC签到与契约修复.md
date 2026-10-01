# 阶段16a：C1-b 数据补齐（JJC + 签到）+ 契约解析器重大修复

日期：2026-10-01 晚　|　模式：C1-b（程序化补齐缺失数据源）

---

## 一、C1-b 的实质与成果

排查发现"图集缺失"（can not find : Atlas）的真正根因**不是资源文件缺失**，
而是**服务端数据缺失**：JJC 信息请求（C→S 2001）从未被应答 → 竞技场/预赛数据为空 →
UI 拿到空 atlas 名 → 异常链打断了 BOB 预赛窗初始化（导致 X 关不掉）。

因此 C1-b 落地为「服务端补齐数据」：
- ✅ **S→C 2001**（JJC 面板：我的防守战力/排名/剩余挑战次数 + 假对手池"暗影剑圣/烈焰法师/圣光守卫"）
- ✅ **S→C 1801**（签到面板：年月/累计天数/每日 prizeStatus）
- **效果：`can not find` 异常从每次登录刷屏 → 0；"预赛"对阵图显示完整假玩家数据**
  （萌萌弗瑞德/回归贝基/星月大熊…+ 我们的角色"爱弗里达"，头像等级齐全）

## 二、契约解析器重大修复（重要资产升级）

`work/parse_protobuf_full.py` 两个 bug 修复 + 一项新能力：

1. **同名属性覆盖 bug**：原实现用属性名字符串做全局 tag 表 key，不同消息类型的
   同名属性（如两个类型都有 RankIndex）互相覆盖 → tag 全错。改为按 Property 表 rid 唯一索引。
2. **DataFormat 提取**：ProtoMember 的 CustomAttribute blob 尾部带 DataFormat 枚举值。
   **实测规则：DF=2 的 int 字段必须用 fixed32 编码，发 varint 客户端直接抛
   ProtoException: Invalid wire-type**（JJC Ret 顶层 tag1-4 实锤）。
   现在 `messages_full.json` 每个字段带 `dataFormat`，后续实现任何消息先查它。

## 三、遗留（下轮继续）

1. **JJCChallengeTargetBriefInfo 子消息仍抛 ProtoException**：
   varint / fixed32 两版都炸在 `Read(BriefInfo)→StartSubItem`，炸点与顶层编码无关，
   需要字段级二分（只发 tag1 → 逐个加字段）。当前影响小：主城 UI 与预赛窗均正常显示。
2. **主城地面浅蓝**（无场景渲染）尚未排查——阶段12-14 时主城有地面，回退点待查。
3. JJC"挑战"按钮 → 对战流程（3203 开战链）待实现。

## 四、给用户的答复记录

- **C1-b 已按此精神执行**（实际比预想更便宜——缺的是数据不是资源文件）。
- **真实玩家对战**：原版是异步 PVP（打镜像），档1（AI 假人池，已起步）即可完整还原原版体验；
  档2（真·多人联机）需第二台设备 + 服务端多连接改造，等你有设备再开。

---

*改动文件：server/game_server.py（2001/1801 应答）、work/parse_protobuf_full.py（bug 修复+DF）、
work/messages_full.json（含 dataFormat 的修正版契约）。日志：/tmp/gs2*.log*
