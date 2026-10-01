"""受控实测脚本：拉起游戏 -> 走完登录/建角 -> 抓 logcat 与分步截图

用法: play.py [boot|flow|create|watch|log|shot]
坐标基于 1920x1080 横屏（MuMu 12）。
"""
import subprocess, time, sys, os, signal

ADB = r'C:/Program Files/Netease/MuMu/nx_main/adb.exe'
DEV = '127.0.0.1:7555'
BASE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(BASE, 'shots')
os.makedirs(SHOTS, exist_ok=True)
PKG = 'com.fl.mhsy.qihoo'
ACT = 'com.fl.mhsy.UnityPlayerNativeActivity'

PT_ENTER = (915, 1034)
PT_OK = (942, 759)
PT_NOTICE_X = (1476, 84)
PT_DICE = (1209, 1058)
PT_START = (1600, 1050)

_lc = None


def ensure():
    """确保 adb 守护 + 设备在线"""
    subprocess.run([ADB, 'start-server'], capture_output=True, timeout=30)
    subprocess.run([ADB, 'connect', DEV], capture_output=True, timeout=30)


def adb(*args, **kw):
    ensure()
    r = subprocess.run([ADB, '-s', DEV] + list(args),
                       capture_output=True, text=True,
                       timeout=kw.get('timeout', 60))
    return r.stdout


def adb_raw(*args, **kw):
    ensure()
    return subprocess.run([ADB, '-s', DEV] + list(args),
                          capture_output=True, timeout=kw.get('timeout', 60)).stdout


def tap(x, y, wait=1.5):
    adb('shell', 'input', 'tap', str(x), str(y))
    time.sleep(wait)


def shot(name):
    d = adb_raw('exec-out', 'screencap', '-p', timeout=60)
    p = os.path.join(SHOTS, name + '.png')
    if d and len(d) > 1000:
        open(p, 'wb').write(d)
        print('  [截图] %s (%dB)' % (name, len(d)))
    else:
        print('  [截图] %s 失败 (%dB)' % (name, len(d) if d else 0))
    return p


def launch():
    adb('shell', 'am', 'force-stop', PKG)
    time.sleep(1)
    adb('shell', 'am', 'start', '-n', '%s/%s' % (PKG, ACT))
    print('  已拉起 %s' % PKG)


def start_logcat(name):
    """后台流式抓取 logcat"""
    global _lc
    ensure()
    p = os.path.join(BASE, name)
    f = open(p, 'w', encoding='utf-8', errors='replace')
    _lc = subprocess.Popen([ADB, '-s', DEV, 'logcat', '-v', 'time'],
                           stdout=f, stderr=subprocess.DEVNULL)
    print('  [logcat] 开始抓取 -> %s' % p)
    return p


def stop_logcat():
    global _lc
    if _lc:
        _lc.terminate()
        try:
            _lc.wait(timeout=10)
        except Exception:
            _lc.kill()
        _lc = None
        print('  [logcat] 已停止')


if __name__ == '__main__':
    s = sys.argv[1] if len(sys.argv) > 1 else 'all'

    if s == 'boot':
        launch()
        start_logcat('logs_q.txt')
        for i in range(8):
            time.sleep(6)
            shot('q01_%02d' % i)
        stop_logcat()

    elif s == 'flow':
        tap(*PT_ENTER, wait=5); shot('q02_enter')
        tap(*PT_OK, wait=3); shot('q03_ok')
        tap(*PT_NOTICE_X, wait=3); shot('q04_notice')
        tap(*PT_ENTER, wait=5); shot('q05_server')
        for i in range(5):
            time.sleep(4); shot('q06_wait%d' % i)

    elif s == 'create':
        tap(*PT_DICE, wait=2); shot('q07_dice')
        tap(*PT_START, wait=3); shot('q08_start')

    elif s == 'watch':
        start_logcat('logs_q_watch.txt')
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
        for i in range(n):
            time.sleep(4)
            shot('q09_%02d' % i)
        stop_logcat()

    elif s == 'shot':
        shot(sys.argv[2] if len(sys.argv) > 2 else 'q_shot')
