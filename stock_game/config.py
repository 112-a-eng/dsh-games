# -*- coding: utf-8 -*-
"""市场规则、费用模型与难度预设。

这里的数字都按真实市场设置：
  * A 股：T+1、100 股一手、主板 ±10%、创业板/科创板 ±20%、ST ±5%；
          佣金万 2.5（最低 5 元，双边）、印花税千 0.5（仅卖出）、过户费 0.001%（双边）。
  * 美股：T+0、1 股起、无涨跌停、零佣金（现代主流券商）。
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MarketRules:
    key: str
    name: str
    currency: str = "元"
    t_plus_1: bool = True                 # 当日买入次日才可卖
    lot_size: int = 100                   # 最小交易单位（股）
    limit_main: float = 0.10              # 主板涨跌幅
    limit_gem: float = 0.20               # 创业板/科创板涨跌幅
    limit_st: float = 0.05                # ST 股涨跌幅
    commission_rate: float = 0.00025      # 佣金费率（双边）
    commission_min: float = 5.0           # 单笔最低佣金
    stamp_tax_sell: float = 0.0005        # 印花税（仅卖出）
    transfer_fee_rate: float = 0.00001    # 过户费（双边）
    slippage_bps: float = 1.5             # 基础滑点（万分之）
    impact_coeff: float = 1.0             # 冲击成本系数
    participation: float = 0.10           # 单分钟最多成交该分钟成交量的比例
    tick: float = 0.01                    # 最小价格变动
    margin_enabled: bool = True           # 是否允许融资
    margin_annual_rate: float = 0.065     # 融资年利率
    margin_ratio: float = 1.00            # 融资保证金比例（1.0 = 最多 1 倍杠杆）
    force_close_ratio: float = 1.10       # 维持担保比例低于此值强平
    warn_ratio: float = 1.30              # 维持担保比例预警线
    minutes_per_day: int = 240            # 4 小时交易时间（分钟）
    price_decimals: int = 2

    def limit_for(self, board: str, st: bool = False) -> float:
        """按板块返回涨跌幅限制；美股为 0 表示不限制。"""
        if self.limit_main <= 0:
            return 0.0
        if st:
            return self.limit_st
        if board in ("创业板", "科创板"):
            return self.limit_gem
        return self.limit_main


A_SHARE = MarketRules(
    key="cn", name="A股", currency="元",
    t_plus_1=True, lot_size=100,
    limit_main=0.10, limit_gem=0.20, limit_st=0.05,
    commission_rate=0.00025, commission_min=5.0,
    stamp_tax_sell=0.0005, transfer_fee_rate=0.00001,
    slippage_bps=1.5, impact_coeff=1.0, participation=0.10,
    margin_enabled=True, margin_annual_rate=0.065,
    margin_ratio=1.00, force_close_ratio=1.10, warn_ratio=1.30,
)

US_STOCK = MarketRules(
    key="us", name="美股", currency="$",
    t_plus_1=False, lot_size=1,
    limit_main=0.0, limit_gem=0.0, limit_st=0.0,
    commission_rate=0.0, commission_min=0.0,
    stamp_tax_sell=0.0, transfer_fee_rate=0.0,
    slippage_bps=1.0, impact_coeff=0.8, participation=0.05,
    margin_enabled=True, margin_annual_rate=0.055,
    margin_ratio=1.00, force_close_ratio=1.25, warn_ratio=1.40,
    minutes_per_day=390, price_decimals=2,
)

MARKETS = {m.key: m for m in (A_SHARE, US_STOCK)}


@dataclass(frozen=True)
class Difficulty:
    key: str
    name: str
    vol_mult: float            # 波动率倍数
    news_per_day: tuple        # 每日新闻条数范围
    description: str


DIFFICULTIES = [
    Difficulty("easy", "轻松", 0.75, (0, 1), "波动小、消息少，适合熟悉操作"),
    Difficulty("normal", "标准", 1.00, (0, 2), "接近真实市场的波动与消息密度"),
    Difficulty("hard", "硬核", 1.35, (1, 3), "高波动 + 高频消息，容易爆仓"),
]
DIFFICULTY_BY_KEY = {d.key: d for d in DIFFICULTIES}


@dataclass
class FeeBreakdown:
    """一笔成交的费用明细。"""
    commission: float = 0.0
    stamp_tax: float = 0.0
    transfer_fee: float = 0.0

    @property
    def total(self) -> float:
        return self.commission + self.stamp_tax + self.transfer_fee

    def as_dict(self) -> dict:
        return {"佣金": round(self.commission, 2),
                "印花税": round(self.stamp_tax, 2),
                "过户费": round(self.transfer_fee, 2),
                "合计": round(self.total, 2)}


def calc_fees(rules: MarketRules, side: str, price: float, qty: int) -> FeeBreakdown:
    """按成交价与数量计算交易费用。side 为 'buy' 或 'sell'。"""
    amount = price * qty
    commission = amount * rules.commission_rate
    if commission > 0:
        commission = max(commission, rules.commission_min)
    fees = FeeBreakdown(
        commission=commission,
        stamp_tax=amount * rules.stamp_tax_sell if side == "sell" else 0.0,
        transfer_fee=amount * rules.transfer_fee_rate,
    )
    return fees


def round_price(rules: MarketRules, price: float) -> float:
    """按最小变动价位取整（A 股 0.01 元）。"""
    tick = rules.tick
    return round(round(price / tick) * tick, rules.price_decimals)
