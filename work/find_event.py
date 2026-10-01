"""扫描所有方法，找出引用指定事件号常量的方法及其上下文调用。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dnfile
from dncil.cil.body import CilMethodBody
from dncil.clr.token import Token
from disasm3 import Reader

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, "apk", "Client_4201.dll")

IDS = set(int(x) for x in sys.argv[1:]) if len(sys.argv) > 1 else {653, 654, 656}

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


def opcode_const(op):
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


for t in mdt.TypeDef.rows:
    tn = "%s.%s" % (t.TypeNamespace.value or "", t.TypeName.value)
    for m in (t.MethodList or []):
        r = m.row
        if not r.Rva:
            continue
        try:
            body = CilMethodBody(Reader(pe, r.Rva))
        except Exception:
            continue
        ins = body.instructions
        hits = []
        for i, op in enumerate(ins):
            v = opcode_const(op)
            if v in IDS:
                ctx = [refname(x.operand.value) for x in ins[i + 1:i + 5]
                       if x.opcode.name in ("call", "callvirt")
                       and isinstance(x.operand, Token)]
                hits.append((i, v, ctx))
        if hits:
            print("%s::%s rva=0x%x" % (tn, str(r.Name), r.Rva))
            for i, v, ctx in hits:
                print("    IL#%d 值=%d 后续调用=%s" % (i, v, ctx))
