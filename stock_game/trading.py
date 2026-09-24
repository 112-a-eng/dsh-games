# -*- coding: utf-8 -*-
"""委托与撮合。

贴近真实的撮合规则：
  * 委托校验：板块最小申报单位（主板/创业板 100 股整数倍、科创板 200 股起 1 股递增、
    美股 1 股）、涨跌停价废单、停牌不可交易、T+1 可用数量、资金/持仓冻结；
  * 不偷价：下单只能由"下单之后的下一根分钟线"撮合，绝不使用已经走完的行情成交；
  * 限价单跳空以更优价成交，未触及则挂单等待；
  * 市价单按"即时成交剩余撤销"(IOC) 处理，未成交部分自动撤单；
  * 滑点 + 冲击成本（与下单量占该分钟成交量的比例相关），并按最小价位让价取整；
  * 单分钟成交量参与度上限，超出部分部分成交，下一分钟继续；
  * 一字板（涨停无卖单/跌停无买单）无法成交；
  * 收盘后所有未成交委托自动失效；手续费按累计成交量重算，避免最低佣金被重复收取。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .account import TradeRecord
from .config import FeeBreakdown, MarketRules, calc_fees, round_price

ACTIVE_STATUS = ("待成交", "部分成交")


@dataclass
class Order:
    id: int
    code: str
    name: str
    side: str                     # buy / sell
    kind: str                     # market / limit
    price: float                  # 限价（市价单为 0）
    qty: int
    day: int
    minute: int
    created_seq: int
    use_margin: bool = False
    filled: int = 0
    amount_filled: float = 0.0
    fees_charged: FeeBreakdown = field(default_factory=FeeBreakdown)
    frozen_per_share: float = 0.0
    status: str = "待成交"
    reason: str = ""
    seq_matched: int = 0          # 已参与撮合的行情序号

    @property
    def remaining(self) -> int:
        return self.qty - self.filled

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_STATUS

    @property
    def avg_price(self) -> float:
        return self.amount_filled / self.filled if self.filled else 0.0

    @property
    def kind_text(self) -> str:
        return "市价" if self.kind == "market" else "限价"

    @property
    def side_text(self) -> str:
        return "买入" if self.side == "buy" else "卖出"

    def frozen_cash_now(self) -> float:
        return self.frozen_per_share * self.remaining if self.side == "buy" else 0.0


def validate_qty(rules: MarketRules, stock_board: str, side: str,
                 qty: int, available: int) -> str | None:
    """按板块规则校验申报数量，返回错误文案或 None。"""
    if qty <= 0:
        return "委托数量必须大于 0"
    if rules.key == "us":
        return None
    lot = rules.lot_size
    if stock_board == "科创板":
        if side == "buy":
            return None if qty >= 200 else "科创板买入申报数量不得低于 200 股"
        if qty < 200 and qty != available:
            return "科创板卖出不足 200 股时需一次性全部卖出"
        return None
    if qty % lot != 0:
        if side == "sell" and qty == available:
            return None
        return "委托数量必须是 %d 股的整数倍" % lot
    return None


class Broker:
    """撮合器：负责校验、冻结、成交与回报。"""

    def __init__(self, rules: MarketRules, market, account):
        self.rules = rules
        self.market = market
        self.account = account
        self.orders: list[Order] = []          # 当日委托
        self.history: list[Order] = []         # 历史委托
        self.log: list[str] = []
        self._next_id = 1

    # ------------------------------------------------------------ 工具
    def _stamp(self) -> str:
        return "[%02d日 %s]" % (self.market.day, self.clock())

    def clock(self) -> str:
        return minute_to_clock(self.market.minute, self.rules, self.market.total_minutes)

    def current_seq(self) -> int:
        """下一根待生成行情线的序号（用于防止用已走完的行情成交）。"""
        return self.market.day * 100000 + self.market.minute

    def _prices(self) -> dict[str, float]:
        return {c: s.last for c, s in self.market.stocks.items()}

    def estimate_buy_cost(self, code: str, qty: int, price: float,
                          kind: str = "limit") -> float:
        """买入所需资金（含费用估计）。市价单按涨停价冻结，与真实券商一致。"""
        stock = self.market.stocks[code]
        if kind == "market":
            ref = stock.limit_up if math.isfinite(stock.limit_up) else stock.last * 1.05
        else:
            ref = price
        return ref * qty + calc_fees(self.rules, "buy", ref, qty).total

    # ------------------------------------------------------------ 下单
    def submit(self, code: str, side: str, qty: int, kind: str = "limit",
               price: float = 0.0, use_margin: bool = False) -> tuple[bool, str, Order | None]:
        stock = self.market.stocks.get(code)
        if stock is None:
            return False, "标的不存在", None
        if self.market.minute >= self.market.total_minutes:
            return False, "已收盘，无法委托", None
        if stock.halted:
            return False, "%s 停牌中，无法交易" % stock.name, None

        qty = int(qty)
        if kind == "limit":
            price = round_price(self.rules, price)
            if price <= 0:
                return False, "委托价格必须大于 0", None
            if price > stock.limit_up + 1e-9:
                return False, "委托价高于涨停价 %.2f，属废单" % stock.limit_up, None
            if price < stock.limit_down - 1e-9:
                return False, "委托价低于跌停价 %.2f，属废单" % stock.limit_down, None

        pos = self.account.position(code, stock.name)
        err = validate_qty(self.rules, stock.board, side, qty,
                           pos.sellable if side == "sell" else 0)
        if err:
            return False, err, None

        if side == "sell":
            if qty > pos.sellable:
                return False, "可用数量不足（可卖 %d 股，T+1 当日买入不可卖）" % pos.sellable, None
        else:
            need = self.estimate_buy_cost(code, qty, price, kind)
            power = self.account.buying_power(self._prices(), use_margin)
            if need > power + 1e-6:
                return False, ("可用资金不足：需 %.2f，可用 %.2f%s"
                               % (need, power, "" if use_margin else "（可勾选融资买入）")), None

        order = Order(
            id=self._next_id, code=code, name=stock.name, side=side, kind=kind,
            price=price, qty=qty, day=self.market.day, minute=self.market.minute,
            created_seq=self.current_seq(), use_margin=use_margin,
        )
        self._next_id += 1

        if side == "buy":
            need = self.estimate_buy_cost(code, qty, price, kind)
            order.frozen_per_share = need / qty
            self.account.freeze_cash(need)
        else:
            self.account.freeze_shares(code, qty)

        self.orders.append(order)
        self.log.append("%s 委托 %s %s %d 股 @ %s [%s]" % (
            self._stamp(), order.side_text, stock.name, qty,
            "市价" if kind == "market" else "%.2f" % price, order.status))
        return True, "委托已提交", order

    # ------------------------------------------------------------ 撤单
    def cancel(self, order_id: int, reason: str = "用户撤单") -> tuple[bool, str]:
        for order in self.orders:
            if order.id == order_id and order.active:
                self._release(order, reason)
                return True, "已撤单"
        return False, "该委托不可撤"

    def _release(self, order: Order, reason: str) -> None:
        if order.side == "buy":
            self.account.release_cash(order.frozen_cash_now())
        else:
            self.account.release_shares(order.code, order.remaining)
        order.status = "已撤单" if order.filled == 0 else "部分成交后撤单"
        order.reason = reason
        self.log.append("%s %s %s %d 股 %s" % (self._stamp(), order.name,
                                               order.side_text, order.remaining, reason))

    def cancel_all(self, reason: str = "收盘未成交委托自动失效") -> int:
        count = 0
        for order in self.orders:
            if order.active:
                self._release(order, reason)
                count += 1
        return count

    def close_day(self) -> None:
        self.cancel_all()
        self.history.extend(self.orders)
        self.orders = []

    # ------------------------------------------------------------ 撮合
    def match_minute(self) -> list[TradeRecord]:
        """用最新的一根分钟线撮合所有活跃委托。"""
        trades: list[TradeRecord] = []
        for order in self.orders:
            if not order.active:
                continue
            stock = self.market.stocks[order.code]
            if not stock.bars:
                continue
            bar = stock.bars[-1]
            seq = self.market.day * 100000 + bar.minute
            if seq < order.created_seq:
                continue
            if bar.volume <= 0:
                continue

            fill_price, block = self._fill_price(order, stock, bar)
            if block:
                if order.kind == "market":
                    self._release(order, block)
                continue
            if fill_price is None:
                if order.kind == "market":
                    self._release(order, "市价委托未成交，自动撤单")
                continue

            qty = self._fillable_qty(order, bar)
            if qty <= 0:
                continue
            price = self._adjust_price(order, bar, fill_price, qty, stock)
            record = self._execute(order, qty, price, bar)
            if record:
                trades.append(record)

            if order.kind == "market" and order.active:
                self._release(order, "市价委托剩余部分自动撤销")
        return trades

    def _fill_price(self, order: Order, stock, bar) -> tuple[float | None, str | None]:
        if order.side == "buy":
            if bar.low >= stock.limit_up - 1e-9:
                return None, "一字涨停，买单无法成交"
            if order.kind == "market":
                return bar.close, None
            if bar.open <= order.price:
                return bar.open, None                 # 跳空低开，以更优价成交
            if bar.low <= order.price:
                return order.price, None
            return None, None
        if bar.high <= stock.limit_down + 1e-9:
            return None, "一字跌停，卖单无法成交"
        if order.kind == "market":
            return bar.close, None
        if bar.open >= order.price:
            return bar.open, None                     # 跳空高开，以更优价成交
        if bar.high >= order.price:
            return order.price, None
        return None, None

    def _fillable_qty(self, order: Order, bar) -> int:
        cap = max(self.rules.lot_size, int(bar.volume * self.rules.participation))
        qty = min(order.remaining, cap)
        if self.rules.lot_size > 1:
            qty = qty // self.rules.lot_size * self.rules.lot_size
            if order.remaining < self.rules.lot_size:      # 零股需一次卖完
                qty = min(order.remaining, cap)
        return max(0, qty)

    def _adjust_price(self, order: Order, bar, base: float, qty: int, stock) -> float:
        """加上滑点与冲击成本，并按最小价位让价取整。"""
        participation = qty / max(1, bar.volume)
        cost = self.rules.slippage_bps / 10000.0 \
            + self.rules.impact_coeff * 0.02 * participation
        raw = base * (1 + cost) if order.side == "buy" else base * (1 - cost)
        tick = self.rules.tick
        if order.side == "buy":
            price = math.ceil(raw / tick - 1e-9) * tick
        else:
            price = math.floor(raw / tick + 1e-9) * tick
        price = round(price, self.rules.price_decimals)
        low = max(bar.low, stock.limit_down)
        high = min(bar.high, stock.limit_up)
        return min(max(price, low), high)

    def _execute(self, order: Order, qty: int, price: float, bar) -> TradeRecord | None:
        account = self.account
        stock = self.market.stocks[order.code]
        order.filled += qty
        order.amount_filled += price * qty

        avg = order.amount_filled / order.filled
        cumulative = calc_fees(self.rules, order.side, avg, order.filled)
        fees = FeeBreakdown(
            commission=cumulative.commission - order.fees_charged.commission,
            stamp_tax=cumulative.stamp_tax - order.fees_charged.stamp_tax,
            transfer_fee=cumulative.transfer_fee - order.fees_charged.transfer_fee,
        )
        order.fees_charged = cumulative

        realized = 0.0
        if order.side == "buy":
            release = order.frozen_per_share * qty
            account.release_cash(release)
            account.apply_buy(order.code, stock.name, qty, price, fees)
        else:
            realized = account.apply_sell(order.code, qty, price, fees)

        order.status = "已成交" if order.filled >= order.qty else "部分成交"
        record = TradeRecord(
            day=order.day, minute=order.minute, code=order.code, name=stock.name,
            side=order.side, qty=qty, price=price, amount=price * qty,
            fees=fees.total, realized=realized,
            note="融资买入" if (order.use_margin and order.side == "buy") else "",
        )
        account.record(record)
        self.log.append("%s 成交 %s %s %d 股 @ %.2f（费用 %.2f）%s" % (
            self._stamp(), record.side_text, stock.name, qty, price, fees.total,
            "剩余 %d 股待成交" % order.remaining if order.active else ""))
        return record


def minute_to_clock(minute: int, rules: MarketRules, total: int | None = None) -> str:
    """把分钟序号换算成交易时钟（A 股含午休）。"""
    total = total or rules.minutes_per_day
    minute = max(0, min(minute, total))
    if rules.key == "cn":
        if minute <= 120:
            h, m = 9 + (30 + minute) // 60, (30 + minute) % 60
        else:
            mm = minute - 120
            h, m = 13 + mm // 60, mm % 60
    else:
        h, m = 9 + (30 + minute) // 60, (30 + minute) % 60
    return "%02d:%02d" % (h, m)
