---
name: improve-standards
description: プロジェクトで作業中に、lab-standards 本体（雛形・labkit・図テンプレート・check のルール・hooks・skills）を改良したくなったときの手順。プロジェクト内のコピーは直さず、本体を feat ブランチで直してテスト・レビュー・リリースし、タグでプロジェクトに取り込む。
---

# lab-standards 本体を改良してプロジェクトに反映する

## 振り分け

| ケース | 対応 |
|---|---|
| このプロジェクトだけの事情（特定ファイルだけ pickle を許す、一時的にチェックを外す） | 本体は直さない。`lab.toml` の `format_allowed` / `plot_import_allowed` / `skip` の変更案を人間に提示する |
| 他のプロジェクトでも役立つ（図テンプレート、check の改善、skill、雛形） | 下の手順で進める |

## 手順

1. 何を・なぜ・どの部品か を 3〜5 行で今日の開発ログに書く。
2. 本体（`~/dev/lab-standards`、または `$LAB_STANDARDS_DEV`）で `git switch -c feat/<短い名前>`。本体の `CLAUDE.md` を読む。
3. 直す。labkit を変えたなら `uv run labkit standards link` でこのプロジェクトから試す（L050 が出る間は commit しない）。
   雛形を変えたら使い捨ての場所に `copier copy --vcs-ref HEAD` で生成して確認する。
4. 本体で `make test`（版の整合 + lint + テスト + 雛形の生成）。
5. **Agent ツールで lab-reviewer を起動**し、本体の差分のレビュー記録をこのプロジェクトの `docs/reviews/`（`labkit review template adhoc standards`）に書かせる。pass まで直す。
6. 本体の `CHANGELOG.md` に `## vX.Y.Z` の節を書き、`python tools/release.py X.Y.Z`、commit。feat ブランチの push は自由。
   `git switch main && git merge --ff-only feat/<名前>`、`git tag vX.Y.Z`、`git push origin main --tags` は承認ゲートの対象
   （人間が `labkit approve` か `labkit delegate release`）。
7. このプロジェクトで `uv run labkit standards unlink --to vX.Y.Z` → commit → `uv run labkit standards template --ref vX.Y.Z`（衝突を解消）→ `make check` → commit。
8. 開発ログに「lab-standards vX.Y.Z に更新（変更点・理由）」。他の PC では `/plugin marketplace update lab-standards` が必要と伝える。

他のプロジェクトは自動では更新しない。各プロジェクトの都合のよいときに 7 の手順で取り込む。
