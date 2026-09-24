# -*- coding: utf-8 -*-
"""tkinter 界面：盘面、图表、下单、账户、持仓/委托/成交/日志。

配色沿用 A 股习惯（红涨绿跌），整体为深色专业行情终端风格。
"""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk

from .charts import DOWN, UP, Chart, fmt_money, fmt_volume
from .config import DIFFICULTIES, MARKETS
from .engine import Game
from .trading import minute_to_clock

BG = "#0b0e14"
PANEL = "#111721"
CARD = "#151c28"
BORDER = "#232c3b"
TEXT = "#dde5ef"
MUTED = "#7d8798"
ACCENT = "#3f8cff"
YELLOW = "#f2c94c"
FONT = "Microsoft YaHei UI"
FRAME_MS = 16

# 节奏直接用“一个交易日走多少秒”表示（A 股一个交易日 240 个交易分钟）。
# 想更慢就往左选；最慢 10 分钟一整天，最快 5 秒一整天。
PACES_SECONDS = [5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 240, 300, 420, 600]
DEFAULT_DAY_SECONDS = 300             # 默认 5 分钟走完一个交易日
# 开局设置里的“节奏”快捷选项（秒/交易日）
PACES_PRESETS = [("悠闲", 600), ("慢", 300), ("标准", 120), ("快", 60), ("极速", 15)]


def pace_text(seconds: int) -> str:
    """把“每交易日秒数”写成人话。"""
    if seconds < 60:
        return "%d 秒/日" % seconds
    minutes, rest = divmod(seconds, 60)
    return "%d 分钟/日" % minutes if rest == 0 else "%d 分%02d 秒/日" % (minutes, rest)


def ticks_per_second(day_seconds: int, minutes: int = 240) -> float:
    """每交易日 day_seconds 秒时，每秒推进多少个交易分钟。"""
    return minutes / day_seconds if day_seconds > 0 else 0.0


class StartDialog:
    """开局设置：市场、难度、初始资金、随机种子、交易日数。"""

    def __init__(self, root):
        self.result = None
        top = self.top = tk.Toplevel(root)
        top.title("股票模拟交易 · 开局设置")
        top.configure(bg=BG)
        top.resizable(False, False)
        # 注意：这里不能用 top.transient(root)。主窗口是 withdrawn 状态，
        # 而 Tk 会让 transient 子窗口跟随主窗口一起隐藏，导致对话框看不见。

        tk.Label(top, text="股票模拟交易", bg=BG, fg=TEXT,
                 font=(FONT, 17, "bold")).grid(row=0, column=0, columnspan=2,
                                               padx=24, pady=(18, 2), sticky="w")
        tk.Label(top, text="A 股规则：涨跌停 ±10%（创业板/科创板 ±20%）、T+1、100 股一手、\n"
                           "佣金万 2.5（最低 5 元）、印花税千 0.5（卖出）、过户费 0.001%，"
                           "支持融资与强制平仓。",
                 bg=BG, fg=MUTED, font=(FONT, 9), justify="left").grid(
            row=1, column=0, columnspan=2, padx=24, pady=(0, 12), sticky="w")

        self.market = tk.StringVar(value="cn")
        self.diff = tk.StringVar(value="normal")
        self.cash = tk.StringVar(value="1000000")
        self.days = tk.StringVar(value="60")
        self.seed = tk.StringVar(value="")
        self.pace = tk.StringVar(value=str(DEFAULT_DAY_SECONDS))

        row = 2
        tk.Label(top, text="市场", bg=BG, fg=MUTED, font=(FONT, 9)).grid(
            row=row, column=0, sticky="w", padx=(24, 8), pady=4)
        box = tk.Frame(top, bg=BG)
        box.grid(row=row, column=1, sticky="w")
        for key, rules in MARKETS.items():
            tk.Radiobutton(box, text=rules.name, value=key, variable=self.market,
                           bg=BG, fg=TEXT, selectcolor=CARD, activebackground=BG,
                           activeforeground=TEXT, font=(FONT, 9),
                           highlightthickness=0).pack(side="left", padx=(0, 10))

        row += 1
        tk.Label(top, text="难度", bg=BG, fg=MUTED, font=(FONT, 9)).grid(
            row=row, column=0, sticky="w", padx=(24, 8), pady=4)
        box = tk.Frame(top, bg=BG)
        box.grid(row=row, column=1, sticky="w")
        for diff in DIFFICULTIES:
            tk.Radiobutton(box, text=diff.name, value=diff.key, variable=self.diff,
                           bg=BG, fg=TEXT, selectcolor=CARD, activebackground=BG,
                           activeforeground=TEXT, font=(FONT, 9),
                           highlightthickness=0).pack(side="left", padx=(0, 10))

        row += 1
        tk.Label(top, text="初始资金", bg=BG, fg=MUTED, font=(FONT, 9)).grid(
            row=row, column=0, sticky="w", padx=(24, 8), pady=4)
        box = tk.Frame(top, bg=BG)
        box.grid(row=row, column=1, sticky="w")
        for label, value in (("10万", "100000"), ("50万", "500000"),
                             ("100万", "1000000"), ("500万", "5000000")):
            tk.Radiobutton(box, text=label, value=value, variable=self.cash, bg=BG,
                           fg=TEXT, selectcolor=CARD, activebackground=BG,
                           activeforeground=TEXT, font=(FONT, 9),
                           highlightthickness=0).pack(side="left", padx=(0, 10))

        row += 1
        tk.Label(top, text="节奏", bg=BG, fg=MUTED, font=(FONT, 9)).grid(
            row=row, column=0, sticky="w", padx=(24, 8), pady=4)
        box = tk.Frame(top, bg=BG)
        box.grid(row=row, column=1, sticky="w")
        for label, seconds in PACES_PRESETS:
            tk.Radiobutton(box, text=label, value=str(seconds), variable=self.pace,
                           bg=BG, fg=TEXT, selectcolor=CARD, activebackground=BG,
                           activeforeground=TEXT, font=(FONT, 9),
                           highlightthickness=0).pack(side="left", padx=(0, 8))
        row += 1
        tk.Label(top, text="节奏 = 一个交易日走多少现实时间：悠闲 10 分钟 / 慢 5 分钟 / "
                           "标准 2 分钟 / 快 60 秒 / 极速 15 秒\n"
                           "游戏中随时可改，也可以暂停后按“进5分”逐分钟推进",
                 bg=BG, fg=MUTED, font=(FONT, 8), justify="left").grid(
            row=row, column=1, sticky="w", pady=(0, 4))

        row += 1
        tk.Label(top, text="交易日数", bg=BG, fg=MUTED, font=(FONT, 9)).grid(
            row=row, column=0, sticky="w", padx=(24, 8), pady=4)
        tk.Entry(top, textvariable=self.days, width=10, bg=CARD, fg=TEXT,
                 insertbackground=TEXT, relief="flat", font=(FONT, 9)).grid(
            row=row, column=1, sticky="w")

        row += 1
        tk.Label(top, text="随机种子", bg=BG, fg=MUTED, font=(FONT, 9)).grid(
            row=row, column=0, sticky="w", padx=(24, 8), pady=4)
        tk.Entry(top, textvariable=self.seed, width=14, bg=CARD, fg=TEXT,
                 insertbackground=TEXT, relief="flat", font=(FONT, 9)).grid(
            row=row, column=1, sticky="w")
        tk.Label(top, text="留空则每次随机（相同种子可复现同一段行情）", bg=BG, fg=MUTED,
                 font=(FONT, 8)).grid(row=row + 1, column=1, sticky="w", pady=(0, 6))

        row += 2
        self.error = tk.Label(top, text="", bg=BG, fg=UP, font=(FONT, 9))
        self.error.grid(row=row, column=0, columnspan=2, sticky="w", padx=24)
        row += 1
        tk.Button(top, text="开始交易", command=self._ok, bg=ACCENT, fg="#ffffff",
                  activebackground="#2f6fd0", activeforeground="#ffffff",
                  relief="flat", font=(FONT, 11, "bold"), width=14).grid(
            row=row, column=0, columnspan=2, pady=(4, 18))

        top.protocol("WM_DELETE_WINDOW", self._cancel)
        top.update_idletasks()
        top.geometry("+%d+%d" % ((top.winfo_screenwidth() - top.winfo_width()) // 2,
                                 (top.winfo_screenheight() - top.winfo_height()) // 3))
        top.deiconify()
        top.lift()
        top.focus_force()
        top.grab_set()

    def _ok(self):
        try:
            cash = float(self.cash.get())
            days = int(self.days.get())
            seed_text = self.seed.get().strip()
            seed = int(seed_text) if seed_text else None
        except ValueError:
            self.error.configure(text="初始资金/交易日数/种子必须是数字")
            return
        if cash < 10000:
            self.error.configure(text="初始资金至少 10,000 元")
            return
        if not 5 <= days <= 2000:
            self.error.configure(text="交易日数需在 5 ~ 2000 之间")
            return
        self.result = {
            "market_key": self.market.get(), "difficulty_key": self.diff.get(),
            "initial_cash": cash, "max_days": days, "seed": seed,
            "pace_seconds": int(self.pace.get()),
        }
        self.top.destroy()

    def _cancel(self):
        self.result = None
        self.top.destroy()


class StockGameUI:
    def __init__(self, root: tk.Tk, game: Game,
                 pace_seconds: int = DEFAULT_DAY_SECONDS):
        self.root = root
        self.game = game
        self.running = True
        self.paused = False
        self.day_seconds = pace_seconds       # 一个交易日走多少现实秒
        self.speed = ticks_per_second(pace_seconds, game.market.total_minutes)
        self.auto_next = tk.BooleanVar(value=True)
        self.tick_acc = 0.0
        self.ui_acc = 0.0
        self._last = time.perf_counter()
        self._last_render = 0.0
        self._error_streak = 0
        self._closed_at = None
        self._event_pos = 0
        self._selected = game.market.order_codes[0]
        self._watch_codes = list(game.market.order_codes)
        self._sort_key = None
        self._sort_reverse = True
        self._trade_rows = 0
        self._ticks_stamp = None
        self._chart_dirty = True

        self._setup_style()
        root.title("股票模拟交易 · Stock Trading Simulator")
        root.configure(bg=BG)
        root.geometry("1400x900")
        root.minsize(1200, 780)

        self._build_topbar()
        # 打包顺序很重要：先放固定高度的状态栏和底部面板，最后才放自适应的主体，
        # 否则主体会先把空间抢光，底部表格被挤成一条缝。
        self._build_statusbar(root)
        self._build_bottom(root)

        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True, padx=8, pady=(4, 0))
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        self._build_watchlist(body)
        self._build_chart(body)
        self._build_right(body)

        self._bind_keys()
        self.select_stock(self._selected)
        self.set_pace(self.day_seconds)     # 显示当前节奏并同步下拉框
        self.refresh_all()
        self.root.after(FRAME_MS, self.loop)

    # ------------------------------------------------------------ 样式
    def _setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Treeview", background=CARD, fieldbackground=CARD,
                        foreground=TEXT, rowheight=21, borderwidth=0,
                        font=(FONT, 9))
        style.configure("Treeview.Heading", background="#1b2431", foreground=MUTED,
                        relief="flat", font=(FONT, 9))
        style.map("Treeview", background=[("selected", "#25406b")],
                  foreground=[("selected", "#ffffff")])
        style.map("Treeview.Heading", background=[("active", "#22303f")])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#161d29", foreground=MUTED,
                        padding=(14, 5), font=(FONT, 9))
        style.map("TNotebook.Tab", background=[("selected", "#22303f")],
                  foreground=[("selected", TEXT)])
        style.configure("TSeparator", background=BORDER)
        # 节奏下拉框（ttk 的下拉列表颜色要靠 Tk 选项数据库设置）
        style.configure("Pace.TCombobox", fieldbackground=CARD, background="#1c2532",
                        foreground=TEXT, arrowcolor=TEXT, borderwidth=0, padding=2)
        # readonly 状态在 clam 主题下有单独的配色分支，必须用 map 覆盖，否则是浅灰底
        style.map("Pace.TCombobox",
                  fieldbackground=[("readonly", CARD), ("disabled", CARD), ("!readonly", CARD)],
                  foreground=[("readonly", TEXT), ("!readonly", TEXT)],
                  background=[("readonly", "#1c2532"), ("active", "#2a3547")],
                  arrowcolor=[("readonly", TEXT), ("active", ACCENT)],
                  bordercolor=[("readonly", BORDER)],
                  lightcolor=[("readonly", BORDER)], darkcolor=[("readonly", BORDER)])
        self.root.option_add("*TCombobox*Listbox.background", CARD)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    # ------------------------------------------------------------ 顶栏
    def _build_topbar(self):
        bar = tk.Frame(self.root, bg=PANEL, height=52)
        bar.pack(fill="x", side="top")
        inner = tk.Frame(bar, bg=PANEL)
        inner.pack(fill="x", padx=12, pady=8)

        self.var_day = tk.StringVar()
        self.var_clock = tk.StringVar()
        self.var_index = tk.StringVar()
        self.var_equity = tk.StringVar()
        self.var_day_pnl = tk.StringVar()
        self.var_return = tk.StringVar()

        def block(title, var, width=12, color=TEXT):
            frame = tk.Frame(inner, bg=PANEL)
            frame.pack(side="left", padx=(0, 12))
            tk.Label(frame, text=title, bg=PANEL, fg=MUTED,
                     font=(FONT, 8)).pack(anchor="w")
            label = tk.Label(frame, textvariable=var, bg=PANEL, fg=color,
                             font=(FONT, 11, "bold"), width=width, anchor="w")
            label.pack(anchor="w")
            return label

        # 顶栏只放最关键的几项；可用资金/融资负债等在右侧“账户”面板里另有显示，
        # 否则加上节奏控件后这一行会放不下、把右侧按钮挤出窗口。
        block("交易日 / 时间", self.var_day, 18)
        self.lbl_clock = tk.Label(inner, textvariable=self.var_clock, bg=PANEL, fg=YELLOW,
                                  font=(FONT, 11, "bold"))
        self.lbl_clock.pack(side="left", padx=(0, 12))
        self.lbl_index = block("指数", self.var_index, 17)
        block("总资产", self.var_equity, 11)
        self.lbl_day_pnl = block("当日盈亏", self.var_day_pnl, 10)
        self.lbl_return = block("累计收益", self.var_return, 10)

        controls = tk.Frame(inner, bg=PANEL)
        controls.pack(side="right")
        self.btn_pause = tk.Button(controls, text="暂停", command=self.toggle_pause,
                                   bg="#1c2532", fg=TEXT, relief="flat", width=6,
                                   activebackground="#2a3547", activeforeground=TEXT,
                                   font=(FONT, 9))
        self.btn_pause.pack(side="left", padx=3)
        self.btn_next = tk.Button(controls, text="下一日", command=self.next_day,
                                  bg="#1c2532", fg=TEXT, relief="flat", width=6,
                                  activebackground="#2a3547", activeforeground=TEXT,
                                  font=(FONT, 9))
        self.btn_next.pack(side="left", padx=3)

        self.btn_step = tk.Button(controls, text="进5分", command=lambda: self.step(5),
                                  bg="#1c2532", fg=TEXT, relief="flat", width=5,
                                  activebackground="#2a3547", activeforeground=TEXT,
                                  font=(FONT, 9))
        self.btn_step.pack(side="left", padx=(3, 8))

        # 节奏：直接按“一个交易日多少秒”来选，范围 5 秒 ~ 10 分钟
        tk.Label(controls, text="节奏", bg=PANEL, fg=MUTED,
                 font=(FONT, 8)).pack(side="left", padx=(0, 4))
        self.var_pace = tk.StringVar()
        self.cmb_pace = ttk.Combobox(controls, textvariable=self.var_pace, width=11,
                                     state="readonly", style="Pace.TCombobox",
                                     font=(FONT, 9),
                                     values=[pace_text(s) for s in PACES_SECONDS])
        self.cmb_pace.pack(side="left", padx=(0, 8))
        self.cmb_pace.bind("<<ComboboxSelected>>", self._on_pace_selected)

        tk.Checkbutton(controls, text="自动", variable=self.auto_next,
                       bg=PANEL, fg=MUTED, selectcolor=CARD, activebackground=PANEL,
                       activeforeground=TEXT, font=(FONT, 9), highlightthickness=0,
                       command=self._sync_pace_label).pack(side="left", padx=(0, 4))

        self.var_regime = tk.StringVar()
        tk.Label(inner, textvariable=self.var_regime, bg=PANEL, fg=ACCENT,
                 font=(FONT, 10, "bold")).pack(side="right", padx=14)

    # ------------------------------------------------------------ 自选股
    def _build_watchlist(self, parent):
        frame = tk.Frame(parent, bg=PANEL, width=334)
        frame.grid(row=0, column=0, sticky="nsw", padx=(0, 6))
        frame.grid_propagate(False)
        tk.Label(frame, text="自选股 / 行情（点表头排序）", bg=PANEL, fg=MUTED,
                 font=(FONT, 9, "bold")).pack(anchor="w", padx=8, pady=(6, 2))

        columns = ("name", "last", "pct", "amount", "hold")
        self.watch = ttk.Treeview(frame, columns=columns, show="headings",
                                  selectmode="browse", height=22)
        widths = {"name": 104, "last": 56, "pct": 58, "amount": 66, "hold": 40}
        titles = {"name": "名称", "last": "现价", "pct": "涨跌幅",
                  "amount": "成交额", "hold": "持仓"}
        for key in columns:
            # 点表头排序，再点一次反向
            self.watch.heading(key, text=titles[key],
                               command=lambda k=key: self.sort_watchlist(k))
            self.watch.column(key, width=widths[key],
                              anchor="center" if key != "name" else "w")
        self.watch.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.watch.tag_configure("up", foreground=UP)
        self.watch.tag_configure("down", foreground=DOWN)
        self.watch.tag_configure("flat", foreground=TEXT)
        self.watch.bind("<<TreeviewSelect>>", self._on_watch_select)

    # ------------------------------------------------------------ 图表
    def _build_chart(self, parent):
        frame = tk.Frame(parent, bg=BG)
        frame.grid(row=0, column=1, sticky="nsew")
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        toolbar = tk.Frame(frame, bg=PANEL, height=30)
        toolbar.grid(row=0, column=0, sticky="ew")
        self.var_chart_title = tk.StringVar()
        tk.Label(toolbar, textvariable=self.var_chart_title, bg=PANEL, fg=TEXT,
                 font=(FONT, 10, "bold")).pack(side="left", padx=10)
        self.btn_mode = tk.Button(toolbar, text="切换到日K", command=self.toggle_mode,
                                  bg="#1c2532", fg=TEXT, relief="flat", width=10,
                                  activebackground="#2a3547", activeforeground=TEXT,
                                  font=(FONT, 9))
        self.btn_mode.pack(side="right", padx=6, pady=3)
        self.var_chart_info = tk.StringVar()
        tk.Label(toolbar, textvariable=self.var_chart_info, bg=PANEL, fg=MUTED,
                 font=(FONT, 9)).pack(side="right", padx=10)

        self.chart_canvas = tk.Canvas(frame, bg="#0b0e14", highlightthickness=1,
                                      highlightbackground=BORDER)
        self.chart_canvas.grid(row=1, column=0, sticky="nsew")
        self.chart = Chart(self.chart_canvas, self.game)
        self.chart_canvas.bind("<Configure>", lambda e: self.chart.redraw())

    # ------------------------------------------------------------ 右侧
    def _build_right(self, parent):
        frame = tk.Frame(parent, bg=BG, width=352)
        frame.grid(row=0, column=2, sticky="nse", padx=(6, 0))
        frame.grid_propagate(False)
        self._build_book_panel(frame)       # 五档盘口在最上面，和真实行情软件一致
        self._build_order_panel(frame)
        tk.Label(frame,
                 text="快捷键：B 买入 S 卖出 空格 暂停 N 下一日\n"
                      "          , 进1分  . 进5分  [ ] 节奏  K 切换图表",
                 bg=BG, fg=MUTED, font=(FONT, 8), justify="left").pack(
            anchor="w", padx=6, pady=(6, 0))

    # ------------------------------------------------------------ 五档盘口
    def _build_book_panel(self, parent):
        frame = tk.LabelFrame(parent, text=" 五档盘口 ", bg=PANEL, fg=MUTED,
                              font=(FONT, 9, "bold"), bd=1, relief="solid",
                              labelanchor="nw")
        frame.pack(fill="x", padx=2, pady=(0, 8))
        self.book_canvas = tk.Canvas(frame, bg="#0e131b", highlightthickness=0,
                                     width=340, height=10 * 17 + 16)
        self.book_canvas.pack(fill="x", padx=6, pady=(4, 6))
        self.book_canvas.bind("<Button-1>", self._on_book_click)
        self._book_levels = []              # 每行的 (y0, y1, side, 序号)
        self._book_hint = tk.StringVar()
        tk.Label(frame, textvariable=self._book_hint, bg=PANEL, fg=MUTED,
                 font=(FONT, 8), anchor="w").pack(fill="x", padx=8, pady=(0, 6))

    def _on_book_click(self, event):
        """点盘口某一档，把价格填进下单框。"""
        for (y0, y1, side, index) in self._book_levels:
            if y0 <= event.y <= y1:
                stock = self.game.market.stocks[self._selected]
                book = stock.asks if side == "ask" else stock.bids
                if index < len(book):
                    self.var_kind.set("limit")
                    self._sync_price_state()
                    self.var_price.set("%.2f" % book[index][0])
                    self.var_status.set("已选取%s%d 价 %.2f"
                                        % ("卖" if side == "ask" else "买",
                                           index + 1, book[index][0]))
                return


    def _build_order_panel(self, parent):
        frame = tk.LabelFrame(parent, text=" 下单 ", bg=PANEL, fg=MUTED,
                              font=(FONT, 9, "bold"), bd=1, relief="solid",
                              labelanchor="nw")
        frame.pack(fill="x", padx=2, pady=(0, 8))

        head = tk.Frame(frame, bg=PANEL)
        head.pack(fill="x", padx=8, pady=(8, 4))
        self.var_order_stock = tk.StringVar()
        self.var_order_price = tk.StringVar()
        tk.Label(head, textvariable=self.var_order_stock, bg=PANEL, fg=TEXT,
                 font=(FONT, 10, "bold")).pack(side="left")
        self.lbl_order_price = tk.Label(head, textvariable=self.var_order_price,
                                        bg=PANEL, fg=TEXT, font=(FONT, 11, "bold"))
        self.lbl_order_price.pack(side="right")

        kind_row = tk.Frame(frame, bg=PANEL)
        kind_row.pack(fill="x", padx=8, pady=2)
        self.var_kind = tk.StringVar(value="limit")
        for text, value in (("限价委托", "limit"), ("市价委托", "market")):
            tk.Radiobutton(kind_row, text=text, value=value, variable=self.var_kind,
                           bg=PANEL, fg=TEXT, selectcolor=CARD, activebackground=PANEL,
                           activeforeground=TEXT, font=(FONT, 9),
                           highlightthickness=0, command=self._sync_price_state).pack(
                side="left", padx=(0, 10))

        price_row = tk.Frame(frame, bg=PANEL)
        price_row.pack(fill="x", padx=8, pady=3)
        tk.Label(price_row, text="价格", bg=PANEL, fg=MUTED,
                 font=(FONT, 9), width=4, anchor="w").pack(side="left")
        self.var_price = tk.StringVar()
        self.ent_price = tk.Entry(price_row, textvariable=self.var_price, width=11,
                                  bg=CARD, fg=TEXT, insertbackground=TEXT, relief="flat",
                                  font=(FONT, 10), justify="center")
        self.ent_price.pack(side="left", padx=4)
        for text, delta in (("−", -1), ("+", 1)):
            tk.Button(price_row, text=text, width=2, relief="flat", bg="#1c2532",
                      fg=TEXT, activebackground="#2a3547", activeforeground=TEXT,
                      command=lambda d=delta: self._bump_price(d)).pack(side="left", padx=1)
        tk.Button(price_row, text="现价", relief="flat", bg="#1c2532", fg=TEXT,
                  activebackground="#2a3547", activeforeground=TEXT, font=(FONT, 8),
                  command=self._price_to_last).pack(side="left", padx=3)

        qty_row = tk.Frame(frame, bg=PANEL)
        qty_row.pack(fill="x", padx=8, pady=3)
        tk.Label(qty_row, text="数量", bg=PANEL, fg=MUTED,
                 font=(FONT, 9), width=4, anchor="w").pack(side="left")
        self.var_qty = tk.StringVar(value="100")
        tk.Entry(qty_row, textvariable=self.var_qty, width=11, bg=CARD, fg=TEXT,
                 insertbackground=TEXT, relief="flat", font=(FONT, 10),
                 justify="center").pack(side="left", padx=4)
        tk.Label(qty_row, text="股", bg=PANEL, fg=MUTED, font=(FONT, 9)).pack(side="left")

        quick = tk.Frame(frame, bg=PANEL)
        quick.pack(fill="x", padx=8, pady=(1, 4))
        for label, action in (("全仓", "all"), ("1/2", "half"), ("1/3", "third"),
                              ("+100", "plus"), ("-100", "minus")):
            tk.Button(quick, text=label, relief="flat", bg="#1c2532", fg=TEXT,
                      activebackground="#2a3547", activeforeground=TEXT, font=(FONT, 8),
                      width=5, command=lambda a=action: self._quick_qty(a)).pack(
                side="left", padx=2)

        info = tk.Frame(frame, bg=PANEL)
        info.pack(fill="x", padx=8, pady=(2, 2))
        self.var_trade_info = tk.StringVar()
        tk.Label(info, textvariable=self.var_trade_info, bg=PANEL, fg=MUTED,
                 font=(FONT, 8), justify="left", anchor="w").pack(fill="x")

        margin_row = tk.Frame(frame, bg=PANEL)
        margin_row.pack(fill="x", padx=8, pady=(2, 4))
        self.var_margin = tk.BooleanVar(value=False)
        self.chk_margin = tk.Checkbutton(
            margin_row, text="融资买入（杠杆）", variable=self.var_margin, bg=PANEL,
            fg=TEXT, selectcolor=CARD, activebackground=PANEL, activeforeground=TEXT,
            font=(FONT, 9), highlightthickness=0)
        self.chk_margin.pack(side="left")

        buttons = tk.Frame(frame, bg=PANEL)
        buttons.pack(fill="x", padx=8, pady=(2, 8))
        tk.Button(buttons, text="买入 B", command=lambda: self.place_order("buy"),
                  bg="#b8353d", fg="#ffffff", activebackground="#d34b53",
                  activeforeground="#ffffff", relief="flat",
                  font=(FONT, 11, "bold")).pack(side="left", fill="x", expand=True,
                                                padx=(0, 4))
        tk.Button(buttons, text="卖出 S", command=lambda: self.place_order("sell"),
                  bg="#1f7a53", fg="#ffffff", activebackground="#2b9c6b",
                  activeforeground="#ffffff", relief="flat",
                  font=(FONT, 11, "bold")).pack(side="left", fill="x", expand=True,
                                                padx=(4, 0))

    def _build_account_panel(self, notebook):
        """账户明细放在底部标签页里（右侧位置让给五档盘口）。"""
        frame = tk.Frame(notebook, bg=CARD)
        notebook.add(frame, text=" 账户 ")
        self.account_vars = {}
        rows = [
            ("总资产", "equity"), ("持仓市值", "market_value"),
            ("可用资金", "available"), ("浮动盈亏", "unrealized"),
            ("已实现盈亏", "realized"), ("融资负债", "debt"),
            ("维持担保比例", "margin_ratio"), ("累计收益率", "return_pct"),
            ("同期指数", "index_return"), ("税费合计", "costs"),
        ]
        grid = tk.Frame(frame, bg=CARD)
        grid.pack(fill="both", expand=True, padx=16, pady=8)
        for i, (label, key) in enumerate(rows):
            r, c = divmod(i, 5)
            cell = tk.Frame(grid, bg=CARD)
            cell.grid(row=r, column=c, sticky="w", padx=(0, 44), pady=3)
            tk.Label(cell, text=label, bg=CARD, fg=MUTED,
                     font=(FONT, 8)).pack(anchor="w")
            var = tk.StringVar(value="—")
            lbl = tk.Label(cell, textvariable=var, bg=CARD, fg=TEXT,
                           font=(FONT, 12, "bold"))
            lbl.pack(anchor="w")
            self.account_vars[key] = (var, lbl)
        self.var_margin_status = tk.StringVar()
        tk.Label(frame, textvariable=self.var_margin_status, bg=CARD, fg=YELLOW,
                 font=(FONT, 9), anchor="w").pack(fill="x", padx=16, pady=(0, 6))

    # ------------------------------------------------------------ 底部
    def _build_bottom(self, root):
        frame = tk.Frame(root, bg=BG, height=196)
        frame.pack(fill="x", side="bottom", padx=8, pady=(4, 0))
        frame.pack_propagate(False)
        notebook = ttk.Notebook(frame)
        notebook.pack(fill="both", expand=True)
        self.notebook = notebook

        self.pos_tree = self._make_tree(notebook, "持仓", (
            ("code", "代码", 70), ("name", "名称", 90), ("shares", "持仓", 70),
            ("available", "可用", 70), ("avg_cost", "成本价", 74),
            ("last", "现价", 74), ("market_value", "市值", 92),
            ("day_pnl", "当日盈亏", 92), ("unrealized", "浮动盈亏", 92),
            ("pnl_pct", "收益率", 70),
        ))
        self.order_tree = self._make_tree(notebook, "委托", (
            ("time", "时间", 54), ("code", "代码", 66), ("name", "名称", 86),
            ("side", "方向", 50), ("kind", "类型", 50), ("price", "委托价", 74),
            ("qty", "数量", 66), ("filled", "已成交", 66),
            ("avg_price", "成交均价", 74), ("status", "状态", 110),
        ))
        self.trade_tree = self._make_tree(notebook, "成交", (
            ("day", "日", 40), ("time", "时间", 54), ("code", "代码", 66),
            ("name", "名称", 86), ("side", "方向", 50), ("price", "成交价", 74),
            ("qty", "数量", 66), ("amount", "金额", 96), ("fees", "费用", 70),
            ("realized", "实现盈亏", 90),
        ))
        # 逐笔成交明细（分时成交），只显示当前选中标的
        self.tick_tree = self._make_tree(notebook, "逐笔", (
            ("time", "时间", 90), ("price", "价格", 100), ("lots", "手数", 90),
            ("side", "方向", 80), ("amount", "金额", 110),
        ))
        self._build_account_panel(notebook)

        log_frame = tk.Frame(notebook, bg=CARD)
        notebook.add(log_frame, text=" 日志 ")
        self.log_text = tk.Text(log_frame, bg=CARD, fg=TEXT, relief="flat",
                                font=(FONT, 9), wrap="none", height=8,
                                insertbackground=TEXT)
        scroll = tk.Scrollbar(log_frame, command=self.log_text.yview, relief="flat")
        self.log_text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True)
        for tag, color in (("up", UP), ("down", DOWN), ("warn", YELLOW),
                           ("news", "#7fb2ff"), ("sys", MUTED)):
            self.log_text.tag_configure(tag, foreground=color)

        actions = tk.Frame(frame, bg=BG)
        actions.pack(fill="x", pady=(3, 0))
        tk.Button(actions, text="撤销选中委托", command=self.cancel_selected,
                  bg="#1c2532", fg=TEXT, relief="flat", font=(FONT, 9),
                  activebackground="#2a3547", activeforeground=TEXT).pack(side="left")
        tk.Button(actions, text="全部撤单", command=self.cancel_all,
                  bg="#1c2532", fg=TEXT, relief="flat", font=(FONT, 9),
                  activebackground="#2a3547", activeforeground=TEXT).pack(side="left", padx=6)
        self.var_footer = tk.StringVar()
        tk.Label(actions, textvariable=self.var_footer, bg=BG, fg=MUTED,
                 font=(FONT, 9)).pack(side="left", padx=12)

    def _make_tree(self, notebook, title, columns):
        frame = tk.Frame(notebook, bg=CARD)
        notebook.add(frame, text=" %s " % title)
        keys = [c[0] for c in columns]
        tree = ttk.Treeview(frame, columns=keys, show="headings", height=7)
        for key, label, width in columns:
            tree.heading(key, text=label)
            anchor = "w" if key in ("name", "status") else "center"
            tree.column(key, width=width, anchor=anchor)
        tree.tag_configure("up", foreground=UP)
        tree.tag_configure("down", foreground=DOWN)
        tree.pack(fill="both", expand=True)
        return tree

    def _build_statusbar(self, root):
        bar = tk.Frame(root, bg=PANEL, height=24)
        bar.pack(fill="x", side="bottom")
        self.var_status = tk.StringVar(value="准备就绪")
        tk.Label(bar, textvariable=self.var_status, bg=PANEL, fg=MUTED,
                 font=(FONT, 9), anchor="w").pack(fill="x", padx=10)

    # ------------------------------------------------------------ 键盘
    def _bind_keys(self):
        root = self.root
        root.bind("<space>", lambda e: self._key(self.toggle_pause))
        root.bind("<Key-b>", lambda e: self._key(lambda: self.place_order("buy")))
        root.bind("<Key-B>", lambda e: self._key(lambda: self.place_order("buy")))
        root.bind("<Key-s>", lambda e: self._key(lambda: self.place_order("sell")))
        root.bind("<Key-S>", lambda e: self._key(lambda: self.place_order("sell")))
        root.bind("<Key-n>", lambda e: self._key(self.next_day))
        root.bind("<Key-N>", lambda e: self._key(self.next_day))
        root.bind("<Key-k>", lambda e: self._key(self.toggle_mode))
        root.bind("<Key-K>", lambda e: self._key(self.toggle_mode))
        # 1~5 对应开局设置里的五档节奏，6 额外给一个 10 秒/日
        quick = [seconds for _label, seconds in PACES_PRESETS] + [10]
        for i, seconds in enumerate(quick, start=1):
            root.bind("<Key-%d>" % i,
                      lambda e, s=seconds: self._key(lambda: self.set_pace(s)))
        root.bind("<bracketleft>", lambda e: self._key(lambda: self.nudge_pace(-1)))
        root.bind("<bracketright>", lambda e: self._key(lambda: self.nudge_pace(1)))
        root.bind("<comma>", lambda e: self._key(lambda: self.step(1)))
        root.bind("<period>", lambda e: self._key(lambda: self.step(5)))
        root.bind("<Escape>", lambda e: root.destroy())

    def _key(self, action):
        """输入框获得焦点时不响应快捷键。"""
        widget = self.root.focus_get()
        if isinstance(widget, (tk.Entry, tk.Text)):
            return
        action()

    # ------------------------------------------------------------ 交互
    def _on_watch_select(self, _event=None):
        selection = self.watch.selection()
        if not selection:
            return
        code = selection[0]
        if code == self._selected:
            return          # 已经在看这只，直接返回，避免 selection_set 造成事件自激循环
        self.select_stock(code)

    def select_stock(self, code: str):
        self._selected = code
        stock = self.game.market.stocks[code]
        self.chart.show(code)
        self.var_order_stock.set("%s %s" % (stock.code, stock.name))
        self.var_chart_title.set("%s %s" % (stock.code, stock.name))
        # 仅在选中项确实不同时才设置，否则会不断生成 <<TreeviewSelect>> 事件
        if self.watch.exists(code) and self.watch.selection() != (code,):
            self.watch.selection_set(code)
        self._price_to_last()
        self._refresh_trade_info()

    def sort_watchlist(self, key: str):
        """点表头排序：同一列再点一次反向。"""
        if self._sort_key == key:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_key, self._sort_reverse = key, True
        market = self.game.market
        positions = self.game.account.positions

        def value(code: str):
            stock = market.stocks[code]
            if key == "name":
                return stock.code
            if key == "last":
                return stock.last
            if key == "pct":
                return stock.change_pct
            if key == "amount":
                return stock.amount
            pos = positions.get(code)
            return pos.shares if pos else 0

        self._watch_codes.sort(key=value, reverse=self._sort_reverse)
        self.watch.delete(*self.watch.get_children())
        self.refresh_quotes()
        label = {"name": "代码", "last": "现价", "pct": "涨跌幅",
                 "amount": "成交额", "hold": "持仓"}[key]
        self.var_status.set("自选股按%s排序（%s）"
                            % (label, "降序" if self._sort_reverse else "升序"))

    def toggle_mode(self):
        self.chart.toggle_mode()
        self.btn_mode.configure(text="切换到分时" if self.chart.mode == "day" else "切换到日K")

    def set_pace(self, day_seconds: int):
        """设置节奏：一个交易日走 day_seconds 现实秒。"""
        self.day_seconds = max(1, int(day_seconds))
        self.speed = ticks_per_second(self.day_seconds, self.game.market.total_minutes)
        self.paused = False
        self.btn_pause.configure(text="暂停")
        self._sync_pace_label()
        self.var_status.set(
            "节奏：%s（每秒推进 %.2f 个交易分钟）"
            % (pace_text(self.day_seconds), self.speed))

    def _on_pace_selected(self, _event=None):
        index = self.cmb_pace.current()
        if 0 <= index < len(PACES_SECONDS):
            self.set_pace(PACES_SECONDS[index])

    def nudge_pace(self, direction: int):
        """[ / ] 在节奏表里向前/向后切换（表是升序，越靠后越慢）。"""
        values = PACES_SECONDS
        index = min(range(len(values)), key=lambda i: abs(values[i] - self.day_seconds))
        index = min(max(index + direction, 0), len(values) - 1)
        self.set_pace(values[index])

    def _sync_pace_label(self):
        """顶栏同步显示节奏与“自动进入下一日”状态。"""
        if not hasattr(self, "var_pace"):
            return
        text = pace_text(self.day_seconds)
        if not self.auto_next.get():
            text += " · 停"
        self.var_pace.set(text)
        self.cmb_pace.configure(foreground=YELLOW if not self.auto_next.get() else TEXT)

    def step(self, minutes: int = 5):
        """手动推进若干个交易分钟（不影响当前是否暂停）。"""
        if self.game.phase != "trading":
            return
        for _ in range(max(1, minutes)):
            self.game.tick()
            if self.game.phase != "trading":
                break
        self._chart_dirty = True
        self.var_status.set("单步推进 %d 个交易分钟 → %s"
                            % (minutes, self.clock_text()))

    def clock_text(self) -> str:
        from .trading import minute_to_clock
        return minute_to_clock(self.game.market.minute, self.game.rules,
                               self.game.market.total_minutes)

    def toggle_pause(self):
        self.paused = not self.paused
        self.btn_pause.configure(text="继续" if self.paused else "暂停")
        self.var_status.set("已暂停" if self.paused else "已继续")

    def next_day(self):
        if self.game.phase == "closed":
            self.game.advance_day()
            self._closed_at = None
            self.consume_events()
            self._chart_dirty = True

    def _sync_price_state(self):
        market = self.var_kind.get() == "market"
        self.ent_price.configure(state="disabled" if market else "normal",
                                 disabledbackground="#0e131b", disabledforeground=MUTED)

    def _bump_price(self, direction: int):
        try:
            price = float(self.var_price.get())
        except ValueError:
            price = self.game.market.stocks[self._selected].last
        stock = self.game.market.stocks[self._selected]
        price = round(price + direction * self.game.rules.tick, 2)
        price = min(max(price, stock.limit_down), stock.limit_up)
        self.var_price.set("%.2f" % price)

    def _price_to_last(self):
        stock = self.game.market.stocks[self._selected]
        self.var_price.set("%.2f" % stock.last)

    def _quick_qty(self, action: str):
        stock = self.game.market.stocks[self._selected]
        lot = max(1, self.game.rules.lot_size)
        try:
            current = int(float(self.var_qty.get()))
        except ValueError:
            current = 0
        if action == "plus":
            qty = current + lot
        elif action == "minus":
            qty = max(0, current - lot)
        elif action == "all":
            price = self._effective_price()
            power = self.game.account.buying_power(
                self.game.prices(), self.var_margin.get())
            qty = int(power / max(price, 0.01) / lot) * lot
        else:
            divisor = 2 if action == "half" else 3
            price = self._effective_price()
            power = self.game.account.buying_power(
                self.game.prices(), self.var_margin.get())
            qty = int(power / max(price, 0.01) / lot / divisor) * lot
        self.var_qty.set(str(max(0, qty)))

    def _effective_price(self) -> float:
        stock = self.game.market.stocks[self._selected]
        if self.var_kind.get() == "market":
            return stock.last
        try:
            return max(0.01, float(self.var_price.get()))
        except ValueError:
            return stock.last

    def place_order(self, side: str):
        if self.game.phase != "trading":
            self.var_status.set("当前非交易时段，无法委托")
            return
        try:
            qty = int(float(self.var_qty.get()))
        except ValueError:
            self.var_status.set("委托数量不合法")
            return
        kind = self.var_kind.get()
        price = 0.0 if kind == "market" else self._effective_price()
        ok, msg, _order = self.game.submit(self._selected, side, qty, kind, price,
                                           self.var_margin.get())
        self.var_status.set(msg)
        self.consume_events()
        self.refresh_tables()
        self._refresh_trade_info()

    def cancel_selected(self):
        selection = self.order_tree.selection()
        if not selection:
            self.var_status.set("请先在委托列表中选择一笔委托")
            return
        try:
            order_id = int(selection[0])
        except ValueError:
            return
        ok, msg = self.game.cancel(order_id)
        self.var_status.set(msg)
        self.consume_events()
        self.refresh_tables()

    def cancel_all(self):
        count = self.game.cancel_all()
        self.var_status.set("已撤销 %d 笔委托" % count)
        self.consume_events()
        self.refresh_tables()

    # ------------------------------------------------------------ 事件
    def consume_events(self):
        events = self.game.events
        if self._event_pos >= len(events):
            return
        for text in events[self._event_pos:]:
            tag = "sys"
            if "成交" in text or "买入" in text:
                tag = "up"
            elif "卖出" in text or "撤单" in text:
                tag = "down"
            if "【风控】" in text or "【终局】" in text:
                tag = "warn"
            if "【消息】" in text:
                tag = "news"
            self.log_text.insert("end", text + "\n", tag)
            self.var_status.set(text)
        self._event_pos = len(events)
        # 只保留最近 1200 行：长时间挂机时 Text 控件不会越用越慢
        lines = int(self.log_text.index("end-1c").split(".")[0])
        if lines > 1400:
            self.log_text.delete("1.0", "%d.0" % (lines - 1200))
        self.log_text.see("end")

    # ------------------------------------------------------------ 刷新
    def _set_var(self, key, text, color=None):
        var, label = self.account_vars[key]
        var.set(text)
        if color:
            label.configure(fg=color)

    def _pnl_color(self, value: float) -> str:
        return UP if value > 0.005 else (DOWN if value < -0.005 else TEXT)

    def refresh_quotes(self):
        selected = self._selected
        for code in self._watch_codes:
            stock = self.game.market.stocks[code]
            pos = self.game.account.positions.get(code)
            holding = pos.shares if pos else 0
            values = (stock.name, "%.2f" % stock.last, "%+.2f%%" % stock.change_pct,
                      fmt_money(stock.amount) if stock.amount else "—",
                      holding if holding else "—")
            tag = "up" if stock.change_pct > 0 else ("down" if stock.change_pct < 0 else "flat")
            if self.watch.exists(code):
                self.watch.item(code, values=values, tags=(tag,))
            else:
                self.watch.insert("", "end", iid=code, values=values, tags=(tag,))
        if self.watch.exists(selected) and self.watch.selection() != (selected,):
            self.watch.selection_set(selected)

        stock = self.game.market.stocks[selected]
        color = self._pnl_color(stock.change_pct)
        self.var_order_price.set("%.2f  %+.2f%%" % (stock.last, stock.change_pct))
        self.lbl_order_price.configure(fg=color)
        self.var_chart_info.set("最高 %.2f  最低 %.2f  成交额 %s"
                                % (stock.high, stock.low,
                                   fmt_money(stock.bars[-1].amount if stock.bars else 0)))
        if self.var_kind.get() == "limit" and self.root.focus_get() is not self.ent_price:
            self._price_to_last()

    def refresh_tables(self):
        # 持仓
        tree = self.pos_tree
        rows = self.game.positions_view()
        tree.delete(*tree.get_children())
        for row in rows:
            tree.insert("", "end", values=(
                row["code"], row["name"], row["shares"], row["sellable"],
                "%.3f" % row["avg_cost"], "%.2f" % row["last"],
                "%.2f" % row["market_value"], "%+.2f" % row["day_pnl"],
                "%+.2f" % row["unrealized"], "%+.2f%%" % row["pnl_pct"]),
                tags=("up" if row["unrealized"] > 0 else
                      ("down" if row["unrealized"] < 0 else ""),))

        # 委托
        tree = self.order_tree
        selected = tree.selection()
        tree.delete(*tree.get_children())
        for row in self.game.orders_view():
            tree.insert("", "end", iid=str(row["id"]), values=(
                row["time"], row["code"], row["name"], row["side"], row["kind"],
                "%.2f" % row["price"] if row["price"] else "市价",
                row["qty"], row["filled"],
                "%.3f" % row["avg_price"] if row["avg_price"] else "—",
                row["status"]))
        for iid in selected:
            if tree.exists(iid):
                tree.selection_add(iid)

        # 成交：只追加新记录（整表重建在长时间挂机时会越来越费）
        tree = self.trade_tree
        trades = self.game.account.trades
        if len(trades) < self._trade_rows:          # 重开了一局
            tree.delete(*tree.get_children())
            self._trade_rows = 0
        for record in trades[self._trade_rows:]:
            tree.insert("", "end", values=(
                record.day, minute_to_clock(record.minute, self.game.rules,
                                            self.game.market.total_minutes),
                record.code, record.name, record.side_text, "%.3f" % record.price,
                record.qty, "%.2f" % record.amount, "%.2f" % record.fees,
                "%+.2f" % record.realized),
                tags=("up" if record.realized > 0 else
                      ("down" if record.realized < 0 else ""),))
        self._trade_rows = len(trades)
        children = tree.get_children()
        if len(children) > 200:                     # 只保留最近 200 笔
            tree.delete(*children[:len(children) - 200])

    def refresh_ticks(self):
        """逐笔成交明细：只在行情推进或切换标的时重建。"""
        stock = self.game.market.stocks.get(self._selected)
        stamp = (self._selected, self.game.market.day, self.game.market.minute)
        if not stock or stamp == self._ticks_stamp:
            return
        self._ticks_stamp = stamp
        tree = self.tick_tree
        tree.delete(*tree.get_children())
        for (minute, second, price, shares, side) in reversed(stock.ticks[-60:]):
            clock = minute_to_clock(minute, self.game.rules, self.game.market.total_minutes)
            tree.insert("", "end", values=(
                "%s:%02d" % (clock, second), "%.2f" % price, shares // 100,
                "主动买" if side == "B" else "主动卖",
                fmt_money(price * shares)),
                tags=("up" if side == "B" else "down",))

    # ------------------------------------------------------------ 五档盘口
    def refresh_book(self):
        canvas = self.book_canvas
        canvas.delete("all")
        self._book_levels = []
        stock = self.game.market.stocks.get(self._selected)
        if stock is None:
            return
        width = int(float(canvas["width"]))
        rows = [("ask", i, stock.asks[i]) for i in range(len(stock.asks) - 1, -1, -1)]
        rows += [("bid", i, stock.bids[i]) for i in range(len(stock.bids))]
        if not rows:
            canvas.create_text(width // 2, 70, text="停牌 / 暂无盘口", fill=MUTED,
                               font=(FONT, 10))
            self._book_hint.set("")
            return

        max_vol = max(v for _s, _i, (_p, v) in rows) or 1
        row_h = 17
        y = 0
        for text, x, anchor in (("档位", 8, "w"), ("价格", width // 2 + 6, "center"),
                                ("委托量(手)", width - 8, "e")):
            canvas.create_text(x, y + 8, text=text, anchor=anchor, fill=MUTED,
                               font=(FONT, 8))
        y += 16
        for side, index, (price, vol) in rows:
            y0, y1 = y, y + row_h
            self._book_levels.append((y0, y1, side, index))
            bar_w = int((width - 16) * vol / max_vol)
            canvas.create_rectangle(width - 8 - bar_w, y0 + 2, width - 8, y1 - 2,
                                    fill="#16202c", outline="")
            canvas.create_text(8, (y0 + y1) // 2,
                               text="%s%d" % ("卖" if side == "ask" else "买", index + 1),
                               anchor="w", fill=DOWN if side == "ask" else UP,
                               font=(FONT, 8))
            price_color = (UP if price > stock.prev_close
                           else (DOWN if price < stock.prev_close else TEXT))
            canvas.create_text(width // 2 + 6, (y0 + y1) // 2, text="%.2f" % price,
                               anchor="center", fill=price_color, font=(FONT, 9, "bold"))
            canvas.create_text(width - 10, (y0 + y1) // 2, text="%d" % (vol // 100),
                               anchor="e", fill=TEXT, font=(FONT, 8))
            y = y1
        self._book_hint.set("点任意一档可填入委托价　最新 %.2f　昨收 %.2f"
                            % (stock.last, stock.prev_close))

    def refresh_account(self):
        game = self.game
        snap = game.snapshot()
        self.var_day.set("第 %d 日  %s" % (snap["day"], snap["date"]))
        self.var_clock.set(snap["clock"])
        color = self._pnl_color(snap["index_pct"])
        self.var_index.set("%s %.2f  %+.2f%%" % (snap["index_name"], snap["index"],
                                                 snap["index_pct"]))
        self.lbl_index.configure(fg=color)
        self.var_regime.set("市场状态：" + snap["regime"])
        self.var_equity.set("%.2f" % snap["equity"])
        self.var_day_pnl.set("%+.2f" % snap["day_pnl"])
        self.lbl_day_pnl.configure(fg=self._pnl_color(snap["day_pnl"]))
        self.var_return.set("%+.2f%%" % snap["return_pct"])
        self.lbl_return.configure(fg=self._pnl_color(snap["return_pct"]))

        self._set_var("equity", "%.2f" % snap["equity"])
        self._set_var("market_value", "%.2f" % snap["market_value"])
        self._set_var("available", "%.2f" % snap["available"])
        self._set_var("unrealized", "%+.2f" % snap["unrealized"],
                      self._pnl_color(snap["unrealized"]))
        self._set_var("realized", "%+.2f" % snap["realized"],
                      self._pnl_color(snap["realized"]))
        self._set_var("debt", "%.2f" % snap["debt"],
                      UP if snap["debt"] > 0 else TEXT)
        self._set_var("costs", "%.2f" % (snap["fees"] + snap["tax"]))
        ratio = snap["margin_ratio"]
        self._set_var("margin_ratio", "∞" if ratio == float("inf") else "%.1f%%" % (ratio * 100),
                      YELLOW if ratio != float("inf") and ratio < 1.3 else TEXT)
        self._set_var("return_pct", "%+.2f%%" % snap["return_pct"],
                      self._pnl_color(snap["return_pct"]))
        diff = snap["return_pct"] - snap["index_return"]
        self._set_var("index_return", "%+.2f%%（超额 %+.2f%%）" % (snap["index_return"], diff),
                      self._pnl_color(diff))
        self.var_margin_status.set(
            "" if snap["debt"] <= 0 else "维持担保比例：%s" % snap["margin_status"])

        phase_text = {"trading": "交易中", "closed": "已收盘（按 N 或等待自动进入下一日）",
                      "finished": "本局已结束", "preopen": "待开盘"}[snap["phase"]]
        self.var_footer.set("状态：%s   冻结 %.2f   手续费 %.2f   印花税 %.2f   利息 %.2f   种子 %d"
                            % (phase_text, snap["frozen_cash"], snap["fees"],
                               snap["tax"], snap["interest"], snap["seed"]))

    def _refresh_trade_info(self):
        stock = self.game.market.stocks[self._selected]
        price = self._effective_price()
        power = self.game.account.buying_power(self.game.prices(), self.var_margin.get())
        lot = max(1, self.game.rules.lot_size)
        max_buy = int(power / max(price, 0.01) / lot) * lot
        pos = self.game.account.positions.get(self._selected)
        sellable = pos.sellable if pos else 0
        limit_text = ""
        if stock.limit_up != float("inf"):
            limit_text = "涨停 %.2f / 跌停 %.2f\n" % (stock.limit_up, stock.limit_down)
        self.var_trade_info.set(
            "%s可用资金 %.2f   最多可买 %d 股（含融资额度）\n可卖 %d 股%s"
            % (limit_text, power, max_buy, sellable,
               "   停牌中" if stock.halted else ""))

    def refresh_all(self):
        self.refresh_quotes()
        self.refresh_tables()
        self.refresh_account()
        self.refresh_book()
        self._ticks_stamp = None            # 强制重建逐笔
        self.refresh_ticks()
        self._refresh_trade_info()
        self.chart.redraw()

    # ------------------------------------------------------------ 主循环
    def loop(self):
        """定时器回调：任何单帧异常都不允许掐断刷新链（否则界面会假死）。"""
        try:
            self._frame()
            self._error_streak = 0
        except Exception as exc:                     # noqa: BLE001
            import traceback
            traceback.print_exc()
            self._error_streak = getattr(self, "_error_streak", 0) + 1
            self.var_status.set("内部错误（第 %d 次）：%r" % (self._error_streak, exc))
            if self._error_streak > 30:
                self.var_status.set("连续内部错误，已停止刷新：%r" % (exc,))
                return
        finally:
            if getattr(self, "_error_streak", 0) <= 30:
                self.root.after(self._next_delay(), self.loop)

    def _next_delay(self) -> int:
        """行情推进或待渲染时用高帧率，空闲（暂停/收盘）时降频省 CPU。"""
        busy = (self.running and not self.paused and self.game.phase == "trading") \
            or self._chart_dirty
        return FRAME_MS if busy else 80

    def _frame(self):
        now = time.perf_counter()
        dt = now - self._last
        self._last = now

        if self.running and not self.paused and self.game.phase == "trading":
            self.tick_acc += dt * self.speed
            steps = int(self.tick_acc)
            if steps > 0:
                self.tick_acc -= steps
                for _ in range(min(steps, 600)):
                    self.game.tick()
                    if self.game.phase != "trading":
                        break
                self._chart_dirty = True

        if self.game.phase == "closed":
            if self._closed_at is None:
                self._closed_at = now
            elif self.auto_next.get() and now - self._closed_at > 2.4:
                self.game.advance_day()
                self._closed_at = None
                self._chart_dirty = True
        elif self.game.phase == "finished" and self.auto_next.get():
            self.auto_next.set(False)

        self.consume_events()
        if self._chart_dirty and now - self._last_render >= 0.08:
            self._last_render = now
            self._chart_dirty = False
            self.ui_acc = 0.0
            self.refresh_quotes()
            self.refresh_tables()
            self.refresh_account()
            self.refresh_book()
            self.refresh_ticks()
            self._refresh_trade_info()
            self.chart.redraw()
        elif not self._chart_dirty:
            self.ui_acc += dt
            if self.ui_acc >= 0.5:              # 空闲时低频刷新时钟/状态
                self.ui_acc = 0.0
                self.refresh_account()
