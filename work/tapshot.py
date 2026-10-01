"""受控点击+截图。
用法:
    tapshot.py shot <name>               只截图
    tapshot.py tap <x> <y> <name>        点击后截图
    tapshot.py seq "<x,y,name;x,y,name>" 连续操作
"""
import subprocess
import sys
import time
import os

ADB = r'C:/Program Files/Netease/MuMu/nx_main/adb.exe'
DEV = '127.0.0.1:7555'
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shots')
os.makedirs(SHOTS, exist_ok=True)


def adb(*a, t=90):
    subprocess.run([ADB, 'start-server'], capture_output=True)
    subprocess.run([ADB, 'connect', DEV], capture_output=True)
    return subprocess.run([ADB, '-s', DEV] + list(a),
                          capture_output=True, timeout=t).stdout


def tap(x, y):
    adb('shell', 'input', 'tap', str(int(x)), str(int(y)))


def shot(name):
    d = adb('exec-out', 'screencap', '-p')
    p = os.path.join(SHOTS, name + '.png')
    if d and len(d) > 1000:
        open(p, 'wb').write(d)
        print('  %s -> %s (%dB)' % (name, p, len(d)), flush=True)
        return p
    print('  %s 截图失败' % name, flush=True)
    return None


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'shot':
        shot(sys.argv[2])
    elif cmd == 'tap':
        x, y, name = sys.argv[2], sys.argv[3], sys.argv[4]
        tap(x, y)
        time.sleep(1.5)
        shot(name)
    elif cmd == 'seq':
        for item in sys.argv[2].split(';'):
            parts = item.split(',')
            x, y, name = parts[0], parts[1], parts[2]
            tap(x, y)
            time.sleep(1.5)
            shot(name)
