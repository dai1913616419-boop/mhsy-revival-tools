#!/usr/bin/env python
"""追加补丁：DrawBaoXiangProperty::UpdateZS10PriceFromServer 开头直接 ret。
APK 内旧版 Msg.dll 无 ZSDrawBaoXiangPriceInfo 字段 -> 客户端(4.2.0.1)的
get_zsDrawBaoXiang10PriceInfo() 返回 null -> ldarg.1 callvirt NRE，
中断 MainPlayer.UnPackData，导致主玩家数据不完整（进副本 OnEvent NRE 根因链首环）。
跳过价格更新 + 事件 630（抽卡 UI 价格刷新）无副作用。
方法体长度不变（仅首条 IL 改 ret 0x2A）。
"""
import sys, os, tempfile, dnfile
from dncil.cil.body import CilMethodBody
sys.path.insert(0, r'C:/Users/19136/WorkBuddy/復活工程/work')
from disasm3 import Reader

SRC = r'C:/Users/19136/WorkBuddy/復活工程/work/apk/Client_patched3.bin'
OUT = r'C:/Users/19136/WorkBuddy/復活工程/work/apk/Client_patched4.bin'
TARGETS = [0x6f09f]  # DrawBaoXiangProperty::UpdateZS10PriceFromServer

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
tmp = os.path.join(tempfile.gettempdir(), '_zs_probe.dll')
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
