#!/usr/bin/env python3
"""裁剪 PNG 并另存（无外部依赖）。
用法: crop_png.py <in.png> <x> <y> <w> <h> <out.png> [scale]
"""
import sys, zlib, struct


def readpng(p):
    d = open(p, 'rb').read(); pos = 8; idat = b''
    while pos < len(d):
        ln = struct.unpack('>I', d[pos:pos+4])[0]
        typ = d[pos+4:pos+8]; data = d[pos+8:pos+8+ln]; pos += 12 + ln
        if typ == b'IHDR':
            w, h, bd, ct = struct.unpack('>IIBB', data[:10])
        elif typ == b'IDAT':
            idat += data
        elif typ == b'IEND':
            break
    raw = zlib.decompress(idat); stride = w * 4
    out = bytearray(); prev = bytearray(stride); i = 0
    for y in range(h):
        f = raw[i]; i += 1
        line = bytearray(raw[i:i+stride]); i += stride
        if f == 1:
            for x in range(4, stride):
                line[x] = (line[x] + line[x-4]) & 255
        elif f == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif f == 3:
            for x in range(stride):
                line[x] = (line[x] + ((line[x-4] if x >= 4 else 0) + prev[x]) // 2) & 255
        elif f == 4:
            for x in range(stride):
                a = line[x-4] if x >= 4 else 0; b = prev[x]; c = prev[x-4] if x >= 4 else 0
                p = a + b - c; pa = abs(p-a); pb = abs(p-b); pc = abs(p-c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[x] = (line[x] + pr) & 255
        out += line; prev = line
    return w, h, bytes(out)


def writepng(p, w, h, px):
    raw = bytearray()
    for y in range(h):
        raw.append(0); raw += px[y*w*4:(y+1)*w*4]
    comp = zlib.compress(bytes(raw), 6)

    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
    png += chunk(b'IDAT', comp)
    png += chunk(b'IEND', b'')
    open(p, 'wb').write(png)


if __name__ == '__main__':
    src, x, y, w, h, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), sys.argv[6]
    sc = int(sys.argv[7]) if len(sys.argv) > 7 else 1
    W, H, px = readpng(src)
    x = max(0, min(x, W-1)); y = max(0, min(y, H-1))
    w = min(w, W-x); h = min(h, H-y)
    buf = bytearray()
    for yy in range(h*sc):
        sy = y + yy//sc
        for xx in range(w*sc):
            sx = x + xx//sc
            o = (sy*W + sx)*4
            buf += px[o:o+4]
    writepng(out, w*sc, h*sc, bytes(buf))
    print("saved", out, w*sc, "x", h*sc, "from", src, (x, y, w, h))
