# lab-standards

研究用計算プロジェクト（数値計算・信号処理・機械学習・シミュレーション・データ解析）の
**ディレクトリ構造・データ形式・図・文書・コードの書き方を固定し、複数プロジェクトで継承する**ための標準リポジトリ。

規約を「覚えさせる」のではなく、**成果物が検証可能であること**を `labkit` のコードと機械的な検証（`labkit check`・pre-commit・Claude Code hooks）で保証する。
Claude は人間の承認を待たずに完全自律で動き、**主線から絶対にずれず、しかし面白い芽を拾い続ける**（主線と芽の台帳・拍の関門・資源の紐付け）。設計は `docs/harness.md`・`docs/decisions/0002-autonomy-mainline-seeds.md`、v1.0.0 に至った監査は `docs/audit-2026-11-02.md`。

## 構成

```
lab-standards/
├── copier.yml, template/     ① プロジェクト雛形（ディレクトリ構造・lab.toml・CLAUDE.md・Makefile …）
├── labkit/python/            ② 共通ライブラリ + CLI（labkit）。hooks の判定もここ（labkit hook）
├── claude-plugin/            ③ Claude Code plugin「lab-rules」（hooks の入口・13 の skills（実験・図・開発ログ・移行・自律運用・1 拍 beat …）・レビュー agent・ぶっちゃけ点検 agent）
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
| 完全自律 | 承認・却下・回答・委任は無い（v2.0.0）。push・merge・tag・raw freeze も Claude が行う。守るのは成果物（data/raw の既存ファイル・runs/・lab.toml・台帳は hooks が止める）。人間への連絡は `labkit queue ask`（一方通行、返事は待たない） |
| 主線から絶対にずれない | `docs/mainline.md`（1 文 + 成果物・完了条件・期限）。拍ごとに `--line main\|seed:Sxxx\|other` を宣言し、主線の割合（既定 70 %）を割る拍・期限が近いのに主線以外を進めた拍は `labkit beat end` が記録しない。完了は根拠つき（`main done --evidence`） |
| ずれないだけでなく、芽を拾い続ける | `docs/seeds.md`（出どころ・最安の確かめ方・当たれば）。`seed_every` 拍（既定 8）芽が無いと拍を閉じられない。芽は主線以外の枠で確かめ、主線のどの項目に効くかを言えたときだけ `seed decide --to promote --serves Mxxx` |
| 資源は必ずどれかの線に紐づく | 主線に open の項目があるあいだ、run の設定に `serves`（Mxxx / Sxxx / `other:<理由>`）が無いと始まらない。同じ run が `fail_repeat` 回（既定 3）続けて失敗し commit が進んでいなければ次を始めない。`beat start`・digest が直近 24 時間の run 時間を線ごと・状態ごとに示す |
| レビューは独立 | `docs/reviews/` は lab-reviewer agent だけが書ける |
| 長い自律運用は考えてから計算する | 目標と 1 拍の指示書は `prompts/`、現行の版は `prompts/current.toml`（`labkit beat start/end` と SessionStart が読み、compact 後は目標の冒頭を原文で再注入）。run の前の予想は `[prediction]` の表（finished 時に hit/miss を自動判定）。記録を見ない candor-check agent の点検（skill: autonomous-run） |
| 人間の入口は 1 枚 | `labkit digest` が `docs/DIGEST.md`（主張の変化・予想と結果・run の収支・新しい図・未解消のレビュー・主線と芽・資源の使い道・人間への連絡・check の集計・文献・コード量）を台帳と run から同じコードで作る。人間は devlog を読まない。退避した run・使われないコードは視界から消す |
| 主張は台帳 | `docs/claims.md` を `labkit claim add / retract` で書く（手で編集しない）。根拠は `labkit cite` の書式。根拠の run が無い・failed・dirty・退避済みになると L036 |
| 実験の入口は共通 | 設定の `entry = "pkg.module:func"` を `labkit run` が実行する（`[sweep]`・`[[pass]]`・`[prediction]` も設定に）。使い捨ての `scripts/run_*.py` を書かず、一度レビューした入口を使い回す |
| コードは読める大きさ | src・scripts のファイルは 300 行以内（L018）。scripts→scripts の import・使われない src は警告。開発ログの自動ブロックにコード量の 1 行 |

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
uv sync && uv run pre-commit install                   # uv.lock も環境の来歴なので commit に含める
git init && git add -A && git commit -m "init from lab-standards"   # 雛形は require_clean = true（未コミットでは run が始まらない）
make check && make example                              # 動作確認（合成信号 → run → 図）
```

## 日々の作業

| やること | コマンド |
|---|---|
| 規約チェック＋テスト | `make check`（成果物の検証だけなら `uv run labkit check --claims`、生データの sha256 まで `--full`） |
| 実験の実行 | `uv run labkit run configs/experiments/<name>.toml [key=value ...]`（設定の `entry` を実行。`[sweep]` は 1 条件 1 行の results.parquet） |
| 予想の判定 / 表の連結 | `uv run labkit runs verdict <id> --say hit\|miss\|partial --note ...`（自由記述の予想。表形式は自動）/ `runs table <name> [--md]`（clean な finished の同名 parquet を連結） |
| 図 | `uv run labkit fig figspecs/<name>.toml --run <run_id>`（`labkit fig list` で一覧） |
| run 一覧 / 詳細 / 異常終了の記録 | `uv run labkit runs list [--all]` / `runs show <id>` / `runs mark <id> --to failed --reason ...` |
| run の退避（削除しない） | `uv run labkit runs archive <id> \| --status failed,interrupted \| --uncited [--older-than N] [--dry-run] [--undo]`（一覧と DIGEST から隠す） |
| 主張の台帳 | `uv run labkit claim add "<1 文>" --evidence <run>:<key>[:<unit>][:<digits>] [--note prereg:slug]` / `claim retract C003 --reason ...` / `claim list [--status open]` |
| 人間の入口 | `uv run labkit digest [--since YYYY-MM-DD]` → `docs/DIGEST.md`（1 日 1 回、人間が読む前に） |
| 主線 | `uv run labkit main set "<1 文>"` / `main add "<成果物>" --done "<完了条件>" --due "YYYY-MM-DD HH:MM"` / `main done M001 --evidence <run\|path\|commit>` / `main status` |
| 芽 | `uv run labkit seed add "<芽>" --from <run\|file> --test "<最安の確かめ方>" --value "<当たれば>"` / `seed decide S001 --to try\|park\|promote\|drop --reason ... [--serves M001]` / `seed list` |
| 1 拍 | `uv run labkit beat start` → 指示書の手順 → `labkit beat end --line main\|seed:Sxxx\|other --predicted ... --observed ... --decided ... [--runs <id>]` / `beat log`（`/loop 20m /lab-rules:beat`） |
| 正本の写し | `uv run labkit mirror push`（`configs/paths/*.toml` の `mirror_root`）/ `mirror pull` |
| 開発ログ / ADR | `uv run labkit devlog`（変更ファイルと run を自動で埋める）/ `uv run labkit adr "タイトル" --slug slug` |
| 文献 | `uv run labkit lit add --doi 10.x \| --arxiv 2606.09554 --tags ...`（一次情報から取得）/ `lit read <citekey> --by human [--scope full]` / `lit queue [--min-relevance 4]`（人間の読書キュー）/ `lit survey --question ...` / `lit surveys` / `lit index` |
| レビュー記録の一覧 | `uv run labkit review list [--open]`（未解消の changes-requested） |
| 生データ登録 | 新しいファイルを cp / mv で `data/raw/` へ（上書きは hooks が止める）→ `uv run labkit raw freeze` |
| 数値の引用 | `uv run labkit cite <run_id> <key> --unit dB` → `12.3 dB [run:<id>:<key>]` を文書に貼る |
| 人間への連絡 | `uv run labkit queue ask "<質問>" --options A B --assumed "<決めたことと理由>"`（返事は待たない）/ `queue list` / `queue done <ID>` |
| 移行の手順 | `uv run labkit flow start migrate` → `flow status` → `flow advance` |

## 主線と芽の 1 日

```
人間  : 「今日 12:00 に発表。2 次元の 5 手法の表が要る」
Claude: labkit main set "2 次元の 5 手法の比較表を完成させる"
        labkit main add "比較表" --done "1 本の集計 run・事前登録の全模型" --due "2026-11-10 09:30"
拍    : beat start → 主線の残り時間・主線の割合・芽・直近 24 時間の資源の使い道
        run（serves = "M001"）→ 妙な数字に気づく → labkit seed add "交差で符号が反転" --from run:X --test "1 例を 2 角度で" --value "交差の法則"
        beat end --line main ...       （期限 12 時間前からは main 以外の拍は記録されない）
主線後: seed:S001 の拍で最安の確かめ → 主線に効くなら seed decide S001 --to promote --serves M00N、効かなければ park
```

- 人間は承認しない。Claude が判断の分かれる問いを自分で決め、`labkit queue ask` で知らせて進む。人間は DIGEST と queue を読み、必要なら目標を書き換える。
- 最後の砦は GitHub 側の main のブランチ保護（`docs/SETUP.md`）と、hooks による成果物の保護。

## 本体を改良する

プロジェクトのコピーは直さない。本体を feat ブランチで直し、テスト・レビュー・リリースしてからタグで取り込む（skill `improve-standards`、本体の `CLAUDE.md`）。

## labkit check のコード

| コード | 内容 |
|---|---|
| 成果物の検証（`--claims`。Stop hook が見る） | |
| L002 / L003 | data/raw が MANIFEST と一致しない / 書き込み可能 |
| L020 / L021 / L023 | run の meta.json 無し・スキーマ違反（開始直後の殻は `labkit runs mark <id> --to interrupted`） / running のまま（警告。`labkit runs mark`） / 実行した labkit の版がプロジェクトの固定版と違う（警告） |
| L022 | data/interim・processed の派生ファイルにサイドカーが無い（サブディレクトリも。data/cache は対象外） |
| L024 | 予想（`prediction`）のある run が finished なのに判定（`prediction_result`）が無い（警告。`labkit runs verdict`） |
| L030 | 開発ログの書式違反、目的・判断と理由・未解決 が空 |
| L032 / L033 / L034 | 引用した run が無い（failed・link・退避済みは警告、dirty は `check.dirty_citation`、既定 warn） / 数値が metrics.json と一致しない / 結果節の数値に引用が無い（警告。引用を含む行は対象外）。対象は `check.claim_docs`（既定 docs/**/*.md と surveys）。自動ブロックと DIGEST は見ない |
| L025 / L026 | 主線の期限切れの open な項目（警告） / 主線・芽の台帳の書式（ID の重複・状態・期限・根拠の無い done・serves の無い promoted） |
| L036 | 主張の台帳 `docs/claims.md` の書式、撤回の理由、open な主張の根拠が無い・failed・dirty・退避済みの run |
| L038 | 結果・主張の節が scratch/ のファイルを根拠にしている（警告） |
| 体裁（pre-commit・CI） | |
| L001 / L004 / L050 | トップレベルの不許可ファイル / 衝突マーカー / 本体を link したまま |
| L005 | `prompts/current.toml` が指す goal/beat が無い、またはより新しい版がある（警告） |
| L010–L018 | 描画ライブラリの直接 import、src→scripts 依存（scripts→scripts は警告）、絶対パス（jobs/ も）、禁止形式、図・データの置き場所、np.save（警告）、どこからも使われない src のモジュール（警告。configs の `entry` も使用に数える）、`check.max_file_lines`（既定 300、空行を除く）を超えるファイル（警告。例外は `max_lines_allowed`） |
| L031 / L035 / L037 | ADR の書式 / レビュー記録の書式（`summary` 無しは警告、`resolves` の先が無いと違反） / state.md の構造（H1 が 2 つ以上・同じ H2 が 2 回以上は違反、`[state] max_lines`（150）超は警告） |
| L040–L048 | 文献管理の書式。L047: status が read/key なのに `claims` が空か `read_scope` が abstract 以下（警告）。L048: done のサーベイに `verdict`・`n_opened` が無い（警告） |

## テスト

```bash
make test        # 版の整合性 + lint + labkit（hooks の判定を含む）+ 雛形の生成
```
