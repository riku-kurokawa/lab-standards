---
name: add-figure-template
description: 既存の図テンプレート（labkit fig list）で表現できない図が必要になったときの手順。プロジェクト内では描画せず、lab-standards の labkit にテンプレートを追加する提案を作る。
---

# 図テンプレートを追加する

図のテンプレートは全プロジェクト共通の資産なので、lab-standards リポジトリの
`labkit/python/src/labkit/viz/templates.py` に追加する。プロジェクト側で描画コードは書かない。

## 1. まず既存テンプレートで表現できないか確認する

- `[options]` や `[data]` の組合せ、事前に集計したデータの保存で済まないか。
- 複数パネルが必要なら、まず 1 枚ずつ作ってよいか人間に確認する。

## 2. 人間に提案する（ここで止まる）

次を提示して承認を待つ:
- テンプレート名（snake_case）と用途
- 必須の `[data]` キーと任意キー、入力データの形式（HDF5 の配列名 / Parquet の列）
- figspec の例
- 既存テンプレートでは足りない理由

## 3. 承認後、lab-standards 側で実装する（人間が lab-standards を開いて依頼した場合）

- `@template(name, required_data, description, example)` デコレータで登録する。
- 共通ヘルパ `_fig`, `_labels`, `_options`, `_legend`, `_get` を使い、スタイル（`style.py`）を上書きしない。
- 計算はしない（スペクトルなど標準的な変換を除く）。データの集計はプロジェクト側の src で行う。
- `labkit/python/tests/test_io.py::test_figure_templates` に spec の例を追加し、`pytest` を通す。
- バージョンを上げてタグを打ち、各プロジェクトは `uv run labkit standards unlink --to vX.Y.Z` で取り込む（skill improve-standards の adopt）。
