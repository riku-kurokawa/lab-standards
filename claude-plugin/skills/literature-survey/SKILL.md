---
name: literature-survey
description: lab.toml のあるプロジェクトで先行研究のサーベイ、論文の追加・整理、PDF の保存、読書ノート作成を行うときの手順。literature/ の references.bib・notes・surveys を規約どおりに作り、読んだ範囲（read_by・read_scope・claims）とサーベイの判定（verdict・n_opened）を正直に残す。
---

# 文献サーベイと文献管理

## サーベイの進め方

1. **問いを決めて雛形を作る**: `uv run labkit lit survey --question "<調査の問い>" --slug <english-slug>`
   → `literature/surveys/YYYY-MM-DD_<slug>.md`
2. **検索方法を先に書く**: frontmatter の `search`（sources, queries, period, inclusion, exclusion）を埋めてから検索する。実際に使った検索語は後から追記する。
3. **検索する**: Web 検索で候補を集める。各候補について、DOI・arXiv ID・出版先を一次情報（出版社ページ、arXiv、DOI 解決先）で確認する。**存在を確認できない文献は登録しない**（記憶から書誌を作らない）。
4. **文献を登録する**（1 件ずつ）: `uv run labkit lit add --doi 10.xxxx/yyy --tags <tags.toml にあるタグ>`（arXiv なら `--arxiv 2606.09554`）。
   書誌は doi.org / arXiv から取得され、出所と取得日が `source` フィールドに残る。どちらも無い文献だけ、出版社の Export を `scratch/entry.bib` に写して `--file`。
   → `references.bib` に追記（citekey 自動生成、DOI 重複は拒否）、`notes/<citekey>.md` の雛形を作成、INDEX.md 更新。
   タグが足りないときは `tags.toml` への追加を人間に提案する（表記ゆれを作らない）。
5. **ノートを書く**: `notes/<citekey>.md` の 4 見出し（一言でいうと / 主な結果 / 限界・疑問点 / 自分の研究との関係）に沿って要約し、frontmatter を正直に付ける:
   `status`（unread / skimmed / read / key）、`read_scope`（none / abstract / sections / full）、`claims: []`（この論文から確立したこと 1〜3 行。主張の根拠に使う）、`relevance`（1〜5）。
   アブストラクトしか読んでいなければ skimmed のまま。read / key にするなら claims と sections 以上の read_scope が要る（L047）。
   読んだ範囲の更新は `uv run labkit lit read <citekey> --by agent --scope sections --status read`。`read_by` は誰が読んだか（agent / human / both）で、`--by human` は人間が打つ。
6. **サーベイ本文を書く**: 主張ごとに `[@citekey]` を付ける。手法の比較表、未解決の問題、本研究への示唆を書く。引用は references.bib にあるものだけ（L046）。
   `status: done` にするときは frontmatter の `verdict`（novel / known / partly / inconclusive。問いへの答えを 1 語で）と `n_opened`（一次情報を実際に開いた件数）を書く（L048）。
7. 最後に `uv run labkit lit index` と `uv run labkit check`（L040〜L048 が書式・タグ・引用・正直さを検査する）。

## 人間の入口

- `uv run labkit lit queue [--min-relevance 4]` は人間の読書キュー（`read_by` が human/both でないノートを relevance 順に）。人間に読んでほしい論文は relevance を上げ、claims を書いておく。
- `uv run labkit lit surveys` はサーベイの一覧（status / verdict / n_opened）。INDEX.md の先頭には relevance ≥ 4 の要点（claims の 1 行目）と、読んだ・使用の列が出る。

## PDF

- ダウンロードした PDF はまず `literature/inbox/` に置く。登録時に `--pdf literature/inbox/<file>.pdf` を付けると `literature/pdfs/<citekey>.pdf` に移動される。
- PDF は git 管理外（著作物・容量）。オープンアクセスでないものを Claude が取得しようとしない。人間に入手を依頼する。

## 規約

- citekey = 第一著者姓（小文字 ASCII）+ 年 + タイトル最初の実語（例: `muller2023fast`）。衝突時は `--key` で末尾に a, b を付ける。
- 本文の引用は要約で書き、原文の長い引用をしない（引用はページ番号つきで短く）。
