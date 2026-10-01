"""列出指定类型（按名字片段）的所有方法名 + RVA + 签名。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dnfile

DLL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "apk", "Client_4201.dll")
PAT = sys.argv[1] if len(sys.argv) > 1 else "NetworkManager"

pe = dnfile.dnPE(DLL)
mdt = pe.net.mdtables

for t in mdt.TypeDef.rows:
    tn = "%s.%s" % (t.TypeNamespace.value or "", t.TypeName.value)
    if PAT.lower() not in tn.lower():
        continue
    print("### %s" % tn)
    for m in (t.MethodList or []):
        r = m.row
        print("   rva=%-10s %s" % (hex(r.Rva) if r.Rva else "-", str(r.Name)))
    print("   --- 字段 ---")
    for f in (t.FieldList or []):
        fr = f.row
        print("   %s" % str(fr.Name))
