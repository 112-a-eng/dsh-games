# -*- coding: utf-8 -*-
"""无界面自测：金额、科目表、凭证校验、过账、余额、报表恒等式、期末结转、长跑不变量。

运行：py -m ledger --self-test
"""
from __future__ import annotations

import random

from . import config as C
from .accounting import Ledger, LedgerError, month_range, valid_date, year_range
from .db import Database
from .models import Account, Entry, Voucher
from .money import fmt_cents, parse_amount
from .reports import (account_balance_table, balance_sheet, income_statement,
                      monthly_series, trial_balance)


class Failure(AssertionError):
    pass


def check(cond, msg):
    if not cond:
        raise Failure(msg)


def fresh(company: str = "测试") -> Ledger:
    db = Database(":memory:")
    db.set_meta("company", company)
    db.set_meta("start_date", "2024-01-01")
    return Ledger(db)


def voucher(day, lines, number="", memo="", source="manual", status="posted"):
    """lines: [(code, debit, credit, summary)]"""
    entries = [Entry(c, s, d, cr) for c, d, cr, s in lines]
    return Voucher(day, entries, number, memo, 0, None, status, source)


# ---------------------------------------------------------------- 金额
def test_money():
    check(parse_amount("12.34") == 1234, "解析 12.34 失败")
    check(parse_amount("1,234.5") == 123450, "解析千分位失败")
    check(parse_amount("¥100") == 10000, "解析货币符号失败")
    check(parse_amount("") == 0, "空值应为 0")
    check(parse_amount("(50)") == -5000, "括号负数解析失败")
    check(parse_amount(100) == 10000, "整数应按元处理")
    check(parse_amount("0.005") == 1, "四舍五入失败")
    check(parse_amount("-3.333") == -333, "负数四舍五入失败")
    check(fmt_cents(123456) == "1,234.56", "格式化失败: %s" % fmt_cents(123456))
    check(fmt_cents(-123456) == "-1,234.56", "负格式化失败")
    check(fmt_cents(0, blank_zero=True) == "", "零应留空")
    try:
        parse_amount("abc")
    except ValueError:
        pass
    else:
        raise Failure("非法金额应抛异常")
    return "金额解析与格式化"


# ---------------------------------------------------------------- 科目表
def test_chart_of_accounts():
    led = fresh()
    accounts = led.accounts()
    check(len(accounts) >= 55, "标准科目数量偏少: %d" % len(accounts))
    codes = {a.code for a in accounts}
    for need in ("1001", "1002", "1122", "1601", "2202", "4001", "4103", "6001", "6602"):
        check(need in codes, "缺少标准科目 %s" % need)
    check(all(a.is_leaf for a in accounts), "标准科目应全部为末级科目")
    check(all(a.code in C.STANDARD_BY_CODE or a.custom for a in accounts), "存在来源不明的科目")
    check(valid_date("2024-02-29") and not valid_date("2023-02-29"), "闰年判断错误")
    check(not valid_date("2024-13-01"), "非法月份应无效")
    check(month_range(2024, 2) == ("2024-02-01", "2024-02-29"), "2 月月末错误")
    check(year_range(2024) == ("2024-01-01", "2024-12-31"), "年度区间错误")
    return "科目表与日期"


# ---------------------------------------------------------------- 凭证校验
def test_validation():
    led = fresh()
    ok = voucher("2024-01-05", [("1001", 100000, 0, "投资"), ("4001", 0, 100000, "投资")])
    check(led.validate(ok) == [], "合法凭证被拒: %r" % led.validate(ok))

    bad_bal = voucher("2024-01-05", [("1001", 100000, 0, ""), ("4001", 0, 90000, "")])
    check(any("不平衡" in e for e in led.validate(bad_bal)), "不平衡凭证未被发现")

    one_line = voucher("2024-01-05", [("1001", 100, 0, "")])
    check(any("两条分录" in e for e in led.validate(one_line)), "单分录凭证未被发现")

    both = voucher("2024-01-05", [("1001", 100, 100, ""), ("4001", 0, 100, "")])
    check(any("只能填一个" in e for e in led.validate(both)), "借贷同填未被发现")

    zero = voucher("2024-01-05", [("1001", 0, 0, ""), ("4001", 0, 0, "")])
    check(any("不能为零" in e for e in led.validate(zero)), "零金额未被发现")

    unknown = voucher("2024-01-05", [("9999", 100, 0, ""), ("4001", 0, 100, "")])
    check(any("不存在" in e for e in led.validate(unknown)), "未知科目未被发现")

    ok_negative_price = voucher("2024-01-05", [("1001", -5, 0, ""), ("4001", 0, -5, "")])
    check(any("不能为负" in e for e in led.validate(ok_negative_price)), "负金额未被发现")

    try:
        led.save_voucher(bad_bal)
    except LedgerError:
        pass
    else:
        raise Failure("不平衡凭证不应保存成功")
    return "凭证借贷校验"


# ---------------------------------------------------------------- 上级科目
def test_parent_account_not_postable():
    led = fresh()
    led.db.add_account(Account("100201", "工行基本户", C.ASSET, C.DEBIT, C.G_CURRENT_ASSET,
                               custom=True))
    parent = led.db.get_account("1002")
    check(parent is not None and not parent.is_leaf, "新增子科目后上级应变为非末级")
    v = voucher("2024-01-05", [("1002", 100, 0, ""), ("4001", 0, 100, "")])
    check(any("上级科目" in e for e in led.validate(v)), "上级科目记账未被拒绝")

    v2 = voucher("2024-01-05", [("100201", 100, 0, ""), ("4001", 0, 100, "")])
    check(led.validate(v2) == [], "自定义子科目应可记账")

    # 删除子科目后上级恢复为末级
    led.db.delete_account("100201")
    check(led.db.get_account("1002").is_leaf, "删除子科目后上级应恢复末级")
    return "明细科目层级"


# ---------------------------------------------------------------- 过账与余额
def test_posting_and_balance():
    led = fresh()
    led.save_voucher(voucher("2024-01-05", [("1001", 100000, 0, "收到投资"),
                                            ("4001", 0, 100000, "收到投资")]))
    led.save_voucher(voucher("2024-01-06", [("1601", 500000, 0, "购设备"),
                                            ("1002", 0, 500000, "购设备")]))
    led.save_voucher(voucher("2024-01-31", [("6602", 20000, 0, "办公费"),
                                            ("1001", 0, 20000, "办公费")]))
    check(led.balance_of("1001") == 80000, "库存现金余额错误: %d" % led.balance_of("1001"))
    check(led.balance_of("1002") == -500000, "银行存款余额错误")
    check(led.balance_of("1601") == 500000, "固定资产余额错误")
    check(led.balance_of("6001") == 0, "无收入应为 0")

    # 草稿凭证不计入余额
    draft = voucher("2024-01-31", [("1001", 30000, 0, "草稿"), ("4001", 0, 30000, "草稿")],
                    status="draft")
    vid = led.db.save_voucher(draft)
    check(led.balance_of("1001") == 80000, "草稿凭证不应影响余额")
    led.post_voucher(vid)
    check(led.balance_of("1001") == 110000, "过账后余额未更新")
    led.unpost_voucher(vid)
    check(led.balance_of("1001") == 80000, "取消过账后余额未回退")
    return "凭证过账与余额"


# ---------------------------------------------------------------- 报表恒等式
def test_reports_identity():
    led = fresh()
    led.save_voucher(voucher("2024-01-05", [("1001", 10000000, 0, "投资"),
                                            ("4001", 0, 10000000, "投资")]))
    led.save_voucher(voucher("2024-01-10", [("1122", 339000, 0, "赊销"),
                                            ("6001", 0, 300000, "收入"),
                                            ("2221", 0, 39000, "销项税")]))
    led.save_voucher(voucher("2024-01-15", [("6401", 120000, 0, "结转成本"),
                                            ("1405", 0, 120000, "结转成本")]))
    led.save_voucher(voucher("2024-01-20", [("1405", 200000, 0, "采购"),
                                            ("2202", 0, 200000, "采购")]))
    led.save_voucher(voucher("2024-01-25", [("6602", 50000, 0, "工资"),
                                            ("1002", 0, 50000, "工资")]))

    tb = trial_balance(led, "2024-01-01", "2024-01-31")
    check(tb["balanced"], "试算不平衡: %r" % tb["totals"])
    check(tb["totals"]["period_debit"] == tb["totals"]["period_credit"], "本期借贷不等")

    bs = balance_sheet(led, "2024-01-31")
    assets = [r for r in bs if r.label == "资产总计"][0].end
    liab = [r for r in bs if r.label == "负债合计"][0].end
    equity = [r for r in bs if r.label == "所有者权益合计"][0].end
    check(assets == liab + equity, "会计恒等式不成立: %d != %d + %d"
          % (assets, liab, equity))

    ist = income_statement(led, "2024-01-01", "2024-01-31")
    net = [r for r in ist if r.label == "四、净利润"][0].value
    expect_net = 300000 - 120000 - 50000
    check(net == expect_net, "净利润错误: %d != %d" % (net, expect_net))
    op = [r for r in ist if r.label == "二、营业利润"][0].value
    check(op == expect_net, "营业利润错误")

    rows = account_balance_table(led, "2024-01-01", "2024-01-31")
    cash = [b for b in rows if b.account.code == "1001"][0]
    check(cash.closing == 10000000, "科目余额表库存现金错误")
    return "试算平衡与会计恒等式"


# ---------------------------------------------------------------- 明细账
def test_detail_ledger():
    led = fresh()
    led.save_voucher(voucher("2024-01-01", [("1001", 100000, 0, "投资"),
                                            ("4001", 0, 100000, "投资")]))
    led.save_voucher(voucher("2024-01-10", [("1001", 5000, 0, "收入"),
                                            ("6001", 0, 5000, "收入")]))
    led.save_voucher(voucher("2024-01-20", [("6602", 3000, 0, "支出"),
                                            ("1001", 0, 3000, "支出")]))
    rows = led.detail_ledger("1001", "2024-01-01", "2024-01-31")
    check(len(rows) == 3, "明细账行数错误: %d" % len(rows))
    check(rows[0].balance == 100000, "首行余额错误")
    check(rows[-1].balance == 102000, "末行余额错误: %d" % rows[-1].balance)
    check(led.opening_of("1001", "2024-01-01") == 0, "期初错误")
    check(led.opening_of("1001", "2024-01-05") == 100000, "1/5 期初应为 10 万")
    check(led.opening_of("1001", "2024-01-15") == 105000, "1/15 期初应为 10.5 万")
    return "明细账滚动余额"


# ---------------------------------------------------------------- 期初余额
def test_opening_balances():
    led = fresh()
    led.db.set_opening("1001", 200000)
    led.db.set_opening("1002", 800000)
    led.db.set_opening("4001", 1000000)
    check(led.opening_check() == 0, "平衡的期初被判定为不平衡")
    check(led.balance_of("1001", "2024-01-01") == 200000, "期初余额未生效")

    led.db.set_opening("2202", 100000)   # 负债 10 万：贷方比借方多 10 万（借正贷负为 -100000）
    check(led.opening_check() == -100000, "期初差额计算错误: %d" % led.opening_check())
    return "期初余额与平衡校验"


# ---------------------------------------------------------------- 期末结转
def test_period_close():
    led = fresh()
    led.save_voucher(voucher("2024-03-05", [("1002", 500000, 0, "收款"),
                                            ("6001", 0, 500000, "收入")]))
    led.save_voucher(voucher("2024-03-20", [("6602", 180000, 0, "费用"),
                                            ("1002", 0, 180000, "费用")]))
    check(led.net_income("2024-03-01", "2024-03-31") == 320000, "结转前净利润错误")

    v = led.close_period("2024-03-01", "2024-03-31")
    check(v is not None and v.balanced(), "结转凭证不平衡")
    check(led.period_nets("2024-03-01", "2024-03-31").get("6001", 0) == 0, "收入未结平")
    check(led.period_nets("2024-03-01", "2024-03-31").get("6602", 0) == 0, "费用未结平")
    check(led.balance_of("4103") == 320000, "本年利润错误: %d" % led.balance_of("4103"))
    check(led.net_income("2024-03-01", "2024-03-31") == 0, "结转后损益应为 0")
    check("2024-03" in led.closed_periods(), "已结转期间未记录")
    check(led.close_period("2024-04-01", "2024-04-30") is None, "空期间不应生成凭证")

    bs = balance_sheet(led, "2024-03-31")
    assets = [r for r in bs if r.label == "资产总计"][0].end
    liab = [r for r in bs if r.label == "负债合计"][0].end
    equity = [r for r in bs if r.label == "所有者权益合计"][0].end
    check(assets == liab + equity, "结转后恒等式不成立")
    undist = [r for r in bs if r.label == "未分配利润"][0].end
    check(undist == 320000, "结转后未分配利润错误: %d" % undist)
    return "期末结转损益"


# ---------------------------------------------------------------- 图表数据
def test_chart_data():
    led = fresh()
    led.save_voucher(voucher("2024-01-10", [("1002", 800000, 0, "收入"),
                                            ("6001", 0, 800000, "收入")]))
    led.save_voucher(voucher("2024-01-15", [("6602", 100000, 0, "管理"),
                                            ("1002", 0, 100000, "管理")]))
    led.save_voucher(voucher("2024-01-16", [("6601", 60000, 0, "销售"),
                                            ("1002", 0, 60000, "销售")]))
    series = monthly_series(led, 2024)
    check(series["revenue"][0] == 800000, "1 月收入错误")
    check(series["expense"][0] == 160000, "1 月费用错误")
    check(series["net"][0] == 640000, "1 月净利错误")
    check(all(x == 0 for x in series["revenue"][1:]), "2 月应为 0")
    from .reports import expense_breakdown, revenue_breakdown
    eb = expense_breakdown(led, "2024-01-01", "2024-01-31")
    check(eb and eb[0][0] == "管理费用", "费用构成排序错误: %r" % eb)
    check(revenue_breakdown(led, "2024-01-01", "2024-01-31")[0][1] == 800000, "收入构成错误")
    return "图表汇总数据"


# ---------------------------------------------------------------- 长跑不变量
def test_long_run_invariants():
    led = fresh()
    accounts = [a.code for a in led.postable_accounts()
                if a.category in (C.ASSET, C.LIABILITY, C.EQUITY, C.PROFIT, C.COST)]
    rng = random.Random(20240101)
    day = 1
    month = 1
    for n in range(600):
        amount = rng.randrange(1, 50000) * 100
        a, b = rng.choice(accounts), rng.choice(accounts)
        if a == b:
            continue
        date = "2024-%02d-%02d" % (month, min(day, 28))
        v = voucher(date, [(a, amount, 0, "分录"), (b, 0, amount, "分录")])
        if not led.validate(v):
            led.save_voucher(v)
        day += 1
        if day > 28:
            day = 1
            month += 1
            if month > 12:
                month = 1
    tb = trial_balance(led, "2024-01-01", "2024-12-31")
    check(tb["balanced"], "长跑后试算不平衡")
    bs = balance_sheet(led, "2024-12-31")
    assets = [r for r in bs if r.label == "资产总计"][0].end
    liab = [r for r in bs if r.label == "负债合计"][0].end
    equity = [r for r in bs if r.label == "所有者权益合计"][0].end
    check(assets == liab + equity, "长跑后会计恒等式不成立: %d != %d + %d"
          % (assets, liab, equity))
    # 明细账滚动余额应与科目余额一致
    for code in ("1001", "1002", "1601", "4001", "6001"):
        rows = led.detail_ledger(code, "2024-01-01", "2024-12-31")
        if rows:
            check(rows[-1].balance == led.balance_of(code, "2024-12-31"),
                  "科目 %s 明细账与余额不符" % code)
    return "600 张凭证长跑不变量"


TESTS = [
    test_money,
    test_chart_of_accounts,
    test_validation,
    test_parent_account_not_postable,
    test_posting_and_balance,
    test_reports_identity,
    test_detail_ledger,
    test_opening_balances,
    test_period_close,
    test_chart_data,
    test_long_run_invariants,
]


def run_all() -> int:
    print("112账务 · 无界面自测")
    print("=" * 56)
    failed = 0
    for fn in TESTS:
        try:
            title = fn()
            print("  [通过] %s" % title)
        except Failure as exc:
            failed += 1
            print("  [失败] %s: %s" % (fn.__name__, exc))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("  [异常] %s: %r" % (fn.__name__, exc))
    print("=" * 56)
    if failed:
        print("自测未通过：%d 项失败" % failed)
        return 1
    print("全部 %d 项自测通过" % len(TESTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(run_all())