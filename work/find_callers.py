"""find_callers.py <dll> <target_rva_hex> [更多rva...]
扫描全 DLL 的 IL 字节, 找出 call/callvirt/newobj/ldftn 引用这些 MethodDef 的位置,
并映射回所属方法。
"""
import sys, os
import dnfile
from dncil.cil.body import CilMethodBody
from disasm3 import Reader
from usheap import USResolver

dll = sys.argv[1]
targets = [int(a, 16) if not a.startswith('0x') else int(a, 16) for a in sys.argv[2:]]
pe = dnfile.dnPE(dll)
mdt = pe.net.mdtables
us = USResolver(pe)

# rva -> (token, name)
tok_by_rva = {}
name_by_rva = {}
owner_of = {}   # rva -> owner type name
for t in mdt.TypeDef.rows:
    tn = (t.TypeNamespace.value or '') + '.' + (t.TypeName.value or '')
    for ti, m in enumerate(t.MethodList or []):
        r = m.row
        if r.Rva:
            tok_by_rva[r.Rva] = (0x06 << 24) | (r.row_index if hasattr(r,'row_index') else 0)
            name_by_rva[r.Rva] = tn + '::' + str(r.Name)
for i, m in enumerate(mdt.MethodDef.rows, 1):
    if m.Rva:
        tok_by_rva[m.Rva] = (0x06 << 24) | i
        if m.Rva not in name_by_rva:
            name_by_rva[m.Rva] = '?::' + str(m.Name)

# owner map: for each rva range
rv = sorted(r for r in tok_by_rva if r)
def owner(rva):
    import bisect
    i = bisect.bisect_right(rv, rva) - 1
    return rv[i] if i >= 0 else None

want = {}
for t in targets:
    if t in tok_by_rva:
        want[tok_by_rva[t]] = name_by_rva.get(t, hex(t))
    else:
        print('!! 未找到 rva', hex(t)); 
print('目标 token:', {hex(k): v for k, v in want.items()})

data = open(dll, 'rb').read()
# map rva -> file offset
def r2o(rva):
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.SizeOfRawData, s.Misc_VirtualSize):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    return None

for tok, nm in want.items():
    pat = bytes([0x28]) + tok.to_bytes(4, 'little')
    # 也匹配 callvirt 0x6F
    for opc in (0x28, 0x6F, 0x73, 0xFE06):
        pb = (bytes([opc]) if opc < 0x100 else bytes([0xFE, 0x06])) + tok.to_bytes(4,'little')
        off = 0
        hits = []
        while True:
            i = data.find(pb, off)
            if i < 0: break
            hits.append(i); off = i + 1
        if hits:
            print(f'\n--- 引用 {nm} (token {hex(tok)}, op {hex(opc)}) : {len(hits)} 处')
            for i in hits[:40]:
                # 找所属方法 rva: 反查 section
                rva = None
                for s in pe.sections:
                    if s.PointerToRawData <= i < s.PointerToRawData + max(s.SizeOfRawData, s.Misc_VirtualSize):
                        rva = s.VirtualAddress + (i - s.PointerToRawData)
                o = owner(rva) if rva else None
                print(f'  fileOff={hex(i)} rva={hex(rva) if rva else "?"}  in {name_by_rva.get(o,"?")}')
