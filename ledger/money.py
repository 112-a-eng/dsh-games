# -*- coding: utf-8 -*-
"""金额处理。

财务软件最忌讳浮点误差，所以内部一律用「分」的整数（int）保存和计算，
只有在解析用户输入和格式化显示时才出现十进制小数。
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_CENT = Decimal("1")
_STRIP = ("¥", "￥", "元", ",", "，", " ", "\u00a0", "\t")


def parse_amount(value) -> int:
    """把用户输入的金额解析成整数「分」。

    接受 int / float / Decimal / str（可含千分位、货币符号、正负号、括号负数）。
    空值视为 0；无法解析时抛 ValueError。
    """
    if value is None:
        return 0
    if isinstance(value, bool):
        raise ValueError("金额格式不正确：%r" % (value,))
    if isinstance(value, int):
        return value * 100
    if isinstance(value, Decimal):
        dec = value
    else:
        text = str(value).strip()
        if not text:
            return 0
        negative = False
        if text.startswith("(") and text.endswith(")"):
            negative = True
            text = text[1:-1]
        for ch in _STRIP:
            text = text.replace(ch, "")
        if text in ("", "+", "-"):
            return 0
        if text.startswith("-"):
            negative = True
            text = text[1:]
        elif text.startswith("+"):
            text = text[1:]
        if not text or text.count(".") > 1 or not text.replace(".", "").isdigit():
            raise ValueError("金额格式不正确：%r" % (value,))
        try:
            dec = Decimal(text)
        except InvalidOperation:
            raise ValueError("金额格式不正确：%r" % (value,)) from None
        if negative:
            dec = -dec
    cents = (dec * 100).quantize(_CENT, rounding=ROUND_HALF_UP)
    return int(cents)


def fmt_cents(cents: int, thousands: bool = True, blank_zero: bool = False) -> str:
    """把整数「分」格式化成人看的金额字符串，如 -1234567 -> '-12,345.67'。"""
    cents = int(cents)
    if cents == 0 and blank_zero:
        return ""
    sign = "-" if cents < 0 else ""
    yuan, fen = divmod(abs(cents), 100)
    whole = "{:,}".format(yuan) if thousands else str(yuan)
    return "%s%s.%02d" % (sign, whole, fen)


def fmt_cents_plain(cents: int, blank_zero: bool = False) -> str:
    """不带千分位，便于导出 CSV。"""
    return fmt_cents(cents, thousands=False, blank_zero=blank_zero)


def cents_to_decimal(cents: int) -> Decimal:
    return (Decimal(int(cents)) / 100).quantize(Decimal("0.01"))