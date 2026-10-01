"""反复冷启动直到客户端稳定存活（houdini 转译缓存冷抖规避）。
用法: relaunch_until_alive.py [最大次数] [存活判定秒数]
"""
import subprocess
import sys
import time
import os
import struct

ADB = r'C:/Program Files/Netease/MuMu/nx_main/adb.exe'
DEV = '127.0.0.1:7555'
BASE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(BASE, 'shots')
PKG = 'com.fl.mhsy.qihoo'
ACT = 'com.fl.mhsy.UnityPlayerNativeActivity'

MAXN = int(sys.argv[1]) if len(sys.argv) > 1 else 5
SETTLE = int(sys.argv[2]) if len(sys.argv) > 2 else 50


def adb(*a, t=90):
    subprocess.run([ADB, 'start-server'], capture_output=True)
    subprocess.run([ADB, 'connect', DEV], capture_output=True)
    return subprocess.run([ADB, '-s', DEV] + list(a),
                          capture_output=True, timeout=t).stdout


def shot(name):
    d = adb('exec-out', 'screencap', '-p')
    if not d or len(d) < 1000:
        return None
    p = os.path.join(SHOTS, name + '.png')
    open(p, 'wb').write(d)
    w, h = struct.unpack('>II', d[16:24])
    return (p, w, h, len(d))


for n in range(1, MAXN + 1):
    print('--- 尝试 %d/%d ---' % (n, MAXN), flush=True)
    adb('shell', 'am', 'force-stop', PKG)
    time.sleep(1)
    adb('shell', 'am', 'start', '-n', '%s/%s' % (PKG, ACT))
    time.sleep(SETTLE)
    pid = adb('shell', 'pidof', PKG).decode('utf-8', 'ignore').strip()
    s = shot('r%02d' % n)
    print('   pid=%r  shot=%s' % (pid, (s[1:3], s[3]) if s else None), flush=True)
    if pid:
        print('存活！停在第 %d 次。' % n, flush=True)
        break
    time.sleep(3)
