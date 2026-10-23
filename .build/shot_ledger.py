# -*- coding: utf-8 -*-
r"""给 112账务界面截图（用演示数据）。PointWindow 抓窗口自身内容，无需第三方库。

用法：py -X utf8 .build\shot_ledger.py
"""
import ctypes
import os
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                            ctypes.c_void_p, ctypes.POINTER(BITMAPINFO), wintypes.UINT]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]


def find_window(prefix):
    result = []

    def cb(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if buf.value.startswith(prefix):
            result.append(hwnd)
            return False
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return result[0] if result else None


def capture(hwnd):
    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    screen = user32.GetDC(None)
    mem = gdi32.CreateCompatibleDC(screen)
    bmp = gdi32.CreateCompatibleBitmap(screen, w, h)
    old = gdi32.SelectObject(mem, bmp)
    user32.PrintWindow(hwnd, mem, 2)
    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = w
    info.bmiHeader.biHeight = -h
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(info), 0)
    gdi32.SelectObject(mem, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(None, screen)
    mv = memoryview(buf.raw)
    rows = []
    for y in range(h):
        base = y * w * 4
        rows.append([(mv[base + x * 4 + 2], mv[base + x * 4 + 1], mv[base + x * 4], 255)
                     for x in range(w)])
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
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 6))
    png += chunk(b"IEND", b"")
    open(path, "wb").write(png)
    print("   截图 %s  (%dx%d)" % (path, w, h))


def shoot(tab, out_path):
    db = os.path.join(tempfile.gettempdir(), "ledger_shot_%d.db" % tab)
    if os.path.exists(db):
        os.remove(db)
    proc = subprocess.Popen(["py", "-X", "utf8", "ledger_gui.py", "--db", db, "--demo",
                             "--tab", str(tab)], cwd=r"D:\DSH")
    hwnd = None
    for _ in range(80):
        time.sleep(0.25)
        hwnd = find_window("112账务")
        if hwnd:
            break
    if not hwnd:
        print("找不到窗口")
        proc.kill()
        return False
    time.sleep(2.0)
    w, h, rows = capture(hwnd)
    save_png(out_path, rows)
    proc.kill()
    time.sleep(0.4)
    return True


def main():
    root = r"D:\DSH"
    os.makedirs(os.path.join(root, "docs"), exist_ok=True)
    ok = shoot(3, os.path.join(root, "docs", "screenshot-ledger.png"))
    ok = shoot(5, os.path.join(root, "docs", "screenshot-ledger-charts.png")) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())