# lab-standards（本体）のメンテナンス規約

このリポジトリは複数の研究プロジェクトが継承する標準。変更はすべてのプロジェクトに波及するので、慎重に変える。
多くの場合、作業はプロジェクトのセッションから `/add-dir` で開かれる（skill: improve-standards）。

## 構成と影響範囲

| 変更する場所 | 影響 | プロジェクトへの反映 |
|---|---|---|
| `template/`, `copier.yml` | 新規プロジェクトと `copier update` | `labkit standards template --ref vX.Y.Z` |
| `labkit/python/` | Python 側の保存・run・図・check | `labkit standards unlink --to vX.Y.Z` |
| `labkit/julia/LabKit/` | Julia 側の保存・run | 同上 |
| `claude-plugin/` | Claude の hooks・skills・agent | `/plugin marketplace update lab-standards` |

## 必ず守ること

1. **main で直接作業しない**。`feat/<名前>` ブランチで作業し、リリース時にマージする。
2. **Python と Julia を揃える**。関数名・引数・ファイル形式（meta.json、サイドカー、HDF5 の軸順）を変えたら両方を直す。スキーマは `labkit/python/src/labkit/schemas/` が正本。
3. **テストを書いて通す**:
   ```bash
   (cd labkit/python && uv run --extra dev pytest -q)
   uv run --with pytest pytest -q claude-plugin/tests
   julia --project=labkit/julia/LabKit -e 'using Pkg; Pkg.test()'   # Julia を変えたとき
   ```
   図テンプレートを追加したら `labkit/python/tests/test_io.py::test_figure_templates` に例を足す。
4. **後方互換を保つ**。既存プロジェクトの `lab.toml`、figspec、run の meta.json が新しい版でもそのまま動くこと。
   壊す場合はメジャー版を上げ、`docs/decisions/` に ADR を書き、CHANGELOG に移行手順を書く。
5. **新しい規約には機械的な検証を付ける**（check のルール、hook、スキーマ）。文章だけの規約を増やさない。
   check のルールを足したら、`labkit/python/src/labkit/check.py` 冒頭のコード一覧と README を更新する。
6. **プロジェクト固有の事情を入れない**。他のプロジェクトで使わないものは、そのプロジェクトの `lab.toml` で例外にする。
7. **hooks は標準ライブラリだけで書く**（Python 3.11+）。`lab.toml` が無いディレクトリでは何もしないこと。

## リリース手順

1. `CHANGELOG.md` の先頭に `## vX.Y.Z — YYYY-MM-DD` の節を書く（追加・変更・移行手順）。
2. `python tools/release.py X.Y.Z` で全ファイルの版を揃える（labkit, LabKit.jl, plugin, 雛形の既定値）。
3. テストを通し、commit → main にマージ → `git tag vX.Y.Z` → `git push origin main --tags`。push は人間の承認後。

版の付け方: 互換を保つ機能追加はマイナー（0.2.0 → 0.3.0）、修正のみはパッチ（0.2.1）、互換を壊す変更はメジャー。
