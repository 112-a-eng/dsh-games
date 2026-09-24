# -*- coding: utf-8 -*-
"""给股票游戏各标签页截图（验证五档盘口、逐笔成交、账户页渲染）。"""
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
for _ in range(2):                                        # 先跑两天攒出日线与盘口
    for _ in range(game.market.total_minutes):
        game.tick()
    game.advance_day()
for code, qty in (("600519", 100), ("000858", 500), ("300750", 300),
                  ("002230", 200), ("601088", 400)):
    stock = game.market.stocks[code]
    game.submit(code, "buy", qty, "limit", round(stock.last * 1.02, 2))
for _ in range(40):
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

TABS = {"持仓": 0, "委托": 1, "成交": 2, "逐笔": 3, "账户": 4, "日志": 5}
for name, index in TABS.items():
    ui.notebook.select(index)
    ui.select_stock("600519")
    for _ in range(20):
        root.update()
    w, h, rows = S.capture(hwnd)
    S.save_png(r"D:\DSH\.build\ui_tab_%s.png" % name, rows)
print("各标签页截图完成")
root.destroy()
