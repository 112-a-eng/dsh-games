# -*- coding: utf-8 -*-
"""行情图表：A 股风格分时图 + 日 K 线图（含均线、成交量、十字光标）。

配色遵循 A 股习惯：红涨绿跌。
"""
from __future__ import annotations

import math

UP = "#f2545b"          # 涨（红）
DOWN = "#3fbf7f"        # 跌（绿）
FLAT = "#9aa4b2"
GRID = "#1c2431"
TEXT = "#c9d3e0"
MUTED = "#7d8798"
BG = "#0b0e14"
LINE = "#e8eef7"
AVG_LINE = "#f2c94c"
MA_COLORS = {5: "#f2c94c", 10: "#5aa9f8", 20: "#b26ff0"}
CROSS = "#8fa0b8"
FONT = "Microsoft YaHei UI"


def fmt_volume(shares: float) -> str:
    """成交量按"手"显示（1 手 = 100 股）。"""
    hands = shares / 100.0
    if hands >= 1e8:
        return "%.2f亿手" % (hands / 1e8)
    if hands >= 1e4:
        return "%.2f万手" % (hands / 1e4)
    return "%.0f手" % hands


def fmt_money(value: float) -> str:
    sign = "-" if value < 0 else ""
    v = abs(value)
    if v >= 1e8:
        return "%s%.2f亿" % (sign, v / 1e8)
    if v >= 1e4:
        return "%s%.2f万" % (sign, v / 1e4)
    return "%s%.2f" % (sign, v)


class Chart:
    """一个画布上的行情图，支持分时 / 日 K 两种模式。"""

    PAD_L, PAD_R, PAD_T, PAD_B = 58, 52, 10, 20
    VOL_H = 0.24          # 成交量区高度占比

    def __init__(self, canvas, game):
        self.canvas = canvas
        self.game = game
        self.code = game.market.order_codes[0]
        self.mode = "minute"
        self.cross_xy = None
        canvas.bind("<Motion>", self._on_motion)
        canvas.bind("<Leave>", self._on_leave)

    # ------------------------------------------------------------ 对外接口
    def show(self, code: str, mode: str | None = None) -> None:
        if code:
            self.code = code
        if mode:
            self.mode = mode
        self.cross_xy = None
        self.redraw()

    def toggle_mode(self) -> None:
        self.mode = "day" if self.mode == "minute" else "minute"
        self.redraw()

    @property
    def stock(self):
        return self.game.market.stocks.get(self.code)

    # ------------------------------------------------------------ 尺寸
    def _size(self) -> tuple[int, int]:
        canvas = self.canvas
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w <= 1:
            w = int(canvas["width"])
        if h <= 1:
            h = int(canvas["height"])
        return w, h

    def _areas(self, w: int, h: int):
        left, right = self.PAD_L, w - self.PAD_R
        top = self.PAD_T
        bottom = h - self.PAD_B
        vol_top = top + (bottom - top) * (1 - self.VOL_H)
        return left, right, top, vol_top - 8, vol_top + 8, bottom

    # ------------------------------------------------------------ 绘制入口
    def redraw(self) -> None:
        canvas = self.canvas
        canvas.delete("all")
        stock = self.stock
        if stock is None:
            return
        w, h = self._size()
        if w < 120 or h < 120:
            return
        left, right, top, price_bottom, vol_top, bottom = self._areas(w, h)
        canvas.create_rectangle(0, 0, w, h, fill=BG, outline="", tags="chart")

        if self.mode == "minute":
            self._draw_minute(stock, left, right, top, price_bottom, vol_top, bottom)
        else:
            self._draw_daily(stock, left, right, top, price_bottom, vol_top, bottom)
        self._draw_header(stock, left, top)
        if self.cross_xy:
            self._draw_cross(left, right, top, bottom, vol_top)

    # ------------------------------------------------------------ 头部信息
    def _draw_header(self, stock, left: int, top: int) -> None:
        canvas = self.canvas
        color = UP if stock.change_pct > 0 else (DOWN if stock.change_pct < 0 else FLAT)
        canvas.create_text(left, top - 2, anchor="w", text="%s %s" % (stock.code, stock.name),
                           fill=TEXT, font=(FONT, 11, "bold"))
        canvas.create_text(left + 150, top - 2, anchor="w",
                           text="%.2f" % stock.last, fill=color,
                           font=(FONT, 12, "bold"))
        canvas.create_text(left + 226, top - 2, anchor="w",
                           text="%+.2f  %+.2f%%" % (stock.last - stock.prev_close,
                                                    stock.change_pct),
                           fill=color, font=(FONT, 10))

    # ------------------------------------------------------------ 分时图
    def _draw_minute(self, stock, left, right, top, price_bottom, vol_top, bottom) -> None:
        canvas = self.canvas
        total = self.game.market.total_minutes
        bars = stock.bars
        base = stock.prev_close

        closes = [b.close for b in bars]
        avgs = []
        cum_amount = cum_volume = 0.0
        for bar in bars:
            cum_amount += bar.amount
            cum_volume += bar.volume
            avgs.append(cum_amount / cum_volume if cum_volume else bar.close)

        deviation = max([abs(c - base) for c in closes] + [abs(a - base) for a in avgs] + [0.0])
        span = max(deviation * 1.12, base * 0.004)
        hi, lo = base + span, base - span

        def px(minute: float) -> float:
            return left + (right - left) * min(max(minute, 0), total) / total

        def py(price: float) -> float:
            return price_bottom - (price - lo) / (hi - lo) * (price_bottom - top)

        # 网格 + 左右价格刻度
        for i in range(5):
            y = top + (price_bottom - top) * i / 4
            price = hi - (hi - lo) * i / 4
            pct = (price / base - 1) * 100
            canvas.create_line(left, y, right, y, fill=GRID)
            canvas.create_text(left - 4, y, anchor="e", text="%.2f" % price,
                               fill=MUTED, font=(FONT, 8))
            pct_color = UP if pct > 0.001 else (DOWN if pct < -0.001 else MUTED)
            canvas.create_text(right + 4, y, anchor="w", text="%+.2f%%" % pct,
                               fill=pct_color, font=(FONT, 8))
        for i in range(5):
            x = left + (right - left) * i / 4
            canvas.create_line(x, top, x, bottom, fill=GRID)
        for i, label in enumerate(self._time_labels()):
            x = left + (right - left) * i / (len(self._time_labels()) - 1)
            canvas.create_text(x, bottom + 8, text=label, fill=MUTED, font=(FONT, 8))

        # 昨收基准线
        y0 = py(base)
        canvas.create_line(left, y0, right, y0, fill="#55606f", dash=(3, 3))

        if len(closes) >= 2:
            pts = []
            for bar, close in zip(bars, closes):
                pts += [px(bar.minute), py(close)]
            canvas.create_line(*pts, fill=LINE, width=2)
            avg_pts = []
            for bar, avg in zip(bars, avgs):
                avg_pts += [px(bar.minute), py(avg)]
            canvas.create_line(*avg_pts, fill=AVG_LINE, width=1)
        if closes:
            # 当前点
            canvas.create_oval(px(bars[-1].minute) - 3, py(closes[-1]) - 3,
                               px(bars[-1].minute) + 3, py(closes[-1]) + 3,
                               fill=LINE, outline="")

        entries = [(left + (right - left) * bar.minute / total, bar.volume,
                    bar.close >= (bars[i - 1].close if i > 0 else base))
                   for i, bar in enumerate(bars)]
        self._draw_volume(entries, left, right, vol_top, bottom)

    def _time_labels(self) -> list[str]:
        if self.game.rules.key == "cn":
            return ["09:30", "10:30", "11:30/13:00", "14:00", "15:00"]
        return ["09:30", "11:00", "12:30", "14:00", "16:00"]

    # ------------------------------------------------------------ 日 K
    def _draw_daily(self, stock, left, right, top, price_bottom, vol_top, bottom) -> None:
        canvas = self.canvas
        daily = stock.daily
        if len(daily) < 2:
            canvas.create_text((left + right) / 2, (top + bottom) / 2,
                               text="数据不足：至少需要 2 个交易日",
                               fill=MUTED, font=(FONT, 11))
            return
        window = min(60, len(daily))
        start = len(daily) - window
        # 固定蜡烛宽度、最新一根贴右边（历史不足时左侧留白，与真实行情软件一致）
        slot = min(18.0, (right - left) / max(1, window))
        view = daily[start:]

        ma = {}
        for period in (5, 10, 20):
            series = []
            for i in range(start, len(daily)):
                if i + 1 >= period:
                    seg = daily[i + 1 - period:i + 1]
                    series.append(sum(d.close for d in seg) / period)
                else:
                    series.append(None)
            ma[period] = series

        highs = [d.high for d in view]
        lows = [d.low for d in view]
        for period in (5, 10, 20):
            highs += [v for v in ma[period] if v]
            lows += [v for v in ma[period] if v]
        hi, lo = max(highs), min(lows)
        pad = (hi - lo) * 0.06 or hi * 0.01
        hi += pad
        lo -= pad

        def cx(i: int) -> float:
            return right - (window - i - 0.5) * slot

        def cy(price: float) -> float:
            return price_bottom - (price - lo) / (hi - lo) * (price_bottom - top)

        for i in range(5):
            y = top + (price_bottom - top) * i / 4
            canvas.create_line(left, y, right, y, fill=GRID)
            canvas.create_text(left - 4, y, anchor="e", text="%.2f" % (hi - (hi - lo) * i / 4),
                               fill=MUTED, font=(FONT, 8))
        step = max(1, int(52 / max(slot, 1)))
        for i in range(window - 1, -1, -step):
            x = cx(i)
            canvas.create_line(x, top, x, bottom, fill=GRID)
            canvas.create_text(x, bottom + 8, text=view[i].date.strftime("%m-%d"),
                               fill=MUTED, font=(FONT, 8))

        # 均线
        for period, color in MA_COLORS.items():
            pts = []
            for i, value in enumerate(ma[period]):
                if value:
                    pts += [cx(i), cy(value)]
            if len(pts) >= 4:
                canvas.create_line(*pts, fill=color, width=1)
        # K 线
        body_w = max(2.0, slot * 0.62)
        for i, bar in enumerate(view):
            color = UP if bar.close >= bar.open else DOWN
            x = cx(i)
            canvas.create_line(x, cy(bar.high), x, cy(bar.low), fill=color)
            y_open, y_close = cy(bar.open), cy(bar.close)
            if abs(y_close - y_open) < 1:
                y_close = y_open + (1 if bar.close >= bar.open else -1)
            canvas.create_rectangle(x - body_w / 2, min(y_open, y_close),
                                    x + body_w / 2, max(y_open, y_close),
                                    fill=color, outline=color)
        legend = "   ".join("MA%d" % p for p in MA_COLORS)
        canvas.create_text(right - 6, top - 2, anchor="e", text=legend, fill=MUTED,
                           font=(FONT, 8))

        entries = [(cx(i), bar.volume, bar.close >= bar.open)
                   for i, bar in enumerate(view)]
        self._draw_volume(entries, left, right, vol_top, bottom, width=body_w)

    # ------------------------------------------------------------ 成交量
    def _draw_volume(self, entries, left, right, vol_top, bottom, width=None) -> None:
        """entries: [(横向像素位置, 成交量, 是否收涨)]"""
        if not entries:
            return
        canvas = self.canvas
        max_vol = max((e[1] for e in entries), default=0) or 1
        if width is None:
            width = max(1.0, (right - left) / max(1, len(entries)) * 0.7)
        for x, volume, up in entries:
            height = max(1.0, (bottom - vol_top) * volume / max_vol)
            canvas.create_rectangle(x - width / 2, bottom - height, x + width / 2, bottom,
                                    fill=UP if up else DOWN, outline="")
        canvas.create_text(left - 4, vol_top, anchor="w", text=fmt_volume(max_vol),
                           fill=MUTED, font=(FONT, 8))

    # ------------------------------------------------------------ 十字光标
    def _on_motion(self, event) -> None:
        self.cross_xy = (event.x, event.y)
        self.canvas.delete("cross")
        w, h = self._size()
        left, right, top, price_bottom, vol_top, bottom = self._areas(w, h)
        self._draw_cross(left, right, top, bottom, vol_top)

    def _on_leave(self, _event) -> None:
        self.cross_xy = None
        self.canvas.delete("cross")

    def _draw_cross(self, left, right, top, bottom, vol_top) -> None:
        if not self.cross_xy:
            return
        canvas = self.canvas
        x, y = self.cross_xy
        if not (left <= x <= right and top <= y <= bottom):
            return
        stock = self.stock
        canvas.delete("cross")
        canvas.create_line(x, top, x, bottom, fill=CROSS, dash=(3, 3), tags="cross")
        canvas.create_line(left, y, right, y, fill=CROSS, dash=(3, 3), tags="cross")

        if self.mode == "minute":
            total = self.game.market.total_minutes
            minute = int(round((x - left) / (right - left) * total))
            bars = stock.bars
            if not bars:
                return
            minute = min(minute, bars[-1].minute)
            bar = None
            for candidate in bars:
                if candidate.minute == minute:
                    bar = candidate
                    break
            if bar is None:
                bar = bars[min(minute, len(bars) - 1)]
            avg = stock.avg_price
            lines = [
                "时间 %s" % self._minute_clock(bar.minute),
                "价格 %.2f  (%+.2f%%)" % (bar.close, (bar.close / stock.prev_close - 1) * 100),
                "均价 %.2f" % avg,
                "成交量 %s" % fmt_volume(bar.volume),
                "最高 %.2f  最低 %.2f" % (bar.high, bar.low),
            ]
        else:
            daily = stock.daily
            if len(daily) < 2:
                return
            window = min(60, len(daily))
            start = len(daily) - window
            slot = min(18.0, (right - left) / max(1, window))
            index = int(round(window - 1 - ((right - x) / slot - 0.5)))
            index = min(max(index, 0), window - 1)
            bar = daily[start + index]
            pct = (bar.close / bar.open - 1) * 100
            lines = [
                bar.date.strftime("%Y-%m-%d"),
                "开 %.2f  高 %.2f" % (bar.open, bar.high),
                "低 %.2f  收 %.2f" % (bar.low, bar.close),
                "振幅 %.2f%%" % pct,
                "成交量 %s" % fmt_volume(bar.volume),
            ]
        self._tooltip(x, y, lines)

    def _tooltip(self, x: float, y: float, lines: list[str]) -> None:
        canvas = self.canvas
        text = "\n".join(lines)
        item = canvas.create_text(0, 0, text=text, anchor="nw", fill=TEXT,
                                  font=(FONT, 9), tags="cross")
        bx0, by0, bx1, by1 = canvas.bbox(item)
        width, height = bx1 - bx0, by1 - by0
        w, h = self._size()
        tx = x + 14 if x + 14 + width < w else x - 14 - width
        ty = y + 12 if y + 12 + height < h else y - 12 - height
        canvas.coords(item, tx + 6, ty + 4)
        rect = canvas.create_rectangle(tx, ty, tx + width + 12, ty + height + 8,
                                       fill="#161c26", outline="#2f3a4d", tags="cross")
        canvas.tag_lower(rect, item)

    def _minute_clock(self, minute: int) -> str:
        from .trading import minute_to_clock
        return minute_to_clock(minute, self.game.rules, self.game.market.total_minutes)
