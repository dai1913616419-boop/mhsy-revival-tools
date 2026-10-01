"""按方法名（忽略大小写，支持正则）全局查找方法 -> (类, rva)。"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dnfile

DLL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "apk", "Client_4201.dll")
if len(sys.argv) > 2:
    DLL = sys.argv[2] if os.sep in sys.argv[2] else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "apk", "managed", sys.argv[2])
PAT = re.compile(sys.argv[1], re.I)

pe = dnfile.dnPE(DLL)
mdt = pe.net.mdtables

for t in mdt.TypeDef.rows:
    tn = "%s.%s" % (t.TypeNamespace.value or "", t.TypeName.value)
    for m in (t.MethodList or []):
        r = m.row
        n = str(r.Name)
        if PAT.search(n):
            print("%-45s rva=%-10s %s" % (tn, hex(r.Rva) if r.Rva else "-", n))
