---
name: write-devlog
description: lab.toml のあるプロジェクトで開発ログ（docs/devlog/YYYY-MM-DD.md）を書く・追記するときの書式。run の数値は `labkit cite` の検証可能な書式で書く。コードや設定を変更したセッションの終わりに必ず使う。
---

# 開発ログを書く

1. `uv run labkit devlog` を実行する。今日のファイル `docs/devlog/YYYY-MM-DD.md` が無ければテンプレートから作られ、パスが表示される。
2. 必須見出し（`labkit check` が確認する）に沿って書く。同じ日の 2 回目以降のセッションは、各見出しの下に `### HH:MM` を付けて追記する。既存の記述は消さない。

| 見出し | 書くこと |
|---|---|
| 目的 | このセッションで達成しようとしたこと（1〜3 行） |
| 実施内容 | 行ったことを箇条書き。試して捨てた方法も書く |
| 変更ファイル | 変更したファイルと要点（`git status` / `git diff --stat` を見て正確に） |
| 実行した run | `runs/<run_id>` と目的・設定の差分・結果の要約。失敗した run も |
| 結果・観察 | 数値（下記の書式）と図（`runs/<id>/figures/<name>.png`）への参照。推測と事実を分ける |
| 判断と理由 | なぜその方法・パラメータを選んだか。重要なら ADR を作りリンク |
| 未解決・次の作業 | 残った問題、次にやること、承認待ち・質問の ID（`labkit queue list`） |

## run の数値の書式（labkit check L032 / L033 が実データと照合する）

数値は記憶や画面のコピーではなく、コマンドの出力を貼る:

```bash
uv run labkit cite <run_id> snr_db --unit dB            # → 12.35 dB [run:20261101-091500_example_0d3f5c2_a8c6:snr_db]
uv run labkit cite <run_id> snr_db --digits 1 --unit dB  # → 12.3 dB [run:...:snr_db]
```

- `[run:<run_id>:<key>]` の run_id は完全な ID。check は run が `runs/` にあり `meta.json` があること、
  表示桁で丸めた値が `metrics.json` と一致することを確かめる。
- run ID と同じ行に書式のない数値を書くと警告になる（日付・時刻は除く）。
- failed / interrupted の run や、link 中の labkit で実行した run を結果として引用すると警告になる。
- HPC の run は `meta.json` と `metrics.json` だけ手元に同期すればよい（skill hpc-job）。

## 書き方

- 事実（実行結果・数値）と解釈・推測を区別する（「〜と考えられる」）。
- レビューする人が差分を読まずに全体像をつかめるように書く。冗長な経緯より、判断と結果を優先する。
