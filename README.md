# lab-standards

研究用計算プロジェクト（数値計算・信号処理・機械学習・シミュレーション・データ解析）の
**ディレクトリ構造・データ形式・図・文書・コードの書き方を固定し、複数プロジェクトで継承する**ための標準リポジトリ。

規約を「覚えさせる」のではなく、**成果物が検証可能であること**を `labkit` のコードと機械的な検証（`labkit check`・pre-commit・Claude Code hooks）で保証する。
人間が不在でも Claude が止まらず、取り返しのつかない操作だけを人間の承認に委ねる。設計は `docs/harness.md`、v1.0.0 に至った監査は `docs/audit-2026-11-02.md`。

## 構成

```
lab-standards/
├── copier.yml, template/     ① プロジェクト雛形（ディレクトリ構造・lab.toml・CLAUDE.md・Makefile …）
├── labkit/python/            ② 共通ライブラリ + CLI（labkit）。hooks の判定もここ（labkit hook）
├── claude-plugin/            ③ Claude Code plugin「lab-rules」（hooks の入口・skills・レビュー agent・ぶっちゃけ点検 agent）
└── .claude-plugin/marketplace.json   この repo 自体が plugin の配布元
```

| 部品 | 継承するもの | 更新の反映 |
|---|---|---|
| ① copier テンプレート | 構造・設定ファイル | `labkit standards template --ref vX.Y.Z` |
| ② labkit | 来歴・保存・図・チェック・ゲートのコード | `labkit standards unlink --to vX.Y.Z` |
| ③ lab-rules plugin | Claude への強制と手順 | `/plugin marketplace update lab-standards` |

## 設計原則

| 原則 | 実装 |
|---|---|
| 原本は不変 | `data/raw` は `labkit raw freeze` で sha256 台帳化＋読み取り専用。hooks も書き込みを拒否 |
| run は再現に必要なものを全部持つ | `meta.json`: commit・dirty（dirty なら `dirty.patch`）・環境（lockfile の hash、パッケージ版、GPU）・seed・入力の hash と生成元 run・出力の hash |
| 正本は機械の外にも置く | `runs/`・`data/` は git 管理外。`labkit mirror push` で `mirror_root` に差分コピー |
| 情報をファイル名に埋め込まない | 条件は設定・属性・サイドカーに。run ID は識別子のみ |
| Functional core, imperative shell | 計算は `src/`（純粋関数）、I/O は `scripts/`。check が依存の向きを検査 |
| 設定とコードの分離 | `configs/experiments/*.toml`（extends 継承）、環境別パス `configs/paths/*.toml` |
| 派生物は再生成可能 | `data/interim`・`processed`（サイドカー付き）・`data/cache`（サイドカー不要）・`runs` |
| 図はテンプレートのみ | `figspecs/*.toml` + `labkit fig`（13 種、複数パネル可）。来歴は `.figmeta.json` |
| 形式の統一 | 配列は HDF5、表は Parquet。pickle は禁止、`np.save` は警告 |
| 報告は実データと照合 | 開発ログの数値（`12.3 dB [run:<id>:<key>]`）を `labkit check` が runs/ と突き合わせる。判断欄が空の開発ログは記録ではない |
| 取り返しのつかない操作だけ人間が承認 | 保護ブランチへの push/merge・tag・gh release/merge・raw freeze。承認は種類＋ブランチ＋期限に結び付く（commit しても無効にならない） |
| レビューは独立 | `docs/reviews/` は lab-reviewer agent だけが書ける |
| 長い自律運用は考えてから計算する | 目標と 1 拍の指示書は `prompts/`（/goal・/loop で再注入）、run の前の予想（`prediction`）、記録を見ない candor-check agent の点検（skill: autonomous-run） |

---

## 初期設定（別の PC で 1 回）

1. `git clone` で本体を `~/dev/lab-standards` に置く（別の場所なら `LAB_STANDARDS_DEV`）。
2. git・gh・uv・copier を入れる（`docs/SETUP.md`）。
3. Claude Code で `/plugin marketplace add riku-kurokawa/lab-standards` → `/plugin install lab-rules@lab-standards`。

plugin は `lab.toml` があるプロジェクトと本体でだけ動く。判定は各プロジェクトの venv の `labkit hook` が行うので、plugin と labkit の版を揃える（SessionStart が不一致を知らせる）。

## 新しいプロジェクトを作る

```bash
copier copy gh:riku-kurokawa/lab-standards ~/research/myproj
cd ~/research/myproj
git init && git add -A && git commit -m "init from lab-standards"
uv sync && uv run pre-commit install
make check && make example                              # 動作確認（合成信号 → run → 図）
```

## 日々の作業

| やること | コマンド |
|---|---|
| 規約チェック＋テスト | `make check`（成果物の検証だけなら `uv run labkit check --claims`、生データの sha256 まで `--full`） |
| 実験の実行 | `uv run python scripts/run_<name>.py configs/experiments/<name>.toml [key=value ...]` |
| 図 | `uv run labkit fig figspecs/<name>.toml --run <run_id>`（`labkit fig list` で一覧） |
| run 一覧 / 詳細 / 異常終了の記録 | `uv run labkit runs list` / `runs show <id>` / `runs mark <id> --to failed --reason ...` |
| 正本の写し | `uv run labkit mirror push`（`configs/paths/*.toml` の `mirror_root`）/ `mirror pull` |
| 開発ログ / ADR | `uv run labkit devlog`（変更ファイルと run を自動で埋める）/ `uv run labkit adr "タイトル" --slug slug` |
| 文献 | `uv run labkit lit add --file x.bib --tags ...` / `labkit lit survey --question ...` / `labkit lit index` |
| 生データ登録 | `uv run labkit raw freeze`（承認ゲートの対象） |
| 数値の引用 | `uv run labkit cite <run_id> <key> --unit dB` → `12.3 dB [run:<id>:<key>]` を文書に貼る |
| 承認・質問 | `uv run labkit queue list` → `labkit approve <ID>` / `labkit reject <ID>` / `labkit answer <ID> "..."`（人間） |
| 委任 | `uv run labkit delegate release --hours 8` / `delegate migrate` / `delegate list` / `delegate revoke <ID>`（人間） |
| 移行の手順 | `uv run labkit flow start migrate` → `flow status` → `flow advance` |

## 人間が不在のときの動き

```
Claude: git push origin main
hooks : 拒否。承認待ち #Q001 を .lab/queue に記録（種類・ブランチ・コマンド・HEAD）
Claude: 依存しない作業を続け、終了時に「承認待ち #Q001」を報告
人間  : labkit queue list → labkit approve Q001     （git_push をブランチ feat/x で 24 時間許可。commit しても有効）
Claude: 次のプロンプトで「承認済み #Q001」を受け取り、実行する
```

- feat ブランチへの push は承認不要。最後の砦は GitHub 側の main のブランチ保護（`docs/SETUP.md`）。
- 対話中（permission mode が default）なら拒否ではなく通常の確認画面になる。
- 判断の分かれる問いは `labkit queue ask` で積み、仮の判断で進む（人間は `labkit answer`）。
- 長い手順を任せるときは `labkit delegate migrate --hours 8` のように委任する。

## 本体を改良する

プロジェクトのコピーは直さない。本体を feat ブランチで直し、テスト・レビュー・リリースしてからタグで取り込む（skill `improve-standards`、本体の `CLAUDE.md`）。

## labkit check のコード

| コード | 内容 |
|---|---|
| 成果物の検証（`--claims`。Stop hook が見る） | |
| L002 / L003 | data/raw が MANIFEST と一致しない / 書き込み可能 |
| L020 / L021 | run の meta.json 無し・スキーマ違反（開始直後の殻は `labkit runs mark <id> --to interrupted`） / running のまま（警告。`labkit runs mark`） |
| L022 | data/interim・processed の派生ファイルにサイドカーが無い（サブディレクトリも。data/cache は対象外） |
| L030 | 開発ログの書式違反、目的・判断と理由・未解決 が空 |
| L032 / L033 / L034 | 引用した run が無い / 数値が metrics.json と一致しない / 結果節の数値に引用が無い（警告） |
| 体裁（pre-commit・CI） | |
| L001 / L004 / L050 | トップレベルの不許可ファイル / 衝突マーカー / 本体を link したまま |
| L010–L017 | 描画ライブラリの直接 import、src→scripts 依存、絶対パス（jobs/ も）、禁止形式、図・データの置き場所、np.save（警告）、どこからも import されない src のモジュール（警告） |
| L031 / L035 / L040–L046 | ADR / レビュー記録 / 文献管理の書式 |

## テスト

```bash
make test        # 版の整合性 + lint + labkit（hooks の判定を含む）+ 雛形の生成
```
