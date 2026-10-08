"""Bypass Unity's obsolete Android identifier JNI call in the known 4.2.0.1 client.

Only AndroidConnector.GetAndroidDeviceID's first seven body bytes change. The
existing WindowsEditor fallback string is reused; no user strings, metadata,
method RVAs, APKs, or runtime files are changed by the importable API.

CLI (writes only the explicitly requested output):
    python patch_device_identifier.py --src Client_opening.bin --out Client_safe.bin

Integration:
    client = apply_patch(client)  # accepts bytes-like input; returns bytes

This avoids a suspected intermittent JNI/Mono exception-unwind boundary. Passing
these structural checks does not establish successful cold-login runtime tests.
"""
import argparse
from pathlib import Path
import struct

import dnfile

TARGET_NAMESPACE = 'MobileGameDemo'
TARGET_CLASS = 'AndroidConnector'
TARGET_METHOD = 'GetAndroidDeviceID'
TARGET_RVA = 0x39df
TARGET_SIGNATURE = b'\x00\x00\x0e'  # static, no arguments, returns string
FALLBACK_TOKEN = 0x700000db
FALLBACK_VALUE = 'WindowsEditor'
ORIGINAL_BODY = bytes.fromhex(
    '6e 28 32 00 00 0a 2c 0e 28 32 00 00 0a 1d 2e 06 '
    '28 33 00 00 0a 2a 72 db 00 00 70 2a'
)
PATCHED_PREFIX = b'\x1a\x72' + struct.pack('<I', FALLBACK_TOKEN) + b'\x2a'


def _find_pe_offset(data):
    """Accept a raw DLL or a Unity wrapper; do not assume a fixed prefix size."""
    start = data.find(b'MZ')
    while start >= 0:
        if start + 0x40 <= len(data):
            nt_offset = struct.unpack_from('<I', data, start + 0x3c)[0]
            if nt_offset >= 0x40 and data[start + nt_offset:start + nt_offset + 4] == b'PE\0\0':
                return start
        start = data.find(b'MZ', start + 1)
    raise ValueError('Embedded client PE not found')


def apply_patch(data):
    """Return an immutable patched copy, or raise ValueError for unknown input.

    Original and already-patched bodies are accepted. A changed getter, method
    signature/RVA, assembly version, or fallback token is rejected rather than
    guessed at. The unused original bytes after the new tiny body stay intact.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError('Client input must be bytes, bytearray, or memoryview')
    raw = bytes(data)
    start = _find_pe_offset(raw)
    try:
        pe = dnfile.dnPE(data=raw[start:])
    except Exception as exc:
        raise ValueError('Cannot parse embedded client PE') from exc
    try:
        if pe.net is None or pe.net.mdtables is None:
            raise ValueError('Embedded PE lacks managed client metadata')
        tables = pe.net.mdtables
        if tables.Assembly is None or len(tables.Assembly.rows) != 1:
            raise ValueError('Expected exactly one Client assembly')
        assembly = tables.Assembly.rows[0]
        version = (assembly.MajorVersion, assembly.MinorVersion,
                   assembly.BuildNumber, assembly.RevisionNumber)
        if str(assembly.Name) != 'Client' or version != (1, 0, 0, 0):
            raise ValueError(f'Unsupported Client assembly/version: {assembly.Name} {version}')
        if tables.TypeDef is None:
            raise ValueError('Client type metadata is missing')
        methods = [mi.row for t in tables.TypeDef.rows
                   if str(t.TypeNamespace) == TARGET_NAMESPACE
                   and str(t.TypeName) == TARGET_CLASS
                   for mi in t.MethodList
                   if str(mi.row.Name) == TARGET_METHOD]
        if len(methods) != 1:
            raise ValueError('Expected exactly one AndroidConnector.GetAndroidDeviceID')
        method = methods[0]
        if bytes(method.Signature.value) != TARGET_SIGNATURE:
            raise ValueError('GetAndroidDeviceID signature is not static/no-argument/string')
        if method.Rva != TARGET_RVA:
            raise ValueError(f'Unsupported GetAndroidDeviceID RVA: {method.Rva:#x}')
        offset = start + pe.get_offset_from_rva(method.Rva)
        body = raw[offset:offset + len(ORIGINAL_BODY)]
        if len(body) != len(ORIGINAL_BODY):
            raise ValueError('GetAndroidDeviceID body is truncated')
        expected_patched = PATCHED_PREFIX + ORIGINAL_BODY[len(PATCHED_PREFIX):]
        if body not in (ORIGINAL_BODY, expected_patched):
            raise ValueError('Unknown GetAndroidDeviceID opcode/header/body version')
        if pe.net.user_strings is None:
            raise ValueError('Client user-string heap is missing')
        try:
            fallback = pe.net.user_strings.get(FALLBACK_TOKEN & 0xffffff)
            value = fallback.value if fallback is not None else None
        except Exception as exc:
            raise ValueError('Cannot resolve existing WindowsEditor user string') from exc
        if value != FALLBACK_VALUE:
            raise ValueError('Existing WindowsEditor fallback token does not match')
        # Guard the JNI/getter call metadata as well as its bytecode tokens.
        if tables.MemberRef is None or len(tables.MemberRef.rows) < 0x33:
            raise ValueError('Client identifier member references are missing')
        for rid, owner, name in (
            (0x32, 'Application', 'get_platform'),
            (0x33, 'SystemInfo', 'get_deviceUniqueIdentifier'),
        ):
            member = tables.MemberRef.rows[rid - 1]
            if (str(getattr(member.Class.row, 'TypeName', '')) != owner
                    or str(member.Name) != name):
                raise ValueError('Unsupported identifier member-reference metadata')
        patched = bytearray(raw)
        patched[offset:offset + len(PATCHED_PREFIX)] = PATCHED_PREFIX
        return bytes(patched)
    finally:
        pe.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--src', required=True, type=Path, help='Input client bundle or raw DLL')
    parser.add_argument('--out', required=True, type=Path, help='Separate patched output file')
    args = parser.parse_args(argv)
    if args.src.resolve() == args.out.resolve():
        parser.error('Use a separate output path; in-place changes are not supported')
    original = args.src.read_bytes()
    try:
        patched = apply_patch(original)
    except ValueError as exc:
        parser.error(str(exc))
    args.out.write_bytes(patched)
    state = 'already safe (unchanged)' if patched == original else 'patched seven-byte getter slot'
    print(f'{args.out}: {state}; {len(patched)} bytes; fallback={FALLBACK_VALUE!r}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
