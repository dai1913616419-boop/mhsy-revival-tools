#!/usr/bin/env python3
"""从正确的 Msg 程序集提取完整 protobuf 契约（含正确的 tag 与 DataFormat）。
用法: extract_contract.py <Msg.dll> [out.json]
DataFormat(protobuf-net): 0=Default(varint) 1=ZigZag 2=TwosComplement(varint)
                         3=FixedSize(fixed32) 4=Group
"""
import sys, json, struct
import dnfile

DFNAME = {0: "varint", 1: "zigzag", 2: "varint", 3: "fixed32", 4: "group"}
ET = {0x02: "bool", 0x03: "char", 0x04: "i1", 0x05: "u1", 0x06: "i2", 0x07: "u2",
      0x08: "int32", 0x09: "uint32", 0x0a: "int64", 0x0b: "uint64", 0x0c: "float",
      0x0d: "double", 0x0e: "string", 0x11: "value", 0x12: "class"}


def read_compressed(b, i):
    x = b[i]
    if x & 0x80 == 0:
        return x, i + 1
    if x & 0xC0 == 0x80:
        return ((x & 0x3F) << 8) | b[i + 1], i + 2
    return ((x & 0x1F) << 24) | (b[i + 1] << 16) | (b[i + 2] << 8) | b[i + 3], i + 4


def read_serstring(b, i):
    n = b[i]
    if n == 0xFF:
        return None, i + 1
    n, i = read_compressed(b, i)
    return b[i:i + n].decode("utf-8", "replace"), i + n


def parse_protomember(blob):
    """-> (tag, {named_args})
    实测布局（.NET 编译器输出）：每个 named arg =
        <0x53 Field | 0x54 Property> <FieldOrPropType> <SerString name> <value>
    FieldOrPropType: 0x02=bool 0x0e=string 0x55=enum(后接 SerString 类型全名)
    """
    b = blob
    if b[0] != 1 or b[1] != 0:
        return None, {}
    i = 2
    tag = struct.unpack_from("<i", b, i)[0]; i += 4
    num = struct.unpack_from("<H", b, i)[0]; i += 2
    named = {}
    for _ in range(num):
        if i + 2 > len(b):
            break
        kind = b[i]; i += 1          # 0x53/0x54
        ft = b[i]; i += 1            # FieldOrPropType
        if ft == 0x55:
            _tn, i = read_serstring(b, i)     # 类型全名（Protobuf.DataFormat,...）
            name, i = read_serstring(b, i)
            named[name] = struct.unpack_from("<i", b, i)[0]; i += 4
        elif ft == 0x0e:
            name, i = read_serstring(b, i)
            named[name], i = read_serstring(b, i)
        else:
            name, i = read_serstring(b, i)
            sz = {0x02: 1, 0x03: 2, 0x04: 1, 0x05: 1, 0x06: 2, 0x07: 2,
                  0x08: 4, 0x09: 4, 0x0a: 8, 0x0b: 8, 0x0c: 4, 0x0d: 8}.get(ft, 0)
            named[name] = b[i:i + sz].hex(); i += sz
    return tag, named


def decode_sig(sig, mdt):
    if len(sig) < 2:
        return "?"
    # PropertySig 首字节 0x28(HASTHIS|PROPERTY) 或 0x08；FieldSig 0x06
    if sig[0] in (0x28, 0x08, 0x08 | 0x20):
        i = 2                      # 跳过 首字节 + param_count
    else:
        i = 1
    if i >= len(sig):
        return "?"
    et = sig[i]
    if et == 0x1D:
        return "list:" + decode_sig(b'\x08\x00' + sig[i + 1:], mdt)
    if et in (0x11, 0x12):
        coded = sig[i + 1] >> 2
        tbl, rid = ("TypeDef" if (coded & 3) == 0 else
                    "TypeRef" if (coded & 3) == 1 else "TypeSpec"), coded >> 2
        try:
            if tbl == "TypeDef":
                r = mdt.TypeDef.rows[rid - 1]
            elif tbl == "TypeRef":
                r = mdt.TypeRef.rows[rid - 1]
            else:
                return "spec"
            return (r.TypeNamespace.value or '') + '.' + (r.TypeName.value or '')
        except Exception:
            return "?"
    if et == 0x15:   # GENERICINST
        return "list:" + decode_sig(b'\x08\x00' + sig[i + 1:], mdt)
    return ET.get(et, "raw:%s" % sig.hex())


def main():
    dll = sys.argv[1]
    outp = sys.argv[2] if len(sys.argv) > 2 else "messages_full.json"
    pe = dnfile.dnPE(dll)
    mdt = pe.net.mdtables

    # Property rid -> (tag, dataFormat)  (用 PropertyMap 的 PropertyList 顺序无关)
    prop_meta = {}
    prop_name = {}
    for pm in mdt.PropertyMap.rows:
        for p in (pm.PropertyList or []):
            prop_name[id(p.row)] = str(p.row.Name)
    for r in mdt.CustomAttribute.rows:
        par = r.Parent
        if par.table is None or getattr(par.table, 'name', '') != 'Property':
            continue
        if id(par.row) not in prop_name:
            continue
        try:
            cls = r.Type.row.Class.row
            tn = (cls.TypeNamespace.value or '') + '.' + (cls.TypeName.value or '')
        except Exception:
            continue
        if 'ProtoMember' not in tn:
            continue
        try:
            tag, named = parse_protomember(bytes(r.Value.value))
        except Exception:
            continue
        if tag is None:
            continue
        prop_meta[id(par.row)] = (tag, named.get("DataFormat", 0))

    result = {}
    for pm in mdt.PropertyMap.rows:
        t = pm.Parent.row
        tn = (t.TypeNamespace.value or '') + '.' + (t.TypeName.value or '')
        if not tn.startswith('NetProto.'):
            continue
        fields = {}
        for p in (pm.PropertyList or []):
            pr = p.row
            meta = prop_meta.get(id(pr))
            if meta is None:
                continue
            tag, df = meta
            sig = bytes(pr.Type.value) if hasattr(pr.Type, 'value') else b''
            fields[str(pr.Name)] = {"tag": tag,
                                    "type": decode_sig(sig, mdt),
                                    "dataFormat": df,
                                    "wire": DFNAME.get(df, "?")}
        if fields:
            result[tn] = fields
    json.dump(result, open(outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("types:", len(result), "->", outp)


if __name__ == "__main__":
    main()
