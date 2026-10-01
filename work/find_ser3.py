"""扫描 ProtobufSerializer，输出每个 Write 方法的 (field, wiretype) 序列。
用法: python find_ser3.py [min_fields]
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dnfile
from dncil.cil.body import CilMethodBody
from dncil.clr.token import Token
from disasm3 import Reader

DLL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "protobuf_serializer.dll")
MIN = int(sys.argv[1]) if len(sys.argv) > 1 else 6

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


def cval(op):
    """ldc.i4.x 短格式值在操作码名里；长格式在 operand。"""
    n = op.opcode.name
    if n == "ldc.i4.m1":
        return -1
    if n.startswith("ldc.i4.") and n[-1].isdigit():
        return int(n[-1])
    if n.startswith("ldc.i4"):
        return op.operand
    return None


def is_const(op):
    return op.opcode.name.startswith("ldc.i4") and cval(op) is not None


t = mdt.TypeDef.rows[1]  # ProtobufSerializer
for m in (t.MethodList or []):
    r = m.row
    if not r.Rva:
        continue
    try:
        body = CilMethodBody(Reader(pe, r.Rva))
    except Exception:
        continue
    ins = body.instructions
    seq = []
    for i, op in enumerate(ins):
        if op.opcode.name not in ("callvirt", "call") or not isinstance(op.operand, Token):
            continue
        nm = refname(op.operand.value)
        if "WriteFieldHeader" not in nm:
            continue
        consts = [cval(x) for x in ins[max(0, i - 6):i] if is_const(x)]
        if len(consts) >= 2:
            seq.append((consts[-2], consts[-1]))
    if len(seq) >= MIN:
        print("rva=0x%-7x fields=%d  %s" % (r.Rva, len(seq), seq))
