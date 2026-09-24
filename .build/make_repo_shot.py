# -*- coding: utf-8 -*-
"""生成仓库用的股票游戏截图（docs/screenshot-stock.png）。"""
import os
import sys
import time
import tkinter as tk

sys.path.insert(0, r"D:\DSH")
sys.path.insert(0, r"D:\DSH\.build")
import shot_stock as S                                    # noqa: E402
from stock_game.engine import Game                        # noqa: E402
from stock_game.ui import StockGameUI                     # noqa: E402

game = Game(seed=20240918, max_days=20, initial_cash=1_000_000)
game.start()
for _ in range(2):                                        # 跑两天，攒出日线与盘口
    for _ in range(game.market.total_minutes):
        game.tick()
    game.advance_day()
for code, qty in (("600519", 100), ("000858", 500), ("300750", 300),
                  ("002230", 200), ("601088", 400)):
    stock = game.market.stocks[code]
    game.submit(code, "buy", qty, "limit", round(stock.last * 1.02, 2))
for _ in range(60):                                        # 让行情走动一段
    game.tick()

root = tk.Tk()
ui = StockGameUI(root, game, pace_seconds=120)
root.geometry("+20+20")
for _ in range(30):
    root.update()
    time.sleep(0.02)

hwnd = S.user32.FindWindowW(None, "股票模拟交易 · Stock Trading Simulator")
if not hwnd:
    print("找不到窗口")
    sys.exit(1)
w, h, rows = S.capture(hwnd)
os.makedirs(r"D:\DSH\docs", exist_ok=True)
S.save_png(r"D:\DSH\docs\screenshot-stock.png", rows)
print("股票游戏截图完成 %dx%d" % (w, h))
root.destroy()
