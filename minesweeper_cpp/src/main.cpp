// 扫雷 · Win32 / GDI 实现
//   * 纯 Win32 API + GDI，无第三方库，静态链接 CRT（/MT），单文件 exe 可直接分发
//   * 双缓冲绘制，无闪烁；7 段数码管、笑脸按钮、3D 立体格子全部用 GDI 手绘
//   * 支持鼠标（左键翻开 / 右键插旗 / 双键和弦）与键盘（方向键 + 空格 + F）
//   * 成绩存入注册表 HKCU\Software\CppMinesweeper
#define WINVER 0x0A00
#define _WIN32_WINNT 0x0A00
#define WIN32_LEAN_AND_MEAN

#include <windows.h>
#include <windowsx.h>

#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <random>
#include <string>
#include <vector>

#include "game.h"

using sweeper::Board;
using sweeper::Cell;
using sweeper::Config;
using sweeper::Status;
using sweeper::FLAGGED;
using sweeper::HIDDEN;
using sweeper::QUESTION;
using sweeper::REVEALED;

// ---------------------------------------------------------------- 常量
namespace {

const wchar_t* kClassName = L"CppMinesweeperWnd";
const wchar_t* kDlgClass = L"CppMinesweeperCustomDlg";
const wchar_t* kRegPath = L"Software\\CppMinesweeper";
const wchar_t* kAppTitle = L"扫雷 · C++ / Win32";

// 经典配色
const COLORREF kFace = RGB(192, 192, 192);
const COLORREF kLight = RGB(255, 255, 255);
const COLORREF kDark = RGB(128, 128, 128);
const COLORREF kDarker = RGB(96, 96, 96);
const COLORREF kGridLine = RGB(160, 160, 160);
const COLORREF kLedBg = RGB(0, 0, 0);
const COLORREF kLedOn = RGB(255, 0, 0);
const COLORREF kLedOff = RGB(48, 0, 0);
const COLORREF kRed = RGB(255, 0, 0);
const COLORREF kYellow = RGB(255, 220, 60);

const COLORREF kNumber[9] = {
    RGB(0, 0, 0), RGB(0, 0, 255), RGB(0, 128, 0), RGB(255, 0, 0),
    RGB(0, 0, 128), RGB(128, 0, 0), RGB(0, 128, 128), RGB(0, 0, 0),
    RGB(128, 128, 128),
};

// 菜单 / 命令
enum : UINT {
    IDM_NEW = 1001,
    IDM_BEGINNER, IDM_INTERMEDIATE, IDM_EXPERT, IDM_CUSTOM,
    IDM_SAFE_FIRST, IDM_QUESTION, IDM_BEST, IDM_EXIT,
    IDM_HOWTO, IDM_ABOUT,
    IDC_EDIT_W = 2001, IDC_EDIT_H, IDC_EDIT_M, IDC_OK, IDC_CANCEL,
    IDT_CLOCK = 1,
};

// 布局（逻辑像素，实际会乘以 DPI 缩放）
const int kCellLogical = 22;
const int kPadLogical = 6;
const int kBorderLogical = 3;
const int kPanelLogical = 38;
const int kGapLogical = 6;
const int kDigitWLogical = 13;
const int kDigitHLogical = 23;
const int kSmileyLogical = 26;

struct App {
    HWND hwnd = nullptr;
    Board board;
    Config cfg = sweeper::presetBeginner();
    uint32_t seed = 0;

    double scale = 1.0;
    int cell = kCellLogical;
    int pad = kPadLogical;
    int border = kBorderLogical;
    int panelH = kPanelLogical;
    int gap = kGapLogical;

    RECT field{}, panel{}, grid{}, smiley{}, mineLed{}, timeLed{};
    int mineDigits[3] = {0, 0, 0};
    int timeDigits[3] = {0, 0, 0};

    ULONGLONG startTick = 0;
    int elapsed = 0;

    bool leftDown = false, rightDown = false;
    int leftCell = -1, rightCell = -1;
    bool smileyDown = false;
    bool cursorOn = false;
    int cursorX = 0, cursorY = 0;

    HDC memDc = nullptr;
    HBITMAP memBmp = nullptr;
    int memW = 0, memH = 0;
    HFONT fontNum = nullptr, fontUi = nullptr;

    int best[3] = {0, 0, 0};      // 初级 / 中级 / 高级 最佳用时（秒），0 表示无
    HMENU gameMenu = nullptr;     // “游戏”子菜单，用于勾选状态
};

App g;

int S(int v) { return (int)(v * g.scale + 0.5); }

std::wstring Format(const wchar_t* fmt, ...) {
    wchar_t buf[512];
    va_list args;
    va_start(args, fmt);
    _vsnwprintf_s(buf, _TRUNCATE, fmt, args);
    va_end(args);
    return std::wstring(buf);
}

// ---------------------------------------------------------------- 绘制工具
void FillRectColor(HDC dc, const RECT& r, COLORREF color) {
    HBRUSH brush = CreateSolidBrush(color);
    FillRect(dc, &r, brush);
    DeleteObject(brush);
}

// 经典 3D 边框：raised = true 凸起，false 凹陷
void DrawBevel(HDC dc, const RECT& r, bool raised, int t) {
    RECT a = r;
    // 上/左
    RECT top = {a.left, a.top, a.right, a.top + t};
    RECT left = {a.left, a.top, a.left + t, a.bottom};
    // 下/右
    RECT bottom = {a.left, a.bottom - t, a.right, a.bottom};
    RECT right = {a.right - t, a.top, a.right, a.bottom};
    FillRectColor(dc, top, raised ? kLight : kDark);
    FillRectColor(dc, left, raised ? kLight : kDark);
    FillRectColor(dc, bottom, raised ? kDark : kLight);
    FillRectColor(dc, right, raised ? kDark : kLight);
}

// 7 段数码管
void DrawDigit(HDC dc, int digit, const RECT& r, bool on) {
    // 段位：a=上 b=右上 c=右下 d=下 e=左下 f=左上 g=中
    static const unsigned char kSeg[10] = {
        0b0111111,  // 0: a b c d e f
        0b0000110,  // 1: b c
        0b1011011,  // 2: a b d e g
        0b1001111,  // 3: a b c d g
        0b1100110,  // 4: b c f g
        0b1101101,  // 5: a c d f g
        0b1111101,  // 6: a c d e f g
        0b0000111,  // 7: a b c
        0b1111111,  // 8: 全亮
        0b1101111,  // 9: a b c d f g
    };
    const int w = r.right - r.left;
    const int t = (w + 5) / 6;                 // 段宽
    const int hx = r.left + t / 2;
    const int hy = r.top + t / 2;
    const int hx2 = r.right - t / 2;
    const int hy2 = r.bottom - t / 2;
    const int midY = (r.top + r.bottom) / 2;

    RECT segs[7];
    segs[0] = {hx, r.top, hx2, r.top + t};                                  // a
    segs[1] = {r.right - t, hy, r.right, midY - t / 2};                     // b
    segs[2] = {r.right - t, midY + t / 2, r.right, hy2};                    // c
    segs[3] = {hx, r.bottom - t, hx2, r.bottom};                            // d
    segs[4] = {r.left, midY + t / 2, r.left + t, hy2};                       // e
    segs[5] = {r.left, hy, r.left + t, midY - t / 2};                        // f
    segs[6] = {hx, midY - t / 2, hx2, midY + t / 2};                        // g

    unsigned char mask = 0;
    if (digit == -1) mask = (1u << 6);          // 负号：只亮中间那一段
    else if (digit >= 0 && digit <= 9) mask = kSeg[digit];
    for (int i = 0; i < 7; ++i) {
        const bool lit = on && (mask & (1u << i));
        FillRectColor(dc, segs[i], lit ? kLedOn : kLedOff);
    }
}

// 笑脸按钮
void DrawSmiley(HDC dc, const RECT& r, int face) {
    FillRectColor(dc, r, kFace);
    DrawBevel(dc, r, true, S(2));

    RECT inner = {r.left + S(3), r.top + S(3), r.right - S(3), r.bottom - S(3)};
    HBRUSH yellow = CreateSolidBrush(kYellow);
    HBRUSH oldBrush = (HBRUSH)SelectObject(dc, yellow);
    HPEN pen = CreatePen(PS_SOLID, S(1), RGB(0, 0, 0));
    HPEN oldPen = (HPEN)SelectObject(dc, pen);
    Ellipse(dc, inner.left, inner.top, inner.right, inner.bottom);
    SelectObject(dc, oldBrush);
    SelectObject(dc, oldPen);
    DeleteObject(yellow);
    DeleteObject(pen);

    const int cx = (inner.left + inner.right) / 2;
    const int cy = (inner.top + inner.bottom) / 2;
    // 尺寸很小，用实心方块画眼睛、用折线画嘴，比 Arc/Ellipse 可控得多
    const int eyeOff = max(2, S(4));
    const int eyeW = max(1, S(1));                     // 眼睛约 3px 见方，和经典扫雷一致
    const int eyeTop = cy - S(4);
    const int mouthW = max(3, S(5));
    const int mouthH = max(1, S(2));

    HBRUSH black = CreateSolidBrush(RGB(0, 0, 0));
    HGDIOBJ ob = SelectObject(dc, black);
    HGDIOBJ op = SelectObject(dc, GetStockObject(NULL_PEN));

    if (face == 3) {                                   // 胜利：墨镜横带
        RECT glasses = {cx - eyeOff - eyeW, eyeTop - eyeW, cx + eyeOff + eyeW, eyeTop + eyeW + 1};
        FillRectColor(dc, glasses, RGB(0, 0, 0));
    } else if (face == 2) {                            // 失败：X 眼
        HPEN xp = CreatePen(PS_SOLID, max(1, S(1)) + 1, RGB(0, 0, 0));
        SelectObject(dc, xp);
        for (int s = -1; s <= 1; s += 2) {
            const int ex = cx + s * eyeOff;
            MoveToEx(dc, ex - eyeW, eyeTop - eyeW, nullptr);
            LineTo(dc, ex + eyeW + 1, eyeTop + eyeW + 1);
            MoveToEx(dc, ex + eyeW, eyeTop - eyeW, nullptr);
            LineTo(dc, ex - eyeW - 1, eyeTop + eyeW + 1);
        }
        SelectObject(dc, GetStockObject(NULL_PEN));
        DeleteObject(xp);
    } else {                                           // 正常 / 按下：两只眼睛
        RECT e1 = {cx - eyeOff - eyeW, eyeTop - eyeW, cx - eyeOff + eyeW + 1, eyeTop + eyeW + 1};
        RECT e2 = {cx + eyeOff - eyeW, eyeTop - eyeW, cx + eyeOff + eyeW + 1, eyeTop + eyeW + 1};
        FillRectColor(dc, e1, RGB(0, 0, 0));
        FillRectColor(dc, e2, RGB(0, 0, 0));
    }

    // 嘴：折线画弧（dy=+1 微笑 ⌣，dy=-1 皱眉 ⌢）
    HPEN mp = CreatePen(PS_SOLID, max(1, S(1)) + 1, RGB(0, 0, 0));
    SelectObject(dc, mp);
    SelectObject(dc, GetStockObject(NULL_BRUSH));
    if (face == 1) {                                   // 按下：小圆嘴
        HBRUSH oldB = (HBRUSH)SelectObject(dc, GetStockObject(NULL_BRUSH));
        Ellipse(dc, cx - S(2), cy + S(1), cx + S(2) + 1, cy + S(5) + 1);
        SelectObject(dc, oldB);
    } else {
        const int dy = (face == 2) ? -1 : 1;
        const int baseY = cy + S(2);
        POINT pts[5] = {
            {cx - mouthW, baseY},
            {cx - mouthW / 2, baseY + dy * mouthH / 2},
            {cx, baseY + dy * mouthH},
            {cx + mouthW / 2, baseY + dy * mouthH / 2},
            {cx + mouthW, baseY},
        };
        Polyline(dc, pts, 5);
    }
    SelectObject(dc, ob);
    SelectObject(dc, op);
    DeleteObject(black);
    DeleteObject(mp);
}

// 一颗雷
void DrawMine(HDC dc, const RECT& r) {
    const int cx = (r.left + r.right) / 2;
    const int cy = (r.top + r.bottom) / 2;
    const int rad = (r.right - r.left) / 2 - S(4);
    if (rad < 2) return;

    HPEN pen = CreatePen(PS_SOLID, S(2), RGB(0, 0, 0));
    HPEN oldPen = (HPEN)SelectObject(dc, pen);
    const int spike = rad + S(3);
    MoveToEx(dc, cx - spike, cy, nullptr); LineTo(dc, cx + spike + 1, cy);
    MoveToEx(dc, cx, cy - spike, nullptr); LineTo(dc, cx, cy + spike + 1);
    SelectObject(dc, oldPen);
    DeleteObject(pen);

    HBRUSH black = CreateSolidBrush(RGB(0, 0, 0));
    HBRUSH oldBrush = (HBRUSH)SelectObject(dc, black);
    HPEN nullPen = (HPEN)GetStockObject(NULL_PEN);
    oldPen = (HPEN)SelectObject(dc, nullPen);
    Ellipse(dc, cx - rad, cy - rad, cx + rad + 1, cy + rad + 1);
    SelectObject(dc, oldBrush);
    SelectObject(dc, oldPen);
    DeleteObject(black);

    RECT hi = {cx - rad / 2, cy - rad / 2, cx - rad / 4, cy - rad / 4};
    FillRectColor(dc, hi, RGB(255, 255, 255));
}

// 一面旗
void DrawFlag(HDC dc, const RECT& r) {
    const int cx = (r.left + r.right) / 2;
    const int top = r.top + S(4);
    const int bottom = r.bottom - S(5);
    const int flagW = (r.right - r.left) / 3;

    HPEN pen = CreatePen(PS_SOLID, S(2), RGB(0, 0, 0));
    HPEN oldPen = (HPEN)SelectObject(dc, pen);
    MoveToEx(dc, cx, top, nullptr);
    LineTo(dc, cx, bottom + S(1));
    SelectObject(dc, oldPen);
    DeleteObject(pen);

    POINT tri[3] = {{cx, top}, {cx + flagW, top + flagW / 2 + S(1)}, {cx, top + flagW + S(2)}};
    HBRUSH red = CreateSolidBrush(kRed);
    HBRUSH oldBrush = (HBRUSH)SelectObject(dc, red);
    Polygon(dc, tri, 3);
    SelectObject(dc, oldBrush);
    DeleteObject(red);

    RECT base = {cx - flagW, bottom, cx + flagW + S(1), bottom + S(3)};
    FillRectColor(dc, base, RGB(0, 0, 0));
}

// ---------------------------------------------------------------- 布局
void Layout(bool resizeWindow) {
    const int cols = g.board.cols();
    const int rows = g.board.rows();
    g.cell = S(kCellLogical);
    g.pad = S(kPadLogical);
    g.border = S(kBorderLogical);
    g.panelH = S(kPanelLogical);
    g.gap = S(kGapLogical);

    const int gridW = cols * g.cell;
    const int gridH = rows * g.cell;
    const int fieldW = g.border * 2 + gridW;
    const int fieldH = g.border * 2 + g.panelH + g.gap + gridH;

    g.field = {g.pad, g.pad, g.pad + fieldW, g.pad + fieldH};

    const int innerL = g.field.left + g.border;
    const int innerT = g.field.top + g.border;
    const int innerR = g.field.right - g.border;
    g.panel = {innerL, innerT, innerR, innerT + g.panelH};
    g.grid = {innerL, g.panel.bottom + g.gap, innerL + gridW, g.panel.bottom + g.gap + gridH};

    const int ledW = 3 * S(kDigitWLogical) + S(4);
    const int ledH = S(kDigitHLogical) + S(4);
    const int ledY = g.panel.top + (g.panelH - ledH) / 2;
    g.mineLed = {g.panel.left + S(6), ledY, g.panel.left + S(6) + ledW, ledY + ledH};
    g.timeLed = {g.panel.right - S(6) - ledW, ledY, g.panel.right - S(6), ledY + ledH};

    const int sm = S(kSmileyLogical);
    g.smiley = {(g.panel.left + g.panel.right) / 2 - sm / 2, g.panel.top + (g.panelH - sm) / 2,
                (g.panel.left + g.panel.right) / 2 - sm / 2 + sm,
                g.panel.top + (g.panelH - sm) / 2 + sm};

    if (resizeWindow && g.hwnd) {
        RECT want = {0, 0, g.field.right + g.pad, g.field.bottom + g.pad};
        AdjustWindowRectEx(&want, (DWORD)GetWindowLongPtrW(g.hwnd, GWL_STYLE), TRUE,
                           (DWORD)GetWindowLongPtrW(g.hwnd, GWL_EXSTYLE));
        SetWindowPos(g.hwnd, nullptr, 0, 0, want.right - want.left, want.bottom - want.top,
                     SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE);
    }
}

bool CellFromPoint(POINT p, int& cx, int& cy) {
    if (!PtInRect(&g.grid, p)) return false;
    cx = (p.x - g.grid.left) / g.cell;
    cy = (p.y - g.grid.top) / g.cell;
    return cx >= 0 && cy >= 0 && cx < g.board.cols() && cy < g.board.rows();
}

RECT CellRect(int x, int y) {
    return {g.grid.left + x * g.cell, g.grid.top + y * g.cell,
            g.grid.left + (x + 1) * g.cell, g.grid.top + (y + 1) * g.cell};
}

// ---------------------------------------------------------------- 状态
void UpdateDigits() {
    int mines = g.board.minesRemaining();
    g.mineDigits[0] = mines < 0 ? -1 : (mines / 100) % 10;
    g.mineDigits[1] = mines < 0 ? -1 : (mines / 10) % 10;
    g.mineDigits[2] = mines < 0 ? -1 : 0;      // 占位，见下方重算
    // 逐位拆分（负数显示为 -01 ~ -99）
    const int v = mines;
    if (v < 0) {
        g.mineDigits[0] = -1;                  // 负号占第一段
        g.mineDigits[1] = (-v / 10) % 10;
        g.mineDigits[2] = (-v) % 10;
    } else {
        g.mineDigits[0] = (v / 100) % 10;
        g.mineDigits[1] = (v / 10) % 10;
        g.mineDigits[2] = v % 10;
        if (v > 999) { g.mineDigits[0] = 9; g.mineDigits[1] = 9; g.mineDigits[2] = 9; }
    }

    int t = g.elapsed;
    if (t > 999) t = 999;
    g.timeDigits[0] = (t / 100) % 10;
    g.timeDigits[1] = (t / 10) % 10;
    g.timeDigits[2] = t % 10;
}

void StartClock() {
    if (g.board.status() == Status::Playing && g.startTick == 0) {
        g.startTick = GetTickCount64();
        g.elapsed = 0;
    }
}

void TickClock() {
    if (g.board.status() == Status::Playing && g.startTick != 0) {
        g.elapsed = (int)((GetTickCount64() - g.startTick) / 1000);
    }
}

int FaceState() {
    if (g.board.status() == Status::Lost) return 2;
    if (g.board.status() == Status::Won) return 3;
    if (g.smileyDown || g.leftDown || g.rightDown) return 1;
    return 0;
}

// ---------------------------------------------------------------- 注册表成绩
void LoadBest() {
    HKEY key = nullptr;
    if (RegOpenKeyExW(HKEY_CURRENT_USER, kRegPath, 0, KEY_READ, &key) != ERROR_SUCCESS) return;
    const wchar_t* names[3] = {L"beginner", L"intermediate", L"expert"};
    for (int i = 0; i < 3; ++i) {
        DWORD value = 0, size = sizeof(DWORD), type = 0;
        if (RegQueryValueExW(key, names[i], nullptr, &type, (LPBYTE)&value, &size) ==
                ERROR_SUCCESS && type == REG_DWORD) {
            g.best[i] = (int)value;
        }
    }
    RegCloseKey(key);
}

void SaveBest(int level, int seconds) {
    if (level < 0 || level > 2) return;
    if (g.best[level] != 0 && g.best[level] <= seconds) return;
    g.best[level] = seconds;
    HKEY key = nullptr;
    if (RegCreateKeyExW(HKEY_CURRENT_USER, kRegPath, 0, nullptr, 0, KEY_WRITE, nullptr, &key,
                        nullptr) != ERROR_SUCCESS) {
        return;
    }
    const wchar_t* names[3] = {L"beginner", L"intermediate", L"expert"};
    DWORD value = (DWORD)seconds;
    RegSetValueExW(key, names[level], 0, REG_DWORD, (const BYTE*)&value, sizeof(value));
    RegCloseKey(key);
}

int PresetLevelOf(const Config& c) {
    const Config b = sweeper::presetBeginner();
    const Config i = sweeper::presetIntermediate();
    const Config e = sweeper::presetExpert();
    if (c.cols == b.cols && c.rows == b.rows && c.mines == b.mines) return 0;
    if (c.cols == i.cols && c.rows == i.rows && c.mines == i.mines) return 1;
    if (c.cols == e.cols && c.rows == e.rows && c.mines == e.mines) return 2;
    return -1;
}

// ---------------------------------------------------------------- 游戏流程
void NewGame(HWND hwnd, const Config& cfg, uint32_t seed) {
    g.cfg = cfg;
    g.seed = seed;
    g.board.reset(cfg, seed);
    g.startTick = 0;
    g.elapsed = 0;
    g.leftDown = g.rightDown = false;
    g.leftCell = g.rightCell = -1;
    g.smileyDown = false;
    g.cursorOn = false;
    Layout(true);
    UpdateDigits();
    InvalidateRect(hwnd, nullptr, FALSE);
}

void CheckRecord(HWND hwnd) {
    if (g.board.status() != Status::Won) return;
    const int level = PresetLevelOf(g.cfg);
    if (level < 0) return;
    const bool record = (g.best[level] == 0 || g.elapsed < g.best[level]);
    SaveBest(level, g.elapsed);
    if (record && g.elapsed > 0) {
        const wchar_t* names[3] = {L"初级", L"中级", L"高级"};
        MessageBoxW(hwnd,
                    Format(L"恭喜！%s新纪录：%d 秒", names[level], g.elapsed).c_str(),
                    L"新纪录", MB_OK | MB_ICONINFORMATION);
    }
}

void DoReveal(HWND hwnd, int x, int y) {
    if (g.board.reveal(x, y)) {
        StartClock();
        if (g.board.finished()) {
            TickClock();
            CheckRecord(hwnd);
        }
        UpdateDigits();
        InvalidateRect(hwnd, &g.panel, FALSE);
        InvalidateRect(hwnd, &g.grid, FALSE);
    }
}

void DoFlag(HWND hwnd, int x, int y) {
    if (g.board.toggleFlag(x, y)) {
        UpdateDigits();
        InvalidateRect(hwnd, &g.panel, FALSE);
        InvalidateRect(hwnd, &g.grid, FALSE);
    }
}

void DoChord(HWND hwnd, int x, int y) {
    if (g.board.chord(x, y)) {
        if (g.board.finished()) {
            TickClock();
            CheckRecord(hwnd);
        }
        UpdateDigits();
        InvalidateRect(hwnd, &g.panel, FALSE);
        InvalidateRect(hwnd, &g.grid, FALSE);
    }
}

// ---------------------------------------------------------------- 自定义对话框
struct CustomState {
    HWND hwnd = nullptr;
    HWND editW = nullptr, editH = nullptr, editM = nullptr, label = nullptr;
    bool ok = false;
    Config config;
};
CustomState g_dlg;

void DlgSyncEdits() {
    HWND focus = GetFocus();
    wchar_t buf[16];
    int w = 9, h = 9, m = 10;
    GetWindowTextW(g_dlg.editW, buf, 16); w = _wtoi(buf);
    GetWindowTextW(g_dlg.editH, buf, 16); h = _wtoi(buf);
    GetWindowTextW(g_dlg.editM, buf, 16); m = _wtoi(buf);
    const int maxMines = (w > 1 && h > 1) ? w * h - 9 : 1;
    const bool bad = (w < 5 || w > 50 || h < 5 || h > 30 || m < 1 || m > maxMines);
    EnableWindow(GetDlgItem(g_dlg.hwnd, IDC_OK), !bad);
    SetWindowTextW(g_dlg.label,
                   bad ? L"宽度 5-50，高度 5-30，雷数 1 ~ 宽×高-9"
                       : Format(L"雷数上限 %d", maxMines).c_str());
    (void)focus;
}

LRESULT CALLBACK CustomDlgProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
        case WM_CREATE: {
            HINSTANCE hi = (HINSTANCE)GetWindowLongPtrW(hwnd, GWLP_HINSTANCE);
            const int ew = 60, eh = 24, gapY = 34;
            struct Row { const wchar_t* text; int id; };
            const Row rows[3] = {{L"宽度（列）", IDC_EDIT_W}, {L"高度（行）", IDC_EDIT_H},
                                 {L"雷数", IDC_EDIT_M}};
            for (int i = 0; i < 3; ++i) {
                CreateWindowExW(0, L"STATIC", rows[i].text, WS_CHILD | WS_VISIBLE,
                                18, 18 + i * gapY, 84, 20, hwnd, nullptr, hi, nullptr);
                HWND edit = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"",
                                            WS_CHILD | WS_VISIBLE | WS_TABSTOP | ES_NUMBER,
                                            108, 15 + i * gapY, ew, eh, hwnd,
                                            (HMENU)(INT_PTR)rows[i].id, hi, nullptr);
                if (i == 0) g_dlg.editW = edit;
                if (i == 1) g_dlg.editH = edit;
                if (i == 2) g_dlg.editM = edit;
            }
            g_dlg.label = CreateWindowExW(0, L"STATIC", L"", WS_CHILD | WS_VISIBLE,
                                          18, 18 + 3 * gapY + 2, 200, 20, hwnd, nullptr, hi,
                                          nullptr);
            CreateWindowExW(0, L"BUTTON", L"确定",
                            WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_DEFPUSHBUTTON, 40,
                            18 + 3 * gapY + 30, 84, 28, hwnd, (HMENU)IDC_OK, hi, nullptr);
            CreateWindowExW(0, L"BUTTON", L"取消", WS_CHILD | WS_VISIBLE | WS_TABSTOP,
                            140, 18 + 3 * gapY + 30, 84, 28, hwnd, (HMENU)IDC_CANCEL, hi,
                            nullptr);
            return 0;
        }
        case WM_COMMAND: {
            const int id = LOWORD(wp);
            if (id == IDC_OK) {
                wchar_t buf[16];
                GetWindowTextW(g_dlg.editW, buf, 16); const int w = _wtoi(buf);
                GetWindowTextW(g_dlg.editH, buf, 16); const int h = _wtoi(buf);
                GetWindowTextW(g_dlg.editM, buf, 16); const int m = _wtoi(buf);
                g_dlg.config = sweeper::customConfig(w, h, m);
                g_dlg.ok = true;
                DestroyWindow(hwnd);
            } else if (id == IDC_CANCEL || id == IDCANCEL) {
                DestroyWindow(hwnd);
            } else if (HIWORD(wp) == EN_CHANGE && (id == IDC_EDIT_W || id == IDC_EDIT_H ||
                                                   id == IDC_EDIT_M)) {
                DlgSyncEdits();
            }
            return 0;
        }
        case WM_CLOSE:
            DestroyWindow(hwnd);
            return 0;
        case WM_DESTROY:
            g_dlg.hwnd = nullptr;
            return 0;
        default:
            break;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}

bool ShowCustomDialog(HWND owner, Config& io) {
    static bool registered = false;
    HINSTANCE hi = (HINSTANCE)GetWindowLongPtrW(owner, GWLP_HINSTANCE);
    if (!registered) {
        WNDCLASSEXW wc{};
        wc.cbSize = sizeof(wc);
        wc.lpfnWndProc = CustomDlgProc;
        wc.hInstance = hi;
        wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
        wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
        wc.lpszClassName = kDlgClass;
        RegisterClassExW(&wc);
        registered = true;
    }
    g_dlg = CustomState();
    g_dlg.config = io;
    g_dlg.hwnd = CreateWindowExW(WS_EX_DLGMODALFRAME | WS_EX_CONTROLPARENT, kDlgClass,
                                 L"自定义雷区", WS_POPUPWINDOW | WS_CAPTION | WS_VISIBLE,
                                 CW_USEDEFAULT, CW_USEDEFAULT, 288, 18 * 2 + 3 * 34 + 30 + 66,
                                 owner, nullptr, hi, nullptr);
    if (!g_dlg.hwnd) return false;

    SetWindowTextW(g_dlg.editW, Format(L"%d", io.cols).c_str());
    SetWindowTextW(g_dlg.editH, Format(L"%d", io.rows).c_str());
    SetWindowTextW(g_dlg.editM, Format(L"%d", io.mines).c_str());
    DlgSyncEdits();

    RECT rc, ro;
    GetWindowRect(g_dlg.hwnd, &rc);
    GetWindowRect(owner, &ro);
    SetWindowPos(g_dlg.hwnd, nullptr, ro.left + ((ro.right - ro.left) - (rc.right - rc.left)) / 2,
                 ro.top + ((ro.bottom - ro.top) - (rc.bottom - rc.top)) / 2, 0, 0,
                 SWP_NOSIZE | SWP_NOZORDER);
    SetFocus(g_dlg.editW);
    EnableWindow(owner, FALSE);

    MSG msg;
    while (g_dlg.hwnd && GetMessageW(&msg, nullptr, 0, 0)) {
        if (!IsDialogMessageW(g_dlg.hwnd, &msg)) {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
    }
    EnableWindow(owner, TRUE);
    SetForegroundWindow(owner);
    if (g_dlg.ok) {
        io = g_dlg.config;
        return true;
    }
    return false;
}

// ---------------------------------------------------------------- 绘制主画面
void DrawBoard(HDC dc, const RECT& client) {
    FillRectColor(dc, client, kFace);

    // 外框（凹陷）
    FillRectColor(dc, g.field, kFace);
    DrawBevel(dc, g.field, false, g.border);

    // 面板
    FillRectColor(dc, g.panel, kFace);
    RECT panelInner = g.panel;
    DrawBevel(dc, panelInner, false, S(2));

    // LED 数字
    FillRectColor(dc, g.mineLed, kLedBg);
    FillRectColor(dc, g.timeLed, kLedBg);
    const int dw = (g.mineLed.right - g.mineLed.left) / 3;
    for (int i = 0; i < 3; ++i) {
        RECT d1 = {g.mineLed.left + i * dw + 1, g.mineLed.top + 1,
                   g.mineLed.left + (i + 1) * dw - 1, g.mineLed.bottom - 1};
        DrawDigit(dc, g.mineDigits[i], d1, true);
        RECT d2 = {g.timeLed.left + i * dw + 1, g.timeLed.top + 1,
                   g.timeLed.left + (i + 1) * dw - 1, g.timeLed.bottom - 1};
        DrawDigit(dc, g.timeDigits[i], d2, true);
    }

    // 笑脸按钮
    DrawSmiley(dc, g.smiley, FaceState());

    // 格子
    HFONT oldFont = (HFONT)SelectObject(dc, g.fontNum);
    SetBkMode(dc, TRANSPARENT);
    for (int y = 0; y < g.board.rows(); ++y) {
        for (int x = 0; x < g.board.cols(); ++x) {
            RECT r = CellRect(x, y);
            const Cell& c = g.board.at(x, y);

            if (c.state == REVEALED) {
                FillRectColor(dc, r, kFace);
                if (c.mine) {
                    if (c.exploded) FillRectColor(dc, r, kRed);
                    DrawMine(dc, r);
                } else if (c.adj > 0) {
                    SetTextColor(dc, kNumber[c.adj]);
                    wchar_t t[2] = {(wchar_t)(L'0' + c.adj), 0};
                    DrawTextW(dc, t, 1, &r, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
                }
                // 已翻开的格子画细网格线
                RECT top = {r.left, r.top, r.right, r.top + 1};
                RECT left = {r.left, r.top, r.left + 1, r.bottom};
                FillRectColor(dc, top, kGridLine);
                FillRectColor(dc, left, kGridLine);
            } else {
                FillRectColor(dc, r, kFace);
                DrawBevel(dc, r, true, (g.cell >= 18) ? S(2) : 1);
                if (c.state == FLAGGED) {
                    DrawFlag(dc, r);
                } else if (c.state == QUESTION) {
                    SetTextColor(dc, RGB(0, 0, 0));
                    DrawTextW(dc, L"?", 1, &r, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
                }
            }
            if (c.wrong_flag) {                 // 失败后标出插错的旗
                HPEN pen = CreatePen(PS_SOLID, S(2), kRed);
                HPEN op = (HPEN)SelectObject(dc, pen);
                MoveToEx(dc, r.left + S(3), r.top + S(3), nullptr);
                LineTo(dc, r.right - S(3), r.bottom - S(3));
                MoveToEx(dc, r.right - S(3), r.top + S(3), nullptr);
                LineTo(dc, r.left + S(3), r.bottom - S(3));
                SelectObject(dc, op);
                DeleteObject(pen);
            }
        }
    }
    SelectObject(dc, oldFont);

    // 键盘光标
    if (g.cursorOn) {
        const RECT r = CellRect(g.cursorX, g.cursorY);
        HPEN pen = CreatePen(PS_DOT, 1, RGB(0, 0, 0));
        HPEN op = (HPEN)SelectObject(dc, pen);
        HBRUSH ob = (HBRUSH)SelectObject(dc, GetStockObject(NULL_BRUSH));
        Rectangle(dc, r.left + 1, r.top + 1, r.right - 1, r.bottom - 1);
        SelectObject(dc, op);
        SelectObject(dc, ob);
        DeleteObject(pen);
    }
}

void OnPaint(HWND hwnd) {
    PAINTSTRUCT ps;
    HDC dc = BeginPaint(hwnd, &ps);

    RECT client;
    GetClientRect(hwnd, &client);
    const int w = client.right, h = client.bottom;

    if (!g.memDc || g.memW != w || g.memH != h) {     // 重建后备缓冲
        if (g.memBmp) DeleteObject(g.memBmp);
        if (g.memDc) DeleteDC(g.memDc);
        g.memDc = CreateCompatibleDC(dc);
        g.memBmp = CreateCompatibleBitmap(dc, w, h);
        SelectObject(g.memDc, g.memBmp);
        g.memW = w;
        g.memH = h;
    }
    DrawBoard(g.memDc, client);
    BitBlt(dc, 0, 0, w, h, g.memDc, 0, 0, SRCCOPY);
    EndPaint(hwnd, &ps);
}

// ---------------------------------------------------------------- 输入
void OnButtonDown(HWND hwnd, bool left, POINT p) {
    if (left) {
        g.leftDown = true;
        if (PtInRect(&g.smiley, p) && !g.board.finished()) {
            g.smileyDown = true;
            InvalidateRect(hwnd, &g.smiley, FALSE);
            return;
        }
    } else {
        g.rightDown = true;
    }
    int cx = -1, cy = -1;
    if (!CellFromPoint(p, cx, cy) || g.board.finished()) return;

    if (left) g.leftCell = g.board.index(cx, cy);
    else g.rightCell = g.board.index(cx, cy);

    // 双键和弦
    if (g.leftDown && g.rightDown && g.leftCell == g.rightCell && g.leftCell >= 0) {
        DoChord(hwnd, cx, cy);
        g.leftCell = g.rightCell = -1;
        return;
    }
    g.cursorOn = true;
    g.cursorX = cx;
    g.cursorY = cy;
    InvalidateRect(hwnd, &g.grid, FALSE);
}

void OnButtonUp(HWND hwnd, bool left, POINT p) {
    int cx = -1, cy = -1;
    const bool inCell = CellFromPoint(p, cx, cy);
    const int index = inCell ? g.board.index(cx, cy) : -1;

    if (left) {
        g.leftDown = false;
        if (g.smileyDown) {
            g.smileyDown = false;
            InvalidateRect(hwnd, &g.smiley, FALSE);
            if (PtInRect(&g.smiley, p)) NewGame(hwnd, g.cfg, 0);
            return;
        }
        const int pressed = g.leftCell;
        g.leftCell = -1;
        if (pressed >= 0 && pressed == index && !g.rightDown) {
            DoReveal(hwnd, index % g.board.cols(), index / g.board.cols());
        }
    } else {
        g.rightDown = false;
        const int pressed = g.rightCell;
        g.rightCell = -1;
        if (pressed >= 0 && pressed == index && !g.leftDown) {
            DoFlag(hwnd, index % g.board.cols(), index / g.board.cols());
        }
    }
}

void OnKeyDown(HWND hwnd, WPARAM key) {
    switch (key) {
        case VK_F2:
            NewGame(hwnd, g.cfg, 0);
            return;
        case VK_LEFT: case VK_RIGHT: case VK_UP: case VK_DOWN: {
            if (!g.cursorOn) {
                g.cursorOn = true;
                g.cursorX = 0;
                g.cursorY = 0;
            } else {
                if (key == VK_LEFT && g.cursorX > 0) --g.cursorX;
                if (key == VK_RIGHT && g.cursorX + 1 < g.board.cols()) ++g.cursorX;
                if (key == VK_UP && g.cursorY > 0) --g.cursorY;
                if (key == VK_DOWN && g.cursorY + 1 < g.board.rows()) ++g.cursorY;
            }
            InvalidateRect(hwnd, &g.grid, FALSE);
            return;
        }
        case VK_SPACE:
            if (g.cursorOn && !g.board.finished()) {
                DoReveal(hwnd, g.cursorX, g.cursorY);
            }
            return;
        case 'F':
            if (g.cursorOn && !g.board.finished()) {
                DoFlag(hwnd, g.cursorX, g.cursorY);
            }
            return;
        case 'C':
            if (g.cursorOn) DoChord(hwnd, g.cursorX, g.cursorY);
            return;
        default:
            return;
    }
}

// ---------------------------------------------------------------- 菜单
HMENU BuildMenu() {
    HMENU bar = CreateMenu();
    HMENU game = CreatePopupMenu();
    AppendMenuW(game, MF_STRING, IDM_NEW, L"新游戏(&N)\tF2");
    AppendMenuW(game, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(game, MF_STRING, IDM_BEGINNER, L"初级(&B)\t9×9, 10 雷");
    AppendMenuW(game, MF_STRING, IDM_INTERMEDIATE, L"中级(&I)\t16×16, 40 雷");
    AppendMenuW(game, MF_STRING, IDM_EXPERT, L"高级(&E)\t30×16, 99 雷");
    AppendMenuW(game, MF_STRING, IDM_CUSTOM, L"自定义(&C)...");
    AppendMenuW(game, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(game, MF_STRING, IDM_SAFE_FIRST, L"首点安全(&S)");
    CheckMenuItem(game, IDM_SAFE_FIRST, MF_BYCOMMAND | MF_CHECKED);
    AppendMenuW(game, MF_STRING, IDM_QUESTION, L"允许问号标记(&Q)");
    CheckMenuItem(game, IDM_QUESTION, MF_BYCOMMAND | MF_CHECKED);
    AppendMenuW(game, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(game, MF_STRING, IDM_BEST, L"最佳成绩(&R)...");
    AppendMenuW(game, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(game, MF_STRING, IDM_EXIT, L"退出(&X)");
    AppendMenuW(bar, MF_POPUP, (UINT_PTR)game, L"游戏(&G)");
    g.gameMenu = game;

    HMENU help = CreatePopupMenu();
    AppendMenuW(help, MF_STRING, IDM_HOWTO, L"操作说明(&H)\tF1");
    AppendMenuW(help, MF_STRING, IDM_ABOUT, L"关于(&A)...");
    AppendMenuW(bar, MF_POPUP, (UINT_PTR)help, L"帮助(&H)");
    return bar;
}

void ShowHowTo(HWND hwnd) {
    MessageBoxW(hwnd,
                L"目标：翻开所有不是雷的格子，且不踩到雷。\n\n"
                L"【鼠标】\n"
                L"  左键          翻开格子\n"
                L"  右键          插旗 / 问号 / 取消（循环）\n"
                L"  左右键同按    和弦：周围旗数等于数字时，一次翻开其余邻格\n"
                L"  中键          和弦\n"
                L"  点笑脸        重新开始\n\n"
                L"【键盘】\n"
                L"  方向键        移动光标\n"
                L"  空格          翻开\n"
                L"  F             插旗\n"
                L"  C             和弦\n"
                L"  F2            新游戏\n"
                L"  F1            本说明\n\n"
                L"【颜色】数字 1-8 各有固定颜色，和 Windows 扫雷一致。\n"
                L"首次点击永远安全：那一下及其周围 8 格都不会有雷。",
                L"操作说明", MB_OK | MB_ICONINFORMATION);
}

void ShowAbout(HWND hwnd) {
    auto bestText = [](int level) {
        if (g.best[level] <= 0) return std::wstring(L"暂无");
        return Format(L"%d 秒", g.best[level]);
    };
    MessageBoxW(hwnd,
                Format(L"扫雷 · C++ / Win32   版本 1.0.0\n\n"
                       L"纯 Win32 API + GDI 实现，无第三方库，静态链接 CRT。\n"
                       L"核心逻辑与界面分离，逻辑部分有独立单元测试。\n\n"
                       L"最佳成绩\n"
                       L"  初级   %s\n  中级   %s\n  高级   %s\n\n"
                       L"成绩保存位置：HKEY_CURRENT_USER\\Software\\CppMinesweeper",
                       bestText(0).c_str(), bestText(1).c_str(), bestText(2).c_str())
                    .c_str(),
                L"关于", MB_OK | MB_ICONINFORMATION);
}

// ---------------------------------------------------------------- 窗口过程
LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
        case WM_CREATE:
            g.hwnd = hwnd;
            SetTimer(hwnd, IDT_CLOCK, 100, nullptr);
            return 0;

        case WM_ERASEBKGND:
            return 1;                      // 全部由双缓冲绘制

        case WM_PAINT:
            OnPaint(hwnd);
            return 0;

        case WM_TIMER:
            if (wp == IDT_CLOCK) {
                if (g.board.status() == Status::Playing) {
                    const int before = g.elapsed;
                    TickClock();
                    if (g.elapsed != before) {
                        UpdateDigits();
                        InvalidateRect(hwnd, &g.panel, FALSE);
                    }
                }
            }
            return 0;

        case WM_LBUTTONDOWN:
            OnButtonDown(hwnd, true, {GET_X_LPARAM(lp), GET_Y_LPARAM(lp)});
            return 0;
        case WM_LBUTTONUP:
            OnButtonUp(hwnd, true, {GET_X_LPARAM(lp), GET_Y_LPARAM(lp)});
            return 0;
        case WM_RBUTTONDOWN:
            OnButtonDown(hwnd, false, {GET_X_LPARAM(lp), GET_Y_LPARAM(lp)});
            return 0;
        case WM_RBUTTONUP:
            OnButtonUp(hwnd, false, {GET_X_LPARAM(lp), GET_Y_LPARAM(lp)});
            return 0;
        case WM_MBUTTONDOWN: {
            int cx, cy;
            POINT p{GET_X_LPARAM(lp), GET_Y_LPARAM(lp)};
            if (CellFromPoint(p, cx, cy)) DoChord(hwnd, cx, cy);
            return 0;
        }
        case WM_KEYDOWN:
            OnKeyDown(hwnd, wp);
            return 0;

        case WM_GETMINMAXINFO: {
            auto* mmi = (MINMAXINFO*)lp;
            RECT want = {0, 0, g.field.right + g.pad, g.field.bottom + g.pad};
            AdjustWindowRectEx(&want, (DWORD)GetWindowLongPtrW(hwnd, GWL_STYLE), TRUE,
                               (DWORD)GetWindowLongPtrW(hwnd, GWL_EXSTYLE));
            mmi->ptMinTrackSize.x = mmi->ptMaxTrackSize.x = want.right - want.left;
            mmi->ptMinTrackSize.y = mmi->ptMaxTrackSize.y = want.bottom - want.top;
            return 0;
        }

        case WM_COMMAND: {
            switch (LOWORD(wp)) {
                case IDM_NEW:
                    NewGame(hwnd, g.cfg, 0);
                    return 0;
                case IDM_BEGINNER:
                    NewGame(hwnd, sweeper::presetBeginner(), 0);
                    return 0;
                case IDM_INTERMEDIATE:
                    NewGame(hwnd, sweeper::presetIntermediate(), 0);
                    return 0;
                case IDM_EXPERT:
                    NewGame(hwnd, sweeper::presetExpert(), 0);
                    return 0;
                case IDM_CUSTOM: {
                    Config cfg = g.cfg;
                    if (ShowCustomDialog(hwnd, cfg)) NewGame(hwnd, cfg, 0);
                    return 0;
                }
                case IDM_SAFE_FIRST: {
                    const bool on = g.board.config().safe_first_click;
                    Config cfg = g.cfg;
                    cfg.safe_first_click = !on;
                    CheckMenuItem(g.gameMenu, IDM_SAFE_FIRST,
                                  MF_BYCOMMAND | (cfg.safe_first_click ? MF_CHECKED : MF_UNCHECKED));
                    NewGame(hwnd, cfg, 0);
                    return 0;
                }
                case IDM_QUESTION: {
                    g.cfg.question_marks = !g.cfg.question_marks;
                    g.board.setQuestionMarks(g.cfg.question_marks);
                    CheckMenuItem(g.gameMenu, IDM_QUESTION,
                                  MF_BYCOMMAND | (g.cfg.question_marks ? MF_CHECKED
                                                                       : MF_UNCHECKED));
                    return 0;
                }
                case IDM_BEST:
                    ShowAbout(hwnd);
                    return 0;
                case IDM_HOWTO:
                    ShowHowTo(hwnd);
                    return 0;
                case IDM_ABOUT:
                    ShowAbout(hwnd);
                    return 0;
                case IDM_EXIT:
                    DestroyWindow(hwnd);
                    return 0;
                default:
                    return 0;
            }
        }

        case WM_DESTROY:
            KillTimer(hwnd, IDT_CLOCK);
            if (g.memBmp) DeleteObject(g.memBmp);
            if (g.memDc) DeleteDC(g.memDc);
            if (g.fontNum) DeleteObject(g.fontNum);
            if (g.fontUi) DeleteObject(g.fontUi);
            PostQuitMessage(0);
            return 0;
        default:
            break;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}

void EnableDpiAwareness() {
    // 优先用 Per-Monitor V2，老系统退回到 system aware
    HMODULE user32 = GetModuleHandleW(L"user32.dll");
    if (user32) {
        using SetCtxFn = BOOL(WINAPI*)(void*);
        auto fn = (SetCtxFn)GetProcAddress(user32, "SetProcessDpiAwarenessContext");
        if (fn && fn((void*)-4 /* PER_MONITOR_AWARE_V2 */)) return;
    }
    SetProcessDPIAware();
}

}  // namespace

int WINAPI wWinMain(HINSTANCE hInstance, HINSTANCE, LPWSTR lpCmdLine, int) {
    (void)lpCmdLine;
    EnableDpiAwareness();
    LoadBest();

    WNDCLASSEXW wc{};
    wc.cbSize = sizeof(wc);
    wc.style = CS_HREDRAW | CS_VREDRAW;
    wc.lpfnWndProc = WndProc;
    wc.hInstance = hInstance;
    wc.hIcon = LoadIconW(hInstance, MAKEINTRESOURCEW(101));   // res/app.rc 的 IDI_APPICON
    wc.hIconSm = wc.hIcon;
    wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
    wc.lpszClassName = kClassName;
    if (!RegisterClassExW(&wc)) {
        MessageBoxW(nullptr, L"窗口类注册失败", kAppTitle, MB_ICONERROR);
        return 1;
    }

    HDC screen = GetDC(nullptr);
    g.scale = GetDeviceCaps(screen, LOGPIXELSX) / 96.0;
    ReleaseDC(nullptr, screen);

    g.board.reset(g.cfg, 0);
    Layout(false);

    RECT want = {0, 0, g.field.right + g.pad, g.field.bottom + g.pad};
    AdjustWindowRectEx(&want, WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX, TRUE, 0);
    const int winW = want.right - want.left;
    const int winH = want.bottom - want.top;

    HWND hwnd = CreateWindowExW(0, kClassName, kAppTitle,
                                WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX,
                                CW_USEDEFAULT, CW_USEDEFAULT, winW, winH, nullptr,
                                BuildMenu(), hInstance, nullptr);
    if (!hwnd) {
        MessageBoxW(nullptr, L"窗口创建失败", kAppTitle, MB_ICONERROR);
        return 1;
    }

    g.fontNum = CreateFontW(-S(15), 0, 0, 0, FW_BOLD, FALSE, FALSE, FALSE, DEFAULT_CHARSET,
                            OUT_TT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
                            DEFAULT_PITCH | FF_DONTCARE, L"Consolas");
    g.fontUi = CreateFontW(-S(14), 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE, DEFAULT_CHARSET,
                           OUT_TT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
                           DEFAULT_PITCH | FF_DONTCARE, L"Microsoft YaHei UI");

    ShowWindow(hwnd, SW_SHOW);
    UpdateWindow(hwnd);
    NewGame(hwnd, g.cfg, 0);          // 重新布局一次，确保尺寸与 DPI 一致

    ACCEL accel[1];
    accel[0].fVirt = FVIRTKEY;
    accel[0].key = VK_F2;
    accel[0].cmd = IDM_NEW;
    HACCEL hAccel = CreateAcceleratorTableW(accel, 1);

    MSG msg;
    while (GetMessageW(&msg, nullptr, 0, 0)) {
        if (hAccel && TranslateAcceleratorW(hwnd, hAccel, &msg)) continue;
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
    if (hAccel) DestroyAcceleratorTable(hAccel);
    return (int)msg.wParam;
}
