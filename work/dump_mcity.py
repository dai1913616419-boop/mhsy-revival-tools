# -*- coding: utf-8 -*-
"""反汇编 MainCityEntryInfo 的初始化链路：ᝁ::.cctor / ᝁ::ᜏ / MainCityEntryInfo::.ctor"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ildump import Ill

ill = Ill('apk/Client_4201.dll')

# 找出所有名为 ᝁ 的 TypeDef
print('=== 所有 TypeDef 名含 ᝁ 的 ===')
cnt = 0
for i, td in enumerate(ill.mdt.TypeDef.rows, 1):
    tn = ill.TN[i]
    if tn.endswith('ᝁ') or tn == 'ᝁ':
        print('  #%d %s  fields=%s  methods=%s' % (
            i, tn,
            ', '.join(str(f.row.Name) for f in (td.FieldList or [])),
            ','.join(str(m.row.Name) for m in (td.MethodList or []))))
        cnt += 1
print('  共', cnt)

print()
print('=== MainCityEntryInfo::.ctor ===')
try:
    ill.dump('MobileGameDemo.MainCityEntryInfo', '.ctor')
except Exception as e:
    print('  err', e)

print()
print('=== ᝁ::.cctor ===')
try:
    ill.dump('ᝁ', '.cctor')
except Exception as e:
    print('  err', e)

print()
print('=== ᝁ::ᜏ ===')
try:
    ill.dump('ᝁ', 'ᜏ')
except Exception as e:
    print('  err', e)
