"""冷启动客户端 + 逐步截图（阶段16f 出生点修复验证）。
用法:
  run_login.py boot          冷启动并每 10s 截图一次
  run_login.py tap x y name  单次点击 + 截图
  run_login.py wait n name   等 n 秒 + 截图
"""
import subprocess
import sys
import time
import os

ADB = r'C:/Program Files/Netease/MuMu/nx_main/adb.exe'
DEV = '127.0.0.1:7555'
BASE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(BASE, 'shots')
PKG = 'com.fl.mhsy.qihoo'
ACT = 'com.fl.mhsy.UnityPlayerNativeActivity'


def adb(*a, t=90):
    subprocess.run([ADB, 'start-server'], capture_output=True)
    subprocess.run([ADB, 'connect', DEV], capture_output=True)
    return subprocess.run([ADB, '-s', DEV] + list(a),
                          capture_output=True, timeout=t).stdout


def shot(n):
    d = adb('exec-out', 'screencap', '-p')
    p = os.path.join(SHOTS, n + '.png')
    if d and len(d) > 1000:
        open(p, 'wb').write(d)
    print('  [shot] %s %dB' % (n, len(d) if d else 0), flush=True)


def alive():
    return (adb('shell', 'pidof', PKG) or b'').decode().strip()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'boot'
    if mode == 'boot':
        adb('logcat', '-c')
        adb('shell', 'am', 'force-stop', PKG)
        time.sleep(1)
        adb('shell', 'am', 'start', '-n', '%s/%s' % (PKG, ACT))
        for i in range(8):
            time.sleep(10)
            pid = alive()
            print('  t=%ds pid=%s' % ((i + 1) * 10, pid), flush=True)
            shot('L%02d' % i)
            if not pid:
                print('  !! DEAD at t=%ds' % ((i + 1) * 10), flush=True)
                break
    elif mode == 'tap':
        x, y, n = sys.argv[2], sys.argv[3], sys.argv[4]
        w = float(sys.argv[5]) if len(sys.argv) > 5 else 2.0
        adb('shell', 'input', 'tap', x, y)
        time.sleep(w)
        shot(n)
    elif mode == 'wait':
        n_sec = float(sys.argv[2])
        time.sleep(n_sec)
        shot(sys.argv[3])


if __name__ == '__main__':
    main()
