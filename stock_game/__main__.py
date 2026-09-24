# -*- coding: utf-8 -*-
"""入口：python -m stock_game [选项]

选项：
  --self-test            运行无界面自测（交易规则/会计/长跑）
  --market cn|us         市场（默认 cn）
  --difficulty easy|normal|hard
  --cash 1000000         初始资金
  --days 60              交易日数（默认 60 个交易日）
  --seed 12345           随机种子（相同种子可复现同一段行情）
  --pace 300             节奏：一个交易日走多少现实秒（300=5分钟/日，60=1分钟/日，10=10秒/日）
  --no-dialog            跳过开局设置，直接用命令行参数开局
"""
from __future__ import annotations

import sys


USAGE = __doc__


def parse_args(argv: list[str]) -> dict:
    # 节奏默认值以界面模块的定义为准（延迟到函数内导入，这样 --self-test 不必加载 tkinter）
    from .ui import DEFAULT_DAY_SECONDS

    opts = {"market_key": "cn", "difficulty_key": "normal",
            "initial_cash": 1_000_000.0, "max_days": 60, "seed": None,
            "pace_seconds": DEFAULT_DAY_SECONDS}
    skip_dialog = False
    i = 0
    while i < len(argv):
        arg = argv[i]
        nxt = argv[i + 1] if i + 1 < len(argv) else None
        if arg == "--market" and nxt:
            opts["market_key"] = nxt
            i += 2
        elif arg == "--difficulty" and nxt:
            opts["difficulty_key"] = nxt
            i += 2
        elif arg == "--cash" and nxt:
            opts["initial_cash"] = float(nxt)
            i += 2
        elif arg == "--days" and nxt:
            opts["max_days"] = int(nxt)
            i += 2
        elif arg == "--seed" and nxt:
            opts["seed"] = int(nxt)
            i += 2
        elif arg == "--pace" and nxt:
            opts["pace_seconds"] = int(float(nxt))
            i += 2
        elif arg == "--no-dialog":
            skip_dialog = True
            i += 1
        else:
            i += 1
    return opts, skip_dialog


def _apply_window_icon(root) -> None:
    """给窗口设置图标（源码运行取项目根目录，打包后取解包目录）。"""
    import os

    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "stock_icon.png")
    try:
        image = tk.PhotoImage(file=path)
        root.iconphoto(True, image)
        root._icon_ref = image          # 保持引用，避免被回收
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--help" in argv or "-h" in argv:
        print(USAGE)
        return 0
    if "--self-test" in argv:
        from .selftest import run_all
        return run_all()

    import tkinter as tk

    from .engine import Game
    from .ui import StartDialog, StockGameUI

    opts, skip_dialog = parse_args(argv)

    root = tk.Tk()
    root.withdraw()
    _apply_window_icon(root)

    if not skip_dialog:
        dialog = StartDialog(root)
        root.wait_window(dialog.top)
        if not dialog.result:
            root.destroy()
            return 0
        opts = dict(opts)
        opts.update(dialog.result)

    speed = int(opts.pop("pace_seconds", 300))      # 节奏是界面状态，不传给 Game
    game = Game(**opts)
    game.start()
    root.deiconify()
    StockGameUI(root, game, pace_seconds=speed)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
