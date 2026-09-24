// 扫雷核心逻辑的单元测试（控制台程序，不依赖 Windows API）
// 用法：tests.exe        正常输出
//       tests.exe -v     额外打印每个用例的统计
#include <algorithm>
#include <cstdio>
#include <random>
#include <string>
#include <vector>

#include "game.h"

using namespace sweeper;

static int g_checks = 0;
static int g_fails = 0;
static bool g_verbose = false;

#define CHECK(cond, msg)                                                        \
    do {                                                                        \
        ++g_checks;                                                             \
        if (!(cond)) {                                                          \
            ++g_fails;                                                          \
            std::printf("      [FAIL] %s:%d  %s\n", __FILE__, __LINE__, (msg)); \
        }                                                                       \
    } while (0)

static void section(const char* title) {
    std::printf("  %-34s", title);
    std::fflush(stdout);
}

static void done(const std::string& detail = "") {
    std::printf("OK%s\n", detail.empty() ? "" : ("   " + detail).c_str());
}

// ---------------------------------------------------------------- 用例

static void test_presets_and_reset() {
    section("难度预设与重置");
    const Config cfgBeginner = presetBeginner();
    const Config cfgIntermediate = presetIntermediate();
    const Config cfgExpert = presetExpert();
    CHECK(cfgBeginner.cols == 9 && cfgBeginner.rows == 9 && cfgBeginner.mines == 10,
          "初级应为 9x9/10");
    CHECK(cfgIntermediate.cols == 16 && cfgIntermediate.rows == 16 &&
              cfgIntermediate.mines == 40, "中级应为 16x16/40");
    CHECK(cfgExpert.cols == 30 && cfgExpert.rows == 16 && cfgExpert.mines == 99,
          "高级应为 30x16/99");

    // 雷数超限必须被截断，否则首点安全区无处安放
    Config silly = customConfig(9, 9, 500);
    Board board;
    board.reset(silly, 1);
    CHECK(board.mineCount() == 72, "9x9 的雷数上限应为 72（81-9）");
    CHECK(board.cols() == 9 && board.rows() == 9, "尺寸被改动了");

    Config tiny = customConfig(1, 1, 5);
    board.reset(tiny, 1);
    CHECK(board.cols() >= 2 && board.rows() >= 2, "尺寸下限应为 2x2");

    board.reset(presetBeginner(), 42);
    CHECK(board.status() == Status::Ready, "新局应为 Ready");
    CHECK(!board.minesPlaced(), "首点之前不应布雷");
    CHECK(board.flags() == 0 && board.revealedCount() == 0, "新局计数应为 0");
    int mines = 0;
    for (int i = 0; i < board.cols() * board.rows(); ++i) mines += board.atIndex(i).mine;
    CHECK(mines == 0, "首点之前棋盘上不应有雷");
    done();
}

static void test_first_click_safety() {
    section("首点安全（300 局随机验证）");
    Board board;
    std::mt19937 rng(12345);
    std::uniform_int_distribution<int> pick(0, 8);
    int cases = 0;
    for (int t = 0; t < 300; ++t) {
        board.reset(presetBeginner(), (uint32_t)(t + 1));
        const int x = pick(rng), y = pick(rng);
        CHECK(board.reveal(x, y), "首点应被接受");
        CHECK(board.minesPlaced(), "首点之后应已布雷");
        CHECK(board.status() == Status::Playing, "首点之后应进入 Playing");
        int mines = 0;
        for (int i = 0; i < board.cols() * board.rows(); ++i) mines += board.atIndex(i).mine;
        CHECK(mines == 10, "雷数应恒为 10");
        for (int dy = -1; dy <= 1; ++dy) {
            for (int dx = -1; dx <= 1; ++dx) {
                const int nx = x + dx, ny = y + dy;
                if (board.inBounds(nx, ny)) {
                    CHECK(!board.at(nx, ny).mine, "首点 3x3 范围内不应有雷");
                }
            }
        }
        ++cases;
    }
    done(std::to_string(cases) + " 局");
}

static void test_adjacency() {
    section("相邻雷数计算");
    Board board;
    for (int t = 0; t < 50; ++t) {
        board.reset(presetIntermediate(), (uint32_t)(t * 7 + 3));
        board.reveal(8, 8);
        for (int y = 0; y < board.rows(); ++y) {
            for (int x = 0; x < board.cols(); ++x) {
                const Cell& c = board.at(x, y);
                if (c.mine) {
                    CHECK(c.adj == 0, "雷格的数字应为 0");
                    continue;
                }
                int n = 0;
                for (int dy = -1; dy <= 1; ++dy) {
                    for (int dx = -1; dx <= 1; ++dx) {
                        if (!dx && !dy) continue;
                        const int nx = x + dx, ny = y + dy;
                        if (board.inBounds(nx, ny) && board.at(nx, ny).mine) ++n;
                    }
                }
                CHECK(c.adj == n, "数字与暴力统计不一致");
            }
        }
    }
    done();
}

static void test_flood_fill() {
    section("洪水展开（0 格向外扩散）");
    Board board;
    for (int t = 0; t < 50; ++t) {
        board.reset(presetExpert(), (uint32_t)(t + 100));
        board.reveal(15, 8);
        for (int y = 0; y < board.rows(); ++y) {
            for (int x = 0; x < board.cols(); ++x) {
                const Cell& c = board.at(x, y);
                if (c.state == REVEALED) {
                    CHECK(!c.mine, "展开出来的格子不应该是雷");
                    if (c.adj == 0) {
                        // 0 格必须把 8 个邻居全部展开（无插旗时的不动点性质）
                        for (int dy = -1; dy <= 1; ++dy) {
                            for (int dx = -1; dx <= 1; ++dx) {
                                const int nx = x + dx, ny = y + dy;
                                if (!board.inBounds(nx, ny)) continue;
                                CHECK(board.at(nx, ny).state == REVEALED ||
                                          board.at(nx, ny).mine,
                                      "0 格的邻居未被展开");
                            }
                        }
                    }
                }
            }
        }
    }
    done();
}

static void test_win() {
    section("胜利判定（翻完所有非雷格）");
    Board board;
    for (int t = 0; t < 30; ++t) {
        board.reset(presetBeginner(), (uint32_t)(t + 500));
        board.reveal(0, 0);
        for (int y = 0; y < board.rows(); ++y) {
            for (int x = 0; x < board.cols(); ++x) {
                if (!board.at(x, y).mine) board.reveal(x, y);
            }
        }
        CHECK(board.status() == Status::Won, "翻完非雷格应判胜");
        CHECK(board.flags() == board.mineCount(), "胜利后所有雷应被自动插旗");
        CHECK(board.minesRemaining() == 0, "胜利后剩余雷数应为 0");
        CHECK(board.revealedCount() == board.safeTotal(), "已翻开数应等于安全格数");
        int flagged = 0;
        for (int i = 0; i < board.cols() * board.rows(); ++i) {
            const Cell& c = board.atIndex(i);
            if (c.mine) CHECK(c.state == FLAGGED, "雷应处于插旗状态");
            if (c.state == FLAGGED) ++flagged;
        }
        CHECK(flagged == board.mineCount(), "插旗数应等于雷数");
    }
    done();
}

static void test_lose() {
    section("失败判定（踩雷与错误插旗）");
    Board board;
    for (int t = 0; t < 30; ++t) {
        board.reset(presetBeginner(), (uint32_t)(t + 900));
        board.reveal(4, 4);
        // 先在一颗确定的非雷格上插旗，用于检验 wrong_flag
        int flagX = -1, flagY = -1;
        for (int y = 0; y < board.rows() && flagX < 0; ++y) {
            for (int x = 0; x < board.cols(); ++x) {
                if (!board.at(x, y).mine && board.at(x, y).state == HIDDEN) {
                    flagX = x; flagY = y; break;
                }
            }
        }
        CHECK(flagX >= 0, "应能找到可插旗的非雷格");
        board.toggleFlag(flagX, flagY);

        int mineX = -1, mineY = -1;
        for (int y = 0; y < board.rows() && mineX < 0; ++y) {
            for (int x = 0; x < board.cols(); ++x) {
                if (board.at(x, y).mine) { mineX = x; mineY = y; break; }
            }
        }
        CHECK(mineX >= 0, "应能找到雷");
        CHECK(board.reveal(mineX, mineY), "踩雷应被接受");
        CHECK(board.status() == Status::Lost, "踩雷应判负");
        CHECK(board.at(mineX, mineY).exploded, "踩中的雷应被标记");

        int exploded = 0;
        for (int i = 0; i < board.cols() * board.rows(); ++i) {
            if (board.atIndex(i).exploded) ++exploded;
        }
        CHECK(exploded == 1, "只应有一颗雷被标记为踩中");
        CHECK(board.at(flagX, flagY).wrong_flag, "错误的旗应被标出");
        CHECK(!board.reveal(3, 3), "结束后不应还能继续操作");
        CHECK(!board.toggleFlag(3, 3), "结束后不应还能插旗");
    }
    done();
}

static void test_flag_cycle() {
    section("插旗 / 问号循环");
    Board board;
    board.reset(presetBeginner(), 777);
    board.reveal(4, 4);

    auto find = [&](uint8_t want, int& ox, int& oy) {
        for (int y = 0; y < board.rows(); ++y) {
            for (int x = 0; x < board.cols(); ++x) {
                if (board.at(x, y).state == want) { ox = x; oy = y; return true; }
            }
        }
        return false;
    };

    int x = -1, y = -1;
    CHECK(find(HIDDEN, x, y), "应存在未翻开的格子");
    CHECK(board.toggleFlag(x, y), "插旗应被接受");
    CHECK(board.at(x, y).state == FLAGGED && board.flags() == 1, "应变为旗且计数为 1");
    CHECK(board.minesRemaining() == board.mineCount() - 1, "剩余雷数应减一");
    CHECK(!board.reveal(x, y), "插旗的格子不能被翻开");

    CHECK(board.toggleFlag(x, y), "再次右键应被接受");
    CHECK(board.at(x, y).state == QUESTION && board.flags() == 0, "应变为问号且计数归零");
    CHECK(board.toggleFlag(x, y), "第三次右键应被接受");
    CHECK(board.at(x, y).state == HIDDEN && board.flags() == 0, "应回到未翻开状态");

    board.setQuestionMarks(false);
    CHECK(board.toggleFlag(x, y), "关闭问号后插旗");
    CHECK(board.at(x, y).state == FLAGGED, "应为旗");
    CHECK(board.toggleFlag(x, y), "关闭问号后再次右键");
    CHECK(board.at(x, y).state == HIDDEN, "应直接回到未翻开（跳过问号）");

    // 已翻开的格子不能插旗
    CHECK(find(REVEALED, x, y), "应存在已翻开的格子");
    CHECK(!board.toggleFlag(x, y), "已翻开的格子不应能插旗");
    done();
}

static void test_chord() {
    section("和弦展开（双击数字）");
    Board board;
    int okCount = 0, boomCount = 0, emptyCount = 0;
    for (int t = 0; t < 200; ++t) {
        board.reset(presetExpert(), (uint32_t)(t + 2000));
        board.reveal(15, 8);

        // 找一个已翻开的数字格，其邻格里还有未翻开的
        int cx = -1, cy = -1;
        for (int y = 0; y < board.rows() && cx < 0; ++y) {
            for (int x = 0; x < board.cols(); ++x) {
                const Cell& c = board.at(x, y);
                if (c.state != REVEALED || c.adj == 0) continue;
                bool hasHidden = false;
                for (int dy = -1; dy <= 1 && !hasHidden; ++dy) {
                    for (int dx = -1; dx <= 1; ++dx) {
                        const int nx = x + dx, ny = y + dy;
                        if (!board.inBounds(nx, ny) || (!dx && !dy)) continue;
                        if (board.at(nx, ny).state == HIDDEN) { hasHidden = true; break; }
                    }
                }
                if (hasHidden) { cx = x; cy = y; break; }
            }
        }
        if (cx < 0) continue;

        // 数一数这个数字格周围还有多少未翻开的格子（区分是雷还是安全格）
        const Cell& c = board.at(cx, cy);
        int hiddenMines = 0, hiddenSafe = 0;
        for (int dy = -1; dy <= 1; ++dy) {
            for (int dx = -1; dx <= 1; ++dx) {
                if (!dx && !dy) continue;
                const int nx = cx + dx, ny = cy + dy;
                if (!board.inBounds(nx, ny)) continue;
                if (board.at(nx, ny).state != HIDDEN) continue;
                if (board.at(nx, ny).mine) ++hiddenMines; else ++hiddenSafe;
            }
        }
        CHECK(hiddenMines == c.adj,
              "已翻开的数字格周围未翻开的雷数应等于其数字");

        const int before = board.revealedCount();
        for (int dy = -1; dy <= 1; ++dy) {          // 把周围所有的雷都插上旗
            for (int dx = -1; dx <= 1; ++dx) {
                if (!dx && !dy) continue;
                const int nx = cx + dx, ny = cy + dy;
                if (!board.inBounds(nx, ny)) continue;
                if (board.at(nx, ny).mine && board.at(nx, ny).state == HIDDEN) {
                    CHECK(board.toggleFlag(nx, ny), "插旗应成功");
                }
            }
        }
        const bool changed = board.chord(cx, cy);
        if (board.status() == Status::Lost) {
            ++boomCount;
            CHECK(false, "周围雷都已正确标出，和弦不应导致失败");
        } else if (hiddenSafe > 0) {
            CHECK(changed, "周围雷全部标出后和弦应展开邻格");
            CHECK(board.revealedCount() > before, "和弦应增加已翻开数");
            ++okCount;
        } else {
            // 唯一的未翻开邻居都是雷，插旗后没有可展开的格子，返回 false 才对
            CHECK(!changed, "无可展开的安全格时和弦不应报告发生变化");
            ++emptyCount;
        }
    }
    CHECK(okCount > 50, "应有多数情况下和弦成功展开");
    if (g_verbose) {
        std::printf("(展开 %d / 无可展开 %d / 失败 %d) ", okCount, emptyCount, boomCount);
    }

    // 边界情形
    Board b2;
    b2.reset(presetBeginner(), 5);
    b2.reveal(4, 4);
    CHECK(!b2.chord(-1, 0), "越界和弦应返回 false");
    int hx = -1, hy = -1;
    for (int y = 0; y < b2.rows() && hx < 0; ++y) {
        for (int x = 0; x < b2.cols(); ++x) {
            if (b2.at(x, y).state == HIDDEN) { hx = x; hy = y; break; }
        }
    }
    CHECK(!b2.chord(hx, hy), "未翻开的格子不能和弦");
    done();
}

static void test_bounds() {
    section("边界与非法操作");
    Board board;
    board.reset(presetBeginner(), 3);
    CHECK(board.inBounds(0, 0) && board.inBounds(8, 8), "合法坐标判定错误");
    CHECK(!board.inBounds(-1, 0) && !board.inBounds(0, -1), "负坐标应越界");
    CHECK(!board.inBounds(9, 0) && !board.inBounds(0, 9), "超界坐标应越界");
    CHECK(!board.reveal(-1, -1), "越界翻开应失败");
    CHECK(!board.toggleFlag(100, 100), "越界插旗应失败");
    CHECK(!board.chord(50, 50), "越界和弦应失败");
    board.reveal(4, 4);
    CHECK(!board.reveal(4, 4), "重复翻开同一格应无效");
    done();
}

static void test_random_play() {
    section("随机对局不变量（400 局）");
    Board board;
    std::mt19937 rng(20240918);
    int clicks = 0, wins = 0, losses = 0;
    for (int t = 0; t < 400; ++t) {
        const Config cfg = (t % 3 == 0) ? presetBeginner()
                          : (t % 3 == 1) ? presetIntermediate()
                                         : presetExpert();
        board.reset(cfg, (uint32_t)(t * 31 + 7));
        for (int step = 0; step < 120 && !board.finished(); ++step) {
            const int x = (int)(rng() % (uint32_t)board.cols());
            const int y = (int)(rng() % (uint32_t)board.rows());
            const int action = (int)(rng() % 3);
            if (action == 0) board.reveal(x, y);
            else if (action == 1) board.toggleFlag(x, y);
            else board.chord(x, y);
            ++clicks;

            // 不变量
            int mines = 0, flagged = 0, revealed = 0, exploded = 0;
            for (int i = 0; i < board.cols() * board.rows(); ++i) {
                const Cell& c = board.atIndex(i);
                if (c.mine) ++mines;
                if (c.state == FLAGGED) ++flagged;
                if (c.state == REVEALED && !c.mine) ++revealed;
                if (c.exploded) ++exploded;
                CHECK(!(c.state == REVEALED && c.mine && !c.exploded &&
                        board.status() != Status::Lost),
                      "失败局面外不应有被翻开的雷");
                CHECK(!(c.exploded && !c.mine), "只有雷才可能被标记为踩中");
            }
            if (board.minesPlaced()) CHECK(mines == board.mineCount(), "雷数应保持不变");
            CHECK(flagged == board.flags(), "插旗计数与实际不符");
            CHECK(revealed == board.revealedCount(), "已翻开计数与实际不符");
            CHECK(exploded <= 1, "最多只有一颗雷被踩中");
            if (board.status() == Status::Won) {
                CHECK(board.revealedCount() == board.safeTotal(), "胜利时应翻完所有安全格");
                CHECK(flagged == board.mineCount(), "胜利时应全部插旗");
            }
        }
        if (board.status() == Status::Won) ++wins;
        if (board.status() == Status::Lost) ++losses;
    }
    CHECK(wins + losses <= 400, "状态统计异常");
    done(std::to_string(clicks) + " 次操作，胜 " + std::to_string(wins) +
         " 负 " + std::to_string(losses));
}

static void test_reproducible() {
    section("同种子可复现");
    Board a, b;
    a.reset(presetIntermediate(), 20240102);
    b.reset(presetIntermediate(), 20240102);
    a.reveal(5, 5);
    b.reveal(5, 5);
    bool same = true;
    for (int i = 0; i < a.cols() * a.rows(); ++i) {
        if (a.atIndex(i).mine != b.atIndex(i).mine ||
            a.atIndex(i).adj != b.atIndex(i).adj) { same = false; break; }
    }
    CHECK(same, "相同种子应生成完全相同的雷区");
    Board c;
    c.reset(presetIntermediate(), 20240103);
    int diff = 0;
    for (int i = 0; i < a.cols() * a.rows(); ++i) {
        if (a.atIndex(i).mine != c.atIndex(i).mine) ++diff;
    }
    CHECK(diff > 0, "不同种子应生成不同的雷区");
    done();
}

int main(int argc, char** argv) {
    for (int i = 1; i < argc; ++i) {
        if (std::string(argv[i]) == "-v") g_verbose = true;
    }
    std::printf("扫雷核心逻辑自测\n");
    std::printf("----------------\n");
    test_presets_and_reset();
    test_first_click_safety();
    test_adjacency();
    test_flood_fill();
    test_win();
    test_lose();
    test_flag_cycle();
    test_chord();
    test_bounds();
    test_reproducible();
    test_random_play();
    std::printf("----------------\n");
    std::printf("%d 项断言，%d 项失败\n", g_checks, g_fails);
    return g_fails == 0 ? 0 : 1;
}
