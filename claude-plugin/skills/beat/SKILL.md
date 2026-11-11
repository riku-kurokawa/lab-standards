---
name: beat
description: lab.toml のあるプロジェクトで長い自律運用の 1 拍を回す入口（`/loop 20m /lab-rules:beat`）。`labkit beat start` で現行の目標・指示書と状態を読み、指示書の手順を実行し、`labkit beat end` で予想・結果・判断の 3 行を記録する。
---

# 1 拍を回す

1. `uv run labkit beat start`。`prompts/current.toml` が指す現行の goal・beat の本文と状態（主線の残り時間・主線の割合・芽・直近 24 時間の資源の使い道、今日の run、open な主張、前の拍の判断）が出る。これを読み直す（/goal の本文を貼り直さない）。
   出力に「拍 N は閉じていない」とあれば、その作業の続きをやり、先に `labkit beat end` でその拍を閉じる（end は start した拍にだけ打てる）。
   出力の先頭に「人間の返信 N00x」があれば、この拍で最初に対応し、`uv run labkit note done N00x --reply "<何を変えたか。変えないなら理由>"` で答える（フィードの同じ投稿のスレッドに出る）。
2. 出力された beat ファイルの手順を実行する（手順の正本は beat ファイル。計算の完了を待つだけで拍を終えない）。
3. `uv run labkit beat end --line main:Mxxx|seed:Sxxx|other --predicted "…" --observed "…" --decided "…" [--runs <id> ...]`。各 1 行、`--decided` は必須。
   主線の拍は進めた open の項目を名指しする。進められる項目が無い主線では拍は記録されない（先に `labkit main add`。人間待ちは `labkit main block`）。主線に open の項目があると `--line` が必須で、主線の割合・期限・芽の頻度を満たさない拍は記録されない（理由とやるべきことが出る。従う）。時刻は機械が入れ、開発ログの自動ブロックに「拍（自動）」として写る。
4. 自問する: この拍で、人間の理解か判断が変わることが起きたか。起きたときだけ `uv run labkit post` で 1 件投稿する（しないのが既定。何を・どの図で・どう書くかは [post.md](post.md)）。
5. `docs/state.md` の該当欄を上書き（積み上げない。L037）、commit。

- current が古い（L005: 指す版が無い・より新しい版がある）ときは、新しい版のファイルを作ったうえで `prompts/current.toml` の `goal` / `beat` をその版に書き換える（古い版は消さない）。
- 同じ判断・結果（数字の揺れを除く）で run の無い拍が `autonomy.stall_beats` 回（既定 3）続くと、`labkit beat end` は記録を拒む。資源の停止は人間の停止ではない: 原因を外して止まった計算を再開するか、台帳の統合など人間を要しない仕事を始める。本当に待つしかないときだけ `--stall-reason` に理由を書く（停滞として開発ログと digest に残る）。
- 4 拍に 1 回の candor-check、予想の関門と撤回の扱いは skill: autonomous-run。人間の入口 `docs/DIGEST.md` は `beat end` が古くなったら作り直す。
