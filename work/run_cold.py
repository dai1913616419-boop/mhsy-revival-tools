"""冷启动实测：重启客户端 -> 走登录 -> 抓 logcat + 定时截图。
用于验证 102 里新增 resourceFBData(tag115) 是否消除主城 TiaoZhanNanDu NRE。
用法: run_cold.py [seconds]
"""
import subprocess, time, os, sys

ADB = r'C:/Program Files/Netease/MuMu/nx_main/adb.exe'
DEV = '127.0.0.1:7555'
PKG = 'com.fl.mhsy.qihoo'
ACT = 'com.fl.mhsy.UnityPlayerNativeActivity'
BASE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(BASE, 'shots')
os.makedirs(SHOTS, exist_ok=True)


def adb(*a, timeout=60):
    return subprocess.run([ADB, '-s', DEV] + list(a),
                          capture_output=True, text=True, timeout=timeout)


def adb_raw(*a, timeout=60):
    return subprocess.run([ADB, '-s', DEV] + list(a),
                          capture_output=True, timeout=timeout).stdout


def shot(name):
    d = adb_raw('exec-out', 'screencap', '-p', timeout=90)
    p = os.path.join(SHOTS, name + '.png')
    if d and len(d) > 1000:
        open(p, 'wb').write(d)
        print('  [shot] %s (%dB)' % (name, len(d)), flush=True)
    else:
        print('  [shot] %s FAIL (%dB)' % (name, len(d) if d else 0), flush=True)


def main():
    total = int(sys.argv[1]) if len(sys.argv) > 1 else 75
    adb('shell', 'am', 'force-stop', PKG)
    time.sleep(1)
    adb('logcat', '-c')
    time.sleep(0.5)
    lf = open(os.path.join(BASE, 'logs_cold.txt'), 'w', encoding='utf-8', errors='replace')
    lc = subprocess.Popen([ADB, '-s', DEV, 'logcat', '-v', 'time'],
                          stdout=lf, stderr=subprocess.DEVNULL)
    print('  [logcat] -> work/logs_cold.txt', flush=True)

    adb('shell', 'am', 'start', '-n', '%s/%s' % (PKG, ACT))
    print('  launched', flush=True)

    t0 = time.time()
    i = 0
    while time.time() - t0 < total:
        time.sleep(8)
        i += 1
        shot('cold_%02d' % i)
    lc.terminate()
    try:
        lc.wait(timeout=10)
    except Exception:
        lc.kill()
    lf.close()
    print('done, shots=%d' % i, flush=True)


if __name__ == '__main__':
    main()
