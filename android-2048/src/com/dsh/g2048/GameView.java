package com.dsh.g2048;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.os.SystemClock;
import android.view.MotionEvent;
import android.view.View;

import java.util.ArrayList;
import java.util.List;

/**
 * 2048 的棋盘视图：全部用 Canvas 手绘（没有布局 XML、没有图片资源、不依赖 AndroidX）。
 *
 * <p>动画分两段：先让方块滑到目标格（{@link #SLIDE_MS}），再让合并/新生的方块弹一下
 * （{@link #POP_MS}）。滑动期间目标格先不画，靠滑动中的"精灵"落位，避免出现重影。
 */
public class GameView extends View {

    public interface Listener {
        void onScoreChanged(int score, int best);

        void onNewBest(int best);
    }

    private static final long SLIDE_MS = 110;
    private static final long POP_MS = 90;

    private static final int BG = 0xFF0D1017;
    private static final int BOARD_BG = 0xFF1A2029;
    private static final int EMPTY_CELL = 0xFF232B36;
    private static final int TEXT_DARK = 0xFF776E65;
    private static final int TEXT_LIGHT = 0xFFF9F6F2;
    private static final int PANEL = 0xFF1B2431;
    private static final int ACCENT = 0xFF3F8CFF;
    private static final int MUTED = 0xFF7D8798;

    private static final int[] TILE_VALUE = {
            0, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048
    };
    private static final int[] TILE_COLOR = {
            0xFFBDAC97, 0xFFEEE4DA, 0xFFEDE0C8, 0xFFF2B179, 0xFFF59563, 0xFFF67C5F,
            0xFFF65E3B, 0xFFEDCF72, 0xFFEDCC61, 0xFFEDC850, 0xFFEDC53F, 0xFFEDC22E
    };
    private static final int TILE_BIG = 0xFF3C3A32;

    private final Game game;
    private final Listener listener;
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF rect = new RectF();

    private int bestScore;
    private boolean newBestShown;

    // 动画状态
    private long animStart;
    private List<Game.Motion> motions = new ArrayList<Game.Motion>();
    private int spawnX = -1, spawnY = -1;
    private final boolean[] popCells = new boolean[16];

    // 触摸
    private float downX, downY;

    // 布局（每次 onSizeChanged 重算）
    private float boardLeft, boardTop, boardSize, cellSize, gap;
    private final RectF undoBtn = new RectF();
    private final RectF newBtn = new RectF();
    private final RectF continueBtn = new RectF();
    private final RectF restartBtn = new RectF();

    public GameView(Context context, Game game, int bestScore, Listener listener) {
        super(context);
        this.game = game;
        this.bestScore = bestScore;
        this.listener = listener;
        setBackgroundColor(BG);
        setFocusable(true);
    }

    public void setBestScore(int best) {
        bestScore = best;
    }

    // ---------------------------------------------------------------- 尺寸

    @Override
    protected void onSizeChanged(int w, int h, int oldw, int oldh) {
        super.onSizeChanged(w, h, oldw, oldh);
        float pad = w * 0.045f;
        float headerH = h * 0.20f;
        boardLeft = pad;
        boardTop = headerH;
        boardSize = Math.min(w - pad * 2, h - headerH - pad * 2.2f);
        gap = boardSize * 0.030f;
        cellSize = (boardSize - gap * 5) / 4f;
    }

    private float cellLeft(int x) {
        return boardLeft + gap + x * (cellSize + gap);
    }

    private float cellTop(int y) {
        return boardTop + gap + y * (cellSize + gap);
    }

    // ---------------------------------------------------------------- 交互

    @Override
    public boolean onTouchEvent(MotionEvent e) {
        switch (e.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                downX = e.getX();
                downY = e.getY();
                return true;
            case MotionEvent.ACTION_UP:
                handleTap(e.getX(), e.getY());
                return true;
            default:
                break;
        }
        return super.onTouchEvent(e);
    }

    private void handleTap(float x, float y) {
        // 结算界面：直接点按钮
        if (game.isOver()) {
            if (restartBtn.contains(x, y) || true) {   // 结束后点哪里都重开
                newGame();
            }
            return;
        }
        if (game.hasWon() && !game.isKeepPlaying()) {
            if (continueBtn.contains(x, y)) {
                game.keepPlaying();
                invalidate();
                return;
            }
            if (restartBtn.contains(x, y)) {
                newGame();
                return;
            }
            return;
        }
        if (undoBtn.contains(x, y)) {
            if (game.undo()) {
                animStart = 0;
                notifyScore();
                invalidate();
            }
            return;
        }
        if (newBtn.contains(x, y)) {
            newGame();
            return;
        }
        // 滑动判定
        float dx = x - downX, dy = y - downY;
        float threshold = Math.max(24f, boardSize * 0.06f);
        if (Math.abs(dx) < threshold && Math.abs(dy) < threshold) {
            return;                                   // 点击棋盘不做事
        }
        Game.Dir dir;
        if (Math.abs(dx) > Math.abs(dy)) {
            dir = dx > 0 ? Game.Dir.RIGHT : Game.Dir.LEFT;
        } else {
            dir = dy > 0 ? Game.Dir.DOWN : Game.Dir.UP;
        }
        Game.Result r = game.move(dir);
        if (r.moved) {
            startAnimation(r);
        }
        invalidate();
    }

    /** 外部（Activity 恢复局面后）调用，刷新分数显示。 */
    public void notifyScore() {
        if (listener != null) {
            listener.onScoreChanged(game.score(), bestScore);
        }
        if (game.score() > bestScore) {
            bestScore = game.score();
            if (listener != null) {
                listener.onNewBest(bestScore);
            }
        }
    }

    private void newGame() {
        game.reset();
        animStart = 0;
        newBestShown = false;
        notifyScore();
        invalidate();
    }

    private void startAnimation(Game.Result r) {
        motions = r.motions;
        spawnX = r.spawnedX;
        spawnY = r.spawnedY;
        for (int i = 0; i < popCells.length; i++) {
            popCells[i] = false;
        }
        for (Game.Motion m : motions) {
            if (m.mergeInto) {
                popCells[m.toY * Game.SIZE + m.toX] = true;
            }
        }
        animStart = SystemClock.uptimeMillis();
        notifyScore();
    }

    // ---------------------------------------------------------------- 绘制

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        drawHeader(canvas);
        drawBoard(canvas);
        drawTiles(canvas);
        if (game.isOver()) {
            drawOverlay(canvas, "无路可走", "得分 " + game.score(), "点任意处再来一局");
        } else if (game.hasWon() && !game.isKeepPlaying()) {
            drawWinOverlay(canvas);
        }
        if (animStart != 0) {
            long elapsed = SystemClock.uptimeMillis() - animStart;
            if (elapsed < SLIDE_MS + POP_MS) {
                postInvalidateOnAnimation();
            } else {
                animStart = 0;
            }
        }
    }

    private void drawHeader(Canvas canvas) {
        float w = getWidth();
        float pad = boardLeft;
        float titleSize = Math.min(w, getHeight()) * 0.075f;

        paint.setTypeface(Typeface.DEFAULT_BOLD);
        paint.setColor(TEXT_LIGHT);
        paint.setTextSize(titleSize);
        paint.setTextAlign(Paint.Align.LEFT);
        canvas.drawText("2048", pad, titleSize * 1.5f, paint);

        paint.setTypeface(Typeface.DEFAULT);
        paint.setTextSize(titleSize * 0.30f);
        paint.setColor(MUTED);
        canvas.drawText("滑动合并相同数字", pad, titleSize * 2.05f, paint);

        // 分数框
        float boxW = w * 0.20f, boxH = titleSize * 1.45f;
        float right = w - pad;
        drawScoreBox(canvas, right - boxW, pad * 0.6f, boxW, boxH, "分数", game.score());
        drawScoreBox(canvas, right - boxW * 2 - pad * 0.5f, pad * 0.6f, boxW, boxH,
                "最高", bestScore);

        // 按钮
        float btnH = titleSize * 1.25f, btnW = w * 0.26f;
        float btnY = boardTop - btnH - pad * 0.7f;
        drawButton(canvas, undoBtn, pad, btnY, btnW, btnH, "撤销",
                game.canUndo() ? PANEL : 0xFF141A24, game.canUndo() ? TEXT_LIGHT : 0xFF4A5364);
        drawButton(canvas, newBtn, pad + btnW + pad * 0.5f, btnY, btnW, btnH, "新游戏",
                ACCENT, 0xFFFFFFFF);
    }

    private void drawScoreBox(Canvas canvas, float x, float y, float w, float h,
                              String label, int value) {
        paint.setColor(PANEL);
        rect.set(x, y, x + w, y + h);
        canvas.drawRoundRect(rect, h * 0.22f, h * 0.22f, paint);

        paint.setTextAlign(Paint.Align.CENTER);
        paint.setTypeface(Typeface.DEFAULT);
        paint.setColor(MUTED);
        paint.setTextSize(h * 0.28f);
        canvas.drawText(label, x + w / 2, y + h * 0.36f, paint);

        paint.setTypeface(Typeface.DEFAULT_BOLD);
        paint.setColor(TEXT_LIGHT);
        paint.setTextSize(h * 0.42f);
        canvas.drawText(String.valueOf(value), x + w / 2, y + h * 0.82f, paint);
    }

    private void drawButton(Canvas canvas, RectF out, float x, float y, float w, float h,
                            String text, int bg, int fg) {
        out.set(x, y, x + w, y + h);
        paint.setColor(bg);
        canvas.drawRoundRect(out, h * 0.28f, h * 0.28f, paint);
        paint.setTextAlign(Paint.Align.CENTER);
        paint.setTypeface(Typeface.DEFAULT_BOLD);
        paint.setColor(fg);
        paint.setTextSize(h * 0.44f);
        canvas.drawText(text, x + w / 2, y + h * 0.68f, paint);
    }

    private void drawBoard(Canvas canvas) {
        paint.setColor(BOARD_BG);
        rect.set(boardLeft, boardTop, boardLeft + boardSize, boardTop + boardSize);
        canvas.drawRoundRect(rect, boardSize * 0.03f, boardSize * 0.03f, paint);

        paint.setColor(EMPTY_CELL);
        float r = cellSize * 0.12f;
        for (int y = 0; y < Game.SIZE; y++) {
            for (int x = 0; x < Game.SIZE; x++) {
                rect.set(cellLeft(x), cellTop(y), cellLeft(x) + cellSize, cellTop(y) + cellSize);
                canvas.drawRoundRect(rect, r, r, paint);
            }
        }
    }

    private void drawTiles(Canvas canvas) {
        long now = SystemClock.uptimeMillis();
        long elapsed = animStart == 0 ? Long.MAX_VALUE : now - animStart;

        if (elapsed < SLIDE_MS) {
            float t = ease(elapsed / (float) SLIDE_MS);
            boolean[] hidden = new boolean[16];
            for (Game.Motion m : motions) {
                hidden[m.toY * Game.SIZE + m.toX] = true;
            }
            if (spawnX >= 0) {
                hidden[spawnY * Game.SIZE + spawnX] = true;
            }
            for (int y = 0; y < Game.SIZE; y++) {
                for (int x = 0; x < Game.SIZE; x++) {
                    if (hidden[y * Game.SIZE + x]) continue;
                    int v = game.get(x, y);
                    if (v != 0) drawTile(canvas, x, y, v, 1f);
                }
            }
            for (Game.Motion m : motions) {
                float fx = m.fromX + (m.toX - m.fromX) * t;
                float fy = m.fromY + (m.toY - m.fromY) * t;
                drawTileAt(canvas, fx, fy, m.value, 1f);
            }
            if (spawnX >= 0) {
                drawTile(canvas, spawnX, spawnY, game.get(spawnX, spawnY), 0.35f + 0.65f * t);
            }
            return;
        }

        float popT = -1f;
        if (elapsed < SLIDE_MS + POP_MS) {
            popT = (elapsed - SLIDE_MS) / (float) POP_MS;
        }
        for (int y = 0; y < Game.SIZE; y++) {
            for (int x = 0; x < Game.SIZE; x++) {
                int v = game.get(x, y);
                if (v == 0) continue;
                float scale = 1f;
                if (popT >= 0 && popCells[y * Game.SIZE + x]) {
                    scale = 1f + 0.16f * (float) Math.sin(Math.PI * popT);
                }
                drawTile(canvas, x, y, v, scale);
            }
        }
    }

    private static float ease(float t) {
        return t < 0.5f ? 2f * t * t : 1f - 2f * (1f - t) * (1f - t);
    }

    private void drawTile(Canvas canvas, int x, int y, int value, float scale) {
        drawTileAt(canvas, x, y, value, scale);
    }

    private void drawTileAt(Canvas canvas, float gx, float gy, int value, float scale) {
        float left = cellLeft(0) + gx * (cellSize + gap);
        float top = cellTop(0) + gy * (cellSize + gap);
        float size = cellSize * scale;
        float cx = left + cellSize / 2f, cy = top + cellSize / 2f;
        float l = cx - size / 2f, t = cy - size / 2f;

        paint.setColor(tileColor(value));
        float r = size * 0.12f;
        rect.set(l, t, l + size, t + size);
        canvas.drawRoundRect(rect, r, r, paint);

        String text = String.valueOf(value);
        float textSize = size * (value >= 1024 ? 0.30f : value >= 128 ? 0.36f : 0.44f);
        paint.setTypeface(Typeface.DEFAULT_BOLD);
        paint.setTextSize(textSize);
        paint.setTextAlign(Paint.Align.CENTER);
        paint.setColor(value <= 4 ? TEXT_DARK : TEXT_LIGHT);
        Paint.FontMetrics fm = paint.getFontMetrics();
        canvas.drawText(text, cx, cy - (fm.ascent + fm.descent) / 2f, paint);
    }

    private static int tileColor(int value) {
        for (int i = 0; i < TILE_VALUE.length; i++) {
            if (TILE_VALUE[i] == value) return TILE_COLOR[i];
        }
        return TILE_BIG;
    }

    private void drawOverlay(Canvas canvas, String title, String sub, String hint) {
        paint.setColor(0xE60D1017);
        canvas.drawRect(0, 0, getWidth(), getHeight(), paint);

        paint.setTextAlign(Paint.Align.CENTER);
        paint.setTypeface(Typeface.DEFAULT_BOLD);
        paint.setColor(TEXT_LIGHT);
        paint.setTextSize(getWidth() * 0.085f);
        canvas.drawText(title, getWidth() / 2f, getHeight() * 0.40f, paint);

        paint.setTypeface(Typeface.DEFAULT);
        paint.setColor(ACCENT);
        paint.setTextSize(getWidth() * 0.045f);
        canvas.drawText(sub, getWidth() / 2f, getHeight() * 0.47f, paint);

        paint.setColor(MUTED);
        paint.setTextSize(getWidth() * 0.038f);
        canvas.drawText(hint, getWidth() / 2f, getHeight() * 0.54f, paint);

        float bw = getWidth() * 0.34f, bh = getWidth() * 0.12f;
        float by = getHeight() * 0.60f;
        drawButton(canvas, restartBtn, getWidth() / 2f - bw / 2f, by, bw, bh, "再来一局",
                ACCENT, 0xFFFFFFFF);
    }

    private void drawWinOverlay(Canvas canvas) {
        paint.setColor(0xCC0D1017);
        canvas.drawRect(0, 0, getWidth(), getHeight(), paint);

        paint.setTextAlign(Paint.Align.CENTER);
        paint.setTypeface(Typeface.DEFAULT_BOLD);
        paint.setColor(0xFFEDC22E);
        paint.setTextSize(getWidth() * 0.085f);
        canvas.drawText("达成 2048！", getWidth() / 2f, getHeight() * 0.38f, paint);

        paint.setTypeface(Typeface.DEFAULT);
        paint.setColor(MUTED);
        paint.setTextSize(getWidth() * 0.038f);
        canvas.drawText("还能继续冲更高分", getWidth() / 2f, getHeight() * 0.44f, paint);

        float bw = getWidth() * 0.32f, bh = getWidth() * 0.115f;
        float by = getHeight() * 0.50f;
        drawButton(canvas, continueBtn, getWidth() / 2f - bw - getWidth() * 0.015f, by,
                bw, bh, "继续玩", ACCENT, 0xFFFFFFFF);
        drawButton(canvas, restartBtn, getWidth() / 2f + getWidth() * 0.015f, by,
                bw, bh, "重开", PANEL, TEXT_LIGHT);
    }
}
