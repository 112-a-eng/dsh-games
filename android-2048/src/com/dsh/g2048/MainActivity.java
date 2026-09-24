package com.dsh.g2048;

import android.app.Activity;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.view.WindowManager;
import android.widget.Toast;

/**
 * 唯一的一个 Activity：负责生命周期、最高分与局面的持久化。
 * 界面全部在 {@link GameView} 里用 Canvas 绘制，没有布局 XML、没有 AndroidX。
 */
public class MainActivity extends Activity implements GameView.Listener {

    private static final String PREFS = "g2048";
    private static final String KEY_BEST = "best";
    private static final String KEY_BOARD = "board";
    private static final String KEY_SCORE = "score";

    private SharedPreferences prefs;
    private Game game;
    private GameView view;
    private int best;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        best = prefs.getInt(KEY_BEST, 0);

        game = new Game();
        String saved = prefs.getString(KEY_BOARD, null);
        if (saved != null) {
            int[] board = parse(saved);
            if (board != null) {
                game.restore(board, prefs.getInt(KEY_SCORE, 0));
            }
        }

        view = new GameView(this, game, best, this);
        setContentView(view);
        view.notifyScore();
    }

    @Override
    protected void onPause() {
        super.onPause();
        save();
    }

    @Override
    protected void onDestroy() {
        save();
        super.onDestroy();
    }

    private void save() {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 16; i++) {
            if (i > 0) sb.append(',');
            sb.append(game.get(i % 4, i / 4));
        }
        prefs.edit()
                .putString(KEY_BOARD, sb.toString())
                .putInt(KEY_SCORE, game.score())
                .putInt(KEY_BEST, Math.max(best, game.score()))
                .apply();
    }

    private static int[] parse(String text) {
        String[] parts = text.split(",");
        if (parts.length != 16) return null;
        int[] board = new int[16];
        try {
            for (int i = 0; i < 16; i++) {
                board[i] = Integer.parseInt(parts[i].trim());
                if (board[i] < 0) return null;
            }
        } catch (NumberFormatException e) {
            return null;
        }
        return board;
    }

    // ------------------------------------------------------------ Listener

    @Override
    public void onScoreChanged(int score, int bestScore) {
        if (score > best) {
            best = score;
            prefs.edit().putInt(KEY_BEST, best).apply();
        }
    }

    @Override
    public void onNewBest(int bestScore) {
        Toast.makeText(this, "新纪录：" + bestScore, Toast.LENGTH_SHORT).show();
    }
}
