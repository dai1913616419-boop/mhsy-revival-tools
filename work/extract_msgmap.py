"""提取消息号 <-> NetProto 类型 映射表。

原理：
  1. 找到所有调用 RegisterMessageDelegate 的方法（注册表），
     提取 (msgid, handler方法) 对 —— IL 模式:
         ldc.i4 <id>; ...; ldftn <handler>; newobj; callvirt RegisterMessageDelegate
  2. 对每个 handler，找其中的 MethodSpec（DeserializeProtobuf<T>），
     解析泛型参数得到 NetProto 类型名。

输出: output/09_消息号映射.json / .md
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dnfile
from dncil.cil.body import CilMethodBody
from dncil.clr.token import Token
from disasm3 import Reader

DLL = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "apk", "Client_4201.dll")

pe = dnfile.dnPE(DLL)
mdt = pe.net.mdtables

# RegisterMessageDelegate 的 MethodDef token
reg_rid = None
for i, r in enumerate(mdt.MethodDef.rows, 1):
    if str(r.Name) == "RegisterMessageDelegate":
        reg_rid = i
        break
REG_TOKEN = 0x06000000 | reg_rid


def typename_from_methodspec(tok):
    """MethodSpec token -> 泛型参数类型名。"""
    tb = (tok >> 24) & 0xFF
    rid = tok & 0xFFFFFF
    if tb != 0x2B:
        return None
    inst = mdt.MethodSpec.rows[rid - 1].Instantiation
    b = inst.value
    i = 1 if b[0] == 0x0A else 0
    try:
        count = b[i]              # GenArgCount
        ts = b[i + 1]             # 第一个类型签名
    except IndexError:
        return None
    code = ts if ts in (0x11, 0x12, 0x1B) else None
    if code is None:
        return None
    rest = b[i + 2:]
    if not rest:
        return None
    v = rest[0]
    if v & 0x80:
        if len(rest) < 2:
            return None
        v = ((v & 0x7F) << 8) | rest[1]
    table = v & 3
    row = v >> 2
    try:
        if table == 1:
            tr = mdt.TypeRef.rows[row - 1]
            return "%s.%s" % (tr.TypeNamespace.value or "", tr.TypeName.value)
        if table == 0:
            td = mdt.TypeDef.rows[row - 1]
            return "%s.%s" % (td.TypeNamespace.value or "", td.TypeName.value)
    except Exception:
        return None
    return "TypeSpec%d" % row


def owner_of_methoddef(rid):
    for t in mdt.TypeDef.rows:
        for m in (t.MethodList or []):
            r = m.row
            if getattr(r, "row_index", None) == rid or r is mdt.MethodDef.rows[rid - 1]:
                return "%s.%s" % (t.TypeNamespace.value or "", t.TypeName.value)
    return "?"


# 1) 收集 (msgid, handler_rid)
pairs = []
seen_methods = 0
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
        seen_methods += 1
        i = 0
        while i < len(ins):
            op = ins[i]
            if op.opcode.name in ("ldc.i4", "ldc.i4.s") and isinstance(op.operand, int):
                # 向后找 8 条内是否有 RegisterMessageDelegate 且中间有 ldftn
                window = ins[i:i + 8]
                ids = [x.opcode.name for x in window]
                if "ldftn" in ids and any(
                        x.opcode.name == "callvirt" and isinstance(x.operand, Token)
                        and x.operand.value == REG_TOKEN for x in window):
                    msgid = op.operand
                    h = None
                    for x in window:
                        if x.opcode.name == "ldftn" and isinstance(x.operand, Token):
                            h = x.operand.value & 0xFFFFFF
                            break
                    if h:
                        pairs.append((msgid, h, r.Rva, tn))
                        i += 8
                        continue
            i += 1

print("扫描方法 %d 个，注册对 %d 个" % (seen_methods, len(pairs)))

# 2) 每个 handler 找 DeserializeProtobuf 泛型
mapping = []
for msgid, hrid, from_rva, tn in pairs:
    r = mdt.MethodDef.rows[hrid - 1]
    handler_name = str(r.Name)
    handler_owner = owner_of_methoddef(hrid)
    mtype = None
    try:
        body = CilMethodBody(Reader(pe, r.Rva))
    except Exception:
        body = None
    if body:
        cands = []
        for ins in body.instructions:
            if ins.opcode.name == "call" and isinstance(ins.operand, Token):
                t2 = typename_from_methodspec(ins.operand.value)
                if t2:
                    cands.append(t2)
        for t2 in cands:
            if t2.startswith("NetProto."):
                mtype = t2
                break
        if not mtype and cands:
            mtype = cands[0]
    mapping.append({"msgid": msgid, "handler": "%s::%s" % (handler_owner, handler_name),
                    "type": mtype, "reg_from": tn})

mapping.sort(key=lambda x: x["msgid"])
for m in mapping:
    print("%5d  %-55s %s" % (m["msgid"], m["type"] or "?", m["handler"]))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output", "09_消息号映射.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(mapping, f, ensure_ascii=False, indent=1)
print("已写出", out)
