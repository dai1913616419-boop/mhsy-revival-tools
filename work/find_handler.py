"""查找某个 handler 方法所属的 TypeDef（按方法名），并可选反汇编。
用法: find_handler.py <dll> <MethodName> [lo] [hi]
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ildump import Ill

dll = sys.argv[1]
target = sys.argv[2]
lo = int(sys.argv[3], 16) if len(sys.argv) > 3 else None
hi = int(sys.argv[4], 16) if len(sys.argv) > 4 else None

ill = Ill(dll)
hits = []
for i, tt in enumerate(ill.mdt.TypeDef.rows, 1):
    ns = tt.TypeNamespace.value or ''
    tn = tt.TypeName.value or ''
    full = (ns + '.' + tn).lstrip('.')
    for m in tt.MethodList:
        if str(m.row.Name) == target:
            hits.append((i, full, m.row))

print('hits for %s: %d' % (target, len(hits)))
for i, full, row in hits:
    print('  typedef#%d  %s  rva=%s' % (i, full, hex(row.Rva)))

if len(sys.argv) > 2 and hits:
    i, full, row = hits[0]
    ill.dump(full, target, lo, hi)
