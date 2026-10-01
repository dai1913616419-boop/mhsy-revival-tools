#!/usr/bin/env python3
"""解析 protobuf-net 消息契约 DLL（NetProto）→ 完整 messages_full.json
用法: python parse_protobuf_full.py <dll> [out.json]
输出: {TypeName: {field_name: {"tag": n, "type": "int32/string/float/bool/message:T"}}}
"""
import sys, os, json, struct
import dnfile

ET = {0x02:"bool",0x04:"int8",0x05:"uint8",0x06:"int16",0x07:"uint16",
      0x08:"int32",0x09:"uint32",0x0A:"int64",0x0B:"uint64",
      0x0C:"float",0x0D:"double",0x0E:"string"}

def main():
    dll = sys.argv[1]
    outp = sys.argv[2] if len(sys.argv) > 2 else "messages_full.json"
    pe = dnfile.dnPE(dll)
    mdt = pe.net.mdtables
    prop_by_rid = {i: str(r.Name) for i, r in enumerate(mdt.Property.rows, 1)}
    prop_row_id = {id(r): i for i, r in enumerate(mdt.Property.rows, 1)}

    # 属性(按 rid 唯一标识，避免不同类型同名属性互相覆盖) -> ProtoMember tag + DataFormat
    # ⚠ 实测坑：DataFormat=2(FixedSize) 的 int 字段必须用 fixed32 编码，
    #   发 varint 客户端报 ProtoException: Invalid wire-type（阶段15 JJC 实锤）。
    prop_meta = {}
    for r in mdt.CustomAttribute.rows:
        par = r.Parent
        if par.table is None or getattr(par.table, 'name', '') != 'Property':
            continue
        try:
            cls = r.Type.row.Class.row
            tn = (cls.TypeNamespace.value or '') + '.' + (cls.TypeName.value or '')
        except Exception:
            continue
        if 'ProtoMember' not in tn:
            continue
        b = bytes(r.Value.value)
        if len(b) >= 7 and b[0] == 1 and b[1] == 0:
            meta = {"tag": struct.unpack('<i', b[2:6])[0]}
            # blob 含 "Protobuf.DataFormat, protobuf-net..." 程序集限定名，
            # 真正的 named arg 在尾部独立出现的 "DataFormat"（前缀 len=0x0a）-> 用 rfind
            i2 = b.rfind(b"DataFormat")
            if i2 >= 0:
                p = i2 + 10                  # 跳过 "DataFormat"
                if p + 4 <= len(b):
                    meta["dataFormat"] = struct.unpack('<i', b[p:p+4])[0]
            prop_meta[par.row_index] = meta

    # ProtoInclude: 类型继承树（不必须）
    # 类型 -> 属性列表（带返回类型签名）
    result = {}
    for pm in mdt.PropertyMap.rows:
        t = pm.Parent.row
        tn = (t.TypeNamespace.value or '') + '.' + (t.TypeName.value or '')
        if not tn.startswith('NetProto.'):
            continue
        fields = {}
        for p in (pm.PropertyList or []):
            name = str(p.row.Name)
            prow = p.row
            sig = bytes(prow.Type.value) if hasattr(prow.Type, 'value') else b''
            # 简单签名解析: CALLCONV PROP(0x08) + param_count + ret_type
            ftype = decode_sig(sig, mdt)
            rid = prop_row_id.get(id(prow))
            meta = prop_meta.get(rid)
            if meta is None:
                continue
            fields[name] = {"tag": meta["tag"], "type": ftype,
                            "dataFormat": meta.get("dataFormat", 0)}
        if fields:
            result[tn] = fields

    json.dump(result, open(outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("types:", len(result), "->", outp)

def decode_sig(sig, mdt):
    """FieldSig/PropertySig: 0x08 + count + type"""
    if len(sig) < 3:
        return "?"
    i = 0
    if sig[0] == 0x08:   # PropertySig
        i = 2            # skip 0x08, param_count
    elif sig[0] == 0x06: # FieldSig
        i = 1
    else:
        i = 1
    if i >= len(sig):
        return "?"
    et = sig[i]
    if et in ET:
        return ET[et]
    if et in (0x11, 0x12):  # valuetype/class -> TypeDefOrRef coded
        coded = sig[i+1] >> 2
        tbl, rid = decode_coded(coded)
        name = resolve_name(mdt, tbl, rid)
        return name or ("vt#%d" % coded)
    if et == 0x1D:  # szarray
        return "list:" + decode_sig(b'\x08\x00' + sig[i+1:], mdt).split(":",1)[-1]
    if et == 0x02 and len(sig) > i+1 and sig[i+1] == 0x12:
        pass
    return "raw:%s" % sig.hex()

def decode_coded(v):
    # TypeDefOrRef: 2 bits tag: 0=TypeDef,1=TypeRef,2=TypeSpec
    tag = v & 3
    rid = v >> 2
    return ("TypeDef" if tag==0 else "TypeRef" if tag==1 else "TypeSpec"), rid

def resolve_name(mdt, tbl, rid):
    try:
        if tbl == "TypeDef":
            r = mdt.TypeDef.rows[rid-1]
            return (r.TypeNamespace.value or '') + '.' + (r.TypeName.value or '')
        if tbl == "TypeRef":
            r = mdt.TypeRef.rows[rid-1]
            return (r.TypeNamespace.value or '') + '.' + (r.TypeName.value or '')
    except Exception:
        pass
    return None

if __name__ == "__main__":
    main()
