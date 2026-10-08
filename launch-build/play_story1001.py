"""Real ADB input smoke-test for story1001; never sends game packets or edits saves.

Run from C:\\mhsy-local after formation is ready. Default presses Fight, waits for
scene load, finishes the movement hint, attacks, then opens the game's own Pause
menu before taking a screenshot. Pausing prevents model/tool inspection latency
from consuming the normal three-minute battle timer. --continue starts from the
in-game pause dialog and presses its Continue button before the next input batch.
"""
import argparse
import time
import android_control as ctl


def press(x, y):
    ctl.adb('shell', 'input', 'swipe', str(x), str(y), str(x), str(y), '200')


def hold(x, y, ms):
    ctl.adb('shell', 'input', 'swipe', str(x), str(y), str(x), str(y), str(ms))


def move(dx, dy, ms):
    ctl.adb('shell', 'input', 'swipe', '148', '405', str(148 + dx), str(405 + dy), str(ms))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--continue', dest='continuing', action='store_true')
    ap.add_argument('--attack-seconds', type=int, default=10)
    ap.add_argument('--ultimate', action='store_true')
    ap.add_argument('--move-x', type=int, default=0)
    ap.add_argument('--move-y', type=int, default=-64)
    ap.add_argument('--move-ms', type=int, default=1700)
    ap.add_argument('--screenshot', default='opening-1001-input-pause.png')
    args = ap.parse_args()
    if args.continuing:
        press(575, 270)  # Native pause dialog's Continue button.
    else:
        press(780, 444)
        time.sleep(3)  # Real scene loading; no network or profile-state injection.
    if args.ultimate:
        press(913, 340)
    if args.move_ms:
        move(args.move_x, args.move_y, args.move_ms)
    if args.attack_seconds > 0:
        hold(904, 475, args.attack_seconds * 1000)
    ctl.adb('shell', 'screencap', '-p', '/sdcard/mhsy-screen.png')
    press(32, 29)  # Pause AFTER capture, so the inspected frame isn't hidden behind the dialog.
    print(ctl.adb('pull', '/sdcard/mhsy-screen.png', str(ctl.ROOT / args.screenshot)))
    print('Real inputs sent; inspect screenshot/profile for the actual result. No victory assumed.')
