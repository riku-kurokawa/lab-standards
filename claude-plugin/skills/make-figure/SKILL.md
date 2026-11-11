---
name: make-figure
description: lab.toml のあるプロジェクトで図・グラフ・プロットを作るときの手順。figspecs/*.toml を書いて labkit fig で出力する（図の元データと体裁が figmeta に残る）。合うテンプレートが無いときの追加の手順も含む。
---

# 図を作る

## 論文・発表の図の約束（比べる図ほど厳しく）
- **比べるものは同じ物差しで**: 複数パネルは `share = "x" | "y" | "both"` で軸の範囲を、`clim = "shared"` でヒートマップの色の範囲をそろえる。別の図に分けるときも `options.xlim/ylim/clim` を同じ値にする。差の図は `diverging = true`（0 中心）。
- **読める文字**: 発表は `style = "slide"`（16 pt、最小 12 pt）、論文は `style = "paper"`（実寸 8 pt、最小 6 pt）。ラベルは物理量と単位、手法名は正確に（略号だけにしない）。
- **重ねない**: 文字どうし・凡例とデータの重なり、小さすぎる文字は `labkit fig` が検査し、`lab.toml` の `[fig] overlap = "error"` なら保存しない（既定は警告と figmeta の `layout_issues`）。
  凡例が重なるなら `legend_loc = "outside"`、文字が詰まるなら `size` を大きくするかラベルを短くする。
- **代表例は図を見る前に決める**（規則を事前に書く）。代表例の図と、全例の分布の図（boxplot・scatter）を両方出す。

図はすべて labkit の図テンプレートで作る。matplotlib などを直接使うコードは hooks がブロックする。

1. **テンプレートを選ぶ**: `uv run labkit fig list` で一覧と必須キー・例を確認する。
   timeseries, band（平均±帯）, spectrogram, psd, learning_curve, errorbar（類別または数値 x、log 軸可）, bar, scatter, heatmap, histogram, boxplot（分布）, convergence（両対数の収束と次数）, panels（複数パネル）
2. **データを用意する**: 図に必要な値は run の中に保存しておく（`save(runpath(run, "x.h5"), ...)`、表なら `.parquet`）。集計は src の関数で行いスクリプトで保存する（図テンプレートで計算しない）。
3. **figspec を書く**: `figspecs/<name>.toml`
   ```toml
   template = "timeseries"
   name = "filtered_vs_raw"        # 出力ファイル名
   size = "double"                 # single | onehalf | double | square | slide | [幅, 高さ]（inch）
   description = "図の意図"         # DIGEST の図の説明に使われる

   [data]
   file = "signal.h5"              # run 内の相対パス。data/ のファイルは "data:processed/x.parquet"
   x = "t"
   y = ["raw", "filtered"]
   legend = ["raw", "filtered"]

   [labels]
   title = "Filtered vs raw"       # DIGEST に写る図の見出し（無いと name が使われる）
   x = "Time [s]"                  # 物理量と単位を必ず書く
   y = "Voltage [µV]"

   style = "paper"                 # paper（論文の実寸、8 pt）| slide（発表、16 pt）

   [options]                       # xlim, ylim, logx, logy, grid, legend, legend_loc（"outside" で軸の外、"direct" で線の横に名前）, hlines / vspan / notes（基準の線・範囲の帯・注記）, aspect, clim（色の範囲）
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
   新しい図は `labkit digest` が `docs/DIGEST.md` に写す（最新 `digest.max_figures` 枚）。人間が図だけ見て分かるよう `labels.title` と `description` を書く。

## 合うテンプレートが無いとき

図のテンプレートは全プロジェクト共通の資産で、来歴（figmeta）もテンプレート経由でだけ付く。プロジェクト内に描画コードは書かず、本体に足す。

1. まず既存で描けないか確かめる: `[options]` の組合せ、`panels`（複数パネル）、`band`（平均±帯）、`errorbar` の `xmode = "numeric"`、事前に集計したデータの保存。
2. 足りない理由を 1 行で言えるなら、本体の `labkit/python/src/labkit/viz/templates.py` に追加する（skill: improve-standards）。
   `@template(name, required_data, description, example)` で登録し、`(spec, ctx, ax) -> None` で渡された軸に描く。共通ヘルパ（`_labels`・`_options`・`_legend`・`_get`・`_col`）を使い、
   スタイルは上書きしない。集計はプロジェクトの src で行い、テンプレートでは計算しない。`tests/test_io.py::test_figure_templates` に例を足す。
