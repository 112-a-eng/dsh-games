# -*- coding: utf-8 -*-
"""tkinter 界面：凭证录入、凭证管理、账簿、报表、科目与期初、图表。

界面只负责收集输入和展示结果，所有账务计算都交给 accounting / reports 里的纯逻辑层。
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import config as C
from .accounting import Ledger, LedgerError, month_range, valid_date, year_range
from .charts import ChartCanvas, abbrev
from .models import Account, Entry, Voucher
from .money import fmt_cents, parse_amount
from .reports import (account_balance_table, available_years, balance_sheet,
                      expense_breakdown, income_statement, monthly_series,
                      revenue_breakdown, trial_balance)

FONT = "Microsoft YaHei UI"
BG = "#eef1f6"
CARD = "#ffffff"
ACCENT = "#2f6fed"
ACCENT_DK = "#1f4fb0"
TEXT = "#1f2937"
MUTED = "#6b7280"
BORDER = "#d6dce6"
GOOD = "#1a8f5a"
BAD = "#c0392b"


def today() -> str:
    return dt.date.today().isoformat()


def enable_high_dpi() -> float:
    """让 Windows 按真实 DPI 渲染（避免高分屏下的整窗模糊）。

    返回缩放系数（96 DPI 为 1.0）。失败时静默降级，不影响主流程。
    """
    if not sys.platform.startswith("win"):
        return 1.0
    try:
        import ctypes

        try:
            # 2 = Per-Monitor V2，Win10 1703+
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:  # noqa: BLE001
            ctypes.windll.user32.SetProcessDPIAware()
        dc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, dc)
        return max(1.0, min(dpi / 96.0, 3.0))
    except Exception:  # noqa: BLE001
        return 1.0


def safe_parse(text) -> int:
    try:
        return parse_amount(text)
    except ValueError:
        return 0


def _apply_window_icon(root) -> None:
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "ledger_icon.png")
    try:
        image = tk.PhotoImage(file=path)
        root.iconphoto(True, image)
        root._icon_ref = image
    except Exception:
        pass


def setup_style(root) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    root.configure(background=BG)
    root.option_add("*Font", (FONT, 10))
    root.option_add("*TCombobox*Listbox.font", (FONT, 10))

    style.configure(".", font=(FONT, 10), background=BG, foreground=TEXT)
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=CARD)
    style.configure("Table.TFrame", background="#f8fafd")
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Card.TLabel", background=CARD, foreground=TEXT)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED)
    style.configure("Header.TLabel", background=ACCENT, foreground="white",
                    font=(FONT, 15, "bold"))
    style.configure("HeaderSub.TLabel", background=ACCENT, foreground="#dbe6ff",
                    font=(FONT, 9))
    style.configure("H1.TLabel", background=BG, foreground=TEXT, font=(FONT, 13, "bold"))
    style.configure("Section.TLabel", background=CARD, foreground=MUTED,
                    font=(FONT, 10, "bold"))
    style.configure("Kpi.TLabel", background=CARD, foreground=TEXT,
                    font=(FONT, 16, "bold"))
    style.configure("KpiCap.TLabel", background=CARD, foreground=MUTED, font=(FONT, 9))
    style.configure("TableHead.TLabel", background="#f8fafd", foreground=MUTED,
                    font=(FONT, 9, "bold"))
    style.configure("TableBig.TLabel", background="#f8fafd", foreground=TEXT,
                    font=(FONT, 11, "bold"))
    style.configure("BadgeOk.TLabel", background="#e2f5ea", foreground=GOOD,
                    font=(FONT, 9, "bold"), padding=(8, 2))
    style.configure("BadgeBad.TLabel", background="#fdeaea", foreground=BAD,
                    font=(FONT, 9, "bold"), padding=(8, 2))
    style.configure("BadgeIdle.TLabel", background="#eceff5", foreground=MUTED,
                    font=(FONT, 9, "bold"), padding=(8, 2))

    style.configure("TButton", padding=(10, 5))
    style.configure("Accent.TButton", padding=(12, 6), background=ACCENT,
                    foreground="white", borderwidth=0)
    style.map("Accent.TButton",
              background=[("active", ACCENT_DK), ("pressed", ACCENT_DK)])
    style.configure("Soft.TButton", padding=(10, 5), background="#e6ebf5",
                    foreground=TEXT, borderwidth=0)
    style.map("Soft.TButton",
              background=[("active", "#d8e0ee"), ("pressed", "#cfd9ea")])
    style.configure("Ghost.TButton", padding=(10, 5))

    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure("TNotebook.Tab", padding=(16, 8), background="#dfe4ee",
                    foreground=TEXT, font=(FONT, 10))
    style.map("TNotebook.Tab",
              background=[("selected", CARD)],
              foreground=[("selected", ACCENT)])

    style.configure("TLabelframe", background=BG, bordercolor=BORDER)
    style.configure("TLabelframe.Label", background=BG, foreground=MUTED,
                    font=(FONT, 10, "bold"))

    style.configure("Treeview", rowheight=28, font=(FONT, 10), background=CARD,
                    fieldbackground=CARD, foreground=TEXT, borderwidth=0)
    style.configure("Treeview.Heading", font=(FONT, 10, "bold"),
                    background="#e9edf5", foreground=TEXT, relief="flat", padding=(6, 7))
    style.map("Treeview.Heading", background=[("active", "#dde3ee")])
    style.map("Treeview", background=[("selected", "#cfe0ff")],
              foreground=[("selected", TEXT)])

    style.configure("TEntry", fieldbackground="white", bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER, padding=4)
    style.configure("TCombobox", fieldbackground="white", padding=3)
    style.configure("Status.TLabel", background="#dfe4ee", foreground=MUTED,
                    font=(FONT, 9))


class AccountCombo(ttk.Combobox):
    """带科目下拉与代码解析的输入框。"""

    def __init__(self, master, app, width=26, **kw):
        super().__init__(master, width=width, state="normal", **kw)
        self.app = app
        self._acc_options = []
        self.set_accounts(app.postable_options())
        self.bind("<KeyRelease>", self._autocomplete)

    def set_accounts(self, options):
        self._acc_options = options
        self["values"] = options

    def code(self):
        text = self.get().strip()
        if not text:
            return None
        token = text.split()[0]
        return token if token.isdigit() else None

    def set_code(self, code):
        if not code:
            self.set("")
            return
        for opt in self._acc_options:
            if opt.split()[0] == code:
                self.set(opt)
                return
        self.set(code)

    def _autocomplete(self, event):
        if event.keysym in ("BackSpace", "Delete", "Left", "Right", "Up", "Down",
                            "Escape", "Return", "Tab"):
            return
        text = self.get().strip()
        if not text:
            return
        matches = [o for o in self._acc_options if text in o]
        if matches and text not in self._options:
            self["values"] = matches
            self.icursor("end")


class ScrollFrame(ttk.Frame):
    """可纵向滚动的容器，内容放进 .inner。"""

    def __init__(self, master, background=CARD, inner_style="Card.TFrame"):
        super().__init__(master, style="Card.TFrame")
        self.canvas = tk.Canvas(self, highlightthickness=0, bg=background)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas, style=inner_style)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        for w in (self.canvas, self.inner):
            w.bind("<MouseWheel>", self._on_wheel)

    def _on_inner(self, _e):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)

    def _on_wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")


def save_csv(root, default_name, headers, rows) -> bool:
    try:
        parent = root.winfo_toplevel()
    except Exception:  # noqa: BLE001
        parent = root
    path = filedialog.asksaveasfilename(
        parent=parent, title="导出 CSV", defaultextension=".csv",
        initialfile=default_name, filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")])
    if not path:
        return False
    try:
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh)
            writer.writerow(headers)
            for row in rows:
                writer.writerow(row)
    except OSError as exc:
        messagebox.showerror("导出失败", str(exc), parent=root)
        return False
    messagebox.showinfo("导出成功", "已导出到：\n%s" % path, parent=root)
    return True


class BaseTab(ttk.Frame):
    # 自带底色的 tag，斑马纹不去覆盖它们
    ZEBRA_SKIP = ("total", "bold", "section", "open")

    def __init__(self, master, app):
        super().__init__(master, style="TFrame", padding=12)
        self.app = app
        self.ledger = app.ledger

    def refresh(self):
        pass

    def make_tree(self, parent, hint="暂无数据", **kw):
        tree = ttk.Treeview(parent, **kw)
        tree.tag_configure("odd", background="#f7f9fc")
        tree.tag_configure("even", background=CARD)
        tree._hint = tk.Label(parent, text=hint, background=CARD, foreground=MUTED,
                              font=(FONT, 10), justify="center")
        return tree

    def stripe(self, tree):
        """给表格加斑马纹；合计 / 分组等自带底色的行保持原样，并处理空表提示。"""
        for i, iid in enumerate(tree.get_children("")):
            tags = [t for t in tree.item(iid, "tags") if t not in ("odd", "even")]
            if any(t in self.ZEBRA_SKIP for t in tags):
                tree.item(iid, tags=tuple(tags))
            else:
                tree.item(iid, tags=tuple(tags) + ("odd" if i % 2 else "even",))
        hint = getattr(tree, "_hint", None)
        if hint is None:
            return
        if tree.get_children(""):
            hint.place_forget()
        else:
            hint.place(relx=0.5, rely=0.5, anchor="center")
            hint.lift()


# ==================================================================== 凭证录入
class VoucherEntryTab(BaseTab):
    # 列：标题、最小宽度（像素）、伸展权重
    COLS = (("摘要", 220, 3), ("会计科目", 300, 3), ("借方金额", 130, 1),
            ("贷方金额", 130, 1), ("", 44, 0))

    def __init__(self, master, app):
        super().__init__(master, app)
        self.rows = []
        self.editing_id = None
        self._build()

    def _build(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Label(bar, text="日期").pack(side="left")
        self.var_date = tk.StringVar(value=today())
        ent = ttk.Entry(bar, textvariable=self.var_date, width=12)
        ent.pack(side="left", padx=(4, 12))
        self.var_date.trace_add("write", lambda *_: self._sync_number())

        ttk.Label(bar, text="凭证号").pack(side="left")
        self.var_number = tk.StringVar()
        ttk.Entry(bar, textvariable=self.var_number, width=14).pack(side="left", padx=(4, 12))

        ttk.Label(bar, text="附单据").pack(side="left")
        self.var_attach = tk.StringVar(value="0")
        ttk.Spinbox(bar, from_=0, to=999, width=4,
                    textvariable=self.var_attach).pack(side="left", padx=(4, 12))

        self.var_memo = tk.StringVar()
        ttk.Label(bar, text="备注").pack(side="left")
        ttk.Entry(bar, textvariable=self.var_memo, width=26).pack(side="left", padx=(4, 0))

        card = ttk.Frame(self, style="Table.TFrame", padding=(12, 10))
        card.pack(fill="both", expand=True)

        totals = ttk.Frame(card, style="Table.TFrame")
        totals.pack(side="bottom", fill="x", pady=(10, 0))
        self.lbl_debit = ttk.Label(totals, text="借方合计 0.00", style="TableBig.TLabel")
        self.lbl_debit.pack(side="left")
        self.lbl_credit = ttk.Label(totals, text="贷方合计 0.00", style="TableBig.TLabel")
        self.lbl_credit.pack(side="left", padx=(20, 0))
        self.lbl_diff = ttk.Label(totals, text="差额 0.00", style="TableBig.TLabel")
        self.lbl_diff.pack(side="left", padx=(20, 10))
        self.lbl_badge = ttk.Label(totals, text="待输入", style="BadgeIdle.TLabel")
        self.lbl_badge.pack(side="left")

        self.scroll = ScrollFrame(card, background="#f8fafd", inner_style="Table.TFrame")
        self.scroll.pack(fill="both", expand=True)
        inner = self.scroll.inner
        for i, (_title, minw, weight) in enumerate(self.COLS):
            inner.columnconfigure(i, minsize=minw, weight=weight)
        for i, (title, _minw, _weight) in enumerate(self.COLS):
            ttk.Label(inner, text=title, style="TableHead.TLabel", anchor="w").grid(
                row=0, column=i, sticky="ew", padx=(0, 8), pady=(0, 6))
        self._row_base = 1

        footer = ttk.Frame(self)
        footer.pack(fill="x", pady=(10, 0))
        acts = ttk.Frame(footer)
        acts.pack(fill="x")
        ttk.Button(acts, text="保存并过账", style="Accent.TButton",
                   command=lambda: self.save("posted")).pack(side="left")
        ttk.Button(acts, text="保存为草稿", style="Soft.TButton",
                   command=lambda: self.save("draft")).pack(side="left", padx=8)
        ttk.Button(acts, text="清空", style="Soft.TButton",
                   command=self.clear).pack(side="left")
        self.var_edit = tk.StringVar(value="")
        ttk.Label(acts, textvariable=self.var_edit, style="Muted.TLabel").pack(
            side="left", padx=12)
        ttk.Button(acts, text="增加行", command=self.add_row).pack(side="right")
        ttk.Button(acts, text="删除末行", command=self.remove_last).pack(
            side="right", padx=(0, 8))
        ttk.Label(footer, style="Muted.TLabel",
                  text="快捷键：Ctrl+Enter 保存并过账 · Ctrl+S 保存草稿 · "
                       "Ctrl+N 增加行 · Ctrl+D 删除末行").pack(anchor="w", pady=(8, 0))

        self.hotkeys = {"save_posted": lambda: self.save("posted"),
                        "save_draft": lambda: self.save("draft"),
                        "add_row": self.add_row,
                        "del_row": self.remove_last}

        self.add_row()
        self.add_row()
        self._sync_number()
        self._update_totals()

    # -------------------------------------------------------- 行管理
    def add_row(self, summary="", code="", debit="", credit=""):
        v_sum = tk.StringVar(value=summary)
        v_deb = tk.StringVar(value=debit)
        v_cre = tk.StringVar(value=credit)
        e_sum = ttk.Entry(self.scroll.inner, textvariable=v_sum)
        combo = AccountCombo(self.scroll.inner, self.app)
        combo.set_code(code)
        e_deb = ttk.Entry(self.scroll.inner, textvariable=v_deb, justify="right")
        e_cre = ttk.Entry(self.scroll.inner, textvariable=v_cre, justify="right")
        btn = ttk.Button(self.scroll.inner, text="×", width=3)
        rec = {"widgets": (e_sum, combo, e_deb, e_cre, btn), "summary": v_sum,
               "account": combo, "debit": v_deb, "credit": v_cre}
        btn.configure(command=lambda: self.remove_row(rec))
        for var in (v_deb, v_cre):
            var.trace_add("write", lambda *_: self._update_totals())
        for ent in (e_sum, e_deb, e_cre):
            ent.bind("<MouseWheel>", self.scroll._on_wheel)
        self.rows.append(rec)
        self._place_rows()
        self._update_totals()
        return rec

    def _place_rows(self):
        for idx, rec in enumerate(self.rows):
            row = self._row_base + idx
            for col, widget in enumerate(rec["widgets"]):
                widget.grid(row=row, column=col, sticky="ew" if col < 4 else "",
                            padx=(0, 8), pady=2)

    def remove_row(self, rec):
        if len(self.rows) <= 1:
            return
        for widget in rec["widgets"]:
            widget.destroy()
        self.rows.remove(rec)
        self._place_rows()
        self._update_totals()

    def remove_last(self):
        if len(self.rows) > 1:
            self.remove_row(self.rows[-1])

    def clear(self):
        for rec in list(self.rows):
            for widget in rec["widgets"]:
                widget.destroy()
        self.rows = []
        self.editing_id = None
        self.var_edit.set("")
        self.var_memo.set("")
        self.var_attach.set("0")
        self.var_date.set(today())
        self.add_row()
        self.add_row()
        self._sync_number()
        self._update_totals()

    def _collect(self, strict=True):
        entries = []
        errors = []
        for i, rec in enumerate(self.rows, start=1):
            summary = rec["summary"].get().strip()
            code = rec["account"].code()
            deb_txt = rec["debit"].get().strip()
            cre_txt = rec["credit"].get().strip()
            if not (code or deb_txt or cre_txt or summary):
                continue
            try:
                debit = parse_amount(deb_txt)
                credit = parse_amount(cre_txt)
            except ValueError:
                if strict:
                    errors.append("第 %d 行金额格式不正确" % i)
                debit = credit = 0
            if not code and strict:
                errors.append("第 %d 行未选择会计科目" % i)
            entries.append(Entry(code or "", summary, debit, credit))
        return entries, errors

    def _update_totals(self):
        entries, _ = self._collect(strict=False)
        d = sum(e.debit for e in entries)
        c = sum(e.credit for e in entries)
        diff = d - c
        self.lbl_debit.configure(text="借方合计 %s" % fmt_cents(d))
        self.lbl_credit.configure(text="贷方合计 %s" % fmt_cents(c))
        self.lbl_diff.configure(text="差额 %s" % fmt_cents(diff))
        if d == 0 and c == 0:
            self.lbl_diff.configure(foreground=MUTED)
            self.lbl_badge.configure(text="待输入", style="BadgeIdle.TLabel")
        elif diff == 0:
            self.lbl_diff.configure(foreground=GOOD)
            self.lbl_badge.configure(text="借贷平衡", style="BadgeOk.TLabel")
        else:
            self.lbl_diff.configure(foreground=BAD)
            self.lbl_badge.configure(text="不平衡", style="BadgeBad.TLabel")

    def _sync_number(self):
        if self.editing_id:
            return
        day = self.var_date.get().strip()
        if valid_date(day):
            self.var_number.set(self.ledger.db.next_voucher_number(day))

    def save(self, status):
        entries, errors = self._collect(strict=True)
        if errors:
            messagebox.showerror("无法保存", "\n".join(errors), parent=self)
            return
        day = self.var_date.get().strip()
        v = Voucher(day, entries, self.var_number.get().strip(), self.var_memo.get().strip(),
                    int(self.var_attach.get() or 0), self.editing_id, status)
        if self.editing_id:
            v.status = status
        try:
            self.ledger.save_voucher(v, post=(status == "posted"))
        except LedgerError as exc:
            messagebox.showerror("凭证错误", str(exc), parent=self)
            return
        self.app.set_status("凭证 %s 已保存（%s）" % (v.number, "已过账" if status == "posted"
                                                      else "草稿"))
        self.clear()
        self.app.refresh_views()

    def load_voucher(self, v: Voucher):
        self.clear()
        self.editing_id = v.voucher_id
        self.var_date.set(v.date)
        self.var_number.set(v.number)
        self.var_memo.set(v.memo)
        self.var_attach.set(str(v.attachments))
        for rec in list(self.rows):
            for widget in rec["widgets"]:
                widget.destroy()
        self.rows = []
        for e in v.entries:
            self.add_row(e.summary, e.account_code,
                         fmt_cents(e.debit, thousands=False, blank_zero=True),
                         fmt_cents(e.credit, thousands=False, blank_zero=True))
        if not self.rows:
            self.add_row()
        self.var_edit.set("正在编辑凭证 #%s（保存将覆盖）" % v.number)
        self._update_totals()

    def refresh(self):
        for rec in self.rows:
            rec["account"].set_accounts(self.app.postable_options())


# ==================================================================== 凭证管理
class VoucherListTab(BaseTab):
    def __init__(self, master, app):
        super().__init__(master, app)
        self._build()
        self.query()

    def _build(self):
        filt = ttk.Frame(self)
        filt.pack(fill="x", pady=(0, 8))
        ttk.Label(filt, text="起").pack(side="left")
        self.var_start = tk.StringVar(value="%s-01-01" % today()[:4])
        ttk.Entry(filt, textvariable=self.var_start, width=12).pack(side="left", padx=(4, 8))
        ttk.Label(filt, text="止").pack(side="left")
        self.var_end = tk.StringVar(value=today())
        ttk.Entry(filt, textvariable=self.var_end, width=12).pack(side="left", padx=(4, 8))
        ttk.Label(filt, text="关键字").pack(side="left")
        self.var_kw = tk.StringVar()
        ttk.Entry(filt, textvariable=self.var_kw, width=16).pack(side="left", padx=(4, 8))
        ttk.Label(filt, text="科目").pack(side="left")
        self.var_acc = tk.StringVar()
        self.combo_acc = AccountCombo(filt, self.app, width=20)
        self.combo_acc.pack(side="left", padx=(4, 8))
        self.var_status = tk.StringVar(value="全部")
        ttk.Combobox(filt, textvariable=self.var_status, width=7, state="readonly",
                     values=("全部", "已过账", "草稿")).pack(side="left", padx=(0, 8))
        ttk.Button(filt, text="查询", style="Accent.TButton",
                   command=self.query).pack(side="left")

        cols = ("date", "number", "memo", "debit", "lines", "status", "source")
        self.tree = self.make_tree(self, columns=cols, show="headings",
                                   selectmode="browse",
                                   hint="没有符合条件的凭证\n试试放宽日期范围，或清空筛选条件")
        heads = {"date": ("日期", 100), "number": ("凭证号", 110), "memo": ("摘要", 300),
                 "debit": ("金额", 120), "lines": ("分录", 60), "status": ("状态", 70),
                 "source": ("来源", 80)}
        for c in cols:
            self.tree.heading(c, text=heads[c][0])
            self.tree.column(c, width=heads[c][1],
                             anchor="e" if c == "debit" else "w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.edit())
        self.tree.tag_configure("draft", foreground=MUTED)

        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(8, 0))
        ttk.Button(bar, text="查看/编辑", command=self.edit).pack(side="left")
        ttk.Button(bar, text="过账", command=lambda: self.set_status("posted")).pack(
            side="left", padx=6)
        ttk.Button(bar, text="取消过账", command=lambda: self.set_status("draft")).pack(
            side="left", padx=6)
        ttk.Button(bar, text="删除", command=self.delete).pack(side="left", padx=6)
        ttk.Button(bar, text="导出 CSV", command=self.export).pack(side="right")
        self.var_info = tk.StringVar()
        ttk.Label(bar, textvariable=self.var_info, style="Muted.TLabel").pack(
            side="right", padx=12)

    def _status_filter(self):
        return {"全部": None, "已过账": "posted", "草稿": "draft"}[self.var_status.get()]

    def query(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        acc = self.combo_acc.code()
        vouchers = self.ledger.db.list_vouchers(
            self.var_start.get().strip() or None, self.var_end.get().strip() or None,
            self.var_kw.get().strip() or None, acc, self._status_filter())
        self._vouchers = vouchers
        for v in vouchers:
            self.tree.insert("", "end", iid=str(v.voucher_id), values=(
                v.date, v.number, v.summary(),
                fmt_cents(v.total_debit), len(v.entries),
                "已过账" if v.status == "posted" else "草稿",
                {"manual": "手工", "opening": "期初", "closing": "结转"}.get(v.source, v.source)),
                tags=("draft",) if v.status == "draft" else ())
        self.stripe(self.tree)
        self.var_info.set("共 %d 张凭证" % len(vouchers))

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择一张凭证", parent=self)
            return None
        return int(sel[0])

    def edit(self):
        vid = self._selected()
        if vid is None:
            return
        v = self.ledger.db.get_voucher(vid)
        if v is None:
            return
        self.app.edit_voucher(v)

    def set_status(self, status):
        vid = self._selected()
        if vid is None:
            return
        try:
            if status == "posted":
                self.ledger.post_voucher(vid)
            else:
                self.ledger.unpost_voucher(vid)
        except LedgerError as exc:
            messagebox.showerror("操作失败", str(exc), parent=self)
            return
        self.app.refresh_views()

    def delete(self):
        vid = self._selected()
        if vid is None:
            return
        if not messagebox.askyesno("确认删除", "确定删除这张凭证吗？此操作不可撤销。",
                                   parent=self):
            return
        self.ledger.delete_voucher(vid)
        self.app.set_status("凭证已删除")
        self.app.refresh_views()

    def export(self):
        rows = [(v.date, v.number, v.summary(), fmt_cents(v.total_debit),
                 fmt_cents(v.total_credit), "已过账" if v.status == "posted" else "草稿")
                for v in getattr(self, "_vouchers", [])]
        save_csv(self, "凭证明细.csv",
                 ("日期", "凭证号", "摘要", "借方合计", "贷方合计", "状态"), rows)

    def refresh(self):
        self.combo_acc.set_accounts(self.app.postable_options())
        self.query()


# ==================================================================== 账簿
class LedgerTab(BaseTab):
    def __init__(self, master, app):
        super().__init__(master, app)
        self._build()
        self.query()

    def _build(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        self.var_mode = tk.StringVar(value="明细账")
        ttk.Radiobutton(bar, text="明细账", value="明细账", variable=self.var_mode,
                        command=self.query).pack(side="left")
        ttk.Radiobutton(bar, text="总账", value="总账", variable=self.var_mode,
                        command=self.query).pack(side="left", padx=(0, 12))
        ttk.Label(bar, text="科目").pack(side="left")
        self.combo_acc = AccountCombo(bar, self.app, width=22)
        self.combo_acc.pack(side="left", padx=(4, 12))
        ttk.Label(bar, text="起").pack(side="left")
        self.var_start = tk.StringVar(value="%s-01-01" % today()[:4])
        ttk.Entry(bar, textvariable=self.var_start, width=12).pack(side="left", padx=(4, 8))
        ttk.Label(bar, text="止").pack(side="left")
        self.var_end = tk.StringVar(value=today())
        ttk.Entry(bar, textvariable=self.var_end, width=12).pack(side="left", padx=(4, 8))
        ttk.Button(bar, text="查询", style="Accent.TButton",
                   command=self.query).pack(side="left")
        ttk.Button(bar, text="导出", command=self.export).pack(side="right")

        self.tree = self.make_tree(self, columns=(), show="headings",
                                   hint="请先在上方选择会计科目")
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("total", background="#eef4ff", font=(FONT, 10, "bold"))
        self.tree.tag_configure("open", background="#f6f8fc", foreground=MUTED)

        self.var_info = tk.StringVar()
        ttk.Label(self, textvariable=self.var_info, style="Muted.TLabel").pack(
            anchor="w", pady=(6, 0))

    def _set_columns(self, spec):
        cols = [c for c, _ in spec]
        self.tree.configure(columns=cols)
        for c, (title, width) in spec:
            self.tree.heading(c, text=title)
            self.tree.column(c, width=width,
                             anchor="e" if c in ("debit", "credit", "balance") else "w")

    def query(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        if self.var_mode.get() == "总账":
            self._query_general()
        else:
            self._query_detail()

    def _query_general(self):
        self._set_columns((("code", ("科目代码", 110)), ("name", ("科目名称", 180)),
                           ("open", ("期初余额", 130)), ("debit", ("本期借方", 130)),
                           ("credit", ("本期贷方", 130)), ("balance", ("期末余额", 130)),
                           ("dir", ("方向", 60))))
        start, end = self.var_start.get().strip(), self.var_end.get().strip()
        rows = account_balance_table(self.ledger, start, end)
        for b in rows:
            self.tree.insert("", "end", values=(
                b.account.code, b.account.name, fmt_cents(b.opening, blank_zero=True),
                fmt_cents(b.period_debit, blank_zero=True),
                fmt_cents(b.period_credit, blank_zero=True),
                fmt_cents(b.closing, blank_zero=True), b.account.direction))
        self.stripe(self.tree)
        self.var_info.set("总账：%s ~ %s，共 %d 个科目" % (start, end, len(rows)))
        self._export_rows = [("科目代码", "科目名称", "期初", "本期借", "本期贷", "期末", "方向")]
        self._export_rows += [(b.account.code, b.account.name, str(b.opening),
                               str(b.period_debit), str(b.period_credit),
                               str(b.closing), b.account.direction) for b in rows]

    def _query_detail(self):
        code = self.combo_acc.code()
        if not code:
            self.tree.configure(columns=())
            self.stripe(self.tree)
            self.var_info.set("请选择要查看的会计科目")
            return
        start, end = self.var_start.get().strip(), self.var_end.get().strip()
        self._set_columns((("date", ("日期", 100)), ("number", ("凭证号", 110)),
                           ("summary", ("摘要", 300)), ("debit", ("借方", 130)),
                           ("credit", ("贷方", 130)), ("dir", ("方向", 60)),
                           ("balance", ("余额", 140))))
        open_bal = self.ledger.opening_of(code, start)
        acc = self.ledger.db.get_account(code)
        self.tree.insert("", "end", values=("", "", "期初余额", "", "",
                                            "借" if open_bal >= 0 else "贷",
                                            fmt_cents(open_bal)), tags=("open",))
        rows = self.ledger.detail_ledger(code, start, end)
        td = tc = 0
        for r in rows:
            td += r.debit
            tc += r.credit
            self.tree.insert("", "end", values=(
                r.date, r.voucher_number, r.summary, fmt_cents(r.debit, blank_zero=True),
                fmt_cents(r.credit, blank_zero=True), r.direction, fmt_cents(r.balance)))
        close_bal = open_bal + td - tc if acc and acc.direction == C.DEBIT else open_bal - (td - tc)
        self.tree.insert("", "end", values=("", "", "本期合计", fmt_cents(td),
                                            fmt_cents(tc), "", fmt_cents(close_bal)),
                         tags=("total",))
        self.stripe(self.tree)
        self.var_info.set("%s %s：%s ~ %s，共 %d 笔" %
                          (acc.code, acc.name, start, end, len(rows))) if acc else None
        self._export_rows = [("日期", "凭证号", "摘要", "借方", "贷方", "方向", "余额")]
        self._export_rows += [(r.date, r.voucher_number, r.summary, str(r.debit),
                               str(r.credit), r.direction, str(r.balance)) for r in rows]

    def export(self):
        name = "总账.csv" if self.var_mode.get() == "总账" else "明细账.csv"
        rows = getattr(self, "_export_rows", [])
        if not rows:
            messagebox.showinfo("提示", "没有可导出的数据", parent=self)
            return
        save_csv(self, name, rows[0], rows[1:])

    def refresh(self):
        self.combo_acc.set_accounts(self.app.postable_options())
        self.query()


# ==================================================================== 报表
class ReportsTab(BaseTab):
    REPORTS = ["资产负债表", "利润表", "科目余额表", "试算平衡表"]

    def __init__(self, master, app):
        super().__init__(master, app)
        self._build()
        self.run()

    def _build(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Label(bar, text="报表").pack(side="left")
        self.var_kind = tk.StringVar(value=self.REPORTS[0])
        cb = ttk.Combobox(bar, textvariable=self.var_kind, values=self.REPORTS,
                          width=12, state="readonly")
        cb.pack(side="left", padx=(4, 12))
        cb.bind("<<ComboboxSelected>>", lambda e: self.run())

        ttk.Label(bar, text="会计期间").pack(side="left")
        self.var_from = tk.StringVar(value="%s-01-01" % today()[:4])
        self.var_to = tk.StringVar(value=today())
        ttk.Entry(bar, textvariable=self.var_from, width=12).pack(side="left", padx=(4, 6))
        ttk.Label(bar, text="~").pack(side="left")
        ttk.Entry(bar, textvariable=self.var_to, width=12).pack(side="left", padx=(6, 10))

        ttk.Button(bar, text="本月", command=lambda: self._quick("month")).pack(side="left")
        ttk.Button(bar, text="本季", command=lambda: self._quick("quarter")).pack(
            side="left", padx=4)
        ttk.Button(bar, text="本年", command=lambda: self._quick("year")).pack(side="left")
        ttk.Button(bar, text="生成", style="Accent.TButton",
                   command=self.run).pack(side="left", padx=8)

        self.tree = self.make_tree(self, columns=(), show="headings",
                                   hint="没有数据，换个会计期间试试")
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("bold", font=(FONT, 10, "bold"), background="#f2f6ff")
        self.tree.tag_configure("section", font=(FONT, 10, "bold"),
                                background="#e9edf5", foreground=ACCENT_DK)
        self.tree.tag_configure("indent", foreground=MUTED)

        foot = ttk.Frame(self)
        foot.pack(fill="x", pady=(8, 0))
        ttk.Button(foot, text="导出 CSV", command=self.export).pack(side="right")
        self.var_info = tk.StringVar()
        ttk.Label(foot, textvariable=self.var_info, style="Muted.TLabel").pack(
            side="left")

    def _quick(self, which):
        t = dt.date.today()
        if which == "month":
            self.var_from.set(t.replace(day=1).isoformat())
        elif which == "quarter":
            qm = (t.month - 1) // 3 * 3 + 1
            self.var_from.set(t.replace(month=qm, day=1).isoformat())
        else:
            self.var_from.set(t.replace(month=1, day=1).isoformat())
        self.var_to.set(t.isoformat())
        self.run()

    def _cols(self, spec):
        cols = [c for c, _ in spec]
        self.tree.configure(columns=cols)
        for c, (title, width) in spec:
            self.tree.heading(c, text=title)
            self.tree.column(c, width=width,
                             anchor="e" if c in ("end", "begin", "value", "debit", "credit",
                                                 "od", "oc", "cd", "cc") else "w")

    def run(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        kind = self.var_kind.get()
        start, end = self.var_from.get().strip(), self.var_to.get().strip()
        if not (valid_date(start) and valid_date(end)):
            self.var_info.set("日期格式应为 YYYY-MM-DD")
            return
        if kind == "资产负债表":
            self._render_balance_sheet(end)
        elif kind == "利润表":
            self._render_income(start, end)
        elif kind == "科目余额表":
            self._render_balance_table(start, end)
        else:
            self._render_trial(start, end)

    def _render_balance_sheet(self, end):
        self._cols((("item", ("项目", 300)), ("end", ("期末余额", 150)),
                    ("begin", ("年初余额", 150))))
        rows = balance_sheet(self.ledger, end)
        out = [("项目", "期末余额", "年初余额")]
        for r in rows:
            tag = "section" if r.level == 0 else ("bold" if r.bold else "")
            label = ("  " * r.level) + r.label if r.label else ""
            if r.level == 0 and not r.label:
                continue
            vals = (label,
                    "" if r.level == 0 else fmt_cents(r.end, blank_zero=True),
                    "" if r.level == 0 else fmt_cents(r.begin, blank_zero=True))
            self.tree.insert("", "end", values=vals, tags=(tag,))
            out.append((label, str(r.end), str(r.begin)))
        self.stripe(self.tree)
        company = self.ledger.db.company
        self.var_info.set("资产负债表 · %s · %s（单位：元）" % (company, end))
        self._export_rows = out

    def _render_income(self, start, end):
        self._cols((("item", ("项目", 300)), ("value", ("本期金额", 160))))
        rows = income_statement(self.ledger, start, end)
        out = [("项目", "本期金额")]
        for r in rows:
            tag = "bold" if r.bold else "indent"
            self.tree.insert("", "end", values=(r.label, fmt_cents(r.value)),
                             tags=(tag,))
            out.append((r.label, str(r.value)))
        self.stripe(self.tree)
        self.var_info.set("利润表 · %s ~ %s（单位：元）" % (start, end))
        self._export_rows = out

    def _render_balance_table(self, start, end):
        self._cols((("code", ("科目代码", 100)), ("name", ("科目名称", 180)),
                    ("od", ("期初借方", 120)), ("oc", ("期初贷方", 120)),
                    ("debit", ("本期借方", 120)), ("credit", ("本期贷方", 120)),
                    ("cd", ("期末借方", 120)), ("cc", ("期末贷方", 120))))
        rows = account_balance_table(self.ledger, start, end)
        out = [("科目代码", "科目名称", "期初借", "期初贷", "本期借", "本期贷", "期末借", "期末贷")]
        for b in rows:
            if b.account.direction == C.DEBIT:
                od, oc = (b.opening, 0) if b.opening >= 0 else (0, -b.opening)
                cd, cc = (b.closing, 0) if b.closing >= 0 else (0, -b.closing)
            else:
                od, oc = (0, b.opening) if b.opening >= 0 else (-b.opening, 0)
                cd, cc = (0, b.closing) if b.closing >= 0 else (-b.closing, 0)
            self.tree.insert("", "end", values=(
                b.account.code, b.account.name, fmt_cents(od, blank_zero=True),
                fmt_cents(oc, blank_zero=True), fmt_cents(b.period_debit, blank_zero=True),
                fmt_cents(b.period_credit, blank_zero=True), fmt_cents(cd, blank_zero=True),
                fmt_cents(cc, blank_zero=True)))
            out.append((b.account.code, b.account.name, str(od), str(oc), str(b.period_debit),
                        str(b.period_credit), str(cd), str(cc)))
        self.stripe(self.tree)
        self.var_info.set("科目余额表 · %s ~ %s，共 %d 个科目" % (start, end, len(rows)))
        self._export_rows = out

    def _render_trial(self, start, end):
        self._cols((("code", ("科目", 90)), ("name", ("名称", 150)),
                    ("od", ("期初借", 110)), ("oc", ("期初贷", 110)),
                    ("debit", ("本期借", 110)), ("credit", ("本期贷", 110)),
                    ("cd", ("期末借", 110)), ("cc", ("期末贷", 110))))
        tb = trial_balance(self.ledger, start, end)
        out = [("科目", "名称", "期初借", "期初贷", "本期借", "本期贷", "期末借", "期末贷")]
        for r in tb["rows"]:
            self.tree.insert("", "end", values=(
                r["code"], r["name"], fmt_cents(r["open_debit"], blank_zero=True),
                fmt_cents(r["open_credit"], blank_zero=True),
                fmt_cents(r["period_debit"], blank_zero=True),
                fmt_cents(r["period_credit"], blank_zero=True),
                fmt_cents(r["close_debit"], blank_zero=True),
                fmt_cents(r["close_credit"], blank_zero=True)))
            out.append((r["code"], r["name"], str(r["open_debit"]), str(r["open_credit"]),
                        str(r["period_debit"]), str(r["period_credit"]),
                        str(r["close_debit"]), str(r["close_credit"])))
        t = tb["totals"]
        self.tree.insert("", "end", values=("合计", "", fmt_cents(t["open_debit"]),
                                            fmt_cents(t["open_credit"]),
                                            fmt_cents(t["period_debit"]),
                                            fmt_cents(t["period_credit"]),
                                            fmt_cents(t["close_debit"]),
                                            fmt_cents(t["close_credit"])), tags=("bold",))
        out.append(("合计", "", str(t["open_debit"]), str(t["open_credit"]),
                    str(t["period_debit"]), str(t["period_credit"]),
                    str(t["close_debit"]), str(t["close_credit"])))
        self.stripe(self.tree)
        ok = "✔ 借贷平衡" if tb["balanced"] else "✘ 借贷不平衡，请检查凭证"
        self.var_info.set("试算平衡表 · %s ~ %s · %s" % (start, end, ok))
        self._export_rows = out

    def export(self):
        rows = getattr(self, "_export_rows", [])
        if not rows:
            messagebox.showinfo("提示", "请先生成报表", parent=self)
            return
        save_csv(self, "%s.csv" % self.var_kind.get(), rows[0], rows[1:])

    def refresh(self):
        self.run()


# ==================================================================== 科目与期初
class AccountsTab(BaseTab):
    def __init__(self, master, app):
        super().__init__(master, app)
        self._build()
        self.reload()

    def _build(self):
        panes = ttk.Frame(self)
        panes.pack(fill="both", expand=True)
        left = ttk.Frame(panes)
        left.pack(side="left", fill="both", expand=True)
        right = ttk.Frame(panes, width=280)
        right.pack(side="right", fill="y", padx=(12, 0))
        right.pack_propagate(False)

        self.tree = self.make_tree(left, columns=("name", "category", "direction", "flag"),
                                   show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="科目代码")
        self.tree.column("#0", width=110)
        for c, (t, w) in {"name": ("科目名称", 200), "category": ("类别", 100),
                          "direction": ("方向", 60), "flag": ("属性", 90)}.items():
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("custom", foreground=ACCENT_DK)

        ttk.Label(right, text="科目操作", style="Section.TLabel").pack(anchor="w")
        ttk.Label(right, text="选中一个科目后可在其下增加明细科目；\n明细科目才能用于记账。",
                  style="Muted.TLabel", justify="left").pack(anchor="w", pady=(4, 10))
        ttk.Button(right, text="新增子科目", style="Accent.TButton",
                   command=self.add_child).pack(fill="x", pady=3)
        ttk.Button(right, text="修改名称/方向", command=self.edit).pack(fill="x", pady=3)
        ttk.Button(right, text="停用 / 启用", command=self.toggle).pack(fill="x", pady=3)
        ttk.Button(right, text="删除明细科目", command=self.delete).pack(fill="x", pady=3)
        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=14)
        ttk.Button(right, text="设置期初余额", style="Accent.TButton",
                   command=self.open_opening).pack(fill="x", pady=3)
        self.var_open = tk.StringVar()
        ttk.Label(right, textvariable=self.var_open, style="Muted.TLabel",
                  justify="left", wraplength=250).pack(anchor="w", pady=(8, 0))

    def reload(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        accounts = self.ledger.db.list_accounts(include_disabled=True)
        by_parent = {}
        nodes = {}
        for a in accounts:
            parent = a.code[:-2] if len(a.code) > 4 else ""
            by_parent.setdefault(parent, []).append(a)

        def insert(parent_node, code):
            for a in by_parent.get(code, []):
                flag = "自定义" if a.custom else ""
                if not a.enabled:
                    flag = "已停用"
                elif not a.is_leaf:
                    flag = "上级科目"
                node = self.tree.insert(parent_node, "end", iid=a.code,
                                        text=a.code,
                                        values=(a.name, a.category, a.direction, flag),
                                        open=(code == ""), tags=("custom",) if a.custom else ())
                nodes[a.code] = node
                insert(a.code, a.code)

        insert("", "")
        self.stripe(self.tree)
        self._check_opening()

    def _check_opening(self):
        diff = self.ledger.opening_check()
        total = sum(abs(v) for v in self.ledger.db.get_openings().values())
        if total == 0:
            self.var_open.set("尚未录入期初余额。")
        elif diff == 0:
            self.var_open.set("期初已录入且借贷平衡（合计 %s）。" % fmt_cents(total))
        else:
            self.var_open.set("⚠ 期初借贷不平衡：差额 %s（借正贷负）。请检查。"
                              % fmt_cents(diff))

    def _selected_code(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择一个科目", parent=self)
            return None
        return sel[0]

    def add_child(self):
        code = self._selected_code()
        if not code:
            return
        parent = self.ledger.db.get_account(code)
        if parent is None:
            return
        AccountDialog(self, self.app, parent=parent, on_done=self._after)

    def edit(self):
        code = self._selected_code()
        if not code:
            return
        acc = self.ledger.db.get_account(code)
        AccountDialog(self, self.app, account=acc, on_done=self._after)

    def toggle(self):
        code = self._selected_code()
        if not code:
            return
        acc = self.ledger.db.get_account(code)
        acc.enabled = not acc.enabled
        self.ledger.db.update_account(acc)
        self._after()

    def delete(self):
        code = self._selected_code()
        if not code:
            return
        acc = self.ledger.db.get_account(code)
        if not acc.custom:
            messagebox.showwarning("不可删除", "标准科目不能删除，只能停用。", parent=self)
            return
        if self.ledger.db.account_has_entries(code):
            messagebox.showwarning("不可删除", "该科目已有分录，不能删除。", parent=self)
            return
        if any(len(a.code) > 4 and a.code[:-2] == code
               for a in self.ledger.db.list_accounts(include_disabled=True)):
            messagebox.showwarning("不可删除", "请先删除其下级科目。", parent=self)
            return
        if not messagebox.askyesno("确认", "删除科目 %s？" % acc.full_name, parent=self):
            return
        self.ledger.db.delete_account(code)
        self._after()

    def open_opening(self):
        OpeningDialog(self, self.app, on_done=self._after)

    def _after(self):
        self.reload()
        self.app.accounts_changed()


class AccountDialog(tk.Toplevel):
    def __init__(self, master, app, parent=None, account=None, on_done=None):
        super().__init__(master)
        self.app = app
        self.ledger = app.ledger
        self.parent_acc = parent
        self.account = account
        self.on_done = on_done
        self.title("修改科目" if account else "新增明细科目")
        self.configure(background=BG)
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.grab_set()

        base = account or parent
        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)

        self.var_code = tk.StringVar(
            value=account.code if account else (parent.code + "01"))
        self.var_name = tk.StringVar(value=account.name if account else "")
        self.var_cat = tk.StringVar(value=base.category)
        self.var_dir = tk.StringVar(value=base.direction)
        self.var_group = tk.StringVar(value=base.group)

        rows = [("科目代码", ttk.Entry(body, textvariable=self.var_code, width=22)),
                ("科目名称", ttk.Entry(body, textvariable=self.var_name, width=22))]
        for i, (label, widget) in enumerate(rows):
            ttk.Label(body, text=label).grid(row=i, column=0, sticky="w", pady=6)
            widget.grid(row=i, column=1, sticky="w", pady=6)
        if account:
            rows[0][1].configure(state="readonly")

        ttk.Label(body, text="类别").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Combobox(body, textvariable=self.var_cat, values=C.CATEGORIES, width=20,
                     state="readonly").grid(row=2, column=1, sticky="w", pady=6)
        ttk.Label(body, text="余额方向").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Combobox(body, textvariable=self.var_dir, values=(C.DEBIT, C.CREDIT), width=20,
                     state="readonly").grid(row=3, column=1, sticky="w", pady=6)
        ttk.Label(body, text="报表分组").grid(row=4, column=0, sticky="w", pady=6)
        groups = [g for g in (C.G_CURRENT_ASSET, C.G_NONCURRENT_ASSET, C.G_CURRENT_LIAB,
                              C.G_NONCURRENT_LIAB, C.G_EQUITY, C.G_COST, C.G_REVENUE,
                              C.G_OP_COST, C.G_PERIOD_EXP, C.G_OTHER, C.G_TAX)]
        ttk.Combobox(body, textvariable=self.var_group, values=groups, width=20,
                     state="readonly").grid(row=4, column=1, sticky="w", pady=6)

        if parent is not None:
            ttk.Label(body, text="上级科目：%s" % parent.full_name,
                      style="Muted.TLabel").grid(row=5, column=0, columnspan=2,
                                                 sticky="w", pady=(6, 0))

        bar = ttk.Frame(self, padding=(16, 0, 16, 16))
        bar.pack(fill="x")
        ttk.Button(bar, text="确定", style="Accent.TButton",
                   command=self.ok).pack(side="right")
        ttk.Button(bar, text="取消", command=self.destroy).pack(side="right", padx=6)

    def ok(self):
        code = self.var_code.get().strip()
        name = self.var_name.get().strip()
        if not code.isdigit() or len(code) < 4:
            messagebox.showerror("错误", "科目代码应为 4 位以上数字", parent=self)
            return
        if not name:
            messagebox.showerror("错误", "请输入科目名称", parent=self)
            return
        if self.account:
            self.account.name = name
            self.account.category = self.var_cat.get()
            self.account.direction = self.var_dir.get()
            self.account.group = self.var_group.get()
            self.ledger.db.update_account(self.account)
        else:
            if self.ledger.db.account_exists(code):
                messagebox.showerror("错误", "科目代码已存在", parent=self)
                return
            if self.parent_acc and not code.startswith(self.parent_acc.code):
                messagebox.showerror("错误", "子科目代码应以 %s 开头" % self.parent_acc.code,
                                     parent=self)
                return
            acc = Account(code, name, self.var_cat.get(), self.var_dir.get(),
                          self.var_group.get(), custom=True)
            self.ledger.db.add_account(acc)
        self.destroy()
        if self.on_done:
            self.on_done()


class OpeningDialog(tk.Toplevel):
    def __init__(self, master, app, on_done=None):
        super().__init__(master)
        self.app = app
        self.ledger = app.ledger
        self.on_done = on_done
        self.title("设置期初余额")
        self.configure(background=BG)
        self.geometry("520x620")
        self.transient(master.winfo_toplevel())
        self.grab_set()

        ttk.Label(self, text="期初余额（按各科目余额方向填正数，单位：元）",
                  style="H1.TLabel", padding=12).pack(anchor="w")
        ttk.Label(self, text="只填有余额的科目即可。借方合计应等于贷方合计。",
                  style="Muted.TLabel").pack(anchor="w", padx=12)

        self.scroll = ScrollFrame(self, background=CARD)
        self.scroll.pack(fill="both", expand=True, padx=12, pady=8)
        self.entries = {}
        openings = self.ledger.db.get_openings()
        for a in self.ledger.db.list_accounts():
            if not a.is_leaf:
                continue
            row = ttk.Frame(self.scroll.inner, style="Card.TFrame")
            row.pack(fill="x", pady=1)
            ttk.Label(row, text="%s %s" % (a.code, a.name), style="Card.TLabel",
                      width=28, anchor="w").pack(side="left")
            ttk.Label(row, text=a.direction, style="Muted.TLabel", width=3).pack(side="left")
            var = tk.StringVar(value=fmt_cents(openings.get(a.code, 0), thousands=False,
                                               blank_zero=True))
            ent = ttk.Entry(row, textvariable=var, width=14, justify="right")
            ent.pack(side="left")
            var.trace_add("write", lambda *_: self._update_diff())
            self.entries[a.code] = var

        foot = ttk.Frame(self, padding=(12, 0, 12, 12))
        foot.pack(fill="x")
        self.var_diff = tk.StringVar()
        ttk.Label(foot, textvariable=self.var_diff).pack(side="left")
        ttk.Button(foot, text="保存", style="Accent.TButton",
                   command=self.save).pack(side="right")
        ttk.Button(foot, text="取消", command=self.destroy).pack(side="right", padx=6)
        self._update_diff()

    def _collect(self):
        mapping = {}
        for code, var in self.entries.items():
            mapping[code] = safe_parse(var.get())
        return mapping

    def _update_diff(self):
        mapping = self._collect()
        amap = self.ledger.account_map()
        net = sum(v if amap[c].direction == C.DEBIT else -v
                  for c, v in mapping.items() if v)
        self.var_diff.set("借方 - 贷方 = %s" % fmt_cents(net))

    def save(self):
        mapping = self._collect()
        amap = self.ledger.account_map()
        net = sum(v if amap[c].direction == C.DEBIT else -v
                  for c, v in mapping.items() if v)
        self.ledger.db.replace_openings(mapping)
        if net != 0:
            messagebox.showwarning("提示", "期初借贷不平衡（差额 %s），已保存，"
                                   "请后续调整。" % fmt_cents(net), parent=self)
        self.destroy()
        if self.on_done:
            self.on_done()


# ==================================================================== 图表
class ChartsTab(BaseTab):
    def __init__(self, master, app):
        super().__init__(master, app)
        self._build()
        self.run()

    def _build(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Label(bar, text="会计年度").pack(side="left")
        self.var_year = tk.StringVar(value=today()[:4])
        self.combo_year = ttk.Combobox(bar, textvariable=self.var_year, width=8,
                                       state="readonly")
        self.combo_year.pack(side="left", padx=(4, 12))
        ttk.Button(bar, text="刷新", style="Accent.TButton",
                   command=self.run).pack(side="left")
        ttk.Button(bar, text="结转本年损益", command=self.close_year).pack(side="left",
                                                                         padx=8)
        self.var_scope = tk.StringVar(value="全年")
        ttk.Label(bar, text="周期").pack(side="left", padx=(12, 0))
        ttk.Combobox(bar, textvariable=self.var_scope, width=8, state="readonly",
                     values=("全年",) + tuple("%d月" % m for m in range(1, 13))).pack(
            side="left", padx=4)

        kpis = ttk.Frame(self)
        kpis.pack(fill="x")
        self.kpi = {}
        for key, cap in (("revenue", "收入"), ("expense", "费用"),
                         ("net", "净利润"), ("assets", "资产总计")):
            card = ttk.Frame(kpis, style="Card.TFrame", padding=14)
            card.pack(side="left", fill="both", expand=True, padx=(0, 8))
            ttk.Label(card, text=cap, style="KpiCap.TLabel").pack(anchor="w")
            lbl = ttk.Label(card, text="--", style="Kpi.TLabel")
            lbl.pack(anchor="w")
            self.kpi[key] = lbl

        charts = ttk.Frame(self)
        charts.pack(fill="both", expand=True, pady=(10, 0))
        pie_card = ttk.Frame(charts, style="Card.TFrame")
        pie_card.pack(side="left", fill="both", expand=True, padx=(0, 8))
        bar_card = ttk.Frame(charts, style="Card.TFrame")
        bar_card.pack(side="left", fill="both", expand=True)
        self.pie = ChartCanvas(tk.Canvas(pie_card, height=320), BG)
        self.pie.canvas.pack(fill="both", expand=True)
        self.bars = ChartCanvas(tk.Canvas(bar_card, height=320), BG)
        self.bars.canvas.pack(fill="both", expand=True)

    def _period(self):
        year = int(self.var_year.get())
        scope = self.var_scope.get()
        if scope == "全年":
            return year_range(year)
        return month_range(year, int(scope[:-1]))

    def run(self):
        years = [str(y) for y in available_years(self.ledger)]
        self.combo_year["values"] = years
        if self.var_year.get() not in years and years:
            self.var_year.set(years[-1])
        year = int(self.var_year.get())
        start, end = self._period()
        series = monthly_series(self.ledger, year)
        self.bars.show_bars(range(1, 13), series["revenue"], series["expense"],
                            series["net"], "月度收入 / 费用 / 净利润（%d 年）" % year)
        exp = expense_breakdown(self.ledger, start, end)
        if exp:
            self.pie.show_pie(exp, "费用构成 · %s" % self.var_scope.get())
        else:
            rev = revenue_breakdown(self.ledger, start, end)
            self.pie.show_pie(rev, "收入构成 · %s" % self.var_scope.get())

        rev_total, exp_total = sum(series["revenue"]), sum(series["expense"])
        if self.var_scope.get() != "全年":
            m = int(self.var_scope.get()[:-1]) - 1
            rev_total, exp_total = series["revenue"][m], series["expense"][m]
        net = self.ledger.net_income(start, end)
        bs = balance_sheet(self.ledger, end)
        assets = [r for r in bs if r.label == "资产总计"][0].end
        self.kpi["revenue"].configure(text=abbrev(rev_total))
        self.kpi["expense"].configure(text=abbrev(exp_total))
        self.kpi["net"].configure(text=abbrev(net))
        self.kpi["assets"].configure(text=abbrev(assets))

    def close_year(self):
        year = int(self.var_year.get())
        start, end = year_range(year)
        if not messagebox.askyesno("结转损益", "将 %d 年全年损益结转至「本年利润」，"
                                   "并生成一张已过账凭证，继续吗？" % year, parent=self):
            return
        v = self.ledger.close_period(start, end)
        if v is None:
            messagebox.showinfo("提示", "该年度没有需要结转的损益。", parent=self)
            return
        self.app.set_status("已生成结转凭证 %s" % v.number)
        self.app.refresh_views()

    def refresh(self):
        self.run()


# ==================================================================== 主窗口
class LedgerUI:
    HOTKEYS = (("<Control-Return>", "save_posted"), ("<Control-s>", "save_draft"),
               ("<Control-n>", "add_row"), ("<Control-d>", "del_row"))

    def __init__(self, root, ledger: Ledger):
        self.root = root
        self.ledger = ledger
        setup_style(root)
        root.title("%s · %s" % (C.APP_NAME, ledger.db.company))
        self._place_window()
        self._build_header()
        self._build_status()
        self._build_notebook()
        self._bind_hotkeys()

    # -------------------------------------------------------- 窗口位置
    def _place_window(self):
        root = self.root
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        try:
            scale = max(1.0, min(root.winfo_fpixels("1i") / 96.0, 2.5))
        except tk.TclError:
            scale = 1.0
        w = min(int(1220 * scale), max(920, sw - 80))
        h = min(int(780 * scale), max(620, sh - 120))
        self.root.geometry("%dx%d+%d+%d" % (w, h, max(0, (sw - w) // 2),
                                            max(0, (sh - h) // 2 - 24)))
        root.minsize(min(int(1000 * scale), sw - 80),
                     min(int(640 * scale), sh - 120))

    # -------------------------------------------------------- 快捷键
    def _bind_hotkeys(self):
        for seq, name in self.HOTKEYS:
            self.root.bind(seq, lambda _e, n=name: self._hotkey(n))
        self.root.bind("<F5>", lambda _e: self._refresh_hotkey())

    def _hotkey(self, name):
        tab = self.nb.nametowidget(self.nb.select())
        action = getattr(tab, "hotkeys", {}).get(name)
        if action is None:
            return None
        action()
        return "break"

    def _refresh_hotkey(self):
        self.refresh_views()
        self.set_status("已刷新（F5）")
        return "break"

    # -------------------------------------------------------- 头部
    def _build_header(self):
        header = tk.Frame(self.root, background=ACCENT)
        header.pack(fill="x")
        left = tk.Frame(header, background=ACCENT)
        left.pack(side="left", padx=20, pady=11)
        tk.Label(left, text=C.APP_NAME, background=ACCENT, foreground="white",
                 font=(FONT, 17, "bold")).pack(anchor="w")
        self.lbl_company = tk.Label(
            left, text="%s · 会计启用日 %s" % (self.ledger.db.company, self.ledger.db.start_date),
            background=ACCENT, foreground="#dbe6ff", font=(FONT, 9))
        self.lbl_company.pack(anchor="w", pady=(2, 0))
        right = tk.Frame(header, background=ACCENT)
        right.pack(side="right", padx=20)
        self._header_button(right, "账套设置", self.open_settings)
        self._header_button(right, "关于", self.about)

    def _header_button(self, parent, text, command):
        btn = tk.Button(parent, text=text, command=command, relief="flat", bd=0,
                        background=ACCENT, foreground="white",
                        activebackground="white", activeforeground=ACCENT,
                        font=(FONT, 10), cursor="hand2", padx=12, pady=5)
        btn.pack(side="right", padx=(8, 0))
        return btn

    def _build_notebook(self):
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=12, pady=12)
        self.tabs = {}
        specs = [("凭证录入", VoucherEntryTab), ("凭证管理", VoucherListTab),
                 ("账簿查询", LedgerTab), ("财务报表", ReportsTab),
                 ("科目与期初", AccountsTab), ("图表分析", ChartsTab)]
        for title, cls in specs:
            tab = cls(self.nb, self)
            self.nb.add(tab, text=title)
            self.tabs[cls.__name__] = tab
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab)

    def _build_status(self):
        bar = tk.Frame(self.root, background="#dfe4ee")
        bar.pack(fill="x", side="bottom")
        self.var_status = tk.StringVar(value="就绪 · 账套：%s" % self.ledger.db.path)
        ttk.Label(bar, textvariable=self.var_status, style="Status.TLabel",
                  anchor="w", padding=(12, 5)).pack(side="left", fill="x", expand=True)
        ttk.Label(bar, text="F5 刷新 · Ctrl+Enter 过账保存", style="Status.TLabel",
                  padding=(12, 5)).pack(side="right")

    def _on_tab(self, _e):
        idx = self.nb.index(self.nb.select())
        tab = self.nb.nametowidget(self.nb.select())
        if hasattr(tab, "refresh"):
            try:
                tab.refresh()
            except Exception as exc:  # noqa: BLE001
                self.set_status("刷新失败：%r" % exc)

    # -------------------------------------------------------- 对外接口
    def select_tab(self, index):
        tabs = self.nb.tabs()
        if 0 <= index < len(tabs):
            self.nb.select(tabs[index])

    def postable_options(self):
        return ["%s %s" % (a.code, a.name) for a in self.ledger.postable_accounts()]

    def set_status(self, text):
        self.var_status.set(text)

    def refresh_views(self):
        self.tabs["VoucherListTab"].refresh()
        self.tabs["LedgerTab"].refresh()
        self.tabs["ReportsTab"].refresh()
        self.tabs["ChartsTab"].refresh()

    def accounts_changed(self):
        for tab in self.tabs.values():
            try:
                tab.refresh()
            except Exception:  # noqa: BLE001
                pass

    def edit_voucher(self, v: Voucher):
        tab = self.tabs["VoucherEntryTab"]
        self.nb.select(tab)
        tab.load_voucher(v)
        self.set_status("正在编辑凭证 %s" % v.number)

    def open_settings(self):
        SettingsDialog(self.root, self)

    def about(self):
        messagebox.showinfo(
            "关于 %s" % C.APP_NAME,
            "%s v%s\n\n"
            "一个 Windows 桌面复式记账软件。\n"
            "· 借贷记账法，凭证保存即校验借贷平衡\n"
            "· 科目余额表 / 试算平衡表 / 资产负债表 / 利润表\n"
            "· 期末结转损益、期初余额、明细账与总账\n"
            "· 数据保存在本地 SQLite 账套文件中\n\n"
            "新建账套：用命令 py -m ledger --db 新账套.db 打开另一个文件即可。"
            % (C.APP_NAME, C.APP_VERSION), parent=self.root)


class SettingsDialog(tk.Toplevel):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.title("账套设置")
        self.configure(background=BG)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        self.var_company = tk.StringVar(value=app.ledger.db.company)
        self.var_start = tk.StringVar(value=app.ledger.db.start_date)
        ttk.Label(body, text="公司 / 单位名称").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(body, textvariable=self.var_company, width=28).grid(row=0, column=1, pady=6)
        ttk.Label(body, text="会计启用日期").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(body, textvariable=self.var_start, width=28).grid(row=1, column=1, pady=6)
        ttk.Label(body, text="账套文件：%s" % app.ledger.db.path,
                  style="Muted.TLabel", wraplength=320, justify="left").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        bar = ttk.Frame(self, padding=(16, 0, 16, 16))
        bar.pack(fill="x")
        ttk.Button(bar, text="保存", style="Accent.TButton",
                   command=self.save).pack(side="right")
        ttk.Button(bar, text="取消", command=self.destroy).pack(side="right", padx=6)

    def save(self):
        if not valid_date(self.var_start.get().strip()):
            messagebox.showerror("错误", "启用日期格式应为 YYYY-MM-DD", parent=self)
            return
        self.app.ledger.db.set_meta("company", self.var_company.get().strip() or "未命名单位")
        self.app.ledger.db.set_meta("start_date", self.var_start.get().strip())
        self.app.lbl_company.configure(
            text="%s · 会计启用日 %s" % (self.app.ledger.db.company,
                                        self.app.ledger.db.start_date))
        self.app.root.title("%s · %s" % (C.APP_NAME, self.app.ledger.db.company))
        self.app.refresh_views()
        self.destroy()