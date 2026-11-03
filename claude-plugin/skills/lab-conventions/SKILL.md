---
name: lab-conventions
description: lab.toml があるプロジェクトで、ファイルを作る・置く・保存する前に参照する規約の全体像（置き場所、保存形式、run、図、文書、禁止事項、承認ゲート）。どこに何を書くか迷ったときに使う。
---

# lab-standards の規約

規約の設定源は `lab.toml`。守られたかは成果物（run の meta.json、サイドカー、開発ログの引用）を `labkit check` が検証する。

## 置き場所

| 作るもの | 置き場所 | 作り方 |
|---|---|---|
| 再利用する関数 | `src/<pkg>/` | 純粋関数。I/O・設定読込・描画を入れない。テストを `tests/` に |
| 実行の入口 | `scripts/` | 設定を読む → src を呼ぶ → labkit で保存、だけの薄い層 |
| パラメータ | `configs/experiments/<name>.toml` | `extends = "../base.toml"` で差分だけ書く。seed を持つ |
| 環境別パス | `configs/paths/{local,hpc}.toml` | コードに絶対パスを書かない。`datapath("processed", ...)`。`mirror_root` に写し先 |
| 実験結果 | `runs/<run_id>/` | `with Run(...)` の中で `runpath(run, ...)` に保存。異常終了は `labkit runs mark` |
| 派生データ | `data/interim/`, `data/processed/` | `save(datapath(...), data)`。巨大データは `writer()`。再生成できる中間物は `data/cache/` |
| 図 | `runs/<run_id>/figures/` | `figspecs/<name>.toml` + `labkit fig`（skill: make-figure） |
| 開発ログ | `docs/devlog/YYYY-MM-DD.md` | skill: write-devlog |
| 設計判断 | `docs/decisions/NNNN-slug.md` | skill: write-adr |
| 文献・サーベイ | `literature/` | skill: literature-survey |
| HPC ジョブ | `jobs/` | skill: hpc-job |
| 長い自律運用 | `prompts/`, `docs/state.md`, `docs/backlog.md` | skill: autonomous-run |
| LLM プロンプト | `prompts/<用途>_v<N>.md` | 改訂時は版を上げる |
| 試行錯誤 | `scratch/` | git 管理外。成果物の根拠にしない |

## API

| 操作 | Python |
|---|---|
| 設定 | `cfg = load_config(path, ["k=v"])` |
| run | `with Run(name, cfg, inputs=[...]) as run:` |
| run 内パス | `runpath(run, "x.h5")` |
| 指標 | `log_metric(run, "loss", v, step=i)` |
| ログ | `log_message(run, "msg")` |
| 保存 | `save(path, {"x": arr}, attrs={...})` |
| 読込 | `load(path, verify=True)` |
| データパス | `datapath("processed", "f.parquet")` |
| 図 | `fig("figspecs/a.toml", run)` |
| 数値の引用 | `cite(run_id, "snr_db", digits=1, unit="dB")` |

## 禁止事項（hooks がブロックする）

- `data/raw/`・`runs/`・`lab.toml`・`.lab/` の直接編集。data/ へのファイルの手書き。
- 描画ライブラリ（matplotlib など）の直接 import。pickle / joblib などの保存形式。
- `layout.writable` 以外への書き込み。新しい置き場所が必要なら、作らずに人間に提案する。

## 人間が不在でも止まらない（承認ゲートとキュー）

- 承認ゲートの対象は、保護ブランチへの push/merge・`git tag`・`gh release`・`gh pr merge`・`labkit raw freeze` だけ。feat ブランチへの push は自由。
  対象の操作は拒否され、承認待ち `.lab/queue/<ID>` に記録される。その操作に依存しない作業を続け、終了時に ID を報告する。
  人間の `labkit approve <ID>` はその種類の操作をそのブランチで 24 時間許可する（commit しても無効にならない。同じ種類なら何度でも通る）。
- 判断が分かれる問いは `labkit queue ask "<質問>" --options A B --assumed "<仮の判断と理由>" --impact "<変更時の影響>"` に積み、仮の判断で進む。
- 人間が `labkit delegate <カテゴリ> --hours N` で委任した種類の操作（`labkit delegate list`）は、承認を待たずに実行してよい。
- `labkit approve / reject / answer / delegate` は人間専用。レビュー記録 `docs/reviews/` は lab-reviewer agent だけが書く。

## 完了条件

`make check` が通り、コードを変えた日は開発ログの 目的・判断と理由・未解決 が書かれていること（終了時チェックが確認する）。
規約そのものを変えたいときは skill: improve-standards。
