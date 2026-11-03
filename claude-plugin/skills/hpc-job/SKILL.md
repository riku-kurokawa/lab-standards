---
name: hpc-job
description: lab.toml のあるプロジェクトで HPC（Slurm・PBS など）向けのジョブスクリプト作成、パラメータスイープの配列ジョブ、HPC と手元の結果のやりとりを行うときの手順。
---

# HPC ジョブ

## 原則

- コードは git でのみ移す（手元で commit → push → HPC で pull）。HPC 上でコードを編集しない。
- データと run は HPC のストレージに置く。パスは `configs/paths/hpc.toml`、実行時は `LAB_ENV=hpc`。jobs/ にも絶対パスを書かない（L012）。
- 手元へは小さな成果物（`meta.json`, `metrics.json`, `figures/`）だけを持ってくる。

## ジョブスクリプトを作る

1. `jobs/slurm_example.sh` をコピーして `jobs/<name>.sh` を作る。変えるのは `#SBATCH` 行と最後のコマンドだけ。
2. 必ず残す部分: `export LAB_ENV=hpc`、未コミット変更チェック、`set -euo pipefail`。
3. 資源量（time, mem, cpus, gpus）は見積もりの根拠を開発ログに書く。分からなければ小さく試してから増やす。

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
時間切れで running のまま残った run は `labkit runs mark <id> --to interrupted --reason "time limit"`。

## 運用で踏んだ罠（先に確かめる）

- **1 ノードあたりの GPU 数**を、計算機の利用案内で確かめてからランクを割り当てる（1 ノード 1 GPU の機で 8 ランクを載せると、7 ランクが CPU に落ちても気づかない）。
  ジョブの冒頭で `nvidia-smi -L` をログに出す。
- **ジョブの作業ディレクトリ**: PBS は既定で `$HOME` から始まる。スクリプトの冒頭でプロジェクトに `cd` し、相対パスに頼らない。
- **手元の長い計算**は `setsid` で親から切り離す（`nohup` だけだと、親のシェルを止めたときに一緒に止まることがある）。
- **一時ファイル**（外部ソルバーの入出力）は計算ごとに消すか、run の中に縮約だけを残す。`/tmp` やクォータが溢れると無関係の計算が落ちる。
- 待ち時間が読めないときは、同じ計算を複数のキューに投げ、先に始まった方を使い、残りは状態を確かめてから取り消す。

## 人間が決めること

ジョブの投入は、人間が計算資源の使用を任せたとき（目標や queue の回答で明示）に Claude が行ってよい。
任されていない場合と、HPC 上のファイル削除は、スクリプトとコマンドを用意して人間に提示する。
