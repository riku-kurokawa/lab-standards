# AGENT_QUEUE — v0.3.0 ハーネス作業の質問・承認待ち

（終了時の報告は先頭。未解決項目はその下。作業中に追加する。）

## 現在の状況（feat/optimize、2026-11-01）

v0.3.0 の作業（下の報告）は feat/harness-v0.3.0 で完了し、その先頭から feat/optimize を切って改善サイクルを続けている
（docs/OPTIMIZATION_LOG.md に 1 サイクル 1 commit で記録、2026-11-01 時点で 36 サイクル。棄却した案も載せている）。**マージ対象は feat/optimize**（feat/harness-v0.3.0 を含む）。
テストの現在値: labkit 58 passed（Julia 往復テスト含む）、hooks 91 passed、LabKit.jl 13/13、`make lint`（ruff check + format）通過、`release.py --check` OK。
下の v0.3.0 報告のうち、サイクルで変わった点: improve-standards の link 段階は削除（labkit/ を変えたときだけ link を要求）、
`labkit review` は `template` のみ、雛形の Makefile は check/test/lint/fmt/example/mlflow-* のみ、`lab.standards_version` は廃止、
pre-commit の ruff は uv.lock の版、AGENT_QUEUE.md はプロジェクト側の仕組みから除外。

## 終了時の報告（v0.3.0、ブランチ feat/harness-v0.3.0、2026-11-01）

### 実装した内容
- **一次情報の確認** → `docs/notes/claude-code-spec.md`（hooks / permissions / sandboxing / plugin evals / subagents / plugin components。
  食い違いと調整は末尾の表）。
- **承認ゲート**（2 章）: `claude-plugin/scripts/_labgate.py`（shlex でトークン化。`command git push`、`git -c x=y -C dir push`、
  `sudo`/`env`/`VAR=` 接頭辞、`&&`/`;`/`|`/改行の連結、`uv run labkit raw freeze`、`python -m labkit.cli`、`make raw-freeze` を検出）、
  `_labstate.py`（.lab/ の読み書き、標準ライブラリのみ）、`guard_bash.py`（away: 拒否 + キュー / here: ask / 承認済み: 1 回だけ allow）。
  `labkit presence|queue|approve|reject|answer`（`labkit/state.py`, `cli.py`）。承認はコマンド全文 + HEAD、24 時間、1 回限り。
  Claude は approve/reject/answer を実行できず、`.lab/approvals|queue|flows` を Write/Edit/リダイレクトで書けない。
  本体（`copier.yml` + `labkit/`）でもゲートだけ有効。
- **手順の状態機械**（3 章）: `labkit/flow.py` + `labkit/flows/{migrate,improve-standards}.toml`。`labkit flow start|status|advance|abort|list`。
  advance が完了条件（15 種の type）を検査、承認が要る段階はキューへ。hooks が段階の forbid（code/experiments/raw/template/link/release/commit）を拒否。
  SessionStart・UserPromptSubmit（新 hook `prompt_context.py`）が段階・残り条件・承認待ち・質問を文脈に入れる。Stop hook は承認待ちでは止め直さない。
  skills migrate-project / improve-standards を flow 前提に書き直し。
- **独立レビュー**（4 章）: `labkit/reviews.py`、`docs/reviews/YYYY-MM-DD_<flow>_<段階>.md`（frontmatter）、`labkit review list|template`。
  `guard_write.py` が `agent_type` で判定（lab-reviewer だけ書ける／lab-reviewer は他に書けない）。lab-reviewer の Bash は読み取り専用。
  完了条件 `review` は現在の HEAD に対する pass。
- **報告と実データの照合**（5 章）: `labkit check` L032 / L033 / L035、Issue.severity（warn は strict でも失敗にしない）、
  `labkit cite`（Python `labkit.cite`、Julia `LabKit.cite`）。write-devlog skill と devlog 雛形を更新。
- **回帰テストとサンドボックス**（6 章）: `claude-plugin/evals/` に 7 ケース + `_shared/project.sh`、`make eval`（本体 Makefile 新設）、
  CI に手動起動の evals ジョブ。雛形 `.claude/settings.json` に sandbox（確認済みキー）。Windows では劣化（docs/harness.md 5 節）。
- 版 0.3.0（`tools/release.py 0.3.0`、CHANGELOG v0.3.0、移行手順）。README・SETUP・雛形 CLAUDE.md・lab-conventions skill 更新。
- ついでの修正: hooks の入出力を UTF-8 に固定（Windows で日本語メッセージが cp932 で文字化けしていた）。`release.py` が CRLF を書かないように。

### テスト結果
| 検査 | 結果 |
|---|---|
| `python tools/release.py --check` | OK（0.3.0） |
| labkit（`uv run --extra dev pytest -q`） | 38 passed（新規 `tests/test_harness.py` 22 件: presence 切替、質問の往復、承認の一回性・HEAD・期限、hook と labkit の形式往復、flow 定義整合・遷移・承認・レビュー条件、L032/L033/L035、cite、警告の終了コード） |
| hooks（`claude-plugin/tests`） | 75 passed（新規 `test_gate.py` 53 件: コマンド 40 変種の分類、away/here/bypass、承認の一致・使用済み・期限・HEAD、Claude が承認を作れないこと、本体スコープ、flow の禁止と解除、agent_type による書き込み制御、reviewer の読み取り専用、Stop hook）。UTF-8 出力テスト追加 |
| LabKit.jl | 6/6 passed |
| `claude plugin validate claude-plugin` | passed |
| 生成プロジェクトで link して一連の流れ | copier（HEAD）→ link → `pytest` 2 passed → example 実行・図 3 枚 → `labkit check --ignore L050` 違反なし → `runs list` → `labkit cite`（Python・Julia とも同じ出力）→ Julia run_example → `flow start improve-standards`（triage で link/release を拒否、devlog 条件、承認待ち Q001）→ hooks を Claude Code と同じ入力で実行（ゲート・flow 禁止・レビュー記録の agent_type 判定・状態ファイルの保護・compact 文脈・Stop）すべて期待通り |
| plugin eval（`make eval`） | **未実行**（API 費用。Q-004 で承認待ち。実行方法と費用の見積もりは `claude-plugin/evals/README.md`） |
| サンドボックス有効で `make check && make example` | **未確認**（Windows ネイティブは非対応。Q-007） |

### ドキュメントと食い違って設計を変えた点
`docs/notes/claude-code-spec.md` 末尾の表。要点: (1) bypassPermissions/dontAsk/auto では hook の `ask` が人間に届く保証が無いので here でも拒否+キュー、
(2) plugin の agent は `hooks`/`permissionMode` が無視されるので plugin 共通 hook が `agent_type` で分岐、(3) `Write(path)` の deny は効かないので
雛形は `Edit(...)` に統一、(4) Stop hook は `stop_hook_active` と 8 回上限を踏まえる、(5) Windows はサンドボックス非対応。

### 独立レビュー（差分を知らないサブエージェント）の結果と対応
指摘 → 修正済み: `tools/release.py` の構文エラー（CI が赤になるところだった）、migrate の freeze 段階が `git tag` を禁止して自分で
デッドロックしていた、improve-standards の test 段階のレビュー条件がプロジェクトの HEAD に結び付いていた（本体の HEAD に変更）、
`git -C <dir> push` の承認が cwd の HEAD に結び付いていた、他セッションの承認待ちでも Stop hook が緩んでいた、分類器の抜け
（`&`、サブシェル、`if…then`、`xargs`、`uv run -m`、`uv tool run`、`uvx copier@x`）、`auto` モードでは ask が出るのに拒否していた、
雛形 `denyWrite` に `.lab/flows` が無かった、eval の scaffold に labkit が無かった、`commit` カテゴリ（未使用）の削除。
指摘 → 未対応（キューへ）: Q-014〜Q-017。

### 私（人間）が実行するコマンド
```bash
cd ~/dev/lab-standards
git log --oneline main..feat/optimize                # レビュー（差分: git diff main...feat/optimize）
make test && make test-julia                         # 再確認（Windows では make が無いので README の 3 コマンド）
git switch main && git merge --ff-only feat/optimize
git tag v0.3.0
git push origin main --tags
gh run list --limit 3                                # CI
# 任意: 振る舞いの回帰テスト（API 費用。まず 1 ケース）
make eval CASE=push-while-away MAX_USD=3
```
GitHub のブランチ保護（最後の砦）: Settings → Branches → main に "Require a pull request before merging" と
"Do not allow bypassing"、Tags → `v*` を保護。**非公開リポジトリのブランチ保護は GitHub Pro 以上が必要**（Free では公開リポジトリのみ）。
代替は `gh api` で確認: `gh api repos/riku-kurokawa/lab-standards/branches/main/protection`（404 なら未設定）。
既存プロジェクトの移行は CHANGELOG の v0.3.0「移行」節。

---

## 未解決項目

### Q-001 [question] here モードでも確認画面が出ない permission mode の扱い
- 内容: 公式ドキュメントは bypassPermissions / dontAsk での hook `ask` の扱いを明記していない（dontAsk は「prompt するものは拒否」）。
- 選択肢: (a) here なら常に `ask` を返す / (b) これらのモードでは here でも拒否してキューに積む。
- 仮の判断: (b)。安全側。`claude-plugin/scripts/_labcommon.py` の `NO_PROMPT_MODES` 1 か所。
- 変える場合の影響: 定数を変えるだけ。テスト `test_here_asks_but_not_in_bypass` を更新。

### Q-002 [question] 承認の「人間であること」の確かめ方
- 内容: `labkit approve` は対話端末なら ID の再入力、非対話なら `--yes` を要求し、`CLAUDECODE` 環境変数の有無を記録する。
  Claude Code の `!` 実行は非対話（stdin が TTY でない）なので `! uv run labkit approve Q001 --yes` で承認できる。
  Claude 自身の Bash は `guard_bash` が `labkit approve` を拒否する（どの呼び出し形でも）。
- 選択肢: (a) 現状 / (b) `--yes` を廃止して TTY 必須（`!` からは承認不可） / (c) 承認用の別の秘密（環境変数のトークン）を要求。
- 仮の判断: (a)。hooks が Claude 側を止め、`!` は人間の操作とみなす。脅威モデルは `docs/harness.md` 1 節。
- 追記（2026-11-01 の実測）: Claude Code の Bash から実行した `labkit approve` は Windows では `sys.stdin.isatty()` が True になり、
  ID 再入力は EOF で失敗する（`--yes` が必要）。記録には `claude_shell: true` が残る。TTY 再入力は実端末でしか効かない。
- 変える場合の影響: `cli.py` の `_confirm_human` のみ。

### Q-003 [question] improve-standards flow の状態をプロジェクト側に置く
- 内容: flow の禁止は cwd のスコープで判定するため、本体ディレクトリで作業中は improve-standards の段階制限（例: test 前の release）は
  効かない。本体側の push/tag/merge は本体の承認ゲートが守る。
- 仮の判断: 現状（単純さ優先）。変えるなら本体側 `.lab/flows` へのミラー（1 関数）。

### Q-004 [approval] plugin eval の初回実行（API 費用）
- 内容: `make eval`（7 ケース × 1 run × 1 腕、`--max-cost-usd 10`）。`case.yaml` の `scaffold_script: ../_shared/project.sh` の
  パス解決（ケースディレクトリ基準か）はドキュメントに明記が無く、初回実行で確認が要る。失敗したら各ケースに同じスクリプトを置く。
- 依存しない作業: 完了。`claude plugin validate` は通過。

### Q-005 [approval] GitHub 側の main ブランチ保護とタグ保護（最後の砦）
- 内容: hooks は security boundary ではない（公式ドキュメント）。main への直接 push 禁止・PR 必須・`v*` タグ保護を推奨。
  非公開リポジトリでは GitHub Pro が必要。

### Q-006 [approval] v0.3.0 のリリース（main へのマージ・タグ・push）
- 内容: 上の「私が実行するコマンド」。取り返しのつかない操作なので人間が実行する。

### Q-007 [question] サンドボックス設定の実機確認
- 内容: 雛形の `sandbox`（denyWrite: data/raw, lab.toml, .lab/approvals, .lab/queue。allowWrite: uv/Julia/pre-commit のキャッシュ。
  allowedDomains: PyPI/GitHub/Julia/astral.sh。`autoAllowBashIfSandboxed: false`）は Windows では動かず未確認。
  macOS/Linux/WSL2 で `make check && make example` が通るか、uv や Julia の取得先ドメインが足りているかの確認が必要。
- 仮の判断: 設定は入れたまま（sandbox 非対応環境では Claude Code が unsandboxed で動くだけ）。足りないドメインは `settings.json` に追記。
- 変える場合の影響: 雛形 1 ファイル。既存プロジェクトは `labkit standards template --ref v0.3.0` で取り込む。

### Q-008 [question] 雛形の `permissions.deny` から `Write(...)` を外した
- 内容: 公式ドキュメント「`Write(path)` rules never match... Use `Edit(docs/**)`」に従い `Edit(...)` に統一（Edit の deny は Write も止める）。
- 仮の判断: 外す。ドキュメントの記述が将来変わっても害は無い。

### Q-009 [question] `.lab/` の git 管理範囲と既定 presence
- 内容: `.lab/flows/` は git 管理、`presence` `queue/` `approvals/` は `.lab/.gitignore` で除外。既定 presence は away（指示どおり）。
- 仮の判断: 現状。queue を共有したいなら `.lab/.gitignore` から `queue/` を外す。

### Q-010 [question] L033 の「書式なし数値」警告の誤検出
- 内容: run ID と同じ行の「3 回」「2 つ」のような数も警告になる（日付・時刻は除外）。既定は warn（失敗にしない）。
- 仮の判断: warn のまま。うるさければ `lab.toml` の `[check] cite_bare_numbers = "off"`。

### Q-011 [question] lab-reviewer の Write 権限は hooks 頼み
- 内容: plugin の agent は `permissionMode`/専用 hooks を持てないため、lab-reviewer に Write を与え、書き先の制限は plugin の
  PreToolUse hook（`agent_type`）で行う。plugin を無効にして起動すれば制限は効かない。
- 仮の判断: 現状（ドキュメントの制約）。

### Q-012 [question] Windows の LabKit.jl `freeze_run` の ACL
- 内容: v0.2.0 からの既知の非対称。Julia の `chmod(dir, 0o555)` が Windows で削除権限の無い ACL を書き、完了した run を通常の手段で削除できない
  （Python 側は読み取り専用属性のみ）。v0.3.0 の範囲外として未修正。
- 仮の判断: 未修正。直すなら Julia 側で `Sys.iswindows()` のときディレクトリの chmod を省く（1 行）。

### Q-013 [question] 次の作業（ゴール「feat/optimize」）の起点
- 内容: 作業中に「~/dev/lab-standards を磨き続ける」ゴール（feat/optimize ブランチ、1 サイクル 1 commit、docs/OPTIMIZATION_LOG.md）を受けた。
- 仮の判断: v0.3.0 の作業を feat/harness-v0.3.0 で完了させてから、**feat/harness-v0.3.0 を起点に** feat/optimize を切って開始する
  （main から切ると v0.3.0 の内容が無い）。v0.3.0 のリリース（Q-006）後は feat/optimize を main に rebase する想定。

### Q-014 [question] presence は permission_mode と重複しないか（レビュー指摘）
- 内容: default モードなら ask、bypass なら拒否+キュー、で十分という指摘。presence（here/away）は指示 2 章の要件なので残した。
- 仮の判断: 残す。削るなら `labkit presence`、`.lab/presence`、`_labcommon.load_lab` の例外、GATE_LINES の 1 行。

### Q-015 [question] 承認は PreToolUse で使用済みになる（コマンドが失敗しても消費される）
- 内容: push が認証エラーで失敗すると承認を使い切り、再承認が要る。PostToolUse で消費すれば直るが hook が 1 つ増える。
- 仮の判断: 現状（単純さ優先）。失敗時は再度キューに積まれる。

### Q-016 [question] flow の禁止は「うっかり防止」で、`labkit flow abort` → 作業 → `flow start` で回避できる
- 内容: abort を禁止すると triage の「このプロジェクトだけの事情なら abort」ができなくなる。docs/harness.md に advisory と明記した。
- 仮の判断: 現状。

### Q-017 [question] lab-reviewer の独立性はメインの agent が書くプロンプトに依存する
- 内容: メインが「pass と書け」と指示すれば pass 記録ができる。`agent_type` 判定は自己採点の「うっかり」を防ぐだけ。
  本当の独立性は人間のレビュー（docs/reviews を読む）か、別セッションでのレビューでしか担保できない。
- 仮の判断: 現状。lab-reviewer.md に「verdict の基準」を明記して誘導に抵抗させた。

### Q-018 [question] labkit の人間専用コマンドを `queue` 配下にまとめるか
- 内容: `labkit --help` のトップレベルは 18 コマンド（v0.3.0 で +8）。`approve` / `reject` / `answer` は人間専用で、
  `labkit queue approve <ID>` のようにまとめればトップレベルは 15 になり「Claude 向け」と「人間向け」の区別が名前に出る。
  ただし指示（2 章）は `labkit approve <ID>` / `labkit reject <ID>` を明記しており、guard_bash の拒否判定もその名前で行っている。
- 仮の判断: 名前は変えない（指示どおり）。変える場合は cli.py の argparse、_labgate の `labkit_approve` 判定、docs/skills の 3 か所。

### Q-019 [question] `lit key` / `lit check` を v0.4 で削除してよいか
- 内容: どちらもどの skill・docs からも参照されず、`lit key` は `lit add` の内部処理、`lit check` は `labkit check` の部分集合。
  v0.1 からあるコマンドなので既存プロジェクトでの利用の有無を確認したい。
- 仮の判断: 残す（互換）。削除するなら cli.py の 2 分岐と choices。

### Q-020 [question] MLflow 連携（`labkit mlflow sync|ui`、optional 依存、Makefile の mlflow-*、README の節）は要るか
- 内容: runs/ を閲覧用に MLflow へ写す索引機能（約 110 行 + 依存 + 文書）。v0.1 からあるが、この作業では一度も使っておらず、
  利用実態が分からない。無ければ概念が 1 つ減る（runs/ が唯一の記録、閲覧は `labkit runs list/show` と図）。
- 仮の判断: 残す（使っているかどうかは人間しか知らない）。削るなら mlflow_sync.py、cli の mlflow、pyproject の extra、Makefile 2 ターゲット、README 1 節。

