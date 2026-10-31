---
name: hpc-job
description: lab.toml のあるプロジェクトで HPC（Slurm など）向けのジョブスクリプト作成、パラメータスイープの配列ジョブ、HPC と手元の結果のやりとりを行うときの手順。
---

# HPC ジョブ

## 原則

- コードは git でのみ移す（手元で commit → push → HPC で pull）。HPC 上でコードを編集しない。
- データと run は HPC のストレージに置く。パスは `configs/paths/hpc.toml`、実行時は `LAB_ENV=hpc`。
- 手元へは小さな成果物（`meta.json`, `metrics.json`, `figures/`）だけを持ってくる。

## ジョブスクリプトを作る

1. `jobs/slurm_example.sh` をコピーして `jobs/<name>.sh` を作る。変えるのは `#SBATCH` 行と最後のコマンドだけ。
2. 必ず残す部分: `export LAB_ENV=hpc`、未コミット変更チェック、`set -euo pipefail`。
3. 資源量（time, mem, cpus, gpus）は見積もりの根拠を開発ログに書く。分からなければ小さく試してから増やす。
4. Julia の場合: 最後のコマンドを `julia --project=jl jl/scripts/run_<name>.jl "${CONFIG}" ...` にする。

## パラメータスイープ

- 設定ファイルを量産しない。配列ジョブのタスク番号から上書き引数を作る:
  ```bash
  CUTOFFS=(10 20 50 100)
  EXTRA=("filter.cutoff_hz=${CUTOFFS[$SLURM_ARRAY_TASK_ID]}")
  ```
- 各タスクが独立した run になり、`meta.json` の `slurm.array_task_id` で対応が分かる。

## 結果を手元へ

```bash
rsync -av --include='*/' --include='meta.json' --include='metrics.json' --include='config.json' \
  --include='figures/***' --exclude='*' hpc:<runs_root>/ runs/
```
図は HPC 上で `LAB_ENV=hpc uv run labkit fig ...` を実行して作れば、大きなデータを動かさずに済む。

## Claude が HPC に対してしないこと

ジョブの投入（sbatch）、キャンセル、HPC 上のファイル削除は人間が行う。Claude はスクリプトとコマンドを用意して提示する。
