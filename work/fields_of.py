import sys, dnfile
pe = dnfile.dnPE(sys.argv[1]); mdt = pe.net.mdtables
pat = sys.argv[2]
rows = list(mdt.Field.rows)
idx = {id(r): i for i, r in enumerate(rows, 1)}
seen = set()
for t in mdt.TypeDef.rows:
    tn = (t.TypeNamespace.value or '') + '.' + (t.TypeName.value or '')
    if pat.lower() in tn.lower():
        print('===', tn)
        for f in (t.FieldList or []):
            r = f.row
            rid = idx.get(id(r))
            if rid is None or rid in seen: continue
            seen.add(rid)
            print(f'   rid={rid:>6} tok=0x{(0x04<<24)|rid:08x}  {r.Name}')
