#!/usr/bin/env python
"""把打了补丁的 Client.dll 替换进 360 4.2.0.1 APK 的副本（不改动原始 APK）。

背景：客户端优先从 persistentDataPath 加载热更 DLL，但那里要求
UncompressedAssetBundle(UnityRaw) 格式；APK 内置的是 Unity 序列化文件，
两者格式不同。因此最可靠的注入方式是直接替换 APK 内的同名条目。

用法:
    python repack_apk.py --apk <原APK> --dll <补丁后的序列化文件> --out <输出>
    python repack_apk.py   # 使用默认路径

随后需要签名（sign_apk.py）再安装。
"""
import argparse
import os
import shutil
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))

# 360 4.2.0.1 里承载 Client.dll 的 Unity 资源条目
CLIENT_ENTRY = "assets/bin/Data/3a856d039ee973a45b8db02f22473eeb"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apk", default=os.path.join(ROOT, "work", "apk", "mhsy_qihoo_4201.apk"))
    ap.add_argument("--dll", default=os.path.join(ROOT, "work", "apk", "Client_patched.bin"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work", "apk", "mhsy_qihoo_4201_patched.apk"))
    ap.add_argument("--entry", default=CLIENT_ENTRY)
    args = ap.parse_args()

    src_dll = open(args.dll, "rb").read()
    print("补丁 DLL : %s (%d bytes)" % (args.dll, len(src_dll)))

    zin = zipfile.ZipFile(args.apk)
    entries = [(i, None) for i in zin.infolist()]

    replaced = False
    kept_meta = []
    with zipfile.ZipFile(args.out, "w", allowZip64=True) as zout:
        for info in zin.infolist():
            # 旧的签名目录必须丢弃，稍后由 sign_apk.py 重建
            if info.filename.startswith("META-INF/"):
                kept_meta.append(info.filename)
                continue
            data = zin.read(info.filename)
            if info.filename == args.entry:
                print("替换条目 : %s  %d -> %d bytes" % (info.filename, len(data), len(src_dll)))
                data = src_dll
                replaced = True
            new = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            new.compress_type = info.compress_type
            new.external_attr = info.external_attr
            new.internal_attr = info.internal_attr
            new.create_system = info.create_system
            zout.writestr(new, data)
    zin.close()

    if not replaced:
        raise SystemExit("!! 未在 APK 中找到条目 %s，请确认路径" % args.entry)

    print("移除旧签名 : %d 个 META-INF 条目" % len(kept_meta))
    print("已写出     : %s (%d bytes)" % (args.out, os.path.getsize(args.out)))
    print()
    print("下一步:")
    print("  python sign_apk.py \"%s\" --inplace" % os.path.relpath(args.out, HERE))
    print("  adb uninstall com.fl.mhsy.qihoo")
    print("  adb install \"%s\"" % args.out)


if __name__ == "__main__":
    main()
