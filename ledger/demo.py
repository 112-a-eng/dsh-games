# -*- coding: utf-8 -*-
"""演示数据：载入一套覆盖数月经营业务的账套，方便查看报表与图表效果。

只在空账套上调用；金额按固定公式生成，保证每次载入结果一致。
"""
from __future__ import annotations

import datetime as dt

from .accounting import Ledger
from .models import Entry, Voucher


def _yuan(n) -> int:
    return int(round(n * 100))


def _v(day, lines, memo, source="manual"):
    entries = [Entry(code, summary, debit, credit)
               for code, debit, credit, summary in lines]
    return Voucher(day, entries, "", memo, 0, None, "posted", source)


def load_demo(ledger: Ledger) -> int:
    db = ledger.db
    year = dt.date.today().year
    db.set_meta("company", "示例科技有限公司")
    db.set_meta("start_date", "%d-01-01" % year)

    # 期初余额：银行存款 + 库存现金 + 固定资产 = 实收资本
    db.replace_openings({
        "1002": _yuan(1_200_000),      # 银行存款
        "1001": _yuan(20_000),         # 库存现金
        "1601": _yuan(500_000),        # 固定资产
        "4001": _yuan(1_720_000),      # 实收资本
    })

    today = dt.date.today()
    last_month = today.month if today.year == year else 12
    count = 0

    for m in range(1, last_month + 1):
        base = 200_000 + m * 5_000
        revenue = _yuan(base)
        tax_out = _yuan(base * 0.13)
        cost = _yuan(base * 0.52)
        purchase = _yuan(base * 0.56)
        tax_in = int(round(purchase * 0.13))
        salary_admin = _yuan(38_000)
        salary_sell = _yuan(22_000)
        rent = _yuan(15_000)
        depreciation = _yuan(9_000)
        interest = _yuan(2_600)

        def day(d):
            return "%04d-%02d-%02d" % (year, m, d)

        # 赊销确认收入
        ledger.save_voucher(_v(day(5), [
            ("1122", revenue + tax_out, 0, "销售商品"),
            ("6001", 0, revenue, "销售商品"),
            ("2221", 0, tax_out, "销项税额"),
        ], "销售商品"))
        count += 1

        # 结转销售成本
        ledger.save_voucher(_v(day(5), [
            ("6401", cost, 0, "结转销售成本"),
            ("1405", 0, cost, "结转销售成本"),
        ], "结转销售成本"))
        count += 1

        # 采购入库
        ledger.save_voucher(_v(day(8), [
            ("1405", purchase, 0, "采购商品"),
            ("2221", tax_in, 0, "进项税额"),
            ("2202", 0, purchase + tax_in, "采购商品"),
        ], "采购商品"))
        count += 1

        # 收到货款
        receipt = revenue + tax_out if m % 2 == 0 else int(round((revenue + tax_out) / 1.13))
        ledger.save_voucher(_v(day(18), [
            ("1002", receipt, 0, "收回货款"),
            ("1122", 0, receipt, "收回货款"),
        ], "收回货款"))
        count += 1

        # 支付供应商货款
        payment = purchase + tax_in
        ledger.save_voucher(_v(day(20), [
            ("2202", payment, 0, "支付货款"),
            ("1002", 0, payment, "支付货款"),
        ], "支付货款"))
        count += 1

        # 计提工资
        ledger.save_voucher(_v(day(25), [
            ("6602", salary_admin, 0, "管理人员工资"),
            ("6601", salary_sell, 0, "销售人员工资"),
            ("2211", 0, salary_admin + salary_sell, "计提工资"),
        ], "计提工资"))
        count += 1

        # 发放工资
        ledger.save_voucher(_v(day(26), [
            ("2211", salary_admin + salary_sell, 0, "发放工资"),
            ("1002", 0, salary_admin + salary_sell, "发放工资"),
        ], "发放工资"))
        count += 1

        # 房租、折旧、利息
        ledger.save_voucher(_v(day(28), [
            ("6602", rent, 0, "办公房租"),
            ("1002", 0, rent, "办公房租"),
        ], "办公房租"))
        count += 1
        ledger.save_voucher(_v(day(28), [
            ("6602", depreciation, 0, "计提固定资产折旧"),
            ("1602", 0, depreciation, "计提固定资产折旧"),
        ], "计提折旧"))
        count += 1
        ledger.save_voucher(_v(day(28), [
            ("6603", interest, 0, "银行贷款利息"),
            ("1002", 0, interest, "银行贷款利息"),
        ], "银行利息"))
        count += 1

    return count