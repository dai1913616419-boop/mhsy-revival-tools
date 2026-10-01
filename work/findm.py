"""按方法名查找：print_find_method.py <dll> <name> [name2 ...]"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dnfile

pe = dnfile.dnPE(sys.argv[1])
mdt = pe.net.mdtables
names = set(sys.argv[2:])
for i, t in enumerate(mdt.TypeDef.rows, 1):
    tn = ((t.TypeNamespace.value or '') + '.' + (t.TypeName.value or '')).lstrip('.')
    for m in (t.MethodList or []):
        r = m.row
        if str(r.Name) in names:
            print('mdef#%-6d rva=%-10s %s::%s' % (m.row_index,
                  hex(r.Rva) if r.Rva else '-', tn, r.Name))
