import zipfile, re, sys, json
apk = r'work\apk\mhsy_qihoo_4201.apk'
z = zipfile.ZipFile(apk)
names = [n for n in z.namelist() if n.startswith('assets/bin/Data/')]
pat = re.compile(rb'CAB-([ -~]{3,60})')
named = []
pes = []
for i, n in enumerate(names):
    try:
        with z.open(n) as f:
            head = f.read(8192)
    except Exception:
        continue
    if head[:2] == b'MZ' and b'BSJB' in head[:1024]:
        pes.append(n)
    for m in pat.finditer(head):
        named.append((n, m.group(1).decode('ascii', 'replace')))
    if i % 1000 == 0:
        print('  ...%d/%d' % (i, len(names)), file=sys.stderr)
print('扫描文件数', len(names))
print('CAB 资产名条目', len(named))
print('内嵌 PE(DLL) 数', len(pes))
json.dump({'named': named, 'pes': pes}, open(r'work\apk\assets_index.json', 'w', encoding='utf-8'), ensure_ascii=False)
