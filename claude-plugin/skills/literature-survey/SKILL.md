---
name: literature-survey
description: lab.toml のあるプロジェクトで先行研究のサーベイ、論文の追加・整理、PDF の保存、読書ノート作成を行うときの手順。literature/ の references.bib・notes・surveys を規約どおりに作る。
---

# 文献サーベイと文献管理

## サーベイの進め方

1. **問いを決めて雛形を作る**: `uv run labkit lit survey --question "<調査の問い>" --slug <english-slug>`
   → `literature/surveys/YYYY-MM-DD_<slug>.md`
2. **検索方法を先に書く**: frontmatter の `search`（sources, queries, period, inclusion, exclusion）を埋めてから検索する。実際に使った検索語は後から追記する。
3. **検索する**: Web 検索で候補を集める。各候補について、DOI・arXiv ID・出版先を一次情報（出版社ページ、arXiv、DOI 解決先）で確認する。**存在を確認できない文献は登録しない**（記憶から書誌を作らない）。
4. **文献を登録する**（1 件ずつ）:
   - BibTeX を一次情報（出版社の Export / arXiv の BibTeX / doi.org の内容）から作り、`scratch/entry.bib` に書く。
   - `uv run labkit lit add --file scratch/entry.bib --tags <tags.toml にあるタグ>`
     → `references.bib` に追記（citekey 自動生成、DOI 重複は拒否）、`notes/<citekey>.md` の雛形を作成、INDEX.md 更新。
   - タグが足りないときは `tags.toml` への追加を人間に提案する（表記ゆれを作らない）。
5. **ノートを書く**: `notes/<citekey>.md` の見出しに沿って要約する。読んだ範囲に応じて `status`（unread / skimmed / read / key）を正直に付ける。アブストラクトしか読んでいなければ skimmed。
6. **サーベイ本文を書く**: 主張ごとに `[@citekey]` を付ける。手法の比較表、未解決の問題、本研究への示唆を書く。引用は references.bib にあるものだけ（`labkit check` L046 が検査）。
7. 最後に `uv run labkit lit index` と `uv run labkit check`。

## PDF

- ダウンロードした PDF はまず `literature/inbox/` に置く。
- 登録時に `--pdf literature/inbox/<file>.pdf` を付けると `literature/pdfs/<citekey>.pdf` に移動される。
- PDF は git 管理外（著作物・容量）。オープンアクセスでないものを Claude が取得しようとしない。人間に入手を依頼する。

## 規約

- citekey = 第一著者姓（小文字 ASCII）+ 年 + タイトル最初の実語（例: `muller2023fast`）。衝突時は `--key` で末尾に a, b を付ける。
- 本文の引用は要約で書き、原文の長い引用をしない（引用はページ番号つきで短く）。
