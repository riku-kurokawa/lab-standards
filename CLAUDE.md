# lab-standards（本体）のメンテナンス規約

このリポジトリは複数の研究プロジェクトが継承する標準。変更はすべてのプロジェクトに波及するので、慎重に変える。
目的は「研究記録が検証可能であること」。Claude に何を打たせないかではなく、成果物（run・データ・文書）が検証できるかに投資する。

## 構成と影響範囲

| 変更する場所 | 影響 | プロジェクトへの反映 |
|---|---|---|
| `template/`, `copier.yml` | 新規プロジェクトと `copier update` | `labkit standards template --ref vX.Y.Z` |
| `labkit/python/` | 来歴・保存・図・check・ゲートの判定（`labkit hook`） | `labkit standards unlink --to vX.Y.Z` |
| `claude-plugin/` | hooks の入口・skills・agent | `/plugin marketplace update lab-standards` |

## 必ず守ること

1. **main で直接作業しない**。`feat/<名前>` ブランチで作業し、リリース時にマージする。
2. **小さく保つ**。機能を足すときは、それが無いと成果物が検証できなくなるかを問う。使われていない機能・重複・形骸は削る。
3. **テストを書いて通す**: `make test`（版の整合 + lint + labkit + 雛形の生成）。hooks の判定は `labkit/python/tests/test_hook.py`。
4. **後方互換を保つ**。既存プロジェクトの `lab.toml`、figspec、run の meta.json が新しい版でもそのまま動くこと。壊す場合はメジャー版を上げ、`docs/decisions/` に ADR を書き、CHANGELOG に移行手順を書く。
5. **新しい規約には機械的な検証を付ける**（check のルール、hook、スキーマ）。文章だけの規約を増やさない。check のルールを足したら `check.py` 冒頭と README の表を更新する。
6. **プロジェクト固有の事情を入れない**。他のプロジェクトで使わないものは、そのプロジェクトの `lab.toml` で例外にする。
7. **plugin の入口（`claude-plugin/scripts/hook.py`）は標準ライブラリだけ**。判定は labkit に置く（1 か所）。

## リリース手順

1. `CHANGELOG.md` の先頭に `## vX.Y.Z — YYYY-MM-DD` の節を書く（追加・変更・移行手順）。
2. `python tools/release.py X.Y.Z` で全ファイルの版を揃える。
3. `make test` → commit → `git switch main && git merge --ff-only feat/<名前>` → `git tag vX.Y.Z` → `git push origin main --tags`。
   merge / tag / push は承認ゲートの対象（人間が `labkit approve` か `labkit delegate release`）。

版の付け方: 互換を保つ機能追加はマイナー、修正のみはパッチ、互換を壊す変更はメジャー。
