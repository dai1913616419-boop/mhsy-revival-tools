"""冷启动 -> 关闭全部弹窗 -> 主城 -> 打开"任务"面板。
用法: goto_task.py
坐标基于设备 1920x1080（实测校准）。
"""
import subprocess, time, os

ADB = r'C:/Program Files/Netease/MuMu/nx_main/adb.exe'
DEV = '127.0.0.1:7555'
PKG = 'com.fl.mhsy.qihoo'
ACT = 'com.fl.mhsy.UnityPlayerNativeActivity'
BASE = os.path.dirname(os.path.abspath(__file__))


def adb(*a, timeout=60):
    return subprocess.run([ADB, '-s', DEV] + list(a), capture_output=True, text=True, timeout=timeout)


def raw(*a, timeout=90):
    return subprocess.run([ADB, '-s', DEV] + list(a), capture_output=True, timeout=timeout).stdout


def shot(n):
    d = raw('exec-out', 'screencap', '-p')
    open(os.path.join(BASE, 'shots', n + '.png'), 'wb').write(d)
    print('  [shot]', n, len(d), flush=True)


def tap(x, y, w=3.0):
    print('  tap', x, y, flush=True)
    adb('shell', 'input', 'tap', str(x), str(y)); time.sleep(w)


def main():
    adb('shell', 'am', 'force-stop', PKG); time.sleep(1.5)
    adb('shell', 'am', 'start', '-n', '%s/%s' % (PKG, ACT))
    print('  launched', flush=True)
    time.sleep(45)
    shot('t0_boot')

    # 依次关闭：提示"知道了" -> 公告X -> 进入游戏 -> JJC X -> 退出挑战赛
    tap(956, 733, 2.5);  shot('t1_know')
    tap(1445, 72, 3.0);  shot('t2_notice')
    tap(962, 988, 6.0);  shot('t3_enter')
    time.sleep(8);       shot('t4_wait')
    tap(1700, 80, 3.0);  shot('t5_jjcX')
    tap(750, 728, 4.0);  shot('t6_exit')
    time.sleep(3);       shot('t7_city')

    # 任务按钮（右侧竖排：主线 / 挑战 / 任务）
    tap(1785, 786, 4.0); shot('t8_task')
    time.sleep(3);       shot('t9_task2')


if __name__ == '__main__':
    main()
