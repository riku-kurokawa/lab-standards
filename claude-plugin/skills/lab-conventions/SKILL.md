---
name: lab-conventions
description: lab.toml があるプロジェクトで、ファイルを作る・置く・保存する前に参照する規約の全体像（置き場所、保存形式、run、図、文書、禁止事項）。どこに何を書くか迷ったときに使う。
---

# lab-standards の規約

規約の設定源は `lab.toml`。hooks と `labkit check` が機械的に検証するので、ここに書かれた規約に従えば作業が止まらない。

## 置き場所

| 作るもの | 置き場所 | 作り方 |
|---|---|---|
| 再利用する関数 | `src/<pkg>/`（Python）、`jl/src/`（Julia） | 純粋関数。I/O・設定読込・描画を入れない。テストを `tests/`・`jl/test/` に |
| 実行の入口 | `scripts/`、`jl/scripts/` | 設定を読む → src を呼ぶ → labkit で保存、だけの薄い層 |
| パラメータ | `configs/experiments/<name>.toml` | `extends = "../base.toml"` で差分だけ書く |
| 環境別パス | `configs/paths/{local,hpc}.toml` | コードに絶対パスを書かない。`datapath("processed", ...)` |
| 実験結果 | `runs/<run_id>/` | `with Run(...)`（Julia: `Run(...) do run`）の中で `runpath(run, ...)` に保存 |
| 派生データ | `data/interim/`, `data/processed/` | `save(datapath(...), data)`。巨大データは `writer()` |
| 図 | `runs/<run_id>/figures/` | `figspecs/<name>.toml` + `labkit fig`（skill: make-figure） |
| 開発ログ | `docs/devlog/YYYY-MM-DD.md` | skill: write-devlog |
| 設計判断 | `docs/decisions/NNNN-slug.md` | skill: write-adr |
| 文献・サーベイ | `literature/` | skill: literature-survey |
| HPC ジョブ | `jobs/` | skill: hpc-job |
| LLM プロンプト | `prompts/<用途>_v<N>.md` | 改訂時は版を上げる |
| 試行錯誤 | `scratch/` | git 管理外。成果物の根拠にしない |

## Python と Julia の対応（同じ名前・同じ形式）

| 操作 | Python | Julia |
|---|---|---|
| 設定 | `cfg = load_config(path, ["k=v"])` | `cfg = load_config(path; overrides=["k=v"])` |
| run | `with Run(name, cfg, inputs=[...]) as run:` | `Run(name, cfg; inputs=[...]) do run ... end` |
| run 内パス | `runpath(run, "x.h5")` | `runpath(run, "x.h5")` |
| 指標 | `log_metric(run, "loss", v, step=i)` | `log_metric(run, "loss", v; step=i)` |
| ログ | `log_message(run, "msg")` | `log_message(run, "msg")` |
| 保存 | `save(path, {"x": arr}, attrs={...})` | `save(path, Dict("x"=>arr); attrs=Dict(...))` |
| 読込 | `load(path, verify=True)` | `load(path; verify=true)` |
| データパス | `datapath("processed", "f.parquet")` | `datapath("processed", "f.parquet")` |
| 図 | `fig("figspecs/a.toml", run)` | `fig("figspecs/a.toml"; run=run)` |
| 数値の引用 | `cite(run_id, "snr_db", digits=1, unit="dB")` | `cite(run_id, "snr_db"; digits=1, unit="dB")` |

配列の軸: Python の shape (n_ch, n_t) は Julia でも size (n_ch, n_t)。HDF5 上の並びは labkit が揃える。
bool 配列: HDF5 上は uint8 + データセット属性 `labkit_dtype="bool"`（両言語で bool に戻る。h5py/HDF5.jl/MATLAB で直接読むと 0/1）。

## 禁止事項（hooks がブロックする）

- `data/raw/`・`runs/`・`lab.toml` の直接編集。data/ へのファイルの手書き。
- 描画ライブラリ（matplotlib, Plots, Makie など）の直接 import。
- pickle / joblib / JLD2 / BSON などの保存形式。
- `layout.writable` 以外への書き込み。新しい置き場所が必要なら、作らずに人間に提案する。

## 人間が不在でも止まらない（承認ゲートとキュー）

- `git push` / `git tag` / 保護ブランチへの merge / `gh pr merge` / `gh release` / `labkit raw freeze` / `copier` は hooks が止める。
  `presence=away`（既定、`labkit presence status`）では拒否され、承認待ち `.lab/queue/<ID>` に記録される。
  その操作に依存しない作業を続け、終了時に ID を報告する。承認後は同じリポジトリ・同じ HEAD で同じコマンド全文を実行する（1 回限り）。
- 判断が分かれる問いは `labkit queue ask "<質問>" --options A B --assumed "<仮の判断と理由>" --impact "<変更時の影響>"` に積み、仮の判断で進む。
- `labkit approve / reject / answer` は人間専用。レビュー記録 `docs/reviews/` は lab-reviewer agent だけが書く。
- 手順のある作業（移行、本体の改良）は `labkit flow start <migrate|improve-standards>` → `status` → `advance`。

## 規約そのものを変えたいとき

プロジェクト内で雛形・labkit・hooks を直さない。skill: improve-standards（本体を直す → link で試す → リリース → 取り込む）。
このプロジェクトだけの例外は `lab.toml` の変更案を人間に出す。

## 完了条件

`make check` が通り、コードを変えた日は開発ログが書かれていること（Stop hook が確認する）。
