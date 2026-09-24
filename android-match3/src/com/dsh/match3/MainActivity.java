package com.dsh.match3;

import android.app.Activity;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.view.WindowManager;
import android.widget.Toast;

/**
 * 唯一的一个 Activity：负责生命周期与进度持久化。
 * 界面全部在 {@link GameView} 里用 Canvas 绘制，没有布局 XML、没有 AndroidX。
 */
public class MainActivity extends Activity implements GameView.Listener {

    private static final String PREFS = "match3";
    private static final String KEY_LEVEL = "level";
    private static final String KEY_STARS = "stars";

    private SharedPreferences prefs;
    private Board board;
    private GameView view;
    private int level;
    private int[] stars;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);

        level = Math.max(1, prefs.getInt(KEY_LEVEL, 1));
        stars = parseStars(prefs.getString(KEY_STARS, ""), level);

        board = new Board();
        board.newLevel(level);

        view = new GameView(this, board, this);
        setContentView(view);
    }

    @Override
    protected void onPause() {
        super.onPause();
        save();
    }

    private void save() {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < stars.length; i++) {
            if (i > 0) sb.append(',');
            sb.append(stars[i]);
        }
        prefs.edit()
                .putInt(KEY_LEVEL, level)
                .putString(KEY_STARS, sb.toString())
                .apply();
    }

    private static int[] parseStars(String text, int level) {
        int[] out = new int[Math.max(8, level + 1)];
        if (text == null || text.isEmpty()) return out;
        String[] parts = text.split(",");
        for (int i = 0; i < parts.length && i < out.length; i++) {
            try {
                out[i] = Integer.parseInt(parts[i].trim());
            } catch (NumberFormatException ignored) {
                out[i] = 0;
            }
        }
        return out;
    }

    private void ensureCapacity(int index) {
        if (index < stars.length) return;
        int[] bigger = java.util.Arrays.copyOf(stars, index + 8);
        stars = bigger;
    }

    // ------------------------------------------------------------ Listener

    @Override
    public void onScoreChanged(int score, int movesLeft) {
        // 每一次有效移动都会回调，这里只更新界面，不用每次都写盘
    }

    @Override
    public void onLevelComplete(int completedLevel, int earnedStars, int score) {
        ensureCapacity(completedLevel);
        stars[completedLevel - 1] = Math.max(stars[completedLevel - 1], earnedStars);
        level = completedLevel + 1;
        ensureCapacity(level);
        save();
        Toast.makeText(this, "第 " + completedLevel + " 关过关：" + earnedStars + " 星",
                Toast.LENGTH_SHORT).show();
    }

    @Override
    public void onLevelFailed(int failedLevel, int score) {
        Toast.makeText(this, "步数用完了，得 " + score + " 分", Toast.LENGTH_SHORT).show();
    }
}
