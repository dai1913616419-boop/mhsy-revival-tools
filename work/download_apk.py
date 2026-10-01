"""下载远端 APK（支持断点续传 + 校验）。

用法:
  python download_apk.py <url> <out_path> [expected_size]
仅下载到本地沙箱，不上传、不分发。
"""
import os
import sys
import time
import hashlib
import urllib.request

URL = sys.argv[1] if len(sys.argv) > 1 else "http://andl.guopan.cn/110378-33762-1526495791.apk"
OUT = sys.argv[2] if len(sys.argv) > 2 else r"C:\Users\19136\WorkBuddy\復活工程\work\samples\mhsy_guopan_8.1.0.apk"
EXPECT = int(sys.argv[3]) if len(sys.argv) > 3 else 171674375

HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.xiagai.com/youxi/17659.html",
    "Accept": "*/*",
    "Accept-Encoding": "identity",
    "Connection": "keep-alive",
}

CHUNK = 4 * 1024 * 1024


def get_total():
    req = urllib.request.Request(URL, headers={**HDRS, "Range": "bytes=0-0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        cr = r.headers.get("Content-Range") or ""
        if "/" in cr:
            return int(cr.split("/")[-1])
        return int(r.headers.get("Content-Length", 0))


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    total = EXPECT
    try:
        t = get_total()
        if t:
            total = t
    except Exception as e:
        print("探测总大小失败，使用预设值:", type(e).__name__, e)
    print(f"目标: {URL}")
    print(f"总大小: {total} bytes ({total/1048576:.2f} MiB)")
    print(f"输出: {OUT}")

    have = os.path.getsize(OUT) if os.path.exists(OUT) else 0
    if have == total:
        print("文件已完整，跳过下载")
    else:
        if have > 0:
            print(f"断点续传，已有 {have} bytes")
        f = open(OUT, "r+b" if have else "wb")
        f.seek(have)
        pos = have
        t0 = time.time()
        while pos < total:
            end = min(pos + CHUNK, total) - 1
            ok = False
            for attempt in range(5):
                try:
                    req = urllib.request.Request(
                        URL, headers={**HDRS, "Range": f"bytes={pos}-{end}"})
                    with urllib.request.urlopen(req, timeout=120) as r:
                        data = r.read()
                    if len(data) != (end - pos + 1):
                        raise IOError(f"短读 {len(data)} != {end-pos+1}")
                    f.write(data)
                    f.flush()
                    pos += len(data)
                    ok = True
                    break
                except Exception as e:
                    print(f"  段 {pos}-{end} 第 {attempt+1} 次失败: {type(e).__name__} {e}")
                    time.sleep(2 + attempt * 3)
            if not ok:
                f.close()
                print("下载中止于", pos)
                sys.exit(1)
            pct = pos * 100.0 / total
            el = time.time() - t0
            spd = (pos - have) / 1048576 / el if el > 0 else 0
            print(f"  {pct:6.2f}%  {pos}/{total}  {spd:.2f} MiB/s", end="\r", flush=True)
        f.close()
        print()

    size = os.path.getsize(OUT)
    print(f"\n下载完成: {size} bytes")
    if size != total:
        print("!! 大小不符，可能不完整")
        sys.exit(2)

    h = hashlib.sha256()
    m = hashlib.md5()
    with open(OUT, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
            m.update(c)
    print("SHA256:", h.hexdigest())
    print("MD5   :", m.hexdigest())
    with open(OUT, "rb") as fh:
        print("文件头:", fh.read(8))
    with open(OUT + ".sha256.txt", "w") as fh:
        fh.write(f"{h.hexdigest()}  {os.path.basename(OUT)}\n")
        fh.write(f"size={size}\nmd5={m.hexdigest()}\nurl={URL}\n")


if __name__ == "__main__":
    main()
