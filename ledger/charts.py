# -*- coding: utf-8 -*-
"""图表：用 tkinter Canvas 手绘饼图与分组柱状图（不依赖 matplotlib）。

同时被界面层和截图脚本使用，绘图逻辑本身不引用账务数据，只接受已经算好的数值。
"""
from __future__ import annotations

import math

# 浅色专业配色
BG = "#ffffff"
GRID = "#e6eaf0"
AXIS = "#b7c0cc"
TEXT = "#1f2937"
MUTED = "#8792a2"
FONT = "Microsoft YaHei UI"

PALETTE = [
    "#2f6fed", "#f2a33c", "#3fbf7f", "#e05a6b", "#8b5cf6",
    "#14b8a6", "#f472b6", "#f59e0b", "#6366f1", "#10b981",
    "#ef4444", "#0ea5e9",
]

REVENUE_COLOR = "#2f6fed"
EXPENSE_COLOR = "#e05a6b"
NET_COLOR = "#3fbf7f"


def abbrev(cents: int) -> str:
    """把「分」缩写成带 万 / 亿 的字符串，用于坐标轴与图例。"""
    sign = "-" if cents < 0 else ""
    v = abs(cents) / 100.0
    if v >= 1e8:
        return "%s%.2f亿" % (sign, v / 1e8)
    if v >= 1e4:
        return "%s%.2f万" % (sign, v / 1e4)
    return "%s%.2f" % (sign, v)


class ChartCanvas:
    """一个会随窗口大小自动重绘的图表画布。"""

    def __init__(self, canvas, background=BG):
        self.canvas = canvas
        self.background = background
        self._kind = "empty"
        self._data = None
        self._title = ""
        canvas.configure(background=background, highlightthickness=0)
        canvas.bind("<Configure>", self._on_configure)

    def _on_configure(self, _event=None):
        self.redraw()

    def clear(self):
        self._kind = "empty"
        self._data = None
        self.canvas.delete("all")

    def show_pie(self, items, title=""):
        """items: [(label, value_cents)]，value 为负数时取其绝对值。"""
        cleaned = [(lbl, abs(int(v))) for lbl, v in items if int(v) != 0]
        cleaned.sort(key=lambda x: -x[1])
        self._kind = "pie"
        self._data = cleaned
        self._title = title
        self.redraw()

    def show_bars(self, months, revenue, expense, net=None, title=""):
        self._kind = "bars"
        self._data = (list(months), list(revenue), list(expense),
                      list(net) if net is not None else None)
        self._title = title
        self.redraw()

    def redraw(self):
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w <= 1 or h <= 1:
            return
        title_y = 24
        if self._title:
            self.canvas.create_text(20, title_y, anchor="w", text=self._title,
                                    fill=TEXT, font=(FONT, 12, "bold"))
            top = 48
        else:
            top = 16
        if self._kind == "pie":
            self._draw_pie(w, h, top)
        elif self._kind == "bars":
            self._draw_bars(w, h, top)
        else:
            self._draw_empty(w, h)

    def _draw_empty(self, w, h):
        self.canvas.create_text(w // 2, h // 2, text="暂无数据",
                                fill=MUTED, font=(FONT, 12))

    # ------------------------------------------------------------ 饼图
    def _draw_pie(self, w, h, top):
        items = self._data
        total = sum(v for _, v in items)
        if not items or total <= 0:
            self._draw_empty(w, h)
            return
        legend_w = min(260, max(150, int(w * 0.34)))
        cx = (w - legend_w) // 2 + 10
        cy = top + (h - top) // 2
        r = max(30, min((w - legend_w) // 2 - 24, (h - top) // 2 - 24))
        x0, y0, x1, y1 = cx - r, cy - r, cx + r, cy + r

        start = 90.0
        for i, (label, value) in enumerate(items):
            extent = -value / total * 360.0
            if abs(extent) < 0.01:
                extent = -0.01
            color = PALETTE[i % len(PALETTE)]
            self.canvas.create_arc(x0, y0, x1, y1, start=start, extent=extent,
                                   fill=color, outline="white", width=1.5)
            start += extent
        self.canvas.create_oval(cx - r * 0.5, cy - r * 0.5, cx + r * 0.5, cy + r * 0.5,
                                fill=self.background, outline="")
        self.canvas.create_text(cx, cy - 8, text="合计", fill=MUTED, font=(FONT, 10))
        self.canvas.create_text(cx, cy + 12, text=abbrev(total), fill=TEXT,
                                font=(FONT, 12, "bold"))

        lx = w - legend_w + 6
        ly = top + 6
        line_h = 22
        for i, (label, value) in enumerate(items[:14]):
            color = PALETTE[i % len(PALETTE)]
            self.canvas.create_rectangle(lx, ly + 4, lx + 12, ly + 16,
                                         fill=color, outline="")
            pct = value / total * 100.0
            self.canvas.create_text(lx + 20, ly + 10, anchor="w",
                                    text="%s  %.1f%%（%s）" % (label, pct, abbrev(value)),
                                    fill=TEXT, font=(FONT, 9))
            ly += line_h
        self.canvas.create_line(lx - 10, top, lx - 10, h - 8, fill=GRID)

    # ------------------------------------------------------------ 柱状图
    def _draw_bars(self, w, h, top):
        months, revenue, expense, net = self._data
        n = len(months)
        if n == 0:
            self._draw_empty(w, h)
            return
        pad_l, pad_r, pad_b, pad_t = 66, 20, 44, top + 22
        plot_w = w - pad_l - pad_r
        plot_h = h - pad_b - pad_t
        if plot_w < 40 or plot_h < 40:
            return

        if net is None:
            values = revenue + expense
        else:
            values = revenue + expense + [abs(x) for x in net]
        vmax = max(values) if values else 0
        if vmax <= 0:
            vmax = 100
        vmin = 0
        if net is not None and min(net) < 0:
            vmin = min(net)
        span = vmax - vmin

        def y_of(v):
            return pad_t + plot_h - (v - vmin) / span * plot_h

        zero_y = y_of(0)

        # 网格 + 刻度
        for step in range(6):
            val = vmin + span * step / 5.0
            y = y_of(val)
            self.canvas.create_line(pad_l, y, w - pad_r, y, fill=GRID)
            self.canvas.create_text(pad_l - 8, y, anchor="e", text=abbrev(int(val)),
                                    fill=MUTED, font=(FONT, 8))
        self.canvas.create_line(pad_l, zero_y, w - pad_r, zero_y, fill=AXIS)
        self.canvas.create_line(pad_l, pad_t, pad_l, h - pad_b, fill=AXIS)

        slot = plot_w / n
        bar_w = min(16, slot / 3.4)
        for i, m in enumerate(months):
            cx = pad_l + slot * (i + 0.5)
            # 收入
            self._bar(cx - bar_w, y_of(revenue[i]), zero_y, bar_w - 2, REVENUE_COLOR)
            # 费用
            self._bar(cx + 1, y_of(expense[i]), zero_y, bar_w - 2, EXPENSE_COLOR)
            self.canvas.create_text(cx, h - pad_b + 14, text="%d月" % m,
                                    fill=MUTED, font=(FONT, 8))
            if net is not None and net[i] != 0:
                ny = y_of(net[i])
                self.canvas.create_line(cx, ny - 3, cx, ny + 3, fill=NET_COLOR, width=2)

        # 图例
        lx = pad_l
        ly = top - 6
        for label, color in (("收入", REVENUE_COLOR), ("费用", EXPENSE_COLOR)):
            self.canvas.create_rectangle(lx, ly, lx + 12, ly + 12, fill=color, outline="")
            self.canvas.create_text(lx + 18, ly + 6, anchor="w", text=label,
                                    fill=TEXT, font=(FONT, 9))
            lx += 80
        if net is not None:
            self.canvas.create_line(lx, ly + 6, lx + 14, ly + 6, fill=NET_COLOR, width=2)
            self.canvas.create_text(lx + 20, ly + 6, anchor="w", text="净利润",
                                    fill=TEXT, font=(FONT, 9))

    def _bar(self, x, y_value, y_zero, width, color):
        if abs(y_value - y_zero) < 1:
            return
        top = min(y_value, y_zero)
        bottom = max(y_value, y_zero)
        self.canvas.create_rectangle(x, top, x + width, bottom, fill=color,
                                     outline="", width=0)


def sparkline_points(values, x0, y0, x1, y1):
    """把一组数值映射到线段的点列，供曲线使用（可选）。"""
    if not values:
        return []
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    n = len(values)
    pts = []
    for i, v in enumerate(values):
        x = x0 + (x1 - x0) * (i / (n - 1) if n > 1 else 0)
        y = y1 - (v - lo) / span * (y1 - y0)
        pts.append((x, y))
    return pts