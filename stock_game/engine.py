# -*- coding: utf-8 -*-
"""游戏主引擎：驱动时间、撮合、结算、融资风控与交易日历。

时间模型：一个 tick = 一个交易分钟（A 股每天 240 分钟）。开盘后逐分钟推进，
每分钟先走行情、再用这根分钟线撮合委托，收盘自动结算当日盈亏并生成日线。
"""
from __future__ import annotations

import random

from .account import Account
from .config import DIFFICULTY_BY_KEY, MARKETS, MarketRules
from .market import Difficulty, Market
from .trading import Broker, minute_to_clock


class Game:
    def __init__(self, market_key: str = "cn", difficulty_key: str = "normal",
                 initial_cash: float = 1_000_000.0, seed: int | None = None,
                 max_days: int = 250):
        self.rules: MarketRules = MARKETS[market_key]
        self.difficulty: Difficulty = DIFFICULTY_BY_KEY[difficulty_key]
        self.seed = seed if seed is not None else random.randrange(1, 10 ** 9)
        self.market = Market(self.rules, self.difficulty, seed=self.seed)
        self.account = Account(self.rules, initial_cash)
        self.broker = Broker(self.rules, self.market, self.account)

        self.events: list[str] = []
        self.broker.log = self.events
        self.phase = "preopen"          # preopen / trading / closed / finished
        self.max_days = max_days
        self.day_start_equity = initial_cash
        self._margin_warned = False

    # ------------------------------------------------------------ 时间
    def start(self) -> None:
        """开始新的一天（首个交易日）。"""
        if self.phase == "preopen":
            self.market.start_day()
            self.account.release_t1()
            self.day_start_equity = self.account.equity(self.prices())
            self.phase = "trading"
            self._log_day_open()

    def tick(self) -> None:
        """推进一分钟。"""
        if self.phase != "trading":
            return
        self.market.step()
        self.broker.match_minute()
        self.account.refresh_prices(self.market)
        self._check_margin()
        if self.market.minute >= self.market.total_minutes:
            self.close_day()

    def advance_day(self) -> None:
        """收盘后进入下一个交易日。"""
        if self.phase != "closed":
            return
        if self.max_days and self.market.day >= self.max_days:
            self.finish()
            return
        self.market.start_day()
        self.account.release_t1()
        self.day_start_equity = self.account.equity(self.prices())
        self._margin_warned = False
        self.phase = "trading"
        self._log_day_open()

    def close_day(self) -> None:
        self.broker.close_day()
        self.market.end_day()
        prices = self.prices()
        self.account.settle_day(self.market.day, prices, self.market.index.last)
        snap = self.account.snapshot(prices)
        day_pnl = snap["equity"] - self.day_start_equity
        self.events.append("【收盘】第 %d 日 %s 总资产 %.2f（当日 %+.2f，%.2f%%）指数 %.2f%%"
                           % (self.market.day, self.market.date.strftime("%Y-%m-%d"),
                              snap["equity"], day_pnl,
                              day_pnl / self.day_start_equity * 100 if self.day_start_equity else 0,
                              self.market.index.change_pct))
        self.phase = "closed"

    def finish(self) -> None:
        snap = self.account.snapshot(self.prices())
        self.events.append("【终局】%d 个交易日结束：总资产 %.2f，累计收益 %.2f%%，"
                           "同期指数 %.2f%%"
                           % (self.market.day, snap["equity"], snap["return_pct"],
                              self.benchmark_return() * 100))
        self.phase = "finished"

    def _log_day_open(self) -> None:
        self.events.append("【开盘】第 %d 日 %s（%s）指数昨收 %s"
                           % (self.market.day, self.market.date.strftime("%Y-%m-%d"),
                              self.market.regime_name,
                              "—" if not self.market.index.daily else
                              "%.2f" % self.market.index.prev_close))
        for news in self.market.news_today:
            self.events.append("【消息】" + news.text())

    # ------------------------------------------------------------ 查询
    def prices(self) -> dict[str, float]:
        return {c: s.last for c, s in self.market.stocks.items()}

    def clock(self) -> str:
        return minute_to_clock(self.market.minute, self.rules, self.market.total_minutes)

    def snapshot(self) -> dict:
        snap = self.account.snapshot(self.prices())
        index = self.market.index
        snap.update({
            "day": self.market.day,
            "date": self.market.date.strftime("%Y-%m-%d"),
            "clock": self.clock(),
            "phase": self.phase,
            "regime": self.market.regime_name,
            "index_name": index.name,
            "index": index.last,
            "index_pct": index.change_pct,
            "index_return": self.benchmark_return() * 100,
            "day_pnl": snap["equity"] - self.day_start_equity,
            "initial": self.account.initial_cash,
            "seed": self.seed,
        })
        return snap

    def benchmark_return(self) -> float:
        if not self.market.index.daily:
            return 0.0
        base = self.market.index.daily[0].open
        return self.market.index.last / base - 1.0

    def positions_view(self) -> list[dict]:
        rows = []
        for pos in self.account.positions.values():
            if pos.shares <= 0:
                continue
            stock = self.market.stocks.get(pos.code)
            prev_close = stock.prev_close if stock else pos.last
            rows.append({
                "code": pos.code, "name": pos.name, "shares": pos.shares,
                "available": pos.available, "sellable": pos.sellable,
                "avg_cost": pos.avg_cost, "last": pos.last,
                "market_value": pos.market_value, "unrealized": pos.unrealized,
                "pnl_pct": pos.pnl_pct, "realized": pos.realized,
                "day_pnl": (pos.last - prev_close) * pos.shares,
            })
        rows.sort(key=lambda r: -r["market_value"])
        return rows

    def orders_view(self) -> list[dict]:
        rows = []
        for order in self.broker.orders:
            rows.append({
                "id": order.id, "code": order.code, "name": order.name,
                "side": order.side_text, "kind": order.kind_text,
                "price": order.price, "qty": order.qty, "filled": order.filled,
                "status": order.status, "avg_price": order.avg_price,
                "time": minute_to_clock(order.minute, self.rules, self.market.total_minutes),
            })
        return rows

    # ------------------------------------------------------------ 交易
    def submit(self, code: str, side: str, qty: int, kind: str = "limit",
               price: float = 0.0, use_margin: bool = False):
        return self.broker.submit(code, side, qty, kind, price, use_margin)

    def cancel(self, order_id: int):
        return self.broker.cancel(order_id)

    def cancel_all(self) -> int:
        return self.broker.cancel_all("手动全部撤单")

    # ------------------------------------------------------------ 风控
    def _check_margin(self) -> None:
        if self.account.debt <= 0:
            self._margin_warned = False
            return
        ratio, _ = self.account.margin_status(self.prices())
        if ratio < self.rules.force_close_ratio:
            self.events.append("【风控】维持担保比例 %.0f%% 低于平仓线 %.0f%%，启动强制平仓"
                               % (ratio * 100, self.rules.force_close_ratio * 100))
            self.account.alerts.append("强制平仓（担保比例 %.0f%%）" % (ratio * 100))
            self._liquidate()
        elif ratio < self.rules.warn_ratio and not self._margin_warned:
            self._margin_warned = True
            self.events.append("【风控】维持担保比例 %.0f%% 已低于预警线 %.0f%%，"
                               "请及时补仓或卖券还款"
                               % (ratio * 100, self.rules.warn_ratio * 100))

    def _liquidate(self) -> None:
        """强制平仓：按市值从大到小市价卖出，直到担保比例回到预警线以上。"""
        self.account.forced_liquidation += 1
        pending = {o.code for o in self.broker.orders if o.active and o.side == "sell"}
        submitted = 0
        for pos in sorted(self.account.holdings(), key=lambda p: -p.market_value):
            if pos.code in pending or pos.sellable <= 0:
                continue
            self.broker.submit(pos.code, "sell", pos.sellable, kind="market")
            submitted += 1
            ratio, _ = self.account.margin_status(self.prices())
            if ratio >= self.rules.warn_ratio:
                break
        if not submitted:
            self.events.append("【风控】当前无可卖股份（T+1 限制），暂无法执行平仓")
