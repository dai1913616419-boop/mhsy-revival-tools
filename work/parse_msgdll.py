#!/usr/bin/env python3
"""
从 Msg.dll 中提取 protobuf-net 消息契约。
纯 Python（dnfile），无需 Java / ILSpy / dnSpy。

输出：
  work/messages.json   机器可读，供后续生成 .proto / Python 服务端
  打印摘要到 stdout
用法：
  python parse_msgdll.py <dll路径> [输出json路径]
"""
import sys, os, json, struct, collections, re

import dnfile
from dnfile.mdtable import (
    TypeDefRow, TypeRefRow, FieldRow, PropertyRow, MethodDefRow, TypeSpecRow
)

# ---------- 字段签名解析（ECMA-335 II.23.2.4 FieldSig） ----------
ET = {
    0x02: "bool", 0x03: "char", 0x04: "int8", 0x05: "uint8",
    0x06: "int16", 0x07: "uint16", 0x08: "int32", 0x09: "uint32",
    0x0A: "int64", 0x0B: "uint64", 0x0C: "float", 0x0D: "double",
    0x0E: "string", 0x0F: "ptr", 0x16: "typedref", 0x18: "IntPtr",
    0x19: "UIntPtr", 0x1C: "object", 0x11: "valuetype", 0x12: "class",
    0x15: "genericinst", 0x1D: "szarray", 0x14: "array", 0x0D: "double",
}


class BlobReader:
    def __init__(self, b):
        self.b = b
        self.i = 0

    def u8(self):
        v = self.b[self.i]; self.i += 1; return v

    def compressed_uint(self):
        """ECMA-335 II.23.2 compressed unsigned integer"""
        b0 = self.u8()
        if b0 & 0x80 == 0:
            return b0
        if b0 & 0xC0 == 0x80:
            return ((b0 & 0x3F) << 8) | self.u8()
        if b0 & 0xE0 == 0xC0:
            hi = ((b0 & 0x1F) << 24) | (self.u8() << 16) | (self.u8() << 8) | self.u8()
            return hi
        raise ValueError("bad compressed uint at %d" % self.i)

    def typedef_or_ref(self):
        """TypeDefOrRef coded index (2 bits tag): 0=TypeDef 1=TypeRef 2=TypeSpec
        返回 (0-based 行索引, tag) —— coded index 的 rid 是 1-based，需 -1"""
        v = self.compressed_uint()
        return (v >> 2) - 1, v & 3


def resolve_type_name(pe, ridx, tag):
    tbl = {0: "TypeDef", 1: "TypeRef", 2: "TypeSpec"}.get(tag)
    try:
        if tbl == "TypeDef":
            r = pe.net.mdtables.TypeDef.rows[ridx]
            return str(r.TypeName)
        if tbl == "TypeRef":
            r = pe.net.mdtables.TypeRef.rows[ridx]
            return str(r.TypeName)
    except Exception:
        pass
    return "?"


def parse_type(pe, br):
    """解析一个 ELEMENT_TYPE，返回可读类型名"""
    e = br.u8()
    if e in (0x1D,):  # SZARRAY
        return parse_type(pe, br) + "[]"
    if e == 0x15:  # GENERICINST
        br.u8()  # 0x12 class 或 0x11 valuetype
        ridx, tag = br.typedef_or_ref()
        base = resolve_type_name(pe, ridx, tag)
        cnt = br.compressed_uint()
        args = [parse_type(pe, br) for _ in range(cnt)]
        return f"{base}<{','.join(args)}>"
    if e in (0x11, 0x12):  # VALUETYPE / CLASS
        ridx, tag = br.typedef_or_ref()
        return resolve_type_name(pe, ridx, tag)
    if e == 0x14:  # ARRAY
        t = parse_type(pe, br)
        rank = br.compressed_uint()
        return t + "[]"
    if e == 0x1F or e == 0x21:  # VAR / MVAR (泛型参数)
        br.compressed_uint()
        return "T"
    return ET.get(e, "0x%02x" % e)


def field_type(pe, sig_blob):
    try:
        b = bytes(sig_blob)
        br = BlobReader(b)
        br.u8()  # calling convention 0x06 FIELD
        return parse_type(pe, br)
    except Exception:
        return "?"


# ---------- 特性解析 ----------
def attr_full_name(row):
    """CustomAttribute.Type -> (命名空间.特性名, 构造函数所在类型名)"""
    t = row.Type.row
    if isinstance(t, dnfile.mdtable.MemberRefRow):
        cls = t.Class.row
        if isinstance(cls, TypeRefRow):
            return f"{cls.TypeNamespace}.{cls.TypeName}"
        if isinstance(cls, TypeSpecRow):
            return "TypeSpec"
    elif isinstance(t, MethodDefRow):
        return "MethodDef"
    return "?"


def proto_member_tag(row):
    """ProtoMember(n) -> n"""
    b = bytes(row.Value.value)
    if len(b) >= 6 and b[0] == 0x01 and b[1] == 0x00:
        return struct.unpack_from("<i", b, 2)[0]
    return None


def property_type(pe, sig_blob):
    """PropertySig: 0x08 prolog, uint32 ParamCount, Type, Param*"""
    try:
        b = bytes(sig_blob.value) if hasattr(sig_blob, "value") else bytes(sig_blob)
        br = BlobReader(b)
        prolog = br.u8()          # 0x08 (static) 或 0x28 (0x08 | HASTHIS 实例属性)
        count = br.compressed_uint()  # ParamCount
        return parse_type(pe, br)
    except Exception:
        return "?"


def name_of(parent_row):
    try:
        return str(parent_row.Name)
    except Exception:
        return "?"


def main(dll, outjson):
    pe = dnfile.dnPE(dll)
    n = pe.net
    asm = n.mdtables.Assembly.rows[0]
    print(f"[*] 程序集: {asm.Name} {asm.MajorVersion}.{asm.MinorVersion}.{asm.BuildNumber}.{asm.RevisionNumber}")
    print(f"[*] TypeDef: {len(n.mdtables.TypeDef.rows)}  CustomAttribute: {len(n.mdtables.CustomAttribute.rows)}")

    # 索引 TypeDef -> 字段列表（TypeDef 的 FieldList 是连续区间）
    fields = n.mdtables.Field.rows
    tdefs = n.mdtables.TypeDef.rows
    props = n.mdtables.Property.rows

    # 建立 rid -> owner TypeDef 的映射（用 FieldList 区间推算）
    # dnfile 已把 FieldList 解析为 FieldRow 列表，直接建 id -> owner 映射
    field_owner = {}
    for t in tdefs:
        for f in (t.FieldList or []):
            field_owner[id(f)] = t

    # PropertyMap: Parent -> TypeDef, PropertyList -> [Property]
    prop_owner = {}
    for pm in n.mdtables.PropertyMap.rows:
        owner = pm.Parent.row
        for p in (pm.PropertyList or []):
            prop_owner[id(p.row if hasattr(p, "row") else p)] = owner

    # 扫描 CustomAttribute
    contracts = collections.OrderedDict()   # TypeName -> {ns, fields:[{name,type,tag}]}
    for row in n.mdtables.CustomAttribute.rows:
        an = attr_full_name(row)
        if an == "ProtoBuf.ProtoContractAttribute":
            p = row.Parent.row
            if isinstance(p, TypeDefRow):
                key = f"{p.TypeNamespace}.{p.TypeName}" if p.TypeNamespace else str(p.TypeName)
                contracts.setdefault(key, {"ns": str(p.TypeNamespace or ""), "name": str(p.TypeName), "fields": []})
        elif an == "ProtoBuf.ProtoMemberAttribute":
            tag = proto_member_tag(row)
            p = row.Parent.row
            if isinstance(p, FieldRow):
                owner = field_owner.get(id(p))
                if owner is None:
                    continue
                key = f"{owner.TypeNamespace}.{owner.TypeName}" if owner.TypeNamespace else str(owner.TypeName)
                c = contracts.setdefault(key, {"ns": str(owner.TypeNamespace or ""), "name": str(owner.TypeName), "fields": []})
                fn = name_of(p)
                if fn.startswith("<") and fn.endswith(">k__BackingField"):
                    fn = fn[1:-len(">k__BackingField")]
                c["fields"].append({"name": fn, "type": field_type(pe, p.Signature), "tag": tag})
            elif isinstance(p, PropertyRow):
                owner = prop_owner.get(id(p))
                if owner is None:
                    continue
                key = f"{owner.TypeNamespace}.{owner.TypeName}" if owner.TypeNamespace else str(owner.TypeName)
                c = contracts.setdefault(key, {"ns": str(owner.TypeNamespace or ""), "name": str(owner.TypeName), "fields": []})
                c["fields"].append({"name": name_of(p), "type": property_type(pe, p.Type), "tag": tag})

    # 按 tag 排序字段
    for k, c in contracts.items():
        if k == "__props__":
            continue
        c["fields"].sort(key=lambda f: (f["tag"] is None, f["tag"]))

    msgs = {k: v for k, v in contracts.items() if k != "__props__" and v["fields"]}
    print(f"\n[+] 带 [ProtoContract] 且有 ProtoMember 的消息类型: {len(msgs)}")

    # 去重：同一类型名只保留字段最全的
    json.dump({"assembly": str(asm.Name), "messages": msgs},
              open(outjson, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[+] 已写入 {outjson}")

    # 摘要
    total = sum(len(v["fields"]) for v in msgs.values())
    print(f"[+] 字段总数: {total}")
    print("\n=== 消息清单（前 40，按名排序）===")
    for k in sorted(msgs)[:40]:
        fs = msgs[k]["fields"]
        print(f"  {msgs[k]['name']:<42} {len(fs):>3} 字段")
    return msgs


if __name__ == "__main__":
    dll = sys.argv[1] if len(sys.argv) > 1 else "carved/CAB-Protobuf_00002231.dll"
    out = sys.argv[2] if len(sys.argv) > 2 else "messages.json"
    main(dll, out)
