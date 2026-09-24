package com.dsh.match3;

import java.util.List;
import java.util.Random;

/**
 * 三消逻辑自测（纯 Java，不需要 Android，也不需要 JUnit）。
 *
 * <pre>
 *   javac -d classes src/com/dsh/match3/Board.java src/com/dsh/match3/BoardTest.java
 *   java -cp classes com.dsh.match3.BoardTest
 * </pre>
 */
public final class BoardTest {

    private static int checks = 0;
    private static int fails = 0;

    private static void check(boolean ok, String msg) {
        checks++;
        if (!ok) {
            fails++;
            System.out.println("      [失败] " + msg);
        }
    }

    private static void section(String title) {
        System.out.printf("  %-30s", title);
        System.out.flush();
    }

    private static void done() {
        done("");
    }

    private static void done(String detail) {
        System.out.println("OK" + (detail.isEmpty() ? "" : "   " + detail));
    }

    // ------------------------------------------------------------ 工具

    /**
     * 一张"安全底"：相邻格颜色必然不同（(x+y)%2 交替），所以本身不会有任何三连。
     * 测试时往上覆盖几个格子，就能精确构造出想要的形状。
     */
    private static int[] safeBase() {
        int[] t = new int[Board.SIZE * Board.SIZE];
        for (int y = 0; y < Board.SIZE; y++) {
            for (int x = 0; x < Board.SIZE; x++) {
                t[Board.indexOf(x, y)] = ((x + y) % 2 == 0) ? 4 : 5;
            }
        }
        return t;
    }

    private static void put(int[] t, int x, int y, int value) {
        t[Board.indexOf(x, y)] = value;
    }

    private static String dump(Board b) {
        StringBuilder sb = new StringBuilder();
        for (int y = 0; y < Board.SIZE; y++) {
            sb.append("      [");
            for (int x = 0; x < Board.SIZE; x++) {
                int i = Board.indexOf(x, y);
                int v = b.typeAt(i);
                sb.append(v == Board.EMPTY ? " ." : String.format("%2d", v));
                if (b.specialAt(i) != Board.SPECIAL_NONE) sb.append('*');
                else sb.append(' ');
            }
            sb.append("]\n");
        }
        return sb.toString();
    }

    // ------------------------------------------------------------ 用例

    private static void testInitialBoard() {
        section("铺盘（无初始三连、有解）");
        for (int seed = 1; seed <= 60; seed++) {
            Board b = new Board(seed);
            check(b.findMatches().isEmpty(), "新棋盘不应自带三连（seed=" + seed + "）\n" + dump(b));
            check(b.hasMove(), "新棋盘必须有可行交换（seed=" + seed + "）\n" + dump(b));
            int nonEmpty = 0;
            for (int i = 0; i < 64; i++) {
                int v = b.typeAt(i);
                check(v >= 0 && v < Board.TYPES, "颜色应在 0..5，实际 " + v);
                if (v != Board.EMPTY) nonEmpty++;
            }
            check(nonEmpty == 64, "开局应铺满 64 格，实际 " + nonEmpty);
            check(b.score() == 0 && b.movesLeft() == Board.movesFor(1), "开局分数/步数不对");
        }
        done("60 个种子");
    }

    private static void testMatchDetection() {
        section("匹配检测");
        Board b = new Board(7);

        int[] t = safeBase();
        put(t, 0, 0, 0);
        put(t, 1, 0, 0);
        b.setTypes(t);
        check(b.findMatches().isEmpty(), "只有两连不应算匹配\n" + dump(b));

        put(t, 2, 0, 0);
        b.setTypes(t);
        Board.MatchSet set = b.findMatches();
        check(set.count == 3, "横向三连应消 3 格，实际 " + set.count);
        check(set.runs.size() == 1 && set.runs.get(0).horizontal, "应识别为一条横向线段");

        t = safeBase();
        put(t, 3, 1, 1);
        put(t, 3, 2, 1);
        put(t, 3, 3, 1);
        b.setTypes(t);
        set = b.findMatches();
        check(set.count == 3, "纵向三连应消 3 格，实际 " + set.count);
        check(set.runs.size() == 1 && !set.runs.get(0).horizontal, "应识别为一条纵向线段");

        // 十字形：横 3 + 竖 3 共享一格 → 5 格
        t = safeBase();
        put(t, 2, 2, 2);
        put(t, 1, 2, 2);
        put(t, 3, 2, 2);
        put(t, 2, 1, 2);
        put(t, 2, 3, 2);
        b.setTypes(t);
        set = b.findMatches();
        check(set.count == 5, "十字形应消 5 格，实际 " + set.count);
        check(set.runs.size() == 2, "十字形应有两条线段");
        done();
    }

    private static void testSwapRules() {
        section("交换合法性");
        Board b = new Board(11);
        int[] t = safeBase();
        put(t, 0, 0, 0);
        put(t, 1, 0, 0);
        put(t, 2, 0, 1);          // 0 0 1 ... 把 (2,0) 与 (3,0) 换一下不成匹配
        b.setTypes(t);

        check(!b.canSwap(Board.indexOf(0, 0), Board.indexOf(1, 0)),
                "交换两个同色格不应算合法（换完还是没有新匹配）");
        check(!b.canSwap(Board.indexOf(0, 0), Board.indexOf(0, 2)),
                "不相邻的格子不能交换");

        // 让 (2,0) 变成 0 就能凑成三连：把 (2,0) 与 (1,1) 换？不邻接。
        // 换个构造：0 0 _ 0 0，把 (2,0) 与 (3,0) 交换后若 (3,0) 也是 0 则成 3 连
        t = safeBase();
        put(t, 0, 0, 0);
        put(t, 1, 0, 0);
        put(t, 3, 0, 0);
        put(t, 2, 0, 3);
        b.setTypes(t);
        int a = Board.indexOf(2, 0), c = Board.indexOf(3, 0);
        check(b.canSwap(a, c), "换进来能凑成三连，应判为合法\n" + dump(b));
        b.swap(a, c);
        check(b.findMatches().count == 3, "交换后应能查到三连");
        done();
    }

    private static void testScoringAndCascade() {
        section("计分与连锁倍数");
        Board b = new Board(21);
        int[] t = safeBase();
        put(t, 0, 0, 0);
        put(t, 1, 0, 0);
        put(t, 2, 0, 0);
        b.setTypes(t);
        b.resetCascade();

        Board.MatchSet set = b.findMatches();
        Board.ClearOutcome out = b.clear(set, -1, -1);
        check(out.cleared.length == 3, "应消 3 格");
        check(b.score() == 3 * Board.BASE_SCORE, "第 1 层连锁应为 3×20=60 分，实际 " + b.score());
        check(out.gained == 60, "本次得分应为 60，实际 " + out.gained);

        // 第二层连锁 ×2
        int before = b.score();
        t = safeBase();
        put(t, 4, 4, 1);
        put(t, 5, 4, 1);
        put(t, 6, 4, 1);
        b.setTypes(t);
        // 注意：setTypes 不重置连锁计数，所以这一轮是第 2 层
        out = b.clear(b.findMatches(), -1, -1);
        check(out.gained == 3 * Board.BASE_SCORE * 2,
                "第 2 层连锁应为 120 分，实际 " + out.gained);
        check(b.score() == before + 120, "总分累加不对");
        b.endCascade();
        check(b.cascade() == 0, "endCascade 后连锁应清零");
        done();
    }

    private static void testSpecialSpawn() {
        section("道具生成规则");
        Board b = new Board(31);

        // 横向 4 连 → 直线炸弹（清整行）
        int[] t = safeBase();
        for (int x = 0; x < 4; x++) put(t, x, 0, 0);
        b.setTypes(t);
        Board.ClearOutcome out = b.clear(b.findMatches(), Board.indexOf(0, 0), -1);
        check(out.spawnCount == 1, "4 连应生成 1 个道具，实际 " + out.spawnCount);
        check(out.spawnSpecial[0] == Board.SPECIAL_LINE_H, "横向 4 连应生成整行炸弹");
        check(out.spawnIndex[0] == Board.indexOf(0, 0), "道具应落在交换点上");

        // 纵向 4 连 → 整列炸弹
        t = safeBase();
        for (int y = 0; y < 4; y++) put(t, 0, y, 0);
        b.setTypes(t);
        out = b.clear(b.findMatches(), -1, -1);
        check(out.spawnCount == 1 && out.spawnSpecial[0] == Board.SPECIAL_LINE_V,
                "纵向 4 连应生成整列炸弹");

        // 5 连 → 彩虹
        t = safeBase();
        for (int x = 0; x < 5; x++) put(t, x, 0, 0);
        b.setTypes(t);
        out = b.clear(b.findMatches(), -1, -1);
        check(out.spawnCount == 1 && out.spawnSpecial[0] == Board.SPECIAL_RAINBOW,
                "5 连应生成彩虹球，实际 " + (out.spawnCount > 0 ? out.spawnSpecial[0] : -1));

        // L 形（横 3 + 竖 3 交于角）→ 3x3 爆炸
        t = safeBase();
        for (int x = 0; x < 3; x++) put(t, x, 0, 0);
        put(t, 0, 1, 0);
        put(t, 0, 2, 0);
        b.setTypes(t);
        out = b.clear(b.findMatches(), -1, -1);
        check(out.spawnCount == 1 && out.spawnSpecial[0] == Board.SPECIAL_BOMB,
                "L 形应生成 3x3 爆炸，实际 " + (out.spawnCount > 0 ? out.spawnSpecial[0] : -1));
        check(out.spawnIndex[0] == Board.indexOf(0, 0), "爆炸应生成在交叉点上");

        // 生成的道具要留在棋盘上
        check(b.specialAt(out.spawnIndex[0]) == Board.SPECIAL_BOMB, "道具应写入棋盘");
        check(b.typeAt(out.spawnIndex[0]) != Board.EMPTY, "道具格不应为空");
        done();
    }

    private static void testSpecialTrigger() {
        section("道具触发效果");
        Board b = new Board(41);

        // 整行炸弹：消掉整行 8 格
        int[] t = safeBase();
        for (int x = 0; x < 3; x++) put(t, x, 0, 0);
        int lineIndex = Board.indexOf(1, 0);
        b.setTypes(t);
        b.setSpecial(lineIndex, Board.SPECIAL_LINE_H);
        Board.MatchSet set = b.findMatches();
        check(set.count == Board.SIZE, "整行炸弹应清掉一整行（8 格），实际 " + set.count);

        // 整列炸弹：三连那 3 格 + 整列 8 格，重叠 1 格 → 10
        b.setTypes(t);
        b.setSpecial(lineIndex, Board.SPECIAL_LINE_V);
        set = b.findMatches();
        check(set.count == 10, "整列炸弹应清掉整列 + 触发它的三连，共 10 格，实际 " + set.count);

        // 3x3 爆炸：位于角上只有 6 格
        b.setTypes(t);
        b.setSpecial(lineIndex, Board.SPECIAL_BOMB);
        set = b.findMatches();
        check(set.count == 6, "角上的 3x3 爆炸应影响 6 格，实际 " + set.count);

        // 彩虹：消除全部同色（棋盘上额外的同色格也要被清）
        t = safeBase();
        for (int x = 0; x < 3; x++) put(t, x, 0, 0);
        put(t, 7, 7, 0);                     // 角落里再放一个同色格
        b.setTypes(t);
        b.setSpecial(Board.indexOf(1, 0), Board.SPECIAL_RAINBOW);
        set = b.findMatches();
        check(set.cells[Board.indexOf(7, 7)], "彩虹应把角落里的同色格也带走");
        check(set.count == 4, "彩虹应清掉全部 4 个同色格，实际 " + set.count);

        // 彩虹球和普通宝石交换：直接消掉那种颜色
        b.setTypes(t);
        b.setSpecial(Board.indexOf(1, 0), Board.SPECIAL_RAINBOW);
        set = b.rainbowMatch(Board.indexOf(1, 0), Board.indexOf(4, 4));
        check(set.count >= 2, "彩虹交换应至少消掉彩虹本身和目标色");
        done();
    }

    private static void testCollapseAndRefill() {
        section("下落与补充");
        Board b = new Board(51);
        int[] t = safeBase();
        // 第 0 列挖两个洞
        t[Board.indexOf(0, 1)] = Board.EMPTY;
        t[Board.indexOf(0, 4)] = Board.EMPTY;
        b.setTypes(t);
        int[] columnBefore = new int[Board.SIZE];
        int k = 0;
        for (int y = 0; y < Board.SIZE; y++) {
            int v = b.typeAt(Board.indexOf(0, y));
            if (v != Board.EMPTY) columnBefore[k++] = v;
        }

        List<int[]> moves = b.collapse();
        // 洞在 y=1 和 y=4：y=5,6,7 原地不动，y=0,2,3 各下移一格 → 3 次移动
        check(moves.size() == 3, "应有 3 块宝石下落，实际移动 " + moves.size() + " 次");
        check(b.typeAt(Board.indexOf(0, 0)) == Board.EMPTY
                        && b.typeAt(Board.indexOf(0, 1)) == Board.EMPTY,
                "顶部两格应空出来\n" + dump(b));
        for (int y = 0; y < k; y++) {
            check(b.typeAt(Board.indexOf(0, 2 + y)) == columnBefore[y],
                    "下落必须保持原有顺序（第 " + y + " 块）");
        }

        int emptyBefore = 0;
        for (int i = 0; i < 64; i++) if (b.typeAt(i) == Board.EMPTY) emptyBefore++;
        List<int[]> spawned = b.refill();
        check(spawned.size() == emptyBefore, "补充数量应等于空格数");
        for (int[] s : spawned) {
            check(s[1] >= 1, "新宝石应从上方掉下来（距离应 ≥1），实际 " + s[1]);
            check(b.typeAt(s[0]) != Board.EMPTY, "补充后不应还是空格");
        }
        for (int i = 0; i < 64; i++) {
            check(b.typeAt(i) != Board.EMPTY, "补充后棋盘应满");
        }
        done();
    }

    private static void testDeadlockAndShuffle() {
        section("死局检测与自动打乱");
        Board b = new Board(61);
        // 三色斜纹盘 (x+y)%3：任何相邻交换都只能形成两连，所以是真正的死局
        // （注意两色棋盘 (x+y)%2 不是死局：横着换一下就会竖着凑成三连）
        int[] t = new int[64];
        for (int y = 0; y < Board.SIZE; y++) {
            for (int x = 0; x < Board.SIZE; x++) {
                t[Board.indexOf(x, y)] = (x + y) % 3;
            }
        }
        b.setTypes(t);
        check(!b.hasMove(), "三色斜纹盘应无解\n" + dump(b));
        check(b.findMoves().isEmpty(), "无解时 findMoves 应为空");

        boolean shuffled = b.ensurePlayable();
        check(shuffled, "无解时应自动打乱");
        check(b.hasMove(), "打乱后必须有解\n" + dump(b));
        check(b.findMatches().isEmpty(), "打乱后不应自带三连");

        int[] hint = b.hint();
        check(hint != null && hint.length == 2, "有解时应能给出提示");
        check(b.canSwap(hint[0], hint[1]), "提示的那一步必须真的是合法交换");
        done();
    }

    private static void testLevelAndStars() {
        section("关卡目标与星级");
        Board b = new Board(71);
        b.newLevel(1);
        check(b.level() == 1 && b.target() == Board.targetFor(1), "第 1 关目标分不对");
        check(b.movesLeft() == 24, "第 1 关应给 24 步，实际 " + b.movesLeft());

        b.setProgress(Board.targetFor(1) - 1, 5, Board.targetFor(1));
        check(!b.isCleared() && b.stars() == 0, "没达标不应算过关");
        check(!b.isFailed(), "还有步数就不算失败");

        b.setProgress(Board.targetFor(1), 5, Board.targetFor(1));
        check(b.isCleared() && b.stars() == 1, "刚达标应为 1 星");

        b.setProgress((int) (Board.targetFor(1) * 1.5), 5, Board.targetFor(1));
        check(b.stars() == 2, "1.5 倍应为 2 星");

        b.setProgress(Board.targetFor(1) * 2, 5, Board.targetFor(1));
        check(b.stars() == 3, "2 倍应为 3 星");

        b.setProgress(100, 0, Board.targetFor(1));
        check(b.isFailed(), "步数用完且没达标应算失败");

        b.newLevel(3);
        check(b.movesLeft() == Board.movesFor(3), "第 3 关步数应为 " + Board.movesFor(3));
        check(Board.movesFor(30) >= 18, "步数下限应为 18");
        done();
    }

    private static void testFullCascades() {
        section("完整连锁结算（长跑 300 局）");
        Random rnd = new Random(20240924);
        long totalCleared = 0;
        long totalMoves = 0;
        int maxCascade = 0;
        int maxScore = 0;

        for (int game = 0; game < 300; game++) {
            Board b = new Board(rnd.nextLong());
            int guard = 0;
            while (!b.isCleared() && !b.isFailed() && guard++ < 200) {
                b.ensurePlayable();
                List<int[]> moves = b.findMoves();
                if (moves.isEmpty()) break;
                int[] mv = moves.get(rnd.nextInt(moves.size()));
                b.swap(mv[0], mv[1]);
                b.consumeMove();
                totalMoves++;

                int cascadeGuard = 0;
                while (cascadeGuard++ < 60) {
                    Board.MatchSet set = b.findMatches();
                    if (set.isEmpty()) break;
                    Board.ClearOutcome out = b.clear(set, mv[0], mv[1]);
                    totalCleared += out.cleared.length;
                    b.collapse();
                    b.refill();
                    maxCascade = Math.max(maxCascade, b.cascade());
                }
                b.endCascade();

                // 静止后必须：满盘、无匹配（这是最关键的不变量）
                for (int i = 0; i < 64; i++) {
                    check(b.typeAt(i) != Board.EMPTY, "静止后不应有空格");
                }
                check(b.findMatches().isEmpty(), "静止后不应还有三连\n" + dump(b));
                check(b.score() >= 0, "分数不应为负");
                check(b.movesLeft() >= 0, "步数不应为负");
                // 满盘但可能无解，下一轮 ensurePlayable 会处理
            }
            maxScore = Math.max(maxScore, b.score());
        }
        done(totalMoves + " 步有效交换，消除 " + totalCleared + " 个宝石，最长连锁 "
                + maxCascade + " 层，单局最高 " + maxScore + " 分");
    }

    public static void main(String[] args) {
        System.out.println("三消核心逻辑自测");
        System.out.println("----------------");
        testInitialBoard();
        testMatchDetection();
        testSwapRules();
        testScoringAndCascade();
        testSpecialSpawn();
        testSpecialTrigger();
        testCollapseAndRefill();
        testDeadlockAndShuffle();
        testLevelAndStars();
        testFullCascades();
        System.out.println("----------------");
        System.out.printf("%d 项断言，%d 项失败%n", checks, fails);
        System.exit(fails == 0 ? 0 : 1);
    }
}
