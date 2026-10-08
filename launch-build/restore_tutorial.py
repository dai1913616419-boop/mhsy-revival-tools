"""Selectively undo only the historical GuideClick early-return patches."""
import dnfile

TARGETS = (0x15cdfc, 0x15d368)


def restore_guide_click(client: bytes | bytearray, original_dll: bytes) -> bytearray:
    data = bytearray(client)
    start = data.find(b'MZ')
    while start >= 0 and data[start + int.from_bytes(data[start + 0x3c:start + 0x40], 'little'):][:4] != b'PE\0\0':
        start = data.find(b'MZ', start + 1)
    if start < 0:
        raise ValueError('Embedded client PE not found')
    original = dnfile.dnPE(data=original_dll)
    current = dnfile.dnPE(data=bytes(data[start:]))
    for rva in TARGETS:
        src = original.get_offset_from_rva(rva)
        dst = start + current.get_offset_from_rva(rva)
        first = original_dll[src]
        if first & 3 == 2:
            header, code_size = 1, first >> 2
        else:
            header = (int.from_bytes(original_dll[src:src + 2], 'little') >> 12) * 4
            code_size = int.from_bytes(original_dll[src + 4:src + 8], 'little')
        assert data[dst:dst + header] == original_dll[src:src + header], hex(rva)
        assert data[dst + header] == 0x2a, f'{rva:x}: expected historical ret patch'
        assert data[dst + header + 1:dst + header + code_size] == original_dll[src + header + 1:src + header + code_size], hex(rva)
        data[dst + header] = original_dll[src + header]
    original.close()
    current.close()
    return data
