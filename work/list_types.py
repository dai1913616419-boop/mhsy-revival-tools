import sys,re
import dnfile
p=sys.argv[1]; kw=sys.argv[2] if len(sys.argv)>2 else '.'
pe=dnfile.dnPE(p)
names=[]
def walk(t,prefix=""):
    for td in t.tdefs if hasattr(t,'tdefs') else []:
        full=prefix+td.namespace.value+"."+td.name.value if td.namespace.value else prefix+td.name.value
        names.append(full)
        if hasattr(td,'nested') and td.nested: walk(td,full+"/")
for row in pe.net.mdtables.TypeDef.rows:
    ns=row.TypeNamespace.value or ""; nm=row.TypeName.value or ""
    names.append((ns+"."+nm).lstrip("."))
for n in names:
    if re.search(kw,n,re.I): print(n)
print("TOTAL",len(names))
