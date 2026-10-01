"""field_owner.py <dll> <field_rid|name> [field2 ...]
给定 FieldDef rid 或字段名，打印其所属类型与类型提示。
也可用 --list <TypeNamePattern> 列出该类型全部字段。
"""
import sys, dnfile

dll = sys.argv[1]
pe = dnfile.dnPE(dll)
mdt = pe.net.mdtables
rows = list(mdt.Field.rows)
rid_of = {id(r): i for i, r in enumerate(rows, 1)}

# field rid -> owner type name
owner = {}
for t in mdt.TypeDef.rows:
    tn = ((t.TypeNamespace.value or '') + '.' + (t.TypeName.value or '')).lstrip('.')
    for f in (t.FieldList or []):
        r = f.row
        i = rid_of.get(id(r))
        if i is not None:
            owner.setdefault(i, tn)

args = sys.argv[2:]
if args and args[0] == '--list':
    pat = args[1].lower()
    for t in mdt.TypeDef.rows:
        tn = ((t.TypeNamespace.value or '') + '.' + (t.TypeName.value or '')).lstrip('.')
        if pat in tn.lower():
            print('===', tn)
            for f in (t.FieldList or []):
                r = f.row
                i = rid_of.get(id(r))
                fsig = r.Signature.value if hasattr(r.Signature, 'value') else None
                print('   rid=%d  %s' % (i, r.Name))
    sys.exit(0)

for a in args:
    if a.isdigit():
        i = int(a)
        print('field rid=%d  owner=%s  name=%s' % (i, owner.get(i, '?'), rows[i-1].Name))
    else:
        for i, r in enumerate(rows, 1):
            if str(r.Name) == a:
                print('field name=%s  rid=%d  owner=%s' % (a, i, owner.get(i, '?')))
