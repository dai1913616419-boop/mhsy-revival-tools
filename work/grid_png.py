#!/usr/bin/env python3
"""裁剪 PNG 并叠加坐标网格，便于人工读取点击坐标。
用法: grid_png.py <in.png> <x> <y> <w> <h> <out.png> [scale] [step]
网格线每 step 像素一条（默认 50），并在左/上边缘标注真实坐标。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crop_png import readpng, writepng

src, x, y, w, h, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), sys.argv[6]
sc = int(sys.argv[7]) if len(sys.argv) > 7 else 1
step = int(sys.argv[8]) if len(sys.argv) > 8 else 50

W, H, px = readpng(src)
x = max(0, min(x, W - 1)); y = max(0, min(y, H - 1))
w = min(w, W - x); h = min(h, H - y)

buf = bytearray()
for yy in range(h * sc):
    sy = y + yy // sc
    for xx in range(w * sc):
        sx = x + xx // sc
        o = (sy * W + sx) * 4
        buf += px[o:o + 4]

# 画网格
def setpx(cx, cy, rgb):
    if 0 <= cx < w * sc and 0 <= cy < h * sc:
        o = (cy * w * sc + cx) * 4
        buf[o] = rgb[0]; buf[o + 1] = rgb[1]; buf[o + 2] = rgb[2]

for gx in range(0, w, step):
    rx = x + gx
    if rx % step:  # 只画真实坐标为 step 整数倍处
        continue
    for yy in range(h * sc):
        setpx(gx * sc, yy, (255, 0, 0) if rx % (step * 2) == 0 else (0, 160, 255))
for gy in range(0, h, step):
    ry = y + gy
    if ry % step:
        continue
    for xx in range(w * sc):
        setpx(xx, gy * sc, (255, 0, 0) if ry % (step * 2) == 0 else (0, 160, 255))

writepng(out, w * sc, h * sc, bytes(buf))
# 打印网格坐标参考
print('crop origin=(%d,%d) size=%dx%d scale=%d step=%d' % (x, y, w, h, sc, step))
xs = [x + gx for gx in range(0, w, step) if (x + gx) % step == 0]
ys = [y + gy for gy in range(0, h, step) if (y + gy) % step == 0]
print('vertical lines (real x, red=even multiples):', xs)
print('horizontal lines (real y):', ys)
