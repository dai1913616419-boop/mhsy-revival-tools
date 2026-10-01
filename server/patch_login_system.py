#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""阶段 9：把「选服登录」强制打开，并把服务器列表 URL 指向本地服务端。

背景（见 output/08b、output/09）：
  360 渠道包内置的 GameData/game.cfg 里 choice_server_login=false，
  所以 LoginSystem::Open 永远不会 StartCoroutine(FetchServerList)，
  选服列表拿不到，游戏就卡在登录界面。

补丁清单（偏移均为「内嵌 PE 文件内」的相对偏移，4.2.0.1 版校验过）：
  P1  AndroidSdkConnector::StartLogin          -> 6 字节，直接 return（跳过 SDK 登录）
  P2  LoginSystem::Open 0x1a4be1  15B          -> 第一行的键比较恒为真
  P3  LoginSystem::Open 0x1a4bf0   8B          -> mChoiceServerLogin = true
  P4  LoginSystem::Open 0x1a4c0f   8B          -> mShow_nonsdk_pwd_dlg = false
  P5  LoginSystem::Open 0x1a4edd   5B          -> ldsfld mChoiceServerLogin 换成 ldc.i4.1（必走 FetchServerList）
  P6  FetchServerList  0x1a5bb8  11B          -> this.ᜋ 换成 ldstr（我们自己的 URL）
  P7  #US 堆 0x384022  86B                    -> 改写那条 URL 字符串内容（等长替换）

用法:
    python patch_login_system.py [--src <序列化文件>] [--out <输出>]
                                 [--url http://192.168.0.12:80/Other/serverlist.txt]
"""
import argparse
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))

# ---- 补丁常量（PE 内相对偏移 / 期望原字节 / 新字节） ----
PATCHES = [
    # (名称, 偏移, 期望原字节 or None, 新字节, 说明)
    ("P2 choice_server_login 分支恒真", 0x1A4BE1,
     bytes.fromhex("09169a72f4dc0270281f00000a2c0f"),
     b"\x17" + b"\x00" * 12 + b"\x2c\x01",
     "ldloc.3/ldc.i4.0/ldelem.ref/ldstr/call/brfalse.s -> ldc.i4.1 + nop*12 + brfalse.s+1"),

    ("P3 mChoiceServerLogin = true", 0x1A4BF0,
     bytes.fromhex("09179a28e900000a"),
     b"\x17" + b"\x00" * 7,
     "ldloc.3/ldc.i4.1/ldelem.ref/ToBoolean -> ldc.i4.1"),

    ("P4 mShow_nonsdk_pwd_dlg = false", 0x1A4C0F,
     bytes.fromhex("09179a28e900000a"),
     b"\x16" + b"\x00" * 7,
     "同上，但改写成 ldc.i4.0"),

    ("P5 强制进入 FetchServerList", 0x1A4EDD,
     bytes.fromhex("7e133100 04".replace(" ", "")),
     b"\x17" + b"\x00" * 4,
     "ldsfld mChoiceServerLogin -> ldc.i4.1（后面的 brfalse.s 永不跳转）"),

    ("P6 FetchServerList 用硬编码 URL", 0x1A5BB8,
     bytes.fromhex("027b323100047b18310004"),
     b"\x72\x85\x0a\x00\x70" + b"\x00" * 6,
     "ldarg.0/ldfld ᜀ/ldfld ᜋ -> ldstr #US:0xA85 + nop*6"),
]

# #US 堆中要被改写的原始字符串（43 个 UTF-16 字符 = 86 字节）
US_URL_OLD = "http://192.168.0.157/UpLoad/UnityUpload.php"
US_URL_OFF = 0x384022           # 在 PE 内的偏移（字符串内容起点，不含长度前缀）
US_URL_LEN = len(US_URL_OLD)    # 字符数 43

SKIP_BYTES = b"\x17" + b"\x00" * 5   # StartLogin: ldc.i4.1 + nop*5


def find_pe_offset(data: bytes) -> int:
    i = 0
    while True:
        i = data.find(b"MZ", i)
        if i < 0:
            raise SystemExit("未找到内嵌 PE（MZ）")
        if b"BSJB" in data[i:]:
            return i
        i += 1


def find_startlogin_code(pe_bytes: bytes):
    """返回 StartLogin 方法体第一条指令在 pe_bytes 内的偏移。"""
    import tempfile
    import dnfile
    tmp = os.path.join(tempfile.gettempdir(), "_pls_client.dll")
    with open(tmp, "wb") as f:
        f.write(pe_bytes)
    pe = dnfile.dnPE(tmp)
    for t in pe.net.mdtables.TypeDef.rows:
        tn = ((t.TypeNamespace.value or "") + "." + t.TypeName.value).lstrip(".")
        if "AndroidSdkConnector" not in tn:
            continue
        for m in (t.MethodList or []):
            r = m.row if hasattr(m, "row") else m
            if str(r.Name) != "StartLogin" or not r.Rva:
                continue
            off = pe.get_offset_from_rva(r.Rva)
            return (off + 1) if (pe.__data__[off] & 3) == 2 else (off + 12)
    raise SystemExit("未找到 AndroidSdkConnector::StartLogin")


def build_url(base: str) -> str:
    """把 URL 补齐到 43 个字符（#US 条目长度固定，不能改长度前缀）。"""
    n = US_URL_LEN - len(base)
    if n < 0:
        raise SystemExit("URL 太长：%d > %d，请缩短路径" % (len(base), US_URL_LEN))
    if n == 0:
        return base
    return base + "?" + "x" * (n - 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(ROOT, "work", "apk", "client_4201.bin"))
    ap.add_argument("--out", default=os.path.join(ROOT, "work", "apk", "Client_patched.bin"))
    ap.add_argument("--url", default="http://192.168.0.12:80/Other/serverlist.txt")
    ap.add_argument("--no-sdk-patch", action="store_true", help="不打 P1（跳过 SDK 登录）")
    args = ap.parse_args()

    data = bytearray(open(args.src, "rb").read())
    pe_off = find_pe_offset(bytes(data))
    pe_len = len(data) - pe_off
    print("序列化文件 : %d bytes" % len(data))
    print("内嵌 PE    : 偏移 0x%x, 长度 %d" % (pe_off, pe_len))

    abs_off = lambda off: pe_off + off

    # ---------- P1 ----------
    if not args.no_sdk_patch:
        code = find_startlogin_code(bytes(data[pe_off:]))
        a = abs_off(code)
        old = bytes(data[a:a + 6])
        if old != bytes.fromhex("027b1e000004"):
            print("!! P1 首字节不是预期的 02 7B 1E 00 00 04（实际 %s），跳过" % old.hex(" "))
        else:
            data[a:a + 6] = SKIP_BYTES
            print("P1 StartLogin           @PE+0x%x : %s -> %s" % (code, old.hex(" "), SKIP_BYTES.hex(" ")))

    # ---------- P2..P6 ----------
    for name, off, expect, new, note in PATCHES:
        a = abs_off(off)
        cur = bytes(data[a:a + len(expect)])
        if cur != expect:
            raise SystemExit("!! %s 校验失败\n   偏移 0x%x 实际 %s\n   期望 %s"
                             % (name, off, cur.hex(" "), expect.hex(" ")))
        data[a:a + len(new)] = new
        print("%-32s @PE+0x%x : OK   (%s)" % (name, off, note))

    # ---------- P7: #US 字符串 ----------
    old_bytes = US_URL_OLD.encode("utf-16-le")
    a = abs_off(US_URL_OFF)
    cur = bytes(data[a:a + len(old_bytes)])
    if cur != old_bytes:
        raise SystemExit("!! P7 校验失败：0x%x 处不是原 URL" % US_URL_OFF)
    url = build_url(args.url)
    new_bytes = url.encode("utf-16-le")
    assert len(new_bytes) == len(old_bytes), (len(new_bytes), len(old_bytes))
    data[a:a + len(new_bytes)] = new_bytes
    print("P7 #US URL              @PE+0x%x : \"%s\" -> \"%s\"" % (US_URL_OFF, US_URL_OLD, url))

    with open(args.out, "wb") as f:
        f.write(bytes(data))
    print()
    print("已写出     : %s (%d bytes)" % (args.out, len(data)))
    print()
    print("下一步:")
    print("  python repack_apk.py")
    print("  python sign_apk.py ../work/apk/mhsy_qihoo_4201_patched.apk --inplace")
    print("  adb uninstall com.fl.mhsy.qihoo && adb install ../work/apk/mhsy_qihoo_4201_patched.apk")


if __name__ == "__main__":
    main()
