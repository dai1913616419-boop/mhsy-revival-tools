#!/usr/bin/env python3
"""从 Unity AssetBundle（或任意二进制）中雕刻 .NET 程序集。
用法: carve_dlls.py <bundle_file> [outdir]
扫描 MZ/PE 签名，验证 .NET 元数据，输出每个程序集到 outdir/<asmname>.dll
"""
import sys, os, struct
import dnfile

def pe_size(d):
    if d[:2] != b"MZ":
        return None
    try:
        e_lfanew = struct.unpack_from("<I", d, 0x3C)[0]
        if d[e_lfanew:e_lfanew+4] != b"PE\x00\x00":
            return None
        coff = e_lfanew + 4
        num_sec = struct.unpack_from("<H", d, coff+2)[0]
        opt_size = struct.unpack_from("<H", d, coff+16)[0]
        opt = coff + 20
        magic = struct.unpack_from("<H", d, opt)[0]
        # size of image at opt+56
        size_image = struct.unpack_from("<I", d, opt+56)[0]
        return size_image
    except Exception:
        return None

def main():
    path = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else "work/carved2"
    os.makedirs(outdir, exist_ok=True)
    data = open(path, "rb").read()
    n = 0
    i = 0
    while True:
        j = data.find(b"MZ", i)
        if j < 0:
            break
        sz = pe_size(data[j:j+0x1000])
        cand = data[j:j+sz] if sz else None
        ok = False
        asm = None
        if cand and sz and 4096 <= sz <= 40*1024*1024:
            tmp = os.path.join(outdir, "_tmp.dll")
            open(tmp, "wb").write(cand)
            try:
                pe = dnfile.dnPE(tmp)
                a = pe.net.mdtables.Assembly
                if a and a.rows:
                    asm = str(a.rows[0].Name)
                    ok = True
            except Exception:
                ok = False
        if ok:
            out = os.path.join(outdir, asm + ".dll")
            with open(out, "wb") as f:
                f.write(cand)
            print("FOUND asm=%-24s off=0x%x size=%d -> %s" % (asm, j, sz, out))
            n += 1
            i = j + sz
        else:
            i = j + 2
    if os.path.exists(os.path.join(outdir, "_tmp.dll")):
        os.remove(os.path.join(outdir, "_tmp.dll"))
    print("total assemblies:", n)

if __name__ == "__main__":
    main()
