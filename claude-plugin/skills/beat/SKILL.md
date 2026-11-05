---
name: beat
description: lab.toml のあるプロジェクトで長い自律運用の 1 拍を回す入口（`/loop 20m /lab-rules:beat`）。`labkit beat start` で現行の目標・指示書と状態を読み、指示書の手順を実行し、`labkit beat end` で予想・結果・判断の 3 行を記録する。
---

# 1 拍を回す

1. `uv run labkit beat start`。`prompts/current.toml` が指す現行の goal・beat の本文と状態（今日の run、回答、open な主張、前の拍の判断）が出る。これを読み直す（/goal の本文を貼り直さない）。
   出力に「拍 N は閉じていない」とあれば、その作業の続きをやり、先に `labkit beat end` でその拍を閉じる（end は start した拍にだけ打てる）。
2. 出力された beat ファイルの手順を実行する（手順の正本は beat ファイル。計算の完了を待つだけで拍を終えない）。
3. `uv run labkit beat end --predicted "…" --observed "…" --decided "…" [--runs <id> ...]`。各 1 行、`--decided` は必須。時刻は機械が入れ、開発ログの自動ブロックに「拍（自動）」として写る。
4. `docs/state.md` の該当欄を上書き（積み上げない。L037）、commit。

- current が古い（L005: 指す版が無い・より新しい版がある）ときは、新しい版のファイルを作ったうえで `prompts/current.toml` の `goal` / `beat` をその版に書き換える（古い版は消さない）。
- 4 拍に 1 回の candor-check、1 日 1 回の `labkit digest`、予想の関門と撤回の扱いは skill: autonomous-run。
