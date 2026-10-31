---
name: data-pipeline
description: lab.toml のあるプロジェクトで生データの受け入れ・登録、前処理による派生データ（data/interim, data/processed）の作成、データ辞書の更新を行うときの手順。
---

# データの受け入れと前処理

## 生データ（data/raw）

- 生データの配置は人間が行う。Claude は data/raw に書き込めない（hooks がブロックする）。
- 配置後、人間が `uv run labkit raw freeze` を実行すると `MANIFEST.sha256` に登録され、読み取り専用になる。
- 新しい生データが来たら `docs/data-dictionary.md` の data/raw の表（取得元・取得日・形式・変数・単位）を埋める。分からない項目は空欄にせず「要確認」と書き、人間に尋ねる。
- 形式が HDF5 / Parquet 以外（.mat, .csv, 機器固有形式）でもそのまま置く。変換結果は派生データとして作る。

## 派生データ（data/interim, data/processed）

1. 変換・前処理の計算は `src/<pkg>/` の純粋関数にし、テストを書く。
2. `scripts/prepare_<name>.py` で、読む → 変換 → 保存する。
   ```python
   cfg = load_config(sys.argv[1], sys.argv[2:])
   src = datapath("raw", "rec01.mat")
   with Run("prepare-<name>", cfg, inputs=[src]) as run:
       table = <src の関数>(...)
       save(datapath("processed", "<name>.parquet"), table, inputs=[src],
            description="列の意味は docs/data-dictionary.md 参照", overwrite=True)
   ```
   - 配列は `.h5`、表は `.parquet`。それ以外の形式で保存しない。
   - 再生成のときだけ `overwrite=True`。
   - TB 級で一度にメモリに載らないときは `writer()` で一時パスを受け取り、チャンク単位で書く。
3. `docs/data-dictionary.md` の data/processed の表に、生成スクリプト・変数・単位を追記する。
4. 派生データは消しても `生データ + コード + 設定` から再生成できる状態を保つ。手で修正したデータを作らない。

## 外部データ（data/external）

公開データセットなどは取得スクリプトを `scripts/fetch_<name>.py` に書き、取得元 URL・取得日・ライセンスをデータ辞書に記録する。
