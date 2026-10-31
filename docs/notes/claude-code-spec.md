# Claude Code 仕様の確認メモ（v0.3.0 ハーネス設計の根拠）

確認日: 2026-10-31。記憶ではなく公式ドキュメント（code.claude.com/docs）を取得して確認した。
引用は原文（英語）のまま。設計との食い違いは末尾「設計への反映」と AGENT_QUEUE.md に記録。

## hooks — https://code.claude.com/docs/en/hooks.md

- 共通入力（stdin JSON）: `session_id`, `prompt_id`, `transcript_path`, `cwd`, `scratchpad_dir`, `permission_mode`
  （`default | plan | acceptEdits | auto | dontAsk | bypassPermissions`）, `effort`, `hook_event_name`。
- サブエージェント識別: `agent_id` = "Unique identifier for the subagent or in-process teammate the hook fires in."
  `agent_type` = "Agent name (for example, "Explore" or "security-reviewer"). Present when the session uses `--agent`
  or the hook fires inside a subagent." → レビュー記録の書き込み制御（4 章）はこの `agent_type` で行える。
  plugin の agent 名は `<plugin>:<name>`（例 `lab-rules:lab-reviewer`）になるので、両方の表記を受け付ける。
- PreToolUse 入力: `tool_name`, `tool_input`, `tool_use_id`。出力:
  ```json
  {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow|deny|ask|defer",
    "permissionDecisionReason": "...", "updatedInput": {...}, "additionalContext": "..."}}
  ```
  - `permissionDecisionReason`: `ask` では人間に、`deny` では Claude に表示される。`allow` では debug ログのみ。
  - 複数 hook の優先順位: `deny` > `defer` > `ask` > `allow`。
  - 旧形式の top-level `decision`/`reason` は PreToolUse では非推奨（`approve`→`allow`, `block`→`deny`）。
- 終了コード: 0 = 出力 JSON を適用。2 = ブロック（"Exit 2 blocks even when your hook prints JSON"、理由は stderr、
  PreToolUse では `deny` と同じ扱い）。その他 = 非ブロックのエラー（処理は続行）。
- `ask` と permission mode: auto モードでは "a PreToolUse hook's "ask" normally sends the tool call to the permission
  prompt"。`dontAsk` は "anything that would prompt is denied"。`bypassPermissions` での hook `ask` の扱いは
  **ドキュメントに記述なし** → 設計では、`permission_mode` が `bypassPermissions | dontAsk | auto` のときは
  presence=here でも `ask` を返さず away と同じ扱い（拒否＋キュー）にする（安全側）。
- SessionStart: `source` は `startup | resume | clear | compact | fork`。**ブロック不可**（"Context only"）。
  stdout（exit 0）か `hookSpecificOutput.additionalContext` で文脈を追加。
- UserPromptSubmit: `hookSpecificOutput.additionalContext` で文脈追加。`decision: "block"` でプロンプト拒否。
  "Neither channel produces a visible transcript entry."
- Stop: 入力に `stop_hook_active`（"true when Claude Code is already continuing as a result of a stop hook"）、
  `last_assistant_message`。出力 `{"decision": "block", "reason": "..."}` で続行させる。
  無限ループ対策として "8-consecutive-continuation cap"（連続 8 回で強制終了。`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`）。
- plugin の hooks: `hooks/hooks.json` に `"hooks": {...}`。`${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}`（永続）,
  `${CLAUDE_PROJECT_DIR}`。matcher は `Edit|Write` 形式か正規表現。SessionStart の matcher は source 名。
  command hook の既定 timeout は 600 秒。hooks は **サンドボックスの外**で実行される。

## permissions — https://code.claude.com/docs/en/permissions.md

- 評価順: deny → ask → allow。Bash ルールは `Bash(git push *)` のような前方一致（`:*` も同義）。
- "A Bash rule matches the command text Claude writes... isn't a security boundary around the program."
  例: `Bash(git push *)` は `git -C . push origin main` を止めない。→ 正規表現の限界（2 章末尾）の根拠。
- パスルール: `//abs`, `~/home`, `/project-relative`, `relative`。`Write(path)` ルールは **効かない**
  ("`Write(path)` ... rules never match... Use `Edit(docs/**)`")。→ 雛形の settings.json から `Write(...)` を外し
  `Edit(...)` に統一（Edit の deny は Write にも効く）。`Read(path)` の deny は Edit/Write も止める。
- "For filesystem and network enforcement that doesn't depend on the command text, use sandboxing."

## sandboxing — https://code.claude.com/docs/en/sandboxing.md

- 対応: "The sandbox runs on macOS, Linux, and WSL2. On native Windows, Claude Code runs commands unsandboxed."
  Linux/WSL2 は `bubblewrap` と `socat` が必要。
- 設定キー（確認済み）: `sandbox.enabled`, `sandbox.failIfUnavailable`, `sandbox.allowUnsandboxedCommands`,
  `sandbox.autoAllowBashIfSandboxed`（既定 true）, `sandbox.excludedCommands`,
  `sandbox.filesystem.{allowWrite,denyWrite,allowRead,denyRead,disabled}`,
  `sandbox.network.{allowedDomains,deniedDomains,allowUnixSockets,allowAllUnixSockets,tlsTerminate}`,
  `sandbox.credentials.{files,envVars}`。
- パス: `/abs` は絶対、`~/` はホーム、接頭辞なし・`./` はプロジェクト設定ならプロジェクトルート基準
  ("the relative path `.` resolves to the project root when the configuration lives in project settings")。
- 書き込みは既定で作業ディレクトリ＋一時ディレクトリのみ許可。`.git`, `.claude` などは保護パス。
- ネットワークは allowlist（空から始まる）。プロキシ経由で TCP のみ。UDP/QUIC/ICMP は出ない。

## plugin eval — https://code.claude.com/docs/en/plugin-evals.md

- 必要: Claude Code v2.1.269 以上（手元は 2.1.316）。
- 配置: `<plugin>/evals/<case>/prompt.md`（frontmatter: `max_turns`, `allowed_tools`, `timeout_seconds`, `model`,
  `tags`, `runs`, `env`）+ `graders/<name>.md`（frontmatter `type: llm | regex | tool_used | tool_order |
  file_exists | baseline`, `weight`, `arm`）+ 任意の `case.yaml`（`schema_version: "1.1"`, `name`,
  `context.scaffold_script`, `context.add_dirs`, `context.history_file`）。`results/` は生成物（.gitignore）。
- `context.scaffold_script` は "A Bash script in the case directory"（ケースディレクトリ内）。`--scaffold` を付けたときだけ、
  空の作業ディレクトリで Claude の前に実行される（HOME は run 用の一時ディレクトリ）。120 秒超・非ゼロ終了で `scaffold failed`。
- `allowed_tools` で付与できるのは読み取り系（Read, Glob, Grep, NotebookRead, Skill, AskUserQuestion, Agent, TodoWrite, Task*）だけ。
  Bash / Write / Edit / WebFetch / WebSearch は `--allow-tools` で付与しないとセッションから外される。
- grader: `tool_used`（`tool`, `input_match`, `min`, `max`）、`file_exists`（`path` glob, `exists`。"Only files created during the run count"）、
  `regex`（`pattern`, `flags`, `match`, `target`）、`llm`（本文が基準）、`tool_order`、`baseline`。
- 実行: `claude plugin eval <plugin-dir> [--case <glob>] [--runs N] [--ablation none|with-without]
  [--allow-tools Bash Write Edit ...] [--threshold 0..1] [--max-cost-usd N] [--json path] [--trust-plugin]`。
  既定は各ケース 3 回 × with/without の 2 腕。Bash/Write/Edit は `--allow-tools` で明示しないと使えない。
- 費用: "Every eval run and judge grader is a real model call on your account."
- 終了コード: 0 合格、1 閾値未達/読込失敗、2 部分実行（費用上限など）。

## subagents — https://code.claude.com/docs/en/sub-agents.md

- frontmatter: `name`, `description`, `tools`, `disallowedTools`, `model`, `permissionMode`, `maxTurns`, `skills`,
  `hooks`, `memory`, `background`, `isolation`, ...。
- **plugin の agent では `hooks`, `mcpServers`, `permissionMode` は無視される**
  ("For security reasons, plugin subagents don't support the `hooks`, `mcpServers`, or `permissionMode`
  frontmatter fields")。→ lab-reviewer 専用の hook は書けない。plugin 全体の PreToolUse hook が
  `agent_type` を見て分岐する（4 章の実装方針）。
- plugin の agent 名は `<plugin>:<name>`。`SubagentStart/Stop` の matcher は agent type 名。

## plugin components — https://code.claude.com/docs/en/plugins/components.md

- 配置: `.claude-plugin/plugin.json`（`name` のみ必須）, `skills/<name>/SKILL.md`, `agents/<name>.md`,
  `hooks/hooks.json`, `bin/`, `settings.json`（効くのは `agent` と `subagentStatusLine` のみ）。
- plugin は permissions（allow/deny）を配布できない → 権限はプロジェクトの `.claude/settings.json`（雛形）で配る。

## 設計への反映（ドキュメントに合わせて調整した点）

| 当初の設計 | ドキュメント | 調整 |
|---|---|---|
| here モードでは常に `ask` | bypassPermissions/dontAsk での hook `ask` は未記述。dontAsk は「prompt するものは拒否」 | `permission_mode` が bypassPermissions / dontAsk / auto なら here でも拒否＋キュー（Q-001） |
| lab-reviewer に専用 hook を付けて書き込みを制限 | plugin agent の `hooks` は無視される | plugin 共通の PreToolUse hook が `agent_type` で分岐 |
| 雛形 settings.json の `Write(data/raw/**)` deny | `Write(path)` ルールは効かない | `Edit(...)` に統一（Edit の deny は Write も止める） |
| Stop hook のループ防止を独自カウンタのみで | `stop_hook_active` と 8 回上限がある | 独自カウンタは Claude Code の 8 回上限より小さい既定（3 回）にし、承認待ちが理由なら止め直さない |
| サンドボックスを全 OS で | Windows ネイティブは非対応 | Windows では hooks + chmod のみに劣化（docs/harness.md） |
