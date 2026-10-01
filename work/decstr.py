"""还原 Client.dll 中被 b(string, int) 混淆的字符串。

算法（反汇编 b @0x25757c 得出）：
    k = 1432267889 + key            (int32 溢出回绕)
    for i in range(len(chars)):
        lo = (chars[i] & 0xFF) ^ (k & 0xFF); k += 1
        hi = (chars[i] >> 8) ^ (k & 0xFF); k += 1
        chars[i] = ((hi & 0xFF) << 8) | lo

用法: decstr.py <dll> <rva1> [rva2 ...]   # 反汇编这些方法并解码其中的混淆字符串
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dnfile
from dncil.cil.body import CilMethodBody
from dncil.clr.token import Token, StringToken
from usheap import parse_us
from disasm3 import Reader, build


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


def main():
    path = sys.argv[1]
    rvas = [int(x, 0) for x in sys.argv[2:]]
    pe = dnfile.dnPE(path)
    us = parse_us(pe.net.user_strings.__data__)
    mdt = pe.net.mdtables

    # 找到 b 的 MethodDef token（名字为 'b' 且有两个参数的那种，直接按名字取）
    b_rids = set()
    for i, r in enumerate(mdt.MethodDef.rows, 1):
        if str(r.Name) == "b":
            b_rids.add(0x06000000 | i)

    for rva in rvas:
        print("=== RVA 0x%x ===" % rva)
        body = CilMethodBody(Reader(pe, rva))
        ins = body.instructions
        # 局部变量赋值表: stloc idx -> 最近一次 ldc 的常量
        locals_const = {}
        i = 0
        while i < len(ins):
            op = ins[i]
            name = op.opcode.name
            if name.startswith("ldc.i4") and isinstance(op.operand, int):
                val = op.operand
                # 向后看是否 stloc
                if i + 1 < len(ins) and ins[i + 1].opcode.name.startswith("stloc"):
                    tgt = ins[i + 1].operand
                    key = getattr(tgt, "index", None)
                    if key is None:
                        key = str(tgt)
                    locals_const[key] = val
            if name == "ldstr" and isinstance(op.operand, StringToken):
                raw = us.get(op.operand.rid, "")
                # 找下一个 call 且是 b
                if i + 2 < len(ins) and ins[i + 2].opcode.name == "call" \
                        and isinstance(ins[i + 2].operand, Token) \
                        and ins[i + 2].operand.value in b_rids:
                    mid = ins[i + 1]
                    key = None
                    if isinstance(mid.operand, int):
                        key = mid.operand
                    elif mid.opcode.name.startswith("ldloc") or mid.opcode.name == "ldloc.s":
                        t = mid.operand
                        key = locals_const.get(getattr(t, "index", str(t)))
                    if key is not None:
                        print("  [%s] %r" % (key, b_decode(raw, key)))
                        i += 3
                        continue
                    print("  [?key] raw=%r" % raw[:40])
            i += 1


main()
