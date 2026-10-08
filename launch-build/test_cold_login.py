"""Side-effect-free tests for uniquely labelled, bounded cold-login batches."""
import json
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch
import android_control

class ColdHelperTest(unittest.TestCase):
    def test_one_cycle_uses_new_prefix_and_never_runs_three(self):
        calls = []
        def fake_adb(*args, **kwargs):
            calls.append(args)
            if kwargs.get('binary'):
                return b''
            if args == ('shell', 'pidof', 'com.fl.mhsy.qihoo'):
                return '123'
            return ''
        with tempfile.TemporaryDirectory() as temp, patch.object(android_control, 'ROOT', Path(temp)), patch.object(android_control, 'adb', fake_adb), patch('time.sleep'), patch.object(sys, 'argv', ['verify_cold_login.py', '--cycles', '1', '--prefix', 'fresh19-check']):
            runpy.run_path(str(Path(__file__).with_name('verify_cold_login.py')), run_name='__main__')
            data = json.loads((Path(temp) / 'fresh19-check-report.json').read_text())
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]['screenshot'], 'fresh19-check-1.png')
            self.assertFalse((Path(temp) / 'opening-cold-login-safe-report.json').exists())
        stops = [a for a in calls if a[:3] == ('shell', 'am', 'force-stop')]
        self.assertEqual(len(stops), 1)

    def test_bad_prefix_fails_before_any_device_input(self):
        with patch.object(android_control, 'adb') as adb, patch.object(sys, 'argv', ['verify_cold_login.py', '--prefix', '../old-output']):
            with self.assertRaises(SystemExit) as error:
                runpy.run_path(str(Path(__file__).with_name('verify_cold_login.py')), run_name='__main__')
            self.assertEqual(error.exception.code, 2)
            adb.assert_not_called()

if __name__ == '__main__':
    unittest.main()
