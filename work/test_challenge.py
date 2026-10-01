"""阶段16e 实测：冷启动 -> 主城 -> 打开「挑战」 -> 点击遮罩返回。
输出：shots/e_*.png + logs_e.txt（含 Unity NRE 堆栈）
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


def adb(*a, **kw):
    subprocess.run([ADB, 'start-server'], capture_output=True)
    subprocess.run([ADB, 'connect', DEV], capture_output=True)
    return subprocess.run([ADB, '-s', DEV] + list(a),
                          capture_output=True, timeout=kw.get('t', 90)).stdout


def tap(x, y, wait=1.5):
    adb('shell', 'input', 'tap', str(x), str(y))
    time.sleep(wait)


def shot(name):
    d = adb('exec-out', 'screencap', '-p')
    p = os.path.join(SHOTS, name + '.png')
    ok = d and len(d) > 1000
    if ok:
        open(p, 'wb').write(d)
    print('  [shot] %s %s' % (name, ('%dB' % len(d)) if ok else 'FAIL'), flush=True)
    return p


def main():
    print('== clear logcat ==', flush=True)
    adb('logcat', '-c')
    logf = open(os.path.join(BASE, 'logs_e.txt'), 'w', encoding='utf-8', errors='replace')
    lc = subprocess.Popen([ADB, '-s', DEV, 'logcat', '-v', 'time'],
                          stdout=logf, stderr=subprocess.DEVNULL)
    print('== force-stop + launch ==', flush=True)
    adb('shell', 'am', 'force-stop', PKG)
    time.sleep(1)
    adb('shell', 'am', 'start', '-n', '%s/%s' % (PKG, ACT))

    for i in range(13):
        time.sleep(5)
        shot('e%02d' % i)
    lc.terminate()
    try:
        lc.wait(timeout=10)
    except Exception:
        lc.kill()
    logf.close()
    print('== done ==', flush=True)


if __name__ == '__main__':
    main()
