"""在 ProtobufSerializer.dll 中按 WriteFieldHeader 序列定位类型的 Write/Read。

用法: python find_ser2.py <字段序列,如 "1:0,2:2,3:2">
输出匹配的 Write 方法 RVA 和相邻的 Read 方法候选。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dnfile
from dncil.cil.body import CilMethodBody
from dncil.clr.token import Token
from disasm3 import Reader

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, "protobuf_serializer.dll")

want = []
if len(sys.argv) > 1:
    for part in sys.argv[1].split(","):
        f, w = part.split(":")
        want.append((int(f), int(w)))
else:
    want = [(1, 0), (2, 2), (3, 2)]

pe = dnfile.dnPE(DLL)
mdt = pe.net.mdtables


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


def const_value(op):
    """返回 ldc.i4* 的常数值，非常数指令返回 None。"""
    n = op.opcode.name
    if n in ("ldc.i4", "ldc.i4.s", "ldc.i8"):
        return op.operand if isinstance(op.operand, int) else None
    if n == "ldc.i4.m1":
        return -1
    if n.startswith("ldc.i4."):
        try:
            return int(n.split(".")[2])
        except Exception:
            return None
    return None


t = mdt.TypeDef.rows[1]
methods = [m.row for m in (t.MethodList or []) if m.row.Rva]
print("方法数 %d, 目标序列 %s" % (len(methods), want))

bodies = {}
for r in methods:
    try:
        bodies[r.Rva] = CilMethodBody(Reader(pe, r.Rva))
    except Exception:
        pass

results = []
for rva, body in bodies.items():
    ins = body.instructions
    seq = []
    for i, op in enumerate(ins):
        if op.opcode.name not in ("call", "callvirt"):
            continue
        if not isinstance(op.operand, Token):
            continue
        nm = refname(op.operand.value)
        if "WriteFieldHeader" not in nm:
            continue
        consts = [v for v in (const_value(x) for x in ins[max(0, i - 6):i])
                  if v is not None]
        if len(consts) >= 2:
            seq.append((consts[-2], consts[-1]))
    if seq[:len(want)] == want or seq == want:
        results.append((rva, seq))

print("匹配 Write 方法 %d 个" % len(results))
for rva, seq in sorted(results):
    print("  Write rva=0x%x  seq=%s" % (rva, seq))

# 找每个 Write 对应的 Read，并打印 Read 的调用集合
allrva = sorted(bodies)
for rva, seq in sorted(results):
    idx = allrva.index(rva)
    for j in range(idx + 1, len(allrva)):
        cand = allrva[j]
        ins = bodies[cand].instructions
        names = [refname(x.operand.value) for x in ins
                 if x.opcode.name in ("call", "callvirt")
                 and isinstance(x.operand, Token)]
        if any("ReadFieldHeader" in n for n in names):
            reads = sorted(set(n for n in names if n.startswith("Read")))
            print("  Write rva=0x%x seq=%s -> Read rva=0x%x %s"
                  % (rva, seq, cand, reads))
            break
