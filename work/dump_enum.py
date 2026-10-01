"""dump_enum.py <dll> <EnumNamePattern>  列出枚举成员及常量值"""
import sys, dnfile

dll, pat = sys.argv[1], sys.argv[2].lower()
pe = dnfile.dnPE(dll)
mdt = pe.net.mdtables

# Constant 表: 按 parent (Field rid) 索引
const_by_field = {}
try:
    for c in mdt.Constant.rows:
        try:
            par = c.Parent
            if par.table is not None and par.table.name == 'Field':
                const_by_field[par.row_index] = c.Value
        except Exception:
            pass
except Exception as e:
    print('constant table err', e)

rows = list(mdt.Field.rows)
idx = {id(r): i for i, r in enumerate(rows, 1)}

for t in mdt.TypeDef.rows:
    tn = ((t.TypeNamespace.value or '') + '.' + (t.TypeName.value or '')).lstrip('.')
    if pat not in tn.lower():
        continue
    print('=== %s' % tn)
    for f in (t.FieldList or []):
        r = f.row
        rid = idx.get(id(r))
        val = const_by_field.get(rid)
        v = val.value if val is not None and hasattr(val, 'value') else val
        print('   %-40s = %s' % (r.Name, v))
