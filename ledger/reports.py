# -*- coding: utf-8 -*-
"""财务报表：科目余额表、试算平衡表、资产负债表、利润表，以及图表用的汇总数据。

金额一律为整数「分」。资产负债表按「资产 = 负债 + 所有者权益」的恒等式编制，
利润表按「收入 − 费用 = 利润」的多步式结构编制。
"""
from __future__ import annotations

from dataclasses import dataclass

from . import config as C
from .accounting import Ledger


@dataclass
class BSRow:
    label: str
    end: int
    begin: int
    level: int = 1
    bold: bool = False


@dataclass
class ISRow:
    label: str
    value: int
    level: int = 1
    bold: bool = False
    indent: bool = False


# 资产负债表项目 -> 科目代码集合
ASSET_LINES = [
    ("货币资金", ("1001", "1002", "1012")),
    ("交易性金融资产", ("1101",)),
    ("应收票据", ("1121",)),
    ("应收账款", ("1122", "1231")),
    ("预付款项", ("1123",)),
    ("其他应收款", ("1131", "1132", "1221")),
    ("存货", ("1401", "1402", "1403", "1405", "1408", "1471", "5001", "5101", "5201")),
    ("固定资产", ("1601", "1602", "1603")),
    ("无形资产", ("1701", "1702")),
    ("长期待摊费用", ("1801",)),
    ("递延所得税资产", ("1811",)),
]
LIABILITY_LINES = [
    ("短期借款", ("2001",)),
    ("应付票据", ("2201",)),
    ("应付账款", ("2202",)),
    ("预收款项", ("2203",)),
    ("应付职工薪酬", ("2211",)),
    ("应交税费", ("2221",)),
    ("应付利息", ("2231",)),
    ("应付股利", ("2232",)),
    ("其他应付款", ("2241",)),
    ("长期借款", ("2501",)),
    ("预计负债", ("2801",)),
    ("递延所得税负债", ("2901",)),
]
EQUITY_LINES = [
    ("实收资本", ("4001",)),
    ("资本公积", ("4002",)),
    ("盈余公积", ("4101",)),
]


def _prev_year_end(day: str) -> str:
    return "%04d-12-31" % (int(day[:4]) - 1)


def _sum(nets: dict, codes) -> int:
    return sum(nets.get(c, 0) for c in codes)


def _undistributed(ledger: Ledger, nets: dict) -> int:
    """未分配利润 = 利润分配 + 本年利润 + 尚未结转的当期损益。"""
    unclosed = 0
    amap = ledger.account_map()
    for code, net in nets.items():
        acc = amap.get(code)
        if acc and acc.category == C.PROFIT:
            unclosed += net
    return -(nets.get(C.ACCOUNT_PROFIT_DISTRIBUTION, 0)
             + nets.get(C.ACCOUNT_INCOME_SUMMARY, 0) + unclosed)


def balance_sheet(ledger: Ledger, end: str, begin: str | None = None) -> list:
    """资产负债表。end 为报表日；begin 默认取上一年 12 月 31 日（年初数）。"""
    if begin is None:
        begin = _prev_year_end(end)
    ne = ledger.cumulative_nets(end)
    nb = ledger.cumulative_nets(begin)

    rows = [BSRow("资产", 0, 0, level=0, bold=True)]
    asset_total_e = asset_total_b = 0
    for label, codes in ASSET_LINES:
        ve, vb = _sum(ne, codes), _sum(nb, codes)
        asset_total_e += ve
        asset_total_b += vb
        rows.append(BSRow(label, ve, vb))
    rows.append(BSRow("资产总计", asset_total_e, asset_total_b, bold=True))

    rows.append(BSRow("负债和所有者权益", 0, 0, level=0, bold=True))
    rows.append(BSRow("负债", 0, 0, level=0, bold=True))
    liab_total_e = liab_total_b = 0
    for label, codes in LIABILITY_LINES:
        ve, vb = -_sum(ne, codes), -_sum(nb, codes)
        liab_total_e += ve
        liab_total_b += vb
        rows.append(BSRow(label, ve, vb))
    rows.append(BSRow("负债合计", liab_total_e, liab_total_b, bold=True))

    rows.append(BSRow("所有者权益", 0, 0, level=0, bold=True))
    eq_total_e = eq_total_b = 0
    for label, codes in EQUITY_LINES:
        ve, vb = -_sum(ne, codes), -_sum(nb, codes)
        eq_total_e += ve
        eq_total_b += vb
        rows.append(BSRow(label, ve, vb))
    undist_e, undist_b = _undistributed(ledger, ne), _undistributed(ledger, nb)
    eq_total_e += undist_e
    eq_total_b += undist_b
    rows.append(BSRow("未分配利润", undist_e, undist_b))
    rows.append(BSRow("所有者权益合计", eq_total_e, eq_total_b, bold=True))
    rows.append(BSRow("负债和所有者权益总计", liab_total_e + eq_total_e,
                      liab_total_b + eq_total_b, bold=True))
    return rows


def income_statement(ledger: Ledger, start: str, end: str) -> list:
    """多步式利润表。"""
    n = ledger.period_nets(start, end)
    revenue = -(_sum(n, ("6001", "6051")))
    op_cost = _sum(n, ("6401", "6402"))
    tax_surcharge = _sum(n, ("6403",))
    sell = _sum(n, ("6601",))
    admin = _sum(n, ("6602",))
    finance = _sum(n, ("6603",))
    invest = -_sum(n, ("6111",))
    impair = _sum(n, ("6701",))
    op_profit = revenue - op_cost - tax_surcharge - sell - admin - finance + invest - impair
    nonop_in = -_sum(n, ("6301",))
    nonop_out = _sum(n, ("6711",))
    total_profit = op_profit + nonop_in - nonop_out
    income_tax = _sum(n, ("6801",))
    net_profit = total_profit - income_tax

    return [
        ISRow("一、营业收入", revenue, bold=True),
        ISRow("减：营业成本", op_cost, indent=True),
        ISRow("税金及附加", tax_surcharge, indent=True),
        ISRow("销售费用", sell, indent=True),
        ISRow("管理费用", admin, indent=True),
        ISRow("财务费用", finance, indent=True),
        ISRow("加：投资收益", invest, indent=True),
        ISRow("资产减值损失", impair, indent=True),
        ISRow("二、营业利润", op_profit, bold=True),
        ISRow("加：营业外收入", nonop_in, indent=True),
        ISRow("减：营业外支出", nonop_out, indent=True),
        ISRow("三、利润总额", total_profit, bold=True),
        ISRow("减：所得税费用", income_tax, indent=True),
        ISRow("四、净利润", net_profit, bold=True),
    ]


def account_balance_table(ledger: Ledger, start: str, end: str) -> list:
    """科目余额表（只列有发生额或期初余额的科目）。"""
    return ledger.balances(start, end)


def trial_balance(ledger: Ledger, start: str, end: str) -> dict:
    """试算平衡表：按借贷两栏列示期初 / 本期 / 期末，并给出合计与差额校验。"""
    rows = []
    totals = {"open_debit": 0, "open_credit": 0,
              "period_debit": 0, "period_credit": 0,
              "close_debit": 0, "close_credit": 0}
    for b in ledger.balances(start, end):
        od, oc = _split(b, "opening")
        cd, cc = _split(b, "closing")
        rows.append({
            "code": b.account.code, "name": b.account.name, "account": b.account,
            "open_debit": od, "open_credit": oc,
            "period_debit": b.period_debit, "period_credit": b.period_credit,
            "close_debit": cd, "close_credit": cc,
        })
        totals["open_debit"] += od
        totals["open_credit"] += oc
        totals["period_debit"] += b.period_debit
        totals["period_credit"] += b.period_credit
        totals["close_debit"] += cd
        totals["close_credit"] += cc
    balanced = (totals["open_debit"] == totals["open_credit"]
                and totals["period_debit"] == totals["period_credit"]
                and totals["close_debit"] == totals["close_credit"])
    return {"rows": rows, "totals": totals, "balanced": balanced}


def _split(balance, which: str) -> tuple:
    """把某个方向的余额拆成借/贷两栏展示。"""
    value = balance.opening if which == "opening" else balance.closing
    if balance.account.direction == C.DEBIT:
        return (value, 0) if value >= 0 else (0, -value)
    return (0, value) if value >= 0 else (-value, 0)


# ---------------------------------------------------------------- 图表数据
def expense_breakdown(ledger: Ledger, start: str, end: str) -> list:
    """费用构成：(科目名, 金额)。用于饼图。"""
    n = ledger.period_nets(start, end)
    amap = ledger.account_map()
    out = []
    for code, net in n.items():
        acc = amap.get(code)
        if acc and acc.category == C.PROFIT and acc.direction == C.DEBIT and net > 0:
            out.append((acc.name, net))
    out.sort(key=lambda x: -x[1])
    return out


def revenue_breakdown(ledger: Ledger, start: str, end: str) -> list:
    n = ledger.period_nets(start, end)
    amap = ledger.account_map()
    out = []
    for code, net in n.items():
        acc = amap.get(code)
        if acc and acc.category == C.PROFIT and acc.direction == C.CREDIT and net < 0:
            out.append((acc.name, -net))
    out.sort(key=lambda x: -x[1])
    return out


def monthly_series(ledger: Ledger, year: int) -> dict:
    """按月统计收入 / 费用 / 净利润，用于柱状图。"""
    from .accounting import month_range
    revenue, expense, net = [], [], []
    for m in range(1, 13):
        s, e = month_range(year, m)
        n = ledger.period_nets(s, e)
        amap = ledger.account_map()
        rev = exp = 0
        for code, val in n.items():
            acc = amap.get(code)
            if not acc or acc.category != C.PROFIT:
                continue
            if acc.direction == C.CREDIT:
                rev += -val
            else:
                exp += val
        revenue.append(rev)
        expense.append(exp)
        net.append(rev - exp)
    return {"year": year, "revenue": revenue, "expense": expense, "net": net}


def available_years(ledger: Ledger) -> list:
    rows = ledger.db.conn.execute(
        "SELECT DISTINCT substr(date,1,4) AS y FROM vouchers ORDER BY y").fetchall()
    years = [int(r["y"]) for r in rows if r["y"]]
    return years or [int(ledger.db.start_date[:4])]