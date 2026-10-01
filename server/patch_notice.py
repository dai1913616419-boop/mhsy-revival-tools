#!/usr/bin/env python
"""在已有补丁 DLL 基础上追加：InGameNoticeSystem::Open 开头直接 ret。
使登录主城后的「活动公告」自动弹窗不再出现（其关闭按钮绑定在缺资源环境下失效，
会全屏遮罩锁死 UI，见 output/13 报告）。
方法体长度不变（仅首条 IL 改为 ret 0x2A），无需修正 PE 偏移。
"""
import sys, dnfile
from dncil.cil.body import CilMethodBody
sys.path.insert(0, r'C:/Users/19136/WorkBuddy/復活工程/work')
from disasm3 import Reader

SRC = r'C:/Users/19136/WorkBuddy/復活工程/work/apk/Client_patched.bin'
OUT = r'C:/Users/19136/WorkBuddy/復活工程/work/apk/Client_patched2.bin'
TARGET_RVA = 0x16046c  # MobileGameDemo.InGameNoticeSystem::Open

data = bytearray(open(SRC, 'rb').read())
print('输入', len(data), 'bytes')

# 定位内嵌 PE 起点（MZ + 后续存在 BSJB 即可，与 patch_client_dll 一致）
pe_off = None
i = 0
while True:
    i = data.find(b'MZ', i)
    if i < 0: break
    if b'BSJB' in bytes(data[i:]):
        pe_off = i; break
    i += 1
if pe_off is None:
    raise SystemExit('未找到内嵌 PE')
print('PE 起点 0x%x' % pe_off)

import io, os, tempfile
TMP = os.path.join(tempfile.gettempdir(), '_notice_probe.dll')
open(TMP, 'wb').write(bytes(data[pe_off:]))
pe = dnfile.dnPE(TMP)
# rva -> file offset(相对 PE)
def r2o(rva):
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.SizeOfRawData, s.Misc_VirtualSize):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    raise SystemExit('rva 不在 section 内')
off = r2o(TARGET_RVA)
print('方法体头 PE 内偏移 0x%x' % off)

# 解析方法体头确定 IL 起点
b0 = data[pe_off + off]
if b0 & 3 == 2:
    il_rel = 1; print('tiny 头')
else:
    il_rel = 12; print('fat 头  flags=0x%x size=%d' % (b0 & 3, (b0 >> 12) & 0xF))
il_abs = pe_off + off + il_rel
old = bytes(data[il_abs:il_abs+4])
data[il_abs] = 0x2A  # ret
print('IL 0x%x: %s -> 2a (ret)' % (il_abs, old.hex(' ')))

open(OUT, 'wb').write(bytes(data))
print('已写出', OUT)

# 验证
open(TMP, 'wb').write(bytes(data[pe_off:]))
pe2 = dnfile.dnPE(TMP)
body = CilMethodBody(Reader(pe2, TARGET_RVA))
print('验证: 方法前 3 条指令:', [(i.opcode.name) for i in body.instructions[:3]])
