# -*- coding: utf-8 -*-
"""领域模型：会计科目、记账凭证、凭证分录、科目余额。

这些对象只描述数据，不接触数据库也不接触界面，方便单独测试。
金额字段一律是整数「分」。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import config as C
from .money import fmt_cents


@dataclass
class Account:
    code: str
    name: str
    category: str
    direction: str
    group: str
    is_leaf: bool = True
    custom: bool = False
    enabled: bool = True

    @property
    def full_name(self) -> str:
        return "%s %s" % (self.code, self.name)

    def as_def(self) -> C.AccountDef:
        return C.AccountDef(self.code, self.name, self.category,
                            self.direction, self.group, self.is_leaf, self.custom)


@dataclass
class Entry:
    """凭证的一条分录。借方或贷方有且只有一方非零。"""
    account_code: str
    summary: str = ""
    debit: int = 0      # 分
    credit: int = 0     # 分
    line_no: int = 0
    account_name: str = ""

    @property
    def amount(self) -> int:
        return self.debit or self.credit

    @property
    def side(self) -> str:
        return C.DEBIT if self.debit else C.CREDIT

    @property
    def display_account(self) -> str:
        if self.account_name:
            return "%s %s" % (self.account_code, self.account_name)
        return self.account_code


@dataclass
class Voucher:
    """记账凭证。entries 为分录列表，借贷必须平衡。"""
    date: str                       # 'YYYY-MM-DD'
    entries: list = field(default_factory=list)
    number: str = ""                # 凭证号，如 '记-0001'
    memo: str = ""
    attachments: int = 0            # 附单据张数
    voucher_id: int | None = None
    status: str = "draft"           # draft / posted
    source: str = "manual"          # manual / opening / closing

    @property
    def total_debit(self) -> int:
        return sum(e.debit for e in self.entries)

    @property
    def total_credit(self) -> int:
        return sum(e.credit for e in self.entries)

    def balanced(self) -> bool:
        return self.total_debit == self.total_credit and self.total_debit > 0

    def summary(self) -> str:
        if self.memo:
            return self.memo
        for e in self.entries:
            if e.summary:
                return e.summary
        return ""


@dataclass
class AccountBalance:
    """某科目在某个期间（或到某日为止）的借贷发生额与余额。"""
    account: Account
    opening: int = 0        # 期初余额（按科目余额方向的正数；负数表示方向反了）
    period_debit: int = 0   # 本期借方发生额
    period_credit: int = 0  # 本期贷方发生额
    closing: int = 0        # 期末余额（按科目余额方向）

    @property
    def debit_balance(self) -> int:
        """余额落在借方的部分（用于试算平衡表/科目余额表展示）。"""
        if self.account.direction == C.DEBIT:
            return self.closing if self.closing >= 0 else 0
        return -self.closing if self.closing < 0 else 0

    @property
    def credit_balance(self) -> int:
        if self.account.direction == C.CREDIT:
            return self.closing if self.closing >= 0 else 0
        return -self.closing if self.closing < 0 else 0

    def opening_text(self) -> str:
        return fmt_cents(self.opening, blank_zero=True)

    def closing_text(self) -> str:
        return fmt_cents(self.closing, blank_zero=True)


@dataclass
class LedgerRow:
    """明细账的一行（一笔分录）。"""
    date: str
    voucher_number: str
    summary: str
    debit: int
    credit: int
    balance: int          # 按科目余额方向的滚动余额
    direction: str        # 余额方向（借/贷/平）


@dataclass
class ReportLine:
    """报表的一行：可以带缩进层级，也可以是小计 / 合计行。"""
    label: str
    value: int = 0
    level: int = 0
    bold: bool = False
    codes: tuple = ()