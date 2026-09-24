# -*- coding: utf-8 -*-
"""生成 2048 的启动图标（5 个密度的 PNG）。

设计：深色圆角底 + 2x2 的方块，颜色从奶油色递增到 2048 的金色 —— 一眼就是 2048。
纯标准库实现，带 1px 抗锯齿。
"""
import math
import os
import struct
import sys
import zlib

BG = (0x0D, 0x10, 0x17)
# 2 / 8 / 32 / 2048 的经典配色，按"越来越亮"排列
TILES = [
    [(0xEE, 0xE4, 0xDA), (0xF2, 0xB1, 0x79)],
    [(0xF6, 0x7C, 0x5F), (0xED, 0xC2, 0x2E)],
]
DENSITIES = [
    ("mipmap-mdpi", 48),
    ("mipmap-hdpi", 72),
    ("mipmap-xhdpi", 96),
    ("mipmap-xxhdpi", 144),
    ("mipmap-xxxhdpi", 192),
]


def _clamp01(v):
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def _mix(a, b, t):
    t = _clamp01(t)
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _rounded_cov(x, y, size, left, top, right, bottom, radius):
    """圆角矩形覆盖度（归一化坐标，乘 size 换算回像素）。"""
    cx = min(max(x, left + radius), right - radius)
    cy = min(max(y, top + radius), bottom - radius)
    dx = abs(x - cx) - (right - radius - left - radius) / 2.0
    dy = abs(y - cy) - (bottom - radius - top - radius) / 2.0
    d = math.hypot(max(dx, 0.0), max(dy, 0.0)) + min(max(dx, dy), 0.0)
    return _clamp01((radius - d) * size + 0.5)


def render(size):
    pad = 0.085
    gap = 0.055
    tile = (1.0 - pad * 2 - gap) / 2.0
    radius = tile * 0.22
    rows = []
    for py in range(size):
        row = []
        y = (py + 0.5) / size
        for px in range(size):
            x = (px + 0.5) / size
            color = BG
            alpha = _rounded_cov(x, y, size, 0.0, 0.0, 1.0, 1.0, 0.20)

            for ty in range(2):
                for tx in range(2):
                    left = pad + tx * (tile + gap)
                    top = pad + ty * (tile + gap)
                    cov = _rounded_cov(x, y, size, left, top, left + tile, top + tile, radius)
                    if cov <= 0:
                        continue
                    base = TILES[ty][tx]
                    # 左上高光、右下阴影，做出一点立体感
                    rel_x = (x - left) / tile
                    rel_y = (y - top) / tile
                    t = (rel_x + rel_y) / 2.0
                    shade = _mix(_mix(base, (255, 255, 255), 0.28), base, t)
                    color = _mix(color, shade, cov)
            row.append((color[0], color[1], color[2], int(round(alpha * 255))))
        rows.append(row)
    return rows


def write_png(path, rows):
    h = len(rows)
    w = len(rows[0])
    raw = bytearray()
    for row in rows:
        raw.append(0)
        for px in row:
            raw += bytes(px)

    def chunk(tag, payload):
        body = tag + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)


def main():
    res = sys.argv[1] if len(sys.argv) > 1 else "res"
    preview = sys.argv[2] if len(sys.argv) > 2 else None
    for folder, size in DENSITIES:
        out_dir = os.path.join(res, folder)
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "ic_launcher.png")
        write_png(path, render(size))
        print("  %-22s %d x %d" % (folder, size, size))
    if preview:
        write_png(preview, render(192))
        print("  预览图: %s" % preview)
    return 0


if __name__ == "__main__":
    sys.exit(main())
