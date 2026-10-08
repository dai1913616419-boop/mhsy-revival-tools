"""Only real UI inputs: finish escort boss conversation/combat, then native Pause."""
import argparse
import android_control as ctl
from play_story1001 import press, hold

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshot', default='opening-escort-final-fight.png')
    args = parser.parse_args()
    for _ in range(6):
        press(855, 518)
    press(913, 340)
    hold(904, 475, 16000)
    for _ in range(6):
        press(855, 518)
    ctl.adb('shell', 'screencap', '-p', '/sdcard/mhsy-screen.png')
    press(32, 29)
    print(ctl.adb('pull', '/sdcard/mhsy-screen.png', str(ctl.ROOT / args.screenshot)))
