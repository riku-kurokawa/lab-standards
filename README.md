# lab-standards

研究用計算プロジェクト（数値計算・信号処理・機械学習・シミュレーション・データ解析）の
**ディレクトリ構造・データ形式・図・文書・コードの書き方を固定し、複数プロジェクトで継承する**ための標準リポジトリ。

規約を「覚えさせる」のではなく、**コード（labkit）と機械的な検証（labkit check・pre-commit・Claude Code hooks）**で守らせる。
v0.3.0 からは、人間が不在でも Claude が止まらず、しかし取り返しのつかない操作はしない**ハーネス**（承認ゲート・手順の状態機械・
独立レビュー・報告と実データの照合）を備える。全体像は `docs/harness.md`。

## 構成

```
lab-standards/
├── copier.yml                ① プロジェクト雛形の設定
├── template/                 ① 雛形本体（ディレクトリ構造・lab.toml・CLAUDE.md・Makefile …）
├── labkit/
│   ├── python/               ② 共通ライブラリ + CLI（labkit）
│   └── julia/LabKit/         ② 同じ API・同じファイル形式の Julia 版
├── claude-plugin/            ③ Claude Code plugin「lab-rules」（hooks・skills・レビュー agent・evals）
├── .claude-plugin/marketplace.json   ③ この repo 自体が plugin の配布元
└── .github/workflows/ci.yml
```

| 部品 | 継承するもの | 更新の反映 |
|---|---|---|
| ① copier テンプレート | 構造・設定ファイル | 各プロジェクトで `copier update` |
| ② labkit / LabKit.jl | 保存・run・図・チェックのコード | `pyproject.toml` / `jl/Project.toml` のタグを上げる |
| ③ lab-rules plugin | Claude への強制と手順 | `/plugin marketplace update lab-standards` |

## 設計原則

| 原則 | 実装 |
|---|---|
| 原本は不変 | `data/raw` は `labkit raw freeze` で sha256 台帳化＋読み取り専用。hooks も書き込みを拒否 |
| 来歴の記録 | run の `meta.json`（git commit・dirty・環境・Slurm・入力 hash）、データの `.meta.json` サイドカー、図の `.figmeta.json` |
| 情報をファイル名に埋め込まない | 条件は設定・属性・サイドカーに。run ID は識別子のみ |
| データ辞書 | `docs/data-dictionary.md` |
| Functional core, imperative shell | 計算は `src/`（純粋関数）、I/O は `scripts/`。check が依存の向きを検査 |
| 設定とコードの分離 | `configs/experiments/*.toml`（extends 継承）、環境別パス `configs/paths/*.toml` |
| ADR | `docs/decisions/`（`labkit adr`） |
| 派生物は再生成可能 | `data/interim`・`processed`・`runs` は git 管理外。生データ＋コード＋設定から作り直せる |
| 図はテンプレートのみ | `figspecs/*.toml` + `labkit fig`。描画ライブラリの直接 import は hooks と check が拒否 |
| 形式の統一 | 配列は HDF5、表は Parquet。pickle・JLD2 は禁止 |
| 取り返しのつかない操作は人間が承認 | push / tag / merge / raw freeze / copier は hooks が止め、`.lab/queue` に積む。`labkit approve <ID>` で 1 回だけ通る |
| 手順は状態機械 | `labkit flow`（migrate / improve-standards）。完了条件を機械的に検査し、段階外の操作を hooks が拒否 |
| レビューは独立 | `docs/reviews/` は lab-reviewer agent だけが書ける（agent_type で判定） |
| 報告は実データと照合 | 開発ログの run ID と数値（`12.3 dB [run:<id>:<key>]`）を `labkit check` が runs/ と突き合わせる |

---

## 初期設定（別の PC で 1 回）

1. `git clone` で本体を `~/dev/lab-standards` に置く（別の場所なら `LAB_STANDARDS_DEV`）。
2. git・gh（`gh auth login` + `gh auth setup-git`）・uv・copier・Julia を入れる。
3. Claude Code で `/plugin marketplace add ~/dev/lab-standards` → `/plugin install lab-rules@lab-standards`
   （他の PC では `/plugin marketplace add riku-kurokawa/lab-standards`）。

詳細は `docs/SETUP.md`。plugin は `lab.toml` があるプロジェクトと本体でだけ動く。

## 新しいプロジェクトを作る

```bash
copier copy gh:riku-kurokawa/lab-standards ~/research/myproj
cd ~/research/myproj
git init && git add -A && git commit -m "init from lab-standards"
uv sync
julia --project=jl -e 'using Pkg; Pkg.instantiate()'    # Julia を使う場合
uv run pre-commit install
make check && make example                              # 動作確認（合成信号 → run → 図）
claude
```

## 日々の作業

| やること | コマンド |
|---|---|
| 規約チェック＋テスト | `make check`（生データの sha256 まで照合するなら `uv run labkit check --full`） |
| 実験の実行 | `uv run python scripts/run_<name>.py configs/experiments/<name>.toml [key=value ...]` |
| 図 | `uv run labkit fig figspecs/<name>.toml --run <run_id>`（`labkit fig list` で一覧） |
| run 一覧 / 詳細 | `uv run labkit runs list` / `labkit runs show <run_id>` |
| データ置き場の確認 | `uv run labkit paths`（LAB_ENV ごとの data_root / runs_root） |
| 開発ログ / ADR | `uv run labkit devlog` / `uv run labkit adr "タイトル" --slug slug` |
| 文献 | `uv run labkit lit add --file x.bib --tags ...` / `labkit lit survey --question ...` |
| 生データ登録 | `uv run labkit raw freeze`（人間が実行。承認ゲートの対象） |
| 数値の引用 | `uv run labkit cite <run_id> <key> --unit dB` → `12.3 dB [run:<id>:<key>]` を文書に貼る |
| 在席状態 | `uv run labkit presence here|away|status`（既定 away） |
| 承認・質問 | `uv run labkit queue list` → `labkit approve <ID>` / `labkit reject <ID>` / `labkit answer <ID> "..."`（人間） |
| 手順 | `uv run labkit flow start migrate|improve-standards` → `flow status` → `flow advance` |
| 実験の比較画面 | `make mlflow-sync && make mlflow-ui` → http://127.0.0.1:5000 |

### 実験管理（MLflow）について

- MLflow はオープンソース（Apache 2.0）で無料。ここでは**プロジェクト内の SQLite ファイルにだけ**保存し、UI は `127.0.0.1` にのみ公開する。
- MLflow 3.2 以降は匿名の利用統計を既定で送信するが、labkit は `MLFLOW_DISABLE_TELEMETRY=true` と `DO_NOT_TRACK=true` を必ず設定する（プロジェクトの `.claude/settings.json` と HPC ジョブ雛形にも設定済み）。シェルの起動ファイルにも書いておくとより確実。
- 記録の正本は `runs/`（ただのファイル）。MLflow は閲覧用の索引なので、Python の run も Julia の run も同じ画面に並び、`.mlflow/` を消しても `labkit mlflow sync` で作り直せる。

### HPC

```bash
# 手元: commit → push。HPC: pull して
sbatch jobs/slurm_example.sh configs/experiments/example.toml
# 結果の要約だけ手元へ（skill: hpc-job 参照）
```

`LAB_ENV=hpc` のとき、データと run は `configs/paths/hpc.toml` の場所（大容量ストレージ）に置かれる。

## 人間が不在のときの動き（ハーネス）

```
Claude: git push origin main
hooks : 拒否。承認待ち #Q001 を .lab/queue に記録（コマンド全文・cwd・ブランチ・HEAD・差分の要約）
Claude: 依存しない作業を続け、終了時に「承認待ち #Q001」を報告
人間  : labkit queue list → labkit approve Q001        （24 時間有効・1 回限り・同じ HEAD にのみ）
Claude: 次のセッションで「承認済み #Q001」を文脈に受け取り、同じコマンド全文を実行 → 通る
```

- 判断の分かれる問いは `labkit queue ask` で積み、仮の判断で進む（人間は `labkit answer`）。
- `labkit presence here` にすると、拒否ではなく通常の確認画面（ask）になる。
- 検出の限界（`sh -c`、スクリプト経由）とサンドボックス、GitHub のブランチ保護については `docs/harness.md`。

## 作業中のプロジェクトから本体を改良する

プロジェクトのコピーは直さない。気づいたプロジェクトのセッションのまま本体を直し、試し、リリースしてから取り込む。
Claude には「lab-standards を改良したい: ○○」と頼めば skill `improve-standards` の手順で進む。

```
uv run labkit flow start improve-standards
triage【承認】 → branch → implement（必要なら link） → test【レビュー】 → release【承認】 → adopt → done
```
各段階の完了条件（本体のブランチが feat/*、link 状態、本体のテスト、現在の HEAD に対する lab-reviewer の pass、タグが origin にある…）を
`labkit flow advance` が検査し、段階外の操作（例: test 前の release）は hooks が拒否する。

| 安全装置 | 内容 |
|---|---|
| link のまま commit できない | `labkit check` L050 を pre-commit が検出（作業終了時の hook では止めない） |
| link 中の run に印 | `meta.json` の `labkit_source.mode = "link"` と本体の commit・dirty |
| 他のプロジェクトに波及しない | 各プロジェクトはタグ固定。好きなときに ⑥ で更新 |
| 版の整合 | `tools/release.py` が全ファイルの版と CHANGELOG を検査（CI でも実行） |

本体のメンテナンス規約は `CLAUDE.md`（このリポジトリのルート）。本体でも承認ゲート（push / tag / merge）は有効（`.lab-standards-root`）。

## labkit check のコード

| コード | 内容 |
|---|---|
| L001 | トップレベルに許可されていないファイル/ディレクトリ |
| L002 / L003 | data/raw が MANIFEST と一致しない / 書き込み可能 |
| L010–L015 | 描画ライブラリの直接 import、src→scripts 依存、絶対パス、禁止形式、図・データの置き場所 |
| L020–L022 | run の meta.json 無し/スキーマ違反、running のまま、派生データのサイドカー |
| L030 / L031 | 開発ログ / ADR の書式 |
| L032 | 文書が引用する run が runs/ に無い（failed・link 中の run の引用は警告） |
| L033 | 数値の引用が `[run:<id>:<key>]` 書式でない / metrics.json と一致しない（書式なし数値は警告） |
| L035 | レビュー記録（docs/reviews/）の書式 |
| L040–L046 | 文献管理 |
| L050 | 本体を link したまま（commit 禁止） |

警告（`(warn)`）は strict でも失敗にしない。

## テスト

```bash
make test                      # 版の整合性 + lint（ruff check/format）+ labkit + hooks
make test-julia
make test-cross                # Julia が書いたファイルを Python が読む（対称性）
make eval                      # 振る舞いの回帰テスト（API 費用。claude-plugin/evals/README.md）
```
