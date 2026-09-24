package com.dsh.g2048;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Random;

/**
 * 2048 逻辑自测（纯 Java，不需要 Android，也不需要 JUnit）。
 *
 * <pre>
 *   javac -d classes src/com/dsh/g2048/Game.java src/com/dsh/g2048/GameTest.java
 *   java -cp classes com.dsh.g2048.GameTest
 * </pre>
 *
 * 关键思路：除了边界用例，还写了一个"一眼就对"的朴素参考实现，用随机棋盘和它逐格对拍。
 */
public final class GameTest {

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

    /** 把 4x4 棋盘按一行行写成可读字符串，方便报错时定位。 */
    private static String dump(Game g) {
        StringBuilder sb = new StringBuilder();
        for (int y = 0; y < Game.SIZE; y++) {
            sb.append('[');
            for (int x = 0; x < Game.SIZE; x++) {
                sb.append(String.format("%4d", g.get(x, y)));
            }
            sb.append("]\n");
        }
        return sb.toString();
    }

    /** 用 4 行字符串摆棋盘，例如 board("2 2 4 4", "0 0 0 0", "0 0 0 0", "0 0 0 0")。 */
    private static int[] board(String... rows) {
        int[] b = new int[Game.SIZE * Game.SIZE];
        for (int y = 0; y < Game.SIZE; y++) {
            String[] parts = rows[y].trim().split("\\s+");
            for (int x = 0; x < Game.SIZE; x++) {
                b[y * Game.SIZE + x] = Integer.parseInt(parts[x]);
            }
        }
        return b;
    }

    private static int[] playAndStrip(Game g, Game.Dir dir) {
        Game.Result r = g.move(dir);
        int[] b = g.snapshot();
        if (r.moved && r.spawnedX >= 0) {
            b[r.spawnedY * Game.SIZE + r.spawnedX] = 0;   // 去掉新生成的方块
        }
        return b;
    }

    // ------------------------------------------------------------ 朴素参考实现

    /** 把一条线按"朝 0 号方向压缩合并"处理，返回结果线与得分。 */
    private static int[] refLine(int[] line, int[] gainedOut) {
        List<Integer> vals = new ArrayList<Integer>();
        for (int v : line) if (v != 0) vals.add(v);
        List<Integer> out = new ArrayList<Integer>();
        int gained = 0;
        for (int i = 0; i < vals.size(); i++) {
            if (i + 1 < vals.size() && vals.get(i).intValue() == vals.get(i + 1).intValue()) {
                int merged = vals.get(i) * 2;
                out.add(merged);
                gained += merged;
                i++;
            } else {
                out.add(vals.get(i));
            }
        }
        while (out.size() < Game.SIZE) out.add(0);
        int[] res = new int[Game.SIZE];
        for (int i = 0; i < Game.SIZE; i++) res[i] = out.get(i);
        gainedOut[0] = gained;
        return res;
    }

    /** 用朴素实现算出某个方向的结果（不含新方块）。 */
    private static int[] reference(int[] board, Game.Dir dir) {
        int[] out = new int[board.length];
        int[] gained = new int[1];
        for (int line = 0; line < Game.SIZE; line++) {
            int[] in = new int[Game.SIZE];
            int[] idx = new int[Game.SIZE];
            for (int k = 0; k < Game.SIZE; k++) {
                int x, y;
                switch (dir) {
                    case LEFT:  x = k;            y = line; break;
                    case RIGHT: x = Game.SIZE - 1 - k; y = line; break;
                    case UP:    x = line;         y = k;    break;
                    default:    x = line;         y = Game.SIZE - 1 - k; break;
                }
                idx[k] = y * Game.SIZE + x;
                in[k] = board[idx[k]];
            }
            int[] res = refLine(in, gained);
            for (int k = 0; k < Game.SIZE; k++) out[idx[k]] = res[k];
        }
        return out;
    }

    // ------------------------------------------------------------ 用例

    private static void testInit() {
        section("初始局面");
        Game g = new Game(1);
        int nonZero = 0;
        for (int i = 0; i < 16; i++) {
            int x = i % 4, y = i / 4;
            int v = g.get(x, y);
            if (v != 0) {
                nonZero++;
                check(v == 2 || v == 4, "初始方块只能是 2 或 4，实际 " + v);
            }
        }
        check(nonZero == 2, "开局应有 2 个方块，实际 " + nonZero);
        check(g.score() == 0, "开局得分应为 0");
        check(!g.isOver() && !g.hasWon(), "开局不应结束");
        check(!g.canUndo(), "开局不该能撤销");
        done("2 个方块，2 或 4");
    }

    private static void testMerges() {
        section("合并规则（经典用例）");
        // 2 2 4 4 左移 → 4 8 0 0，得分 12
        Game g = new Game(1);
        g.setBoard(board("2 2 4 4", "0 0 0 0", "0 0 0 0", "0 0 0 0"));
        Game.Result r = g.move(Game.Dir.LEFT);
        check(r.gained == 12, "2244 左移得分应为 12，实际 " + r.gained);
        check(g.get(0, 0) == 4 && g.get(1, 0) == 8, "2244 左移应为 4,8\n" + dump(g));

        // 2 2 2 左移 → 4 2 0 0（不能连锁合并）
        g.setBoard(board("2 2 2 0", "0 0 0 0", "0 0 0 0", "0 0 0 0"));
        r = g.move(Game.Dir.LEFT);
        check(g.get(0, 0) == 4 && g.get(1, 0) == 2, "222 左移应为 4,2\n" + dump(g));
        check(r.gained == 4, "222 左移得分应为 4，实际 " + r.gained);

        // 2 2 2 2 左移 → 4 4 0 0，得分 8
        g.setBoard(board("2 2 2 2", "0 0 0 0", "0 0 0 0", "0 0 0 0"));
        r = g.move(Game.Dir.LEFT);
        check(g.get(0, 0) == 4 && g.get(1, 0) == 4, "2222 左移应为 4,4\n" + dump(g));
        check(r.gained == 8, "2222 左移得分应为 8，实际 " + r.gained);

        // 4 4 8 8 右移 → 0 0 8 16
        g.setBoard(board("4 4 8 8", "0 0 0 0", "0 0 0 0", "0 0 0 0"));
        g.move(Game.Dir.RIGHT);
        check(g.get(2, 0) == 8 && g.get(3, 0) == 16, "4488 右移应为 _,_,8,16\n" + dump(g));
        done();
    }

    private static void testNoChange() {
        section("无效移动不生成新方块");
        Game g = new Game(7);
        g.setBoard(board("2 0 0 0", "0 0 0 0", "0 0 0 0", "0 0 0 0"));      // 只有一个方块且已贴左边
        int[] before = g.snapshot();
        int beforeScore = g.score();
        Game.Result r = g.move(Game.Dir.LEFT);
        check(!r.moved, "没有方块可动时应返回 moved=false");
        check(Arrays.equals(before, g.snapshot()), "无效移动不应改变棋盘\n" + dump(g));
        check(g.score() == beforeScore, "无效移动不应计分");
        check(r.spawnedX < 0, "无效移动不应生成新方块");

        // 上移同样无效
        r = g.move(Game.Dir.UP);
        check(!r.moved, "上移也应无效");
        done();
    }

    private static void testSumInvariant() {
        section("数值守恒与只加一个方块");
        Game g = new Game(99);
        Random rnd = new Random(4242);
        for (int step = 0; step < 400; step++) {
            int sumBefore = 0, tilesBefore = 0;
            for (int i = 0; i < 16; i++) {
                int v = g.get(i % 4, i / 4);
                sumBefore += v;
                if (v != 0) tilesBefore++;
            }
            Game.Dir dir = Game.Dir.values()[rnd.nextInt(4)];
            int[] before = g.snapshot();
            Game.Result r = g.move(dir);
            if (!r.moved) {
                check(Arrays.equals(before, g.snapshot()), "moved=false 时棋盘不应变化");
                if (g.isOver()) g.reset();
                continue;
            }
            int sumAfter = 0, tilesAfter = 0;
            for (int i = 0; i < 16; i++) {
                int v = g.get(i % 4, i / 4);
                sumAfter += v;
                if (v != 0) tilesAfter++;
            }
            int spawned = r.spawnedX >= 0 ? g.get(r.spawnedX, r.spawnedY) : 0;
            check(r.spawnedX >= 0, "成功移动后必须生成一个新方块");
            check(spawned == 2 || spawned == 4, "新方块只能是 2 或 4，实际 " + spawned);
            // 合并不改变数值总和，所以总和只增加新方块那一个
            check(sumAfter == sumBefore + spawned,
                  "数值总和不守恒: " + sumBefore + " + " + spawned + " != " + sumAfter);
            check(tilesAfter >= 1 && tilesAfter <= tilesBefore + 1,
                  "方块数量异常: " + tilesBefore + " -> " + tilesAfter);
            check(g.score() >= 0, "得分不应为负");
            if (g.isOver()) g.reset();
        }
        done();
    }

    private static void testAgainstReference() {
        section("与朴素实现逐格对拍");
        Random rnd = new Random(20240918);
        Game g = new Game(5);
        int cases = 0;
        for (int round = 0; round < 300; round++) {
            // 随机铺一个棋盘（数值取自常见阶梯，保证能出现合并）
            int[] b = new int[16];
            int[] pool = {0, 0, 0, 2, 2, 4, 4, 8, 16, 32, 64, 128};
            for (int i = 0; i < 16; i++) b[i] = pool[rnd.nextInt(pool.length)];
            g.setBoard(b.clone());
            for (Game.Dir dir : Game.Dir.values()) {
                g.setBoard(b.clone());
                int[] mine = playAndStrip(g, dir);
                int[] ref = reference(b, dir);
                if (!Arrays.equals(mine, ref)) {
                    check(false, dir + " 结果与朴素实现不一致"
                            + "\n输入: " + Arrays.toString(b)
                            + "\n我方: " + Arrays.toString(mine)
                            + "\n参考: " + Arrays.toString(ref));
                } else {
                    checks++;
                }
                cases++;
            }
        }
        done(cases + " 组对拍");
    }

    private static void testUndo() {
        section("撤销");
        Game g = new Game(3);
        g.setBoard(board("2 2 0 0", "0 0 0 0", "0 0 0 0", "0 0 0 0"));
        int[] before = g.snapshot();
        check(!g.canUndo(), "走之前不该能撤销");
        g.move(Game.Dir.LEFT);
        check(g.canUndo(), "走之后应能撤销");
        check(g.score() == 4, "得分应为 4");
        check(g.undo(), "撤销应成功");
        check(Arrays.equals(before, g.snapshot()), "撤销后棋盘应恢复\n" + dump(g));
        check(g.score() == 0, "撤销后得分应恢复");
        check(!g.canUndo(), "只能撤销一步");
        check(!g.undo(), "没有可撤销内容时应返回 false");
        done();
    }

    private static void testWinAndLose() {
        section("胜利与死局判定");
        Game g = new Game(11);
        g.setBoard(board("1024 1024 0 0", "0 0 0 0", "0 0 0 0", "0 0 0 0"));
        Game.Result r = g.move(Game.Dir.LEFT);
        check(r.won, "凑出 2048 时应报告胜利");
        check(g.hasWon(), "hasWon 应为 true");
        check(g.get(0, 0) == 2048, "合并结果应为 2048\n" + dump(g));
        g.keepPlaying();
        check(g.isKeepPlaying(), "选择继续后 isKeepPlaying 应为 true");

        // 死局：满盘且相邻都不相同
        Game d = new Game(12);
        d.setBoard(board("2 4 6 8", "8 2 4 6", "2 4 6 8", "8 2 4 6"));
        check(!d.hasMove(), "这种满盘应无路可走");
        Game.Result dr = d.move(Game.Dir.LEFT);
        check(!dr.moved, "死局时移动应无效");
        check(d.isOver(), "死局后 isOver 应为 true");

        // 有空格就不算死
        Game e = new Game(13);
        e.setBoard(board("2 4 6 8", "8 2 4 6", "2 4 6 8", "8 2 0 0"));
        check(e.hasMove(), "还有空格时应可继续");
        done();
    }

    private static void testMotions() {
        section("滑动动画数据");
        Game g = new Game(21);
        g.setBoard(board("2 0 2 2", "0 0 0 0", "0 0 0 0", "0 0 0 0"));      // 2 _ 2 2 左移
        Game.Result r = g.move(Game.Dir.LEFT);
        check(!r.motions.isEmpty(), "有滑动就应有动画数据");
        for (Game.Motion m : r.motions) {
            check(m.fromX >= 0 && m.fromX < 4 && m.fromY >= 0 && m.fromY < 4,
                    "起点越界: " + m.fromX + "," + m.fromY);
            check(m.toX >= 0 && m.toX < 4 && m.toY >= 0 && m.toY < 4,
                    "终点越界: " + m.toX + "," + m.toY);
            check(m.fromX != m.toX || m.fromY != m.toY, "原地不动的不应产生动画");
            check(m.value > 0, "动画数值应为正");
        }
        done(r.motions.size() + " 条轨迹");
    }

    private static void testLongRun() {
        section("随机对局长跑（2000 局）");
        Random rnd = new Random(777);
        long totalMoves = 0;
        int best = 0;
        int emptyChecks = 0;
        for (int game = 0; game < 2000; game++) {
            Game g = new Game(rnd.nextLong());
            int guard = 0;
            while (!g.isOver() && guard++ < 3000) {
                Game.Dir dir = Game.Dir.values()[rnd.nextInt(4)];
                int[] before = g.snapshot();
                int scoreBefore = g.score();
                Game.Result r = g.move(dir);
                if (r.moved) {
                    totalMoves++;
                    check(g.score() >= scoreBefore, "得分不应减少");
                    check(!Arrays.equals(before, g.snapshot()), "moved=true 时棋盘必须有变化");
                    check(r.spawnedX >= 0, "成功移动后应有新方块");
                    check(g.emptyCount() >= 0 && g.emptyCount() <= 16, "空格数越界");
                    int max = g.maxValue();
                    check(max > 0 && (max & (max - 1)) == 0, "方块值必须是 2 的幂，实际 " + max);
                    emptyChecks++;
                } else {
                    check(Arrays.equals(before, g.snapshot()), "moved=false 时棋盘不应变化");
                }
            }
            check(!g.hasMove() == g.isOver(), "isOver 应与 hasMove 相反");
            best = Math.max(best, g.maxValue());
        }
        done(totalMoves + " 步有效移动，最大方块 " + best + "（校验 " + emptyChecks + " 次）");
    }

    public static void main(String[] args) {
        System.out.println("2048 核心逻辑自测");
        System.out.println("----------------");
        testInit();
        testMerges();
        testNoChange();
        testSumInvariant();
        testAgainstReference();
        testUndo();
        testWinAndLose();
        testMotions();
        System.out.println("----------------");
        System.out.printf("%d 项断言，%d 项失败%n", checks, fails);
        System.exit(fails == 0 ? 0 : 1);
    }
}
