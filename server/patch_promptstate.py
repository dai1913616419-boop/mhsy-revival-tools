#!/usr/bin/env python
"""16b-2 补丁：MainPlayer::DailyTaskPromptState / TeQuanFuLiPromptState 开头 ldc.i4.0; ret。

背景：DaTingMainUISystem.Open() 依次调用三个 PromptState：
  OnceTaskPromptState (0x60e48)   —— patched5 已补丁
  DailyTaskPromptState (0x60dbc)  —— 本次
  TeQuanFuLiPromptState (0x60ed4) —— 本次
三者都以 mCompleteMember / Attribute 为起点，空引用 NRE 会中断 Open 后半段，
导致主城 UI（含任务/挑战按钮注册）无法完成 -> 表现为主城加载条卡在 90%。

三者返回类型均为 bool（IL 尾部为 ldc.i4.x; ret），直接回 false = "无提示"，
不依赖数据，绕开空引用；任务/福利列表 UI 数据仍由 1103/1101 等服务端消息提供。

从 Client_patched5.bin（已含 OnceTask 补丁）出发，产出 Client_patched6.bin。
"""
import os, tempfile, dnfile

SRC = r'C:/Users/19136/WorkBuddy/復活工程/work/apk/Client_patched5.bin'
OUT = r'C:/Users/19136/WorkBuddy/復活工程/work/apk/Client_patched6.bin'
TARGETS = [
    (0x60dbc, 'DailyTaskPromptState'),
    (0x60ed4, 'TeQuanFuLiPromptState'),
]

data = bytearray(open(SRC, 'rb').read())
pe_off = None
i = 0
while True:
    i = data.find(b'MZ', i)
    if i < 0:
        break
    if b'BSJB' in bytes(data[i:]):
        pe_off = i
        break
    i += 1
print('PE 起点 0x%x' % pe_off)
tmp = os.path.join(tempfile.gettempdir(), '_ps_probe.dll')
open(tmp, 'wb').write(bytes(data[pe_off:]))
pe = dnfile.dnPE(tmp)


def r2o(rva):
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.SizeOfRawData, s.Misc_VirtualSize):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    raise SystemExit('rva 越界')


for rva, name in TARGETS:
    off = r2o(rva)
    b0 = data[pe_off + off]
    il_rel = 1 if (b0 & 3) == 2 else 12
    il_abs = pe_off + off + il_rel
    old = bytes(data[il_abs:il_abs + 4])
    data[il_abs] = 0x16      # ldc.i4.0
    data[il_abs + 1] = 0x2A  # ret
    print('%-24s rva 0x%x IL 0x%x: %s -> 16 2a' % (name, rva, il_abs, old.hex(' ')))

open(OUT, 'wb').write(bytes(data))
print('已写出', OUT)
