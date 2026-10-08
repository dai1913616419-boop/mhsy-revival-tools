"""Transport regression: a lost console must not abort real opening handlers.

Fixtures are in-memory socket boundaries and temporary profiles/logs; these
checks never connect to the game, inject live packets or edit a real save.
"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import game_server as legacy
from opening_server import OpeningClient
from opening_state import OpeningStore
from test_opening_protocol import MemorySocket, request_frame, response_frames

class OpeningLoggingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.log = self.root / 'opening.log'
        self.store = OpeningStore(self.root / 'profile.json')
        sink = patch.object(legacy, 'LOG', str(self.log))
        sink.start()
        self.addCleanup(sink.stop)

    def test_broken_pipe_does_not_drop_init_or_heartbeat(self):
        conn = MemorySocket([request_frame(1) + request_frame(3, b'echo')])
        client = OpeningClient(conn, ('offline-fixture', 0), self.store)
        with patch('builtins.print', side_effect=BrokenPipeError('detached console')):
            client.run()
        self.assertEqual([(msgid, body) for msgid, body, _ in response_frames(conn.output)], [(1, b'\x08\x01'), (3, b'echo')])
        self.assertTrue(conn.closed)
        self.assertIn('request 1', self.log.read_text())
        self.assertIn('send 1', self.log.read_text())

    def test_invalid_windows_console_does_not_abort_handler(self):
        conn = MemorySocket([request_frame(1)])
        client = OpeningClient(conn, ('offline-fixture', 0), self.store)
        with patch('builtins.print', side_effect=OSError(22, 'Invalid argument')):
            client.run()
        self.assertEqual(response_frames(conn.output)[0][:2], (1, b'\x08\x01'))
        self.assertIn('request 1', self.log.read_text())

    def test_closed_text_stream_keeps_file_logging(self):
        with patch('builtins.print', side_effect=ValueError('I/O operation on closed file')):
            legacy.log('[opening] fixture console detached')
        self.assertIn('fixture console detached', self.log.read_text())

if __name__ == '__main__':
    unittest.main()
