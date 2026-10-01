#!/usr/bin/env python3
"""重建客户端文本配置包 GameText.txt.bytes（阶段16b）。

包格式（TextFileManager.Init/i 逆向实锤）：
  - 整包每字节 XOR 0x97 加密（i(byte[]) = b ^ 151）
  - 明文: [0:10] ASCII 十进制 = XML 清单长度
          [10:10+N] XML 清单（Directory/File 树，File 带 Name/StartPos/Length）
          [10+N:] 文件数据区；读取 Seek 基准 = (xmlLen+10) + StartPos
客户端 Init：persistentDataPath(/data/data/<pkg>/files/MHSY/ABs) 存在则直接用。

用法: python pack_gametext.py pull | inject | verify
"""
import os
import sys
import subprocess
import xml.etree.ElementTree as ET

ADB = r"C:/Program Files/Netease/MuMu/nx_main/adb.exe"
DEV = "127.0.0.1:7555"
PKG_REMOTE = ("/data/data/com.fl.mhsy.qihoo/files/MHSY/ABs"
              "/Client/GameRes/Resources/GameText.txt.bytes")
GD_REMOTE = ("/data/data/com.fl.mhsy.qihoo/files/MHSY/ABs/GameData")
BASE = os.path.dirname(os.path.abspath(__file__))
PKG_LOCAL = os.path.join(BASE, "gametext_local.bytes")
PKG_PLAIN = os.path.join(BASE, "gametext_plain.bytes")
INJECT_NAMES = [
    "OnceTaskConfig.txt",
    "DailyTaskConfig.txt",
]
XOR_KEY = 0x97


def adb(*args, timeout=300):
    r = subprocess.run([ADB, "-s", DEV] + list(args), capture_output=True,
                       timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError("%s -> %s" % (args[:2], r.stderr.decode("utf-8", "replace")))
    return r.stdout


def xor(buf, key=XOR_KEY):
    return bytes(b ^ key for b in buf)


def parse_plain(plain):
    xml_len = int(plain[:10].decode("ascii").strip())
    xml_bytes = plain[10:10 + xml_len]
    data = plain[10 + xml_len:]
    return xml_len, xml_bytes, data


def walk(node, prefix, out):
    for child in node:
        if child.tag == "Directory":
            name = child.get("Name", "")
            walk(child, prefix + name + "/" if name else prefix, out)
        elif child.tag == "File":
            out[prefix + child.get("Name", "")] = child


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "pull"

    # 拉包（root cat + exec-out 避免换行转换损坏二进制）
    r = adb("exec-out", "su 0 cat '%s'" % PKG_REMOTE)
    plain = xor(r)
    open(PKG_LOCAL, "wb").write(r)
    open(PKG_PLAIN, "wb").write(plain)
    xml_len, xml_bytes, data = parse_plain(plain)
    root = ET.fromstring(xml_bytes.decode("utf-8"))
    files = {}
    walk(root, "", files)
    print("包=%d 字节 xmlLen=%d 数据区=%d 清单文件数=%d"
          % (len(r), xml_len, len(data), len(files)))
    if mode == "pull":
        for p in sorted(files):
            if any(k in p for k in ("Task", "Region", "Chapter")):
                f = files[p]
                print("  ", p, f.get("StartPos"), f.get("Length"))
        return

    if mode == "verify":
        # 抽查：解出 GameData/OnceTaskConfig.txt 若在包里
        for p in INJECT_NAMES:
            f = files.get("GameData/" + p)
            if f is not None:
                s, ln = int(f.get("StartPos")), int(f.get("Length"))
                print("---", p, "前120字节 ---")
                print(data[s:s + 120].decode("utf-8", "replace"))
        return

    if mode == "inject":
        # 注入：缺的文件追加到数据区尾部并在根下加 File 节点；
        # 已存在的改写其 StartPos/Length 指向新数据（覆盖）
        new_payload = b""
        offset = 0
        for name in INJECT_NAMES:
            content = open(os.path.join(BASE, "gametext_inject", name), "rb").read()
            new_payload += content
            path = "GameData/" + name
            node = files.get(path)
            if node is not None:
                node.set("StartPos", str(len(data) + offset))
                node.set("Length", str(len(content)))
                print("覆盖节点", path, len(content))
            else:
                f = ET.SubElement(root, "File")
                f.set("Name", path)
                f.set("StartPos", str(len(data) + offset))
                f.set("Length", str(len(content)))
                print("新增节点", path, len(content))
            offset += len(content)
        data += new_payload
        new_xml = ET.tostring(root, encoding="utf-8")
        head = ("%010d" % len(new_xml)).encode("ascii")
        new_plain = head + new_xml + data
        new_enc = xor(new_plain)
        tmp = PKG_REMOTE + ".new"
        open(os.path.join(BASE, "gametext_new.bytes"), "wb").write(new_enc)
        adb("push", os.path.join(BASE, "gametext_new.bytes"), "/data/local/tmp/gt_new.bytes")
        adb("shell", "su 0 cp -f /data/local/tmp/gt_new.bytes '%s.new'" % PKG_REMOTE)
        adb("shell", "su 0 chmod 660 '%s.new'" % PKG_REMOTE)
        adb("shell", "su 0 mv -f '%s.new' '%s'" % (PKG_REMOTE, PKG_REMOTE))
        print("新包 %d 字节已回推（明文 xmlLen=%d 数据区=%d）"
              % (len(new_enc), len(new_xml), len(data)))
        return

    print(__doc__)


if __name__ == "__main__":
    main()
