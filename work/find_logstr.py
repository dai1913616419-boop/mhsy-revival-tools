"""扫描所有方法，解码 b(str,key) 混淆字符串，找出包含目标文本的方法。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dnfile
from dncil.cil.body import CilMethodBody
from dncil.clr.token import Token, StringToken
from usheap import parse_us
from disasm3 import Reader

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(HERE, "apk", "Client_4201.dll")

TARGETS = sys.argv[1:] or ["received one message", "connection had a error"]

pe = dnfile.dnPE(DLL)
us = parse_us(pe.net.user_strings.__data__)
mdt = pe.net.mdtables

b_rids = set()
for i, r in enumerate(mdt.MethodDef.rows, 1):
    if str(r.Name) == "b":
        b_rids.add(0x06000000 | i)


def b_decode(s, key):
    k = (1432267889 + key) & 0xFFFFFFFF
    out = []
    for ch in s:
        c = ord(ch)
        lo = (c & 0xFF) ^ (k & 0xFF)
        k = (k + 1) & 0xFFFFFFFF
        hi = ((c >> 8) & 0xFF) ^ (k & 0xFF)
        k = (k + 1) & 0xFFFFFFFF
        out.append(chr(((lo & 0xFF) << 8) | (hi & 0xFF)))
    return "".join(out)


def owner_of(rid):
    for t in mdt.TypeDef.rows:
        tn = "%s.%s" % (t.TypeNamespace.value or "", t.TypeName.value)
        for m in (t.MethodList or []):
            if m.row.row_index == rid:
                return "%s::%s" % (tn, str(m.row.Name))
    return "?"


found = 0
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
        locals_const = {}
        i = 0
        while i < len(ins):
            op = ins[i]
            name = op.opcode.name
            if name.startswith("ldc.i4") and isinstance(op.operand, int) \
                    and i + 1 < len(ins) and ins[i + 1].opcode.name.startswith("stloc"):
                tgt = ins[i + 1].operand
                locals_const[getattr(tgt, "index", str(tgt))] = op.operand
            if name == "ldstr" and isinstance(op.operand, StringToken) \
                    and i + 2 < len(ins) and ins[i + 2].opcode.name == "call" \
                    and isinstance(ins[i + 2].operand, Token) \
                    and ins[i + 2].operand.value in b_rids:
                raw = us.get(op.operand.rid, "")
                mid = ins[i + 1]
                key = None
                if isinstance(mid.operand, int):
                    key = mid.operand
                elif mid.opcode.name.startswith("ldloc"):
                    tt = mid.operand
                    key = locals_const.get(getattr(tt, "index", str(tt)))
                if key is not None:
                    s = b_decode(raw, key)
                    if any(x in s for x in TARGETS):
                        print("命中: %s  rva=0x%x  key=%s  %r"
                              % (tn, r.Rva, key, s))
                        found += 1
                i += 3
                continue
            i += 1
print("共命中 %d" % found)
