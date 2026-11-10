---
name: lab-conventions
description: lab.toml があるプロジェクトで、どこに何を置き、どの API・コマンドで作るか迷ったときの早見表（置き場所、labkit の Python API、hooks が止める操作、ADR）。
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
| 設計判断 | `docs/decisions/NNNN-slug.md` | `labkit adr`（下の ADR） |
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

## 人間の入口

人間は devlog を読まない。読むのは `docs/DIGEST.md`（`labkit digest`）、`docs/claims.md`、`labkit runs list` / `review list` / `beat log` / `lit queue` の 1 行ずつ。
どれも台帳・meta.json・frontmatter から作られるので、人間に伝えたいことは文章ではなく台帳と run に入れる。

## hooks が止める操作（原本・記録・規約を、検証の根拠として保つため）

- `data/raw/` の既存ファイル・`runs/`・`lab.toml`・`.lab/`・台帳（`docs/claims.md`・`mainline.md`・`seeds.md`・`DIGEST.md`）の直接編集。data/ へのファイルの手書き。
  新しい生データは上書きしない cp / mv で `data/raw/` に入れて `labkit raw freeze`。
- 描画ライブラリ（matplotlib など）の直接 import（図の来歴が付かない）。pickle / joblib などの保存形式（言語と版に依存し、読めなくなる）。
- `layout.writable` 以外への書き込み。新しい置き場所が要るなら `labkit queue ask` で知らせ、今ある場所で進める。
- `docs/reviews/` は lab-reviewer agent だけが書ける（自己採点にしないため）。

プロジェクトだけの例外（特定ファイルの pickle など）は `lab.toml` の `format_allowed` / `plot_import_allowed` / `skip` の変更案を `labkit queue ask` で伝える。
規約そのものを直したいときは skill: improve-standards。

## ADR（設計判断）

複数の案から 1 つを選んだとき、後から変えると影響が大きいとき、先行研究と違う設定を採ったときに書く: `uv run labkit adr "タイトル" --slug english-slug`（番号は自動）。
状態は「提案」から始め、実装して検証が通ったら「採用」。覆すときは古い ADR を消さずに状態を「置換（NNNN）」にして新しい ADR を作る。

## 関連する skill

実験と比較: new-experiment（比較の規則は同 skill の `compare.md`）／図: make-figure／記録: write-devlog／文献: literature-survey／データ: data-pipeline／HPC: hpc-job／
自律運用と主線・芽: autonomous-run、1 拍は beat。
