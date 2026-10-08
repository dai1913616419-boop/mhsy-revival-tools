"""Regression check: Mono must see only 'ldc.i4.0; ret', not leftover IL/EH."""
from pathlib import Path
import struct
import sys
import unittest
import dnfile

TARGETS = ('DailyTaskPromptState', 'OnceTaskPromptState', 'TeQuanFuLiPromptState')

def verify_stub_bodies(data):
    pe_start = data.find(b'MZ')
    pe = dnfile.dnPE(data=data[pe_start:])
    checked = []
    for t in pe.net.mdtables.TypeDef.rows:
        if str(t.TypeName) != 'MainPlayer':
            continue
        for m in t.MethodList:
            r = m.row
            if str(r.Name) not in TARGETS:
                continue
            p = pe_start + pe.get_offset_from_rva(r.Rva)
            flags, stack, size, locals_token = struct.unpack_from('<HHII', data, p)
            assert size == 2, f'{r.Name}: Mono still sees {size} IL bytes'
            assert flags == 0x3003, f'{r.Name}: unexpected flags/EH sections {flags:x}'
            assert stack == 1 and locals_token == 0, str(r.Name)
            assert data[p+12:p+14] == b'\x16\x2a', str(r.Name)
            checked.append(str(r.Name))
    assert set(checked) == set(TARGETS), checked

class PromptStubTest(unittest.TestCase):
    def test_actual_client_stub_bodies(self):
        verify_stub_bodies(Path(sys.argv[1]).read_bytes())

if __name__ == '__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(PromptStubTest)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
