# -*- coding: utf-8 -*-
"""反汇编 901 重连 handler，确认重连后角色位置的来源。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ildump import Ill

ill = Ill('apk/Client_4201.dll')

print('=== ᝁ::OnReConnectRet（901 handler）===')
try:
    ill.dump('ᝁ', 'OnReConnectRet')
except Exception as e:
    print('  err', e)
