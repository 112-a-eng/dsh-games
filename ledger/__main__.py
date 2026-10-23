# -*- coding: utf-8 -*-
"""入口：python -m ledger [选项]

选项：
  --self-test            运行无界面自测（金额/凭证/报表/结转/长跑）
  --db PATH              指定账套文件（默认文档目录下的 112账务\账套.db）
  --company NAME         新建账套时的公司名称
  --demo                 载入一套演示数据后打开界面
  --tab N                启动后直接切到第 N 个标签页（0 起，便于截图）
  --no-dialog            跳过界面里的示例数据提示
"""
from __future__ import annotations

import os
import sys

USAGE = __doc__


def default_db_path() -> str:
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    base = os.path.join(docs, "112账务")
    # 兼容改名前的旧账套：若 112账务 还没建过，但旧的「凭安账务」目录里有账套，就沿用旧位置。
    legacy = os.path.join(docs, "凭安账务")
    if not os.path.isdir(base) and os.path.isfile(os.path.join(legacy, "账套.db")):
        base = legacy
    return os.path.join(base, "账套.db")


def parse_args(argv: list) -> tuple:
    opts = {"db": None, "company": None, "demo": False, "no_dialog": False, "tab": None}
    i = 0
    while i < len(argv):
        arg = argv[i]
        nxt = argv[i + 1] if i + 1 < len(argv) else None
        if arg == "--db" and nxt:
            opts["db"] = nxt
            i += 2
        elif arg == "--company" and nxt:
            opts["company"] = nxt
            i += 2
        elif arg == "--tab" and nxt:
            opts["tab"] = int(nxt)
            i += 2
        elif arg == "--demo":
            opts["demo"] = True
            i += 1
        elif arg == "--no-dialog":
            opts["no_dialog"] = True
            i += 1
        else:
            i += 1
    return opts


def main(argv: list | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(USAGE)
        return 0
    if "--self-test" in argv:
        from .selftest import run_all
        return run_all()

    import tkinter as tk

    from .db import Database
    from .accounting import Ledger
    from .ui import LedgerUI, _apply_window_icon, enable_high_dpi

    opts = parse_args(argv)
    path = opts["db"] or default_db_path()
    db = Database(path)
    if opts["company"]:
        db.set_meta("company", opts["company"])
    ledger = Ledger(db)
    if opts["demo"] and db.count_vouchers() == 0:
        from .demo import load_demo
        load_demo(ledger)

    enable_high_dpi()  # 必须在 Tk 创建窗口之前设置，否则高分屏仍是模糊渲染
    root = tk.Tk()
    _apply_window_icon(root)
    ui = LedgerUI(root, ledger)
    if opts["tab"] is not None:
        ui.select_tab(opts["tab"])
    root.mainloop()
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())