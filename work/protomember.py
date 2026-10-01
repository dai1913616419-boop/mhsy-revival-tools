#!/usr/bin/env python3
"""正确解析 ProtoMember CustomAttribute blob。
ECMA-335 CustomAttrib: 0100 | ctor FixedArgs | u16 num_named | named*
named ::= FIELD(0x53)/PROPERTY(0x54) SerString name FieldOrPropType value
FieldOrPropType 0x55=enum -> SerString typedef name then int32 value
DataFormat (protobuf-net): 0=Default 1=ZigZag 2=TwosComplement 3=FixedSize 4=Group
用法: protomember.py <dll> <TypeFullName>
"""
import sys, struct
import dnfile

DF = {0: "Default(varint)", 1: "ZigZag", 2: "TwosComplement(varint)",
      3: "FixedSize(fixed32)", 4: "Group"}
ET = {0x02: "bool", 0x03: "char", 0x04: "i1", 0x05: "u1", 0x06: "i2", 0x07: "u2",
      0x08: "i4", 0x09: "u4", 0x0a: "i8", 0x0b: "u8", 0x0c: "r4", 0x0d: "r8",
      0x0e: "string", 0x50: "type", 0x51: "object"}

def read_compressed(b, i):
    x = b[i]
    if x & 0x80 == 0:
        return x, i + 1
    if x & 0xC0 == 0x80:
        return ((x & 0x3F) << 8) | b[i+1], i + 2
    return ((x & 0x1F) << 24) | (b[i+1] << 16) | (b[i+2] << 8) | b[i+3], i + 4

def read_serstring(b, i):
    n = b[i]
    if n == 0xFF:
        return None, i + 1
    n, i = read_compressed(b, i)
    return b[i:i+n].decode("utf-8", "replace"), i + n

def parse_blob(b):
    assert b[0] == 1 and b[1] == 0, "bad prolog"
    i = 2
    tag = struct.unpack_from("<i", b, i)[0]; i += 4
    num = struct.unpack_from("<H", b, i)[0]; i += 2
    named = {}
    for _ in range(num):
        kind = b[i]; i += 1
        name, i = read_serstring(b, i)
        ftype = b[i]
        if ftype == 0x55:      # enum
            i += 1
            tn, i = read_serstring(b, i)
            val = struct.unpack_from("<i", b, i)[0]; i += 4
            named[name] = ("enum:" + (tn or "").split(",")[0], val)
        elif ftype in (0x51, 0x50):  # object/array
            named[name] = ("obj", None)
        elif ftype == 0x0e:
            s, i = read_serstring(b, i)
            named[name] = ("string", s)
        else:
            sz = {0x02:1,0x03:2,0x04:1,0x05:1,0x06:2,0x07:2,0x08:4,0x09:4,0x0a:8,0x0b:8,0x0c:4,0x0d:8}.get(ftype,0)
            val = b[i:i+sz]; i += sz
            named[name] = (ET.get(ftype, hex(ftype)), val.hex())
    return tag, named

def main():
    dll, target = sys.argv[1], sys.argv[2]
    pe = dnfile.dnPE(dll); mdt = pe.net.mdtables
    trow = None
    for t in mdt.TypeDef.rows:
        if (t.TypeNamespace.value or '') + '.' + (t.TypeName.value or '') == target:
            trow = t; break
    if trow is None:
        print("type not found"); return
    props = {}
    for pm in mdt.PropertyMap.rows:
        if pm.Parent.row is not trow:
            continue
        for p in (pm.PropertyList or []):
            props[id(p.row)] = str(p.row.Name)
    rows = []
    for r in mdt.CustomAttribute.rows:
        par = r.Parent
        if par.table is None or getattr(par.table, 'name', '') != 'Property':
            continue
        nm = props.get(id(par.row))
        if nm is None:
            continue
        try:
            cls = r.Type.row.Class.row
            tn = (cls.TypeNamespace.value or '') + '.' + (cls.TypeName.value or '')
        except Exception:
            continue
        if 'ProtoMember' not in tn:
            continue
        b = bytes(r.Value.value)
        try:
            tag, named = parse_blob(b)
        except Exception as e:
            rows.append((nm, None, "ERR " + str(e)))
            continue
        df = named.get("DataFormat")
        dfv = df[1] if df else 0
        rows.append((nm, tag, "df=%s(%s) req=%s" % (
            dfv, DF.get(dfv, "?"),
            named.get("IsRequired", ("", ""))[1] if "IsRequired" in named else "-")))
    rows.sort(key=lambda x: (x[1] if x[1] is not None else -1))
    for nm, tag, extra in rows:
        print("  tag=%-5s %-34s %s" % (tag, nm, extra))

if __name__ == "__main__":
    main()
