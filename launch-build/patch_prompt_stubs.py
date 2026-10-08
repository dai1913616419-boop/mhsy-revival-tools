"""Normalize MainPlayer prompt stubs for Unity's old Mono JIT.

The historical patches replace two bytes but leave the old CodeSize and EH
sections. Mono may validate unreachable garbage after ret. Shrink each method's
code length and clear exception/local metadata without moving any method RVA.
"""
import struct
import dnfile

TARGETS = ('DailyTaskPromptState', 'OnceTaskPromptState', 'TeQuanFuLiPromptState')

def patch_prompt_stubs(data):
    data = bytearray(data)
    pe_start = data.find(b'MZ')
    pe = dnfile.dnPE(data=bytes(data[pe_start:]))
    checked = []
    for t in pe.net.mdtables.TypeDef.rows:
        if str(t.TypeName) != 'MainPlayer':
            continue
        for m in t.MethodList:
            r = m.row
            if str(r.Name) not in TARGETS:
                continue
            assert bytes(r.Signature.value) == b'\x20\x00\x02', str(r.Name)
            p = pe_start + pe.get_offset_from_rva(r.Rva)
            flags = struct.unpack_from('<H', data, p)[0]
            assert flags >> 12 == 3 and flags & 3 == 3, str(r.Name)
            assert data[p+12:p+14] == b'\x16\x2a', str(r.Name)
            struct.pack_into('<HHII', data, p, 0x3003, 1, 2, 0)
            checked.append(str(r.Name))
    assert set(checked) == set(TARGETS), checked
    return data
