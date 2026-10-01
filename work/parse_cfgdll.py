"""导出 Client.dll 中配置表类(*Cfg / *Data)的字段结构。

用法: python parse_cfgdll.py <dll> <out.json>
输出: 每个配置类的字段名/类型，用于重建 GameData/*.txt 的列结构。
"""
import json
import sys
import dnfile


class BlobReader:
    def __init__(self, data):
        self.d = data
        self.p = 0

    def u8(self):
        v = self.d[self.p]; self.p += 1; return v

    def compressed_uint(self):
        b = self.u8()
        if b & 0x80 == 0:
            return b
        if b & 0xC0 == 0x80:
            return ((b & 0x3F) << 8) | self.u8()
        if b & 0xE0 == 0xC0:
            return (((b & 0x1F) << 24) | (self.u8() << 16) | (self.u8() << 8) | self.u8())
        raise ValueError("bad compressed uint")

    def typedef_or_ref(self):
        v = self.compressed_uint()
        return (v >> 2) - 1, v & 3


def type_name(pe, br):
    while True:
        e = br.compressed_uint()
        if e == 0x00:
            return "void"
        if e == 0x01: return "void*"
        if e == 0x02: return "bool"
        if e == 0x03: return "char"
        if e == 0x04: return "sbyte"
        if e == 0x05: return "byte"
        if e == 0x06: return "short"
        if e == 0x07: return "ushort"
        if e == 0x08: return "int"
        if e == 0x09: return "uint"
        if e == 0x0a: return "long"
        if e == 0x0b: return "ulong"
        if e == 0x0c: return "float"
        if e == 0x0d: return "double"
        if e == 0x0e: return "string"
        if e == 0x11:  # VALUETYPE
            idx, tag = br.typedef_or_ref()
            return get_name(pe, idx, tag)
        if e == 0x12:  # CLASS
            idx, tag = br.typedef_or_ref()
            return get_name(pe, idx, tag)
        if e == 0x15:  # GENERICINST
            br.compressed_uint()
            idx, tag = br.typedef_or_ref()
            cnt = br.compressed_uint()
            args = [type_name(pe, br) for _ in range(cnt)]
            return f"{get_name(pe, idx, tag)}<{','.join(args)}>"
        if e == 0x1b:  # SZARRAY
            return type_name(pe, br) + "[]"
        if e == 0x1d:  # ARRAY
            t = type_name(pe, br)
            br.compressed_uint()  # rank
            br.compressed_uint()  # numsizes
            return t + "[]"
        raise ValueError(f"unhandled element type 0x{e:x}")


def get_name(pe, idx, tag):
    mt = pe.net.mdtables
    try:
        if tag == 0:
            return str(mt.TypeDef.rows[idx].TypeName)
        if tag == 1:
            r = mt.TypeRef.rows[idx]
            return str(r.TypeName)
        if tag == 2:
            return "TypeSpec"
    except Exception:
        return "?"
    return "?"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "carved/CAB-Client_0000332b.dll"
    out = sys.argv[2] if len(sys.argv) > 2 else "config_schema.json"
    pe = dnfile.dnPE(path)
    mt = pe.net.mdtables

    results = {}
    for t in mt.TypeDef.rows:
        tn = str(t.TypeName)
        ns = str(t.TypeNamespace) or ""
        if not (tn.endswith("Cfg") or tn.endswith("Data")):
            continue
        fields = []
        for f in (t.FieldList or []):
            fr = f.row if hasattr(f, "row") else f
            fn = str(fr.Name)
            sig = fr.Signature
            try:
                b = bytes(sig.value)
                br = BlobReader(b)
                assert br.u8() == 0x06  # FieldSig
                ft = type_name(pe, br)
            except Exception:
                ft = "?"
            fields.append({"name": fn, "type": ft})
        if fields:
            results[f"{ns}.{tn}"] = {"ns": ns, "name": tn, "fields": fields}

    json.dump(results, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"导出 {len(results)} 个配置类 -> {out}")
    for k in sorted(results):
        v = results[k]
        print(f"  {v['name']:<38} {len(v['fields']):>3} 字段")


if __name__ == "__main__":
    main()
