# -*- coding: utf-8 -*-
"""反汇编 103 的 handler，确认出生点的消费时机。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ildump import Ill

ill = Ill('apk/Client_4201.dll')

# 找 handler 所属类型（ᝁ 类里）
print('=== ᝁ::OnSetMainCityBornPos（103 handler）===')
try:
    ins = ill.dump('ᝁ', 'OnSetMainCityBornPos')
except Exception as e:
    print('  err', e)

print()
print('=== ᝁ::OnQuestFirstEnterRegionRet（102 handler）===')
try:
    ins2 = ill.dump('ᝁ', 'OnQuestFirstEnterRegionRet')
except Exception as e:
    print('  err', e)
