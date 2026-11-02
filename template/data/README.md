# data/

| ディレクトリ | 中身 | 規則 |
|---|---|---|
| `raw/` | 取得した生データ | **不変**。`labkit raw freeze` で `MANIFEST.sha256` に登録し読み取り専用化。git には MANIFEST だけ |
| `external/` | 外部から取得したデータ（公開データセット等） | 取得元 URL・取得日・ライセンスを `docs/data-dictionary.md` に記録 |
| `interim/` | 中間生成物 | `labkit.save` / `writer` 経由でのみ作る（サイドカー付き）。消してよい |
| `processed/` | 解析に使う最終派生データ | 同上。生データ + コード + 設定から再生成できること |
| `cache/` | 再生成できるキャッシュ（前計算、学習の中間重みなど） | サイドカー不要・引用不可（check の対象外）。消してよい |

- 形式: 配列は HDF5（`.h5`）、表は Parquet（`.parquet`）。pickle は使わない。`np.save` は来歴が付かない（L016 警告）。
- 各ファイルに `<name>.meta.json`（sha256・作成 run・入力・属性）が付く。run の `inputs` はこれを辿って系譜を記録する。
- HPC では `LAB_ENV=hpc` にすると `configs/paths/hpc.toml` の `data_root` が使われる。
- 列・変数の意味と単位は `docs/data-dictionary.md` に書く。
- この下は git 管理外。`labkit mirror push` で `configs/paths/*.toml` の `mirror_root` に写す。
