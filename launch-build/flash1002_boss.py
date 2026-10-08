"""Spend actually charged19/31 ultimates with real native portrait presses."""
import android_control as ctl
from play_story1001 import press, hold

if __name__ == '__main__':
    press(575, 270)
    press(913, 340)
    press(913, 239)
    hold(904, 475, 12000)
    ctl.adb('shell', 'screencap', '-p', '/sdcard/mhsy-screen.png')
    press(32, 29)
    print(ctl.adb('pull', '/sdcard/mhsy-screen.png', str(ctl.ROOT / 'opening-flash-story1002-after-ultimates.png')))
    print('Real charged portrait inputs; inspect actual server result. This is NOT proof of the first1001 ultimate lesson.')
