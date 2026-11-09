---
name: add-figure-template
description: 既存の図テンプレート（labkit fig list）で表現できない図が必要になったときの手順。プロジェクト内では描画せず、lab-standards の labkit にテンプレートを追加する提案を作る。
---

# 図テンプレートを追加する

図のテンプレートは全プロジェクト共通の資産なので、lab-standards の `labkit/python/src/labkit/viz/templates.py` に追加する。
プロジェクト側で描画コードは書かない。

## 1. まず既存テンプレートで表現できないか確認する

- `[options]`（xlim, ylim, logx, logy, grid, legend, aspect）や `[data]` の組合せ、事前に集計したデータの保存で済まないか。
- 複数パネルは `panels`、平均±帯は `band`、数値 x の比較は `errorbar` の `xmode = "numeric"` で描ける。

## 2. 案を書く

次を本体の issue か CHANGELOG の案に書く（承認は待たない。既存テンプレートで足りない理由を言えないなら作らない）:
- テンプレート名（snake_case）と用途
- 必須の `[data]` キーと任意キー、入力データの形式（HDF5 の配列名 / Parquet の列）
- figspec の例
- 既存テンプレートでは足りない理由

## 3. lab-standards 側で実装する（skill: improve-standards）

- `@template(name, required_data, description, example)` で登録し、`(spec, ctx, ax) -> None` で渡された軸に描く。
- 共通ヘルパ `_labels`, `_options`, `_legend`, `_get`, `_col` を使い、スタイル（`style.py`）を上書きしない。
- 計算はしない（スペクトルなど標準的な変換を除く）。データの集計はプロジェクト側の src で行う。
- `labkit/python/tests/test_io.py::test_figure_templates` に spec の例を追加し、`REGISTRY` の件数を更新する。
