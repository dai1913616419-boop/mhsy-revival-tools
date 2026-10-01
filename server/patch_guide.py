#!/usr/bin/env python
"""追加补丁：GuideClickSystem::Open / Show 开头直接 ret。
引导点击遮罩（isShieldedClick 全屏 collider）在缺资源环境下锁死主城全部点击；
配合服务端 Varis(NG_*=1) 跳过引导逻辑，此补丁确保遮罩 UI 永不出现。
方法体长度不变（仅首条 IL 改 ret 0x2A）。
"""
import sys, os, tempfile, dnfile
from dncil.cil.body import CilMethodBody
sys.path.insert(0, r'C:/Users/19136/WorkBuddy/復活工程/work')
from disasm3 import Reader

SRC = r'C:/Users/19136/WorkBuddy/復活工程/work/apk/Client_patched2.bin'
OUT = r'C:/Users/19136/WorkBuddy/復活工程/work/apk/Client_patched3.bin'
TARGETS = [0x15cdfc, 0x15d368]  # GuideClickSystem::Open / Show

data = bytearray(open(SRC, 'rb').read())
pe_off = None
i = 0
while True:
    i = data.find(b'MZ', i)
    if i < 0: break
    if b'BSJB' in bytes(data[i:]):
        pe_off = i; break
    i += 1
print('PE 起点 0x%x' % pe_off)
tmp = os.path.join(tempfile.gettempdir(), '_guide_probe.dll')
open(tmp, 'wb').write(bytes(data[pe_off:]))
pe = dnfile.dnPE(tmp)

def r2o(rva):
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.SizeOfRawData, s.Misc_VirtualSize):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    raise SystemExit('rva 越界')

for rva in TARGETS:
    off = r2o(rva)
    b0 = data[pe_off + off]
    il_rel = 1 if (b0 & 3) == 2 else 12
    il_abs = pe_off + off + il_rel
    old = bytes(data[il_abs:il_abs+4])
    data[il_abs] = 0x2A
    print('rva 0x%x IL 0x%x: %s -> 2a (ret)' % (rva, il_abs, old.hex(' ')))

open(OUT, 'wb').write(bytes(data))
print('已写出', OUT)
