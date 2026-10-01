"""find_fieldrefs.py <dll> <field_rid>  扫描 ldfld/stfld/ldflda 引用并定位所属方法"""
import sys, bisect, dnfile
pe = dnfile.dnPE(sys.argv[1]); mdt = pe.net.mdtables
rid = int(sys.argv[2]); tok = (0x04 << 24) | rid
name_by_rva = {}
for t in mdt.TypeDef.rows:
    tn = (t.TypeNamespace.value or '') + '.' + (t.TypeName.value or '')
    for m in (t.MethodList or []):
        r = m.row
        if r.Rva: name_by_rva[r.Rva] = tn + '::' + str(r.Name)
rv = sorted(name_by_rva)
data = open(sys.argv[1],'rb').read()
tb = tok.to_bytes(4,'little')
for opc, nm in ((0x7B,'ldfld'),(0x7C,'ldflda'),(0x7D,'stfld'),(0x7E,'stsfld'),(0x80,'stsfld?')):
    pat = bytes([opc]) + tb
    off=0; hits=[]
    while True:
        i = data.find(pat, off)
        if i<0: break
        hits.append(i); off=i+1
    if not hits: continue
    print(f'--- {nm} ({len(hits)})')
    for i in hits:
        rva=None
        for s in pe.sections:
            if s.PointerToRawData <= i < s.PointerToRawData + max(s.SizeOfRawData, s.Misc_VirtualSize):
                rva = s.VirtualAddress + (i - s.PointerToRawData)
        o = rv[bisect.bisect_right(rv, rva)-1] if rva else None
        print(f'   rva={hex(rva)}  {name_by_rva.get(o,"?")}')
