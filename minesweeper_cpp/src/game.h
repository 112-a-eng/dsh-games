// 扫雷核心逻辑：纯 C++ 实现，不依赖任何 Windows API，因此可以单独做单元测试。
#pragma once

#include <cstdint>
#include <random>
#include <vector>

namespace sweeper {

// 格子状态
enum CellState : uint8_t {
    HIDDEN = 0,     // 未翻开
    REVEALED = 1,   // 已翻开
    FLAGGED = 2,    // 插旗
    QUESTION = 3,   // 问号（可关闭）
};

// 局面状态
enum class Status { Ready, Playing, Won, Lost };

struct Cell {
    bool mine = false;        // 是否是雷
    uint8_t adj = 0;          // 周围 8 格的雷数
    uint8_t state = HIDDEN;
    bool exploded = false;    // 踩中的那颗雷（用于绘制红底）
    bool wrong_flag = false;  // 失败后暴露出来的错误插旗
};

struct Config {
    int cols = 9;
    int rows = 9;
    int mines = 10;
    bool question_marks = true;   // 右键循环：旗 → 问号 → 空
    bool safe_first_click = true; // 首次点击保证不是雷，且周围 8 格也没有雷
    const char* name = "初级";
};

Config presetBeginner();       // 9 x 9, 10 雷
Config presetIntermediate();   // 16 x 16, 40 雷
Config presetExpert();         // 30 x 16, 99 雷
Config customConfig(int cols, int rows, int mines);   // 自定义（雷数会被安全截断）

class Board {
public:
    Board() = default;

    // seed == 0 表示用随机源播种；给定种子可完全复现同一局
    void reset(const Config& cfg, uint32_t seed = 0);

    const Config& config() const { return cfg_; }
    int cols() const { return cfg_.cols; }
    int rows() const { return cfg_.rows; }
    int mineCount() const { return cfg_.mines; }
    int safeTotal() const { return cfg_.cols * cfg_.rows - cfg_.mines; }

    bool inBounds(int x, int y) const {
        return x >= 0 && y >= 0 && x < cfg_.cols && y < cfg_.rows;
    }
    int index(int x, int y) const { return y * cfg_.cols + x; }
    const Cell& at(int x, int y) const { return cells_[(size_t)index(x, y)]; }
    const Cell& atIndex(int i) const { return cells_[(size_t)i]; }

    Status status() const { return status_; }
    bool finished() const { return status_ == Status::Won || status_ == Status::Lost; }
    bool minesPlaced() const { return placed_; }
    int flags() const { return flags_; }
    int revealedCount() const { return revealed_; }
    int minesRemaining() const { return cfg_.mines - flags_; }
    int cursor() const { return cursor_; }          // 键盘光标位置（-1 表示无）
    void setCursor(int i) { cursor_ = i; }

    // 三种操作；返回棋盘是否发生变化
    bool reveal(int x, int y);        // 左键
    bool toggleFlag(int x, int y);    // 右键（旗 → 问号 → 空）
    bool chord(int x, int y);         // 双击/双键：周围旗数 == 数字时展开其余邻格

    void setQuestionMarks(bool on) { cfg_.question_marks = on; }
    bool questionMarks() const { return cfg_.question_marks; }

private:
    bool revealImpl(int x, int y);
    void placeMines(int safeX, int safeY);
    void computeAdjacency();
    void floodReveal(int startIndex);
    void revealAllMines();
    void checkWin();
    int neighborMines(int x, int y) const;

    Config cfg_{};
    std::vector<Cell> cells_;
    Status status_ = Status::Ready;
    bool placed_ = false;
    int flags_ = 0;
    int revealed_ = 0;
    int cursor_ = -1;
    std::mt19937 rng_{};
};

}  // namespace sweeper
