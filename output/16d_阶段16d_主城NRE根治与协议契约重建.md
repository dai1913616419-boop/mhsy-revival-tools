# 阶段 16d — 主城 NRE 根治 + 协议契约重建（阶段性里程碑）

日期：2026-10-01
目标：根治主城每帧 `TiaoZhanNanDu.IsAvailable` NullReferenceException，
     让"挑战"图标与任务"前往"按钮真正可点；同时修复长期存在的**错误契约源**问题。

---

## 1. 本轮最大发现：**契约 DLL 一直是旧版本**

### 现象
- 客户端 `MainPlayer.UnPackData` 读 `CMsgDetailPlayerInfo.resourceFBData`，
  但此前所有契约提取产物（`work/carved/CAB-Protobuf_00002231.dll`，asm=Msg，566784B）
  **根本没有这个属性**：全文搜索 `ResourceFBSaoDangRequireType` 命中 0 次。
- 通过 MemberRef 解析确认客户端引用的目标程序集是 `Msg`：
  ```
  MREF get_resourceFBData  owner=NetProto.CMsgDetailPlayerInfo  scope=ASM:Msg
  MREF get_ResourceFBSaoDangRequireType  owner=NetProto.CMsgDetailPlayerInfo  scope=ASM:Msg
  ```

### 根因
APK 的 `assets/bin/Data/` 下存放的是**不带扩展名的 Unity AssetBundle（文件名=MD5）**。
同一个 `Msg` 程序集存在**两份**：

| APK 内文件 | 大小 | 内含程序集 | `resourceFBData` 命中 | 说明 |
|---|---|---|---|---|
| `assets/bin/Data/c287f4e7...` | 648464 | Msg（旧） | 1 | 此前误用/误雕的源 |
| `assets/bin/Data/3f1bdaed...` | 896728 | **Msg（现行）** | **5** | 运行时真正加载的 |
| `assets/bin/Data/3a856d03...` | 4102884 | Client | 1 | 与 `Client_4201.dll` 同尺寸(4102884) |

> `3a856d03...` 的大小与 `work/apk/Client_4201.dll` **完全一致（4102884）**，
> 反向印证"APK 里这些 hash 文件就是运行时加载的托管程序集"。

### 修复
- 新增 `work/carve_dlls.py`：从任意二进制中按 `MZ`+PE 头+`IMAGE_SIZE` 雕刻并
  用 dnfile 校验 .NET 元数据，输出 `<AssemblyName>.dll`。
- 从 `3f1bdaed...` 雕出正确的 `Msg.dll`（888328B）→ `work/carve/msg/Msg.dll`。

---

## 2. 契约提取器修正（tag / DataFormat 双双纠错）

### 2.1 属性签名解码错误（类型名全变成 raw:hex）
`PropertySig` 首字节是 `0x28`（HASTHIS|PROPERTY），旧代码只判 `0x08`，
导致所有属性类型退化成 `raw:280008` 这种十六进制。已修正。

### 2.2 CustomAttribute blob 布局纠错（Tag 本身是对的，DataFormat 解码错位）
实测 .NET 输出的 named arg 布局为：
```
<0x53 Field | 0x54 Property> <FieldOrPropType> <SerString name> <value>
    FieldOrPropType: 0x02=bool  0x0e=string  0x55=enum(后接 SerString 类型全名)
```
旧代码按 `kind → name → type → value` 解析，DataFormat 值偶尔落到垃圾上。

### 2.3 **重要结论：DataFormat 语义修正**
protobuf-net `DataFormat`：**0=Default 1=ZigZag 2=TwosComplement 3=FixedSize 4=Group**。
- **2 = TwosComplement = varint（不是 fixed32！）**
- 3 才是 FixedSize（fixed32）

本文档同时确认：protobuf-net 的 `ProtoReader.ReadInt32` 对 **varint 与 fixed32 两种
wire type 都接受**，所以"发 varint 也能过、发 fixed32 也能过"是正常现象——
之前"契约写 DF=2 就必须 fixed32"的经验规则**是误判**，不影响既有代码，
但后续实现以本契约 `wire` 字段为准。

### 2.4 新契约产物
`work/extract_contract.py` → `work/messages_full.json`
- **665 个类型**（旧：421），每字段含 `tag / type / dataFormat / wire`
- 旧版备份：`work/messages_full_OLD.json`

---

## 3. 主城 NRE 根治

### 病灶链（已在反汇编中逐环确认）
1. `MainPlayer.UnPackData(CMsgDetailPlayerInfo)`：
   ```
   ldarg.1 ; callvirt get_resourceFBData ; stfld mResourceFBDataList
   ```
   → `mResourceFBDataList` 直接来自 102 的 `CMsgDetailPlayerInfo.resourceFBData`。
2. `TiaoZhanNanDu.IsAvailable(type)`（`DaTingMainUISystem.Update` 每帧调用，
   对 5/6/8/9/10 五种资源副本各调一次）：
   ```
   MainPlayer.GetResourceFBData(type)   // List.Find 找不到 -> null
   ... get_playTime                     // -> NullReferenceException
   ... get_lastPlayTime                 // 之后 DateTime.ParseExact("yyyy-MM-dd HH:mm:ss")
   ```
3. 异常打断 `DaTingMainUISystem.Update` → 主城 HUD 的"挑战"图标、
   任务面板"前往"按钮**点击被吞**（点击事件确实发出，但后续帧更新中断）。

### 关键认识
**450（`CCMsgResouceFBDataUpdate`）只是增量更新**，它内部同样按 `regionType`
在已有列表里 `Find`——列表为空时它自己就抛 NRE（正是
`ᝁ.OnUpdateResouceFBData` 的那条异常）。**必须在 102 里把列表建起来**。

### 修复
新增 `server/game_server.py::build_resource_fb_list()`，在 `build_player()`
（用于 S→C 102 `CCMsgMainPlayer.player`，以及 601/901 重连的 `build_reconnect_ret`）中下发：

```python
# CMsgDetailPlayerInfo.resourceFBData  tag=115  repeated CCMsgResouceFBData
for t in (5, 6, 8, 9, 10):                     # 镜像挑战/死亡躲避/致命游戏/圣诞堡垒/命运之镰
    b += proto.m_field(115,
            proto.v_field(1, t)                        # regionType  df=2 -> varint
          + proto.v_field(2, 0)                        # playTime
          + proto.s_field(3, "2020-01-01 00:00:00"))   # lastPlayTime (CD 已过)
```

### 实测结果（冷启动 → 登录 → 主城）
| 指标 | 修复前 | 修复后 |
|---|---|---|
| `NullReferenceException`（15s 窗口） | 212–323 次 / 6–7s | **0 次** |
| "挑战"图标点击 | 无响应（事件被吞） | **打开挑战面板** |
| 任务面板"前往"按钮 | 无响应 | **可点（面板响应并关闭）** |

---

## 4. 客户端 UI 实测（截图见同目录）

1. `16d_主城完整HUD_挑战与任务按钮可点.png`
   主城 HUD 完整：头像/等级 30/VIP、体力 0/119、金币 10,000、钻石 0，
   顶部（限时神将/排行/签到/邮箱/活动/充值）、右侧竖排（主线/**挑战**/**任务**）。
   **"挑战"按钮出现红点**（=有可玩内容），此前因每帧 NRE 无法正确刷新。
2. `16d_挑战面板_五类资源副本全显示.png`
   点"挑战"→ 面板正常打开，五类资源副本全部渲染：
   死亡躲避 / 竞技场 / 命运之镰 / 致命游戏 / 圣诞堡垒 / 挑战赛，
   **镜像挑战**显示"通关第2章解锁"（真实门槛：cfg `unlockAfterMainFBNormal`）。
3. `16d_每日活动任务面板_真实进度与前往按钮.png`
   点"任务"→ **"每日活动 / 任务"页签 + 真实任务数据**：
   - 副本杀手 0/10（通关任意副本普通难度 10 次）奖励 EXP×100 —— 前往
   - 精英副本杀手 0/3（精英难度 3 次）奖励 EXP×100 —— 前往
   - 勇士试炼 0/2（命运之镰/致命游戏/圣诞堡垒 共 2 次）奖励 EXP×200 —— 前往
4. `16d_JJC退出确认窗.png`
   JJC 预赛对阵图 → 右上关闭 → "你确定要退出挑战赛吗" 确认框 → 退出 → 回主城。

### 附带确认的坐标（设备 1920×1080 横屏）
| 目标 | 坐标 |
|---|---|
| 提示框"知道了" | (956, 733) |
| 公告 X | (1445, 72) |
| 进入游戏 | (962, 988) |
| JJC 关闭 X | **(1700, 80)** |
| JJC "退出" | (750, 728) |
| 右侧"主线/挑战/任务" | x≈1810；y≈395 / 580 / **760** |
| 底部第三方入口 | (1810, 920) |

---

## 5. 遗留与下一步

| 项 | 状态 | 说明 |
|---|---|---|
| `ChallengeEntryUI.Open()` NRE | 新发现，**非致命** | `at MobileGameDemo.ChallengeEntryUI.Open ()`（由 `DaTingMainUISystem.ᜌ` 点击回调触发）。面板仍正常渲染，说明异常发生在后续某个按钮/数据装配步骤。 |
| 任务"前往"的实际跳转 | 半通 | 点击后回到主城（未进入副本选择流程），服务端未见新 C→S 请求。需追 `OnGoTo` 逻辑与目标 region 数据。 |
| 主城地面浅蓝（场景美术缺失） | 遗留 C1 硬墙 | 与 NRE 无关，属资源未渲染。 |
| 副本内移动 → Trigger 真打怪 | 遗留 | 物理已激活，`Touch floor failed!!!` 仍持续刷（约 30 次/秒）。 |
| 副本胜利结算与掉落 / JJC 3203 开战链 / 主线 1103 进度联动 | 待办 | |

### 下一轮建议入口
1. 反汇编 `ChallengeEntryUI.Open` 全量（`work/disasm3.py Client_4201.dll MobileGameDemo.ChallengeEntryUI Open`），
   定位其内部首次解引用的 null 对象（大概率是某个 `GetCfg(...)` 返回 null 或节点 FindChild 落空）。
2. 用新契约 `messages_full.json` 复核全部已实现 S→C 消息的 tag/wire，
   尤其是 `CCMsgRequestOnceTask_Ret` / 签到 / JJC 三处早期靠经验试出来的编码。
3. 追`Touch floor failed!!!` 的调用点，确认主城与副本的地面碰撞体来源。

---

## 6. 涉及文件

| 文件 | 变更 |
|---|---|
| `server/game_server.py` | 新增 `build_resource_fb_list()`；`build_player()` 追加 tag 115 |
| `work/carve_dlls.py` | 新增：AssetBundle 内 .NET 程序集雕刻器 |
| `work/carve/msg/Msg.dll` | 新增：**现行** Msg 程序集（888328B） |
| `work/extract_contract.py` | 新增：修正版契约提取器（正确 tag/type/DataFormat） |
| `work/messages_full.json` | 重建：665 类型 |
| `work/messages_full_OLD.json` | 备份：旧 421 类型 |
| `work/dump_types.py` / `work/protomember.py` | 新增：类型/属性诊断工具 |
| `work/crop_png.py` / `work/goto_task.py` / `work/run_cold.py` | 新增：截图裁剪与实机自动化脚本 |
