# -*- coding: utf-8 -*-
"""账户、持仓、盈亏与融资（保证金）核算。

会计口径贴近真实券商：
  * 持仓成本含买入费用（摊薄成本），卖出盈亏 = 净卖出所得 - 卖出部分成本；
  * 已实现盈亏与浮动盈亏分开统计，手续费/印花税单独累计；
  * T+1：当日买入计入持仓但不计入可用数量，次日开盘解冻；
  * 挂单资金/股份冻结，撤单或成交后按比例释放；
  * 融资：现金不足时自动转为负债，卖出所得优先还款，每日计提利息，
    维持担保比例低于预警线/平仓线会给出警告并可能被强制平仓。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import FeeBreakdown, MarketRules


@dataclass
class TradeRecord:
    day: int
    minute: int
    code: str
    name: str
    side: str
    qty: int
    price: float
    amount: float
    fees: float
    realized: float = 0.0
    note: str = ""

    @property
    def side_text(self) -> str:
        return "买入" if self.side == "buy" else "卖出"


@dataclass
class Position:
    code: str
    name: str = ""
    shares: int = 0              # 总持仓（股）
    available: int = 0           # 可卖数量（T+1 解冻后）
    frozen: int = 0              # 挂单卖出冻结
    cost_amount: float = 0.0     # 持仓成本总额（含买入费用）
    realized: float = 0.0        # 该股已实现盈亏
    last: float = 0.0            # 最新价（由行情刷新）

    @property
    def avg_cost(self) -> float:
        return self.cost_amount / self.shares if self.shares else 0.0

    @property
    def market_value(self) -> float:
        return self.shares * self.last

    @property
    def unrealized(self) -> float:
        return self.market_value - self.cost_amount

    @property
    def pnl_pct(self) -> float:
        return (self.unrealized / self.cost_amount * 100) if self.cost_amount else 0.0

    @property
    def sellable(self) -> int:
        return max(0, min(self.available - self.frozen, self.shares - self.frozen))


class Account:
    """资金账户。"""

    def __init__(self, rules: MarketRules, initial_cash: float = 1_000_000.0):
        self.rules = rules
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.frozen_cash = 0.0
        self.positions: dict[str, Position] = {}
        self.realized_pnl = 0.0
        self.total_fees = 0.0
        self.total_tax = 0.0
        self.debt = 0.0                  # 融资负债
        self.interest_total = 0.0
        self.trades: list[TradeRecord] = []
        self.nav: list[tuple[int, float]] = []          # (交易日, 总资产)
        self.benchmark: list[tuple[int, float]] = []    # (交易日, 指数)
        self.alerts: list[str] = []
        self.forced_liquidation = 0

    # ---------------------------------------------------------- 基础量
    def position(self, code: str, name: str = "") -> Position:
        pos = self.positions.get(code)
        if pos is None:
            pos = Position(code=code, name=name)
            self.positions[code] = pos
        elif name and not pos.name:
            pos.name = name
        return pos

    def holdings(self) -> list[Position]:
        return [p for p in self.positions.values() if p.shares > 0]

    @property
    def available_cash(self) -> float:
        """可动用资金（扣除挂单冻结）。"""
        return max(0.0, self.cash - self.frozen_cash)

    def market_value(self, prices: dict[str, float]) -> float:
        return sum(p.shares * prices.get(p.code, p.last) for p in self.positions.values())

    def equity(self, prices: dict[str, float]) -> float:
        """总资产（净资产）= 现金 + 持仓市值 - 融资负债。"""
        return self.cash + self.market_value(prices) - self.debt

    def total_assets(self, prices: dict[str, float]) -> float:
        """总资产（含负债口径，用于计算维持担保比例）。"""
        return self.cash + self.market_value(prices)

    def unrealized(self, prices: dict[str, float]) -> float:
        total = 0.0
        for p in self.positions.values():
            price = prices.get(p.code, p.last)
            total += p.shares * price - p.cost_amount
        return total

    def refresh_prices(self, market) -> None:
        for code, pos in self.positions.items():
            stock = market.stocks.get(code)
            if stock:
                pos.last = stock.last
                if not pos.name:
                    pos.name = stock.name

    # ---------------------------------------------------------- 冻结
    def freeze_cash(self, amount: float) -> None:
        self.frozen_cash += amount

    def release_cash(self, amount: float) -> None:
        self.frozen_cash = max(0.0, self.frozen_cash - amount)

    def freeze_shares(self, code: str, qty: int) -> None:
        self.position(code).frozen += qty

    def release_shares(self, code: str, qty: int) -> None:
        pos = self.position(code)
        pos.frozen = max(0, pos.frozen - qty)

    def release_t1(self) -> None:
        """新交易日开盘：昨日买入的股份转为可用。"""
        for pos in self.positions.values():
            pos.available = max(0, pos.shares - pos.frozen)

    # ---------------------------------------------------------- 成交处理
    def apply_buy(self, code: str, name: str, qty: int, price: float,
                  fees: FeeBreakdown) -> None:
        pos = self.position(code, name)
        cost = price * qty + fees.total
        pos.shares += qty
        pos.cost_amount += cost
        if not self.rules.t_plus_1:
            pos.available += qty

        self.cash -= cost
        self.total_fees += fees.commission + fees.transfer_fee
        self.total_tax += fees.stamp_tax
        if self.cash < 0:                      # 现金不足部分自动转为融资负债
            self.debt += -self.cash
            self.cash = 0.0

    def apply_sell(self, code: str, qty: int, price: float,
                   fees: FeeBreakdown) -> float:
        pos = self.position(code)
        avg_cost = pos.avg_cost
        cost_removed = avg_cost * qty
        proceeds = price * qty - fees.total
        realized = proceeds - cost_removed

        pos.shares -= qty
        pos.available = max(0, pos.available - qty)
        pos.frozen = max(0, pos.frozen - qty)
        pos.cost_amount = max(0.0, pos.cost_amount - cost_removed)
        pos.realized += realized
        if pos.shares == 0:
            pos.cost_amount = 0.0

        self.cash += proceeds
        self.realized_pnl += realized
        self.total_fees += fees.commission + fees.transfer_fee
        self.total_tax += fees.stamp_tax

        if self.debt > 0:                      # 卖出所得优先偿还融资负债
            repay = min(self.cash, self.debt)
            if repay > 0:
                self.cash -= repay
                self.debt -= repay
        return realized

    def record(self, record: TradeRecord) -> None:
        self.trades.append(record)

    # ---------------------------------------------------------- 融资
    def accrue_interest(self) -> float:
        if self.debt <= 0:
            return 0.0
        interest = self.debt * self.rules.margin_annual_rate / 365.0
        self.debt += interest
        self.interest_total += interest
        return interest

    def margin_ratio(self, prices: dict[str, float]) -> float:
        """维持担保比例 = 总资产 / 负债；无负债返回 inf。"""
        if self.debt <= 0:
            return float("inf")
        return self.total_assets(prices) / self.debt

    def margin_room(self, prices: dict[str, float]) -> float:
        """还可融资的额度：净资产 × 保证金比例 - 已有负债。"""
        if not self.rules.margin_enabled:
            return 0.0
        net = self.equity(prices)
        return max(0.0, net * self.rules.margin_ratio - self.debt)

    def buying_power(self, prices: dict[str, float], use_margin: bool) -> float:
        power = self.available_cash
        if use_margin:
            power += self.margin_room(prices)
        return power

    def margin_status(self, prices: dict[str, float]) -> tuple[float, str]:
        """返回（维持担保比例, 状态文案）。"""
        if self.debt <= 0:
            return float("inf"), "无负债"
        ratio = self.margin_ratio(prices)
        if ratio < self.rules.force_close_ratio:
            return ratio, "已触及平仓线"
        if ratio < self.rules.warn_ratio:
            return ratio, "低于预警线，请及时补仓或还款"
        return ratio, "正常"

    # ---------------------------------------------------------- 结算
    def settle_day(self, day: int, prices: dict[str, float], index_value: float) -> None:
        self.accrue_interest()
        self.nav.append((day, self.equity(prices)))
        self.benchmark.append((day, index_value))

    def snapshot(self, prices: dict[str, float]) -> dict:
        mv = self.market_value(prices)
        equity = self.cash + mv - self.debt
        ratio, status = self.margin_status(prices)
        return {
            "cash": self.cash,
            "available": self.available_cash,
            "frozen_cash": self.frozen_cash,
            "market_value": mv,
            "equity": equity,
            "debt": self.debt,
            "interest": self.interest_total,
            "realized": self.realized_pnl,
            "unrealized": self.unrealized(prices),
            "fees": self.total_fees,
            "tax": self.total_tax,
            "return_pct": (equity / self.initial_cash - 1.0) * 100,
            "margin_ratio": ratio,
            "margin_status": status,
        }
