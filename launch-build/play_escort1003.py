"""Real-input escort1003 smoke test. No packets, profile writes or synthetic wins.

Start with the legitimate saved two-hero formation ready. All actions below are
normal joystick, attack, ultimate and dialogue inputs. The original cutscenes
and escort dialogues can ignore Pause while the battle timer runs; therefore
this bounded input batch avoids model/tool latency between those scenes.
"""
import argparse
import time
import android_control as ctl
from play_story1001 import press, hold, move


def attack(seconds):
    hold(904, 475, int(seconds * 1000))


def dialogue():
    for _ in range(4):
        press(100, 518)
        time.sleep(.2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshot', default='opening-escort1003-batched-result.png')
    args = parser.parse_args()
    press(780, 444)
    time.sleep(3)
    attack(22)  # Native intro movie, then first wave.
    attack(14)  # Finish first wave / allow native second cinematic.
    move(32, 64, 2000)
    attack(14)  # Follow protected target through area2's waves.
    move(64, 17, 2900)
    attack(10)  # Area3; protected target activates its own triggers.
    move(64, 10, 1500)
    dialogue()  # Original boss introduction, no guide-variable changes.
    press(913, 340)  # Native ultimate, only works if legitimately charged.
    attack(15)
    dialogue()  # Original post-boss conversation.
    move(64, 0, 1500)
    attack(5)
    ctl.adb('shell', 'screencap', '-p', '/sdcard/mhsy-screen.png')
    press(32, 29)
    print(ctl.adb('pull', '/sdcard/mhsy-screen.png', str(ctl.ROOT / args.screenshot)))
    print('Real inputs completed. Inspect actual client settlement and server profile; no win assumed.')
