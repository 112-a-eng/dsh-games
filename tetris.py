# -*- coding: utf-8 -*-
"""俄罗斯方块 (Tetris) —— 单文件 tkinter 游戏，无需第三方依赖。

运行:      py tetris.py
逻辑自测:  py tetris.py --self-test

操作:
    左 / 右方向键   左右移动 (长按连发)
    上方向键 / X    顺时针旋转
    Z               逆时针旋转
    下方向键        软降 (+1 分/格, 长按连发)
    空格            硬降 (+2 分/格)
    C               暂存 / 取出 (Hold)
    P               暂停
    R               重新开始
    Esc             退出

实现要点:
    * 渲染固定 60FPS，与重力速度解耦，输入即时可见；
    * Canvas 元素一次性创建后复用（只改坐标/颜色），不做整屏重建；
    * 长按连发自带 DAS/ARR 节奏，绕开系统按键重复的 500ms 延迟。
"""

import random
import sys
import time
import tkinter as tk

# ---------------------------------------------------------------- 基础常量
COLS, ROWS = 10, 20
CELL = 30

SHAPES = {
    "I": [[0, 0, 0, 0], [1, 1, 1, 1], [0, 0, 0, 0], [0, 0, 0, 0]],
    "J": [[1, 0, 0], [1, 1, 1], [0, 0, 0]],
    "L": [[0, 0, 1], [1, 1, 1], [0, 0, 0]],
    "O": [[1, 1], [1, 1]],
    "S": [[0, 1, 1], [1, 1, 0], [0, 0, 0]],
    "T": [[0, 1, 0], [1, 1, 1], [0, 0, 0]],
    "Z": [[1, 1, 0], [0, 1, 1], [0, 0, 0]],
}
PIECE_KINDS = list(SHAPES)

COLORS = {
    "I": "#38d6e6",
    "J": "#4b7df5",
    "L": "#f5a13c",
    "O": "#f2d244",
    "S": "#4fd97b",
    "T": "#b26ff0",
    "Z": "#f2545b",
}

# 旋转踢墙尝试顺序（简化版 SRS）
KICKS = [(0, 0), (-1, 0), (1, 0), (-2, 0), (2, 0),
         (0, -1), (-1, -1), (1, -1), (-2, -1), (2, -1)]

LINE_SCORE = {1: 100, 2: 300, 3: 500, 4: 800}

# 手感参数（毫秒）
FRAME_MS = 16          # 渲染帧间隔 ≈ 60 FPS
DAS_MS = 170           # 长按多久开始连发
ARR_MS = 35            # 左右连发间隔
SOFT_DROP_MS = 40      # 软降连发间隔


def rotate_cw(matrix):
    """顺时针旋转一个方阵。"""
    n = len(matrix)
    return [[matrix[n - 1 - x][y] for x in range(n)] for y in range(n)]


def build_rotations():
    table = {}
    for kind, matrix in SHAPES.items():
        states = [matrix]
        for _ in range(3):
            states.append(rotate_cw(states[-1]))
        table[kind] = states
    return table


ROTATIONS = build_rotations()


def _shade(hex_color, factor):
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    clamp = lambda v: max(0, min(255, int(v * factor)))
    return "#%02x%02x%02x" % (clamp(r), clamp(g), clamp(b))


LIGHT = {k: _shade(v, 1.45) for k, v in COLORS.items()}
DARK = {k: _shade(v, 0.55) for k, v in COLORS.items()}


def cells_of_matrix(matrix):
    return [(x, y) for y, row in enumerate(matrix) for x, v in enumerate(row) if v]


# ---------------------------------------------------------------- 游戏逻辑
class TetrisEngine:
    """与界面完全解耦的游戏内核，可无界面运行（便于自测）。"""

    def __init__(self, rng=None):
        self.rng = rng if rng is not None else random.Random()
        self.board_version = 0
        self.reset()

    # -- 开局 / 重开 -------------------------------------------------
    def reset(self):
        self.board = [[None] * COLS for _ in range(ROWS)]
        self.bag = []
        self.queue = []
        self.hold = None
        self.hold_used = False
        self.score = 0
        self.lines = 0
        self.level = 1
        self.combo = -1
        self.game_over = False
        self.piece = None
        self.board_version += 1
        self._fill_queue()
        self.spawn()

    # -- 7-bag 随机 --------------------------------------------------
    def _next_kind(self):
        if not self.bag:
            self.bag = PIECE_KINDS[:]
            self.rng.shuffle(self.bag)
        return self.bag.pop()

    def _fill_queue(self):
        while len(self.queue) < 5:
            self.queue.append(self._next_kind())

    # -- 方块 --------------------------------------------------------
    def spawn(self):
        kind = self.queue.pop(0)
        self._fill_queue()
        n = len(SHAPES[kind])
        self.piece = {"kind": kind, "rot": 0, "x": (COLS - n) // 2, "y": 0}
        self.hold_used = False
        if self.collides(self.piece):
            self.game_over = True

    def cells_of(self, piece):
        matrix = ROTATIONS[piece["kind"]][piece["rot"] % 4]
        return [(piece["x"] + x, piece["y"] + y) for x, y in cells_of_matrix(matrix)]

    def collides(self, piece):
        for x, y in self.cells_of(piece):
            if x < 0 or x >= COLS or y >= ROWS:
                return True
            if y >= 0 and self.board[y][x]:
                return True
        return False

    # -- 操作 --------------------------------------------------------
    def move(self, dx, dy=0):
        if self.game_over or self.piece is None:
            return False
        probe = dict(self.piece)
        probe["x"] += dx
        probe["y"] += dy
        if self.collides(probe):
            return False
        self.piece = probe
        return True

    def rotate(self, direction=1):
        if self.game_over or self.piece is None:
            return False
        rot = (self.piece["rot"] + direction) % 4
        for kx, ky in KICKS:
            probe = dict(self.piece)
            probe["rot"] = rot
            probe["x"] += kx
            probe["y"] += ky
            if not self.collides(probe):
                self.piece = probe
                return True
        return False

    def ghost_y(self):
        if self.piece is None:
            return 0
        probe = dict(self.piece)
        while not self.collides(dict(probe, y=probe["y"] + 1)):
            probe["y"] += 1
        return probe["y"]

    def soft_drop(self):
        if self.game_over or self.piece is None:
            return False
        if self.move(0, 1):
            self.score += 1
            return True
        self.lock()
        return False

    def hard_drop(self):
        if self.game_over or self.piece is None:
            return False
        target = self.ghost_y()
        self.score += 2 * (target - self.piece["y"])
        self.piece = dict(self.piece, y=target)
        self.lock()
        return True

    def hold_piece(self):
        if self.game_over or self.piece is None or self.hold_used:
            return False
        current = self.piece["kind"]
        if self.hold is None:
            self.hold = current
            self.spawn()
        else:
            swap = self.hold
            self.hold = current
            n = len(SHAPES[swap])
            self.piece = {"kind": swap, "rot": 0, "x": (COLS - n) // 2, "y": 0}
            if self.collides(self.piece):
                self.game_over = True
        self.hold_used = True
        return True

    def tick(self):
        """重力推进一格；无法下落则锁定。"""
        if self.game_over or self.piece is None:
            return
        if not self.move(0, 1):
            self.lock()

    # -- 锁定 / 消行 -------------------------------------------------
    def lock(self):
        if self.piece is None:
            return
        locked_above_top = False
        for x, y in self.cells_of(self.piece):
            if y < 0:
                locked_above_top = True
                continue
            if 0 <= y < ROWS and 0 <= x < COLS:
                self.board[y][x] = self.piece["kind"]
        self.board_version += 1

        cleared = self.clear_lines()
        if cleared:
            self.combo += 1
            if self.combo > 0:
                self.score += 50 * self.combo * self.level
        else:
            self.combo = -1

        self.piece = None
        if locked_above_top:
            self.game_over = True
            return
        self.spawn()

    def clear_lines(self):
        full = [y for y in range(ROWS) if all(self.board[y])]
        for y in full:
            del self.board[y]
            self.board.insert(0, [None] * COLS)
        n = len(full)
        if n:
            self.lines += n
            self.score += LINE_SCORE[n] * self.level
            self.level = 1 + self.lines // 10
        return n

    # -- 速度 --------------------------------------------------------
    @property
    def drop_interval(self):
        """毫秒：等级越高下落越快。"""
        return max(70, 800 - (self.level - 1) * 70)


# ---------------------------------------------------------------- 绘制元素
class CellSprite:
    """可复用的方块图形：一次创建，之后只改坐标与颜色。"""

    __slots__ = ("canvas", "size", "ghost", "bevel", "rect", "hi_h", "hi_v",
                 "kind", "shown")

    def __init__(self, canvas, size, ghost=False):
        self.canvas = canvas
        self.size = size
        self.ghost = ghost
        self.bevel = (not ghost) and size >= 14
        self.kind = None
        self.shown = False
        if ghost:
            self.rect = canvas.create_rectangle(0, 0, 0, 0, fill="", width=2,
                                                dash=(4, 3), state="hidden")
        else:
            self.rect = canvas.create_rectangle(0, 0, 0, 0, outline="",
                                                state="hidden")
        self.hi_h = canvas.create_line(0, 0, 0, 0, width=2, state="hidden")
        self.hi_v = canvas.create_line(0, 0, 0, 0, width=2, state="hidden")

    def _items(self):
        return (self.rect,) if self.ghost else (self.rect, self.hi_h, self.hi_v)

    def move_to(self, px, py, kind):
        size = self.size
        x1, y1 = px + size, py + size
        canvas = self.canvas
        if kind != self.kind:
            self.kind = kind
            if self.ghost:
                canvas.itemconfigure(self.rect, outline=LIGHT[kind])
            else:
                canvas.itemconfigure(self.rect, fill=COLORS[kind], outline=DARK[kind])
                if self.bevel:
                    canvas.itemconfigure(self.hi_h, fill=LIGHT[kind])
                    canvas.itemconfigure(self.hi_v, fill=LIGHT[kind])
        if self.ghost:
            canvas.coords(self.rect, px + 2, py + 2, x1 - 2, y1 - 2)
        else:
            canvas.coords(self.rect, px, py, x1, y1)
            if self.bevel:
                canvas.coords(self.hi_h, px + 2, py + 2, x1 - 3, py + 2)
                canvas.coords(self.hi_v, px + 2, py + 2, px + 2, y1 - 3)
        if not self.shown:
            self.show()

    def show(self):
        for item in self._items():
            self.canvas.itemconfigure(item, state="normal")
        self.shown = True

    def hide(self):
        if self.shown:
            for item in self._items():
                self.canvas.itemconfigure(item, state="hidden")
            self.shown = False


# ---------------------------------------------------------------- 界面
BG = "#0d1017"
GRID = "#171d28"
PANEL = "#11151e"
PANEL_LINE = "#2a3142"
TEXT = "#e6ecf5"
MUTED = "#7d8798"
ACCENT = "#38d6e6"
FONT = "Microsoft YaHei UI"
PREVIEW_CELL = 18


class TetrisApp:
    def __init__(self, root):
        self.root = root
        self.engine = TetrisEngine()
        self.paused = False

        self._acc = 0.0            # 重力计时累加器
        self._last = time.perf_counter()
        self._repeat_job = None
        self._repeat_key = None
        self._board_version = -1
        self._score = self._level = self._lines = None
        self._hold_sig = self._next_sig = self._overlay_state = object()

        root.title("俄罗斯方块 · Tetris")
        root.configure(bg=BG)
        root.resizable(False, False)

        board_w, board_h = COLS * CELL, ROWS * CELL
        self.board_canvas = tk.Canvas(
            root, width=board_w, height=board_h, bg="#080a0f",
            highlightthickness=1, highlightbackground=PANEL_LINE,
        )
        self.board_canvas.grid(row=0, column=0, padx=(16, 12), pady=16,
                               rowspan=2, sticky="n")

        side = tk.Frame(root, bg=BG)
        side.grid(row=0, column=1, padx=(0, 16), pady=16, sticky="n")

        self.score_var = tk.StringVar()
        self.level_var = tk.StringVar()
        self.lines_var = tk.StringVar()

        self._stat(side, "分数", self.score_var, 20)
        row = tk.Frame(side, bg=BG)
        row.pack(fill="x", pady=(8, 12))
        self._stat(row, "等级", self.level_var, 15, side="left", expand=True)
        self._stat(row, "消行", self.lines_var, 15, side="left", expand=True)

        self._caption(side, "暂存 (C)")
        self.hold_canvas = tk.Canvas(
            side, width=4 * PREVIEW_CELL, height=4 * PREVIEW_CELL,
            bg=PANEL, highlightthickness=1, highlightbackground=PANEL_LINE,
        )
        self.hold_canvas.pack(pady=(2, 12))

        self._caption(side, "下一个")
        self.next_canvas = tk.Canvas(
            side, width=4 * PREVIEW_CELL, height=12 * PREVIEW_CELL,
            bg=PANEL, highlightthickness=1, highlightbackground=PANEL_LINE,
        )
        self.next_canvas.pack(pady=(2, 12))

        help_text = ("← →  移动        ↑ / X  旋转\n"
                     "Z    逆时针      ↓      软降\n"
                     "空格 硬降        C      暂存\n"
                     "P    暂停        R      重开")
        tk.Label(side, text=help_text, font=(FONT, 9), fg=MUTED, bg=BG,
                 justify="left", anchor="w").pack(fill="x", pady=(0, 10))

        buttons = tk.Frame(side, bg=BG)
        buttons.pack(fill="x")
        self.pause_btn = tk.Button(
            buttons, text="暂停", font=(FONT, 10), width=8, relief="flat",
            bg="#1c2431", fg=TEXT, activebackground="#2a3547", activeforeground=TEXT,
            command=self.toggle_pause,
        )
        self.pause_btn.pack(side="left")
        tk.Button(
            buttons, text="重开", font=(FONT, 10), width=8, relief="flat",
            bg="#1c2431", fg=TEXT, activebackground="#2a3547", activeforeground=TEXT,
            command=self.restart,
        ).pack(side="left", padx=(8, 0))

        self._build_canvas_items()
        self._bind_keys()

        root.focus_force()
        self.redraw()
        self.root.after(FRAME_MS, self.loop)

    # -- 一次性建好所有画布元素 --------------------------------------
    def _build_canvas_items(self):
        canvas = self.board_canvas
        # 网格线（常驻）
        self.grid_items = []
        for x in range(1, COLS):
            self.grid_items.append(canvas.create_line(x * CELL, 0, x * CELL,
                                                      ROWS * CELL, fill=GRID))
        for y in range(1, ROWS):
            self.grid_items.append(canvas.create_line(0, y * CELL, COLS * CELL,
                                                      y * CELL, fill=GRID))

        # 棋盘格子：200 个常驻 sprite
        self.board_sprites = [
            [CellSprite(canvas, CELL) for _ in range(COLS)] for _ in range(ROWS)
        ]
        # 幽灵落点 4 格 + 当前方块 4 格
        self.ghost_sprites = [CellSprite(canvas, CELL, ghost=True) for _ in range(4)]
        self.piece_sprites = [CellSprite(canvas, CELL) for _ in range(4)]

        # 覆盖层（暂停 / 结束），建在最后以保证在最上层
        w, h = COLS * CELL, ROWS * CELL
        self.overlay_rect = canvas.create_rectangle(
            0, 0, w, h, fill="#05070a", stipple="gray50", outline="", state="hidden")
        self.overlay_title = canvas.create_text(
            w / 2, h / 2 - 18, text="", fill=TEXT, font=(FONT, 22, "bold"),
            state="hidden")
        self.overlay_sub = canvas.create_text(
            w / 2, h / 2 + 18, text="", fill=ACCENT, font=(FONT, 11), state="hidden")

        # 预览区 sprite
        self.hold_sprites = [CellSprite(self.hold_canvas, PREVIEW_CELL) for _ in range(4)]
        self.next_sprites = [CellSprite(self.next_canvas, PREVIEW_CELL) for _ in range(12)]

    # -- 小工具 ------------------------------------------------------
    def _caption(self, parent, text):
        tk.Label(parent, text=text, font=(FONT, 10, "bold"), fg=MUTED,
                 bg=BG, anchor="w").pack(fill="x")

    def _stat(self, parent, title, var, size, side=None, expand=False):
        box = tk.Frame(parent, bg=BG)
        if side:
            box.pack(side=side, fill="x", expand=expand)
        else:
            box.pack(fill="x")
        tk.Label(box, text=title, font=(FONT, 9), fg=MUTED, bg=BG,
                 anchor="w").pack(fill="x")
        tk.Label(box, textvariable=var, font=(FONT, size, "bold"), fg=TEXT,
                 bg=BG, anchor="w").pack(fill="x")

    # -- 按键：自带 DAS/ARR 连发，避免系统重复延迟 --------------------
    def _bind_keys(self):
        root = self.root
        root.bind("<KeyPress-Left>",
                  lambda e: self._press("Left", lambda: self.engine.move(-1), True))
        root.bind("<KeyRelease-Left>", lambda e: self._release("Left"))
        root.bind("<KeyPress-Right>",
                  lambda e: self._press("Right", lambda: self.engine.move(1), True))
        root.bind("<KeyRelease-Right>", lambda e: self._release("Right"))
        root.bind("<KeyPress-Down>",
                  lambda e: self._press("Down", self._soft_drop_step, True))
        root.bind("<KeyRelease-Down>", lambda e: self._release("Down"))

        for seq in ("<Up>", "<x>", "<X>"):
            root.bind(seq, lambda e: self._press("rotate", lambda: self.engine.rotate(1)))
        for seq in ("<z>", "<Z>"):
            root.bind(seq, lambda e: self._press("rotate", lambda: self.engine.rotate(-1)))
        root.bind("<space>", lambda e: self._press("hard", self._hard_drop))
        for seq in ("<c>", "<C>"):
            root.bind(seq, lambda e: self._press("hold", self.engine.hold_piece))
        for seq in ("<p>", "<P>"):
            root.bind(seq, lambda e: (self.toggle_pause(), "break")[1])
        for seq in ("<r>", "<R>"):
            root.bind(seq, lambda e: (self.restart(), "break")[1])
        root.bind("<Escape>", lambda e: root.destroy())

    def _press(self, key, action, repeat=False):
        if self.paused or self.engine.game_over:
            return "break"
        if repeat and self._repeat_key == key:
            return "break"          # 系统自动重复事件，忽略（用自己的节奏）
        self._cancel_repeat()
        action()
        if repeat:
            self._repeat_key = key
            interval = SOFT_DROP_MS if key == "Down" else ARR_MS
            self._repeat_job = self.root.after(
                DAS_MS, lambda: self._repeat_step(key, action, interval))
        self.redraw()
        return "break"

    def _repeat_step(self, key, action, interval):
        self._repeat_job = None
        if self._repeat_key != key or self.paused or self.engine.game_over:
            self._cancel_repeat()
            return
        action()
        self.redraw()
        self._repeat_job = self.root.after(
            interval, lambda: self._repeat_step(key, action, interval))

    def _release(self, key):
        if self._repeat_key == key:
            self._cancel_repeat()
        return "break"

    def _cancel_repeat(self):
        if self._repeat_job is not None:
            self.root.after_cancel(self._repeat_job)
            self._repeat_job = None
        self._repeat_key = None

    def _soft_drop_step(self):
        self.engine.soft_drop()
        self._acc = 0.0

    def _hard_drop(self):
        self.engine.hard_drop()
        self._acc = 0.0

    # -- 控制 --------------------------------------------------------
    def toggle_pause(self):
        if self.engine.game_over:
            return
        self.paused = not self.paused
        if self.paused:
            self._cancel_repeat()
        self.pause_btn.configure(text="继续" if self.paused else "暂停")
        self.redraw()

    def restart(self):
        self._cancel_repeat()
        self.engine.reset()
        self.paused = False
        self._acc = 0.0
        self._board_version = -1
        self.pause_btn.configure(text="暂停")
        self.redraw()

    # -- 主循环：固定帧率渲染，重力按时间累加 ------------------------
    def loop(self):
        now = time.perf_counter()
        dt = (now - self._last) * 1000.0
        self._last = now
        engine = self.engine
        if not self.paused and not engine.game_over:
            self._acc = min(self._acc + dt, engine.drop_interval * 3.0)
            while self._acc >= engine.drop_interval:
                self._acc -= engine.drop_interval
                engine.tick()
                if engine.game_over:
                    break
        self.redraw()
        self.root.after(FRAME_MS, self.loop)

    # -- 增量刷新 ----------------------------------------------------
    def redraw(self):
        engine = self.engine

        if self._board_version != engine.board_version:
            self._board_version = engine.board_version
            self.sync_board()

        if self._score != engine.score:
            self._score = engine.score
            self.score_var.set(str(engine.score))
        if self._level != engine.level:
            self._level = engine.level
            self.level_var.set(str(engine.level))
        if self._lines != engine.lines:
            self._lines = engine.lines
            self.lines_var.set(str(engine.lines))

        self.sync_piece()
        self.sync_overlay()
        self.sync_previews()

    def sync_board(self):
        engine = self.engine
        for y in range(ROWS):
            row = engine.board[y]
            sprites = self.board_sprites[y]
            for x in range(COLS):
                kind = row[x]
                if kind:
                    sprites[x].move_to(x * CELL, y * CELL, kind)
                else:
                    sprites[x].hide()

    def sync_piece(self):
        engine = self.engine
        piece = engine.piece
        alive = piece is not None and not engine.game_over

        visible = [c for c in engine.cells_of(piece) if c[1] >= 0] if alive else []
        for i, sprite in enumerate(self.piece_sprites):
            if i < len(visible):
                x, y = visible[i]
                sprite.move_to(x * CELL, y * CELL, piece["kind"])
            else:
                sprite.hide()

        ghost_cells = []
        if alive:
            gy = engine.ghost_y()
            if gy != piece["y"]:
                ghost_cells = [c for c in engine.cells_of(dict(piece, y=gy)) if c[1] >= 0]
        for i, sprite in enumerate(self.ghost_sprites):
            if i < len(ghost_cells):
                x, y = ghost_cells[i]
                sprite.move_to(x * CELL, y * CELL, piece["kind"])
            else:
                sprite.hide()

    def sync_overlay(self):
        engine = self.engine
        if engine.game_over:
            state = ("游戏结束", "得分 %d · 按 R 重新开始" % engine.score)
        elif self.paused:
            state = ("已暂停", "按 P 继续")
        else:
            state = None
        if state == self._overlay_state:
            return
        self._overlay_state = state
        canvas = self.board_canvas
        if state is None:
            for item in (self.overlay_rect, self.overlay_title, self.overlay_sub):
                canvas.itemconfigure(item, state="hidden")
        else:
            canvas.itemconfigure(self.overlay_title, text=state[0], state="normal")
            canvas.itemconfigure(self.overlay_sub, text=state[1], state="normal")
            canvas.itemconfigure(self.overlay_rect, state="normal")

    def sync_previews(self):
        engine = self.engine
        hold = engine.hold
        if hold != self._hold_sig:
            self._hold_sig = hold
            self._layout(self.hold_sprites, [hold] if hold else [])
        queue = tuple(engine.queue[:3])
        if queue != self._next_sig:
            self._next_sig = queue
            self._layout(self.next_sprites, list(queue))

    @staticmethod
    def _layout(sprites, kinds):
        """把若干方块居中画进 4 列宽的格子，每个占 4 行。"""
        used = 0
        for i, kind in enumerate(kinds):
            if kind is None:
                continue
            cells = cells_of_matrix(ROTATIONS[kind][0])
            xs = [c[0] for c in cells]
            ys = [c[1] for c in cells]
            w = max(xs) - min(xs) + 1
            h = max(ys) - min(ys) + 1
            ox = (4 - w) / 2 * PREVIEW_CELL - min(xs) * PREVIEW_CELL
            oy = i * 4 * PREVIEW_CELL + (4 - h) / 2 * PREVIEW_CELL - min(ys) * PREVIEW_CELL
            for j, (x, y) in enumerate(cells):
                sprites[used + j].move_to(ox + x * PREVIEW_CELL,
                                          oy + y * PREVIEW_CELL, kind)
            used += len(cells)
        for sprite in sprites[used:]:
            sprite.hide()


# ---------------------------------------------------------------- 自测
def run_self_test():
    """无界面随机对局，校验内核不变量。"""
    driver = random.Random(20240607)
    games = steps_total = pieces_seen = 0

    for _ in range(25):
        eng = TetrisEngine(random.Random(driver.randrange(1 << 30)))
        steps = 0
        prev_lines = 0
        while not eng.game_over and steps < 4000:
            r = driver.random()
            if r < 0.22:
                eng.move(-1)
            elif r < 0.44:
                eng.move(1)
            elif r < 0.58:
                eng.rotate(1)
            elif r < 0.62:
                eng.rotate(-1)
            elif r < 0.66:
                eng.hold_piece()
            elif r < 0.72:
                eng.hard_drop()
                pieces_seen += 1
            elif r < 0.80:
                eng.soft_drop()
            else:
                eng.tick()
            steps += 1

            assert len(eng.board) == ROWS, "board row count changed"
            assert all(len(row) == COLS for row in eng.board), "board width changed"
            for row in eng.board:
                for cell in row:
                    assert cell is None or cell in COLORS, "invalid cell: %r" % (cell,)
            assert eng.lines >= prev_lines, "line count went backwards"
            assert not any(all(row) for row in eng.board), "full row left uncleared"
            assert eng.score >= 0, "negative score"
            if eng.piece is not None and not eng.game_over:
                assert not eng.collides(eng.piece), "piece overlaps board after input"
            prev_lines = eng.lines

        games += 1
        steps_total += steps

    # 消行 / 计分 单元校验
    eng = TetrisEngine(random.Random(0))
    eng.piece = None
    for x in range(COLS):
        eng.board[ROWS - 1][x] = "I"
    eng.board[ROWS - 2][0] = "O"
    eng.board[ROWS - 2][1] = "O"
    score_before = eng.score
    cleared = eng.clear_lines()
    assert cleared == 1, "expected 1 cleared row, got %d" % cleared
    assert eng.lines == 1, "line counter wrong"
    assert eng.board[ROWS - 1][0] == "O", "rows not shifted down into the cleared row"
    assert eng.board[ROWS - 1][1] == "O", "rows not shifted down into the cleared row"
    assert all(cell is None for cell in eng.board[ROWS - 2]), "stale row above clear"
    assert all(cell is None for cell in eng.board[0]), "new top row not empty"
    assert eng.score == score_before + LINE_SCORE[1] * 1, "line score wrong"

    # 硬降计分
    eng2 = TetrisEngine(random.Random(1))
    s0 = eng2.score
    eng2.hard_drop()
    assert eng2.score >= s0 + 2, "hard drop score missing"

    # 速度曲线
    eng3 = TetrisEngine(random.Random(2))
    assert eng3.drop_interval == 800, "level 1 interval wrong"
    eng3.lines = 50
    eng3.level = 1 + eng3.lines // 10
    assert eng3.drop_interval == max(70, 800 - 5 * 70), "level 6 interval wrong"

    # 7-bag：强制从空袋开始，每 7 次抽取应恰好是全部 7 种方块
    eng4 = TetrisEngine(random.Random(3))
    eng4.bag = []
    for i in range(10):
        chunk = [eng4._next_kind() for _ in range(7)]
        assert sorted(chunk) == sorted(PIECE_KINDS), "7-bag broken at bag %d" % i

    # board_version 用于界面增量刷新，必须随棋盘变化单调变化
    eng5 = TetrisEngine(random.Random(4))
    v0 = eng5.board_version
    eng5.hard_drop()
    assert eng5.board_version > v0, "board_version did not change on lock"
    v1 = eng5.board_version
    eng5.reset()
    assert eng5.board_version > v1, "board_version did not change on reset"

    print("self-test OK | games=%d steps=%d hard_drops=%d" %
          (games, steps_total, pieces_seen))
    return 0


def main():
    if "--self-test" in sys.argv:
        return run_self_test()
    root = tk.Tk()
    TetrisApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
