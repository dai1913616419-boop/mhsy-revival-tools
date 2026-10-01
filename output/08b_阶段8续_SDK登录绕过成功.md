# 阶段 8（续）：SDK 登录绕过成功 —— 游戏进入自有登录界面

日期：2026-09-29　载体：360 渠道包 `com.fl.mhsy.qihoo` 4.2.0.1（MuMu Android 12）

## 里程碑

```
补丁包安装 → 启动 → 版本检查(本地服务器) → 跳过更新 → Unity 初始化
→ 【360 SDK 登录页已消失】→ 直达游戏自有登录界面（选服 + 进入游戏）
```

截图：`work/shots/shot7.png`（「剑舞者们」登录界面，右下角版本号 4.2.0.1）

## 技术路线（三件套工具，全部就绪）

| 步骤 | 工具 | 说明 |
|---|---|---|
| 1. IL 补丁 | `server/patch_client_dll.py` | `StartLogin` 开头 6 字节 `02 7B 1E000004` → `17 00 00 00 00 00`（`ldc.i4.1` + nop×5），方法体长度不变，dncil 反汇编验证通过 |
| 2. 重打包 | `server/repack_apk.py` | 替换 APK 内 `assets/bin/Data/3a856d…`（Client.dll 载体，4102884 字节不变），剔除旧 META-INF |
| 3. v1 签名 | `server/sign_apk.py` | **手写最小 PKCS#7**（见下），Android 12 验签通过 |

### 签名坑（重要）

`cryptography` 的 `pkcs7.PKCS7SignatureBuilder` 会在认证属性里写 `SMIMECapability`，Android 的 JarVerifier 解析报
`toDerInputStream rejects tag type -96: PKCS9 SMIMECapability attribute not supported` 拒绝安装。
已改为手写 DER 构造 SignedData（只含 contentType + messageDigest 两个属性），CERT.RSA 1276 字节，`Success`。

## 服务器列表（选服）协议 —— 已完全逆向

- 来源：`LoginSystem::FetchServerList` 迭代器（RVA 0x1a78d4）
- 请求：`{ServerListUrl}?_t={Guid 无连字符}`
- 格式：**XML**（`XmlDocument.LoadXml`）：

```xml
<Servers>
  <Area>
    <Sub ID="1" Name="本地服" Status="1" New="true" IP="192.168.0.12" Port="9001"
         Hot="true" OpenDateTime="2026-09-29 00:00:00" Testing="false" />
  </Area>
  <CenterServer IP="192.168.0.12" Port="9001" />
</Servers>
```

字段落位：ID→strServerId、Name→strServerName、Status→strServerStatus、New→strServerIsNew、
IP/Port→服务器地址、ForbiddenSdkNumbers 用 `_` 分割成 int 列表。样例已在 `server/www/Other/serverlist.txt`。

## game.cfg（`GameData/game.cfg`）配置键

| 键 | 作用 |
|---|---|
| `ServerListUrl` | 选服列表 URL（通用） |
| `360_ANDROID_ServerListUrl` | 渠道覆盖版（g_SdkName 前缀，仅 Android 生效） |
| `show_nonsdk_pwd_dlg` | 显示免 SDK 密码框 |
| `choice_server_login` | 选服登录模式 |

**关键条件**：`LoginSystem::Open` 中只有 `show_nonsdk_pwd_dlg=false` 且 `choice_server_login=true`
才 `StartCoroutine(FetchServerList)`。

## 当前卡点（下一轮目标）

serverlist 的 HTTP 请求始终未发出。已排除：
- `ABs/GameData/game.cfg.bytes`（AssetBundle 路径，探针无格式报错 → game.cfg 不走 `OpenTextWithAssetBundle`）
- `files/GameData/game.cfg` 与 sdcard 外部存储两处（已放但无行为差异）
- APK 内无明文 `ServerListUrl`（全包扫描 0 命中）

下一轮入口：完整反汇编 `ResourceControl.ResourceManager::Open`（RVA 0x290624）的迭代器，
确认 `GameData/game.cfg` 的真实读取来源（疑从 APK 内置 AssetBundle 读取）；或行为验证 `Open` 是否真正执行。

## 其他确认

- 点「进入游戏」→ 弹「请选择区服」→ UI 交互正常，验证弹窗可用
- 点「点击选服」无反应（疑列表为空所致）
- `QF.xml` / `Notice.txt` 轮询来自 **Java 层 SDK**（UA=Dalvik），与 Unity 登录流程无关
- hosts（bind mount）在模拟器不重启期间保持有效；重启后需重跑 `setup_mumu_hosts.py`
- 备份：`work/apk/mhsy_qihoo_4201.apk`（原包）、`mhsy_qihoo_4201_patched.apk`（补丁包）
