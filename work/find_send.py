"""扫描所有 MethodSpec 泛型调用点，还原 msgid <-> NetProto 类型 的双向映射。

思路：
  1. 先建 MethodSpec rid -> 泛型参数类型名 的表（只看 NetProto.* ）
  2. 遍历所有方法体，遇到 call/callvirt 且操作数是 MethodSpec(0x2B) 时：
     - 记录被调用方法名 + 泛型类型名 + 调用点所属方法
     - 回溯 12 条指令内的 ldc.i4 常数（作为候选 msgid）
  3. 同时回溯 4 条内是否有 ldstr（便于识别）
输出全部结果，供人工/脚本筛选。
"""
import json
import os
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


def compressed_uint(b, i):
    """读压缩整数，返回 (值, 新位置)。"""
    if i >= len(b):
        return None, i
    v = b[i]
    if v & 0x80 == 0:
        return v, i + 1
    if v & 0xC0 == 0x80:
        if i + 1 >= len(b):
            return None, i + 1
        return ((v & 0x3F) << 8) | b[i + 1], i + 2
    if v & 0xE0 == 0xC0:
        if i + 3 >= len(b):
            return None, i + 4
        return ((v & 0x1F) << 24) | (b[i + 1] << 16) | (b[i + 2] << 8) | b[i + 3], i + 4
    return None, i + 1


def type_from_sig(b, i):
    """从签名 b[i:] 解析一个类型，返回 (类型名, 新位置)。"""
    if i >= len(b):
        return None, i
    e = b[i]
    if e in (0x11, 0x12, 0x1B):       # ELEMENT_TYPE_CLASS / VALUETYPE / ...
        v, j = compressed_uint(b, i + 1)
        if v is None:
            return None, i + 1
        table = v & 3
        row = v >> 2
        name = None
        try:
            if table == 0:
                td = mdt.TypeDef.rows[row - 1]
                name = "%s.%s" % (td.TypeNamespace.value or "", td.TypeName.value)
            elif table == 1:
                tr = mdt.TypeRef.rows[row - 1]
                name = "%s.%s" % (tr.TypeNamespace.value or "", tr.TypeName.value)
            elif table == 2:
                name = "TypeSpec:%d" % row
        except Exception:
            name = None
        return name, j
    if e == 0x15:                      # GENERICINST
        _, j = compressed_uint(b, i + 1)   # 跳过基础类型
        cnt, j = compressed_uint(b, j)
        args = []
        for _ in range(cnt or 0):
            n, j = type_from_sig(b, j)
            args.append(n)
        return "GEN<%s>" % ",".join(str(a) for a in args), j
    if e in (0x1D, 0x1E):              # SZARRAY / ARRAY
        n, j = type_from_sig(b, i + 1)
        return "%s[]" % n, j
    # 基本类型
    prim = {0x02: "bool", 0x03: "char", 0x04: "sbyte", 0x05: "byte", 0x06: "short",
            0x07: "ushort", 0x08: "int", 0x09: "uint", 0x0A: "long", 0x0B: "ulong",
            0x0C: "float", 0x0D: "double", 0x0E: "string", 0x16: "object",
            0x0F: "ptr", 0x10: "byref", 0x18: "IntPtr", 0x19: "UIntPtr"}
    return prim.get(e, "E%02X" % e), i + 1


def methodspec_types(tok):
    tb = (tok >> 24) & 0xFF
    rid = tok & 0xFFFFFF
    if tb != 0x2B:
        return []
    try:
        inst = mdt.MethodSpec.rows[rid - 1].Instantiation
    except Exception:
        return []
    b = inst.value
    if not b:
        return []
    i = 0
    if b[0] == 0x0A:                   # GENERIC
        i = 1
    cnt, i = compressed_uint(b, i)
    out = []
    for _ in range(cnt or 0):
        n, i = type_from_sig(b, i)
        out.append(n)
    return out


def method_name(tok):
    tb = (tok >> 24) & 0xFF
    rid = tok & 0xFFFFFF
    try:
        if tb == 0x06:
            return str(mdt.MethodDef.rows[rid - 1].Name)
        if tb == 0x0A:
            return str(mdt.MemberRef.rows[rid - 1].Name)
    except Exception:
        pass
    return "?"


# 建 owner 表：MethodDef rid -> 类名
owner = {}
for t in mdt.TypeDef.rows:
    tn = "%s.%s" % (t.TypeNamespace.value or "", t.TypeName.value)
    for m in (t.MethodList or []):
        try:
            owner[m.row.row_index] = tn
        except Exception:
            pass

rows = []
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
        for idx, op in enumerate(ins):
            if op.opcode.name not in ("call", "callvirt", "newobj", "ldftn"):
                continue
            if not isinstance(op.operand, Token):
                continue
            tks = methodspec_types(op.operand.value)
            if not tks:
                continue
            net = [x for x in tks if x and x.startswith("NetProto.")]
            if not net:
                continue
            # 回溯常数
            consts = []
            for j in range(max(0, idx - 12), idx):
                o = ins[j]
                if o.opcode.name in ("ldc.i4", "ldc.i4.s") and isinstance(o.operand, int):
                    consts.append(o.operand)
            rows.append({
                "owner": tn,
                "method": str(r.Name),
                "rva": hex(r.Rva),
                "call": method_name(op.operand.value),
                "types": tks,
                "net": net,
                "consts": consts,
            })

print("命中 %d 个 NetProto 泛型调用点" % len(rows))

# 按 NetProto 类型聚合，输出 (类型, 候选msgid集合, 调用方法)
agg = {}
for r in rows:
    for n in r["net"]:
        agg.setdefault(n, {"consts": set(), "sites": []})
        agg[n]["consts"].update(r["consts"])
        agg[n]["sites"].append("%s::%s -> %s" % (r["owner"], r["method"], r["call"]))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output",
                   "09b_泛型调用点.json")
json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("已写出", out)

for n in sorted(agg):
    cs = sorted(agg[n]["consts"])
    print("%-52s msgid候选=%s  调用点=%s" % (
        n, cs[:10], agg[n]["sites"][0]))
