package com.dsh.match3;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.graphics.Shader;
import android.graphics.Typeface;
import android.os.SystemClock;
import android.view.MotionEvent;
import android.view.View;

import java.util.ArrayList;
import java.util.List;

/**
 * 三消棋盘视图：全部用 Canvas 手绘（没有布局 XML、没有图片资源、不依赖 AndroidX）。
 *
 * <p>动画是一个小状态机：交换 → 消除（缩放消失）→ 下落/补充 → 再检查匹配（连锁）→ 回到静止。
 * 每个阶段用自己的时长，阶段结束时才去改棋盘数据，这样逻辑和画面不会打架。
 */
public class GameView extends View {

    public interface Listener {
        void onScoreChanged(int score, int movesLeft);

        void onLevelComplete(int level, int stars, int score);

        void onLevelFailed(int level, int score);
    }

    // 各阶段时长（毫秒）
    private static final long T_SWAP = 150;
    private static final long T_CLEAR = 220;
    private static final long T_FALL = 190;
    private static final long HINT_DELAY = 4000;

    private static final int PHASE_IDLE = 0;
    private static final int PHASE_SWAP = 1;
    private static final int PHASE_SWAP_BACK = 2;
    private static final int PHASE_CLEAR = 3;
    private static final int PHASE_FALL = 4;

    private static final int BG = 0xFF0D1017;
    private static final int BOARD_BG = 0xFF1A2029;
    private static final int CELL_BG = 0xFF232B36;
    private static final int PANEL = 0xFF1B2431;
    private static final int TEXT = 0xFFE6ECF5;
    private static final int MUTED = 0xFF7D8798;
    private static final int ACCENT = 0xFF3F8CFF;
    private static final int GOLD = 0xFFEDC22E;

    private static final int[] GEM_COLOR = {
            0xFFE5484D, 0xFFF5A524, 0xFFF2D244, 0xFF3FBF7F, 0xFF3F8CFF, 0xFFB26FF0
    };
    private static final int[] GEM_DARK = {
            0xFF9E1F26, 0xFFA85300, 0xFFA08A00, 0xFF1F7A4E, 0xFF1B5AA8, 0xFF6B36A8
    };

    private final Board board;
    private final Listener listener;
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF rect = new RectF();
    private final Path path = new Path();

    // 布局
    private float boardLeft, boardTop, boardSize, cellSize, gap;
    private final RectF restartBtn = new RectF();
    private final RectF actionBtn = new RectF();

    // 交互
    private int selected = -1;
    private float downX, downY;
    private int dragFrom = -1;
    private long lastInput;
    private int[] hintMove;
    private long hintShownAt;

    // 动画状态
    private int phase = PHASE_IDLE;
    private long phaseStart;
    private int swapA = -1, swapB = -1;
    private Board.MatchSet pendingClear;
    private int[] clearCells;
    private List<int[]> fallMoves = new ArrayList<int[]>();
    private List<int[]> fallSpawns = new ArrayList<int[]>();
    private int lastGain;
    private float gainPulse;
    private int lastSpawnIndex = -1;

    public GameView(Context context, Board board, Listener listener) {
        super(context);
        this.board = board;
        this.listener = listener;
        setBackgroundColor(BG);
        setFocusable(true);
        lastInput = SystemClock.uptimeMillis();
    }

    // ---------------------------------------------------------------- 尺寸

    @Override
    protected void onSizeChanged(int w, int h, int oldw, int oldh) {
        super.onSizeChanged(w, h, oldw, oldh);
        float pad = w * 0.035f;
        float headerH = h * 0.22f;
        boardLeft = pad;
        boardTop = headerH;
        boardSize = Math.min(w - pad * 2, h - headerH - pad * 1.6f);
        gap = boardSize * 0.022f;
        cellSize = (boardSize - gap * (Board.SIZE + 1)) / Board.SIZE;
    }

    private float cellLeft(float gx) {
        return boardLeft + gap * (1 + gx) + cellSize * gx;
    }

    private float cellTop(float gy) {
        return boardTop + gap * (1 + gy) + cellSize * gy;
    }

    private float centerX(int index) {
        return cellLeft(Board.xOf(index)) + cellSize / 2f;
    }

    private float centerY(int index) {
        return cellTop(Board.yOf(index)) + cellSize / 2f;
    }

    private int cellAt(float px, float py) {
        for (int y = 0; y < Board.SIZE; y++) {
            for (int x = 0; x < Board.SIZE; x++) {
                float l = cellLeft(x), t = cellTop(y);
                if (px >= l && px <= l + cellSize && py >= t && py <= t + cellSize) {
                    return Board.indexOf(x, y);
                }
            }
        }
        return -1;
    }

    // ---------------------------------------------------------------- 输入

    @Override
    public boolean onTouchEvent(MotionEvent e) {
        long now = SystemClock.uptimeMillis();
        switch (e.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                lastInput = now;
                hintMove = null;
                downX = e.getX();
                downY = e.getY();
                dragFrom = cellAt(downX, downY);
                return true;

            case MotionEvent.ACTION_MOVE: {
                if (phase != PHASE_IDLE || dragFrom < 0) return true;
                float dx = e.getX() - downX, dy = e.getY() - downY;
                float threshold = cellSize * 0.42f;
                if (Math.abs(dx) < threshold && Math.abs(dy) < threshold) return true;
                int from = dragFrom;
                dragFrom = -1;
                int tx = Board.xOf(from), ty = Board.yOf(from);
                if (Math.abs(dx) > Math.abs(dy)) {
                    tx += dx > 0 ? 1 : -1;
                } else {
                    ty += dy > 0 ? 1 : -1;
                }
                if (tx < 0 || tx >= Board.SIZE || ty < 0 || ty >= Board.SIZE) return true;
                selected = -1;
                attemptSwap(from, Board.indexOf(tx, ty));
                return true;
            }

            case MotionEvent.ACTION_UP: {
                float dx = e.getX() - downX, dy = e.getY() - downY;
                if (Math.abs(dx) > cellSize * 0.35f || Math.abs(dy) > cellSize * 0.35f) {
                    return true;                       // 已经当滑动处理过了
                }
                handleTap(e.getX(), e.getY());
                return true;
            }
            default:
                return super.onTouchEvent(e);
        }
    }

    private void handleTap(float x, float y) {
        if (phase != PHASE_IDLE) return;
        if (board.isCleared() || board.isFailed()) {
            if (actionBtn.contains(x, y) || true) {
                nextLevelOrRestart();
            }
            return;
        }
        if (restartBtn.contains(x, y)) {
            board.restart();
            afterBoardChanged(true);
            return;
        }
        if (actionBtn.contains(x, y)) {
            int[] move = board.hint();
            if (move != null) {
                hintMove = move;
                hintShownAt = SystemClock.uptimeMillis();
                invalidate();
            }
            return;
        }
        int cell = cellAt(x, y);
        if (cell < 0) return;
        if (selected < 0) {
            selected = cell;
        } else if (selected == cell) {
            selected = -1;
        } else if (Board.adjacent(selected, cell)) {
            attemptSwap(selected, cell);
            selected = -1;
        } else {
            selected = cell;
        }
        invalidate();
    }

    /** 尝试交换：合法才播动画并扣步数，不合法就直接换回去。 */
    private void attemptSwap(int a, int b) {
        if (a < 0 || b < 0 || !board.canSwap(a, b)) {
            swapA = a;
            swapB = b;
            board.swap(a, b);
            phase = PHASE_SWAP_BACK;
            phaseStart = SystemClock.uptimeMillis();
            invalidate();
            return;
        }
        swapA = a;
        swapB = b;
        board.swap(a, b);
        board.consumeMove();
        if (listener != null) {
            listener.onScoreChanged(board.score(), board.movesLeft());
        }
        phase = PHASE_SWAP;
        phaseStart = SystemClock.uptimeMillis();
        invalidate();
    }

    private void nextLevelOrRestart() {
        if (board.isCleared()) {
            board.newLevel(board.level() + 1);
        } else {
            board.restart();
        }
        afterBoardChanged(true);
    }

    private void afterBoardChanged(boolean notify) {
        phase = PHASE_IDLE;
        selected = -1;
        hintMove = null;
        lastInput = SystemClock.uptimeMillis();
        if (notify && listener != null) {
            listener.onScoreChanged(board.score(), board.movesLeft());
        }
        invalidate();
    }

    // ---------------------------------------------------------------- 主循环

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        long now = SystemClock.uptimeMillis();
        long elapsed = now - phaseStart;

        drawHeader(canvas);
        drawBoardBackground(canvas);

        switch (phase) {
            case PHASE_SWAP:
                drawSwap(canvas, ease(elapsed / (float) T_SWAP));
                if (elapsed >= T_SWAP) {
                    pendingClear = board.findMatches();
                    if (pendingClear.isEmpty() && (swapA >= 0 && swapB >= 0)
                            && (board.specialAt(swapA) == Board.SPECIAL_RAINBOW
                            || board.specialAt(swapB) == Board.SPECIAL_RAINBOW)) {
                        // 彩虹球和普通宝石交换：直接消掉那种颜色
                        int rainbow = board.specialAt(swapA) == Board.SPECIAL_RAINBOW ? swapA : swapB;
                        int other = rainbow == swapA ? swapB : swapA;
                        pendingClear = board.rainbowMatch(rainbow, other);
                    }
                    startClear(now);
                }
                break;

            case PHASE_SWAP_BACK:
                drawSwap(canvas, 1f - ease(elapsed / (float) T_SWAP));
                if (elapsed >= T_SWAP) {
                    board.swap(swapA, swapB);
                    phase = PHASE_IDLE;
                    swapA = swapB = -1;
                    lastInput = now;
                }
                break;

            case PHASE_CLEAR:
                drawClearing(canvas, elapsed / (float) T_CLEAR);
                if (elapsed >= T_CLEAR) {
                    Board.ClearOutcome outcome = board.clear(pendingClear, swapA, swapB);
                    lastGain = outcome.gained;
                    gainPulse = 1f;
                    lastSpawnIndex = outcome.spawnCount > 0 ? outcome.spawnIndex[0] : -1;
                    fallMoves = board.collapse();
                    fallSpawns = board.refill();
                    swapA = swapB = -1;
                    phase = PHASE_FALL;
                    phaseStart = now;
                }
                break;

            case PHASE_FALL:
                drawFalling(canvas, ease(elapsed / (float) T_FALL));
                if (elapsed >= T_FALL) {
                    Board.MatchSet next = board.findMatches();
                    if (!next.isEmpty()) {
                        pendingClear = next;
                        startClear(now);
                    } else {
                        board.endCascade();
                        phase = PHASE_IDLE;
                        lastInput = now;
                        if (board.isCleared()) {
                            if (listener != null) {
                                listener.onLevelComplete(board.level(), board.stars(), board.score());
                            }
                        } else if (board.isFailed()) {
                            if (listener != null) {
                                listener.onLevelFailed(board.level(), board.score());
                            }
                        } else if (board.ensurePlayable()) {
                            // 没有可行交换，自动打乱
                            lastInput = now;
                        }
                    }
                }
                break;

            default:
                drawSettled(canvas);
                break;
        }

        drawHint(canvas, now);
        drawOverlays(canvas);

        if (phase != PHASE_IDLE || gainPulse > 0f) {
            if (gainPulse > 0f) {
                gainPulse = Math.max(0f, gainPulse - 0.04f);
            }
            postInvalidateOnAnimation();
        }
    }

    private void startClear(long now) {
        clearCells = pendingClear.toArray();
        phase = PHASE_CLEAR;
        phaseStart = now;
    }

    private static float ease(float t) {
        if (t <= 0) return 0;
        if (t >= 1) return 1;
        return t < 0.5f ? 2 * t * t : 1 - 2 * (1 - t) * (1 - t);
    }

    // ---------------------------------------------------------------- 绘制：棋盘

    private void drawHeader(Canvas canvas) {
        float w = getWidth();
        float pad = boardLeft;
        float title = Math.min(w, getHeight()) * 0.058f;

        paint.setTypeface(Typeface.DEFAULT_BOLD);
        paint.setTextAlign(Paint.Align.LEFT);
        paint.setColor(TEXT);
        paint.setTextSize(title);
        canvas.drawText("第 " + board.level() + " 关", pad, title * 1.35f, paint);

        // 步数
        paint.setTextAlign(Paint.Align.RIGHT);
        paint.setColor(board.movesLeft() <= 5 ? 0xFFE5484D : TEXT);
        canvas.drawText(board.movesLeft() + " 步", w - pad, title * 1.35f, paint);

        // 进度条
        float barY = title * 1.7f;
        float barH = title * 0.42f;
        float barW = w - pad * 2;
        paint.setColor(PANEL);
        rect.set(pad, barY, pad + barW, barY + barH);
        canvas.drawRoundRect(rect, barH / 2, barH / 2, paint);
        float ratio = Math.min(1f, board.score() / (float) board.target());
        if (ratio > 0) {
            paint.setColor(ratio >= 1f ? GOLD : ACCENT);
            rect.set(pad, barY, pad + Math.max(barH, barW * ratio), barY + barH);
            canvas.drawRoundRect(rect, barH / 2, barH / 2, paint);
        }
        paint.setColor(TEXT);
        paint.setTextAlign(Paint.Align.LEFT);
        paint.setTextSize(title * 0.44f);
        canvas.drawText(board.score() + " / " + board.target(), pad + barH * 0.6f,
                barY + barH * 0.82f, paint);

        // 连锁提示
        if (gainPulse > 0f && lastGain > 0) {
            paint.setTextAlign(Paint.Align.RIGHT);
            paint.setColor(GOLD);
            paint.setTextSize(title * 0.5f * (1f + 0.3f * gainPulse));
            canvas.drawText("+" + lastGain, w - pad, barY + barH * 0.9f, paint);
        }

        // 按钮
        float btnH = title * 1.15f;
        float btnW = w * 0.33f;
        float btnY = boardTop - btnH - pad * 0.5f;
        drawButton(canvas, actionBtn, pad, btnY, btnW, btnH, "提示", PANEL, TEXT);
        drawButton(canvas, restartBtn, w - pad - btnW, btnY, btnW, btnH, "重玩", PANEL, TEXT);
    }

    private void drawButton(Canvas canvas, RectF out, float x, float y, float w, float h,
                            String text, int bg, int fg) {
        out.set(x, y, x + w, y + h);
        paint.setColor(bg);
        canvas.drawRoundRect(out, h * 0.3f, h * 0.3f, paint);
        paint.setTextAlign(Paint.Align.CENTER);
        paint.setTypeface(Typeface.DEFAULT_BOLD);
        paint.setColor(fg);
        paint.setTextSize(h * 0.46f);
        canvas.drawText(text, x + w / 2, y + h * 0.68f, paint);
    }

    private void drawBoardBackground(Canvas canvas) {
        paint.setColor(BOARD_BG);
        rect.set(boardLeft, boardTop, boardLeft + boardSize, boardTop + boardSize);
        canvas.drawRoundRect(rect, boardSize * 0.035f, boardSize * 0.035f, paint);

        paint.setColor(CELL_BG);
        float r = cellSize * 0.2f;
        for (int y = 0; y < Board.SIZE; y++) {
            for (int x = 0; x < Board.SIZE; x++) {
                rect.set(cellLeft(x), cellTop(y), cellLeft(x) + cellSize, cellTop(y) + cellSize);
                canvas.drawRoundRect(rect, r, r, paint);
            }
        }
    }

    /** 静止状态：把棋盘上所有宝石按格子画出来。 */
    private void drawSettled(Canvas canvas) {
        for (int i = 0; i < Board.SIZE * Board.SIZE; i++) {
            drawGem(canvas, centerX(i), centerY(i), cellSize, i, 1f);
        }
        if (selected >= 0) {
            drawSelection(canvas, selected);
        }
    }

    /** 交换中的两格：一块从 A 滑向 B，另一块反过来。 */
    private void drawSwap(Canvas canvas, float t) {
        for (int i = 0; i < Board.SIZE * Board.SIZE; i++) {
            if (i == swapA || i == swapB) continue;
            drawGem(canvas, centerX(i), centerY(i), cellSize, i, 1f);
        }
        float ax = centerX(swapA), ay = centerY(swapA);
        float bx = centerX(swapB), by = centerY(swapB);
        drawGemAt(canvas, ax + (bx - ax) * t, ay + (by - ay) * t, cellSize, swapA, 1.06f);
        drawGemAt(canvas, bx + (ax - bx) * t, by + (ay - by) * t, cellSize, swapB, 1.06f);
    }

    /** 消除中：被消掉的宝石缩小并淡出，其余正常。 */
    private void drawClearing(Canvas canvas, float t) {
        float scale = Math.max(0f, 1f - t);
        for (int i = 0; i < Board.SIZE * Board.SIZE; i++) {
            if (isClearing(i)) continue;
            drawGem(canvas, centerX(i), centerY(i), cellSize, i, 1f);
        }
        for (int i : clearCells) {
            drawGem(canvas, centerX(i), centerY(i), cellSize, i, 1f + 0.35f * t);
        }
        // 光晕
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(cellSize * 0.08f * (1f - t));
        paint.setColor(0x66FFFFFF);
        for (int i : clearCells) {
            float r = cellSize * (0.4f + 0.5f * t);
            canvas.drawCircle(centerX(i), centerY(i), r, paint);
        }
        paint.setStyle(Paint.Style.FILL);
    }

    private boolean isClearing(int index) {
        for (int i : clearCells) {
            if (i == index) return true;
        }
        return false;
    }

    /** 下落中：老宝石从 from 滑到 to，新宝石从上方掉进来。 */
    private void drawFalling(Canvas canvas, float t) {
        boolean[] moving = new boolean[Board.SIZE * Board.SIZE];
        for (int[] mv : fallMoves) {
            moving[mv[0]] = true;
            moving[mv[1]] = true;
        }
        for (int[] sp : fallSpawns) {
            moving[sp[0]] = true;
        }
        for (int i = 0; i < Board.SIZE * Board.SIZE; i++) {
            if (moving[i]) continue;
            drawGem(canvas, centerX(i), centerY(i), cellSize, i, 1f);
        }
        for (int[] mv : fallMoves) {
            float fx = centerX(mv[0]), fy = centerY(mv[0]);
            float tx = centerX(mv[1]), ty = centerY(mv[1]);
            drawGemAt(canvas, fx + (tx - fx) * t, fy + (ty - fy) * t, cellSize, mv[1], 1f);
        }
        for (int[] sp : fallSpawns) {
            float ty = centerY(sp[0]);
            float fy = ty - sp[1] * (cellSize + gap);
            drawGemAt(canvas, centerX(sp[0]), fy + (ty - fy) * t, cellSize, sp[0], 1f);
        }
    }

    // ---------------------------------------------------------------- 绘制：宝石

    private void drawSelection(Canvas canvas, int index) {
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(cellSize * 0.07f);
        paint.setColor(0xCCFFFFFF);
        rect.set(cellLeft(Board.xOf(index)) - gap * 0.3f, cellTop(Board.yOf(index)) - gap * 0.3f,
                cellLeft(Board.xOf(index)) + cellSize + gap * 0.3f,
                cellTop(Board.yOf(index)) + cellSize + gap * 0.3f);
        canvas.drawRoundRect(rect, cellSize * 0.24f, cellSize * 0.24f, paint);
        paint.setStyle(Paint.Style.FILL);
    }

    private void drawHint(Canvas canvas, long now) {
        if (phase != PHASE_IDLE || board.isCleared() || board.isFailed()) return;
        if (hintMove == null && now - lastInput > HINT_DELAY) {
            hintMove = board.hint();
            hintShownAt = now;
        }
        if (hintMove == null) return;
        float pulse = 0.5f + 0.5f * (float) Math.sin((now - hintShownAt) / 220.0);
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(cellSize * 0.06f);
        paint.setColor(Color.argb((int) (90 + 120 * pulse), 255, 255, 255));
        for (int i : hintMove) {
            float l = cellLeft(Board.xOf(i)), t = cellTop(Board.yOf(i));
            rect.set(l, t, l + cellSize, t + cellSize);
            canvas.drawRoundRect(rect, cellSize * 0.22f, cellSize * 0.22f, paint);
        }
        paint.setStyle(Paint.Style.FILL);
    }

    private void drawGem(Canvas canvas, float cx, float cy, float size, int index, float scale) {
        drawGemAt(canvas, cx, cy, size, index, scale);
    }

    private void drawGemAt(Canvas canvas, float cx, float cy, float size, int index, float scale) {
        int type = board.typeAt(index);
        if (type == Board.EMPTY) return;
        int special = board.specialAt(index);
        float s = size * scale;
        float left = cx - s / 2f, top = cy - s / 2f;
        float r = s * 0.22f;

        if (special == Board.SPECIAL_RAINBOW) {
            // 彩虹球：多彩光圈
            paint.setShader(new LinearGradient(left, top, left + s, top + s,
                    new int[]{0xFFE5484D, 0xFFF5A524, 0xFF3FBF7F, 0xFF3F8CFF, 0xFFB26FF0},
                    null, Shader.TileMode.CLAMP));
            rect.set(left, top, left + s, top + s);
            canvas.drawRoundRect(rect, r, r, paint);
            paint.setShader(null);
            paint.setColor(0xFFFFFFFF);
            canvas.drawCircle(cx, cy, s * 0.16f, paint);
            return;
        }

        int base = (type >= 0 && type < GEM_COLOR.length) ? GEM_COLOR[type] : GEM_COLOR[0];
        paint.setShader(new LinearGradient(left, top, left, top + s,
                lighten(base), GEM_DARK[type], Shader.TileMode.CLAMP));
        rect.set(left, top, left + s, top + s);
        canvas.drawRoundRect(rect, r, r, paint);
        paint.setShader(null);

        // 内部形状：每种颜色一个形状，色盲也能区分
        paint.setColor(0x33FFFFFF);
        drawShape(canvas, type, cx, cy, s * 0.34f);

        // 道具标记
        if (special == Board.SPECIAL_LINE_H) {
            paint.setColor(0xFFFFFFFF);
            rect.set(left + s * 0.12f, cy - s * 0.06f, left + s * 0.88f, cy + s * 0.06f);
            canvas.drawRoundRect(rect, s * 0.03f, s * 0.03f, paint);
        } else if (special == Board.SPECIAL_LINE_V) {
            paint.setColor(0xFFFFFFFF);
            rect.set(cx - s * 0.06f, top + s * 0.12f, cx + s * 0.06f, top + s * 0.88f);
            canvas.drawRoundRect(rect, s * 0.03f, s * 0.03f, paint);
        } else if (special == Board.SPECIAL_BOMB) {
            paint.setStyle(Paint.Style.STROKE);
            paint.setStrokeWidth(s * 0.07f);
            paint.setColor(0xFFFFFFFF);
            canvas.drawCircle(cx, cy, s * 0.30f, paint);
            canvas.drawCircle(cx, cy, s * 0.16f, paint);
            paint.setStyle(Paint.Style.FILL);
        }
    }

    private static int lighten(int color) {
        int r = Math.min(255, (int) (Color.red(color) * 1.35f));
        int g = Math.min(255, (int) (Color.green(color) * 1.35f));
        int b = Math.min(255, (int) (Color.blue(color) * 1.35f));
        return Color.rgb(r, g, b);
    }

    private void drawShape(Canvas canvas, int type, float cx, float cy, float radius) {
        path.reset();
        switch (type) {
            case 0:
                canvas.drawCircle(cx, cy, radius, paint);
                return;
            case 1:
                path.moveTo(cx, cy - radius);
                path.lineTo(cx + radius, cy);
                path.lineTo(cx, cy + radius);
                path.lineTo(cx - radius, cy);
                path.close();
                break;
            case 2:
                rect.set(cx - radius, cy - radius, cx + radius, cy + radius);
                canvas.drawRoundRect(rect, radius * 0.3f, radius * 0.3f, paint);
                return;
            case 3:
                path.moveTo(cx, cy - radius * 1.1f);
                path.lineTo(cx + radius, cy + radius * 0.8f);
                path.lineTo(cx - radius, cy + radius * 0.8f);
                path.close();
                break;
            case 4:
                for (int i = 0; i < 6; i++) {
                    double angle = Math.PI / 3 * i - Math.PI / 2;
                    float px = cx + (float) Math.cos(angle) * radius;
                    float py = cy + (float) Math.sin(angle) * radius;
                    if (i == 0) path.moveTo(px, py);
                    else path.lineTo(px, py);
                }
                path.close();
                break;
            default:
                for (int i = 0; i < 10; i++) {
                    double angle = Math.PI / 5 * i - Math.PI / 2;
                    float rr = (i % 2 == 0) ? radius : radius * 0.46f;
                    float px = cx + (float) Math.cos(angle) * rr;
                    float py = cy + (float) Math.sin(angle) * rr;
                    if (i == 0) path.moveTo(px, py);
                    else path.lineTo(px, py);
                }
                path.close();
                break;
        }
        canvas.drawPath(path, paint);
    }

    // ---------------------------------------------------------------- 覆盖层

    private void drawOverlays(Canvas canvas) {
        if (board.isCleared()) {
            drawEndOverlay(canvas, true);
        } else if (board.isFailed()) {
            drawEndOverlay(canvas, false);
        }
    }

    private void drawEndOverlay(Canvas canvas, boolean win) {
        float w = getWidth(), h = getHeight();
        paint.setColor(0xE60D1017);
        canvas.drawRect(0, 0, w, h, paint);

        paint.setTextAlign(Paint.Align.CENTER);
        paint.setTypeface(Typeface.DEFAULT_BOLD);
        paint.setColor(win ? GOLD : 0xFFE5484D);
        paint.setTextSize(w * 0.085f);
        canvas.drawText(win ? "过关！" : "步数用完了", w / 2f, h * 0.36f, paint);

        paint.setTypeface(Typeface.DEFAULT);
        paint.setColor(TEXT);
        paint.setTextSize(w * 0.045f);
        canvas.drawText("得分 " + board.score() + " / 目标 " + board.target(),
                w / 2f, h * 0.42f, paint);

        if (win) {
            drawStars(canvas, w / 2f, h * 0.50f, w * 0.075f, board.stars());
        }

        float bw = w * 0.44f, bh = w * 0.13f;
        float by = h * 0.58f;
        drawButton(canvas, actionBtn, w / 2f - bw / 2f, by, bw, bh,
                win ? "下一关" : "重玩本关", win ? ACCENT : PANEL, TEXT);
    }

    private void drawStars(Canvas canvas, float cx, float cy, float radius, int earned) {
        for (int i = 0; i < 3; i++) {
            float x = cx + (i - 1) * radius * 2.6f;
            paint.setColor(i < earned ? GOLD : 0xFF2A3342);
            path.reset();
            for (int k = 0; k < 10; k++) {
                double angle = Math.PI / 5 * k - Math.PI / 2;
                float rr = (k % 2 == 0) ? radius : radius * 0.46f;
                float px = x + (float) Math.cos(angle) * rr;
                float py = cy + (float) Math.sin(angle) * rr;
                if (k == 0) path.moveTo(px, py);
                else path.lineTo(px, py);
            }
            path.close();
            canvas.drawPath(path, paint);
        }
    }
}
