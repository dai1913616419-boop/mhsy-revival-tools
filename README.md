# 梦幻神域（剑舞者们）离线复活工程 — 工具与研究文档（公开部分）

对已停服手游《梦幻神域》（Android / Unity 4.6.6f2 + Mono）的**逆向分析与本地服务端重建**研究记录。

本仓库**只包含自己编写的代码与文档**：

- `server/` — 本地服务端（纯 Python，无第三方依赖）
- `work/` — 逆向分析工具链（dnfile / dncil 反汇编、协议契约提取、实测自动化）
- `output/` — 各阶段研究报告（可行性评估 → 协议分析 → 副本全链路）

---

## ⚠️ 声明

1. **本仓库不含**任何 APK、游戏客户端二进制、美术资源、Lua 源码或配置表 ——
   这些属于原厂商受版权保护的内容，仅保存在**私有研究存档**中，不对外分发。
2. 本项目为**个人学习研究**用途：网络通信协议分析、Unity Mono 程序集逆向方法、
   protobuf-net 序列化行为研究。
3. **禁止**用于商业化运营、公开开设私服、或对外分发游戏客户端。
4. 本仓库中的工具（反汇编器、契约提取器等）是通用的 .NET / Unity 分析工具，
   可应用于任何 Unity Mono 项目。

---

## 最新验证：原始新手开场与双模式启动

- 新增独立 `server/opening_server.py`（TCP 9003）：新角色、原始引导、1001–1003 关卡、招募、首个任务、首次进阶与持久化。
- [构建、部署与测试说明](launch-build/README.md)及[真实验证结论](launch-build/OPENING-VERIFIED.md)。桌面 **MHSY Opening** / **MHSY Local Game** 使用不同存档并选择对应 APK。
- `prepare_launch.py` 和 `launch-build/` 只发布自编源代码/研究文档；构建及 Opening 服务/协议测试需另行持有合法的私有客户端和配置数据。
- 不发布 APK、客户端程序集、游戏配置表、美术截图、签名材料或本地角色存档。报告中的截图及完整 QA 证据仅保存在私有研究存档。
- 原有 Demo 服保留，不能将其预置角色/演示性结算行为当作 Opening 的真实新角色路径。

## 一、目录结构

```
.
├── server/                 本地服务端
│   ├── game_server.py      # 游戏服 (TCP 9001)：登录/建角/进主城/副本/结算/重连
│   ├── update_server.py    # 更新服 (HTTP 80)：版本校验/服务器列表/公告
│   ├── proto.py            # protobuf 最小编码助手（varint/fixed32/string/嵌套）
│   ├── setup_mumu_hosts.py # 模拟器 hosts 劫持
│   ├── patch_*.py          # 客户端程序集 IL 补丁生成脚本
│   ├── make_patch.py / patch_client_dll.py / repack_apk.py / sign_apk.py
│   └── start.bat           # 一键启动
├── work/                   逆向工具链（61 个脚本）
│   ├── ildump.py           # 按方法名反汇编
│   ├── ildump_rva.py       # 按 RVA 反汇编（解决同名重载）
│   ├── carve_dlls.py       # 从 AssetBundle 雕刻 .NET 程序集
│   ├── extract_contract.py # 程序集 → protobuf 契约 JSON（tag/type/dataFormat/wire）
│   ├── dump_enum.py        # 导出托管枚举成员
│   ├── field_owner.py      # 字段号 → 所属类型 + 字段名
│   ├── findm.py / find_handler.py / find_callers.py / find_fieldrefs.py / find_send.py
│   ├── kctl.py             # UDP 控制通道客户端
│   ├── ulog2.py            # Unity logcat 提取（适配新版双列格式）
│   └── ...
└── output/                 阶段报告（23 份）
    ├── 00_可行性评估报告.md
    ├── 04_身份鉴定报告.md
    ├── 05_配置表格式规范.md
    ├── 06_更新服协议与重定向方案.md
    ├── 08_阶段8_SDK登录链逆向与补丁通道.md
    ├── 13_阶段13_副本链路进展.md
    ├── 15_阶段15_副本结算与战斗激活.md
    ├── 17_阶段16g_出战阵容与命运之镰全链路打通.md
    └── ...
```

> 报告正文中的 `.png` 引用指向实测截图，截图仅存于私有存档，公开仓库不附。

---

## 二、快速开始（本地服务端）

```bat
cd server
python update_server.py                                   :: HTTP 80
python game_server.py --port 9001 --serial 1 --dyn-id 1   :: TCP 9001
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--port` | 9001 | 游戏服 TCP 端口 |
| `--serial` | 1 | INIT 应答 SerialNumber（**0 会让客户端走中心服分支**） |
| `--dyn-id` | 1 | `CSMsgAccountEnterRet.dynID` |
| `--born-pos` | auto | 主城出生点（默认从关卡配置读取） |

运行时日志在 `server/logs/`（git 已忽略）。

---

## 三、技术要点速览

### 帧格式
```
[总长 u32 LE][msgid u16 LE][crc32 u32 LE][serial u16 LE][body]
```
CRC = `zlib.crc32(body)`；客户端不校验 serial。

### 部分协议（完整分析见 output/ 报告）

| msgid | 方向 | 内容 |
|---|---|---|
| 1 | 双向 | INIT 握手 |
| 101 | S→C | `CSMsgAccountEnterRet{dynID, mainRoleIndex, svrCurTime, ...}` |
| 102 | S→C | `CCMsgMainPlayer{dynID, res_id, name, player}` |
| 103 | S→C | `CCMsgMainCityBornPos{x, y, z fixed32}` |
| 104 | C→S | `LevelLoadFinish{region_res_id}` |
| 107 | S→C | `ChangeRegionRet{regionId}` |
| 201 | 双向 | `CMsgRequestFormation{type}` / `CMsgFormation{type, wj[5]}` |
| 302 / 332 | C→S | 结算上报 → S→C 1001 |
| 331 | C→S | 资源副本开战请求 |
| 601 / 901 | 双向 | 重连 |

### 逆向方法（可复用于其他 Unity Mono 项目）

- **APK 内 `assets/bin/Data/<32位md5>` 即运行时托管程序集本体**（无扩展名）。
  同一程序集可能有多版本；用客户端 MemberRef 反查 `TypeRef.ResolutionScope = AssemblyRef`
  并核对成员名来判定哪份是现行版本。
- **IL offset 与 RVA 存在固定差值** `D = method.Rva - instructions[0].offset`，
  按 RVA 定位代码段时必须用 `il_offset + D`。
- **混淆后的同名重载极多**（`EmBattleSystem` 有 60+ 个 `ᜀ`），按名字反汇编会串，
  必须按 RVA（`ildump_rva.py`）。
- **protobuf-net `DataFormat` 语义**：0=Default 1=ZigZag **2=TwosComplement(varint)**
  3=FixedSize(fixed32) 4=Group；`ProtoReader.ReadInt32` 对 varint 与 fixed32 **都接受**，
  因此不能只看元数据判定 wire type，必须实测。
- **`Open()/Close()` 状态机陷阱**：若 `Open()` 最后一条指令才置 `state = 2`，
  而 `Close()` 首句 `if (state != 2) return;`，则 Open 中途任何异常都会让面板永久锁死。
  定位方法：找 Open 里读取、且唯一写入点是某条 S→C 消息的字段。

---

## 四、依赖

服务端**零第三方依赖**（Python 3 标准库）。

逆向工具需要：
```
pip install dnfile dncil
```

---

## 五、许可

代码与文档按研究用途提供。请勿将本仓库内容用于商业运营或分发受版权保护的游戏资产。
