---
name: make-figure
description: lab.toml のあるプロジェクトで図・グラフ・プロットを作るときの唯一の手順。figspecs/*.toml を書き labkit fig で出力する。描画ライブラリを直接使わない。
---

# 図を作る

図はすべて labkit の図テンプレートで作る。matplotlib などを直接使うコードは hooks がブロックする。

1. **テンプレートを選ぶ**: `uv run labkit fig list` で一覧と必須キー・例を確認する。
   timeseries, band（平均±帯）, spectrogram, psd, learning_curve, errorbar（類別または数値 x、log 軸可）, bar, scatter, heatmap, histogram, boxplot（分布）, convergence（両対数の収束と次数）, panels（複数パネル）
2. **データを用意する**: 図に必要な値は run の中に保存しておく（`save(runpath(run, "x.h5"), ...)`、表なら `.parquet`）。集計は src の関数で行いスクリプトで保存する（図テンプレートで計算しない）。
3. **figspec を書く**: `figspecs/<name>.toml`
   ```toml
   template = "timeseries"
   name = "filtered_vs_raw"        # 出力ファイル名
   size = "double"                 # single | onehalf | double | square | slide | [幅, 高さ]（inch）
   description = "図の意図"

   [data]
   file = "signal.h5"              # run 内の相対パス。data/ のファイルは "data:processed/x.parquet"
   x = "t"
   y = ["raw", "filtered"]
   legend = ["raw", "filtered"]

   [labels]
   x = "Time [s]"                  # 物理量と単位を必ず書く
   y = "Voltage [µV]"

   [options]                       # xlim, ylim, logx, logy, grid, legend, legend_loc, aspect
   xlim = [0, 2]
   ```
   複数パネル:
   ```toml
   template = "panels"
   layout = [1, 2]
   size = "double"
   [[panel]]
   template = "timeseries"
   data = {file = "s.h5", x = "t", y = "x"}
   labels = {title = "signal", x = "Time [s]", y = "a.u."}
   [[panel]]
   template = "psd"
   data = {file = "s.h5", signal = "x", fs = 1000.0}
   ```
4. **出力する**: `uv run labkit fig figspecs/<name>.toml --run <run_id>`
   → `runs/<run_id>/figures/<name>.pdf`, `.png`, `.figmeta.json`（spec の写し、使ったデータの sha256、commit）
5. **確認する**: png を Read で開いて見た目を確認し、軸ラベル・単位・凡例・範囲を figspec で直す。

## 合うテンプレートが無いとき

プロジェクト内で描画コードを書かない。skill: add-figure-template に従い、必要な図の仕様を人間に提案する。
