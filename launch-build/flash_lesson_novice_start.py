"""New isolated Flash first-lesson QA; genuine original novice inputs only."""
from native_input_batch import run, press, move, hold_basic

gestures = [press(855, 518) for _ in range(10)]
gestures += [move(0, -64, 2000), move(-64, 64, 800), move(64, 0, 1050), move(-64, 64, 850), hold_basic(10000)]
print(run(gestures, 'opening-flash-lesson-novice-waypoints.png'))
