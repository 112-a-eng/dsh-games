# -*- coding: utf-8 -*-
"""行情模拟引擎。

真实感来源：
  * 三层收益分解：市场因子（牛/熊/震荡状态机）× 个股 beta + 个股特质波动（按 beta 校准，
    使个股总波动等于其历史年化波动），全部在对数收益空间做，避免波动率拖累造成虚假下跌；
  * 日内波动 U 型（开盘/尾盘放量）并对方差做归一化，保证日波动落在目标区间；
  * 隔夜跳空、涨跌停一字板/封板/开板、偶发停牌；
  * 新闻事件（宏观/行业/个股）以"带期限的效应"叠加，到期自动失效、可叠加但不会无界累积；
  * 指数由成分股流通市值加权合成，与个股走势自洽。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import date, timedelta

from .config import Difficulty, MarketRules, round_price

TRADING_DAYS = 244          # 一年交易日
MARKET_ANNUAL_VOL = 0.18    # 市场因子年化波动（沪深300 长期约 18%）
# 年化波动是"收盘到收盘"的口径：日内方差 + 隔夜跳空方差 = 目标方差，
# 因此日内部分要按 (1 - 跳空占比) 折算，避免总波动被系统性放大。
IDIO_INTRADAY_SCALE = 0.76   # 特质波动：跳空占 0.35²+0.55² = 0.425
MKT_INTRADAY_SCALE = 0.89    # 市场因子：跳空占 0.45² = 0.20


# ------------------------------------------------------------------ 标的定义
@dataclass(frozen=True)
class StockSpec:
    code: str
    name: str
    sector: str
    board: str
    price0: float
    float_cap: float        # 流通市值（亿元）
    beta: float
    annual_vol: float
    st: bool = False

    @property
    def shares(self) -> float:
        """流通股数（股）。"""
        return self.float_cap * 1e8 / self.price0

    @property
    def turnover(self) -> float:
        """日均换手率：市值越大换手越低（茅台约 0.2%、小盘题材股 1-3%）。"""
        raw = 0.0025 + 0.35 / math.sqrt(max(self.float_cap, 50.0))
        return min(0.030, max(0.0025, raw))

    @property
    def idio_vol(self) -> float:
        """特质波动：总波动² = beta²·市场波动² + 特质波动²。"""
        total2 = self.annual_vol ** 2
        market2 = (self.beta * MARKET_ANNUAL_VOL) ** 2
        return math.sqrt(max(total2 - market2, (0.45 * self.annual_vol) ** 2))


CN_UNIVERSE = [
    StockSpec("600519", "贵州茅台", "白酒", "主板", 1520.0, 21100, 0.85, 0.25),
    StockSpec("000858", "五粮液", "白酒", "主板", 128.5, 4990, 0.95, 0.30),
    StockSpec("601318", "中国平安", "保险", "主板", 46.2, 9500, 1.00, 0.28),
    StockSpec("600036", "招商银行", "银行", "主板", 34.8, 8000, 0.90, 0.22),
    StockSpec("000001", "平安银行", "银行", "主板", 11.3, 2200, 1.05, 0.26),
    StockSpec("300750", "宁德时代", "电池", "创业板", 182.0, 10000, 1.45, 0.45),
    StockSpec("002594", "比亚迪", "汽车", "主板", 243.0, 4200, 1.35, 0.42),
    StockSpec("601899", "紫金矿业", "有色", "主板", 15.6, 4000, 1.10, 0.35),
    StockSpec("688981", "中芯国际", "半导体", "科创板", 56.0, 4500, 1.50, 0.50),
    StockSpec("000725", "京东方A", "面板", "主板", 4.25, 1600, 1.25, 0.40),
    StockSpec("600030", "中信证券", "券商", "主板", 20.4, 3600, 1.40, 0.40),
    StockSpec("601012", "隆基绿能", "光伏", "主板", 18.9, 1400, 1.50, 0.52),
    StockSpec("600276", "恒瑞医药", "医药", "主板", 45.6, 2800, 0.90, 0.32),
    StockSpec("002415", "海康威视", "电子", "主板", 30.2, 3000, 1.10, 0.32),
    StockSpec("601668", "中国建筑", "建筑", "主板", 5.60, 2300, 0.85, 0.22),
    StockSpec("600900", "长江电力", "电力", "主板", 27.4, 6500, 0.60, 0.18),
    StockSpec("600887", "伊利股份", "食品饮料", "主板", 28.6, 1800, 0.85, 0.26),
    StockSpec("601088", "中国神华", "煤炭", "主板", 39.5, 7800, 0.75, 0.24),
    StockSpec("000651", "格力电器", "家电", "主板", 43.2, 2400, 0.95, 0.28),
    StockSpec("600585", "海螺水泥", "建材", "主板", 24.8, 1300, 0.95, 0.30),
    StockSpec("002230", "科大讯飞", "人工智能", "主板", 45.5, 1000, 1.45, 0.48),
    StockSpec("600893", "航发动力", "军工", "主板", 38.2, 900, 1.30, 0.42),
    StockSpec("601919", "中远海控", "航运", "主板", 14.2, 1900, 1.15, 0.40),
]

US_UNIVERSE = [
    StockSpec("AAPL", "Apple", "消费电子", "主板", 228.0, 34000, 1.05, 0.28),
    StockSpec("MSFT", "Microsoft", "软件", "主板", 425.0, 31000, 1.00, 0.26),
    StockSpec("NVDA", "NVIDIA", "半导体", "主板", 132.0, 32000, 1.70, 0.55),
    StockSpec("TSLA", "Tesla", "汽车", "主板", 248.0, 7900, 1.80, 0.60),
    StockSpec("AMZN", "Amazon", "电商", "主板", 186.0, 19000, 1.20, 0.32),
    StockSpec("GOOGL", "Alphabet", "互联网", "主板", 168.0, 20000, 1.10, 0.30),
    StockSpec("META", "Meta", "互联网", "主板", 575.0, 14500, 1.25, 0.36),
    StockSpec("JPM", "JPMorgan", "银行", "主板", 222.0, 6300, 1.00, 0.24),
    StockSpec("XOM", "ExxonMobil", "能源", "主板", 118.0, 5200, 0.85, 0.28),
    StockSpec("JNJ", "Johnson&Johnson", "医药", "主板", 158.0, 3800, 0.60, 0.18),
    StockSpec("AMD", "AMD", "半导体", "主板", 158.0, 2500, 1.75, 0.52),
    StockSpec("NFLX", "Netflix", "传媒", "主板", 690.0, 3000, 1.30, 0.38),
]

UNIVERSES = {"cn": CN_UNIVERSE, "us": US_UNIVERSE}
INDEX_NAMES = {"cn": ("000300", "沪深300", 3520.0), "us": ("SPX", "S&P 500", 5720.0)}

REGIMES = {
    # key: (年化漂移, 波动倍数, 中文名)
    "bull": (0.30, 1.00, "牛市"),
    "bear": (-0.26, 1.30, "熊市"),
    "range": (0.02, 0.85, "震荡市"),
}


def u_shape(minute: int, total: int) -> float:
    """日内成交量/波动的 U 型分布（开盘与尾盘活跃），均值约 1.14。"""
    return 1.0 + 0.95 * math.exp(-minute / 18.0) + 0.85 * math.exp(-(total - 1 - minute) / 18.0)


@dataclass
class Bar:
    minute: int
    open: float
    high: float
    low: float
    close: float
    volume: int              # 成交股数
    amount: float            # 成交额
    sealed: int = 0          # 1 封涨停 / -1 封跌停 / 0 正常

    @property
    def vwap(self) -> float:
        return self.amount / self.volume if self.volume else self.close


@dataclass
class DailyBar:
    day: int
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float


@dataclass
class News:
    day: int
    scope: str               # market / sector / stock
    target: str              # 行业名或股票代码
    title: str
    impact: float            # 累计影响（正=利好），按 days 摊到每日漂移
    days: int
    vol_mult: float = 1.0
    tone: int = 1            # 1 利好 / -1 利空 / 0 中性

    def text(self) -> str:
        tag = {1: "【利好】", -1: "【利空】", 0: "【中性】"}[self.tone]
        return tag + self.title


class Stock:
    """单只股票的实时状态与价格生成。"""

    def __init__(self, spec: StockSpec, rules: MarketRules):
        self.spec = spec
        self.rules = rules
        self.code = spec.code
        self.name = spec.name
        self.sector = spec.sector
        self.board = spec.board
        self.st = spec.st
        self.shares = spec.shares

        self.prev_close = spec.price0
        self.open = spec.price0
        self.high = spec.price0
        self.low = spec.price0
        self.last = spec.price0
        self.volume = 0
        self.amount = 0.0

        self.bars: list[Bar] = []
        self.daily: list[DailyBar] = []
        self.halted = False
        # 五档盘口：bids 从买一到买五（价格递减），asks 从卖一到卖五（价格递增）
        self.bids: list[tuple[float, int]] = []
        self.asks: list[tuple[float, int]] = []
        # 逐笔成交：(交易分钟, 秒, 价格, 股数, 主动方向 'B'/'S')
        self.ticks: list[tuple[int, int, float, int, str]] = []
        self.effects: list[list] = []     # [每日漂移, 剩余天数, 波动倍数]
        self.drift_bonus = 0.0
        self.vol_boost = 1.0
        self._set_limits()

    # -- 涨跌停 ------------------------------------------------------
    def _set_limits(self) -> None:
        limit = self.rules.limit_for(self.board, self.st)
        pc = self.prev_close
        if limit <= 0:
            self.limit_up = float("inf")
            self.limit_down = 0.0
        else:
            self.limit_up = round_price(self.rules, pc * (1 + limit))
            self.limit_down = round_price(self.rules, pc * (1 - limit))

    @property
    def change_pct(self) -> float:
        return (self.last / self.prev_close - 1.0) * 100 if self.prev_close else 0.0

    @property
    def avg_price(self) -> float:
        return self.amount / self.volume if self.volume else self.last

    def at_limit_up(self) -> bool:
        return self.last >= self.limit_up - 1e-9

    def at_limit_down(self) -> bool:
        return self.last <= self.limit_down + 1e-9

    def add_effect(self, per_day: float, days: int, vol_mult: float = 1.0) -> None:
        self.effects.append([per_day, days, vol_mult])

    def decay_effects(self) -> None:
        """每日开盘前推进消息期限，并重算当期漂移与波动放大。"""
        alive = []
        for eff in self.effects:
            eff[1] -= 1
            if eff[1] > 0:
                alive.append(eff)
        self.effects = alive
        self.drift_bonus = sum(e[0] for e in alive)
        self.vol_boost = max([e[2] for e in alive], default=1.0)


class Index:
    """由成分股流通市值加权合成的指数。"""

    def __init__(self, code: str, name: str, base: float):
        self.code, self.name, self.base = code, name, base
        self.prev_close = base
        self.open = base
        self.high = base
        self.low = base
        self.last = base
        self.bars: list[Bar] = []
        self.daily: list[DailyBar] = []

    @property
    def change_pct(self) -> float:
        return (self.last / self.prev_close - 1.0) * 100 if self.prev_close else 0.0


class Market:
    """整个市场的模拟器：只管行情，不碰账户。"""

    def __init__(self, rules: MarketRules, difficulty: Difficulty,
                 seed: int = 20240102, start_date: date | None = None):
        self.rules = rules
        self.diff = difficulty
        self.rng = random.Random(seed)
        self.total_minutes = rules.minutes_per_day
        # 让日内 U 型不影响总方差：按 sqrt(E[u²]) 归一化
        self.u_norm = math.sqrt(
            sum(u_shape(m, self.total_minutes) ** 2 for m in range(self.total_minutes))
            / self.total_minutes)

        specs = UNIVERSES.get(rules.key, CN_UNIVERSE)
        self.stocks = {s.code: Stock(s, rules) for s in specs}
        self.order_codes = [s.code for s in specs]
        code, name, base = INDEX_NAMES.get(rules.key, INDEX_NAMES["cn"])
        self.index = Index(code, name, base)

        self.date = (start_date or date(2024, 1, 2)) - timedelta(days=1)
        self.day = 0
        self.minute = 0
        self.regime = "range"
        self.news_today: list[News] = []
        self.news_log: list[News] = []

        self._weights = {c: s.spec.float_cap for c, s in self.stocks.items()}
        self._weight_sum = sum(self._weights.values())

    # ------------------------------------------------------------ 日循环
    def start_day(self) -> None:
        """进入下一个交易日：结算昨收、隔夜跳空开盘、生成当日新闻。"""
        nxt = self.date + timedelta(days=1)
        while nxt.weekday() >= 5:
            nxt += timedelta(days=1)
        self.date = nxt
        self.day += 1
        self.minute = 0
        self._advance_regime()

        drift_annual, vol_mult, _ = REGIMES[self.regime]
        vol_scale = vol_mult * self.diff.vol_mult
        day_drift = drift_annual / TRADING_DAYS
        mkt_daily_sigma = MARKET_ANNUAL_VOL / math.sqrt(TRADING_DAYS) * vol_scale
        mkt_gap = self.rng.gauss(day_drift * 0.5, 0.45 * mkt_daily_sigma)

        for stock in self.stocks.values():
            stock.decay_effects()
            stock.prev_close = stock.last
            stock._set_limits()
            stock.volume = 0
            stock.amount = 0.0
            stock.bars = []
            stock.ticks = []
            stock.bids = []
            stock.asks = []
            stock.halted = self.rng.random() < 0.002      # 千分之二概率停牌

            if stock.halted:
                stock.open = stock.high = stock.low = stock.last = stock.prev_close
                continue

            daily_idio = stock.spec.idio_vol / math.sqrt(TRADING_DAYS) * vol_scale
            sector_gap = self.rng.gauss(0, 0.35 * daily_idio)
            idio_gap = self.rng.gauss(0, 0.55 * daily_idio)
            gap_log = (stock.spec.beta * mkt_gap + sector_gap + idio_gap
                       + stock.drift_bonus * 0.45)
            price = stock.prev_close * math.exp(gap_log)
            price = min(max(price, stock.limit_down), stock.limit_up)
            stock.open = stock.high = stock.low = stock.last = round_price(self.rules, price)

        idx_gap = sum(self._weights[c] * (s.open / s.prev_close - 1)
                      for c, s in self.stocks.items()) / self._weight_sum
        self.index.prev_close = self.index.last
        self.index.last = self.index.open = self.index.high = self.index.low = \
            self.index.prev_close * (1 + idx_gap)
        self.index.bars = []

        self.news_today = self._make_news()
        self.news_log.extend(self.news_today)
        for news in self.news_today:
            self._apply_news(news)

    def end_day(self) -> None:
        """收盘：把分钟线聚合成日线。"""
        idx = self.index
        idx.daily.append(DailyBar(self.day, self.date, idx.open, idx.high, idx.low,
                                  idx.last, 0, 0.0))
        for stock in self.stocks.values():
            stock.daily.append(DailyBar(
                self.day, self.date, stock.open, stock.high, stock.low,
                stock.last, stock.volume, stock.amount))

    # ------------------------------------------------------------ 分钟循环
    def step(self) -> None:
        """推进一分钟。"""
        minute = self.minute
        drift_annual, vol_mult, _ = REGIMES[self.regime]
        vol_scale = vol_mult * self.diff.vol_mult
        u = u_shape(minute, self.total_minutes) / self.u_norm
        mkt_sigma = (MARKET_ANNUAL_VOL * vol_scale * MKT_INTRADAY_SCALE
                     / math.sqrt(TRADING_DAYS * self.total_minutes))
        mkt_log = (drift_annual / (TRADING_DAYS * self.total_minutes)
                   - 0.5 * (mkt_sigma * u) ** 2 + mkt_sigma * u * self.rng.gauss(0, 1))

        for stock in self.stocks.values():
            stock.bars.append(self._step_stock(stock, minute, mkt_log, vol_scale, u))

        # 指数：流通市值加权（权重固定，等价于价格加权平均）
        idx_r = sum(self._weights[c] * (s.bars[-1].close / s.bars[-1].open - 1)
                    for c, s in self.stocks.items()) / self._weight_sum
        self._step_index(idx_r, minute)
        self.minute += 1

    def _step_stock(self, stock: Stock, minute: int, mkt_log: float,
                    vol_scale: float, u: float) -> Bar:
        if stock.halted:
            px = stock.last
            return Bar(minute, px, px, px, px, 0, 0.0)

        sigma = (stock.spec.idio_vol * vol_scale * stock.vol_boost * IDIO_INTRADAY_SCALE
                 / math.sqrt(TRADING_DAYS * self.total_minutes)) * u
        drift = stock.drift_bonus / self.total_minutes
        log_r = drift - 0.5 * sigma ** 2 + stock.spec.beta * mkt_log \
            + sigma * self.rng.gauss(0, 1)

        open_px = stock.last
        raw = open_px * math.exp(log_r)
        sealed = 0

        if raw >= stock.limit_up:                       # 涨停
            if self.rng.random() < 0.78:
                close_px, sealed = stock.limit_up, 1
            else:                                       # 开板回落
                close_px = max(stock.limit_down,
                               stock.limit_up * (1 - abs(self.rng.gauss(0, 0.004))))
        elif raw <= stock.limit_down:                   # 跌停
            if self.rng.random() < 0.78:
                close_px, sealed = stock.limit_down, -1
            else:
                close_px = min(stock.limit_up,
                               stock.limit_down * (1 + abs(self.rng.gauss(0, 0.004))))
        else:
            close_px = raw
        close_px = min(max(round_price(self.rules, close_px), stock.limit_down),
                       stock.limit_up)

        # 分时高低点：按波动幅度外扩
        wick = abs(self.rng.gauss(0, 1)) * sigma * 0.7
        high = round_price(self.rules, min(max(open_px, close_px) * (1 + wick), stock.limit_up))
        low = round_price(self.rules, max(min(open_px, close_px) * (1 - wick), stock.limit_down))
        high = max(high, open_px, close_px)
        low = min(low, open_px, close_px)

        # 成交量：U 型 × 涨跌幅放大 × 对数正态噪声，封板时缩量
        base = stock.shares * stock.spec.turnover / self.total_minutes
        shock = 0.45 + 2.6 * min(3.0, abs(log_r) / max(sigma, 1e-9))
        noise = math.exp(self.rng.gauss(0, 0.35))
        seal_factor = 0.30 if sealed else 1.0
        volume = max(0, int(base * u_shape(minute, self.total_minutes) * shock
                            * noise * seal_factor))
        amount = volume * (open_px + close_px + high + low) / 4.0

        stock.high = max(stock.high, high)
        stock.low = min(stock.low, low)
        stock.last = close_px
        stock.volume += volume
        stock.amount += amount
        self._make_book(stock, open_px, close_px, high, low, volume, sealed)
        self._make_ticks(stock, minute, high, low, close_px, volume, base)
        return Bar(minute, open_px, high, low, close_px, volume, amount, sealed)

    def _make_book(self, stock: Stock, open_px: float, close_px: float,
                   high: float, low: float, volume: int, sealed: int) -> None:
        """生成五档盘口。挂单量与该分钟成交量挂钩，封板时对应一侧挂空。"""
        tick = self.rules.tick
        base = max(200.0, volume / 10.0)
        # 低价股/小盘股价差略宽
        spread = 1 if stock.spec.float_cap > 2000 else 2

        def level(i: int) -> int:
            raw = base * math.exp(self.rng.gauss(0, 0.55)) * (1.0 + 0.28 * i)
            lots = max(1, int(raw / 100.0))
            return lots * 100

        bids: list[tuple[float, int]] = []
        asks: list[tuple[float, int]] = []
        if sealed == 1:
            # 一字/封涨停：卖盘全空，买单堆在涨停价上排队
            asks = []
            bids = [(stock.limit_up, level(0) * (5 + int(6 * self.rng.random())))]
            for i in range(1, 5):
                px = round_price(self.rules, stock.limit_up - i * tick)
                if px >= stock.limit_down:
                    bids.append((px, level(i)))
        elif sealed == -1:
            bids = []
            asks = [(stock.limit_down, level(0) * (5 + int(6 * self.rng.random())))]
            for i in range(1, 5):
                px = round_price(self.rules, stock.limit_down + i * tick)
                if px <= stock.limit_up:
                    asks.append((px, level(i)))
        else:
            # 最新价要么贴在卖一（收阳、主动买多），要么贴在买一，价差为 1 个价差单位
            anchor = close_px
            step = spread * tick
            if close_px >= open_px:
                ask0, bid0 = anchor, anchor - step
            else:
                ask0, bid0 = anchor + step, anchor
            for i in range(5):
                # 用整数倍最小价位，避免取整后出现重复档位（小数倍在 0.01 价位上会撞车）
                bp = round_price(self.rules, bid0 - i * step)
                ap = round_price(self.rules, ask0 + i * step)
                if bp >= stock.limit_down:
                    bids.append((bp, level(i)))
                if ap <= stock.limit_up:
                    asks.append((ap, level(i)))
        stock.bids = bids[:5]
        stock.asks = asks[:5]

    def _make_ticks(self, stock: Stock, minute: int, high: float, low: float,
                    close_px: float, volume: int, base_volume: float) -> None:
        """生成这一分钟的逐笔成交明细（价格落在该分钟 K 线区间内）。"""
        if volume <= 0 or high <= 0:
            stock.ticks.append((minute, 0, close_px, 0, "B"))
            return
        count = max(2, min(9, int(1 + volume / max(1.0, base_volume) * 2.2)))
        prev = None
        span = max(high - low, self.rules.tick)
        for k in range(count):
            # 越靠近收盘的成交越靠后，价格在区间内随机
            price = round_price(self.rules, low + span * self.rng.random())
            price = min(max(price, low), high)
            lots = max(1, int(base_volume / count / 100.0
                              * math.exp(self.rng.gauss(0, 0.6))))
            shares = lots * 100
            reference = prev if prev is not None else close_px
            side = "B" if price >= reference else "S"
            second = min(59, int((k + 1) * 60 / count - 1)) if count else 0
            stock.ticks.append((minute, second, price, shares, side))
            prev = price
        if len(stock.ticks) > 240:            # 只留最近一段，避免长时间挂机涨内存
            del stock.ticks[:-240]

    def _step_index(self, r: float, minute: int) -> None:
        idx = self.index
        open_px = idx.last
        close_px = open_px * (1 + r)
        wick = abs(r) * 0.6
        idx.high = max(idx.high, close_px * (1 + wick))
        idx.low = min(idx.low, close_px * (1 - wick))
        idx.last = close_px
        idx.bars.append(Bar(minute, open_px, max(open_px, close_px),
                            min(open_px, close_px), close_px, 0, 0.0))

    # ------------------------------------------------------------ 市场状态
    def _advance_regime(self) -> None:
        if self.rng.random() > 0.972:                   # 日均 2.8% 概率切换状态
            self.regime = self.rng.choices(
                ["bull", "bear", "range"], weights=[0.34, 0.28, 0.38])[0]

    @property
    def regime_name(self) -> str:
        return REGIMES[self.regime][2]

    # ------------------------------------------------------------ 新闻
    def _make_news(self) -> list[News]:
        lo, hi = self.diff.news_per_day
        count = self.rng.randint(lo, hi)
        news = []
        codes = list(self.stocks)
        sectors = sorted({s.sector for s in self.stocks.values()})
        for _ in range(count):
            roll = self.rng.random()
            if roll < 0.18:
                news.append(self._macro_news())
            elif roll < 0.52:
                news.append(self._sector_news(self.rng.choice(sectors)))
            else:
                news.append(self._stock_news(self.rng.choice(codes)))
        return news

    def _macro_news(self) -> News:
        good = [
            ("央行宣布降准0.25个百分点，释放长期资金约5000亿元", 0.014),
            ("国常会部署稳增长措施，加大基础设施投资力度", 0.011),
            ("制造业PMI回升至荣枯线上方，经济复苏预期升温", 0.010),
            ("北向资金单日净买入超80亿元，外资持续加仓", 0.009),
        ]
        bad = [
            ("美联储释放鹰派信号，外围市场大幅调整", -0.014),
            ("社融数据不及预期，市场担忧需求疲弱", -0.011),
            ("地缘局势紧张，国际油价与避险资产同步走高", -0.009),
            ("监管收紧量化交易，两市成交明显萎缩", -0.010),
        ]
        title, impact = self.rng.choice(good if self.rng.random() < 0.55 else bad)
        return News(self.day, "market", "", title, impact, self.rng.randint(2, 5),
                    1.10, 1 if impact > 0 else -1)

    def _sector_news(self, sector: str) -> News:
        good = [
            ("工信部发布%s产业支持政策，鼓励技术攻关" % sector, 0.030),
            ("%s板块获机构密集调研，龙头公司订单饱满" % sector, 0.024),
            ("%s产品价格环比上涨，行业景气度回升" % sector, 0.028),
            ("多地出台%s消费补贴细则，需求端有望放量" % sector, 0.022),
        ]
        bad = [
            ("%s行业产能过剩担忧升温，产品价格持续走低" % sector, -0.028),
            ("监管约谈%s重点企业，要求规范经营" % sector, -0.022),
            ("%s板块遭北向资金连续净卖出" % sector, -0.020),
            ("%s原材料成本上行，行业毛利率承压" % sector, -0.021),
        ]
        title, impact = self.rng.choice(good if self.rng.random() < 0.52 else bad)
        return News(self.day, "sector", sector, title, impact, self.rng.randint(3, 8),
                    1.05, 1 if impact > 0 else -1)

    def _stock_news(self, code: str) -> News:
        name = self.stocks[code].name
        good = [
            ("%s：中标重大项目，合同金额约%d亿元" % (name, self.rng.randint(8, 60)), 0.038),
            ("%s：前三季度净利润预增%d%%" % (name, self.rng.randint(20, 120)), 0.048),
            ("%s：拟以%d亿元回购股份并注销" % (name, self.rng.randint(3, 30)), 0.032),
            ("%s：控股股东计划增持不低于%d亿元" % (name, self.rng.randint(1, 10)), 0.028),
            ("%s：核心产品获得注册批件，打开新增长空间" % name, 0.035),
        ]
        bad = [
            ("%s：股东计划减持不超过%d%%股份" % (name, self.rng.randint(1, 4)), -0.038),
            ("%s：收到交易所问询函，需说明业绩波动原因" % name, -0.026),
            ("%s：业绩预告下修，全年增速低于预期" % name, -0.048),
            ("%s：董事长因个人原因辞职" % name, -0.022),
            ("%s：主要产品被纳入集采，价格降幅超预期" % name, -0.042),
        ]
        title, impact = self.rng.choice(good if self.rng.random() < 0.5 else bad)
        return News(self.day, "stock", code, title, impact, self.rng.randint(3, 8),
                    1.15, 1 if impact > 0 else -1)

    def _apply_news(self, news: News) -> None:
        per_day = news.impact / max(1, news.days)
        if news.scope == "market":
            for stock in self.stocks.values():
                stock.add_effect(per_day, news.days, news.vol_mult)
        elif news.scope == "sector":
            for stock in self.stocks.values():
                if stock.sector == news.target:
                    stock.add_effect(per_day, news.days, news.vol_mult)
        else:
            stock = self.stocks.get(news.target)
            if stock:
                stock.add_effect(per_day, news.days, news.vol_mult)
