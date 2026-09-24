# -*- coding: utf-8 -*-
"""从 shot_mine.py 生成的 PNG 里裁剪一块并放大，用于检查细节绘制。"""
import struct
import sys
import zlib


def read_png(path):
    data = open(path, "rb").read()
    pos = 8
    idat = b""
    w = h = None
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        if tag == b"IHDR":
            w, h = struct.unpack(">II", body[:8])
        elif tag == b"IDAT":
            idat += body
        pos += 12 + ln
    raw = zlib.decompress(idat)
    stride = w * 4 + 1
    rows = []
    for y in range(h):
        assert raw[y * stride] == 0, "只支持 filter=0"
        base = y * stride + 1
        rows.append([tuple(raw[base + x * 4:base + x * 4 + 4]) for x in range(w)])
    return w, h, rows


def save_png(path, rows):
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
    open(path, "wb").write(png)


def main():
    src, dst = sys.argv[1], sys.argv[2]
    x0, y0, x1, y1 = (int(v) for v in sys.argv[3:7])
    factor = int(sys.argv[7]) if len(sys.argv) > 7 else 6
    w, h, rows = read_png(src)
    crop = []
    for y in range(max(0, y0), min(h, y1)):
        row = []
        for x in range(max(0, x0), min(w, x1)):
            row.extend([rows[y][x]] * factor)
        for _ in range(factor):
            crop.append(list(row))
    save_png(dst, crop)
    print("裁剪 (%d,%d)-(%d,%d) 放大 %dx -> %s (%dx%d)"
          % (x0, y0, x1, y1, factor, dst, (x1 - x0) * factor, (y1 - y0) * factor))


if __name__ == "__main__":
    main()
