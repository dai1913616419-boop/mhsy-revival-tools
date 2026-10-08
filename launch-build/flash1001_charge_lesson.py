"""Real-input charge batch from the fresh19 first1001 helper dialogue.
No packets, profiles, resources, AI or tutorial completion markers are altered.
The screenshot is evidence only if the actual native ultimate prompt appears.
"""
import android_control as ctl
from play_story1001 import press, move, hold

if __name__ == '__main__':
    for _ in range(6):
        press(855, 518)
    move(24, 64, 1600)
    hold(904, 475, 8000)
    ctl.adb('shell', 'screencap', '-p', '/sdcard/mhsy-screen.png')
    press(32, 29)
    print(ctl.adb('pull', '/sdcard/mhsy-screen.png', str(ctl.ROOT / 'opening-flash-1001-native-ultimate-prompt.png')))
    print('Inspect exact original prompt; capture occurs before any manual Pause. No lesson presumed.')
