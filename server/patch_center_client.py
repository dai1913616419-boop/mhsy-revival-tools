"""补丁：强制创建中心服连接。

目标方法: .ᜀ::ᜀ  rva=0x1a78d4 （FetchServerList 协程 MoveNext）
原 IL:
    callvirt  op_Inequality        ; GetSingleton().ᜁ != ""
    brtrue.s  -> IL_1a5f32         ; 满足则直接创建中心服连接
    ldarg.0 ; ldfld UserAccount
    call      IsNullOrEmpty
    brtrue.s  -> skip              ; UserAccount 为空 -> 跳过创建（我们绕过 SDK 后账号为空，命中这里）

补丁: 把第一条 brtrue.s (0x2D) 改成 br.s (0x2B)，无条件走"创建中心服连接"。
等长替换，不影响方法体长度。
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "work"))
import dnfile
from dncil.cil.body import CilMethodBody
from dncil.clr.token import Token
from disasm3 import Reader

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "work", "apk", "Client_4201.dll")
DST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "work", "apk",
                   "Client_patched_center.dll")

RVA = 0x1A78D4

pe = dnfile.dnPE(SRC)
mdt = pe.net.mdtables

r = None
for t in mdt.TypeDef.rows:
    for m in (t.MethodList or []):
        if m.row.Rva == RVA:
            r = m.row
            break

body = CilMethodBody(Reader(pe, r.Rva))
ins = body.instructions

# 找 ldstr "" ; call op_Inequality ; brtrue.s 序列
target = None
for i in range(len(ins) - 2):
    a, b, c = ins[i], ins[i + 1], ins[i + 2]
    if a.opcode.name == "ldstr" and str(a.operand) == "":
        if b.opcode.name == "callvirt" and isinstance(b.operand, Token) \
                and str(mdt.MemberRef.rows[(b.operand.value & 0xFFFFFF) - 1].Name) \
                == "op_Inequality":
            if c.opcode.name == "brtrue.s":
                target = (i, c)
                break

if target is None:
    print("未找到目标指令序列")
    sys.exit(1)

i, br = target
print("找到: IL偏移=0x%x  %s -> 0x%x" % (br.offset, br.opcode.name, br.operand))
print("上下文:")
for j in range(max(0, i - 1), i + 4):
    print("   0x%x  %s %s" % (ins[j].offset, ins[j].opcode.name, ins[j].operand))

# 计算文件偏移: IL 流起始 = RVA 对应文件偏移 + 头部长度
code_start_fo = pe.get_offset_from_rva(r.Rva)
# fat header: 12 字节（flags 2 + size 2 + maxstack 2 + codesize 4 + varsig 4）
hdr = pe.__data__[code_start_fo:code_start_fo + 1]
if hdr[0] & 3 == 2:            # tiny
    hdr_len = 1
else:                           # fat
    hdr_len = 12
il_fo = code_start_fo + hdr_len
patch_fo = il_fo + br.offset
data = pe.__data__[patch_fo:patch_fo + 2]
print("文件偏移 0x%x  当前字节=%s" % (patch_fo, data.hex()))
assert data[0] == 0x2D, "期望 brtrue.s (0x2D)，实际 %s" % data.hex()

shutil.copy(SRC, DST)
with open(DST, "r+b") as f:
    f.seek(patch_fo)
    f.write(bytes([0x2B, data[1]]))     # brtrue.s -> br.s
print("已写出补丁 DLL:", DST)

# 验证
pe2 = dnfile.dnPE(DST)
r2 = None
for t in pe2.net.mdtables.TypeDef.rows:
    for m in (t.MethodList or []):
        if m.row.Rva == RVA:
            r2 = m.row
            break
body2 = CilMethodBody(Reader(pe2, r2.Rva))
for op in body2.instructions:
    if op.offset == br.offset:
        print("验证: IL 0x%x -> %s %s" % (op.offset, op.opcode.name, op.operand))
