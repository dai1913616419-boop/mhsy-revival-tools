#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""游戏服探针：在指定端口接受 TCP 连接，把收到的原始字节 hexdump 出来。

用途：客户端选服后会直连 IP:Port 发 protobuf 包，先用探针看清第一跳报文，
再据此实现真正的 Python 游戏服。

用法: python probe_tcp.py [--host 0.0.0.0] [--port 9001]
"""
import argparse
import binascii
import os
import socket
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "logs", "tcp_probe.log")


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def hexdump(b, base=0):
    out = []
    for i in range(0, len(b), 16):
        chunk = b[i:i + 16]
        h = binascii.hexlify(chunk).decode()
        h = " ".join(h[j:j + 2] for j in range(0, len(h), 2))
        asc = "".join(chr(c) if 32 <= c < 127 else "." for c in chunk)
        out.append("%08x  %-47s  %s" % (base + i, h, asc))
    return "\n".join(out)


def handle(conn, addr):
    log("连接来自 %s:%d" % addr)
    conn.settimeout(60.0)
    total = 0
    try:
        while True:
            data = conn.recv(8192)
            if not data:
                log("  连接关闭（共 %d 字节）" % total)
                break
            total += len(data)
            log("  收到 %d 字节（累计 %d）:" % (len(data), total))
            for line in hexdump(data).splitlines():
                log("    " + line)
    except socket.timeout:
        log("  空闲超时，关闭（共 %d 字节）" % total)
    except Exception as e:
        log("  异常: %s" % e)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=9001)
    args = ap.parse_args()

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((args.host, args.port))
    s.listen(8)
    log("探针监听 %s:%d，等待客户端连接…" % (args.host, args.port))
    while True:
        conn, addr = s.accept()
        threading.Thread(target=handle, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    main()
