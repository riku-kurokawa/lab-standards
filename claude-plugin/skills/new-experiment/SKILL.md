---
name: new-experiment
description: lab.toml のあるプロジェクトで新しい実験・解析・シミュレーション・学習を実装して実行するときの手順（関数→テスト→設定（entry・予想・合否）→labkit run→図→記録→主張の台帳）。
---

# 新しい実験を追加して実行する

0. **計算する前に結果を予測する**: 定式化・原典・既知の理論から結果を数値で予想し、根拠と一緒に設定の `[prediction]` に書く（下の 3）。
   予測が確かなら、その run は確認でしかない。代表 1 本に絞り、資源は予測が割れる問いに回す（専門家なら分かる結果は `expert_predictable = true` と書き、なぜ計算が要るかを basis に書く）。
   予測と違った結果が出たら、それが最大の成果。何時間も予測どおりの結果しか出ていないなら、問いか方法を変える。
1. **計算を純粋関数として書く**: `src/<pkg>/<module>.py`。引数と戻り値だけで完結させ、ファイル I/O・乱数の生成源・描画を入れない（乱数は `rng` を引数で受け取る）。
   1 ファイル 300 行以内（空行を除く。L018）。超えるなら分割する。
2. **テストを書く**: `tests/test_<module>.py`。既知解・解析解・保存則・形状・境界値など、正しさを確かめられる性質を検証する。
3. **設定を書く**: `configs/experiments/<name>.toml`。実験の入口は設定の `entry` で、スクリプトは書かない。
   ```toml
   extends = "../base.toml"                 # seed は base.toml が持つ（meta.json に記録される）
   name = "<name>"
   entry = "<pkg>.experiments.<name>:run"   # src の関数 run(cfg) -> dict（step 付きの指標が要るなら run(cfg, run) で run.log_metric(..., step=)）
   inputs = ["data:processed/features.parquet"]   # 来歴（sha256・生成元 run）に残す入力

   [prediction]                             # 計算する前に書く。finished 時に metrics と照合され prediction_result（hit/miss/partial/undeterminable）が残る
   basis = "根拠（理論・桁の見積もり・既存の結果）"   # confidence = 0.7 も書ける
   expert_predictable = false
   [[prediction.claims]]
   key = "rmse"
   range = [0.01, 0.03]                     # または point = 0.02, tol = 0.005

   [[pass]]                                 # 事前に書いた合否（事後に基準を動かさない）。metrics の pass_N / pass_all に残る
   key = "rmse"
   max = 0.03                               # min / max。表の列なら table = "results.parquet", where = {cond = "a"}

   [sweep]                                  # 任意。直積で回し、1 条件 1 行の results.parquet を保存する
   "filter.cutoff_hz" = [20, 50, 100]
   ```
   戻り値の dict は種類で保存先が決まる: 数値 → metrics、DataFrame → `<key>.parquet`、ndarray・配列の dict → `.h5`、str → ログ。文書で引用したい量（誤差・率・時間）はすべて数値で返す。
   `scripts/run_*.py` を書くのは entry で書けないもの（外部プロセスの起動など）だけで、冒頭の docstring に「entry で書けない理由」を 1 行書いてから。
4. **commit してから実行する**: `uv run labkit run configs/experiments/<name>.toml [key=value ...]`。未コミットの変更があると `git.dirty=true` になり結果として引用できない
   （`runs.require_clean = true` なら run が始まらない。雛形は true）。小さな試行は scratch で行い、正式な run は commit 後に行う。
5. **予想の判定を見る**: `uv run labkit runs list` の `予想:hit|miss|partial`。自由記述の予想だけの run は `labkit runs verdict <id> --say hit|miss|partial --note "..."`（判定の無い run は L024）。
6. **パラメータを振るとき**: 設定ファイルをコピーせず、`[sweep]` か上書き引数（`filter.cutoff_hz=80`）で振る。複数 run の同名の表は `labkit runs table <name> [--md]` で連結する（集計スクリプトを書かない）。多数なら HPC の配列ジョブ（skill: hpc-job）。
6b. **比較は 1 軸だけを変える（ceteris paribus）**: 手法・設計・設定を比べる run は、run の前に設定へ
   `[compare.<名>] vary = "<軸 1 つ>"`・`keys = [...]`、`[compare.<名>.common]`（vary 以外の全条件。`lab.toml` の `[compare] required` を含む）、
   `[compare.<名>.arms.<腕>]`（軸の値だけ。1 語で腕の名前か `levels` の値）を書く。entry は `arm_conditions(cfg, "<名>")` で腕の条件を読む（手で dict を書かない。
   `[compare]` の外に腕の名前・軸の値・levels を含む表・鍵を置かない）。自由パラメータは `[[compare.<名>.sweep]]` を宣言し（metric は比較の指標を含む名前、direction は `better`。
   1 腕でも調整するなら全腕を同じ総試行数で）、値ごとのスコアを `log_metric` して `chosen(run, "<名>")` の値で評価する。
   対象外は `objective` と capability（人間の `lab.toml` の `[compare.capability]` が独立した宣言）で決まる腕だけ。比較でない指標は `[report] noncomparative` に書く
   （書かない指標は主張の根拠にできない。`*` のような広い glob、腕の名前・軸の値・levels・比べる語を含む名前は不可）。`run.config` を途中で書き換えない。
   1 つでも合わなければ run は始まらないか failed。複数 run にまたがる主張と、同じ指標を複数 run から引く文書は `--axis <設定の鍵>` / `axis=<鍵>`（軸以外の設定と commit が同一）。
7. **図を作る**: skill: make-figure。
8. **記録する**: 開発ログに目的・結果（`labkit cite` の書式）・判断を書く（skill: write-devlog）。確定した主張は `labkit claim add "<1 文>" --evidence <run>:<key>[:<unit>][:<digits>]` で台帳に入れる。重要な判断は ADR に。

## 結果が期待と違うとき

- run を消したり上書きしたりしない（失敗も記録）。コードか設定を直して新しい run を作る。
- 異常終了（OOM・kill・時間切れ）で running のまま残った run は `labkit runs mark <id> --to failed --reason "..."`。開始直後に止めて meta.json の無いディレクトリが残ったら `--to interrupted`。
- failed / interrupted は `labkit runs archive --status failed,interrupted` で退避する（削除はしない。一覧と DIGEST から消え、`runs list --all` で出る。引用すると L032 の警告）。
  引用されていない古い finished は `labkit runs archive --uncited --older-than 14 --dry-run` で候補を見てから退避する。Claude が実行してよい。間違えたら `--undo --reason`（履歴は残る）。
- 条件のそろっていなかった比較（L027）は `labkit runs archive <id> [<id> ...] --reason "条件不一致: <何が違ったか>"` で退避し、それを根拠にした主張は retract する。
  退避した run の数値を文書で引用すると L032 の error（`check.archived_citation`）。消すのではなく視界と根拠から外す（meta.json に理由が残る）。
- 崩れた主張は `labkit claim retract C00N --reason "..."`（撤回は成果。旧値は消さない）。

## 長い run を待つあいだ

run の完了を待ってターンを終えない。何時間も自走させるときの置き方（/goal・/loop・1 拍・ぶっちゃけ点検）は skill: autonomous-run と skill: beat。
