"""根据 handler 方法 RVA/名称，反查它注册的消息号。

用法: python find_msgid_of_handler.py <dll> <rva或方法名> [更多...]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dnfile
from dncil.cil.body import CilMethodBody
from dncil.clr.token import Token
from disasm3 import Reader

DLL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "apk", "Client_4201.dll")
targets = sys.argv[1:]

pe = dnfile.dnPE(DLL)
mdt = pe.net.mdtables

# 目标 -> MethodDef rid
def resolve(t):
    out = {}
    if t.startswith("0x"):
        rva = int(t, 16)
        for i, r in enumerate(mdt.MethodDef.rows, 1):
            if r.Rva == rva:
                out[i] = (str(r.Name), rva)
        return out
    for i, r in enumerate(mdt.MethodDef.rows, 1):
        if str(r.Name) == t and r.Rva:
            out.setdefault(i, (str(r.Name), r.Rva))
    return out

target_rids = {}
for t in targets:
    target_rids.update(resolve(t))
print("目标 handler:", {k: v for k, v in target_rids.items()})

# 扫描所有方法，找 ldftn <target> 附近 8 条内的 ldc.i4
hits = []
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
        for i, op in enumerate(ins):
            if op.opcode.name != "ldftn":
                continue
            if not isinstance(op.operand, Token):
                continue
            rid = op.operand.value & 0xFFFFFF
            if rid not in target_rids:
                continue
            # 前后 10 条内的 ldc.i4
            consts = []
            for j in range(max(0, i - 10), min(len(ins), i + 10)):
                o = ins[j]
                if o.opcode.name in ("ldc.i4", "ldc.i4.s") and isinstance(o.operand, int):
                    consts.append((j - i, o.operand))
            hits.append({
                "handler": target_rids[rid],
                "reg_in": "%s::%s" % (tn, str(r.Name)),
                "reg_rva": hex(r.Rva),
                "consts": consts,
            })

for h in hits:
    print("\nhandler=%s (%s)" % (h["handler"][0], hex(h["handler"][1])))
    print("  注册处: %s  rva=%s" % (h["reg_in"], h["reg_rva"]))
    print("  附近常数(相对偏移, 值): %s" % h["consts"])
