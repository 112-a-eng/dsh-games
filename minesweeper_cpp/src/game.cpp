// 扫雷核心逻辑实现
#include "game.h"

#include <algorithm>
#include <cstdlib>

namespace sweeper {

namespace {
const int DX[8] = {1, 1, 1, 0, 0, -1, -1, -1};
const int DY[8] = {-1, 0, 1, -1, 1, -1, 0, 1};

// 参数校正：尺寸有上下限，雷数必须留出安全首点的空间
void configClamp(Config& c) {
    if (c.cols < 2) c.cols = 2;
    if (c.rows < 2) c.rows = 2;
    if (c.cols > 100) c.cols = 100;
    if (c.rows > 100) c.rows = 100;
    const int total = c.cols * c.rows;
    int maxMines = total - 9;          // 保证首点 3x3 安全区一定能放下
    if (maxMines < 1) maxMines = 1;
    if (c.mines < 1) c.mines = 1;
    if (c.mines > maxMines) c.mines = maxMines;
    if (!c.name) c.name = "自定义";
}
}  // namespace

Config presetBeginner() {
    Config c;
    c.cols = 9; c.rows = 9; c.mines = 10; c.name = "初级";
    return c;
}

Config presetIntermediate() {
    Config c;
    c.cols = 16; c.rows = 16; c.mines = 40; c.name = "中级";
    return c;
}

Config presetExpert() {
    Config c;
    c.cols = 30; c.rows = 16; c.mines = 99; c.name = "高级";
    return c;
}

Config customConfig(int cols, int rows, int mines) {
    Config c;
    c.cols = cols; c.rows = rows; c.mines = mines; c.name = "自定义";
    return c;
}

void Board::reset(const Config& cfg, uint32_t seed) {
    cfg_ = cfg;
    configClamp(cfg_);
    cells_.assign((size_t)cfg_.cols * cfg_.rows, Cell{});
    status_ = Status::Ready;
    placed_ = false;
    flags_ = 0;
    revealed_ = 0;
    cursor_ = -1;
    if (seed == 0) {
        std::random_device rd;
        rng_.seed(rd());
    } else {
        rng_.seed(seed);
    }
}

int Board::neighborMines(int x, int y) const {
    int n = 0;
    for (int k = 0; k < 8; ++k) {
        int nx = x + DX[k], ny = y + DY[k];
        if (inBounds(nx, ny) && cells_[(size_t)index(nx, ny)].mine) ++n;
    }
    return n;
}

void Board::placeMines(int safeX, int safeY) {
    const int total = cfg_.cols * cfg_.rows;
    std::vector<int> pool;
    pool.reserve((size_t)total);

    for (int i = 0; i < total; ++i) {
        if (cfg_.safe_first_click && safeX >= 0) {
            const int x = i % cfg_.cols;
            const int y = i / cfg_.cols;
            // 首点及其周围 8 格都不放雷，保证开局一定能展开
            if (std::abs(x - safeX) <= 1 && std::abs(y - safeY) <= 1) continue;
        }
        pool.push_back(i);
    }
    // 雷太多导致安全区不够用时，退化为全盘随机（自定义极限参数才会走到）
    if ((int)pool.size() < cfg_.mines) {
        pool.clear();
        for (int i = 0; i < total; ++i) pool.push_back(i);
    }

    std::shuffle(pool.begin(), pool.end(), rng_);
    for (int k = 0; k < cfg_.mines; ++k) cells_[(size_t)pool[(size_t)k]].mine = true;
    computeAdjacency();
    placed_ = true;
}

void Board::computeAdjacency() {
    for (int y = 0; y < cfg_.rows; ++y) {
        for (int x = 0; x < cfg_.cols; ++x) {
            Cell& c = cells_[(size_t)index(x, y)];
            c.adj = c.mine ? 0 : (uint8_t)neighborMines(x, y);
        }
    }
}

void Board::floodReveal(int startIndex) {
    std::vector<int> stack;
    stack.push_back(startIndex);
    while (!stack.empty()) {
        const int i = stack.back();
        stack.pop_back();
        Cell& c = cells_[(size_t)i];
        if (c.state == REVEALED || c.state == FLAGGED) continue;
        if (c.mine) continue;                    // 洪水展开不会踩雷
        c.state = REVEALED;
        ++revealed_;
        if (c.adj != 0) continue;
        // 数字为 0 才继续向外扩散
        const int x = i % cfg_.cols;
        const int y = i / cfg_.cols;
        for (int k = 0; k < 8; ++k) {
            const int nx = x + DX[k], ny = y + DY[k];
            if (!inBounds(nx, ny)) continue;
            const uint8_t st = cells_[(size_t)index(nx, ny)].state;
            if (st == HIDDEN || st == QUESTION) stack.push_back(index(nx, ny));
        }
    }
}

void Board::revealAllMines() {
    for (Cell& c : cells_) {
        if (c.mine && c.state != FLAGGED) c.state = REVEALED;
        if (!c.mine && c.state == FLAGGED) c.wrong_flag = true;
    }
}

void Board::checkWin() {
    if (status_ != Status::Playing) return;
    if (revealed_ < safeTotal()) return;
    status_ = Status::Won;
    for (Cell& c : cells_) {
        if (c.mine && c.state != FLAGGED) {
            c.state = FLAGGED;
            ++flags_;
        }
    }
}

bool Board::revealImpl(int x, int y) {
    if (!inBounds(x, y)) return false;
    Cell& c = cells_[(size_t)index(x, y)];
    if (c.state == REVEALED || c.state == FLAGGED) return false;

    if (!placed_) {
        placeMines(x, y);
        status_ = Status::Playing;
    }
    if (c.mine) {                    // 踩雷
        c.state = REVEALED;
        c.exploded = true;
        status_ = Status::Lost;
        revealAllMines();
        return true;
    }
    floodReveal(index(x, y));
    checkWin();
    return true;
}

bool Board::reveal(int x, int y) {
    if (finished()) return false;
    return revealImpl(x, y);
}

bool Board::chord(int x, int y) {
    if (status_ != Status::Playing || !inBounds(x, y)) return false;
    const Cell& c = cells_[(size_t)index(x, y)];
    if (c.state != REVEALED || c.adj == 0) return false;

    int flagged = 0;
    for (int k = 0; k < 8; ++k) {
        const int nx = x + DX[k], ny = y + DY[k];
        if (inBounds(nx, ny) && cells_[(size_t)index(nx, ny)].state == FLAGGED) ++flagged;
    }
    if (flagged != c.adj) return false;

    bool changed = false;
    for (int k = 0; k < 8; ++k) {
        const int nx = x + DX[k], ny = y + DY[k];
        if (!inBounds(nx, ny)) continue;
        const uint8_t st = cells_[(size_t)index(nx, ny)].state;
        if (st != HIDDEN && st != QUESTION) continue;
        changed |= revealImpl(nx, ny);
        if (status_ == Status::Lost) break;      // 猜错了就到此为止
    }
    return changed;
}

bool Board::toggleFlag(int x, int y) {
    if (finished() || !inBounds(x, y)) return false;
    Cell& c = cells_[(size_t)index(x, y)];
    switch (c.state) {
        case HIDDEN:
            c.state = FLAGGED;
            ++flags_;
            return true;
        case FLAGGED:
            --flags_;
            c.state = cfg_.question_marks ? QUESTION : HIDDEN;
            return true;
        case QUESTION:
            c.state = HIDDEN;
            return true;
        default:
            return false;                        // 已翻开的格子不能插旗
    }
}

}  // namespace sweeper
