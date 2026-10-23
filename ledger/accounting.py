# -*- coding: utf-8 -*-
"""复式记账引擎：凭证校验、过账、科目余额、期初平衡、期末结转损益。

账务规则（借贷记账法）：
  * 有借必有贷、借贷必相等：每张凭证借方合计 = 贷方合计；
  * 一条分录只能有借方或贷方其中一个金额；
  * 只能记账到「明细（末级）科目」；
  * 只有「已过账」的凭证参与余额与报表计算。
"""
from __future__ import annotations

import re

from . import config as C
from .db import Database
from .models import AccountBalance, Entry, LedgerRow, Voucher

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class LedgerError(Exception):
    pass


def valid_date(text: str) -> bool:
    if not text or not _DATE_RE.match(text):
        return False
    y, m, d = (int(x) for x in text.split("-"))
    if not (1 <= m <= 12):
        return False
    days = [31, 29 if _leap(y) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return 1 <= d <= days[m - 1]


def _leap(y: int) -> bool:
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def month_range(year: int, month: int) -> tuple:
    start = "%04d-%02d-01" % (year, month)
    if month == 12:
        end = "%04d-12-31" % year
    else:
        last = [31, 29 if _leap(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
        end = "%04d-%02d-%02d" % (year, month, last)
    return start, end


def year_range(year: int) -> tuple:
    return "%04d-01-01" % year, "%04d-12-31" % year


class Ledger:
    def __init__(self, db: Database):
        self.db = db

    # ====================================================== 科目
    def accounts(self, include_disabled: bool = False):
        return self.db.list_accounts(include_disabled)

    def account_map(self) -> dict:
        return {a.code: a for a in self.db.list_accounts(include_disabled=True)}

    def postable_accounts(self) -> list:
        """可用于记账的末级科目。"""
        return [a for a in self.db.list_accounts() if a.is_leaf]

    # ====================================================== 凭证校验
    def validate(self, v: Voucher) -> list:
        errors = []
        if not valid_date(v.date):
            errors.append("凭证日期无效（应为 YYYY-MM-DD）")
        if len(v.entries) < 2:
            errors.append("凭证至少需要两条分录")
        amap = self.account_map()
        for i, e in enumerate(v.entries, start=1):
            acc = amap.get(e.account_code)
            if acc is None:
                errors.append("第 %d 行：科目 %s 不存在" % (i, e.account_code))
                continue
            if not acc.is_leaf:
                errors.append("第 %d 行：%s 是上级科目，不能记账" % (i, acc.full_name))
            if not acc.enabled:
                errors.append("第 %d 行：%s 已停用" % (i, acc.full_name))
            if e.debit < 0 or e.credit < 0:
                errors.append("第 %d 行：金额不能为负" % i)
            elif e.debit == 0 and e.credit == 0:
                errors.append("第 %d 行：金额不能为零" % i)
            elif e.debit > 0 and e.credit > 0:
                errors.append("第 %d 行：借贷方必须且只能填一个" % i)
        if not errors:
            if v.total_debit != v.total_credit:
                errors.append("借贷不平衡：借方 %.2f，贷方 %.2f"
                              % (v.total_debit / 100, v.total_credit / 100))
            elif v.total_debit == 0:
                errors.append("凭证金额不能为零")
        return errors

    def save_voucher(self, v: Voucher, post: bool = True) -> int:
        errors = self.validate(v)
        if errors:
            raise LedgerError("；".join(errors))
        if not v.number:
            v.number = self.db.next_voucher_number(v.date)
        if post:
            v.status = "posted"
        return self.db.save_voucher(v)

    def post_voucher(self, vid: int) -> None:
        v = self.db.get_voucher(vid)
        if v is None:
            raise LedgerError("凭证不存在")
        errors = self.validate(v)
        if errors:
            raise LedgerError("；".join(errors))
        self.db.set_voucher_status(vid, "posted")

    def unpost_voucher(self, vid: int) -> None:
        self.db.set_voucher_status(vid, "draft")

    def delete_voucher(self, vid: int) -> None:
        self.db.delete_voucher(vid)

    # ====================================================== 期初余额
    def opening_nets(self) -> dict:
        """期初余额，换算成「借正贷负」的净额（分）。"""
        amap = self.account_map()
        out = {}
        for code, natural in self.db.get_openings().items():
            acc = amap.get(code)
            if acc is None:
                continue
            out[code] = natural if acc.direction == C.DEBIT else -natural
        return out

    def opening_check(self) -> int:
        """期初借贷差额（借正贷负）；为 0 表示期初平衡。"""
        return sum(self.opening_nets().values())

    # ====================================================== 余额
    def _raw_totals(self, start: str | None, end: str | None,
                    account: str | None = None) -> dict:
        """统计 [start, end] 区间内已过账分录的借贷发生额。"""
        totals = {}
        for r in self.db.iter_posted_entries(start=start, end=end, account=account):
            t = totals.setdefault(r["account_code"], [0, 0])
            t[0] += r["debit"]
            t[1] += r["credit"]
        return totals

    def balances(self, start: str, end: str) -> list:
        """区间科目余额表：期初 / 本期发生 / 期末。"""
        amap = self.account_map()
        opening = self.opening_nets()
        before = self._raw_totals(None, _prev_day(start))
        period = self._raw_totals(start, end)

        result = []
        for code, acc in sorted(amap.items()):
            od, oc = before.get(code, (0, 0))
            pd, pc = period.get(code, (0, 0))
            open_net = opening.get(code, 0) + od - oc
            close_net = open_net + pd - pc
            if not (od or oc or pd or pc or opening.get(code)):
                continue
            sign = 1 if acc.direction == C.DEBIT else -1
            result.append(AccountBalance(acc, open_net * sign, pd, pc, close_net * sign))
        return result

    def balance_of(self, code: str, upto: str | None = None, start: str | None = None) -> int:
        """某科目按余额方向的余额（自然方向正数）。"""
        acc = self.db.get_account(code)
        if acc is None:
            return 0
        nets = self.cumulative_nets(upto)
        net = nets.get(code, 0)
        return net if acc.direction == C.DEBIT else -net

    def cumulative_nets(self, upto: str | None = None) -> dict:
        """含期初、截至 upto 的净额（借正贷负）。"""
        out = dict(self.opening_nets())
        for code, (d, c) in self._raw_totals(None, upto).items():
            out[code] = out.get(code, 0) + d - c
        return out

    def period_nets(self, start: str, end: str) -> dict:
        """仅区间发生额的净额（借正贷负），不含期初。"""
        return {code: d - c for code, (d, c) in self._raw_totals(start, end).items()}

    # ====================================================== 明细账
    def detail_ledger(self, code: str, start: str, end: str) -> list:
        acc = self.db.get_account(code)
        if acc is None:
            raise LedgerError("科目不存在：%s" % code)
        sign = 1 if acc.direction == C.DEBIT else -1
        opening_net = self.opening_nets().get(code, 0)
        for r in self.db.iter_posted_entries(None, _prev_day(start), account=code):
            opening_net += r["debit"] - r["credit"]
        running = opening_net
        rows = []
        for r in self.db.iter_posted_entries(start, end, account=code):
            running += r["debit"] - r["credit"]
            natural = running * sign
            direction = C.DEBIT if natural > 0 else (C.CREDIT if natural < 0 else "平")
            rows.append(LedgerRow(r["date"], r["number"], r["summary"] or "",
                                  r["debit"], r["credit"], natural, direction))
        return rows

    def opening_of(self, code: str, start: str) -> int:
        acc = self.db.get_account(code)
        if acc is None:
            return 0
        sign = 1 if acc.direction == C.DEBIT else -1
        net = self.opening_nets().get(code, 0)
        for r in self.db.iter_posted_entries(None, _prev_day(start), account=code):
            net += r["debit"] - r["credit"]
        return net * sign

    # ====================================================== 期末结转损益
    def close_period(self, start: str, end: str, close_date: str | None = None) -> Voucher | None:
        """把区间内损益类科目余额结转至「本年利润」，生成一张已过账凭证。"""
        nets = self.period_nets(start, end)
        amap = self.account_map()
        entries = []
        plug = 0
        for code, net in sorted(nets.items()):
            acc = amap.get(code)
            if acc is None or acc.category != C.PROFIT or net == 0:
                continue
            if net > 0:      # 费用类：借方余额 → 贷方转出
                entries.append(Entry(code, "结转本期损益", 0, net))
            else:            # 收入类：贷方余额 → 借方转出
                entries.append(Entry(code, "结转本期损益", -net, 0))
            plug += -net
        if not entries:
            return None
        if plug > 0:
            entries.append(Entry(C.ACCOUNT_INCOME_SUMMARY, "结转本期损益", 0, plug))
        elif plug < 0:
            entries.append(Entry(C.ACCOUNT_INCOME_SUMMARY, "结转本期损益", -plug, 0))
        v = Voucher(close_date or end, entries, "", "结转 %s ~ %s 损益" % (start, end),
                    0, None, "posted", "closing")
        v.number = self.db.next_voucher_number(v.date)
        self.db.save_voucher(v)
        return v

    def closed_periods(self) -> list:
        """已经做过结转损益的会计期间（按月份）。"""
        rows = self.db.conn.execute(
            "SELECT DISTINCT substr(date,1,7) AS m FROM vouchers "
            "WHERE source = 'closing' ORDER BY m").fetchall()
        return [r["m"] for r in rows]

    def net_income(self, start: str, end: str) -> int:
        """区间净利润（分）：收入 - 费用。"""
        nets = self.period_nets(start, end)
        amap = self.account_map()
        total = 0
        for code, net in nets.items():
            acc = amap.get(code)
            if acc and acc.category == C.PROFIT:
                total += -net
        return total


def _prev_day(day: str) -> str:
    import datetime as _dt
    y, m, d = (int(x) for x in day.split("-"))
    return (_dt.date(y, m, d) - _dt.timedelta(days=1)).isoformat()