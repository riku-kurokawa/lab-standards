# lab-standards

研究用計算プロジェクト（数値計算・信号処理・機械学習・シミュレーション・データ解析）の
**ディレクトリ構造・データ形式・図・文書・コードの書き方を固定し、複数プロジェクトで継承する**ための標準リポジトリ。

規約を「覚えさせる」のではなく、**コード（labkit）と機械的な検証（labkit check・pre-commit・Claude Code hooks）**で守らせる。

## 構成

```
lab-standards/
├── copier.yml                ① プロジェクト雛形の設定
├── template/                 ① 雛形本体（ディレクトリ構造・lab.toml・CLAUDE.md・Makefile …）
├── labkit/
│   ├── python/               ② 共通ライブラリ + CLI（labkit）
│   └── julia/LabKit/         ② 同じ API・同じファイル形式の Julia 版
├── claude-plugin/            ③ Claude Code plugin「lab-rules」（hooks・skills・レビュー agent）
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

---

## 初期設定（1 回だけ）

手順の詳細は `docs/SETUP.md`。要点:

1. この repo を **`~/dev/lab-standards`** に置く（ここが本体を編集する唯一の場所になる）。
2. `copier.yml` の `YOUR_GITHUB` を自分の GitHub ユーザー名に書き換える。
3. `git init` → commit → **`git tag v0.2.0`** → GitHub に非公開リポジトリを作って push（タグも）。
4. uv・copier・Julia を入れる。
5. Claude Code で、自分の PC では**手元のパス**から plugin を登録する（本体の hooks・skills の編集がすぐ効く）:
   ```
   /plugin marketplace add ~/dev/lab-standards
   /plugin install lab-rules@lab-standards
   ```
   他の PC では `/plugin marketplace add <you>/lab-standards`（GitHub から）。

plugin は `lab.toml` があるディレクトリでのみ動作し、他のプロジェクトでは何もしない。

## 新しいプロジェクトを作る

```bash
copier copy gh:<you>/lab-standards ~/research/myproj
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
| 規約チェック＋テスト | `make check` |
| 実験の実行 | `uv run python scripts/run_<name>.py configs/experiments/<name>.toml [key=value ...]` |
| 図 | `uv run labkit fig figspecs/<name>.toml --run <run_id>`（`labkit fig list` で一覧） |
| run 一覧 | `uv run labkit runs list` |
| 開発ログ / ADR | `uv run labkit devlog` / `uv run labkit adr "タイトル" --slug slug` |
| 文献 | `uv run labkit lit add --file x.bib --tags ...` / `labkit lit survey --question ...` |
| 生データ登録 | `uv run labkit raw freeze`（人間が実行） |
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

## 作業中のプロジェクトから本体を改良する

プロジェクトのコピーは直さない。気づいたプロジェクトのセッションのまま本体を直し、試し、リリースしてから取り込む。
Claude には「lab-standards を改良したい: ○○」と頼めば skill `improve-standards` の手順で進む。

```
① 振り分け    このプロジェクトだけの事情 → lab.toml の例外で終わり / 共通の改良 → ②
② 本体を開く  /add-dir ~/dev/lab-standards、本体で feat/<名前> ブランチ
③ link        uv run labkit standards link        # labkit・LabKit.jl が手元の本体を直接参照
④ 改良と試用  本体を直す → プロジェクトで使って確かめる → 本体のテスト
⑤ リリース    python tools/release.py X.Y.Z → commit → main にマージ → tag → push（人間が承認）
⑥ 取り込み    uv run labkit standards unlink --to vX.Y.Z → commit
              uv run labkit standards template --ref vX.Y.Z → commit
```

| 安全装置 | 内容 |
|---|---|
| link のまま commit できない | `labkit check` L050 を pre-commit が検出（作業終了時の hook では止めない） |
| link 中の run に印 | `meta.json` の `labkit_source.mode = "link"` と本体の commit・dirty |
| 他のプロジェクトに波及しない | 各プロジェクトはタグ固定。好きなときに ⑥ で更新 |
| 版の整合 | `tools/release.py` が全ファイルの版と CHANGELOG を検査（CI でも実行） |

本体のメンテナンス規約は `CLAUDE.md`（このリポジトリのルート）。

## テスト

```bash
cd labkit/python && uv run --extra dev pytest -q          # labkit
uv run --with pytest pytest -q claude-plugin/tests         # hooks
julia --project=labkit/julia/LabKit -e 'using Pkg; Pkg.test()'
```
