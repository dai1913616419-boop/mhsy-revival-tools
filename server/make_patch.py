#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成热更新补丁：把 patches/<ver>/ 下的文件打包成客户端能识别的更新包。

产出（写进 server/www/）：
  Android/UpdateRoot/IncrementPack/<ver>/Client/GameRes/Resources/MD5File.txt.bytes
  Android/UpdateRoot/IncrementPack/<ver>/<每个补丁文件原路径>

MD5File 只需列出「要改动的文件」——客户端 CompareMD5File 的逻辑是：
  遍历服务器清单，凡是本地没有、或本地 md5 不同的条目，才加入下载列表。
所以补丁清单越小越好，没列出的文件客户端会继续用 APK 内置的。

用法：
  python make_patch.py 4.0.0.3
  python make_patch.py 4.0.0.3 --src patches/4.0.0.3
"""

import argparse
import hashlib
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WWW = os.path.join(HERE, "www")
DEFAULT_CHANNEL = "Android"   # UC 包 = Android；360 4.2.x 包 = Android_90


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def build(version, src, channel=DEFAULT_CHANNEL):
    src = os.path.abspath(src)
    if not os.path.isdir(src):
        print("补丁源目录不存在: %s" % src)
        print("提示: 把要替换的文件按原路径放进去，例如")
        print("      %s" % os.path.join(src, "Client", "GameRes", "Resources", "xxx.bytes"))
        return 1

    files = []
    for root, _dirs, names in os.walk(src):
        for n in names:
            full = os.path.join(root, n)
            rel = os.path.relpath(full, src).replace(os.sep, "/")
            files.append((rel, full))
    files.sort()
    if not files:
        print("补丁源目录为空: %s" % src)
        return 1

    out_root = os.path.join(WWW, channel, "UpdateRoot", "IncrementPack", version)

    # 1) 拷贝补丁文件
    for rel, full in files:
        dst = os.path.join(out_root, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(full, dst)
    print("已拷贝 %d 个补丁文件 -> %s" % (len(files), out_root))

    # 2) 生成 MD5 清单（固定路径：Client/GameRes/Resources/MD5File.txt.bytes）
    lines = ["<Version>"]
    for rel, full in files:
        lines.append('  <file fpath="%s" size="%d" md5="%s" />'
                     % (rel, os.path.getsize(full), md5_of(full)))
    lines.append("</Version>")
    xml = "\n".join(lines) + "\n"

    md5_path = os.path.join(out_root, "Client", "GameRes", "Resources", "MD5File.txt.bytes")
    os.makedirs(os.path.dirname(md5_path), exist_ok=True)
    with open(md5_path, "w", encoding="utf-8", newline="") as f:
        f.write(xml)
    print("已生成清单 -> %s (%d 条)" % (md5_path, len(files)))

    # 3) 提醒改配置
    cfg_path = os.path.join(HERE, "update_config.json")
    print("-" * 60)
    print("下一步：把 update_config.json 的 server_version 改成 %s，然后重启 update_server.py" % version)
    print("        或者直接 python update_server.py --version %s" % version)
    return 0


def main():
    ap = argparse.ArgumentParser(description="生成梦幻神域热更新补丁")
    ap.add_argument("version", help="要下发的版本号，例如 4.0.0.3")
    ap.add_argument("--src", default=None, help="补丁源目录，默认 patches/<version>")
    ap.add_argument("--channel", default=DEFAULT_CHANNEL,
                    help="渠道路径，默认 Android；360 4.2.x 用 Android_90")
    args = ap.parse_args()
    src = args.src or os.path.join(HERE, "patches", args.version)
    return build(args.version, src, args.channel)


if __name__ == "__main__":
    sys.exit(main())
