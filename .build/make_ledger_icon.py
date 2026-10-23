# -*- coding: utf-8 -*-
"""生成 112账务图标：账本 + 金色「¥」（多尺寸 ico + 预览 png）。

纯标准库实现：蓝色圆角底板、白色账页、红色页眉、金色货币符号，全部 1px 抗锯齿。
"""
import math
import struct
import sys
import zlib

TILE = (0x2f, 0x6f, 0xed)
TILE_EDGE = (0x1f, 0x4f, 0xb0)
PAGE = (0xf9, 0xfb, 0xff)
PAGE_EDGE = (0xd6, 0xde, 0xef)
BAND = (0xe0, 0x5a, 0x6b)
GOLD = (0xf2, 0xc9, 0x4c)

# 「¥」的线段（归一化坐标，画在页面上）
YEN_LINES = [
    ((0.50, 0.40), (0.50, 0.78)),
    ((0.33, 0.40), (0.50, 0.57)),
    ((0.67, 0.40), (0.50, 0.57)),
    ((0.36, 0.60), (0.64, 0.60)),
    ((0.36, 0.69), (0.64, 0.69)),
]
YEN_W = 0.030


def _clamp01(v):
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def _mix(a, b, t):
    t = _clamp01(t)
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _rrect_cov(x, y, x0, y0, x1, y1, r, size):
    """圆角矩形覆盖度；坐标归一化。"""
    cxp, cyp = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    hx, hy = (x1 - x0) / 2.0 - r, (y1 - y0) / 2.0 - r
    dx = abs(x - cxp) - hx
    dy = abs(y - cyp) - hy
    outside = math.hypot(max(dx, 0.0), max(dy, 0.0))
    sd = outside + min(max(dx, dy), 0.0) - r
    return _clamp01(0.5 - sd * size)


def _seg_cov(x, y, a, b, halfw, size):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 <= 1e-12:
        dist = math.hypot(x - ax, y - ay)
    else:
        t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / l2))
        dist = math.hypot(x - (ax + t * dx), y - (ay + t * dy))
    return _clamp01((halfw - dist) * size + 0.5)


def render(size):
    radius = size * 0.20
    rows = []
    for py in range(size):
        row = []
        cy = (py + 0.5) / size
        for px in range(size):
            cx = (px + 0.5) / size

            tile_cov = _rrect_cov(cx, cy, 0.03, 0.03, 0.97, 0.97, 0.17, size)
            if tile_cov <= 0.0:
                row.append((0, 0, 0, 0))
                continue
            color = TILE
            edge = _rrect_cov(cx, cy, 0.03, 0.03, 0.97, 0.97, 0.17, size * 1.0)
            if edge < 0.995:
                pass
            # 描边：靠近边缘时压暗
            inner = _rrect_cov(cx, cy, 0.03 + 0.018, 0.03 + 0.018,
                               0.97 - 0.018, 0.97 - 0.018, 0.155, size)
            if inner < 0.5:
                color = _mix(TILE_EDGE, TILE, inner * 2)

            # 账页
            page_cov = _rrect_cov(cx, cy, 0.20, 0.14, 0.80, 0.86, 0.035, size)
            if page_cov > 0:
                color = _mix(color, PAGE, page_cov)
                pedge = _rrect_cov(cx, cy, 0.20 + 0.010, 0.14 + 0.010,
                                   0.80 - 0.010, 0.86 - 0.010, 0.028, size)
                if pedge < 0.5:
                    color = _mix(color, PAGE_EDGE, (1 - pedge * 2) * page_cov)

            # 页眉色带（上圆下方）
            band_cov = _rrect_cov(cx, cy, 0.20, 0.14, 0.80, 0.34, 0.035, size)
            band_flat = _clamp01(min(cx - 0.20, 0.80 - cx, cy - 0.14, 0.25 - cy) * size + 0.5)
            band = max(band_cov, band_flat)
            if band > 0:
                color = _mix(color, BAND, band)
                b_inner = _rrect_cov(cx, cy, 0.20 + 0.010, 0.14 + 0.010,
                                     0.80 - 0.010, 0.34, 0.025, size)
                if b_inner < 0.5 and band_flat < 0.5:
                    color = _mix(color, _mix(BAND, (0, 0, 0), 0.25), (1 - b_inner * 2))

            # 金色货币符号
            for a, b in YEN_LINES:
                cov = _seg_cov(cx, cy, a, b, YEN_W / 2, size)
                if cov > 0:
                    color = _mix(color, GOLD, cov)

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
    ico = sys.argv[1] if len(sys.argv) > 1 else "ledger_icon.ico"
    png = sys.argv[2] if len(sys.argv) > 2 else None
    sizes = [16, 24, 32, 48, 64, 128, 256]
    total = write_ico(ico, sizes)
    if png:
        write_png(png, render(256))
    print("wrote %s (%d bytes, sizes=%s)" % (ico, total, sizes))
    return 0


if __name__ == "__main__":
    sys.exit(main())