# -*- coding: utf-8 -*-
"""会计基础设置：科目类别、余额方向、以及一套标准会计科目表。

科目表参照财政部《企业会计准则——应用指南》的常用科目精简而成，
覆盖一般企业日常业务所需的资产 / 负债 / 所有者权益 / 成本 / 损益五类科目。
用户可以在此基础上自由增加明细科目（例如在「银行存款」下按开户行细分）。
"""
from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------- 科目类别
ASSET = "资产"
LIABILITY = "负债"
EQUITY = "所有者权益"
COST = "成本"
PROFIT = "损益"
CATEGORIES = (ASSET, LIABILITY, EQUITY, COST, PROFIT)

# ---------------------------------------------------------------- 余额方向
DEBIT = "借"
CREDIT = "贷"

# ---------------------------------------------------------------- 报表分组
G_CURRENT_ASSET = "流动资产"
G_NONCURRENT_ASSET = "非流动资产"
G_CURRENT_LIAB = "流动负债"
G_NONCURRENT_LIAB = "非流动负债"
G_EQUITY = "所有者权益"
G_COST = "成本"
G_REVENUE = "营业收入"
G_OP_COST = "营业成本"
G_PERIOD_EXP = "期间费用"
G_OTHER = "其他损益"
G_TAX = "所得税费用"

# 类别 -> 默认余额方向（收入类会在科目定义里显式写成「贷」）
DEFAULT_DIRECTION = {
    ASSET: DEBIT,
    LIABILITY: CREDIT,
    EQUITY: CREDIT,
    COST: DEBIT,
    PROFIT: DEBIT,
}


@dataclass(frozen=True)
class AccountDef:
    code: str
    name: str
    category: str
    direction: str
    group: str
    is_leaf: bool = True
    custom: bool = False

    @property
    def full_name(self) -> str:
        return "%s %s" % (self.code, self.name)


def _a(code, name, category, group, direction=None, leaf=True):
    return AccountDef(code, name, category,
                      direction or DEFAULT_DIRECTION[category], group, leaf)


# 标准科目表（is_leaf=False 的只是分类标题，不能再挂凭证）
STANDARD_ACCOUNTS = [
    # ---------------------------------------------------------- 一、资产类
    _a("1001", "库存现金", ASSET, G_CURRENT_ASSET),
    _a("1002", "银行存款", ASSET, G_CURRENT_ASSET),
    _a("1012", "其他货币资金", ASSET, G_CURRENT_ASSET),
    _a("1101", "交易性金融资产", ASSET, G_CURRENT_ASSET),
    _a("1121", "应收票据", ASSET, G_CURRENT_ASSET),
    _a("1122", "应收账款", ASSET, G_CURRENT_ASSET),
    _a("1123", "预付账款", ASSET, G_CURRENT_ASSET),
    _a("1131", "应收股利", ASSET, G_CURRENT_ASSET),
    _a("1132", "应收利息", ASSET, G_CURRENT_ASSET),
    _a("1221", "其他应收款", ASSET, G_CURRENT_ASSET),
    _a("1231", "坏账准备", ASSET, G_CURRENT_ASSET, CREDIT),
    _a("1401", "材料采购", ASSET, G_CURRENT_ASSET),
    _a("1402", "在途物资", ASSET, G_CURRENT_ASSET),
    _a("1403", "原材料", ASSET, G_CURRENT_ASSET),
    _a("1405", "库存商品", ASSET, G_CURRENT_ASSET),
    _a("1408", "委托加工物资", ASSET, G_CURRENT_ASSET),
    _a("1471", "存货跌价准备", ASSET, G_CURRENT_ASSET, CREDIT),
    _a("1601", "固定资产", ASSET, G_NONCURRENT_ASSET),
    _a("1602", "累计折旧", ASSET, G_NONCURRENT_ASSET, CREDIT),
    _a("1603", "固定资产减值准备", ASSET, G_NONCURRENT_ASSET, CREDIT),
    _a("1701", "无形资产", ASSET, G_NONCURRENT_ASSET),
    _a("1702", "累计摊销", ASSET, G_NONCURRENT_ASSET, CREDIT),
    _a("1801", "长期待摊费用", ASSET, G_NONCURRENT_ASSET),
    _a("1811", "递延所得税资产", ASSET, G_NONCURRENT_ASSET),

    # ---------------------------------------------------------- 二、负债类
    _a("2001", "短期借款", LIABILITY, G_CURRENT_LIAB),
    _a("2201", "应付票据", LIABILITY, G_CURRENT_LIAB),
    _a("2202", "应付账款", LIABILITY, G_CURRENT_LIAB),
    _a("2203", "预收账款", LIABILITY, G_CURRENT_LIAB),
    _a("2211", "应付职工薪酬", LIABILITY, G_CURRENT_LIAB),
    _a("2221", "应交税费", LIABILITY, G_CURRENT_LIAB),
    _a("2231", "应付利息", LIABILITY, G_CURRENT_LIAB),
    _a("2232", "应付股利", LIABILITY, G_CURRENT_LIAB),
    _a("2241", "其他应付款", LIABILITY, G_CURRENT_LIAB),
    _a("2501", "长期借款", LIABILITY, G_NONCURRENT_LIAB),
    _a("2801", "预计负债", LIABILITY, G_NONCURRENT_LIAB),
    _a("2901", "递延所得税负债", LIABILITY, G_NONCURRENT_LIAB),

    # ---------------------------------------------------------- 三、所有者权益类
    _a("4001", "实收资本", EQUITY, G_EQUITY),
    _a("4002", "资本公积", EQUITY, G_EQUITY),
    _a("4101", "盈余公积", EQUITY, G_EQUITY),
    _a("4103", "本年利润", EQUITY, G_EQUITY),
    _a("4104", "利润分配", EQUITY, G_EQUITY),

    # ---------------------------------------------------------- 四、成本类
    _a("5001", "生产成本", COST, G_COST),
    _a("5101", "制造费用", COST, G_COST),
    _a("5201", "劳务成本", COST, G_COST),

    # ---------------------------------------------------------- 五、损益类
    _a("6001", "主营业务收入", PROFIT, G_REVENUE, CREDIT),
    _a("6051", "其他业务收入", PROFIT, G_REVENUE, CREDIT),
    _a("6111", "投资收益", PROFIT, G_OTHER, CREDIT),
    _a("6301", "营业外收入", PROFIT, G_OTHER, CREDIT),
    _a("6401", "主营业务成本", PROFIT, G_OP_COST),
    _a("6402", "其他业务成本", PROFIT, G_OP_COST),
    _a("6403", "税金及附加", PROFIT, G_PERIOD_EXP),
    _a("6601", "销售费用", PROFIT, G_PERIOD_EXP),
    _a("6602", "管理费用", PROFIT, G_PERIOD_EXP),
    _a("6603", "财务费用", PROFIT, G_PERIOD_EXP),
    _a("6701", "资产减值损失", PROFIT, G_OTHER),
    _a("6711", "营业外支出", PROFIT, G_OTHER),
    _a("6801", "所得税费用", PROFIT, G_TAX),
]

STANDARD_BY_CODE = {a.code: a for a in STANDARD_ACCOUNTS}

# 结转损益时用到的两个科目
ACCOUNT_INCOME_SUMMARY = "4103"      # 本年利润
ACCOUNT_PROFIT_DISTRIBUTION = "4104"  # 利润分配
ACCOUNT_CASH = "1001"                 # 库存现金

# 增值税相关（常用于应交税费明细）
DEFAULT_TAX_RATE = 0.13

APP_NAME = "112账务"
APP_VERSION = "1.0.0"
SCHEMA_VERSION = 1

# 会计期间：每月一个期间
MONTHS = list(range(1, 13))


def direction_of(category: str, override: str | None = None) -> str:
    return override or DEFAULT_DIRECTION.get(category, DEBIT)


def is_contra(acc: AccountDef) -> bool:
    """备抵科目：资产类但余额方向为贷（如累计折旧、坏账准备）。"""
    return acc.category == ASSET and acc.direction == CREDIT