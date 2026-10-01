"""UDP 控制通道客户端（阶段16e 验证用）。
用法: kctl.py <命令> [参数...]   例如:
    kctl.py who
    kctl.py raw 4602 0800
    kctl.py raw 450 0a170805...
    kctl.py mp
"""
import socket
import sys

PORT = 9002


def send(cmd):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(1.0)
    s.sendto(cmd.encode("utf-8"), ("127.0.0.1", PORT))
    print("-> %s" % cmd)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    send(" ".join(sys.argv[1:]))
