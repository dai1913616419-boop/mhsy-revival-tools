"""Bounded real controls from the paused fresh19 first1001 bridge.
Never injects packets, changes AI/resources or writes a save. Capture the actual
ultimate lesson if energy fills; no lesson or victory is assumed.
"""
import android_control as ctl
from play_story1001 import press, move, hold

if __name__ == '__main__':
    press(575, 270)
    move(64, 36, 2400)
    for _ in range(6):
        press(855, 518)
    move(12, 64, 1300)
    hold(904, 475, 8000)
    ctl.adb('shell', 'screencap', '-p', '/sdcard/mhsy-screen.png')
    press(32, 29)
    print(ctl.adb('pull', '/sdcard/mhsy-screen.png', str(ctl.ROOT / 'opening-flash-1001-ultimate-lesson-candidate.png')))
    print('Capture predates manual Pause; inspect exact original prompt. No victory/lesson presumed.')
