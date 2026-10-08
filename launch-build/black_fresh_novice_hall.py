"""Real movement from cleared novice first fight to the original second scene."""
from native_input_batch import run, move, hold_basic

if __name__ == '__main__':
    print(run([move(48, -64, 2700), move(0, -64, 2700), hold_basic(3000)], 'opening-black-fresh-novice-second-scene.png'))
