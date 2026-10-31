# ハーネス: Claude を規約と手順に従わせる仕組み（v0.3.0）

目的は「人間が不在でも、Claude が止まらず、しかし取り返しのつかない操作はしない」こと。
部品は 4 つ: 承認ゲート、手順の状態機械、独立レビュー、報告と実データの照合。すべて hooks（lab-rules plugin）と
`labkit` のコマンドで機械的に検証し、文章だけの規約を増やさない。

```
人間                         Claude Code                          .lab/（プロジェクト直下）
labkit approve Q001  ──→  approvals/Q001.json  ←── guard_bash が照合 ──  git push（同じコマンド全文・同じ HEAD）
labkit answer Q002   ──→  queue/Q002.json      ←── SessionStart / UserPromptSubmit が文脈へ
labkit presence here ──→  presence             ←── here: ask / away: 拒否してキューへ
                          flows/<name>.json    ←── labkit flow start/advance、guard_* が禁止操作を拒否
docs/reviews/*.md    ←── lab-reviewer agent だけが書く（agent_type で判定）
```

## 1. 承認ゲート

対象: `git push`、`git tag`（作成・削除）、保護ブランチ（`[gate] protected_branches`、既定 main/master）への `git merge`、
`gh pr merge`、`gh release`（create/edit/delete/upload）、`labkit raw freeze`、
`copier copy|update|recopy`、`labkit standards template`（古い雛形の `make raw-freeze` / `make std-*` も検出）。
`command git push`、`git -c x=y -C dir push`、`sudo`/`env`/`VAR=x` 接頭辞、`&&`/`;`/`|`/改行で連結したもの、
`uv run labkit ...`、`python -m labkit.cli ...` も検出する（`claude-plugin/scripts/_labgate.py`、shlex でトークン化）。

| presence | 挙動 |
|---|---|
| `away`（既定） | 拒否。`.lab/queue/<ID>.json` に要求（コマンド全文、cwd、ブランチ、HEAD、差分の要約、理由、時刻、session_id）を記録。Claude には「承認待ち #ID として記録した。依存しない作業を続け、終了時の報告に挙げよ」 |
| `here` | `permissionDecision: "ask"` で通常の確認画面。ただし `permission_mode` が bypassPermissions / dontAsk / auto のときは確認画面が出る保証が無いので away と同じ扱い |

承認は人間だけが行う: `labkit queue list` → `labkit approve <ID>`（対話端末なら ID の再入力、非対話なら `--yes`）。
承認は **コマンド全文 + そのときの HEAD** に結び付き、**24 時間**（`[gate] approval_ttl_hours`）で期限切れ、**1 回限り**。
git リポジトリ外では HEAD は「なし」として記録され、コマンド全文・cwd・期限・1 回限りだけで照合する。
hook は一致する承認があるときだけ通し、通したら `used_at` を記録する。`labkit reject <ID>` で却下。

Claude が承認を作れないようにする層:
1. `guard_bash` が `labkit approve|reject|answer`（どの呼び出し形でも）と、`.lab/approvals|queue|flows` への
   リダイレクト・sed・python -c などを拒否する。
2. `guard_write` が `.lab/approvals`, `.lab/queue`, `.lab/flows` への Write/Edit を拒否する（`.lab/presence` は可）。
3. 雛形の `.claude/settings.json` の `permissions.deny`（`Edit(.lab/approvals/**)` など）と
   サンドボックスの `filesystem.denyWrite`（`.lab/approvals`, `.lab/queue`）が OS レベルで書き込みを止める（対応 OS のみ）。
4. `labkit approve` 自身は、実行環境が Claude Code のシェル（`CLAUDECODE=1`）かを記録する（`claude_shell`）。
   人間が Claude Code の `!` 実行で承認した場合もこのフラグが付く。`!` 実行が PreToolUse hook を通らないことは公式ドキュメントに明記が
   無く、本セッションでの観察（`!` の出力に hook のメッセージが出ない）に基づく（AGENT_QUEUE Q-002）。

### 脅威モデル

| 防げる | 防げない |
|---|---|
| Claude が通常の形で push / tag / merge / freeze / copier を実行すること | `sh -c "git push"`、スクリプトや Makefile のターゲット経由、エイリアス、`.git/` を直接触る操作（テキスト照合の限界。Claude Code の公式ドキュメントも Bash ルールを「security boundary ではない」としている） |
| Claude が `labkit approve` を実行すること、承認ファイルを Write/Edit/リダイレクトで作ること | 書き込み可能な場所（scratch/）に置いたスクリプトが承認ファイルを書くこと（承認記録に秘密は無い）。サンドボックスの `denyWrite` だけが止める（Windows ネイティブでは止まらない） |
| 承認の使い回し（別コマンド、別 HEAD、期限切れ、2 回目） | 承認済みコマンドの中身そのものの危険性（人間が内容を読んで承認する前提） |
| 承認待ちで Claude が止まること（Stop hook が承認待ちを理由に止め直さない） | — |

**最後の砦は GitHub 側の main ブランチ保護**（直接 push の禁止、PR 必須、タグ保護）。これは本リポジトリでは
設定できないので、人間が設定する（AGENT_QUEUE.md の approval 項目）。

## 2. 手順の状態機械（labkit flow）

定義は `labkit/python/src/labkit/flows/<name>.toml`（宣言的）。段階ごとに名前・説明・完了条件（機械的に検査）・
承認の要否・禁止する操作カテゴリを持つ。`labkit flow start` で定義を `.lab/flows/<name>.json`（git 管理）に写すので、
hooks は状態ファイルだけを読む。

- `labkit flow advance` は完了条件を検査し、満たしていなければ不足を列挙して失敗する。承認が要る段階では、承認ゲートと
  同じ仕組みで `labkit flow advance <name>` というコマンドを承認待ちに積む（人間が `labkit approve`）。
- `guard_bash` / `guard_write` は、現在の段階で禁止されたカテゴリ（code, experiments, raw, template, link, release）を
  拒否し、「今は <段階>。先に <条件> が必要」と返す。禁止されていない作業（準備・ドキュメント・テスト・scratch）は続けられる。
  これは**うっかりの防止**であり、敵対的な回避（`labkit flow abort` → 作業 → `flow start`、`cd scripts && python x.py`）は止めない。
  取り返しのつかない操作だけは承認ゲート（別層）が守る。
- SessionStart（compact 含む）が現在の段階・残り条件・承認待ち・質問を文脈に入れる。UserPromptSubmit は人間の操作による差分
  （承認済み・未実行、回答あり、却下）だけを添える。
- フロー: migrate（freeze → inventory【承認】→ apply-template → raw-data → code → reproduce【レビュー】→ strict → done）、
  improve-standards（triage【承認】→ branch → implement → test【レビュー】→ release【承認】→ adopt → done。本体の labkit/ を変えたら link 必須）。
  improve-standards の状態は**プロジェクト側**に置く。本体側の push/tag/merge は本体ディレクトリの承認ゲートが守る。

## 3. 独立レビュー

`lab-reviewer` agent（`claude-plugin/agents/lab-reviewer.md`）がレビューし、`docs/reviews/YYYY-MM-DD_<flow>_<段階>.md` に
frontmatter（reviewer, flow, stage, commit, verdict, findings）付きで保存する。`labkit check` L035 が書式を検査する。

- 自己採点の防止: `guard_write` は、hook 入力の `agent_type` が `lab-reviewer`（plugin では `lab-rules:lab-reviewer`）の
  ときだけ `docs/reviews/` への書き込みを許し、メインのエージェントには拒否する。lab-reviewer は `docs/reviews/` 以外に
  書けず、Bash は許可リストの読み取りコマンドだけ（`_labgate.reviewer_allowed`。載っていないものは拒否し、拒否メッセージに許可一覧を出す）。
- plugin の agent は frontmatter の `hooks` / `permissionMode` が無視される（公式ドキュメント）ため、agent 専用の hook ではなく
  plugin 共通の PreToolUse hook で `agent_type` を見て分岐している。
- 完了条件 `review`: 現在の HEAD に対する verdict=pass の記録。HEAD が変わると無効になるので、指摘に対応して commit したら
  もう一度レビューを受ける（skill に手順）。

## 4. 報告と実データの照合（labkit check）

- **L032**: 開発ログ・ADR・サーベイ・レビュー記録に出てくる run ID（`YYYYMMDD-HHMMSS_<slug>_<commit7>_<hex4>`）が `runs/` に
  あり `meta.json` を持つこと。failed/interrupted/running の run や link 中の labkit で実行した run の引用は警告。
  HPC の run は `meta.json` と `metrics.json` だけ同期すれば足りる。
- **L033**: 数値の引用は `12.3 dB [run:<run_id>:snr_db]` 書式。表示桁で丸めて `metrics.json` と比較する。
  run ID と同じ行の書式なし数値は警告（`[check] cite_bare_numbers = "off"` で無効化）。
- `labkit cite <run_id> <key> [--digits N] [--unit dB]` が書式を出力する（Julia: `LabKit.cite`）。
- 警告（severity=warn）は strict でも終了コードを 1 にしない。`labkit check` の出力に `(warn)` と付く。

## 5. サンドボックス

雛形の `.claude/settings.json` に `sandbox` を設定した（キーは docs/notes/claude-code-spec.md で確認）:
`filesystem.denyWrite` = data/raw, lab.toml, .lab/approvals, .lab/queue。`allowWrite` に uv / Julia / pre-commit のキャッシュ。
`network.allowedDomains` に PyPI・GitHub・Julia パッケージサーバ・astral.sh。`autoAllowBashIfSandboxed: false`
（サンドボックス内でも hooks と確認画面を通す）。runs/・data/interim・data/processed はプロジェクト内なので既定で書ける。

**対応 OS**: macOS、Linux、WSL2（bubblewrap と socat が必要）。**Windows ネイティブでは sandbox は動作せず**、
Claude Code は「unsandboxed」で実行する（公式ドキュメント）。その場合は hooks（テキスト照合）と chmod（run と data/raw の
読み取り専用化）だけの保護に劣化する。本リポジトリの v0.3.0 の開発は Windows で行ったため、サンドボックス有効での
`make check && make example` は未確認（AGENT_QUEUE.md）。

## 6. 振る舞いの回帰テスト（plugin eval）

`claude-plugin/evals/` に 7 ケース（README 参照）。`make eval` で実行。費用はアカウントのモデル呼び出し（README に見積もり）。
CI では手動起動のみ。

## 後方互換と既定値

- v0.2.0 のプロジェクトはそのまま動く。`.lab/` は `labkit` が最初に必要になったときに作り、`.lab/.gitignore` も書く。
  古い `lab.toml` が `layout.allowed` を列挙していても `.lab` は許可される。`.lab/queue` と `approvals` は gitignore され、その PC だけの
  状態（承認は HEAD と 24 時間に結び付く）。質問の置き場は `.lab/queue` の 1 つだけで、終了時の報告は Claude の最後のメッセージ。
- 承認ゲートは既定で有効（presence=away）。無効にするには `lab.toml` の `[gate] enabled = false`（人間が編集）。
- `permissions.deny` の `Write(...)` ルールは公式ドキュメント上効かないので、雛形では `Edit(...)` に統一した
  （Edit の deny は Write にも効く）。
