"""Three real cold-login checks; never writes a profile or injects game packets.

Runtime shots/logs preserve each attempt for independent server/UI verification.
Process alive is necessary, not sufficient: inspect city and101/102 traces too.
"""
import argparse
import json
import time
import android_control as ctl
from play_story1001 import press

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cycles', type=int, choices=range(1, 11), default=3)
    parser.add_argument('--prefix', default='opening-cold-login-safe')
    args = parser.parse_args()
    if not args.prefix or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.prefix):
        parser.error('--prefix must be a nonempty filename stem using letters, digits, hyphen or underscore')
    report = []
    for cycle in range(1, args.cycles + 1):
        ctl.adb('shell', 'am', 'force-stop', 'com.fl.mhsy.qihoo')
        ctl.adb('logcat', '-c')
        ctl.adb('shell', 'am', 'start', '-n', 'com.fl.mhsy.qihoo/com.fl.mhsy.UnityPlayerNativeActivity')
        time.sleep(20)  # Original resources, splash and announcement load.
        press(728, 38)
        time.sleep(1)
        press(483, 490)
        time.sleep(15)  # Real SDK/auth, snapshots and original city assets.
        name = f'{args.prefix}-{cycle}'
        ctl.adb('shell', 'screencap', '-p', '/sdcard/mhsy-screen.png')
        ctl.adb('pull', '/sdcard/mhsy-screen.png', str(ctl.ROOT / (name + '.png')))
        logs = ctl.adb('logcat', '-d', '-v', 'threadtime', binary=True)
        (ctl.ROOT / (name + '.log')).write_bytes(logs)
        pid = ctl.adb('shell', 'pidof', 'com.fl.mhsy.qihoo').strip()
        text = logs.decode('utf-8', 'replace')
        assert 'Assertion at mini-arm.c' not in text, f'Native Mono abort in cycle{cycle}'
        assert 'FATAL EXCEPTION' not in text, f'Android fatal exception in cycle{cycle}'
        assert pid, f'Client process missing in cycle{cycle}'
        report.append({'cycle': cycle, 'pid': pid, 'native_abort': False, 'screenshot': name + '.png'})
        print(json.dumps(report[-1]), flush=True)
    (ctl.ROOT / (args.prefix + '-report.json')).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'{args.cycles} app process(es) survived. Inspect each screenshot and actual server101/102 login before claiming cold-login success.')
