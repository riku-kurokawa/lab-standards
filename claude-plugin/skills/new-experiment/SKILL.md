---
name: new-experiment
description: lab.toml のあるプロジェクトで新しい実験・解析・シミュレーション・学習を実装して実行するときの手順（関数→テスト→設定→スクリプト→run→図→記録）。
---

# 新しい実験を追加して実行する

0. **計算する前に結果を予測する**: 定式化・原典・既知の理論から、結果を 1 行で予測し根拠を書く（開発ログか事前登録）。
   予測が確かなら、その run は確認でしかない。代表 1 本に絞り、資源は予測が割れる問いに回す。
   予測と違った結果が出たら、それが最大の成果。何時間も予測どおりの結果しか出ていないなら、問いか方法を変える。
   予測は設定の `prediction` に書くと meta.json に残る（`lab.toml` の `runs.require_prediction = true` なら、書かないと run が始まらない）。
1. **計算を純粋関数として書く**: `src/<pkg>/<module>.py`。引数と戻り値だけで完結させ、ファイル I/O・乱数の生成源・描画を入れない（乱数は `rng` を引数で受け取る）。
2. **テストを書く**: `tests/test_<module>.py`。既知解・解析解・保存則・形状・境界値など、正しさを確かめられる性質を検証する。
3. **設定を作る**: `configs/experiments/<name>.toml` に `extends = "../base.toml"`、`name = "<name>"`、変更するパラメータだけを書く。`seed` は base.toml が持つ（meta.json に記録される）。
4. **スクリプトを書く**: `scripts/run_<name>.py`。`scripts/run_example.py` と同じ形にする。
   ```python
   cfg = load_config(sys.argv[1], sys.argv[2:])
   with Run(cfg["name"], cfg, inputs=[datapath("processed", "features.parquet")]) as run:
       result = <src の関数>(...)
       save(runpath(run, "result.h5"), {...}, attrs={"unit": "..."})
       log_metric(run, "rmse", value, step=epoch)
       print(run.run_id)
   ```
   - 入力ファイルは必ず `inputs=` に渡す（来歴に sha256 と生成元の run が残る）。
   - 学習曲線・収束履歴は `log_metric(..., step=)` で記録する（図は learning_curve テンプレート）。
   - 文書で引用したい量（誤差・率・時間）はすべて `log_metric` に入れる。入れていない数値は引用できない。
5. **commit してから実行する**: 未コミットの変更があると `git.dirty=true` になり、差分は `dirty.patch` に残るが結果としては引用しない。小さな試行は scratch で行い、正式な run は commit 後に行う。
6. **パラメータを振るとき**: 設定ファイルをコピーせず、上書き引数で振る（`filter.cutoff_hz=80`）。多数なら HPC の配列ジョブ（skill: hpc-job）。
7. **図を作る**: skill: make-figure。
8. **記録する**: 開発ログに目的・結果（`labkit cite` の書式）・判断を書く（skill: write-devlog）。重要な判断は ADR に。

## 結果が期待と違うとき

- run を消したり上書きしたりしない（失敗も記録）。コードか設定を直して新しい run を作る。
- 異常終了（OOM・kill・時間切れ）で running のまま残った run は `labkit runs mark <id> --to failed --reason "..."`。
- 不要な run の整理は人間が判断する。候補を `labkit runs list` で一覧にして提示する。
- 開始直後に止めて meta.json の無いディレクトリが残ったら `labkit runs mark <id> --to interrupted --reason "..."`（削除しない）。

## 長い run を待つあいだ

run の完了を待ってターンを終えない。何時間も自走させるときの置き方（/goal・/loop・1 拍の指示書・ぶっちゃけ点検）は skill: autonomous-run。
