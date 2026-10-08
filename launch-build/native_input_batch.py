"""Run ordinary Android input gestures in ONE ADB shell invocation.

This avoids Windows/ADB/model latency between an original dialogue and combat.
It never emits game packets, changes saves, AI, stats, energy or guide markers.
The screenshot always precedes optional native Pause, matching existing helpers.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import android_control as ctl

@dataclass(frozen=True)
class Gesture:
    x1: int
    y1: int
    x2: int
    y2: int
    ms: int = 200

    def shell_command(self) -> str:
        values = (self.x1, self.y1, self.x2, self.y2, self.ms)
        if any(type(value) is not int for value in values):
            raise ValueError('Gesture arguments must be integers, never shell text')
        if not (0 <= self.x1 < 960 and 0 <= self.x2 < 960 and 0 <= self.y1 < 540 and 0 <= self.y2 < 540):
            raise ValueError('Gesture lies outside the verified960x540 device')
        if not 0 < self.ms <= 120000:
            raise ValueError('Gesture duration must be positive and bounded')
        return f'input swipe {self.x1} {self.y1} {self.x2} {self.y2} {self.ms}'


def press(x: int, y: int) -> Gesture:
    return Gesture(x, y, x, y, 200)


def move(dx: int, dy: int, ms: int) -> Gesture:
    return Gesture(148, 405, 148 + dx, 405 + dy, ms)


def hold_basic(ms: int) -> Gesture:
    return Gesture(904, 475, 904, 475, ms)


def build_shell(gestures: Iterable[Gesture], pause_after: bool = True) -> str:
    commands = [gesture.shell_command() for gesture in gestures]
    commands.append('screencap -p /sdcard/mhsy-screen.png')
    if pause_after:
        commands.append(press(32, 29).shell_command())
    # Stop on any native command error, rather than masking an earlier failure.
    return ' && '.join(commands)


def run(gestures: Iterable[Gesture], screenshot: str, pause_after: bool = True) -> str:
    if not screenshot or Path(screenshot).name != screenshot or '/' in screenshot or '\\' in screenshot or not screenshot.endswith('.png'):
        raise ValueError('Screenshot must be a unique PNG basename, not a path')
    ctl.adb('shell', build_shell(gestures, pause_after))
    return ctl.adb('pull', '/sdcard/mhsy-screen.png', str(ctl.ROOT / screenshot))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gesture', action='append', nargs=5, type=int, metavar=('X1','Y1','X2','Y2','MS'), default=[])
    parser.add_argument('--screenshot', required=True)
    parser.add_argument('--no-pause', action='store_true')
    args = parser.parse_args()
    print(run([Gesture(*values) for values in args.gesture], args.screenshot, not args.no_pause))
