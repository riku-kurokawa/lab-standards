---
name: write-devlog
description: lab.toml のあるプロジェクトで開発ログ（docs/devlog/YYYY-MM-DD.md）を書く・追記するときの書式。変更ファイル・run・拍の 3 行・コード量は labkit devlog が自動で埋め、人は目的・結果・判断・未解決を書く。run の数値は `labkit cite` の検証可能な書式で書く。コードや設定を変更したセッションの終わりに必ず使う。
---

# 開発ログを書く

1. `uv run labkit devlog` を実行する。今日のファイルが無ければ雛形から作られ、あれば `<!-- labkit:auto -->` ブロック
   （変更ファイル・今日の commit・コード量・今日の run と予想の判定・拍の 3 行）が git と runs/ と `.lab/beats/` から作り直される。自動ブロックは手で書かない。
2. 人が書く見出しは 4 つ。同じ日の 2 回目以降のセッションは各見出しの下に `### HH:MM` を付けて追記し、既存の記述は消さない（手書きの時刻は目安。正の時刻は自動ブロックの拍と run にある）。

| 見出し | 書くこと |
|---|---|
| 目的 | このセッションで達成しようとしたこと（1〜3 行） |
| 結果・観察 | 数値（下記の書式）と図（`runs/<id>/figures/<name>.png`）への参照。事実と解釈を分ける |
| 判断と理由 | なぜその方法・パラメータを選んだか。試して捨てた方法も。重要なら ADR を作りリンク |
| 未解決・次の作業 | 残った問題、次にやること、承認待ち・質問の ID（`labkit queue list`） |

目的・判断と理由・未解決 が空のままだと `labkit check` L030 になり、終了時チェックが止める。見出しだけの殻を作らない。
長い自律運用の拍の 3 行（予想・結果・判断）は `labkit beat end` が「拍（自動）」として写すので、devlog に書き直さない。
人間は devlog ではなく `docs/DIGEST.md`（`labkit digest`）を読む。人間に残したい主張は `labkit claim add` で台帳に入れる（devlog の文章は台帳に乗らない）。

## run の数値の書式（labkit check L032 / L033 / L034 が実データと照合する）

数値は記憶や画面のコピーではなく、コマンドの出力を貼る:

```bash
uv run labkit cite <run_id> snr_db --unit dB            # → 12.35 dB [run:20261101-091500_example_0d3f5c2_a8c6:snr_db]
uv run labkit cite <run_id> snr_db --digits 1 --unit dB  # → 12.3 dB [run:...:snr_db]
```

- check は run が `runs/` にあり、表示桁で丸めた値が `metrics.json` と一致することを確かめる。
- 「結果・観察」節の小数・指数表記の数値に引用が無いと警告（L034。引用を含む行は対象外）。引用したい量は entry の戻り値か `log_metric` で run に記録する。
- 結果として引用できない run: dirty（未コミットの差分あり。`check.dirty_citation`、既定 warn）、failed / interrupted / running、退避済み（`labkit runs archive`）、link 中の labkit で実行。
  scratch/ のファイルを結果の根拠にすると L038（src に entry を書いて commit し、`labkit run` の run を引用する）。
- HPC の run は `meta.json` と `metrics.json` だけ手元に同期すればよい（skill: hpc-job）。

## 自動ブロックの「コード量」の読み方

`- コード量: src 1,240 行（+85、12 ファイル）/ scripts 90 行（+0、1 ファイル）/ tests 610 行（+40、9 ファイル）、300 行超 1 本`
— 空行を除いた行数と、その日の増減（git の差分）、`check.max_file_lines` を超えたファイルの数。tests が増えず src だけ増える日、300 行超が減らない日は、判断の欄に理由を書く。
