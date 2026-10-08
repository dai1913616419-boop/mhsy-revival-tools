"""Pure/mock checks for real-input batching, not gameplay-outcome claims."""
import unittest
from unittest.mock import patch
import native_input_batch as batch

class BatchTest(unittest.TestCase):
    def test_eight_real_dialogue_presses_then_move_and_basic(self):
        actions = [batch.press(855, 518)] * 8 + [batch.move(11, 64, 1760), batch.hold_basic(8000)]
        shell = batch.build_shell(actions)
        self.assertEqual(shell.count('input swipe 855 518 855 518 200'), 8)
        self.assertIn('input swipe 148 405 159 469 1760', shell)
        self.assertIn('input swipe 904 475 904 475 8000', shell)
        self.assertLess(shell.index('screencap'), shell.index('input swipe 32 29'))
        self.assertEqual(shell.count(' && '), 11)

    def test_one_shell_call_not_one_adb_process_per_gesture(self):
        with patch.object(batch.ctl, 'adb', return_value='OK') as adb:
            batch.run([batch.press(855, 518)] * 8, 'unique-test.png')
            self.assertEqual(adb.call_count, 2)
            self.assertEqual(adb.call_args_list[0].args[0], 'shell')
            self.assertEqual(adb.call_args_list[1].args[0], 'pull')

    def test_cli_preserves_numeric_gesture_order(self):
        import runpy
        import sys
        from pathlib import Path
        argv = ['native_input_batch.py', '--gesture', '855', '518', '855', '518', '200', '--gesture', '148', '405', '159', '469', '1760', '--screenshot', 'cli-order.png', '--no-pause']
        with patch.object(batch.ctl, 'adb', return_value='OK') as adb, patch.object(sys, 'argv', argv):
            runpy.run_path(str(Path(__file__).with_name('native_input_batch.py')), run_name='__main__')
            shell = adb.call_args_list[0].args[1]
            self.assertLess(shell.index('855 518'), shell.index('148 405'))
            self.assertNotIn('input swipe 32 29', shell)
            self.assertEqual(adb.call_count, 2)

    def test_reject_zero_duration_unintended_tap(self):
        with self.assertRaises(ValueError):
            batch.hold_basic(0).shell_command()

    def test_reject_shell_text_and_outside_viewport(self):
        for gesture in (batch.Gesture('1; false', 1, 1, 1, 200), batch.press(960, 500), batch.move(900, 0, 300)):
            with self.assertRaises(ValueError):
                gesture.shell_command()

    def test_reject_nonunique_path_before_any_input(self):
        with patch.object(batch.ctl, 'adb') as adb:
            with self.assertRaises(ValueError):
                batch.run([batch.press(855, 518)], '../old-output.png')
            adb.assert_not_called()

if __name__ == '__main__':
    unittest.main()
