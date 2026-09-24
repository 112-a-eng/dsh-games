# -*- coding: utf-8 -*-
"""生成俄罗斯方块图标：tetris.ico（含 16~256 多尺寸）+ 预览 PNG。

只用标准库：ICO 内部使用未压缩的 32bpp BMP 条目（兼容性最好），
PNG 用 zlib 手写，便于直接肉眼检查图标效果。
"""
import struct
import sys
import zlib

TILE_BG = (0x12, 0x16, 0x1F)
TILE_EDGE = (0x2A, 0x31, 0x42)
BLOCK = (0xB2, 0x6F, 0xF0)                                   # 游戏里 T 块的紫色
BLOCK_HI = tuple(min(255, int(c * 1.45)) for c in BLOCK)
BLOCK_LO = tuple(int(c * 0.55) for c in BLOCK)

# T 形方块在 3x3 网格中的格子
BLOCKS = ((1, 0), (0, 1), (1, 1), (2, 1))


def _clamp01(v):
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def _mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def render(size):
    """渲染 size×size 的 RGBA 像素，返回按行（自上而下）的列表。"""
    radius = size * 0.20
    pad = size * 0.10
    cell = (size - 2.0 * pad) / 3.0
    gap = max(0.9, size * 0.030)
    bevel = max(1.0, size * 0.045)

    rows = []
    for y in range(size):
        row = []
        cy = y + 0.5
        for x in range(size):
            cx = x + 0.5

            # 圆角矩形的覆盖度（1px 抗锯齿）
            dx = max(radius - cx, cx - (size - radius), 0.0)
            dy = max(radius - cy, cy - (size - radius), 0.0)
            dist = (dx * dx + dy * dy) ** 0.5
            tile_cov = _clamp01(radius - dist + 0.5)
            if tile_cov <= 0.0:
                row.append((0, 0, 0, 0))
                continue

            inward = radius - dist
            if inward < 1.2:                       # 描边
                color = _mix(TILE_BG, TILE_EDGE, _clamp01(1.0 - inward / 1.2))
            else:
                color = TILE_BG

            for gx, gy in BLOCKS:
                x0 = pad + gx * cell + gap / 2.0
                y0 = pad + gy * cell + gap / 2.0
                x1 = pad + (gx + 1) * cell - gap / 2.0
                y1 = pad + (gy + 1) * cell - gap / 2.0
                cover = _clamp01(min(cx - x0, x1 - cx, cy - y0, y1 - cy) + 0.5)
                if cover <= 0.0:
                    continue
                if min(cx - x0, cy - y0) < bevel:                  # 左上高光
                    block = BLOCK_HI
                elif min(x1 - cx, y1 - cy) < bevel * 0.8:           # 右下暗边
                    block = BLOCK_LO
                else:
                    block = BLOCK
                color = _mix(color, block, cover)
                break

            a = int(round(tile_cov * 255))
            row.append((color[0], color[1], color[2], a))
        rows.append(row)
    return rows


def bmp_entry(rows, size):
    pixels = bytearray()
    for y in range(size - 1, -1, -1):              # BMP 自下而上
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
        raw.append(0)                              # filter type 0
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
    ico_path = sys.argv[1] if len(sys.argv) > 1 else "tetris.ico"
    png_path = sys.argv[2] if len(sys.argv) > 2 else None
    sizes = [16, 24, 32, 48, 64, 128, 256]
    total = write_ico(ico_path, sizes)
    if png_path:
        write_png(png_path, render(256))
    print("wrote %s (%d bytes, sizes=%s)" % (ico_path, total, sizes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
