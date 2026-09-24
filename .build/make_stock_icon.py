# -*- coding: utf-8 -*-
"""生成股票游戏图标：K 线 + 趋势线（多尺寸 ico + 预览 png）。

纯标准库实现：圆角底板、三根蜡烛线、金色趋势线，全部带 1px 抗锯齿。
"""
import math
import struct
import sys
import zlib

TILE_BG = (0x12, 0x16, 0x1F)
TILE_EDGE = (0x2A, 0x31, 0x42)
GRID = (0x1E, 0x26, 0x33)
UP = (0xF2, 0x54, 0x5B)          # A 股习惯：红涨
DOWN = (0x3F, 0xBF, 0x7F)        # 绿跌
GOLD = (0xF2, 0xC9, 0x4C)

# 蜡烛： (中心 x, 实体上沿, 实体下沿, 影线上沿, 影线下沿, 是否上涨)
CANDLES = [
    (0.26, 0.60, 0.76, 0.54, 0.82, True),
    (0.50, 0.48, 0.62, 0.42, 0.68, False),
    (0.74, 0.30, 0.46, 0.22, 0.52, True),
]
BODY_W = 0.155
WICK_W = 0.030
TREND = ((0.16, 0.74), (0.84, 0.24))
TREND_W = 0.042


def _clamp01(v):
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def _mix(a, b, t):
    t = _clamp01(t)
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _rect_cov(x, y, x0, y0, x1, y1, size):
    """矩形覆盖度（1px 抗锯齿）；坐标是归一化的，必须乘 size 换算回像素。"""
    return _clamp01(min(x - x0, x1 - x, y - y0, y1 - y) * size + 0.5)


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def render(size):
    radius = size * 0.20
    rows = []
    for y in range(size):
        row = []
        cy = (y + 0.5) / size
        for x in range(size):
            cx = (x + 0.5) / size

            # 圆角底板
            rx = (x + 0.5) - 0.0
            ry = (y + 0.5) - 0.0
            dx = max(radius - rx, rx - (size - radius), 0.0) / size
            dy = max(radius - ry, ry - (size - radius), 0.0) / size
            dist = math.hypot(dx, dy)
            tile_cov = _clamp01((radius / size - dist) * size + 0.5)
            if tile_cov <= 0.0:
                row.append((0, 0, 0, 0))
                continue
            color = TILE_BG
            inward = (radius / size - dist) * size
            if inward < 1.1:
                color = _mix(TILE_BG, TILE_EDGE, 1.0 - inward / 1.1)

            # 背景网格
            for g in (0.28, 0.5, 0.72):
                if abs(cy - g) * size < 0.6 or abs(cx - g) * size < 0.6:
                    color = _mix(color, GRID, 0.85)

            # 趋势线（先画线，蜡烛压在上面）
            line_w = TREND_W / 2
            d = _seg_dist(cx, cy, TREND[0][0], TREND[0][1], TREND[1][0], TREND[1][1])
            cov = _clamp01((line_w - d) * size + 0.5)
            if cov > 0:
                color = _mix(color, GOLD, cov)

            # 蜡烛
            for ccx, top, bottom, wick_top, wick_bottom, up in CANDLES:
                half = WICK_W / 2
                if abs(cx - ccx) <= half and wick_top <= cy <= wick_bottom:
                    color = _mix(color, UP if up else DOWN, 0.95)
                half = BODY_W / 2
                body = _rect_cov(cx, cy, ccx - half, top, ccx + half, bottom, size)
                if body > 0:
                    base = UP if up else DOWN
                    shade = _mix(base, (255, 255, 255), 0.0)
                    color = _mix(color, shade, body)

            a = int(round(tile_cov * 255))
            row.append((color[0], color[1], color[2], a))
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
    ico = sys.argv[1] if len(sys.argv) > 1 else "stock_icon.ico"
    png = sys.argv[2] if len(sys.argv) > 2 else None
    sizes = [16, 24, 32, 48, 64, 128, 256]
    total = write_ico(ico, sizes)
    if png:
        write_png(png, render(256))
    print("wrote %s (%d bytes)" % (ico, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
