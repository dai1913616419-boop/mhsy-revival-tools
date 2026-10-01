#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""打开客户端调试日志：把 Log/LogError 的空壳方法重定向到真正的 Debug.Log。

背景：发行版把 Log/LogError 编译成了只有 `ret` 的空方法（混淆器干的），
而同一个类里留了一个真正的实现（ldarg.0; call UnityEngine.Debug::Log; ret）。
把空壳 MethodDef 的 RVA 改成真实现的 RVA 即可让客户端把内部日志打回 logcat。

用法:
    python patch_debug_log.py [--src <序列化文件>] [--out <输出>]
默认读 work/apk/Client_patched.bin（先跑 patch_login_system.py）。
"""
import argparse
import os

import dnfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))

REAL_LOG_RVA = 0x28EC38          # ldarg.0; call UnityEngine.Debug::Log; ret


def find_pe_offset(data: bytes) -> int:
    i = 0
    while True:
        i = data.find(b"MZ", i)
        if i < 0:
            raise SystemExit("未找到内嵌 PE")
        if b"BSJB" in data[i:]:
            return i
        i += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(ROOT, "work", "apk", "Client_patched.bin"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work", "apk", "Client_patched.bin"))
    args = ap.parse_args()

    data = bytearray(open(args.src, "rb").read())
    pe_off = find_pe_offset(bytes(data))

    # 重新以内存数据建 PE 对象
    import tempfile
    tmp = os.path.join(tempfile.gettempdir(), "_pdl.dll")
    with open(tmp, "wb") as f:
        f.write(bytes(data[pe_off:]))
    pe = dnfile.dnPE(tmp)
    md = pe.net.mdtables.MethodDef
    row_size = md.row_size
    tbl_off = md.file_offset
    print("MethodDef 表: file_offset=0x%x row_size=%d rows=%d" % (tbl_off, row_size, md.num_rows))

    # 在内存数据里定位 MethodDef 表（pe 相对 -> 序列化文件相对）
    # dnfile 的 file_offset 是相对整个 PE 文件的，正好等于 pe 内偏移
    targets = []
    for i, r in enumerate(md.rows, 1):
        nm = str(r.Name)
        if nm in ("Log", "LogError") and r.Rva in (0x9B644, 0x9B646, 0x9B648, 0x9B64A,
                                                   0x9B64C, 0x9B64E, 0x9B650, 0x9B652):
            # 只重定向单参数版本（object），多参数版本保持空壳
            sig = r.Signature.value.hex() if r.Signature else ""
            if sig.startswith("000101"):
                targets.append((i, nm, r.Rva, sig))

    for rid, nm, rva, sig in targets:
        off = pe_off + tbl_off + (rid - 1) * row_size
        cur = int.from_bytes(data[off:off + 4], "little")
        assert cur == rva, "row %d RVA 0x%x != 期望 0x%x" % (rid, cur, rva)
        data[off:off + 4] = REAL_LOG_RVA.to_bytes(4, "little")
        print("rid=%-6d %-9s rva 0x%06x -> 0x%06x  (sig %s)" % (rid, nm, rva, REAL_LOG_RVA, sig))

    if not targets:
        raise SystemExit("未找到可重定向的 Log 空壳")

    with open(args.out, "wb") as f:
        f.write(bytes(data))
    print("已写出:", args.out, len(data))


if __name__ == "__main__":
    main()
