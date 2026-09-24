# -*- coding: utf-8 -*-
"""生成三消的启动图标（5 个密度的 PNG）。

设计：深色圆角底 + 四颗不同形状/颜色的宝石（圆、菱形、三角、六边形），
一眼就是"消除类"游戏。纯标准库实现，带 1px 抗锯齿。
"""
import math
import os
import struct
import sys
import zlib

BG = (0x0D, 0x10, 0x17)
GEMS = [
    # (颜色, 形状, 网格列, 网格行)
    ((0xE5, 0x48, 0x4D), "circle", 0, 0),
    ((0xF2, 0xD2, 0x44), "diamond", 1, 0),
    ((0x3F, 0xBF, 0x7F), "triangle", 0, 1),
    ((0x3F, 0x8C, 0xFF), "hexagon", 1, 1),
]
DENSITIES = [
    ("mipmap-mdpi", 48), ("mipmap-hdpi", 72), ("mipmap-xhdpi", 96),
    ("mipmap-xxhdpi", 144), ("mipmap-xxxhdpi", 192),
]


def _clamp01(v):
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def _mix(a, b, t):
    t = _clamp01(t)
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _rounded_bg(x, y, size, radius):
    cx = min(max(x, radius), 1.0 - radius)
    cy = min(max(y, radius), 1.0 - radius)
    dx = abs(x - cx) - (1.0 - 2 * radius) / 2.0
    dy = abs(y - cy) - (1.0 - 2 * radius) / 2.0
    d = math.hypot(max(dx, 0.0), max(dy, 0.0)) + min(max(dx, dy), 0.0)
    return _clamp01((radius - d) * size + 0.5)


def _poly_cov(x, y, cx, cy, r, sides, rotation, size):
    """正多边形覆盖度（按径向距离近似 + 1px 抗锯齿）。"""
    dx, dy = x - cx, y - cy
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        return 1.0
    ang = math.atan2(dy, dx) - rotation
    seg = 2 * math.pi / sides
    folded = (ang % seg) - seg / 2
    edge = r * math.cos(seg / 2) / max(math.cos(folded), 0.15)
    return _clamp01((edge - dist) * size + 0.5)


def render(size):
    radius = 0.20
    pad = 0.135
    cell = (1.0 - pad * 2) / 2.0
    gem_r = cell * 0.40
    rows = []
    for py in range(size):
        row = []
        y = (py + 0.5) / size
        for px in range(size):
            x = (px + 0.5) / size
            alpha = _rounded_bg(x, y, size, radius)
            color = BG
            if alpha > 0:
                # 底色带一点立体感
                color = _mix(BG, (0x22, 0x2A, 0x38), 1.0 - y)
            for base, shape, gx, gy in GEMS:
                cx = pad + cell * (gx + 0.5)
                cy = pad + cell * (gy + 0.5)
                if shape == "circle":
                    cov = _clamp01((gem_r - math.hypot(x - cx, y - cy)) * size + 0.5)
                elif shape == "diamond":
                    cov = _clamp01((gem_r - (abs(x - cx) + abs(y - cy))) * size + 0.5)
                elif shape == "triangle":
                    cov = _poly_cov(x, y, cx, cy, gem_r * 1.15, 3, -math.pi / 2, size)
                else:
                    cov = _poly_cov(x, y, cx, cy, gem_r, 6, 0.0, size)
                if cov <= 0:
                    continue
                hi = _mix(base, (255, 255, 255), 0.35)
                lo = _mix(base, (0, 0, 0), 0.35)
                t = _clamp01((y - (cy - gem_r)) / (2 * gem_r))
                shade = _mix(hi, lo, t)
                color = _mix(color, shade, cov)
            row.append((color[0], color[1], color[2], int(round(alpha * 255))))
        rows.append(row)
    return rows


def write_png(path, rows):
    h, w = len(rows), len(rows[0])
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
        write_png(os.path.join(out_dir, "ic_launcher.png"), render(size))
        print("  %-22s %d x %d" % (folder, size, size))
    if preview:
        write_png(preview, render(192))
    return 0


if __name__ == "__main__":
    sys.exit(main())
