import sys, dnfile
pe = dnfile.dnPE(sys.argv[1])
mdt = pe.net.mdtables
pat = sys.argv[2]
for t in mdt.TypeDef.rows:
    tn = (t.TypeNamespace.value or '') + '.' + (t.TypeName.value or '')
    if pat.lower() in tn.lower():
        print('===', tn)
        for m in (t.MethodList or []):
            r = m.row
            print(f'  0x{r.Rva:x}  {r.Name}')
