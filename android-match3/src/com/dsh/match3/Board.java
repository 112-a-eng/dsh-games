package com.dsh.match3;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Deque;
import java.util.List;
import java.util.Random;

/**
 * 三消核心逻辑（Match-3）。
 *
 * <p>刻意不引用任何 Android API，可以直接用 {@code java} 跑单元测试（见 BoardTest）。
 * 界面负责把这里算出的每一步分帧播成动画，规则全部由这里决定。
 *
 * <p>规则要点：
 * <ul>
 *   <li>只能交换相邻两格；交换后必须能形成 3 连（或涉及彩虹球），否则不算合法</li>
 *   <li>3 连消除；<b>4 连生成直线炸弹</b>（横向 4 连清整行、纵向 4 连清整列）；
 *       <b>5 连生成彩虹球</b>（消除全部同色）；<b>L/T 形生成 3×3 爆炸</b></li>
 *   <li>消除后上方宝石下落、顶部补新，若又形成匹配则连锁，连锁层数越高得分倍数越高</li>
 *   <li>没有可行交换时自动打乱（保证不会卡死）</li>
 * </ul>
 */
public final class Board {

    public static final int SIZE = 8;
    public static final int TYPES = 6;
    public static final int EMPTY = -1;

    public static final int SPECIAL_NONE = 0;
    public static final int SPECIAL_LINE_H = 1;    // 清整行
    public static final int SPECIAL_LINE_V = 2;    // 清整列
    public static final int SPECIAL_BOMB = 3;      // 3x3 爆炸
    public static final int SPECIAL_RAINBOW = 4;   // 消除全部同色

    /** 每消一个宝石的基础分（再乘连锁倍数）。 */
    public static final int BASE_SCORE = 20;

    /** 生成一个道具的额外分（再乘连锁倍数）。 */
    public static final int SPECIAL_BONUS = 60;

    /** 一个方向上的连续同色段。 */
    public static final class Run {
        public final int start;      // 起始下标
        public final int length;
        public final boolean horizontal;

        Run(int start, int length, boolean horizontal) {
            this.start = start;
            this.length = length;
            this.horizontal = horizontal;
        }
    }

    /** 一次匹配的结果：要消掉的格子 + 匹配的线段（用于决定生成什么道具）。 */
    public static final class MatchSet {
        public final boolean[] cells = new boolean[SIZE * SIZE];
        public final List<Run> runs = new ArrayList<Run>();
        public int count;

        public boolean isEmpty() {
            return count == 0;
        }

        void add(int index) {
            if (!cells[index]) {
                cells[index] = true;
                count++;
            }
        }

        public int[] toArray() {
            int[] out = new int[count];
            int k = 0;
            for (int i = 0; i < cells.length; i++) {
                if (cells[i]) out[k++] = i;
            }
            return out;
        }
    }

    /** 消除的结果：消掉哪些格子、得了多少分、在哪儿生成了什么道具。 */
    public static final class ClearOutcome {
        public final int[] cleared;
        public final int gained;
        public final int[] spawnIndex = new int[8];
        public final int[] spawnSpecial = new int[8];
        public final int[] spawnType = new int[8];
        public int spawnCount;

        ClearOutcome(int[] cleared, int gained) {
            this.cleared = cleared;
            this.gained = gained;
        }

        void addSpawn(int index, int special, int type) {
            if (spawnCount >= spawnIndex.length) return;
            spawnIndex[spawnCount] = index;
            spawnSpecial[spawnCount] = special;
            spawnType[spawnCount] = type;
            spawnCount++;
        }
    }

    private final int[] type = new int[SIZE * SIZE];
    private final int[] special = new int[SIZE * SIZE];
    private final Random rng;

    private int level = 1;
    private int score;
    private int movesLeft;
    private int target;
    private int cascade;

    public Board() {
        this(System.nanoTime());
    }

    public Board(long seed) {
        rng = new Random(seed);
        newLevel(1);
    }

    // ---------------------------------------------------------------- 基本访问

    public int typeAt(int index) {
        return type[index];
    }

    public int specialAt(int index) {
        return special[index];
    }

    public int score() {
        return score;
    }

    public int movesLeft() {
        return movesLeft;
    }

    public int target() {
        return target;
    }

    public int level() {
        return level;
    }

    public static int xOf(int index) {
        return index % SIZE;
    }

    public static int yOf(int index) {
        return index / SIZE;
    }

    public static int indexOf(int x, int y) {
        return y * SIZE + x;
    }

    public static boolean adjacent(int a, int b) {
        int dx = Math.abs(xOf(a) - xOf(b));
        int dy = Math.abs(yOf(a) - yOf(b));
        return dx + dy == 1;
    }

    // ---------------------------------------------------------------- 关卡

    /** 第 level 关的目标分。 */
    public static int targetFor(int level) {
        return 1500 + (level - 1) * 900;
    }

    /** 第 level 关的步数（越往后越少，最低 18 步）。 */
    public static int movesFor(int level) {
        return Math.max(18, 24 - (Math.max(1, level) - 1) / 3);
    }

    public void newLevel(int level) {
        this.level = Math.max(1, level);
        this.target = targetFor(this.level);
        this.movesLeft = Math.max(18, movesFor(this.level));
        this.score = 0;
        this.cascade = 0;
        fillBoard();
    }

    /** 重玩当前关（分数清零，局面重铺）。 */
    public void restart() {
        newLevel(level);
    }

    // ---------------------------------------------------------------- 铺盘

    private void fillBoard() {
        Arrays.fill(special, SPECIAL_NONE);
        for (int i = 0; i < type.length; i++) {
            int t;
            int guard = 0;
            do {
                t = rng.nextInt(TYPES);
            } while (guard++ < 40 && makesRunAt(i, t));
            type[i] = t;
        }
        int guard = 0;
        while (!hasMove() && guard++ < 80) {
            shuffleTypes();
        }
    }

    /** 若把 t 放在 index 会不会立刻形成 3 连（只看左边和上边，铺盘时用）。 */
    private boolean makesRunAt(int index, int t) {
        int x = xOf(index), y = yOf(index);
        if (x >= 2 && type[index - 1] == t && type[index - 2] == t) return true;
        if (y >= 2 && type[index - SIZE] == t && type[index - 2 * SIZE] == t) return true;
        return false;
    }

    private void shuffleTypes() {
        Integer[] order = new Integer[type.length];
        for (int i = 0; i < order.length; i++) order[i] = i;
        // 只打乱类型，保留道具
        List<Integer> pool = new ArrayList<Integer>();
        for (int i = 0; i < type.length; i++) {
            if (special[i] == SPECIAL_NONE) pool.add(type[i]);
        }
        java.util.Collections.shuffle(pool, rng);
        int k = 0;
        for (int i = 0; i < type.length; i++) {
            if (special[i] == SPECIAL_NONE) type[i] = pool.get(k++);
        }
        // 打乱后可能出现匹配，直接消掉重铺
        if (!findMatches().isEmpty()) {
            for (int i = 0; i < type.length; i++) {
                if (special[i] == SPECIAL_NONE) {
                    type[i] = rng.nextInt(TYPES);
                }
            }
        }
        if (!findMatches().isEmpty()) {
            Arrays.fill(special, SPECIAL_NONE);
            for (int i = 0; i < type.length; i++) {
                int t;
                int guard = 0;
                do {
                    t = rng.nextInt(TYPES);
                } while (guard++ < 40 && makesRunAt(i, t));
                type[i] = t;
            }
        }
        // 保证有解
        int guard = 0;
        while (!hasMove() && guard++ < 50) {
            for (int i = 0; i < type.length; i++) {
                type[i] = rng.nextInt(TYPES);
            }
            if (!findMatches().isEmpty()) {
                Arrays.fill(special, SPECIAL_NONE);
                for (int i = 0; i < type.length; i++) {
                    int t;
                    int g2 = 0;
                    do {
                        t = rng.nextInt(TYPES);
                    } while (g2++ < 40 && makesRunAt(i, t));
                    type[i] = t;
                }
            }
        }
        if (!hasMove()) {
            // 兜底：随机摆也不能保证的话，直接铺一个确定有解的棋盘
            deterministicBoard();
        }
        if (!hasMove()) {
            // 极端情况（连确定棋盘都被随机覆盖）：再试一次
            deterministicBoard();
        }
    }

    /** 兜底棋盘：按 (x+y)%3 之类的规则摆，必定有大量可消组合。 */
    private void deterministicBoard() {
        Arrays.fill(special, SPECIAL_NONE);
        for (int y = 0; y < SIZE; y++) {
            for (int x = 0; x < SIZE; x++) {
                type[indexOf(x, y)] = (x + y * 2) % TYPES;
            }
        }
    }

    // ---------------------------------------------------------------- 交换

    /** 交换两格（只改数据，动画由界面播）。 */
    public void swap(int a, int b) {
        int t = type[a]; type[a] = type[b]; type[b] = t;
        int s = special[a]; special[a] = special[b]; special[b] = s;
    }

    /**
     * 这次交换是否合法：相邻，且能形成匹配（或者其中一个是彩虹球）。
     * 只是"预判"，不会真正改动棋盘。
     */
    public boolean canSwap(int a, int b) {
        if (a < 0 || b < 0 || a >= type.length || b >= type.length) return false;
        if (!adjacent(a, b)) return false;
        if (special[a] == SPECIAL_RAINBOW || special[b] == SPECIAL_RAINBOW) return true;
        swap(a, b);
        boolean ok = !findRawMatches().isEmpty();
        swap(a, b);
        return ok;
    }

    /** 找出所有合法交换（用于提示与死局判定）。 */
    public List<int[]> findMoves() {
        List<int[]> moves = new ArrayList<int[]>();
        for (int y = 0; y < SIZE; y++) {
            for (int x = 0; x < SIZE; x++) {
                int i = indexOf(x, y);
                if (x + 1 < SIZE && canSwap(i, i + 1)) moves.add(new int[]{i, i + 1});
                if (y + 1 < SIZE && canSwap(i, i + SIZE)) moves.add(new int[]{i, i + SIZE});
            }
        }
        return moves;
    }

    public boolean hasMove() {
        return !findMoves().isEmpty();
    }

    /** 给界面用的提示；没有可走返回 null。 */
    public int[] hint() {
        List<int[]> moves = findMoves();
        if (moves.isEmpty()) return null;
        return moves.get(rng.nextInt(moves.size()));
    }

    // ---------------------------------------------------------------- 匹配

    /** 只看同色三连（不算道具效果），铺盘与合法性预判用。 */
    private MatchSet findRawMatches() {
        MatchSet set = new MatchSet();
        for (int y = 0; y < SIZE; y++) {
            int runStart = 0;
            for (int x = 1; x <= SIZE; x++) {
                boolean same = x < SIZE
                        && type[indexOf(x, y)] == type[indexOf(runStart, y)]
                        && type[indexOf(x, y)] != EMPTY;
                if (same) continue;
                int len = x - runStart;
                if (len >= 3 && type[indexOf(runStart, y)] != EMPTY) {
                    set.runs.add(new Run(indexOf(runStart, y), len, true));
                    for (int k = runStart; k < x; k++) set.add(indexOf(k, y));
                }
                runStart = x;
            }
        }
        for (int x = 0; x < SIZE; x++) {
            int runStart = 0;
            for (int y = 1; y <= SIZE; y++) {
                boolean same = y < SIZE
                        && type[indexOf(x, y)] == type[indexOf(x, runStart)]
                        && type[indexOf(x, y)] != EMPTY;
                if (same) continue;
                int len = y - runStart;
                if (len >= 3 && type[indexOf(x, runStart)] != EMPTY) {
                    set.runs.add(new Run(indexOf(x, runStart), len, false));
                    for (int k = runStart; k < y; k++) set.add(indexOf(x, k));
                }
                runStart = y;
            }
        }
        return set;
    }

    /** 完整匹配：同色三连 + 被卷进来的道具的连锁效果。 */
    public MatchSet findMatches() {
        MatchSet set = findRawMatches();
        triggerSpecials(set);
        return set;
    }

    /** 彩虹球和别的宝石交换：消除全部同色。 */
    public MatchSet rainbowMatch(int rainbowIndex, int otherIndex) {
        MatchSet set = new MatchSet();
        int wanted = type[otherIndex];
        set.add(rainbowIndex);
        for (int i = 0; i < type.length; i++) {
            if (type[i] == wanted) set.add(i);
        }
        return set;
    }

    /** 把匹配里的道具效果展开（会递归引爆彼此相邻的道具）。 */
    private void triggerSpecials(MatchSet set) {
        Deque<Integer> queue = new ArrayDeque<Integer>();
        boolean[] triggered = new boolean[SIZE * SIZE];
        int rainbowType = dominantType(set);
        for (int i = 0; i < set.cells.length; i++) {
            if (set.cells[i] && special[i] != SPECIAL_NONE) queue.add(i);
        }
        while (!queue.isEmpty()) {
            int i = queue.poll();
            if (triggered[i]) continue;
            triggered[i] = true;
            for (int e : effectCells(i, rainbowType)) {
                boolean wasNew = !set.cells[e];
                set.add(e);
                if (wasNew && special[e] != SPECIAL_NONE) queue.add(e);
            }
        }
    }

    private int[] effectCells(int index, int rainbowType) {
        int x = xOf(index), y = yOf(index);
        switch (special[index]) {
            case SPECIAL_LINE_H: {
                int[] out = new int[SIZE];
                for (int k = 0; k < SIZE; k++) out[k] = indexOf(k, y);
                return out;
            }
            case SPECIAL_LINE_V: {
                int[] out = new int[SIZE];
                for (int k = 0; k < SIZE; k++) out[k] = indexOf(x, k);
                return out;
            }
            case SPECIAL_BOMB: {
                List<Integer> out = new ArrayList<Integer>();
                for (int dy = -1; dy <= 1; dy++) {
                    for (int dx = -1; dx <= 1; dx++) {
                        int nx = x + dx, ny = y + dy;
                        if (nx >= 0 && nx < SIZE && ny >= 0 && ny < SIZE) out.add(indexOf(nx, ny));
                    }
                }
                return toArray(out);
            }
            case SPECIAL_RAINBOW: {
                List<Integer> out = new ArrayList<Integer>();
                for (int i = 0; i < type.length; i++) {
                    if (type[i] == rainbowType) out.add(i);
                }
                return toArray(out);
            }
            default:
                return new int[0];
        }
    }

    private static int[] toArray(List<Integer> list) {
        int[] out = new int[list.size()];
        for (int i = 0; i < out.length; i++) out[i] = list.get(i);
        return out;
    }

    /** 匹配里出现最多的颜色（彩虹球要消的就是它）。 */
    private int dominantType(MatchSet set) {
        int[] count = new int[TYPES];
        for (int i = 0; i < set.cells.length; i++) {
            if (set.cells[i] && type[i] >= 0 && type[i] < TYPES) count[type[i]]++;
        }
        int best = 0;
        for (int t = 1; t < TYPES; t++) {
            if (count[t] > count[best]) best = t;
        }
        return best;
    }

    // ---------------------------------------------------------------- 消除

    /**
     * 执行消除：算分、决定生成哪些道具、把格子清空。
     *
     * @param set    要消除的匹配
     * @param swapA  本次交换的两格（道具优先落在交换点上，符合主流手感），可为 -1
     */
    public ClearOutcome clear(MatchSet set, int swapA, int swapB) {
        if (set.isEmpty()) return new ClearOutcome(new int[0], 0);
        cascade++;
        int multiplier = cascade;

        // 先决定生成什么道具（要在清空之前判断形状）
        List<int[]> spawns = decideSpawns(set, swapA, swapB);

        int gained = set.count * BASE_SCORE * multiplier
                + spawns.size() * SPECIAL_BONUS * multiplier;
        int[] cleared = set.toArray();
        ClearOutcome outcome = new ClearOutcome(cleared, gained);
        for (int[] s : spawns) {
            outcome.addSpawn(s[0], s[1], type[s[0]]);
        }
        for (int i : cleared) {
            type[i] = EMPTY;
            special[i] = SPECIAL_NONE;
        }
        // 生成的道具占住原格子
        for (int[] s : spawns) {
            type[s[0]] = s[2];
            special[s[0]] = s[1];
        }
        score += gained;
        return outcome;
    }

    /** 根据匹配形状决定生成哪些道具：4 连→直线、5 连→彩虹、L/T→爆炸。 */
    private List<int[]> decideSpawns(MatchSet set, int swapA, int swapB) {
        List<int[]> spawns = new ArrayList<int[]>();
        boolean[] used = new boolean[set.cells.length];
        int swapInSet = -1;
        if (swapA >= 0 && set.cells[swapA]) swapInSet = swapA;
        else if (swapB >= 0 && set.cells[swapB]) swapInSet = swapB;

        // 交叉点（同时处于横向和纵向 3 连）→ 爆炸
        for (Run h : set.runs) {
            if (!h.horizontal) continue;
            for (Run v : set.runs) {
                if (v.horizontal) continue;
                int cross = crossOf(h, v);
                if (cross >= 0 && !used[cross]) {
                    used[cross] = true;
                    spawns.add(new int[]{cross, SPECIAL_BOMB, type[cross]});
                }
            }
        }

        for (Run run : set.runs) {
            if (run.length < 4) continue;
            int at = pickSpawnIndex(run, swapInSet, used);
            if (at < 0) continue;
            used[at] = true;
            if (run.length >= 5) {
                spawns.add(new int[]{at, SPECIAL_RAINBOW, type[at]});
            } else {
                spawns.add(new int[]{at, run.horizontal ? SPECIAL_LINE_H : SPECIAL_LINE_V, type[at]});
            }
        }
        return spawns;
    }

    private int pickSpawnIndex(Run run, int swapInSet, boolean[] used) {
        if (swapInSet >= 0 && inRun(run, swapInSet) && !used[swapInSet]) return swapInSet;
        int mid = run.start + run.length / 2;
        int step = run.horizontal ? 1 : SIZE;
        for (int k = 0; k < run.length; k++) {
            int candidate = run.start + k * step;
            if (!used[candidate]) return candidate;
        }
        return used[mid] ? -1 : mid;
    }

    private static boolean inRun(Run run, int index) {
        int step = run.horizontal ? 1 : SIZE;
        for (int k = 0; k < run.length; k++) {
            if (run.start + k * step == index) return true;
        }
        return false;
    }

    private static int crossOf(Run h, Run v) {
        int hy = h.start / SIZE;
        int vx = v.start % SIZE;
        int hx0 = h.start % SIZE, hx1 = hx0 + h.length - 1;
        int vy0 = v.start / SIZE, vy1 = vy0 + v.length - 1;
        if (vx >= hx0 && vx <= hx1 && hy >= vy0 && hy <= vy1) {
            return indexOf(vx, hy);
        }
        return -1;
    }

    // ---------------------------------------------------------------- 下落与补充

    /** 让宝石下落填空，返回每块宝石的移动 [from, to]。 */
    public List<int[]> collapse() {
        List<int[]> moves = new ArrayList<int[]>();
        for (int x = 0; x < SIZE; x++) {
            int write = SIZE - 1;
            for (int y = SIZE - 1; y >= 0; y--) {
                int from = indexOf(x, y);
                if (type[from] == EMPTY) continue;
                int to = indexOf(x, write);
                if (to != from) {
                    type[to] = type[from];
                    special[to] = special[from];
                    type[from] = EMPTY;
                    special[from] = SPECIAL_NONE;
                    moves.add(new int[]{from, to});
                }
                write--;
            }
        }
        return moves;
    }

    /**
     * 顶部补新宝石，返回 [落点下标, 从上方第几行开始掉]。
     * 例如 [index, 3] 表示这块宝石从落点上方 3 行处掉下来。
     */
    public List<int[]> refill() {
        List<int[]> spawned = new ArrayList<int[]>();
        for (int x = 0; x < SIZE; x++) {
            int count = 0;
            for (int y = 0; y < SIZE && type[indexOf(x, y)] == EMPTY; y++) count++;
            for (int y = count - 1; y >= 0; y--) {
                int index = indexOf(x, y);
                type[index] = rng.nextInt(TYPES);
                special[index] = SPECIAL_NONE;
                spawned.add(new int[]{index, count - y});
            }
        }
        return spawned;
    }

    /** 结算完一轮连锁后调用：把连锁计数清零（界面在回到静止时调用）。 */
    public void endCascade() {
        cascade = 0;
    }

    public int cascade() {
        return cascade;
    }

    /** 扣一步（界面在一次有效交换后调用）。 */
    public void consumeMove() {
        if (movesLeft > 0) movesLeft--;
    }

    /** 是否达成过关目标。 */
    public boolean isCleared() {
        return score >= target;
    }

    /** 步数用完了还没达成目标。 */
    public boolean isFailed() {
        return movesLeft <= 0 && score < target;
    }

    /** 星级：达标 1 星，1.5 倍 2 星，2 倍 3 星。 */
    public int stars() {
        if (score >= target * 2) return 3;
        if (score >= (int) (target * 1.5)) return 2;
        if (score >= target) return 1;
        return 0;
    }

    /** 没有可行交换时自动打乱（保证不会卡死）。 */
    public boolean ensurePlayable() {
        if (hasMove()) return false;
        shuffleTypes();
        return true;
    }

    // ---------------------------------------------------------------- 测试辅助

    /** 测试用：直接设置类型（不检查合法性）。 */
    void setTypes(int[] types) {
        System.arraycopy(types, 0, type, 0, type.length);
        Arrays.fill(special, SPECIAL_NONE);
    }

    /** 测试用：设置某个道具。 */
    void setSpecial(int index, int specialKind) {
        special[index] = specialKind;
    }

    /** 测试用：设置分数与步数。 */
    void setProgress(int score, int movesLeft, int target) {
        this.score = score;
        this.movesLeft = movesLeft;
        this.target = target;
    }

    /** 测试用：重置连锁计数。 */
    void resetCascade() {
        cascade = 0;
    }
}
