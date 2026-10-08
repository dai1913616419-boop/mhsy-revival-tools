"""Authentic novice99 input batch for fresh18; no completion assumptions."""
from native_input_batch import run, press, move, hold_basic

if __name__ == '__main__':
    print(run([press(855, 518)] * 4 + [
        move(0, -64, 2000),
        move(-64, 64, 800),
        move(64, 0, 1050),
        move(-48, 64, 850),
        hold_basic(10000),
    ], 'opening-black-fresh-novice-waypoints.png'))
