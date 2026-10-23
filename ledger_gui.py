# -*- coding: utf-8 -*-
"""112账务启动器（同时是打包 exe 的入口）。

直接运行：  py ledger_gui.py
自测：      py ledger_gui.py --self-test
演示数据：  py ledger_gui.py --demo
指定账套：  py ledger_gui.py --db D:\\账套\\2026.db
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ledger.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())