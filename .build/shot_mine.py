# -*- coding: utf-8 -*-
"""扫雷验证工具：启动程序 -> PrintWindow 抓窗口自身画面 -> 模拟鼠标点击 -> 再抓图。

用 ctypes 直接调 Win32，避免 PowerShell 的编组/BOM 问题。
"""
import ctypes
import struct
import subprocess
import sys
import time
import zlib
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

CLASS_NAME = "CppMinesweeperWnd"
EXE = r"D:\DSH\minesweeper_cpp\build\Minesweeper.exe"
OUT_DIR = r"D:\DSH\.build"


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


user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = [wintypes.HWND]
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]

# 句柄是 64 位指针，必须声明 argtypes，否则 ctypes 会按 int 传参而溢出
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                            ctypes.c_void_p, ctypes.POINTER(BITMAPINFO), wintypes.UINT]
gdi32.GetDIBits.restype = ctypes.c_int
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]

WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202
WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0204, 0x0205
WM_COMMAND = 0x0111
IDM_BEGINNER = 1002
IDM_INTERMEDIATE = 1003
IDM_EXPERT = 1004
IDM_CUSTOM = 1005
IDC_CANCEL = 2005
DLG_CLASS = "CppMinesweeperCustomDlg"


def capture(hwnd):
    """用 PrintWindow 抓窗口自身内容，返回 (宽, 高, 自上而下的 RGBA 行)。"""
    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top

    screen = user32.GetDC(None)
    mem = gdi32.CreateCompatibleDC(screen)
    bmp = gdi32.CreateCompatibleBitmap(screen, w, h)
    old = gdi32.SelectObject(mem, bmp)
    if not user32.PrintWindow(hwnd, mem, 2):     # PW_RENDERFULLCONTENT
        raise RuntimeError("PrintWindow 失败")

    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = w
    info.bmiHeader.biHeight = -h                # 负数 = 自上而下
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = 0            # BI_RGB
    buf = ctypes.create_string_buffer(w * h * 4)
    if not gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(info), 0):
        raise RuntimeError("GetDIBits 失败")

    gdi32.SelectObject(mem, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(None, screen)

    # 注意：ctypes 的 create_string_buffer 按索引取出来的是 bytes（长度 1），
    # 用 memoryview 才能拿到整数。
    mv = memoryview(buf.raw)
    rows = []
    for y in range(h):
        base = y * w * 4
        row = [(mv[base + x * 4 + 2], mv[base + x * 4 + 1], mv[base + x * 4], 255)
               for x in range(w)]
        rows.append(row)
    return w, h, rows


def zoom(rows, factor):
    out = []
    for row in rows:
        big = []
        for px in row:
            big.extend([px] * factor)
        for _ in range(factor):
            out.append(list(big))
    return out


def save_png(path, rows):
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
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 6))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)
    return len(png)


def shot(hwnd, name, factor=3):
    w, h, rows = capture(hwnd)
    if factor > 1:
        rows = zoom(rows, factor)
    size = save_png("%s\\%s" % (OUT_DIR, name), rows)
    print("   截图 %-26s 窗口 %dx%d -> %dx%d  (%d KB)"
          % (name, w, h, w * factor, h * factor, size // 1024))


def click(hwnd, cx, cy, scale, right=False):
    """按 main.cpp 的 Layout() 换算格子中心坐标并发送鼠标消息。"""
    cell = int(22 * scale + 0.5)
    pad = int(6 * scale + 0.5)
    border = int(3 * scale + 0.5)
    panel = int(38 * scale + 0.5)
    gap = int(6 * scale + 0.5)
    x = pad + border + cx * cell + cell // 2
    y = pad + border + panel + gap + cy * cell + cell // 2
    lp = (y << 16) | (x & 0xFFFF)
    if right:
        user32.PostMessageW(hwnd, WM_RBUTTONDOWN, 2, lp)
        user32.PostMessageW(hwnd, WM_RBUTTONUP, 0, lp)
    else:
        user32.PostMessageW(hwnd, WM_LBUTTONDOWN, 1, lp)
        user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp)
    time.sleep(0.05)


def client_size(hwnd):
    rc = RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rc))
    return rc.right, rc.bottom


def main():
    subprocess.run(["taskkill", "/F", "/IM", "Minesweeper.exe"],
                   capture_output=True, check=False)
    time.sleep(0.3)
    proc = subprocess.Popen([EXE])
    hwnd = None
    for _ in range(50):
        time.sleep(0.1)
        hwnd = user32.FindWindowW(CLASS_NAME, None)
        if hwnd:
            break
    if not hwnd:
        print("找不到窗口")
        proc.kill()
        return 1
    print("窗口句柄 = %d" % hwnd)

    cw, ch = client_size(hwnd)
    scale = round(cw / 216.0, 3)             # 初级客户区宽 = 216 * scale
    print("初级客户区 = %dx%d   缩放 = %s" % (cw, ch, scale))
    shot(hwnd, "mine_1_fresh.png", 3)

    print("---- 模拟操作：点开中间（首点安全会展开）、在角落插两面旗 ----")
    click(hwnd, 4, 4, scale)
    click(hwnd, 0, 8, scale)
    time.sleep(0.2)
    click(hwnd, 8, 0, scale, right=True)
    click(hwnd, 8, 1, scale, right=True)
    time.sleep(0.3)
    shot(hwnd, "mine_2_playing.png", 3)

    print("---- 切到中级 16x16 / 40 雷，点开几片 ----")
    user32.PostMessageW(hwnd, WM_COMMAND, IDM_INTERMEDIATE, 0)
    time.sleep(0.6)
    cw, ch = client_size(hwnd)
    scale2 = round(cw / (2.0 * 9 + 16 * 22), 3)
    print("中级客户区 = %dx%d   缩放 = %s" % (cw, ch, scale2))
    for c in ((8, 8), (1, 1), (14, 14)):
        click(hwnd, c[0], c[1], scale2)
    time.sleep(0.3)
    shot(hwnd, "mine_3_intermediate.png", 2)

    print("---- 切到高级 30x16 / 99 雷 ----")
    user32.PostMessageW(hwnd, WM_COMMAND, IDM_EXPERT, 0)
    time.sleep(0.6)
    cw, ch = client_size(hwnd)
    scale3 = round(cw / (2.0 * 9 + 30 * 22), 3)
    print("高级客户区 = %dx%d   缩放 = %s" % (cw, ch, scale3))
    click(hwnd, 15, 8, scale3)
    click(hwnd, 3, 2, scale3)
    time.sleep(0.3)
    shot(hwnd, "mine_4_expert.png", 2)

    print("---- 自定义雷区对话框 ----")
    user32.PostMessageW(hwnd, WM_COMMAND, IDM_CUSTOM, 0)
    time.sleep(0.8)
    dlg = user32.FindWindowW(DLG_CLASS, None)
    if not dlg:
        print("!! 自定义对话框没有出现")
    else:
        shot(dlg, "mine_5_dialog.png", 3)
        user32.PostMessageW(dlg, WM_COMMAND, IDC_CANCEL, 0)
        time.sleep(0.5)
        print("   取消后对话框已关闭 = %s" % (not user32.FindWindowW(DLG_CLASS, None)))

    print("---- 回到初级，连点一片，触发踩雷（看失败画面）----")
    user32.PostMessageW(hwnd, WM_COMMAND, IDM_BEGINNER, 0)
    time.sleep(0.5)
    cw, ch = client_size(hwnd)
    scale = round(cw / 216.0, 3)
    for y in range(0, 9, 2):
        for x in range(0, 9, 2):
            click(hwnd, x, y, scale)
    time.sleep(0.4)
    shot(hwnd, "mine_6_lost.png", 3)

    time.sleep(0.2)
    proc.kill()
    print("已关闭")
    return 0


if __name__ == "__main__":
    sys.exit(main())
