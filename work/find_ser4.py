"""扫描 ProtobufSerializer，输出每个 Write 方法的 [(getter名, field, wiretype)] 序列。
用法: python find_ser4.py <getter名关键字> [关键字2...]
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dnfile
from dncil.cil.body import CilMethodBody
from dncil.clr.token import Token
from disasm3 import Reader

DLL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "protobuf_serializer.dll")
KW = [k.lower() for k in sys.argv[1:]] or None

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
    # 收集所有 callvirt 序列（带索引）
    calls = [(i, refname(op.operand.value)) for i, op in enumerate(ins)
             if op.opcode.name in ("callvirt", "call") and isinstance(op.operand, Token)]
    getters = [(i, n) for i, n in calls if n.startswith("get_")]
    if not getters:
        continue
    seq = []
    for i, op in enumerate(ins):
        if op.opcode.name not in ("callvirt", "call") or not isinstance(op.operand, Token):
            continue
        nm = refname(op.operand.value)
        if "WriteFieldHeader" not in nm:
            continue
        consts = [cval(x) for x in ins[max(0, i - 6):i] if is_const(x)]
        fld = consts[-2] if len(consts) >= 2 else None
        wt = consts[-1] if len(consts) >= 2 else None
        # 最近的前一个 getter
        prev = [(j, n) for j, n in getters if j < i]
        gname = prev[-1][1] if prev else "?"
        seq.append((gname, fld, wt))
    full = " ".join(n for n, _, _ in seq)
    if KW and not all(k in full.lower() for k in KW):
        continue
    print("rva=0x%-7x" % r.Rva)
    for g, f, w in seq:
        print("    %-30s field=%-3s wire=%s" % (g, f, w))
