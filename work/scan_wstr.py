import re,sys,os
path=sys.argv[1]
kw=sys.argv[2] if len(sys.argv)>2 else r'Update|Version|MD5|Resource|http'
d=open(path,'rb').read()
pat=re.compile(rb'(?:[\x20-\x7e]\x00){4,}')
for m in pat.finditer(d):
    s=m.group().decode('utf-16le')
    if re.search(kw,s,re.I):
        print(hex(m.start()),'|',s[:200])
