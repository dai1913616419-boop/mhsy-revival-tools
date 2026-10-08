#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
梦幻神域 —— 本地更新服务器（离线复活工程）

只做一件事：冒充已经死掉的 game.360joy.com.cn 更新服，
给客户端喂我们自己控制的版本清单和补丁资源。

客户端实际请求的三个 URL（已由 IL 反汇编确认）：
  1) <VersionURL>/Version.bytes
     = http://game.360joy.com.cn/Android/UpdateRoot/Version/Version.bytes
     返回 "版本URL|增量包URL|版本号"，客户端只用第三段做比较
  2) <IncrementURL>/<服务器版本>/Client/GameRes/Resources/MD5File.txt.bytes
     = http://game.360joy.com.cn/Android/UpdateRoot/IncrementPack/4.0.0.3/Client/GameRes/Resources/MD5File.txt.bytes
     返回 XML 清单；客户端只下载「本地没有 或 md5 不同」的条目
  3) <IncrementURL>/<服务器版本>/<fpath>
     清单里列出的每个资源文件

用法：
  python update_server.py                    # 读同目录 update_config.json
  python update_server.py --port 8080
  python update_server.py --version 4.0.0.3  # 强制下发补丁模式

依赖：仅 Python 标准库。
"""

import argparse
import json
import os
import re
import sys
import time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import unquote

HERE = os.path.dirname(os.path.abspath(__file__))

# 渠道前缀是 Android / Android_90 / Android_xx 等多种，不能写死
RE_VERSION = re.compile(r"^/(Android[^/]*)/UpdateRoot/Version/Version\.bytes$", re.I)
RE_INCREMENT = re.compile(r"^/(Android[^/]*)/UpdateRoot/IncrementPack/([^/]+)/(.+)$", re.I)


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    try:
        print(line, flush=True)
    except (OSError, ValueError):
        # Optional detached-console logging must not turn a valid GET into an
        # empty response or suppress the durable request log.
        pass
    try:
        with open(os.path.join(HERE, "logs", "update_server.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


class UpdateHandler(SimpleHTTPRequestHandler):
    """把请求映射到 www/ 目录，并对 Version.bytes 做动态应答。"""

    server_version = "MHLocalUpdate/1.0"
    cfg = {}
    www = ""
    mirror = ""

    # ---------- 工具 ----------
    def _send_bytes(self, data, ctype="application/octet-stream", code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _send_file(self, path, ctype="application/octet-stream"):
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            return False
        self._send_bytes(data, ctype)
        return True

    def _resolve(self, rel):
        """在 www/ 然后 mirror/ 中查找资源，返回绝对路径或 None。"""
        rel = rel.lstrip("/")
        cand = os.path.join(self.www, rel.replace("/", os.sep))
        if os.path.isfile(cand):
            return cand
        if self.mirror and os.path.isdir(self.mirror):
            cand2 = os.path.join(self.mirror, rel.replace("/", os.sep))
            if os.path.isfile(cand2):
                return cand2
        return None

    def _version_for(self, channel):
        """按渠道返回要下发的版本号（各渠道可不同）。"""
        table = self.cfg.get("server_versions") or {}
        if channel in table:
            return str(table[channel])
        ch = (channel or "").lower()
        for k, v in table.items():
            if k.lower() == ch:
                return str(v)
        return str(self.cfg.get("server_version", "4.0.0.2"))

    def _needs_force_field(self, channel):
        """4.2.x 起版本串新增 ForceUpdateAddress 字段（第 6 段）。"""
        ch = (channel or "").lower()
        for k in (self.cfg.get("force_update_channels") or ["android_90"]):
            if str(k).lower() == ch:
                return True
        return False

    # ---------- 路由 ----------
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = unquote(self.path.split("?", 1)[0].split("#", 1)[0])

        if self.cfg.get("log_requests", True):
            log("%s %s  (UA=%s)" % (self.command, path, self.headers.get("User-Agent", "-")))

        # 1) 版本文件：<渠道>/UpdateRoot/Version/Version.bytes
        m = RE_VERSION.match(path)
        if m:
            ch = m.group(1)
            ver = self._version_for(ch)
            host = self.headers.get("Host") or "game.360joy.com.cn"
            base = "http://%s/%s/UpdateRoot" % (host, ch)
            segs = [base + "/Version", base + "/IncrementPack", ver]
            # 4.2.x 客户端的版本串有 6 段（多出 ForceUpdateAddress），按渠道补齐
            if self._needs_force_field(ch):
                segs += ["0", "0",
                         "http://%s/ForceUpdateAddress/%s/AndroidForceUpdateAddress.txt" % (host, ch)]
            body = "|".join(segs)
            log("  -> 下发版本文件 [%s]: %s" % (ch, body))
            self._send_bytes(body.encode("utf-8"), "text/plain")
            return

        # 2) 增量包：<渠道>/UpdateRoot/IncrementPack/<ver>/<fpath>
        m = RE_INCREMENT.match(path)
        if m:
            ch, ver, fpath = m.group(1), m.group(2), m.group(3)
            if ver != self._version_for(ch):
                log("  !! 版本不匹配: 客户端要 %s, 服务器下发 %s" % (ver, self._version_for(ch)))
            hit = self._resolve(path)
            if hit:
                log("  -> 200 %s  (%d bytes)" % (fpath, os.path.getsize(hit)))
                self._send_file(hit)
                return
            log("  -> 404 %s   (www/mirror 均无此文件)" % fpath)
            self._send_bytes(b"not found", "text/plain", 404)
            return

        # 3) 其他：先试静态目录，否则 404（记录未知请求，用于侦察）
        hit = self._resolve(path)
        if hit:
            self._send_file(hit)
            return
        log("  -> 404 未知请求 %s" % path)
        self._send_bytes(b"not found", "text/plain", 404)

    def log_message(self, fmt, *args):
        pass  # 用自己的 log()


def main():
    ap = argparse.ArgumentParser(description="梦幻神域 本地更新服务器")
    ap.add_argument("--config", default=os.path.join(HERE, "update_config.json"))
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--version", default=None, help="覆盖 server_version，例如 4.0.0.3 触发补丁下发")
    ap.add_argument("--www", default=None)
    args = ap.parse_args()

    cfg = {}
    if os.path.isfile(args.config):
        with open(args.config, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    if args.version:
        cfg["server_version"] = args.version

    www = os.path.abspath(os.path.join(HERE, args.www or cfg.get("www_dir", "www")))
    mirror = os.path.abspath(os.path.join(HERE, cfg.get("mirror_dir", "mirror")))
    os.makedirs(www, exist_ok=True)

    host = args.host or cfg.get("listen_host", "0.0.0.0")
    port = args.port or cfg.get("listen_port", 80)

    # 把配置挂到 handler 类上
    UpdateHandler.cfg = cfg
    UpdateHandler.www = www
    UpdateHandler.mirror = mirror if os.path.isdir(mirror) else ""

    srv = ThreadingHTTPServer((host, port), UpdateHandler)
    log("=" * 60)
    log("更新服务器已启动  http://%s:%d/" % (host, port))
    log("  下发版本号 : %s" % (cfg.get("server_versions") or cfg.get("server_version")))
    log("  www 目录   : %s" % www)
    log("  mirror目录 : %s" % (mirror if UpdateHandler.mirror else "(未配置)"))
    log("=" * 60)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("已停止")
        srv.shutdown()


if __name__ == "__main__":
    main()
