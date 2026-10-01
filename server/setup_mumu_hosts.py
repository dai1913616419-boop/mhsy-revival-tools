#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MuMu 模拟器一键配置：连接 adb → 拿 root → 改 hosts → 把更新服域名指到本地 PC。

用法：
  python setup_mumu_hosts.py                      # 只改 hosts
  python setup_mumu_hosts.py --install "<apk>"    # 顺便装 APK
  python setup_mumu_hosts.py --host 192.168.0.12  # 指定 PC 的局域网 IP
  python setup_mumu_hosts.py --port 7555          # 手动指定 adb 端口

改完后客户端访问 game.360joy.com.cn 就会打到本机 80 端口的 update_server.py。

实测结论（MuMu 12, Android 12, user 版）：
  - adb root 无效（debuggable=0），但 `su 0` 可拿真 root
  - /system 所在块设备只读（blockdev --getro = 1），remount 必败
  - 可行方案：bind mount 覆盖 /system/etc/hosts —— 挂载点层面覆盖，
    不需要写块设备。**模拟器重启后失效，每次启动后重跑本脚本。**
"""

import argparse
import os
import socket
import subprocess
import sys
import time

# 常见模拟器 adb 端口：MuMu 12/15、MuMu 经典版、夜神、雷电
CANDIDATE_PORTS = [7555, 16384, 16400, 16416, 62001, 21503, 5555]

ADB_CANDIDATES = [
    r"C:\Program Files\Netease\MuMu\nx_main\adb.exe",
    r"C:\Program Files\Netease\MuMu\nx_device\15.0\shell\adb.exe",
    r"C:\Program Files\MuMu\emulator\MuMuPlayer\shell\adb.exe",
    "adb",
]

TARGET_DOMAIN = "game.360joy.com.cn"


def find_adb():
    for p in ADB_CANDIDATES:
        if p == "adb":
            continue
        if os.path.isfile(p):
            return p
    try:
        subprocess.run(["adb", "version"], capture_output=True, check=True)
        return "adb"
    except Exception:
        return None


def run(adb, args, quiet=False):
    r = subprocess.run([adb] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not quiet:
        out = (r.stdout or "").strip()
        if out:
            print("   %s" % out.replace("\n", "\n   "))
    return r


def detect_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("223.5.5.5", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def connect(adb, port=None):
    ports = [port] if port else CANDIDATE_PORTS
    for p in ports:
        print("  尝试 127.0.0.1:%d ..." % p)
        r = run(adb, ["connect", "127.0.0.1:%d" % p], quiet=True)
        out = (r.stdout or "") + (r.stderr or "")
        if "connected" in out.lower():
            print("  ✓ 已连接 127.0.0.1:%d" % p)
            return "127.0.0.1:%d" % p
    return None


def sh(adb, dev, cmd):
    """在指定设备上以 root 执行 shell 命令。"""
    r = subprocess.run([adb, "-s", dev, "shell", "su 0 sh -c %s" % _q(cmd)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout or "") + (r.stderr or "")


def _q(s):
    """给远程 sh -c 用的单引号包裹。"""
    return "'" + s.replace("'", "'\\''") + "'"


def wait_for_device(adb, dev_hint, timeout=60):
    print("  等待设备上线 ...")
    end = time.time() + timeout
    while time.time() < end:
        r = subprocess.run([adb, "devices"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        lines = [l for l in (r.stdout or "").splitlines() if "\tdevice" in l]
        for l in lines:
            d = l.split("\t")[0]
            if dev_hint and dev_hint not in d:
                continue
            print("  ✓ 设备就绪: %s" % d)
            return d
        time.sleep(2)
    return None


def ensure_root(adb, dev):
    print("[3] 获取 root ...")
    out = sh(adb, dev, "id")
    if "uid=0" in out:
        print("  ✓ su 0 可用（真 root）")
        return True
    # 退路：adb root（部分镜像支持）
    run(adb, ["root"], quiet=True)
    time.sleep(2)
    out = subprocess.run([adb, "-s", dev, "shell", "id"], capture_output=True,
                         text=True, encoding="utf-8", errors="replace").stdout or ""
    if "uid=0" in out:
        print("  ✓ adb root 生效")
        return True
    print("  ✗ 拿不到 root。请在 MuMu「设置中心 → 其他设置」打开「root 权限」后重启模拟器。")
    return False


def setup_hosts(adb, dev, host):
    print("[4] 配置 hosts: %s -> %s" % (TARGET_DOMAIN, host))

    cur = sh(adb, dev, "cat /system/etc/hosts")
    entry = "%s %s" % (host, TARGET_DOMAIN)
    lines = [l for l in cur.splitlines() if l.strip() and TARGET_DOMAIN not in l]
    lines.append(entry)
    # 写到 /data（可写），再 bind mount 覆盖
    remote = "/data/local/tmp/hosts.mhsy"
    content = "\n".join(lines) + "\n"
    sh(adb, dev, "printf %s > %s" % (_q(content.replace("\n", "\\n")), remote))

    out = sh(adb, dev, "mount -o bind %s /system/etc/hosts; echo rc=$?" % remote)
    if "rc=0" not in out:
        print("  bind mount 失败：")
        print("   " + out.strip().replace("\n", "\n   "))
        return False
    print("  ✓ bind mount 成功（模拟器重启后需重跑本脚本）")

    # 验证
    out = sh(adb, dev, "cat /system/etc/hosts")
    print("  当前 /system/etc/hosts:")
    for l in out.splitlines():
        print("    %s" % l)
    return entry in out


def verify_http(adb, dev, channel="Android_90"):
    print("[5] 验证域名劫持（模拟器内 curl）...")
    url = "http://%s/%s/UpdateRoot/Version/Version.bytes" % (TARGET_DOMAIN, channel)
    out = subprocess.run([adb, "-s", dev, "shell",
                          "curl -s -m 6 -o /dev/null -w '%%{http_code} %%{remote_ip}' %s" % url],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    r = (out.stdout or "").strip()
    ok = r.startswith("200") and "192.168" in r or "10.0.2" in r
    print("  %s -> %s %s" % (url, r, "✓" if ok else "✗"))
    return ok


def show_info(adb, dev):
    print("[6] 设备信息")
    for prop in ["ro.product.model", "ro.build.version.release", "ro.product.cpu.abi",
                 "ro.product.cpu.abilist"]:
        r = subprocess.run([adb, "-s", dev, "shell", "getprop", prop],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        print("  %-28s %s" % (prop, (r.stdout or "").strip()))


def main():
    ap = argparse.ArgumentParser(description="MuMu 模拟器 hosts 一键配置")
    ap.add_argument("--host", default=None, help="PC 局域网 IP，默认自动探测")
    ap.add_argument("--port", type=int, default=None, help="adb 端口，默认自动尝试")
    ap.add_argument("--install", default=None, help="顺便安装 APK")
    ap.add_argument("--channel", default="Android_90", help="验证用的渠道路径，默认 Android_90")
    args = ap.parse_args()

    host = args.host or detect_local_ip()
    print("=" * 60)
    print("MuMu 模拟器 hosts 配置（bind mount 版）")
    print("  目标域名 : %s" % TARGET_DOMAIN)
    print("  指向     : %s" % host)
    print("=" * 60)

    print("[1] 定位 adb ...")
    adb = find_adb()
    if not adb:
        print("  ✗ 没找到 adb.exe。MuMu 自带: C:\\Program Files\\Netease\\MuMu\\nx_main\\adb.exe")
        return 1
    print("  ✓ %s" % adb)

    print("[2] 连接模拟器（需先启动 MuMu）...")
    dev = connect(adb, args.port)
    if not dev:
        print("  ✗ 连不上。请确认 MuMu 已启动并进入桌面。")
        return 1
    dev = wait_for_device(adb, dev) or dev

    if not ensure_root(adb, dev):
        return 1
    ok = setup_hosts(adb, dev, host)
    if ok:
        verify_http(adb, dev, args.channel)
    show_info(adb, dev)

    if args.install:
        print("[7] 安装 APK: %s" % args.install)
        r = run(adb, ["-s", dev, "install", "-r", args.install])
        out = (r.stdout or "") + (r.stderr or "")
        if "no matching abis" in out.lower():
            print("\n  ⚠ INSTALL_FAILED_NO_MATCHING_ABIS：该实例不支持 32 位 armeabi-v7a。")

    print("=" * 60)
    if ok:
        print("hosts 已生效。启动 update_server.py 后在模拟器里打开游戏。")
        print("观察请求： server/logs/update_server.log")
        print("注意：模拟器每次重启后需重跑本脚本（bind mount 不持久）。")
    else:
        print("hosts 配置未确认，请把上面输出贴给助手分析。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
