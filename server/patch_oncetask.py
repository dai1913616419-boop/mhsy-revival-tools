#!/usr/bin/env python
"""16b 补丁：MainPlayer::OnceTaskPromptState 开头直接 ldc.i4.0; ret。

现象：主城每帧 NRE at MainPlayer.OnceTaskPromptState（空/非空任务字典都炸），
中断 DaTingMainUISystem.Open 后半段（UIPrompt 任务提示与后续按钮注册），
任务按钮点击无响应。该 NRE 自阶段 12 起就共存（旧 logcat 缓冲未覆盖到，误判为新）。

方法返回 bool（是否有可领取任务），直接回 false = "无任务提示"，
不依赖 OnceTaskPropertyCfgMgr，绕开空引用；任务列表 UI 数据仍由 1103/1101 提供。
方法体只改前两条 IL，长度不变。
"""
import sys, os, tempfile, dnfile

SRC = r'C:/Users/19136/WorkBuddy/復活工程/work/apk/Client_patched4.bin'
OUT = r'C:/Users/19136/WorkBuddy/復活工程/work/apk/Client_patched5.bin'
TARGETS = [0x60e48]  # MainPlayer::OnceTaskPromptState

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
tmp = os.path.join(tempfile.gettempdir(), '_ot_probe.dll')
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
    data[il_abs] = 0x16      # ldc.i4.0
    data[il_abs + 1] = 0x2A  # ret
    print('rva 0x%x IL 0x%x: %s -> 16 2a (ldc.i4.0; ret)' % (rva, il_abs, old.hex(' ')))

open(OUT, 'wb').write(bytes(data))
print('已写出', OUT)
