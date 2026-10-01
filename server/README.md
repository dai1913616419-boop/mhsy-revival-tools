# 本地更新服务器（梦幻神域 离线复活）

冒充已失效的 `game.360joy.com.cn`，给客户端喂我们控制的版本清单和补丁资源。
纯 Python 标准库，无第三方依赖。

## 目录结构

```
server/
├── update_server.py       # 服务器主程序
├── update_config.json     # 配置（版本号、端口、目录）
├── make_patch.py          # 生成补丁包（MD5 清单 + 资源）
├── patch_apk_version.py   # 改 APK 副本里的更新服域名（备用方案）
├── www/                   # 对外静态根目录
│   └── Android/UpdateRoot/
│       ├── Version/Version.bytes
│       └── IncrementPack/<版本>/...
├── patches/<版本>/        # 补丁源文件（按客户端内路径摆放）
├── mirror/                # （可选）从原 APK 提取的原始资源
└── logs/                  # 请求日志
```

## 启动

```bash
# 模式 A：跳过更新（server_version 与客户端内置 4.0.0.2 相同）
python update_server.py

# 模式 B：下发补丁
python make_patch.py 4.0.0.3     # 先把要改的文件放进 patches/4.0.0.3/
python update_server.py --version 4.0.0.3

# 换端口（80 被占用时）
python update_server.py --port 8080
```

默认监听 `0.0.0.0:80`。客户端请求的是 http，所以端口必须是 80，
否则需要用改包方案把端口写进 APK。

## 自测

```bash
curl http://127.0.0.1/Android/UpdateRoot/Version/Version.bytes
# 期望输出：
# http://game.360joy.com.cn/Android/UpdateRoot/Version|http://game.360joy.com.cn/Android/UpdateRoot/IncrementPack|4.0.0.2
```

## 客户端重定向（必做）

客户端只会访问 APK 里写死的 `game.360joy.com.cn`，二选一：

**方案 1 — 改 hosts（推荐）**

MuMu 一键脚本（自动找 adb、连端口、拿 root、写 hosts、可选装 APK）：

```bash
python setup_mumu_hosts.py                        # 只改 hosts
python setup_mumu_hosts.py --install "<apk路径>"   # 顺带安装
```

手动版：

```bash
adb root
adb remount
adb shell "echo '192.168.0.12 game.360joy.com.cn' >> /system/etc/hosts"
```

**方案 2 — 改 APK 副本**（hosts 改不动时的兜底）

```bash
python patch_apk_version.py --host 192.168.0.12    # 产出未签名副本
python sign_apk.py <副本>.patched.apk --inplace    # 纯 Python 的 v1 签名
adb install -r <副本>.patched.apk
```

`sign_apk.py` 用 `cryptography` 手工实现 v1 签名（MANIFEST.MF / CERT.SF / CERT.RSA），
本机没有 JDK 也能用。已装 `cryptography 50.0.1`。

## 请求日志

所有请求写入 `logs/update_server.log` 并实时打印，
未知路径也会记 404 —— 用来侦察客户端还访问了什么。

## 注意事项

- 客户端的两个服务器域名只来自 APK 内置 `Version.bytes`，服务器下发的新地址无效
- Android 9+ 默认禁用明文 HTTP，模拟器请选 Android 5.1 / 7.1
- 原始 APK 全程只读，不做任何修改
