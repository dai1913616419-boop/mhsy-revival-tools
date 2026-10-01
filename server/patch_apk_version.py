#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修改 APK **副本** 中内置的更新服域名，让客户端指向本地服务器。

背景：客户端的更新服域名写在 Unity TextAsset `Version.bytes` 里
（APK 内路径 assets/bin/Data/7bcccccbb6d31a741b30b3f77d8d946c），
服务器下发的地址无效，所以想换地址只能改这里，或者改 hosts。

本脚本做的事：
  1. 复制 APK -> 同名 .patched.apk（原始 APK 只读，绝不改动）
  2. 定位 value 字符串并替换其中的域名
  3. 同步修正三处长度字段：
       - value 长度（小端，位于字符串前 4 字节）
       - Unity 对象的 byteSize（大端，文件 offset 36）
       - 序列化头 m_FileSize（大端，文件 offset 4）
  4. 尝试重新签名；没有 Java 时给出手工签名命令

用法：
  python patch_apk_version.py --host 192.168.0.12
  python patch_apk_version.py --host 192.168.0.12:8080 --apk <原始apk路径>

⚠️ Android 要求 APK 必须签名才能安装。若本机没有 JDK，脚本无法签名，
   请优先使用 hosts 方案（见 README）。
"""

import argparse
import os
import shutil
import struct
import subprocess
import sys
import zipfile

RES_PATH = "assets/bin/Data/7bcccccbb6d31a741b30b3f77d8d946c"
OLD_DOMAIN = b"game.360joy.com.cn"

OFF_FILESIZE = 4  # 大端，整个文件大小


def find_object_size_off(data: bytes) -> int:
    """定位 Unity 序列化对象表里 byteSize 字段的偏移。

    注意：Unity serialized file 只有头部是大端，metadata（含对象表）是小端。
    做法：读头部的 m_DataOffset，算出该对象应有的大小 (len(data) - dataOffset)，
    再在 metadata 区 4 字节对齐的位置上找吻合的小端 uint32。
    """
    (data_offset,) = struct.unpack_from(">I", data, 12)   # 头部字段，大端
    expected = len(data) - data_offset
    for off in range(data_offset - 4, 19, -4):
        (v,) = struct.unpack_from("<I", data, off)        # 对象表，小端
        if v == expected:
            return off
    raise SystemExit("未能定位对象 byteSize 字段（预期值 %d）" % expected)


def patch_res(data: bytes, new_domain: bytes) -> bytes:
    """替换域名并修正长度字段。返回新的资源文件字节。"""
    # 定位 key: 长度(4)=7 + "Version" + padding(1)
    marker = struct.pack("<I", 7) + b"Version\x00"
    pos = data.find(marker)
    if pos < 0:
        raise SystemExit("未找到 Version key，文件结构可能不同")

    vlen_pos = pos + len(marker)
    (old_len,) = struct.unpack_from("<I", data, vlen_pos)
    vstart = vlen_pos + 4
    old_value = data[vstart:vstart + old_len]

    if OLD_DOMAIN not in old_value:
        raise SystemExit("value 中未找到 %s，可能已被改过" % OLD_DOMAIN.decode())

    new_value = old_value.replace(OLD_DOMAIN, new_domain)
    new_len = len(new_value)

    # Unity 字符串后面 padding 到 4 字节对齐
    old_pad = (4 - old_len % 4) % 4
    new_pad = (4 - new_len % 4) % 4
    tail = data[vstart + old_len + old_pad:]   # 对象数据尾部的其他字段，原样保留

    out = bytearray()
    out += data[:vlen_pos]
    out += struct.pack("<I", new_len)
    out += new_value
    out += b"\x00" * new_pad
    out += tail

    delta = (new_len + new_pad) - (old_len + old_pad)

    off_obj_size = find_object_size_off(data)
    (obj_size,) = struct.unpack_from("<I", out, off_obj_size)
    struct.pack_into("<I", out, off_obj_size, obj_size + delta)
    (file_size,) = struct.unpack_from(">I", out, OFF_FILESIZE)   # 头部字段，大端
    struct.pack_into(">I", out, OFF_FILESIZE, file_size + delta)

    print("  value 长度: %d -> %d (delta %+d)" % (old_len, new_len, delta))
    print("  byteSize  : offset %d, %d -> %d" % (off_obj_size, obj_size, obj_size + delta))
    print("  文件大小  : %d -> %d" % (file_size, file_size + delta))
    return bytes(out)


def rebuild_apk(src_apk: str, dst_apk: str, new_res: bytes):
    """复制 APK 并替换其中的资源条目，保持原有压缩方式。"""
    with zipfile.ZipFile(src_apk, "r") as zin:
        with zipfile.ZipFile(dst_apk, "w") as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename == RES_PATH:
                    data = new_res
                    print("  已替换: %s" % info.filename)
                # 旧签名在改包后失效，直接丢弃，稍后重签
                if info.filename.startswith("META-INF/"):
                    continue
                new_info = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                new_info.compress_type = info.compress_type
                new_info.external_attr = info.external_attr
                zout.writestr(new_info, data)


def try_sign(apk: str) -> bool:
    """有 JDK 就用 keytool+jarsigner 做 v1 签名。"""
    ks = apk + ".keystore"
    cmds = [
        ["keytool", "-genkeypair", "-alias", "mhsy", "-keyalg", "RSA", "-keysize", "2048",
         "-validity", "10950", "-keystore", ks, "-storepass", "123456", "-keypass", "123456",
         "-dname", "CN=mhsy, OU=local, O=local, L=local, S=local, C=CN"],
        ["jarsigner", "-verbose", "-sigalg", "SHA1withRSA", "-digestalg", "SHA1",
         "-keystore", ks, "-storepass", "123456", "-keypass", "123456", apk, "mhsy"],
    ]
    for cmd in cmds:
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except FileNotFoundError:
            print("\n未找到 Java 工具链，无法自动签名。")
            print("请二选一：")
            print("  A) 安装 JDK 后重跑本脚本")
            print("  B) 用 hosts 方案（推荐）：adb shell \"echo '<PC-IP> game.360joy.com.cn' >> /system/etc/hosts\"")
            return False
        except subprocess.CalledProcessError as e:
            print("签名命令失败: %s" % " ".join(cmd))
            print(e.stderr.decode("utf-8", "replace")[:500])
            return False
    print("已签名: %s" % apk)
    return True


def main():
    ap = argparse.ArgumentParser(description="改 APK 副本中的更新服域名")
    ap.add_argument("--apk", default=r"C:\Users\19136\Desktop\梦幻神域_UC_2662808_105628864d2d.apk")
    ap.add_argument("--host", required=True, help="本地服务器地址，如 192.168.0.12 或 192.168.0.12:8080")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    src = args.apk
    if not os.path.isfile(src):
        raise SystemExit("找不到 APK: %s" % src)
    dst = args.out or (os.path.splitext(src)[0] + ".patched.apk")

    print("原始 APK : %s (只读)" % src)
    print("输出副本 : %s" % dst)
    print("新域名   : %s" % args.host)

    with zipfile.ZipFile(src, "r") as z:
        data = z.read(RES_PATH)

    new_res = patch_res(data, args.host.encode("ascii"))
    print("改写资源 : %s (%d -> %d bytes)" % (RES_PATH, len(data), len(new_res)))

    rebuild_apk(src, dst, new_res)
    print("已生成   : %s" % dst)

    signed = try_sign(dst)
    print("-" * 60)
    if signed:
        print("可直接安装：adb install -r \"%s\"" % dst)
    else:
        print("未签名，模拟器/真机会拒绝安装。建议改用 hosts 方案。")
    return 0 if signed else 2


if __name__ == "__main__":
    sys.exit(main())
