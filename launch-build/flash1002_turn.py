"""Real native route turn around the1002 cart; no packet/save manipulation."""
import android_control as ctl
from play_story1001 import press, move, hold

if __name__ == '__main__':
    press(575, 270)
    move(0, 64, 900)
    move(64, 0, 1300)
    hold(904, 475, 10000)
    ctl.adb('shell', 'screencap', '-p', '/sdcard/mhsy-screen.png')
    press(32, 29)
    print(ctl.adb('pull', '/sdcard/mhsy-screen.png', str(ctl.ROOT / 'opening-flash-story1002-route-corner.png')))
