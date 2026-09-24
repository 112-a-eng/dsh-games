# -*- coding: utf-8 -*-
"""无界面自测：交易规则、费用、账户会计、撮合真实性与长跑不变量。

运行：py -m stock_game --self-test
"""
from __future__ import annotations

import math
import random

from .config import A_SHARE, US_STOCK, calc_fees, round_price
from .engine import Game
from .trading import validate_qty


class Failure(AssertionError):
    pass


def check(cond, msg):
    if not cond:
        raise Failure(msg)


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


# ---------------------------------------------------------------- 费用
def test_fees():
    f = calc_fees(A_SHARE, "buy", 10.0, 1000)
    check(approx(f.commission, 5.0), "买入佣金未取最低 5 元: %r" % f.commission)
    check(approx(f.stamp_tax, 0.0), "买入不应收印花税")
    check(approx(f.transfer_fee, 0.1), "过户费错误: %r" % f.transfer_fee)
    check(approx(f.total, 5.1), "买入费用合计错误: %r" % f.total)

    s = calc_fees(A_SHARE, "sell", 11.0, 1000)
    check(approx(s.commission, 5.0), "卖出佣金未取最低 5 元")
    check(approx(s.stamp_tax, 5.5), "印花税应为千分之 0.5: %r" % s.stamp_tax)
    check(approx(s.transfer_fee, 0.11), "过户费错误")
    check(approx(s.total, 10.61), "卖出费用合计错误: %r" % s.total)

    big = calc_fees(A_SHARE, "buy", 100.0, 1000)
    check(approx(big.commission, 25.0), "万 2.5 佣金计算错误: %r" % big.commission)

    us = calc_fees(US_STOCK, "sell", 100.0, 100)
    check(approx(us.total, 0.0), "美股预设应为零佣金: %r" % us.total)
    check(approx(round_price(A_SHARE, 10.005), 10.01), "价格取整错误")
    return "费用模型"


# ---------------------------------------------------------------- 申报数量
def test_lot_rules():
    check(validate_qty(A_SHARE, "主板", "buy", 100, 0) is None, "主板 100 股应合法")
    check(validate_qty(A_SHARE, "主板", "buy", 150, 0) is not None, "主板 150 股应非法")
    check(validate_qty(A_SHARE, "创业板", "buy", 300, 0) is None, "创业板 300 股应合法")
    check(validate_qty(A_SHARE, "科创板", "buy", 100, 0) is not None, "科创板 100 股应非法")
    check(validate_qty(A_SHARE, "科创板", "buy", 201, 0) is None, "科创板 201 股应合法（1 股递增）")
    check(validate_qty(A_SHARE, "主板", "sell", 37, 37) is None, "零股应可一次性卖出")
    check(validate_qty(A_SHARE, "主板", "sell", 37, 137) is not None, "非全部卖出时零股应非法")
    check(validate_qty(US_STOCK, "主板", "buy", 3, 0) is None, "美股 3 股应合法")
    check(validate_qty(A_SHARE, "主板", "buy", 0, 0) is not None, "0 股应非法")
    return "申报数量规则"


# ---------------------------------------------------------------- 撮合真实性
def test_no_lookahead_and_rules():
    game = Game(seed=1001, initial_cash=2_000_000)
    game.start()
    for _ in range(5):
        game.tick()
    stock = game.market.stocks["600519"]

    # 涨停价以上的委托属废单
    ok, msg, _ = game.submit("600519", "buy", 100, "limit", stock.limit_up + 1)
    check(not ok and "废单" in msg, "高于涨停价的委托应被拒绝")

    # 上市首分钟不可能成交：下单后必须等下一根分钟线
    ok, msg, order = game.submit("600519", "buy", 100, "limit", round(stock.last * 1.03, 2))
    check(ok, "合法委托被拒绝: %s" % msg)
    check(order.filled == 0, "下单瞬间就成交了（偷价：用了已走完的行情）")

    game.tick()
    check(order.filled == 100, "下一分钟应成交，实际成交 %d" % order.filled)
    bar = game.market.stocks["600519"].bars[-1]
    check(bar.low - 1e-9 <= order.avg_price <= bar.high + 1e-9,
          "成交价 %.4f 不在该分钟 K 线 [%.4f, %.4f] 内"
          % (order.avg_price, bar.low, bar.high))

    # T+1：当日买入不可卖
    pos = game.account.position("600519")
    check(pos.shares == 100, "持仓数量错误")
    check(pos.sellable == 0, "A 股当日买入不应可卖（T+1）")
    ok, msg, _ = game.submit("600519", "sell", 100, "limit", round(stock.last * 0.97, 2))
    check(not ok and "可用数量不足" in msg, "T+1 限制未生效: %s" % msg)

    # 收盘 → 次日解冻后可卖
    while game.phase == "trading":
        game.tick()
    check(game.phase == "closed", "收盘状态未切换")
    game.advance_day()
    pos = game.account.position("600519")
    check(pos.sellable == 100, "次日应解冻为可卖，实际 %d" % pos.sellable)
    ok, msg, _ = game.submit("600519", "sell", 100, "limit", round(stock.last * 0.97, 2))
    check(ok, "解冻后卖出应被接受: %s" % msg)
    return "撮合与交易规则"


# ---------------------------------------------------------------- 部分成交与冻结
def test_partial_fill_and_cancel():
    game = Game(seed=2002, initial_cash=50_000_000)
    game.start()
    game.tick()
    stock = game.market.stocks["601668"]           # 低价股，方便构造大单
    ok, msg, order = game.submit("601668", "buy", 4_000_000, "limit",
                                 round(stock.last * 1.02, 2))
    check(ok, "大额委托被拒绝: %s" % msg)
    frozen_before = game.account.frozen_cash
    game.tick()
    check(order.filled > 0, "应至少部分成交")
    check(order.active, "大额委托应处于部分成交状态（参与度上限）")
    check(order.filled < order.qty, "参与度上限未生效：一次全部成交了")

    cash_before = game.account.cash
    remaining = order.remaining
    frozen = game.account.frozen_cash
    ok, _ = game.cancel(order.id)
    check(ok, "撤单失败")
    check(order.status.startswith("部分成交后撤单"), "撤单状态错误: %s" % order.status)
    check(game.account.frozen_cash < frozen, "撤单后冻结资金未释放")
    check(approx(game.account.cash, cash_before, 1e-9), "撤单不应改变现金")
    check(game.account.frozen_cash >= -1e-9, "冻结资金为负")
    check(remaining > 0, "测试构造失败")
    return "部分成交与撤单"


# ---------------------------------------------------------------- 会计恒等式
def equity_identity(game):
    """equity == 初始资金 + 已实现 + 浮动 - 累计利息"""
    prices = game.prices()
    acc = game.account
    snap = acc.snapshot(prices)
    lhs = snap["equity"]
    rhs = acc.initial_cash + acc.realized_pnl + snap["unrealized"] - acc.interest_total
    return lhs, rhs


def test_accounting_identity():
    game = Game(seed=3003, initial_cash=1_000_000)
    game.start()
    rng = random.Random(11)
    for _ in range(6):
        for _ in range(game.market.total_minutes):
            if rng.random() < 0.03:
                code = rng.choice(game.market.order_codes)
                stock = game.market.stocks[code]
                qty = rng.choice([100, 200, 500])
                if rng.random() < 0.6:
                    game.submit(code, "buy", qty, "limit", round(stock.last * 1.01, 2))
                else:
                    game.submit(code, "sell", qty, "limit", round(stock.last * 0.99, 2))
            game.tick()
        lhs, rhs = equity_identity(game)
        check(approx(lhs, rhs, 1e-6), "会计恒等式被破坏：%.6f != %.6f" % (lhs, rhs))
        check(game.account.cash >= -1e-6, "现金为负: %r" % game.account.cash)
        check(game.account.frozen_cash >= -1e-9, "冻结资金为负")
        check(game.account.frozen_cash <= game.account.cash + 1e-6, "冻结资金超过现金")
        for pos in game.account.positions.values():
            check(pos.shares >= 0 and pos.available >= 0 and pos.frozen >= 0, "持仓出现负数")
            check(pos.frozen <= pos.shares, "冻结股数超过持仓")
        game.advance_day()

    # 卖出实现盈亏：手工核对一笔
    game2 = Game(seed=3004, initial_cash=1_000_000)
    game2.start()
    game2.tick()
    stock = game2.market.stocks["600030"]
    price = round(stock.last * 1.02, 2)
    ok, msg, order = game2.submit("600030", "buy", 1000, "limit", price)
    check(ok, "买入被拒: %s" % msg)
    game2.tick()
    pos = game2.account.position("600030")
    check(pos.shares == 1000, "买入未成交")
    buy_cost = pos.cost_amount
    check(buy_cost > order.amount_filled, "持仓成本应包含买入费用")
    while game2.phase == "trading":
        game2.tick()
    game2.advance_day()
    stock = game2.market.stocks["600030"]
    sell_price = round(stock.last * 0.98, 2)
    ok, msg, sorder = game2.submit("600030", "sell", 1000, "limit", sell_price)
    check(ok, "卖出被拒: %s" % msg)
    game2.tick()
    check(game2.account.position("600030").shares == 0, "卖出未全部成交")
    expected = sorder.amount_filled - sorder.fees_charged.total - buy_cost
    check(approx(game2.account.realized_pnl, expected, 1e-6),
          "已实现盈亏错误：%.4f != %.4f" % (game2.account.realized_pnl, expected))
    return "账户会计与盈亏"


# ---------------------------------------------------------------- 融资与强平
def test_margin_and_liquidation():
    game = Game(seed=4004, initial_cash=100_000)
    game.start()
    game.tick()
    stock = game.market.stocks["000001"]
    qty = 5_000                                     # 约 5.6 万，加上已有资金可全款
    ok, msg, order = game.submit("000001", "buy", qty, "limit", round(stock.last * 1.01, 2))
    check(ok, "普通买入被拒: %s" % msg)
    game.tick()
    check(game.account.debt == 0, "资金充足时不应产生负债")

    # 融资买入：用超出现金的额度，勾选融资
    stock = game.market.stocks["000001"]
    ok, msg, morder = game.submit("000001", "buy", 8_000, "limit",
                                  round(stock.last * 1.01, 2), use_margin=True)
    check(ok, "融资买入被拒: %s" % msg)
    game.tick()
    check(morder.filled > 0, "融资买入未成交")
    game.tick()
    check(game.account.debt > 0, "融资买入未产生负债")
    check(game.account.interest_total == 0, "利息应在收盘结算时才计提")
    debt_before = game.account.debt
    interest = game.account.accrue_interest()
    check(interest > 0 and game.account.debt > debt_before, "利息计提失败")

    # 正常状态下不应触发强平
    game._check_margin()
    check(not any(o.active and o.side == "sell" for o in game.broker.orders),
          "担保比例正常时不应强平")

    # 次日解冻持仓（T+1 下当日买入无法平仓，这与真实规则一致）
    while game.phase == "trading":
        game.tick()
    game.advance_day()

    # 崩塌行情触发强平：压低行情最新价
    for code in list(game.account.positions):
        game.market.stocks[code].last *= 0.30
    ratio, status = game.account.margin_status(game.prices())
    check(ratio < A_SHARE.force_close_ratio, "构造的担保比例未低于平仓线: %.3f" % ratio)
    before = len(game.broker.orders)
    game._check_margin()
    check(len(game.broker.orders) > before, "未触发强制平仓")
    check(any(o.active and o.side == "sell" for o in game.broker.orders), "强平未生成卖单")
    check(game.account.forced_liquidation > 0, "强平计数未累加")

    # 强平单成交后应偿还负债
    debt_before = game.account.debt
    for _ in range(30):
        game.tick()
    check(game.account.debt < debt_before, "强平成交后负债未下降")
    return "融资、利息与强制平仓"


# ---------------------------------------------------------------- 长跑
def test_long_run():
    game = Game(seed=5150, initial_cash=1_000_000, max_days=60)
    game.start()
    rng = random.Random(2024)
    fills_checked = 0
    orders_seen = 0
    for _ in range(game.max_days):
        for _ in range(game.market.total_minutes):
            if rng.random() < 0.006:
                code = rng.choice(game.market.order_codes)
                stock = game.market.stocks[code]
                qty = rng.choice([100, 200, 500, 1000])
                if rng.random() < 0.55:
                    game.submit(code, "buy", qty, "limit", round(stock.last * 1.005, 2))
                else:
                    game.submit(code, "sell", qty, "limit", round(stock.last * 0.995, 2))
                orders_seen += 1
            if rng.random() < 0.004:
                active = [o for o in game.broker.orders if o.active]
                if active:
                    game.cancel(rng.choice(active).id)

            trades_before = len(game.account.trades)
            game.tick()

            # 每笔成交都必须落在对应分钟 K 线的价格区间内
            for trade in game.account.trades[trades_before:]:
                bar = game.market.stocks[trade.code].bars[-1]
                check(bar.low - 1e-9 <= trade.price <= bar.high + 1e-9,
                      "成交价越界：%s %.4f 不在 [%.4f, %.4f]"
                      % (trade.code, trade.price, bar.low, bar.high))
                check(trade.qty > 0 and trade.qty % 100 == 0 or A_SHARE.key != "cn",
                      "A 股成交数量不是 100 的整数倍: %d" % trade.qty)
                fills_checked += 1

            lhs, rhs = equity_identity(game)
            check(approx(lhs, rhs, 1e-6), "长跑中会计恒等式被破坏：%.6f != %.6f" % (lhs, rhs))
            check(game.account.cash >= -1e-6, "现金为负")
            for pos in game.account.positions.values():
                check(pos.shares >= 0 and pos.frozen <= pos.shares, "持仓异常")
            for stock in game.market.stocks.values():
                check(math.isfinite(stock.last) and stock.last > 0, "股价异常")
                check(stock.limit_down - 1e-9 <= stock.last <= stock.limit_up + 1e-9,
                      "%s 股价越过涨跌停" % stock.code)

        game.advance_day()
        check(not any(o.active for o in game.broker.orders), "收盘后仍有未成交委托")
        settled = game.market.day - 1 if game.phase != "finished" else game.market.day
        check(len(game.account.nav) == settled,
              "净值曲线长度与已结算交易日数不一致：%d != %d"
              % (len(game.account.nav), settled))

    snap = game.snapshot()
    check(math.isfinite(snap["equity"]), "总资产出现 NaN")
    check(len(game.account.nav) == game.max_days, "净值曲线天数错误")
    check(game.phase in ("closed", "finished"), "收盘状态错误: %s" % game.phase)
    return ("长跑 %d 日（下单 %d 次，校验成交 %d 笔）"
            % (game.max_days, orders_seen, fills_checked))


# ---------------------------------------------------------------- 美股预设
def test_us_preset():
    game = Game(market_key="us", seed=6006, initial_cash=100_000)
    game.start()
    game.tick()
    stock = game.market.stocks["AAPL"]
    ok, msg, order = game.submit("AAPL", "buy", 3, "limit", round(stock.last * 1.01, 2))
    check(ok, "美股买入被拒: %s" % msg)
    game.tick()
    check(order.filled == 3, "美股未成交")
    pos = game.account.position("AAPL")
    check(pos.sellable == 3, "美股 T+0 应立即可卖，实际 %d" % pos.sellable)
    check(math.isinf(stock.limit_up), "美股不应有涨停限制")
    f = calc_fees(US_STOCK, "buy", stock.last, 3)
    check(approx(f.total, 0.0), "美股应为零佣金")
    return "美股预设（T+0 / 无涨跌停 / 零佣金）"


def run_all(verbose=True) -> int:
    tests = [
        test_fees, test_lot_rules, test_no_lookahead_and_rules,
        test_partial_fill_and_cancel, test_accounting_identity,
        test_margin_and_liquidation, test_us_preset, test_long_run,
    ]
    failures = 0
    for test in tests:
        try:
            label = test()
            if verbose:
                print("  [通过] %-28s %s" % (test.__name__[5:], label))
        except Failure as exc:
            failures += 1
            print("  [失败] %-28s %s" % (test.__name__[5:], exc))
        except Exception as exc:                     # noqa: BLE001
            failures += 1
            import traceback
            print("  [异常] %-28s %r" % (test.__name__[5:], exc))
            traceback.print_exc()
    print("\n自测结果：%d 项通过，%d 项失败" % (len(tests) - failures, failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run_all())
