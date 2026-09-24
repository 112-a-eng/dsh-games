# -*- coding: utf-8 -*-
"""把小游戏打包成发布用 zip。

用法：
    py make_zip.py            # 合集（股票模拟交易 + 俄罗斯方块）
    py make_zip.py stock      # 只要股票模拟交易
    py make_zip.py tetris     # 只要俄罗斯方块
"""
import os
import sys
import zipfile

ROOT = r"D:\DSH"
VERSION = "1.0.0"

COLLECTION_README = """小游戏合集 v{ver}
================================================

本压缩包内含两个可独立运行的小游戏，都是纯 Python + tkinter 写的，已经打包成
exe，双击即可玩，不需要安装 Python。

【1】股票模拟交易   →  股票模拟交易\\StockGame.exe
      尽可能贴近 A 股实盘的交易模拟游戏：涨跌停（主板 ±10%、创业板/科创板 ±20%）、
      T+1、100 股一手、佣金万 2.5（最低 5 元）、印花税千 0.5、过户费 0.001%、
      滑点与冲击成本、限价挂单 / 撤单 / 部分成交、融资杠杆与强制平仓；
      行情由"市场状态机 + 行业/个股因子 + 新闻事件"生成，并实时合成指数。
      界面含五档盘口（点档位可填价）、逐笔成交明细、分时/日K、持仓/委托/成交/账户页。
      StockGame.exe 旁边的 _internal 文件夹是运行库，不能删、也不要只拷 exe。
      玩法与完整规则见  股票模拟交易\\游戏说明.md

【2】俄罗斯方块   →  俄罗斯方块\\Tetris.exe
      60FPS 增量渲染、幽灵落点、暂存 Hold、7-bag 随机、下三个预览、
      消行计分与等级加速、长按连发手感（自绘 DAS/ARR）。
      操作与源码说明见  俄罗斯方块\\说明.txt

【系统要求】
  Windows 10 / 11 64 位。股票游戏启动约 0.3 秒；俄罗斯方块单文件 exe 首次启动约 2 秒。

【注意】
  * 股票游戏使用了真实公司名与代码方便代入，但行情完全由模型生成，
    与真实市场无关，不构成任何投资建议。
  * exe 都是 PyInstaller 打包的，个别杀毒软件可能误报，加信任即可。

【源码】
  每个游戏目录下都有完整源码和一键打包脚本，需要用 Python 3.14 运行。
  相应入口加 --self-test 可跑无界面自测。
""".format(ver=VERSION)

TETRIS_README = """俄罗斯方块 Tetris v{ver}
================================================

【运行】双击 Tetris.exe

【操作】
  ← →       左右移动（长按连发）
  ↑ / X     顺时针旋转
  Z         逆时针旋转
  ↓         软降（+1 分/格，长按连发）
  空格      硬降（+2 分/格）
  C         暂存 / 取出（Hold）
  P         暂停
  R         重新开始
  Esc       退出

【规则】
  10×20 棋盘；消 1/2/3/4 行 = 100/300/500/800 × 等级，连击额外加分
  软降 +1 分/格，硬降 +2 分/格
  每消 10 行升一级，下落间隔从 800ms 递减到最低 70ms
  7-bag 随机（不会连续憋同一块）、幽灵落点、下三个方块预览、简化 SRS 踢墙

【源码】
  tetris.py                  单文件源码，零第三方依赖
  py tetris.py               直接运行
  py tetris.py --self-test   无界面逻辑自测
  build_exe.ps1              重新打包（需 py -m pip install pyinstaller）
""".format(ver=VERSION)

STOCK_QUICKSTART = """股票模拟交易游戏 v{ver} —— 快速开始
================================================

【怎么玩】
  1. 双击 StockGame.exe
  2. 开局设置：市场（A股 / 美股）、难度、初始资金、交易日数、节奏、随机种子
     节奏 = 一个交易日走多少现实时间：悠闲 10 分钟 / 慢 5 分钟（默认）/ 标准 2 分钟 / 快 60 秒 / 极速 15 秒
     相同种子可以复现完全一样的行情，方便复盘比较
  3. 点"开始交易"进入盘面：左侧选自选股，右侧填价格与数量，点"买入 B"或"卖出 S"

【快捷键】
  B 买入    S 卖出    空格 暂停    N 下一日    K 切换分时/日K    Esc 退出
  [ ] 节奏慢一档 / 快一档      1~5 跳到五档节奏预设
  , 单步进 1 个交易分钟        . 单步进 5 个交易分钟（也可点顶栏"进5分"）
  顶栏"自动"勾选框：取消后每根收盘会停下来，方便复盘当天成交
  鼠标在图表上移动可看十字光标与该点数据；点五档盘口任意一档可填入委托价；
  点自选股表头可按该列排序

【A 股规则要点（游戏里就是这么算的）】
  * 涨跌停：主板 ±10%、创业板/科创板 ±20%、ST ±5%；一字板买不到、卖不出
  * T+1：当日买入次日才可卖，"持仓"与"可卖"分开显示
  * 一手 100 股；科创板 200 股起、超过部分可 1 股递增
  * 费用：佣金万 2.5（单笔最低 5 元）、印花税千 0.5（仅卖出）、过户费 0.001%
  * 涨停价以上的委托是废单；市价买入按涨停价冻结资金
  * 限价单跳空以更优价成交；单分钟最多成交该分钟成交量的 10%，超出部分部分成交
  * 融资买入最多 1 倍杠杆，年利率 6.5%，担保比例低于 110% 会被强制平仓

【注意】
  游戏里用了真实公司名与代码方便代入，但行情完全由模型生成，与真实市场无关，
  不构成任何投资建议。详细规则、设计说明与已知简化见「游戏说明.md」。
  StockGame.exe 旁边的 _internal 文件夹是运行库（约 25 MB），不要删、也不要只拷 exe；
  要移动就整个文件夹一起移动，启动约 0.3 秒。

【源码】
  源码/ 目录：
    py stock_game_gui.py                  直接运行
    py -m stock_game --self-test          无界面自测（8 项，需在本目录执行）
    powershell -ExecutionPolicy Bypass -File build_stock_exe.ps1   重新打包
                                          （需先 py -m pip install pyinstaller）
""".format(ver=VERSION)


def add(zf, src, arc):
    if not os.path.exists(src):
        raise SystemExit("缺少文件: %s" % src)
    zf.write(src, arc)


def build_stock(zf, prefix):
    """股票模拟交易：onedir 版本（exe + _internal）整体放进 prefix 目录。"""
    src = os.path.join(ROOT, "dist", "StockGame")
    if not os.path.isdir(src):
        raise SystemExit("缺少 dist\\StockGame（先运行 build_stock_exe.ps1 生成 onedir 版本）")
    count = 0
    for folder, _dirs, files in os.walk(src):
        for name in files:
            full = os.path.join(folder, name)
            rel = os.path.relpath(full, src).replace("\\", "/")
            zf.write(full, "%s/%s" % (prefix, rel))
            count += 1
    if not os.path.exists(os.path.join(src, "StockGame.exe")):
        raise SystemExit("dist\\StockGame 里没有 StockGame.exe")
    print("   股票模拟交易：onedir 共 %d 个文件" % count)

    add(zf, os.path.join(ROOT, "股票模拟交易说明.md"), prefix + "/游戏说明.md")
    add(zf, os.path.join(ROOT, "stock_icon.png"), prefix + "/stock_icon.png")
    add(zf, os.path.join(ROOT, "stock_icon.ico"), prefix + "/stock_icon.ico")
    zf.writestr(prefix + "/快速开始.txt", STOCK_QUICKSTART)

    pkg = os.path.join(ROOT, "stock_game")
    for name in sorted(os.listdir(pkg)):
        if name.endswith(".py"):
            add(zf, os.path.join(pkg, name), "%s/源码/stock_game/%s" % (prefix, name))
    add(zf, os.path.join(ROOT, "stock_game_gui.py"), prefix + "/源码/stock_game_gui.py")
    add(zf, os.path.join(ROOT, "build_stock_exe.ps1"), prefix + "/源码/build_stock_exe.ps1")
    add(zf, os.path.join(ROOT, ".build", "make_stock_icon.py"),
        prefix + "/源码/.build/make_stock_icon.py")


def build_tetris(zf, prefix):
    """俄罗斯方块：prefix 为该游戏在压缩包内的目录。"""
    add(zf, os.path.join(ROOT, "dist", "Tetris.exe"), prefix + "/Tetris.exe")
    add(zf, os.path.join(ROOT, "tetris.py"), prefix + "/tetris.py")
    add(zf, os.path.join(ROOT, "tetris.ico"), prefix + "/tetris.ico")
    add(zf, os.path.join(ROOT, "build_exe.ps1"), prefix + "/build_exe.ps1")
    add(zf, os.path.join(ROOT, ".build", "make_icon.py"), prefix + "/.build/make_icon.py")
    zf.writestr(prefix + "/说明.txt", TETRIS_README)


def main():
    which = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()

    if which in ("all", "collection", "合集"):
        out = os.path.join(ROOT, "小游戏合集-v%s.zip" % VERSION)
        top = "小游戏合集"
        jobs = [("stock", top + "/股票模拟交易"), ("tetris", top + "/俄罗斯方块")]
    elif which == "stock":
        out = os.path.join(ROOT, "股票模拟交易-v%s.zip" % VERSION)
        top = "股票模拟交易"
        jobs = [("stock", top)]
    elif which == "tetris":
        out = os.path.join(ROOT, "俄罗斯方块-v%s.zip" % VERSION)
        top = "俄罗斯方块"
        jobs = [("tetris", top)]
    else:
        raise SystemExit("用法: py make_zip.py [all|stock|tetris]")

    if os.path.exists(out):
        os.remove(out)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for kind, prefix in jobs:
            build_stock(zf, prefix) if kind == "stock" else build_tetris(zf, prefix)
        if len(jobs) > 1:
            zf.writestr(top + "/说明.txt", COLLECTION_README)
        entries = [(i.filename, i.file_size, i.compress_size) for i in zf.infolist()]

    size = os.path.getsize(out)
    raw = sum(e[1] for e in entries)
    comp = sum(e[2] for e in entries)
    print("已生成 %s（%.2f MB，%d 个文件，压缩率 %.0f%%）"
          % (os.path.basename(out), size / 1048576, len(entries), 100 * comp / max(1, raw)))
    for name, raw_size, _ in entries:
        print("   %-56s %9.1f KB" % (name, raw_size / 1024))

    # 回读校验：CRC、中文名、每个游戏的关键文件与说明
    kinds = {kind for kind, _ in jobs}
    with zipfile.ZipFile(out) as zf:
        bad = zf.testzip()
        if bad:
            raise SystemExit("压缩包损坏: %s" % bad)
        names = zf.namelist()
        assert any("说明" in n for n in names), "缺少说明文件"
        if "stock" in kinds:
            assert any(n.endswith("StockGame.exe") for n in names), "缺少 StockGame.exe"
            assert any("游戏说明.md" in n for n in names), "缺少股票游戏说明"
        if "tetris" in kinds:
            assert any(n.endswith("Tetris.exe") for n in names), "缺少 Tetris.exe"
            assert any(n.endswith("俄罗斯方块/说明.txt") or n == "俄罗斯方块/说明.txt"
                       for n in names), "缺少俄罗斯方块说明"
    print("回读校验通过（CRC 正确、中文文件名正常）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
