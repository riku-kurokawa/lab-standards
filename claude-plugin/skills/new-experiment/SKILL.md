---
name: new-experiment
description: lab.toml のあるプロジェクトで新しい実験・解析・シミュレーション・学習を実装して実行するときの手順（関数→テスト→設定→スクリプト→run→図→記録）。
---

# 新しい実験を追加して実行する

1. **計算を純粋関数として書く**: `src/<pkg>/<module>.py`（Julia は `jl/src/`）。引数と戻り値だけで完結させ、ファイル I/O・乱数の生成源・描画を入れない（乱数は `rng` を引数で受け取る）。
2. **テストを書く**: `tests/test_<module>.py`。既知解・解析解・保存則・形状・境界値など、正しさを確かめられる性質を検証する。`uv run pytest -q tests/test_<module>.py` を通す。
3. **設定を作る**: `configs/experiments/<name>.toml` に `extends = "../base.toml"` と、`name = "<name>"`、変更するパラメータだけを書く。マジックナンバーをコードに残さない。
4. **スクリプトを書く**: `scripts/run_<name>.py`。`scripts/run_example.py` と同じ形にする。
   ```python
   cfg = load_config(sys.argv[1], sys.argv[2:])
   with Run(cfg["name"], cfg, inputs=[datapath("processed", "features.parquet")]) as run:
       result = <src の関数>(...)
       save(runpath(run, "result.h5"), {...}, attrs={"unit": "..."})
       log_metric(run, "rmse", value, step=epoch)
       print(run.run_id)
   ```
   - 入力ファイルは必ず `inputs=` に渡す（来歴に sha256 が残る）。
   - 学習曲線・収束履歴は `log_metric(..., step=)` で記録する（図は learning_curve テンプレートで作れる）。
5. **commit してから実行する**: 未コミットの変更があると `meta.json` の `git.dirty=true` になり、結果を再現できない。小さな試行は scratch で行い、正式な run は commit 後に行う。
   ```bash
   uv run python scripts/run_<name>.py configs/experiments/<name>.toml
   ```
6. **パラメータを振るとき**: 設定ファイルをコピーせず、上書き引数で振る（`filter.cutoff_hz=80`）。多数なら HPC の配列ジョブ（skill: hpc-job）。
7. **図を作る**: skill: make-figure。
8. **記録する**: 開発ログの「実行した run」に run_id と目的・結果を書く（skill: write-devlog）。手法の選択など重要な判断は ADR に。

## 結果が期待と違うとき

- run を消したり上書きしたりしない（失敗も記録）。コードか設定を直して新しい run を作る。
- 不要な run の整理は人間が判断する。候補を `labkit runs list` で一覧にして提示する。
