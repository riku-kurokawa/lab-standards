# Changelog

## v0.3.0 — 2026-11-01

「Claude を規約と手順に忠実に従わせるハーネス」。人間が不在でも止まらず、取り返しのつかない操作はしない。全体像は `docs/harness.md`、
Claude Code の仕様の確認は `docs/notes/claude-code-spec.md`。

### 追加
- **承認ゲート**（hooks `guard_bash`）: `git push` / `git tag` / 保護ブランチへの `git merge` / `gh pr merge` / `gh release` /
  `labkit raw freeze` / `copier copy|update` / `labkit standards template` を止める。`command git push`、`git -c x=y -C dir push`、
  連結コマンド、`uv run labkit ...` も検出。`presence=away`（既定）では拒否して `.lab/queue/<ID>.json` に記録、`here` では確認画面。
- `labkit presence here|away|status`、`labkit queue list|ask|done|show`、`labkit approve|reject <ID>`（人間のみ。対話端末では ID の再入力）、
  `labkit answer <ID> "..."`。承認はコマンド全文 + HEAD に結び付き、24 時間で期限切れ、1 回限り。
  Claude は `labkit approve/reject/answer` を実行できず、`.lab/approvals|queue|flows` を Write/Edit/リダイレクトで書けない。
- **手順の状態機械** `labkit flow start|status|advance|abort|list`（migrate、improve-standards）。定義は `labkit/flows/*.toml`、
  状態は `.lab/flows/<name>.json`（git 管理）。advance が完了条件を検査し、承認が要る段階はキューに積む。hooks が段階外の操作を拒否。
- **独立レビュー**: `docs/reviews/YYYY-MM-DD_<flow>_<段階>.md`（frontmatter: reviewer, flow, stage, commit, verdict, findings）。
  書き込みは hook 入力の `agent_type` が lab-reviewer のときだけ。lab-reviewer は他のファイルを書けず Bash は読み取り専用。
  `labkit review template <flow> <stage>`（frontmatter の雛形）。
- **labkit check** L032（文書が引用する run の存在。failed / link 中の run は警告）、L033（`12.3 dB [run:<id>:<key>]` 書式と
  metrics.json の照合。書式なし数値は警告、`[check] cite_bare_numbers = "off"` で無効化）、L035（レビュー記録の書式）。
  Issue に severity（error / warn）を追加。警告は strict でも終了コード 0。
- `labkit cite <run_id> <key> [--digits N] [--unit dB]`（Python `labkit.cite`、Julia `LabKit.cite`）。
- SessionStart（compact 含む）と UserPromptSubmit の hook が、承認済み・未実行の要求、承認待ち、質問、進行中の flow の段階を文脈に入れる。
  Stop hook は承認待ちが理由のときは止め直さない。
- lab-standards 本体（`.lab-standards-root`）でも承認ゲートだけを有効にする。
- plugin eval 7 ケース（`claude-plugin/evals/`、`make eval`。CI では手動起動のみ）。
- 雛形: `.claude/settings.json` に sandbox（data/raw・lab.toml・.lab/approvals・.lab/queue を denyWrite、PyPI/GitHub/Julia を許可）、
  `lab.toml` に `[gate]`、`docs/reviews/`、CLAUDE.md と skills（migrate-project、improve-standards、write-devlog、lab-conventions）を flow と cite に合わせて改訂。

### 修正
- LabKit.jl `freeze_run`: Windows ではディレクトリの chmod を省く。Julia の chmod は削除権限の無い ACL を書き、完了した run を
  通常の手段で削除できなくしていた（Python 版はディレクトリに実質何もしない）。既に凍結済みの run は
  `icacls <run> /grant "%USERNAME%:(OI)(CI)F" /t` か Julia の `chmod(dir, 0o755; recursive=true)` で戻せる。

### 変更
- `.lab/` の読み書きは `claude-plugin/scripts/_labstate.py` を正本とし、labkit はそのコピー（`labkit/_labstate.py`、テストで一致を検査）を使う。
  `labkit queue list` は壊れた JSON を表示しなくなり、承認待ち要求には差分の要約（`git diff --stat`、直近の commit）が常に付く。
- 雛形の `permissions.deny` から `Write(...)` を削除（公式ドキュメント上効かない。`Edit(...)` が Write も止める）。
- `layout.allowed` に `.lab` を追加（古い lab.toml でも暗黙に許可）。質問の置き場は `.lab/queue`（`labkit queue ask`）の 1 つ。

### 移行（v0.2.0 のプロジェクト）
```bash
uv run labkit standards unlink --to v0.3.0 && git commit -am "lab-standards v0.3.0"
uv run labkit standards template --ref v0.3.0      # settings.json の sandbox、lab.toml の [gate]、docs/reviews/ を取り込む
```
`.lab/` は最初に必要になったときに labkit が作る（`.lab/.gitignore` 付き）。承認ゲートは既定で有効（away）なので、
初回の push は承認待ちになる。無効にするなら `lab.toml` の `[gate] enabled = false`。GitHub 側の main ブランチ保護を推奨。

## v0.2.0 — 2026-10-30

プロジェクトで作業しながら本体を改良し、そのプロジェクトへ反映するフローを追加。

### 追加
- `labkit standards status | link | unlink --to vX.Y.Z | template --ref <ref>`:
  プロジェクトの labkit / LabKit.jl を手元の本体チェックアウト（`$LAB_STANDARDS_DEV` か `~/dev/lab-standards`）に
  つなぎ替える（link）／リリースタグに戻す（unlink）／`copier update` で雛形を取り込む（template）
- `labkit check` L050: link したままの状態を違反にする（pre-commit で commit を止める。作業終了時の hook では止めない）
- `labkit check --ignore <codes>`
- run の `meta.json` に `labkit_source`（release / link、link なら本体の commit と dirty）を記録（Python・Julia）
- skill `improve-standards`（振り分け → ブランチ → link → 改良と試用 → リリース → unlink と取り込み）
- 本体用 `CLAUDE.md`（メンテナンス規約）、`tools/release.py`（版の一括更新と整合性検査）
- SessionStart hook: link 中であることと improve-standards の存在を文脈に入れる

### 修正
- labkit（Python）`standards link`: Windows のパス（`\` 区切り）を書き込むと `re.sub` の置換文字列として
  解釈されて失敗した。パスは `/` 区切り（`Path.as_posix()`）で書き、置換はリテラルで行うようにした
  （`/` 区切りのパスは TOML・uv・Pkg のいずれでも OS を問わず有効）
- LabKit.jl `save()`: `fmt` を `try` ブロック内で代入していたため、ブロックの外で未定義になり
  `UndefVarError: fmt` で常に失敗していた（`local fmt` を追加）
- LabKit.jl `_check_writable()`: 読み取り専用領域の判定が `/` 区切り固定で、Windows では `data/raw` への
  書き込みを拒否できなかった。`normpath` と `joinpath` で OS のセパレータに合わせた
- LabKit.jl `load()`（Parquet）: mmap で開いたファイルが GC まで解放されず、Windows では読み込んだ直後に
  削除・上書きできなかった。`use_mmap=false` で読むようにした

### 移行（v0.1.0 のプロジェクト）
```bash
uv run labkit standards unlink --to v0.2.0 && git commit -am "lab-standards v0.2.0"
uv run labkit standards template --ref v0.2.0
```
v0.1.0 の labkit には `standards` コマンドが無いので、初回だけ `pyproject.toml` と `jl/Project.toml` のタグを手で
`v0.2.0` に書き換えて `uv sync` してもよい。

## v0.1.0 — 2026-10-30

初版。

- labkit（Python）/ LabKit.jl（Julia）: 設定（TOML + extends）、run 管理、HDF5/Parquet の保存と来歴サイドカー、環境別パス
- labkit CLI: check, fig（8 テンプレート）, raw freeze/verify, devlog, adr, lit, runs, mlflow sync/ui, paths
- copier テンプレート: ディレクトリ構造、lab.toml、CLAUDE.md、Makefile、pre-commit、HPC ジョブ雛形、文献管理
- Claude Code plugin（lab-rules）: パス保護・Bash 保護・自動整形・終了時チェック・compact 後の規約再注入、10 skills、レビュー agent

### 既知の制限

- Zarr の `save()` は未対応（v0.2 予定）。`writer()` で包めば保存・来歴記録は可能
- 図は Python（matplotlib）で描画。Julia からは `LabKit.fig()` が labkit CLI を呼ぶ
