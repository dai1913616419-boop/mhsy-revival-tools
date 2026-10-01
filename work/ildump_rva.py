"""按 RVA 反汇编（用于同名重载方法）。
用法: ildump_rva.py <dll> <rva_hex> [起始IL偏移hex] [结束IL偏移hex]
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ildump import Ill, Reader
from dncil.cil.body import CilMethodBody

dll = sys.argv[1]
rva = int(sys.argv[2], 16)
lo = int(sys.argv[3], 16) if len(sys.argv) > 3 else None
hi = int(sys.argv[4], 16) if len(sys.argv) > 4 else None

ill = Ill(dll)
# 反查该 rva 对应的方法
owner = None
name = None
for i, tt in enumerate(ill.mdt.TypeDef.rows, 1):
    for m in (tt.MethodList or []):
        r = m.row
        if r.Rva == rva:
            owner = ((tt.TypeNamespace.value or '') + '.' + (tt.TypeName.value or '')).lstrip('.')
            name = str(r.Name)
if owner is None:
    print('!! no method at rva', hex(rva))
body = CilMethodBody(Reader(ill.pe, rva))
ins = list(body.instructions)
print('=== %s::%s  rva=%s  insns=%d ===' % (owner, name, hex(rva), len(ins)))
for i in ins:
    if lo is not None and i.offset < lo:
        continue
    if hi is not None and i.offset > hi:
        break
    print('  IL_%05x %-12s %s' % (i.offset, i.opcode.name, ill.describe(i)))
