"""Original resource-bootstrap handler must survive losing its optional console.

Temporary filesystem and real do_GET/version routing; no server/listening socket.
"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import update_server as update

class UpdateLoggingTests(unittest.TestCase):
    def test_version_response_survives_detached_console(self):
        failures = [BrokenPipeError('detached console'), OSError(22, 'Invalid argument'), ValueError('I/O operation on closed file')]
        for failure in failures:
            with self.subTest(error=type(failure).__name__), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / 'logs').mkdir()
                handler = object.__new__(update.UpdateHandler)
                handler.path = '/Android_90/UpdateRoot/Version/Version.bytes?native-random-query'
                handler.command = 'GET'
                handler.headers = {'Host': '192.168.1.104', 'User-Agent': 'offline-fixture'}
                handler.cfg = {'log_requests': True, 'server_versions': {'Android_90': '4.2.0.1'}}
                handler._send_bytes = Mock()
                with patch.object(update, 'HERE', str(root)), patch('builtins.print', side_effect=failure):
                    handler.do_GET()
                body, content_type = handler._send_bytes.call_args.args
                self.assertEqual(content_type, 'text/plain')
                fields = body.decode('utf-8').split('|')
                self.assertEqual(len(fields), 6)
                self.assertEqual(fields[2], '4.2.0.1')
                self.assertTrue(fields[0].startswith('http://192.168.1.104/Android_90/'))
                logged = (root / 'logs' / 'update_server.log').read_text(encoding='utf-8')
                self.assertIn('GET /Android_90/UpdateRoot/Version/Version.bytes', logged)
                self.assertIn('4.2.0.1', logged)

if __name__ == '__main__':
    unittest.main()
