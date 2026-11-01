# Changelog

## v0.4.0 — 2026-11-01

「人間を待って止まらない」。v0.3 のハーネスは取り返しのつかない操作を人間の承認に委ねたが、実際の移行（accelerated-diff-pat、
2026-11-01）では、承認 1 件ごとに作業が止まり、承認が HEAD に結び付くため commit のたびに積み直しになった。
人間が「この期間、この種類の操作は任せる」と一度宣言できる**委任**を足す。

### 追加
- **委任** `labkit delegate <カテゴリ...> [--hours N（既定 8）] [--note ...]`（人間のみ。hooks が Claude の実行を拒否する）、
  `labkit delegate list`、`labkit delegate revoke <ID|all>`。記録は `.lab/delegations.json`（git 管理外）。
  カテゴリ: `git_push` `git_tag` `git_merge` `gh_merge` `gh_release` `raw_freeze` `template`（承認ゲートの対象）、
  `flow`（承認段階を待たずに進む）、`raw_write`（data/raw への搬入。削除は委任しても拒否）、`lab_toml`（`labkit mode` と編集）。
  グループ: `release`、`migrate`（flow, raw_write, raw_freeze, lab_toml, template）、`all`。
  期間内は hooks が該当カテゴリを通し（理由に委任 ID）、flow の段階が禁止していても人間の判断を優先する。承認と違い、コマンド全文や HEAD に結び付かない。
- `labkit mode [warn|strict]`: `lab.toml` の `[check] mode` を表示・切替。Claude には承認ゲートの対象（`lab_toml` の委任があれば通る）。
- SessionStart が有効な委任を文脈に入れる。承認待ちの拒否メッセージが、承認のほかに委任の方法も示す。

### 変更
- `labkit flow advance` の承認は HEAD ではなく **段階**（`flow:<name>:<stage>`）に結び付く。承認の後に commit しても無効にならない。
  `.lab/flows/<name>.json` の history に `via`（`approval:Q001` / `delegation:D001`）を記録する。
- `labkit raw freeze` / `check`（L002・L003）は隠しディレクトリ（`.git/` など、生データとして置いた checkout のメタデータ）を台帳に入れない。
  git は読むだけの操作でも `.git/index` を書き換えるので、固定すると検査のたびに「改変」になっていた。旧台帳の該当行は読まず、次の freeze で消える。
- `_labstate.py`: `request_approval(..., head=)` で結び付け先を上書きできる。

### 移行
- 既存プロジェクトは `labkit standards template --ref v0.4.0`（`.gitignore` に `/.lab/delegations.json`）と `pyproject.toml` のタグ更新。
  委任を使わなければ挙動は v0.3 と同じ（既定は従来どおり承認待ち）。

## v0.3.1 — 2026-11-01

### 修正
- CI: python ジョブの runner にも julia があるため言語間テストが未 instantiate の環境で走って落ちていた → python ジョブでは除外（julia ジョブが実行）。
- LabKit.jl のテスト: JSON の検査が Dict の順（Julia の版で異なる）に依存していた（1.11 で失敗、1.13 で通過）→ 順に依らない検査に。
  labkit / LabKit.jl の動作に変更なし。

## v0.3.0 — 2026-11-01

「Claude を規約と手順に忠実に従わせるハーネス」。人間が不在でも止まらず、取り返しのつかない操作はしない。全体像は `docs/harness.md`、
Claude Code の仕様の確認は `docs/notes/claude-code-spec.md`。

### 追加
- **承認ゲート**（hooks `guard_bash`）: `git push` / `git tag` / 保護ブランチへの `git merge` / `gh pr merge` / `gh release` /
  `labkit raw freeze` / `copier copy|update` / `labkit standards template` を止める。`command git push`、`git -c x=y -C dir push`、
  連結コマンド、`uv run labkit ...` も検出。`presence=away`（既定）では拒否して `.lab/queue/<ID>.json` に記録、`here` では確認画面。
- `labkit presence here|away|status`、`labkit queue list|ask|done`、`labkit approve|reject <ID>`（人間のみ。hooks が Claude の実行を拒否する）、
  `labkit answer <ID> "..."`。承認はコマンド全文 + HEAD に結び付き、24 時間で期限切れ、1 回限り。
  Claude は `labkit approve/reject/answer` を実行できず、`.lab/approvals|queue|flows` を Write/Edit/リダイレクトで書けない。
- **手順の状態機械** `labkit flow start|status|advance|abort`（migrate、improve-standards）。定義は `labkit/python/src/labkit/flows/*.toml`（パッケージ同梱）、
  状態は `.lab/flows/<name>.json`（git 管理）。advance が完了条件を検査し、承認が要る段階はキューに積む。hooks が段階外の操作を拒否。
- **独立レビュー**: `docs/reviews/YYYY-MM-DD_<flow>_<段階>.md`（frontmatter: reviewer, flow, stage, commit, verdict, findings）。
  書き込みは hook 入力の `agent_type` が lab-reviewer のときだけ。lab-reviewer は他のファイルを書けず、Bash は許可リストの読み取りコマンドだけ（拒否時に許可一覧を表示）。
  `labkit review template <flow> <stage>`（frontmatter の雛形）。
- **labkit check** L032（文書が引用する run の存在。failed / link 中の run は警告）、L033（`12.3 dB [run:<id>:<key>]` 書式と
  metrics.json の照合。書式なし数値は警告、`[check] cite_bare_numbers = "off"` で無効化）、L035（レビュー記録の書式）。
  Issue に severity（error / warn）を追加。警告は strict でも終了コード 0。
- `labkit cite <run_id> <key> [--digits N] [--unit dB]`（Python は関数 `labkit.cite()`（実装は `labkit.check`）、Julia `LabKit.cite`）。`--digits N` は小数点以下の桁数（既定の有効数字 4 桁とは別の規則）。
- SessionStart（compact 含む）の hook が承認待ち・質問・進行中の flow の段階を文脈に入れ、UserPromptSubmit の hook は人間の操作による差分
  （承認済み・未実行、回答あり、却下）だけを添える。
  Stop hook はこのセッションが積んだ承認待ちがあるときは止め直さない。
- lab-standards 本体（`copier.yml` と `labkit/` を持つリポジトリ）でも承認ゲートだけを有効にする。
- plugin eval 7 ケース（`claude-plugin/evals/`、`make eval`。CI では手動起動のみ）。
- 雛形: `.claude/settings.json` に sandbox（data/raw・lab.toml・.lab/approvals・.lab/queue・.lab/flows を denyWrite、PyPI/GitHub/Julia を許可）、
  `lab.toml` に `[gate]`、`docs/reviews/`、CLAUDE.md を改訂。plugin の skills（migrate-project、improve-standards、write-devlog、lab-conventions）を flow と cite に合わせて改訂。

### 変更
- 例のコード・設定・figspec・ジョブ・手元パス（configs/base.toml、configs/experiments/example.toml、configs/paths/local.toml、
  figspecs/example_*.toml、scripts/run_example.py、jobs/slurm_example.sh、src/<pkg>/__init__.py・filters.py、tests/test_filters.py、
  jl/src・scripts・test）を copier の `_skip_if_exists`（種）に。
  研究者が書き換える前提のファイルを雛形側の変更で衝突させない。更新を受けるのは規約の器（lab.toml、Makefile、pyproject、CLAUDE.md、settings.json など）。

### 追加
- `labkit check` L004: マージの衝突マーカー（`<<<<<<< ` / `>>>>>>> ` で始まる行）。`labkit standards template`（copier update）が残した衝突を、
  pre-commit を入れていなくても check（Stop hook・CI）で止める。`standards template` は衝突したファイルを列挙する。

### 修正
- `labkit fig`: figspec の配列名・列名・`[data]` のキーの打ち間違いは traceback（KeyError）ではなく、figspec を名指しした 1 行
  （HDF5 ではある名前を列挙）。errorbar の `err` は sd | se | ci95 以外を拒否。
- Julia の `LabKit.check()` / `labkit_cli(...)` は終了コードを返す（違反があると例外になっていた。Python の `labkit.check()` と同じ契約）。
- labkit が書くテキスト（meta.json、metrics、log、サイドカー、MANIFEST、devlog/ADR の雛形、link の書き換え）を OS に依らず LF に
  （Windows では CRLF になり、LF で書く Julia 側や他の機械との間で差分が出ていた）。テストが機械的に検査する。
- `tools/release.py X.Y.Z` は CHANGELOG の節を確かめてから版を書き換える（従来は 6 ファイルを書き換えた後に失敗していた）。
- plugin eval の scaffold: 種の meta.json に必須の `command` が無く、すべてのケースが Stop hook の L020 で止まっていた。Git Bash では本体の
  パスが `file:///C:/c/...` になり scaffold が失敗していた（cygpath で変換）。`case.yaml` の未定義キー `tags` を削除。
- HDF5 の bool（配列・スカラー）を uint8 + データセット属性 `labkit_dtype="bool"` で保存し、Python / Julia とも bool に戻す。
  従来は h5py の enum / HDF5.jl の Bool 型で書かれ、相手言語では Int8 / uint8 になっていた（旧ファイルの読み込みは従来どおり）。
- 雛形の `.claude/settings.json` の `env` に `PYTHONUTF8=1`（Windows で自作スクリプトの出力や他ツールも UTF-8 に揃える。SETUP.md に端末側の設定も記載）。
- `labkit` CLI の出力を UTF-8 に固定（hooks と同じ）。cp932 既定の Windows でパイプ越し（Claude Code の Bash、Stop hook、Julia の `cite`）に日本語が文字化けしていた。
- Windows（PYTHONUTF8 無し、既定 cp932）で、日本語を含む meta.json / サイドカー / devlog の読み書きや hooks の出力が壊れうる箇所を修正:
  すべてのテキスト入出力と子プロセスの復号に `encoding="utf-8"` を明示。hooks の UTF-8 固定を python 版の検査より前に。新しいテストが違反を機械的に検出する。
- `labkit standards status` と flow の条件 `linked` は、`pyproject.toml` の無いプロジェクト（雛形適用前）で例外にならず unknown（link ではない）を返す。
- `labkit review template improve-standards test` が入れる `commit:` を本体（lab-standards）の HEAD に。完了条件 `review repo="standards"` が照合するのは本体の HEAD
  なので、従来のプロジェクトの HEAD では test 段階が advance できなかった。
- `load()`（Python / Julia）: 無いファイルは `<path> がありません` と言う（従来 verify=True ではサイドカーの不在を先に報告し、原因を取り違えさせた）。
- CLI の誤用（無い run・ファイル、不正な figspec、TOML の文法エラー、読み取り専用領域、`cite` の無いキー）は traceback ではなく
  `labkit: <理由>` の 1 行で伝える（終了コード 1）。TOML の文法エラーにはファイル名を付ける。`review template` は無い flow/段階を拒否する。
- 図テンプレート `heatmap`: 文書どおりの `z[i, j] = f(x_i, y_j)`（shape (len(x), len(y))、Julia の size と同じ）で描けなかった
  （matplotlib は行＝y を期待するため、正方でない配列はエラー、正方なら転置して描いていた）。規約を明示し、形を検査して転置して渡す。
  histogram / scatter / errorbar / heatmap のテストを追加（従来は 8 テンプレート中 4 つだけがテスト対象だった）。
- hooks: `python3` が 3.11 未満（tomllib なし）のとき、黙って検査を無効化せず exit 1 と説明を出す（macOS の標準 python3 は 3.9 で、
  ハーネス全体が静かに動かなかった）。SETUP に python3 のバージョン要件を追記。
- `labkit cite` の既定の表示を「有効数字 4 桁」の 1 規則に統一（以前は 123456.789 だけ全桁になるなど不揃い）。
  1 万以上の整数は `2e+04` のように指数表示になるので、整数のまま出したいときは `--digits 0`。
- 記録に書く相対パス（meta.json の inputs/outputs、サイドカー、`data/raw/MANIFEST.sha256`）とディレクトリ入力の sha256 を
  OS に依らず `/` 区切りにした（Python・Julia とも）。Windows で凍結した MANIFEST を HPC（Linux）で検証できなかった。
  旧版の `\\` 区切りの MANIFEST 行は読む側で受け付ける。Windows で記録したディレクトリ入力のハッシュだけは値が変わる（元々移植不能だった）。
  Julia 版は Windows で `rel_or_abs` が常に絶対パスを返していたのも修正。
- `labkit check`: Windows で `figure_ok_dirs` / `data_ok_dirs` の除外が効かず（`\\` 区切りの比較）、docs/assets の図が L014 になっていた。
  違反の位置も OS に依らず `/` 区切りで出す（`file:line` のリンクになる）。
- LabKit.jl の JSON 書き出し（meta.json / metrics.json / サイドカー）で `2.0` が `2` になっていた（JSON3.pretty が数値を
  読み直して整数化する）。再パースしない字下げに置き換え、Python の json.dumps と同じ型・同じ形で書く。
- `labkit flow`: lab.toml が無いディレクトリでも git の最上位を root として動く（migrate の freeze / inventory は雛形適用前に行うため）。
  他のコマンドは従来どおり lab.toml を要求する。
- LabKit.jl `freeze_run`: Windows ではディレクトリの chmod を省く。Julia の chmod は削除権限の無い ACL を書き、完了した run を
  通常の手段で削除できなくしていた（Python 版はディレクトリに実質何もしない）。既に凍結済みの run は
  `icacls <run> /grant "%USERNAME%:(OI)(CI)F" /t` か Julia の `chmod(dir, 0o755; recursive=true)` で戻せる。

### 変更
- copier の `_skip_if_exists`: README.md、docs/data-dictionary.md、初期 ADR、references.bib、tags.toml、MANIFEST.sha256 は生成後に
  `copier update` で触らない（書き換えたプロジェクトの README に衝突マーカーが入っていた）。例のコードと設定は引き続き更新を受ける。
- hooks: 編集ごとの ruff（PostToolUse の自動整形と lint）を廃止し、終了時（Stop）に `ruff check` を 1 回だけ行う。
  整形は commit 時の pre-commit と `make fmt` に任せる（編集直後の自動整形は次の Edit の old_string を外す原因だった）。
- 雛形の pre-commit: ruff と nbstripout を `repo: local`（`uv run ...`）で動かし、uv.lock の版を使う（`make lint` と同じ ruff。
  ruff-pre-commit の版を別に管理しない）。pre-commit-hooks を v6.0.0 に。dev 依存の下限を ruff>=0.17, pre-commit>=3.2, nbstripout>=0.9 に。
  既存プロジェクトは `labkit standards template --ref v0.3.0` の後に `uv sync && uv run pre-commit install`（hook ID が ruff → ruff-check に変わる）。
- `lab.toml` の `[lab] standards_version` を書かなくした（どこからも読まれていなかった。残っていても無視される）。生成元の版は
  `.copier-answers.yml` の `standards_ref` / `_commit`（`labkit standards status` が表示）。
- `.lab/` の読み書きは `claude-plugin/scripts/_labstate.py` を正本とし、labkit はそのコピー（`labkit/_labstate.py`、テストで一致を検査）を使う。
  `labkit queue list` は壊れた JSON を表示しなくなり、承認待ち要求には差分の要約（`git diff --stat`、直近の commit）が常に付く。
- 雛形の Makefile から単発コマンドの薄いラッパー（raw-freeze, raw-verify, devlog, runs, lit-index, std-*）を削除。`uv run labkit <cmd>` を使う。
  残るのは複数手順をまとめる check / test / lint / fmt / example / mlflow-*。承認ゲートは古い Makefile の `make raw-freeze` / `make std-*` も引き続き検出する。
- 雛形の `permissions.deny` から `Write(...)` を削除（公式ドキュメント上効かない。`Edit(...)` が Write も止める）。
- `layout.allowed` に `.lab` を追加（古い lab.toml でも暗黙に許可）。質問の置き場は `.lab/queue`（`labkit queue ask`）の 1 つ。

### 移行（v0.2.0 のプロジェクト）
```bash
uv run labkit standards unlink --to v0.3.0 && git commit -am "lab-standards v0.3.0"
uv run labkit standards template --ref v0.3.0      # settings.json の sandbox、lab.toml の [gate]、docs/reviews/ を取り込む
```
v0.2.0 で生成したプロジェクトに対して衝突なく適用できることを確認済み（2026-11-01）。`.lab/` は最初に必要になったときに labkit が作る（`.lab/.gitignore` 付き）。承認ゲートは既定で有効（away）なので、
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
