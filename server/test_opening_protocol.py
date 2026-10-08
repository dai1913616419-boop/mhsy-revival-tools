"""Offline OpeningClient.run integration tests: no listening/network socket or threads.

Input frames are encoded and output frames decoded independently of legacy framing
and opening_wire. The production handler/state APIs run against temporary profiles;
only the socket I/O boundary and log sink are replaced by in-memory fixtures.
"""
from collections import deque
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from opening_server import OpeningClient
from opening_state import OpeningStore
from test_opening_wire import decode_fields, one_field, repeated_fields


def encode_integer(value):
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7f) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def integer_field(tag, value):
    return encode_integer(tag << 3) + encode_integer(value)


def string_field(tag, value):
    value = value.encode('utf-8') if isinstance(value, str) else bytes(value)
    return encode_integer((tag << 3) | 2) + encode_integer(len(value)) + value


def request_frame(msgid, body=b'', serial=0):
    body = bytes(body)
    return struct.pack('<IHIH', len(body) + 12, msgid,
                       zlib.crc32(body) & 0xffffffff, serial) + body


def response_frames(data):
    frames = []
    offset = 0
    while offset < len(data):
        if len(data) - offset < 12:
            raise AssertionError('truncated response header')
        size, msgid, crc, serial = struct.unpack_from('<IHIH', data, offset)
        if size < 12 or size > len(data) - offset:
            raise AssertionError('invalid response length')
        body = bytes(data[offset + 12:offset + size])
        if zlib.crc32(body) & 0xffffffff != crc:
            raise AssertionError('invalid response CRC')
        frames.append((msgid, body, serial))
        offset += size
    return frames


def fragment(data, sizes=(1, 2, 7, 3, 19, 5)):
    parts = []
    offset = 0
    index = 0
    while offset < len(data):
        size = sizes[index % len(sizes)]
        parts.append(data[offset:offset + size])
        index += 1
        offset += size
    return parts


class MemorySocket:
    """A recv/sendall/close boundary, deliberately not a real socket."""
    def __init__(self, parts):
        self.parts = deque(parts)
        self.output = bytearray()
        self.timeout = None
        self.closed = False
        self.recv_calls = 0

    def settimeout(self, timeout):
        self.timeout = timeout

    def recv(self, limit):
        self.recv_calls += 1
        if not self.parts:
            return b''
        part = self.parts.popleft()
        if len(part) > limit:
            self.parts.appendleft(part[limit:])
            return part[:limit]
        return part

    def sendall(self, data):
        if self.closed:
            raise OSError('fixture socket is closed')
        self.output.extend(data)

    def close(self):
        self.closed = True


class OpeningProtocolTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'opening.json'
        self.store = OpeningStore(self.path)
        # Prevent tests from appending logs or touching the legacy demo save.
        log_patch = patch('opening_server.legacy.log')
        self.logs = log_patch.start()
        self.addCleanup(log_patch.stop)
        write_patch = patch('opening_server.legacy.write_save')
        self.legacy_write = write_patch.start()
        self.addCleanup(write_patch.stop)

    def exchange(self, messages, split=True, store=None, initial_serial=0):
        stream = b''.join(request_frame(msgid, body, serial)
                          for serial, (msgid, body) in enumerate(messages, 1))
        conn = MemorySocket(fragment(stream) if split else [stream])
        client = OpeningClient(conn, ('offline-fixture', 0), store or self.store)
        client.serial = initial_serial
        client.run()  # Synchronous; does not start Thread or create a listener.
        frames = response_frames(conn.output)
        self.assertTrue(conn.closed)
        self.assertTrue(client.closed)
        self.assertEqual(conn.timeout, 30)
        self.assertEqual([serial for msgid, body, serial in frames],
                         [(initial_serial + n) & 0xffff for n in range(1, len(frames) + 1)])
        self.legacy_write.assert_not_called()
        return client, conn, frames

    def message_body(self, frames, msgid):
        matches = [body for mid, body, serial in frames if mid == msgid]
        self.assertEqual(len(matches), 1, f'expected exactly one response {msgid}')
        return matches[0]

    def test_fragmented_fresh_login_create_and_once_request_follow_client_sequence(self):
        account = 'fixture-account'
        role_name = '勇者'
        messages = [
            (1, b''),
            (101, string_field(1, account)),
            (1001, string_field(1, role_name) + integer_field(2, 1)),
            (102, b''),
            (703, b''),
        ]
        client, conn, frames = self.exchange(messages)
        self.assertGreater(conn.recv_calls, len(messages))
        ids = [mid for mid, body, serial in frames]
        # 101 is deferred until after character selection, not sent alongside1301.
        self.assertEqual(ids[:5], [1, 108, 1301, 1302, 101])
        self.assertEqual(one_field(self, self.message_body(frames, 108), 1, 0), 1)
        self.assertEqual(self.message_body(frames, 1302), bytes.fromhex('0800'))
        enter = self.message_body(frames, 101)
        self.assertEqual(one_field(self, enter, 2, 0), 0)
        self.assertEqual(one_field(self, enter, 4, 0), 2)
        main = self.message_body(frames, 102)
        self.assertEqual(one_field(self, main, 2, 0), 19)
        self.assertEqual(one_field(self, main, 3, 2).decode('utf-8'), role_name)
        player = one_field(self, main, 4, 2)
        self.assertEqual(one_field(self, player, 2, 2).decode('utf-8'), account)
        self.assertEqual(one_field(self, player, 3, 0), 1)
        # Write0x49724: challenge round22 is int32; force-exit23 is bool.
        self.assertEqual(one_field(self, player, 22, 0), 1)
        self.assertEqual(one_field(self, player, 23, 0), 0)
        owned = repeated_fields(self, player, 101, 2)
        self.assertEqual(len(owned), 1, 'novice trial roster must not become persistent ownership')
        self.assertEqual(one_field(self, owned[0], 2, 0), 19)
        formation = self.message_body(frames, 201)
        self.assertEqual(one_field(self, formation, 1, 0), 0)
        self.assertEqual(repeated_fields(self, formation, 2, 2), [b'', b'', b'', b'', b''],
                         'fresh owned hero must remain unselected for the guide click')
        task = repeated_fields(self, self.message_body(frames, 1103), 1, 2)
        self.assertEqual(len(task), 1)
        self.assertEqual(decode_fields(task[0]), [(1, 0, 1), (2, 0, 0), (3, 0, 0)])
        saved = OpeningStore(self.path).snapshot()
        self.assertEqual((saved['account'], saved['role_name'], saved['res_id']),
                         (account, role_name, 19))
        self.assertFalse(saved['novice_completed'])
        self.assertEqual(saved['formations']['0'], ['', '', '', '', ''])
        self.assertEqual(set(saved['heroes']), {'hero19'})
        self.assertEqual(client.cur_region, 99)

    def test_player_var_1801_set_delete_persists_and_reconnect_restores_tag109(self):
        self.store.create_role('Start', 0)
        _, _, frames = self.exchange([
            (101, string_field(1, 'saved-account')),
            (1801, string_field(1, 'NG_10011B') + string_field(2, '1')),
            (1801, string_field(1, 'MCPlay') + string_field(2, '6')),
            (1801, string_field(1, '临时') + string_field(2, '1')),
            (1801, string_field(1, '临时') + integer_field(3, 1)),
            (1801, string_field(1, '剧情') + string_field(2, '已完成')),
            (601, b''),
        ])
        self.assertNotIn(1801, [mid for mid, body, serial in frames],
                         'player-var updates must not receive sign-in-info1801')
        expected = {'NG_10011B': '1', 'MCPlay': '6', '剧情': '已完成'}
        reloaded = OpeningStore(self.path)
        self.assertEqual(reloaded.snapshot()['vars'], expected)
        # Read a fresh client reconnect from the on-disk profile, not only memory.
        _, _, frames = self.exchange([(601, b'')], store=reloaded)
        reconnect = self.message_body(frames, 901)
        self.assertEqual(one_field(self, reconnect, 1, 0), 1)
        player = one_field(self, reconnect, 2, 2)
        restored = {
            one_field(self, item, 1, 2).decode('utf-8'):
                one_field(self, item, 2, 2).decode('utf-8')
            for item in repeated_fields(self, player, 109, 2)
        }
        self.assertEqual(restored, expected)
        self.assertEqual(one_field(self, player, 3, 0), 1,
                         'opening reconnect must not inherit demo level30')
        self.assertEqual(one_field(self, player, 22, 0), 1)
        self.assertEqual(one_field(self, player, 23, 0), 0)
        owned = repeated_fields(self, player, 101, 2)
        self.assertEqual(len(owned), 1)
        self.assertEqual(one_field(self, owned[0], 2, 0), 18)
        formation = self.message_body(frames, 201)
        self.assertEqual(repeated_fields(self, formation, 2, 2), [b'', b'', b'', b'', b''])
        self.assertEqual(reloaded.snapshot()['formations']['0'], ['', '', '', '', ''])

    def test_once_and_daily_requests_are_703_701_not_response_ids(self):
        self.store.create_role('Start', 0)
        _, _, frames = self.exchange([(703, b''), (701, b'')], split=False)
        ids = [mid for mid, body, serial in frames]
        self.assertIn(1103, ids)
        self.assertIn(1101, ids)
        self.assertNotIn(703, ids)
        self.assertNotIn(701, ids)
        task = repeated_fields(self, self.message_body(frames, 1103), 1, 2)
        self.assertEqual([one_field(self, entry, 1, 0) for entry in task], [1])
        self.assertEqual(one_field(self, task[0], 2, 0), 0)

    def test_actual_2001_dispatch_supplies_empty_arena_wrapper_in_fresh_novice(self):
        self.store.create_role('Start', 0)
        client, _, frames = self.exchange([(102, b''), (2001, b'')])
        self.assertEqual(client.cur_region, 99)
        body = self.message_body(frames, 2001)
        # Independent literal, never wire.empty_arena_info() as expectation.
        self.assertEqual(body, bytes.fromhex('08001000180020003200'))
        self.assertEqual(decode_fields(body), [
            (1, 0, 0), (2, 0, 0), (3, 0, 0), (4, 0, 0), (6, 2, b''),
        ])
        self.assertEqual(decode_fields(one_field(self, body, 6, 2)), [])

    def test_real_novice_304_completion_sends_city_born_before_region107(self):
        self.store.create_role('Start', 0)
        self.assertFalse(self.store.snapshot()['novice_completed'])
        self.assertEqual(self.store.snapshot()['formations']['0'], ['', '', '', '', ''])
        client, _, frames = self.exchange([(102, b''), (304, b''), (304, b'')])
        self.assertEqual(repeated_fields(self, self.message_body(frames, 201), 2, 2),
                         [b'', b'', b'', b'', b''])
        initial = one_field(self, self.message_body(frames, 102), 4, 2)
        owned = repeated_fields(self, initial, 101, 2)
        self.assertEqual(len(owned), 1, 'trial roster does not require permanent formation members')
        self.assertEqual(one_field(self, owned[0], 2, 0), 18)
        self.assertEqual(client.cur_region, 1)
        ids = [mid for mid, body, serial in frames]
        self.assertEqual(ids.count(102), 1, 'returning city must reuse MainPlayer')
        self.assertGreaterEqual(ids.count(107), 1, 'novice completion must request a city scene')
        for index, msgid in enumerate(ids):
            if msgid != 107:
                continue
            self.assertGreater(index, 0)
            self.assertEqual(ids[index - 1], 103)
            self.assertEqual(frames[index][1], bytes.fromhex('0801'))
            born = frames[index - 1][1]
            for tag, expected in ((1, -1.12), (2, 301.52), (3, 15.42)):
                actual = struct.unpack('<f', one_field(self, born, tag, 5))[0]
                self.assertAlmostEqual(actual, expected, places=4)
        saved = OpeningStore(self.path).snapshot()
        self.assertTrue(saved['novice_completed'])
        self.assertEqual(len(saved['settled_battles']), 1,
                         'duplicate304 must not settle novice twice')
        _, _, login_frames = self.exchange([(101, string_field(1, 'local'))],
                                           store=OpeningStore(self.path))
        enter = self.message_body(login_frames, 101)
        self.assertEqual(one_field(self, enter, 2, 0), 1)
        self.assertNotIn(1301, [mid for mid, body, serial in login_frames])

    def test_heartbeat_responses_wrap_u16_serial_without_frame_corruption(self):
        _, _, frames = self.exchange([(3, b''), (3, b'\x08\x01'), (3, b'\x08\x02')],
                                     split=False, initial_serial=65534)
        self.assertEqual([(mid, body, serial) for mid, body, serial in frames],
                         [(3, b'', 65535), (3, b'\x08\x01', 0), (3, b'\x08\x02', 1)])

    def test_corrupt_crc_rejects_frame_before_player_var_persistence(self):
        self.store.create_role('Start', 0)
        body = string_field(1, 'MCPlay') + string_field(2, '999')
        frame = bytearray(request_frame(1801, body, 1))
        frame[6] ^= 1  # CRC at offset6, preserving valid length and protobuf body.
        conn = MemorySocket(fragment(bytes(frame)))
        client = OpeningClient(conn, ('offline-fixture', 0), self.store)
        client.run()
        self.assertTrue(conn.closed)
        self.assertEqual(response_frames(conn.output), [])
        self.assertEqual(OpeningStore(self.path).snapshot()['vars'], {})
        self.assertTrue(any('Invalid frame CRC' in str(call) for call in self.logs.call_args_list))
        self.legacy_write.assert_not_called()

    def test_invalid_frame_lengths_close_without_dispatch(self):
        for size in (0, 11, 1024 * 1024 + 1):
            with self.subTest(size=size):
                conn = MemorySocket([struct.pack('<I', size)])
                client = OpeningClient(conn, ('offline-fixture', 0), self.store)
                client.run()
                self.assertTrue(conn.closed)
                self.assertEqual(response_frames(conn.output), [])
        self.assertEqual(OpeningStore(self.path).snapshot()['vars'], {})
        self.legacy_write.assert_not_called()

    def test_actual202_guide_selection_persists_owned_hero_after_empty_novice_formation(self):
        self.store.create_role('Start', 0)
        _, _, novice = self.exchange([(102, b''), (304, b'')])
        self.assertEqual(repeated_fields(self, self.message_body(novice, 201), 2, 2),
                         [b'', b'', b'', b'', b''])
        self.assertEqual(self.store.snapshot()['formations']['0'], ['', '', '', '', ''])
        selected = integer_field(1, 0) + b''.join(
            string_field(2, slot) for slot in ['hero18', '', '', '', ''])
        _, _, frames = self.exchange([(202, selected), (601, b'')])
        self.assertEqual(repeated_fields(self, self.message_body(frames, 201), 2, 2),
                         [b'hero18', b'', b'', b'', b''])
        saved = OpeningStore(self.path)
        self.assertEqual(saved.snapshot()['formations']['0'], ['hero18', '', '', '', ''])
        self.assertEqual(set(saved.snapshot()['heroes']), {'hero18'})
        _, _, frames = self.exchange([(601, b'')], store=saved)
        self.assertEqual(repeated_fields(self, self.message_body(frames, 201), 2, 2),
                         [b'hero18', b'', b'', b'', b''])
        player = one_field(self, self.message_body(frames, 901), 2, 2)
        self.assertEqual(one_field(self, player, 22, 0), 1)
        self.assertEqual(one_field(self, player, 23, 0), 0)
        owned = repeated_fields(self, player, 101, 2)
        self.assertEqual(len(owned), 1)
        self.assertEqual(one_field(self, owned[0], 2, 0), 18)


if __name__ == '__main__':
    unittest.main()
