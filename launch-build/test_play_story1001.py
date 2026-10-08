"""Real-input helper regression: navigation-only batches must not tap attack."""
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch
import android_control

class HelperTest(unittest.TestCase):
    def test_zero_seconds_does_not_generate_an_attack(self):
        calls = []
        def fake_adb(*args, **kwargs):
            calls.append(args)
            return ''
        with patch.object(android_control, 'adb', fake_adb), patch('time.sleep'), patch.object(sys, 'argv', ['play_story1001.py', '--continue', '--attack-seconds', '0', '--move-ms', '0']):
            runpy.run_path(str(Path(__file__).with_name('play_story1001.py')), run_name='__main__')
        attacks = [a for a in calls if a[:4] == ('shell', 'input', 'swipe', '904')]
        self.assertEqual(attacks, [], 'Zero-duration swipe still taps basic attack and changes position; navigation-only must emit none')

    def test_positive_seconds_preserves_real_held_attack(self):
        calls = []
        def fake_adb(*args, **kwargs):
            calls.append(args)
            return ''
        with patch.object(android_control, 'adb', fake_adb), patch('time.sleep'), patch.object(sys, 'argv', ['play_story1001.py', '--continue', '--attack-seconds', '1', '--move-ms', '0']):
            runpy.run_path(str(Path(__file__).with_name('play_story1001.py')), run_name='__main__')
        attacks = [a for a in calls if a[:4] == ('shell', 'input', 'swipe', '904')]
        self.assertEqual(attacks, [('shell', 'input', 'swipe', '904', '475', '904', '475', '1000')])

if __name__ == '__main__':
    unittest.main()
