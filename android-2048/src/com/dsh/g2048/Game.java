package com.dsh.g2048;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Random;

/**
 * 2048 核心逻辑。
 *
 * <p>刻意不引用任何 Android API，因此可以直接用 {@code java} 跑单元测试（见 GameTest）。
 * 界面只负责把这里算出来的结果画出来，包括每个方块的滑动轨迹（{@link Motion}）。
 */
public final class Game {

    public static final int SIZE = 4;
    public static final int WIN_VALUE = 2048;

    public enum Dir { LEFT, RIGHT, UP, DOWN }

    /** 一个方块的一次移动，供界面做滑动动画。 */
    public static final class Motion {
        public final int value;          // 动画期间画出来的值（合并前各自的原值）
        public final int fromX, fromY;
        public final int toX, toY;
        public final boolean mergeInto;  // true 表示它滑到目标后会被合并掉

        Motion(int value, int fromX, int fromY, int toX, int toY, boolean mergeInto) {
            this.value = value;
            this.fromX = fromX;
            this.fromY = fromY;
            this.toX = toX;
            this.toY = toY;
            this.mergeInto = mergeInto;
        }
    }

    /** 一次移动的结果。 */
    public static final class Result {
        public final boolean moved;
        public final int gained;
        public final int spawnedX, spawnedY;   // 新方块位置，-1 表示没有
        public final boolean won;              // 这一步刚好凑出 2048
        public final boolean dead;             // 移动后已无路可走
        public final List<Motion> motions;

        Result(boolean moved, int gained, int spawnedX, int spawnedY,
               boolean won, boolean dead, List<Motion> motions) {
            this.moved = moved;
            this.gained = gained;
            this.spawnedX = spawnedX;
            this.spawnedY = spawnedY;
            this.won = won;
            this.dead = dead;
            this.motions = motions;
        }
    }

    private final int[] cells = new int[SIZE * SIZE];
    private final Random rng;
    private int score;
    private boolean won;
    private boolean over;
    private boolean keepPlaying;

    private int[] undoBoard;
    private int undoScore;

    public Game() {
        this(System.nanoTime());
    }

    public Game(long seed) {
        this.rng = new Random(seed);
        reset();
    }

    /** 开新局：清空棋盘，放两个方块。 */
    public void reset() {
        Arrays.fill(cells, 0);
        score = 0;
        won = false;
        over = false;
        keepPlaying = false;
        undoBoard = null;
        spawn();
        spawn();
    }

    public int get(int x, int y) {
        return cells[y * SIZE + x];
    }

    public int score() {
        return score;
    }

    public boolean isOver() {
        return over;
    }

    /** 是否已经凑出过 2048（玩家可以选择继续玩）。 */
    public boolean hasWon() {
        return won;
    }

    public void keepPlaying() {
        keepPlaying = true;
    }

    public boolean isKeepPlaying() {
        return keepPlaying;
    }

    public int emptyCount() {
        int n = 0;
        for (int v : cells) if (v == 0) n++;
        return n;
    }

    public int maxValue() {
        int m = 0;
        for (int v : cells) m = Math.max(m, v);
        return m;
    }

    public boolean canUndo() {
        return undoBoard != null;
    }

    /** 撤销上一步（只能退一步）。 */
    public boolean undo() {
        if (undoBoard == null) return false;
        System.arraycopy(undoBoard, 0, cells, 0, cells.length);
        score = undoScore;
        undoBoard = null;
        over = false;
        if (maxValue() < WIN_VALUE) won = false;
        return true;
    }

    public int[] snapshot() {
        return cells.clone();
    }

    // ---------------------------------------------------------------- 移动

    public Result move(Dir dir) {
        if (over) {
            return new Result(false, 0, -1, -1, false, true, new ArrayList<Motion>());
        }
        final int[] before = cells.clone();
        final List<Motion> motions = new ArrayList<Motion>();
        int gained = 0;

        for (int line = 0; line < SIZE; line++) {
            final int[] values = new int[SIZE];
            final int[] index = new int[SIZE];
            for (int k = 0; k < SIZE; k++) {
                // k = 0 是最靠近移动方向的那一格
                int x, y;
                switch (dir) {
                    case LEFT:  x = k;              y = line; break;
                    case RIGHT: x = SIZE - 1 - k;   y = line; break;
                    case UP:    x = line;           y = k;    break;
                    default:    x = line;           y = SIZE - 1 - k; break;
                }
                index[k] = y * SIZE + x;
                values[k] = cells[index[k]];
            }

            final int[] out = new int[SIZE];
            final int[] srcA = new int[SIZE];
            final int[] srcB = new int[SIZE];
            Arrays.fill(srcA, -1);
            Arrays.fill(srcB, -1);

            // 压缩 + 合并：必须拿"已经写出去的最后那个值"来比，
            // 直接比 values[read] 和 values[read+1] 会在中间夹着空格时漏合并
            // （例如 [64,0,64,128] 上移应得 [128,128,0,0]）。
            int write = 0;
            boolean justMerged = false;
            for (int read = 0; read < SIZE; read++) {
                final int v = values[read];
                if (v == 0) continue;
                if (write > 0 && !justMerged && out[write - 1] == v) {
                    out[write - 1] = v * 2;              // 合并到上一格
                    gained += v * 2;
                    srcB[write - 1] = index[read];
                    justMerged = true;
                } else {
                    out[write] = v;
                    srcA[write] = index[read];
                    write++;
                    justMerged = false;
                }
            }

            for (int k = 0; k < SIZE; k++) {
                final int dest = index[k];
                cells[dest] = out[k];
                if (srcA[k] >= 0 && srcA[k] != dest) {
                    motions.add(new Motion(out[k] / (srcB[k] >= 0 ? 2 : 1),
                            srcA[k] % SIZE, srcA[k] / SIZE, dest % SIZE, dest / SIZE,
                            srcB[k] >= 0));
                }
                if (srcB[k] >= 0 && srcB[k] != dest) {
                    motions.add(new Motion(out[k] / 2,
                            srcB[k] % SIZE, srcB[k] / SIZE, dest % SIZE, dest / SIZE, true));
                }
            }
        }

        final boolean moved = !Arrays.equals(before, cells);
        if (!moved) {
            return new Result(false, 0, -1, -1, false, false, motions);
        }

        undoBoard = before;
        undoScore = score;
        score += gained;

        int spawnX = -1, spawnY = -1;
        int[] spot = spawn();
        if (spot != null) {
            spawnX = spot[0];
            spawnY = spot[1];
        }

        boolean justWon = false;
        if (!won && maxValue() >= WIN_VALUE) {
            won = true;
            justWon = !keepPlaying;
        }
        over = !hasMove();
        return new Result(true, gained, spawnX, spawnY, justWon, over, motions);
    }

    /** 在随机空格放一个新方块（90% 是 2，10% 是 4），返回坐标；无空格返回 null。 */
    public int[] spawn() {
        int empty = 0;
        for (int v : cells) if (v == 0) empty++;
        if (empty == 0) return null;
        int pick = rng.nextInt(empty);
        for (int i = 0; i < cells.length; i++) {
            if (cells[i] != 0) continue;
            if (pick-- == 0) {
                cells[i] = rng.nextInt(10) == 0 ? 4 : 2;
                return new int[]{i % SIZE, i / SIZE};
            }
        }
        return null;
    }

    /** 是否还有合法的移动（有空格，或存在相邻相同）。 */
    public boolean hasMove() {
        for (int y = 0; y < SIZE; y++) {
            for (int x = 0; x < SIZE; x++) {
                int v = get(x, y);
                if (v == 0) return true;
                if (x + 1 < SIZE && get(x + 1, y) == v) return true;
                if (y + 1 < SIZE && get(x, y + 1) == v) return true;
            }
        }
        return false;
    }

    /** 测试用：直接摆一个棋盘。 */
    void setBoard(int[] board) {
        System.arraycopy(board, 0, cells, 0, cells.length);
        over = !hasMove();
    }

    /** 从存档恢复（局面 + 分数）。 */
    void restore(int[] board, int score) {
        System.arraycopy(board, 0, cells, 0, cells.length);
        this.score = Math.max(0, score);
        over = !hasMove();
        won = maxValue() >= WIN_VALUE;
        undoBoard = null;
    }
}
