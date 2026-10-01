"""在 ProtobufSerializer.dll 中定位某类型的 Write/Read 方法。

用法: python find_ser.py
通过扫描 Write 方法里的 WriteFieldHeader(字段号, 线型) 序列来匹配消息布局。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dnfile
from dncil.cil.body import CilMethodBody
from dncil.clr.token import Token
from disasm3 import Reader

DLL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "protobuf_serializer.dll")

pe = dnfile.dnPE(DLL)
mdt = pe.net.mdtables

# 收集 MemberRef 名字（WriteFieldHeader 等）
def refname(tok):
    tb = (tok >> 24) & 0xFF
    rid = tok & 0xFFFFFF
    try:
        if tb == 0x0A:
            return str(mdt.MemberRef.rows[rid - 1].Name)
        if tb == 0x06:
            return str(mdt.MethodDef.rows[rid - 1].Name)
    except Exception:
        pass
    return "?"


# 目标布局: [(字段号, 线型, 调用名), ...]
TARGET = [(1, 0, "WriteInt32"), (2, 2, "WriteObject"), (3, 2, "WriteString")]

t = mdt.TypeDef.rows[1]
methods = []
for m in (t.MethodList or []):
    r = m.row
    if r.Rva:
        methods.append(r)

hits = []
for r in methods:
    try:
        body = CilMethodBody(Reader(pe, r.Rva))
    except Exception:
        continue
    ins = body.instructions
    seq = []
    for i, op in enumerate(ins):
        if op.opcode.name not in ("callvirt", "call") or not isinstance(op.operand, Token):
            continue
        name = refname(op.operand.value)
        if not name.startswith("WriteFieldHeader"):
            continue
        consts = [x.operand for x in ins[max(0, i - 5):i]
                  if x.opcode.name in ("ldc.i4", "ldc.i4.s")
                  and isinstance(x.operand, int)]
        if len(consts) >= 2:
            seq.append((consts[-2], consts[-1], name))
    got = [(f, w) for f, w, _ in seq]
    if got == [(1, 0), (2, 2), (3, 2)]:
        hits.append((hex(r.Rva), str(r.Name), seq))

for rva, name, seq in hits:
    print("=== %s %s ===" % (rva, name))
    for f, w, n in seq:
        print("   WriteFieldHeader(%d, %d) + %s" % (f, w, n))
