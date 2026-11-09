---
name: lab-conventions
description: lab.toml があるプロジェクトで、ファイルを作る・置く・保存する前に参照する規約の全体像（置き場所、保存形式、run と labkit run の entry、図、文書、主張の台帳、人間の入口、禁止事項、完全自律と主線・芽）。どこに何を書くか迷ったときに使う。
---

# lab-standards の規約

規約の設定源は `lab.toml`。守られたかは成果物（run の meta.json、サイドカー、開発ログの引用）を `labkit check` が検証する。

## 置き場所

| 作るもの | 置き場所 | 作り方 |
|---|---|---|
| 再利用する関数 | `src/<pkg>/` | 純粋関数。I/O・設定読込・描画を入れない。テストを `tests/` に。1 ファイル 300 行以内（空行を除く。L018） |
| 実験の入口 | `configs/experiments/<name>.toml` の `entry` | `entry = "pkg.module:func"` を `uv run labkit run <config>` が実行する（skill: new-experiment）。`extends = "../base.toml"` で差分だけ書く。seed・`[prediction]`・`[[pass]]`・`[sweep]` も設定に |
| スクリプト | `scripts/` | entry で書けないもの（外部プロセスの起動など）だけ。冒頭に「entry で書けない理由」を 1 行。計算は src に |
| 環境別パス | `configs/paths/{local,hpc}.toml` | コードに絶対パスを書かない。`datapath("processed", ...)`。`mirror_root` に写し先 |
| 実験結果 | `runs/<run_id>/` | `with Run(...)` の中で `runpath(run, ...)` に保存。異常終了は `labkit runs mark` |
| 派生データ | `data/interim/`, `data/processed/` | `save(datapath(...), data)`。巨大データは `writer()`。再生成できる中間物は `data/cache/` |
| 図 | `runs/<run_id>/figures/` | `figspecs/<name>.toml` + `labkit fig`（skill: make-figure） |
| 開発ログ | `docs/devlog/YYYY-MM-DD.md` | skill: write-devlog |
| 主張の台帳 | `docs/claims.md` | `labkit claim add / retract / list`。手で編集しない |
| 人間の入口 | `docs/DIGEST.md`、`docs/assets/digest/` | `labkit digest` が生成（1 日 1 回）。手で編集しない |
| 設計判断 | `docs/decisions/NNNN-slug.md` | skill: write-adr |
| 文献・サーベイ | `literature/` | skill: literature-survey |
| HPC ジョブ | `jobs/` | skill: hpc-job |
| 長い自律運用 | `prompts/current.toml`（現行の goal/beat）, `docs/state.md`, `docs/backlog.md` | skill: autonomous-run、1 拍は skill: beat |
| LLM プロンプト | `prompts/<用途>_v<N>.md` | 改訂時は版を上げる |
| 試行錯誤 | `scratch/` | git 管理外。成果物の根拠にしない |

## API

| 操作 | Python |
|---|---|
| 実験の entry | `def run(cfg: dict) -> dict`（2 引数なら `run(cfg, run)`）。戻り値: 数値 → metrics、DataFrame → `<key>.parquet`、ndarray・配列の dict → `.h5`、str → ログ |
| 設定 | `cfg = load_config(path, ["k=v"])`（entry の外で自分で run を組むとき） |
| run | `with Run(name, cfg, inputs=[...]) as run:`（同上） |
| run 内パス | `runpath(run, "x.h5")` |
| 指標 | `log_metric(run, "loss", v, step=i)` |
| ログ | `log_message(run, "msg")` |
| 保存 | `save(path, {"x": arr}, attrs={...})` |
| 読込 | `load(path, verify=True)` |
| データパス | `datapath("processed", "f.parquet")` |
| 図 | `fig("figspecs/a.toml", run)` |
| 数値の引用 | `cite(run_id, "snr_db", digits=1, unit="dB")` |
| 比較の条件 | 設定の `[compare.<名>]`（vary・keys・better・levels・common・arms・sweep・capability・objective）。entry は `arm_conditions(cfg, "<名>")`・`chosen(run, "<名>")`（`from labkit.compare import ...`） |

## 比較は 1 軸だけを変える（ceteris paribus）

- 腕（手法・設計・設定）の比較が成り立つのは、**宣言した 1 軸（`vary`）以外の条件がすべての腕で同一**で、それを**機械が凍結した設定から確かめた**ときだけ。文章や手書きの dict で「同条件」と書いても根拠にならない。
- 比較は run の前に設定へ書く: `[compare.<名>]` に `vary = "<軸 1 つ>"`・`keys = ["<この比較の指標>"]`、`[compare.<名>.common]` に全腕で同一の条件、
  `[compare.<名>.arms.<腕>]` に軸の値だけ（1 語で、腕の名前か `levels = [...]` の値。`"ours+lr0.1"` のように束ねない）。腕の条件は common ∪ 腕の表から導出され
  （entry は `labkit.compare.arm_conditions(cfg, "<名>")` で読む）、腕の表に軸以外の鍵があれば run は始まらない。`[compare]` の外（common の中も）に腕の名前を含む鍵
  （`[solver.ours]`・`flat_steps`）があっても始まらない。`lab.toml` の `[compare] required`（人間が分野の条件を列挙する）が common に無い・空・`n/a`・`未定` などでも始まらない。
- 比較対象の自由パラメータ（平板の高さなど）は `[[compare.<名>.sweep]]`（arm・param・values・metric・direction）で掃引を宣言し、値ごとのスコアを `log_metric` する。
  metric は比較の指標を含む名前（`"gain_db_flat_h{value}"`）、direction は比較の `better = "max" | "min"` と同じ。1 腕でも調整するなら、対象外でない全腕を同じ総試行数で調整する。
  最良は run の記録から決まり（`labkit.compare.chosen(run, "<名>")`）、腕の値が最良でなければ run は failed。
- 目的を受け取れない腕が「対象外」（負けではない）になるのは `objective` と capability の宣言だけ。人間が `lab.toml` の `[compare.capability]`（手法 = 受け取れる目的）に
  登録したものが独立した宣言。設定の `[compare.<名>.capability]` は著者の宣言として comparisons.json と check（L027 の警告）に出て、`lab.toml` と食い違えば拒否する。
- 設定は開始時に凍結される（`meta.config_sha256`）。entry が `run.config` や config.json を途中で書き換えると run は failed。比較の run は `labkit runs mark ... finished` にできない。
- 比較の記録 `comparisons.json` は Run の終了時に 1 回だけ書かれ、meta の outputs に hash が載る。L027 は凍結した config.json・metrics.json から計算し直す（記録の matched は信用しない）。
- **主張の根拠は既定で拒否**: 指標は matched な比較の `keys` か、設定の `[report] noncomparative`（比較ではない指標。ワイルドカードの前に 2 文字以上の固定の接頭辞。
  腕の名前・比較の指標の語幹・vs/minus/over などの比べる語を含まない）に run の前に書いたものだけ。台帳の本文・備考の引用も同じ基準で照合する。
  根拠が複数の run にまたがるなら `labkit claim add ... --axis <設定の鍵>`（`_git_commit` などの内部の鍵は不可）。軸以外の凍結した設定（`[compare.<名>]` の common・arms を含む）と
  commit が同一でなければ拒否する。他の文書でも、run をまたぐ段落は同じ段落に `axis=<鍵>` を書き、軸以外が同一でなければ L027（開発ログだけ警告、他は error）。
- 条件のそろっていなかった run は `labkit runs archive <id> ... --reason "条件不一致: ..."` で退避し（削除しない。取り消しも理由つきで履歴に残る）、その数値の引用は L032 の error。

## 人間の入口

人間は devlog を読まない。読むのは `docs/DIGEST.md`（`labkit digest`）、`docs/claims.md`（`labkit claim list`）、`labkit runs list` / `review list` / `beat log` / `lit queue` の 1 行ずつ。
これらは台帳・meta.json・frontmatter から同じコードで作られるので、人間に伝えたいことは文章ではなく台帳と run に入れる。不要な run は `labkit runs archive`（削除しない）で視界から消す。

## 禁止事項（hooks がブロックする）

- `data/raw/` の既存ファイル・`runs/`・`lab.toml`・`.lab/`・台帳（`docs/claims.md`・`mainline.md`・`seeds.md`）の直接編集。data/ へのファイルの手書き。
- 描画ライブラリ（matplotlib など）の直接 import。pickle / joblib などの保存形式。
- `layout.writable` 以外への書き込み。新しい置き場所が必要なら、作らずに人間に提案する。

## 完全自律（承認を待つ操作は無い）

- push・merge・tag・release・`labkit raw freeze` も自分で行う。守るのは成果物（hooks）と検証（`labkit check`・レビュー）。
- 判断が分かれる問いは自分で決めて根拠を残し、`labkit queue ask "<質問>" --options A B --assumed "<決めたことと理由>" --impact "<変更時の影響>"` で知らせて進む。返事は待たない。
- 人間の答え・実機の作業を待つことは止まる理由にならない。人間なしで同じ問いに答える方法（計算・公開データ・独立実装）に置き換えるか、依存しない作業を進める。`/loop` を止めるのは人間だけ（hooks が CronDelete・ScheduleWakeup の stop を拒否する。`claude.allow_self_stop`）。
- レビュー記録 `docs/reviews/` は lab-reviewer agent だけが書く。

## 主線と芽（主線から絶対にずれず、芽を拾い続ける）

- 期限のある約束は主線の項目にする: `labkit main add "<成果物>" --done "<完了条件>" --due "YYYY-MM-DD HH:MM"`。完了は `labkit main done M00N --evidence <run|path|commit>`。
- 拍は `labkit beat end --line main|seed:Sxxx|other`。主線の割合（`autonomy.main_share`）を割る拍、期限が近い（`main_guard_hours`）のに主線以外の拍は記録されない。
- 主線の作業中の外れた予想・妙な数字は `labkit seed add "<芽>" --from <run|file> --test "<最安の確かめ方>" --value "<当たれば>"`。`seed_every` 拍芽が無いと拍を閉じられない。
  主線に入れるのは `labkit seed decide S00N --to promote --serves M00N`（どの項目に効くかを言えるときだけ）。
- run の設定に `serves = "M001" | "S003" | "other:<理由>"`（主線に open の項目があると必須）。同じ run が `fail_repeat` 回続けて失敗し commit が進んでいなければ次は始まらない。

## 完了条件

`make check` が通り、コードを変えた日は開発ログの 目的・判断と理由・未解決 が書かれていること（終了時チェックが確認する）。
規約そのものを変えたいときは skill: improve-standards。
