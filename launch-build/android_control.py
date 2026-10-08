"""ADB helper for this BlueStacks instance; use bundled ADB consistently."""
import argparse
from pathlib import Path
import subprocess
import sys

ADB = r'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'
DEVICE = 'emulator-5554'
ROOT = Path(r'C:\mhsy-local')

def adb(*args, binary=False, check=True, timeout=120):
    p = subprocess.run([ADB, '-s', DEVICE, *args], capture_output=True, timeout=timeout)
    if p.stderr:
        print(p.stderr.decode('utf-8', 'replace'), file=sys.stderr)
    if check and p.returncode:
        raise RuntimeError(f'ADB {args} failed: {p.stdout.decode("utf-8", "replace")}')
    return p.stdout if binary else p.stdout.decode('utf-8', 'replace')

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['info','install','launch','shot','logs','tap','press','shell'])
    ap.add_argument('args', nargs='*')
    a = ap.parse_args()
    if a.action == 'info':
        print(adb('shell','getprop','sys.boot_completed'))
        print(adb('shell','getprop','ro.product.cpu.abilist'))
        print(adb('shell','wm','size'))
    elif a.action == 'install':
        name = a.args[0] if a.args else 'mhsy_local_latest.apk'
        print(adb('install','-r',str(ROOT / name), timeout=300))
    elif a.action == 'launch':
        print(adb('logcat','-c'))
        print(adb('shell','am','start','-n','com.fl.mhsy.qihoo/com.fl.mhsy.UnityPlayerNativeActivity'))
    elif a.action == 'shot':
        name = a.args[0] if a.args else 'game.png'
        adb('shell','screencap','-p','/sdcard/mhsy-screen.png')
        print(adb('pull','/sdcard/mhsy-screen.png',str(ROOT / name)))
    elif a.action == 'logs':
        data=adb('logcat','-d','-v','threadtime', binary=True)
        (ROOT / 'client-logcat.txt').write_bytes(data)
        print(f'Saved {len(data)} log bytes')
    elif a.action == 'tap':
        print(adb('shell','input','tap',*a.args))
    elif a.action == 'press':
        if len(a.args) not in (2, 3):
            ap.error('press requires X Y [milliseconds]')
        x, y = a.args[:2]
        duration = a.args[2] if len(a.args) == 3 else '200'
        # Zero-duration ADB taps can miss Unity4 frame-polled input.
        print(adb('shell', 'input', 'swipe', x, y, x, y, duration))
    elif a.action == 'shell':
        print(adb('shell',*a.args))
