# -*- coding: utf-8 -*-
"""股票模拟交易游戏启动器（同时是打包 exe 的入口）。

直接运行：  py stock_game_gui.py
自测：      py stock_game_gui.py --self-test
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stock_game.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
