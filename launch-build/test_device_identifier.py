"""Regression tests use real client bytes and in-memory patches only.

Run with the existing dnfile dependency on PYTHONPATH:
    python test_device_identifier.py [Client_opening.bin]
"""
from contextlib import redirect_stdout
import io
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

import dnfile
from patch_device_identifier import apply_patch, main

CLIENT_PATH = Path(__file__).with_name('Client_opening.bin')


def inspect_identifier(data):
    """Independently observe the public binary contract, not patch internals."""
    pe_start = data.find(b'MZ')
    while pe_start >= 0:
        if pe_start + 0x40 <= len(data):
            nt_offset = struct.unpack_from('<I', data, pe_start + 0x3c)[0]
            if data[pe_start + nt_offset:pe_start + nt_offset + 4] == b'PE\0\0':
                break
        pe_start = data.find(b'MZ', pe_start + 1)
    if pe_start < 0:
        raise AssertionError('Client PE not found')
    pe = dnfile.dnPE(data=data[pe_start:])
    try:
        rows = [mi.row for t in pe.net.mdtables.TypeDef.rows
                if str(t.TypeNamespace) == 'MobileGameDemo'
                and str(t.TypeName) == 'AndroidConnector'
                for mi in t.MethodList
                if str(mi.row.Name) == 'GetAndroidDeviceID']
        if len(rows) != 1:
            raise AssertionError('Expected one AndroidConnector.GetAndroidDeviceID')
        method = rows[0]
        offset = pe_start + pe.get_offset_from_rva(method.Rva)
        first = data[offset]
        size = first >> 2 if first & 3 == 2 else None
        code = data[offset + 1:offset + 1 + size] if size is not None else b''
        token = struct.unpack_from('<I', code, 1)[0] if len(code) == 6 and code[0] == 0x72 else None
        value = pe.net.user_strings.get(token & 0xffffff).value if token is not None else None
        return {
            'pe_start': pe_start, 'offset': offset, 'header': first,
            'code_size': size, 'code': code, 'token': token, 'value': value,
            'rva': method.Rva, 'signature': bytes(method.Signature.value),
            'rva_offset': pe_start + method.struct.get_field_absolute_offset('Rva'),
            'signature_offset': pe_start + pe.get_offset_from_rva(method.Signature.rva) + 1,
            'revision_offset': pe_start + pe.net.mdtables.Assembly.rows[0].struct.get_field_absolute_offset('RevisionNumber'),
        }
    finally:
        pe.close()


class DeviceIdentifierTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = CLIENT_PATH.read_bytes()

    def assert_safe_identifier(self, data):
        info = inspect_identifier(data)
        self.assertEqual(info['rva'], 0x39df)
        self.assertEqual(info['signature'], b'\x00\x00\x0e')
        self.assertEqual(info['header'], 0x1a, 'Getter must use a complete tiny six-byte IL body')
        self.assertEqual(info['code_size'], 6)
        self.assertEqual(info['code'][0], 0x72)  # ldstr; no native identifier call
        self.assertEqual(info['code'][-1], 0x2a)  # ret; no trailing parsed IL
        self.assertEqual(info['token'], 0x700000db)
        self.assertEqual(info['value'], 'WindowsEditor')
        return info

    def test_client_identifier_is_safe(self):
        self.assert_safe_identifier(apply_patch(self.client))

    def test_original_fixture_still_exercises_the_unsafe_jni_getter(self):
        original = inspect_identifier(self.client)
        if original['header'] == 0x1a:
            self.skipTest('Supplied client is already patched; initial red was run on the original fixture')
        self.assertEqual(original['header'], 0x6e)
        self.assertEqual(original['code_size'], 27)
        self.assertIn(b'\x28\x33\x00\x00\x0a', original['code'])
        # Keep the initial red regression as an observed precondition.
        with self.assertRaises(AssertionError):
            self.assert_safe_identifier(self.client)

    def test_only_the_seven_byte_getter_slot_changes(self):
        result = apply_patch(self.client)
        info = self.assert_safe_identifier(result)
        offset = info['offset']
        self.assertIsInstance(result, bytes)
        self.assertEqual(len(result), len(self.client))
        if inspect_identifier(self.client)['header'] == 0x6e:
            self.assertNotEqual(result[offset:offset + 7], self.client[offset:offset + 7])
        else:
            self.assertEqual(result, self.client)
        self.assertEqual(result[:offset], self.client[:offset])
        self.assertEqual(result[offset + 7:], self.client[offset + 7:])
        # A tiny header has no EH section or locals token; only six IL bytes
        # are parsed even though the old unused tail stays intact.
        self.assertEqual(result[offset:offset + 7], bytes.fromhex('1a 72 db 00 00 70 2a'))

    def test_already_patched_input_is_idempotent(self):
        once = apply_patch(self.client)
        self.assertEqual(apply_patch(once), once)
        self.assert_safe_identifier(once)

    def test_mutable_input_is_not_modified(self):
        mutable = bytearray(self.client)
        result = apply_patch(mutable)
        self.assertEqual(bytes(mutable), self.client)
        self.assertIsInstance(result, bytes)
        self.assert_safe_identifier(result)

    def test_raw_dll_and_nonstandard_wrapper_are_supported(self):
        original = inspect_identifier(self.client)
        dll = self.client[original['pe_start']:]
        self.assertEqual(self.assert_safe_identifier(apply_patch(dll))['pe_start'], 0)
        # Include a false MZ candidate; the valid PE starts at a new offset.
        prefix = b'MZ' + b'\0' * 80 + b'nonstandard-wrapper'
        result = apply_patch(prefix + dll)
        self.assertEqual(result[:len(prefix)], prefix)
        self.assertEqual(self.assert_safe_identifier(result)['pe_start'], len(prefix))

    def test_unknown_opcode_is_rejected_without_mutation(self):
        info = inspect_identifier(self.client)
        changed = bytearray(self.client)
        changed[info['offset'] + 1] = 0x00
        before = bytes(changed)
        with self.assertRaisesRegex(ValueError, 'opcode/header/body'):
            apply_patch(changed)
        self.assertEqual(bytes(changed), before)

    def test_old_header_with_partial_ret_patch_is_rejected(self):
        info = inspect_identifier(self.client)
        changed = bytearray(self.client)
        changed[info['offset'] + 1] = 0x2a
        with self.assertRaisesRegex(ValueError, 'opcode/header/body'):
            apply_patch(changed)

    def test_wrong_method_rva_is_rejected(self):
        info = inspect_identifier(self.client)
        changed = bytearray(self.client)
        struct.pack_into('<I', changed, info['rva_offset'], 0x39e0)
        with self.assertRaisesRegex(ValueError, 'RVA'):
            apply_patch(changed)

    def test_wrong_static_signature_is_rejected(self):
        info = inspect_identifier(self.client)
        changed = bytearray(self.client)
        self.assertEqual(changed[info['signature_offset']:info['signature_offset'] + 3], b'\x00\x00\x0e')
        changed[info['signature_offset']] = 0x20  # wrong: instance/has-this
        with self.assertRaisesRegex(ValueError, 'signature'):
            apply_patch(changed)

    def test_wrong_assembly_version_is_rejected(self):
        info = inspect_identifier(self.client)
        changed = bytearray(self.client)
        struct.pack_into('<H', changed, info['revision_offset'], 1)
        with self.assertRaisesRegex(ValueError, 'assembly/version'):
            apply_patch(changed)

    def test_fallback_string_mismatch_is_rejected(self):
        changed = bytearray(self.client)
        needle = 'WindowsEditor'.encode('utf-16le')
        offset = changed.index(needle)
        changed[offset] = ord('N')
        with self.assertRaisesRegex(ValueError, 'fallback token'):
            apply_patch(changed)

    def test_missing_pe_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'PE not found'):
            apply_patch(b'not a client bundle')

    def test_cli_writes_only_requested_output_with_no_fixture_file_created(self):
        output = CLIENT_PATH.with_name('IN_MEMORY_ONLY_device_identifier.bin')
        with patch.object(Path, 'write_bytes', autospec=True) as write_output:
            with redirect_stdout(io.StringIO()):
                status = main(['--src', str(CLIENT_PATH), '--out', str(output)])
        self.assertEqual(status, 0)
        write_output.assert_called_once()
        written_path, written_bytes = write_output.call_args.args
        self.assertEqual(written_path, output)
        self.assert_safe_identifier(written_bytes)
        self.assertEqual(CLIENT_PATH.read_bytes(), self.client)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        CLIENT_PATH = Path(sys.argv.pop(1))
    unittest.main(verbosity=2)
