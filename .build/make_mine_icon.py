# -*- coding: utf-8 -*-
"""生成扫雷图标：未翻开的格子 + 一颗雷（多尺寸 ico + 预览 png）。

纯标准库实现，全部带 1px 抗锯齿。
"""
import math
import struct
import sys
import zlib

FACE = (0xC0, 0xC0, 0xC0)      # 经典灰
LIGHT = (0xFF, 0xFF, 0xFF)
DARK = (0x80, 0x80, 0x80)
EDGE = (0x60, 0x60, 0x60)
MINE = (0x00, 0x00, 0x00)


def _clamp01(v):
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def _mix(a, b, t):
    t = _clamp01(t)
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _rect_cov(x, y, x0, y0, x1, y1, size):
    """矩形覆盖度；坐标归一化，必须乘 size 换算回像素。"""
    return _clamp01(min(x - x0, x1 - x, y - y0, y1 - y) * size + 0.5)


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def render(size):
    radius = 0.16
    bevel = 0.075                          # 立体边宽度（归一化）
    mx, my, mr = 0.5, 0.52, 0.20           # 雷的位置与半径
    spike = mr + 0.10

    rows = []
    for y in range(size):
        row = []
        cy = (y + 0.5) / size
        for x in range(size):
            cx = (x + 0.5) / size

            # 圆角底板
            dx = max(radius - cx, cx - (1 - radius), 0.0)
            dy = max(radius - cy, cy - (1 - radius), 0.0)
            dist = math.hypot(dx, dy)
            cov = _clamp01((radius - dist) * size + 0.5)
            if cov <= 0.0:
                row.append((0, 0, 0, 0))
                continue

            color = FACE
            # 立体边：左上亮、右下暗，最外圈描边
            if cx < bevel or cy < bevel:
                color = _mix(color, LIGHT, 0.9)
            if cx > 1 - bevel or cy > 1 - bevel:
                color = _mix(color, DARK, 0.95)
            inner = (radius - dist) * size
            if inner < 1.0:
                color = _mix(color, EDGE, 1.0 - inner)

            # 雷的八根尖刺（四条穿过圆心的线）
            for ang in (0.0, math.pi / 4, math.pi / 2, 3 * math.pi / 4):
                ax = mx - math.cos(ang) * spike
                ay = my - math.sin(ang) * spike
                bx = mx + math.cos(ang) * spike
                by = my + math.sin(ang) * spike
                d = _seg_dist(cx, cy, ax, ay, bx, by)
                c = _clamp01((0.028 - d) * size + 0.5)
                if c > 0:
                    color = _mix(color, MINE, c)

            # 雷本体
            d = math.hypot(cx - mx, cy - my)
            body = _clamp01((mr - d) * size + 0.5)
            if body > 0:
                color = _mix(color, MINE, body)
                # 左上高光
                hi = math.hypot(cx - (mx - mr * 0.38), cy - (my - mr * 0.38))
                hc = _clamp01((mr * 0.26 - hi) * size + 0.5)
                if hc > 0:
                    color = _mix(color, (255, 255, 255), hc * body)

            row.append((color[0], color[1], color[2], int(round(cov * 255))))
        rows.append(row)
    return rows


def bmp_entry(rows, size):
    pixels = bytearray()
    for y in range(size - 1, -1, -1):
        for r, g, b, a in rows[y]:
            pixels += bytes((b, g, r, a))
    mask_row = ((size + 31) // 32) * 4
    mask = bytes(mask_row * size)
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0,
                         len(pixels) + len(mask), 0, 0, 0, 0)
    return bytes(header) + bytes(pixels) + mask


def write_ico(path, sizes):
    images = [(s, bmp_entry(render(s), s)) for s in sizes]
    out = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    offset = 6 + 16 * len(images)
    for size, data in images:
        dim = 0 if size >= 256 else size
        out += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    for _, data in images:
        out += data
    with open(path, "wb") as fh:
        fh.write(bytes(out))
    return len(out)


def write_png(path, rows):
    size = len(rows)
    raw = bytearray()
    for row in rows:
        raw.append(0)
        for px in row:
            raw += bytes(px)

    def chunk(tag, payload):
        body = tag + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)


def main():
    ico = sys.argv[1] if len(sys.argv) > 1 else "app.ico"
    png = sys.argv[2] if len(sys.argv) > 2 else None
    sizes = [16, 24, 32, 48, 64, 128, 256]
    total = write_ico(ico, sizes)
    if png:
        write_png(png, render(256))
    print("wrote %s (%d bytes)" % (ico, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
