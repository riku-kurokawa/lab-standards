# notebooks/

探索用。命名は `NN_<内容>.ipynb`（例: `01_explore-raw.ipynb`）。

- 出力は commit 前に nbstripout で消える。
- `src` から import されない（依存は notebooks → src の一方向）。
- 描画ライブラリの直接 import は禁止（`labkit check` L010）。図は `labkit.fig()` で作る。
- 報告に使う数値・図は scripts 化して run にする。文書からの引用は L032/L033 が runs/ と照合するので、notebook の出力は引用できない。
