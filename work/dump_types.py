#!/usr/bin/env python3
"""列出 DLL 中所有 TypeDef，并可 grep 关键字；并打印某类型的属性表 + ProtoMember tag。
用法:
  python dump_types.py <dll>                 # 列出所有类型名
  python dump_types.py <dll> grep <kw>       # 只列名字含 kw 的
  python dump_types.py <dll> type <FullName> # 打印该类型属性/字段 + tag
"""
import sys, struct
import dnfile

def typename(t):
    return (t.TypeNamespace.value or '') + '.' + (t.TypeName.value or '')

def main():
    dll = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "list"
    pe = dnfile.dnPE(dll)
    mdt = pe.net.mdtables
    if mode in ("list", "grep"):
        kw = sys.argv[3].lower() if mode == "grep" else None
        n = 0
        for t in mdt.TypeDef.rows:
            nm = typename(t)
            if kw is None or kw in nm.lower():
                print(nm)
                n += 1
        print("---- total:", n)
        return

    if mode == "type":
        target = sys.argv[3]
        # find TypeDef
        trow = None
        for t in mdt.TypeDef.rows:
            if typename(t) == target:
                trow = t
                break
        if trow is None:
            print("type not found:", target)
            return
        # ProtoMember tags per Property row_index
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
                tag = struct.unpack('<i', b[2:6])[0]
                df = 0
                i2 = b.rfind(b"DataFormat")
                if i2 >= 0:
                    p = i2 + 10
                    if p + 4 <= len(b):
                        df = struct.unpack('<i', b[p:p+4])[0]
                prop_meta[id(par.row)] = (tag, df)
        print("== type", target)
        found = False
        for pm in mdt.PropertyMap.rows:
            par = pm.Parent.row
            if par is not trow and id(par) != id(trow):
                continue
            found = True
            for p in (pm.PropertyList or []):
                pr = p.row
                tag, df = prop_meta.get(id(pr), (None, None))
                sig = bytes(pr.Type.value) if hasattr(pr.Type, 'value') else b''
                print("  %-34s tag=%-4s df=%s sig=%s" % (str(pr.Name), tag, df, sig.hex()))
        if not found:
            print("  (no PropertyMap entry)")
        # fields
        for f in mdt.Field.rows:
            try:
                is_owned = f.Owner.row is trow
            except Exception:
                is_owned = False
            if is_owned:
                print("  [field] %s sig=%s" % (str(f.Name), bytes(f.Signature.value).hex()))
        return

    print("unknown mode", mode)

if __name__ == "__main__":
    main()
