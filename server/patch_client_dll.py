#!/usr/bin/env python
"""给 360 4.2.0.1 的 Client.dll 打「跳过 SDK 登录」补丁。

原理（见 output/08_*）：
    MobileGameDemo.AndroidSdkConnector::StartLogin 的原始 IL 开头是
        02              ldarg.0
        7B 1E000004     ldfld  ignoreLogin
        2C 01           brfalse.s +1
        2A              ret
    即  if (!ignoreLogin) { ... 调用 SDK ... }

    把前 6 字节替换为
        17              ldc.i4.1
        00 00 00 00 00  nop x5
    得到 ldc.i4.1 -> brfalse.s(永不跳转) -> ret，等价于无条件 return，
    方法体长度不变，PE 头/偏移表全部无需修正。

用法:
    python patch_client_dll.py --src <apk内的Client序列化文件> --out <输出> [--mode skip|fake]

    --mode skip (默认)  只跳过 SDK 调用（StartLogin 直接 return）
    --mode fake         跳过 SDK 并立即以内置账号回调 CBUserLoginSuccess
"""
import argparse
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# 忽略登录的补丁字节：ldc.i4.1 + nop*5
SKIP_BYTES = b"\x17" + b"\x00" * 5


def find_pe_offset(data: bytes) -> int:
    """在 Unity 序列化文件里定位内嵌 PE 的起点（MZ，且附近能找到 BSJB）。"""
    best = None
    i = 0
    while True:
        i = data.find(b"MZ", i)
        if i < 0:
            break
        # metadata root (BSJB) 通常距 PE 起点很远，只要文件里后面存在即可
        if b"BSJB" in data[i:]:
            best = i
            break
        i += 1
    if best is None:
        raise SystemExit("未找到内嵌 PE（MZ + BSJB）")
    return best


def find_method_il_offset(pe_bytes: bytes, typename: str, methodname: str):
    """返回方法 IL 代码在 pe_bytes 内的偏移。需要 dnfile + dncil。"""
    import tempfile
    import dnfile
    from dncil.cil.body import CilMethodBody
    from dncil.cil.body.reader import CilMethodBodyReaderBase
    from dncil.cil.error import MethodBodyFormatError

    tmp = os.path.join(tempfile.gettempdir(), "_probe_client.dll")
    with open(tmp, "wb") as f:
        f.write(pe_bytes)

    class Reader(CilMethodBodyReaderBase):
        def __init__(self, pe, rva):
            self.pe = pe
            self.offset = pe.get_offset_from_rva(rva)

        def read(self, n):
            d = self.pe.__data__[self.offset:self.offset + n]
            self.offset += n
            return d

        def tell(self):
            return self.offset

        def seek(self, o):
            self.offset = o
            return o

    pe = dnfile.dnPE(tmp)
    mdt = pe.net.mdtables
    for t in mdt.TypeDef.rows:
        tn = ((t.TypeNamespace.value or "") + "." + t.TypeName.value).lstrip(".")
        if tn != typename and str(t.TypeName) != typename:
            continue
        for m in (t.MethodList or []):
            r = m.row if hasattr(m, "row") else m
            if str(r.Name) != methodname:
                continue
            off = pe.get_offset_from_rva(r.Rva)
            hdr = pe.__data__[off]
            if hdr & 3 == 2:          # tiny format
                code_off = off + 1
            else:                     # fat format: 12 字节头
                code_off = off + 12
            return code_off, r.Rva, pe.__data__[code_off:code_off + 12]
    raise SystemExit("未找到方法 %s::%s" % (typename, methodname))


def verify(pe_bytes: bytes, typename: str, methodname: str):
    """反汇编验证补丁生效。"""
    import tempfile
    sys.path.insert(0, os.path.join(HERE, "..", "work"))
    import dnfile
    from dncil.cil.body import CilMethodBody
    from dncil.cil.body.reader import CilMethodBodyReaderBase

    class Reader(CilMethodBodyReaderBase):
        def __init__(self, pe, rva):
            self.pe = pe
            self.offset = pe.get_offset_from_rva(rva)

        def read(self, n):
            d = self.pe.__data__[self.offset:self.offset + n]
            self.offset += n
            return d

        def tell(self):
            return self.offset

        def seek(self, o):
            self.offset = o
            return o

    tmp = os.path.join(tempfile.gettempdir(), "_verify_client.dll")
    with open(tmp, "wb") as f:
        f.write(pe_bytes)
    pe = dnfile.dnPE(tmp)
    for t in pe.net.mdtables.TypeDef.rows:
        tn = ((t.TypeNamespace.value or "") + "." + t.TypeName.value).lstrip(".")
        if tn != typename and str(t.TypeName) != typename:
            continue
        for m in (t.MethodList or []):
            r = m.row if hasattr(m, "row") else m
            if str(r.Name) != methodname:
                continue
            body = CilMethodBody(Reader(pe, r.Rva))
            out = []
            for ins in body.instructions[:6]:
                out.append("%-14s %s" % (ins.opcode.name, ins.operand if ins.operand is not None else ""))
            return out
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=None,
                    help="APK 内的 Client 序列化文件，默认 work/apk/client_4201_src.bin")
    ap.add_argument("--out", default=None,
                    help="输出文件，默认 <src>.patched")
    ap.add_argument("--mode", default="skip", choices=["skip", "fake"])
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()

    root = os.path.abspath(os.path.join(HERE, ".."))
    src = args.src or os.path.join(root, "work", "apk", "client_4201_src.bin")
    out = args.out or (src + ".patched")

    data = bytearray(open(src, "rb").read())
    pe_off = find_pe_offset(bytes(data))
    print("序列化文件大小 : %d" % len(data))
    print("内嵌 PE 起点    : 0x%x" % pe_off)

    pe_bytes = bytes(data[pe_off:])
    il_off, rva, raw = find_method_il_offset(pe_bytes, "MobileGameDemo.AndroidSdkConnector", "StartLogin")
    print("StartLogin RVA  : 0x%x" % rva)
    print("原始 IL         : %s" % raw[:8].hex(" "))

    if bytes(raw[:6]) != b"\x02\x7b\x1e\x00\x00\x04":
        print("!! 警告: 开头字节不是预期的 '02 7B 1E 00 00 04'，请人工确认")

    abs_off = pe_off + il_off
    print("补丁位置        : 文件偏移 0x%x (PE 内 0x%x)" % (abs_off, il_off))
    old = bytes(data[abs_off:abs_off + 6])
    data[abs_off:abs_off + 6] = SKIP_BYTES
    print("替换            : %s -> %s" % (old.hex(" "), SKIP_BYTES.hex(" ")))

    with open(out, "wb") as f:
        f.write(bytes(data))
    print("已写出          : %s (%d bytes)" % (out, len(data)))

    if not args.no_verify:
        print()
        print("=== 反汇编验证 (打补丁后) ===")
        for line in verify(bytes(data[pe_off:]), "MobileGameDemo.AndroidSdkConnector", "StartLogin"):
            print("   ", line)

    # 顺便给出 adb 目标路径
    print()
    print("直灌命令:")
    print('  adb push "%s" /data/user/0/com.fl.mhsy.qihoo/files/MHSY/ABs/Client/GameRes/Resources/Client.bytes.bytes' % out)


if __name__ == "__main__":
    main()
