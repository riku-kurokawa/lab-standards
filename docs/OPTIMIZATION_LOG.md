# OPTIMIZATION_LOG — lab-standards を磨くサイクルの記録

1 サイクル = 1 commit。観点、提案、監査の要点、結論、規模の増減を数行で。棄却した案も残し、同じ案を繰り返さない。
ブランチ feat/optimize（起点: feat/harness-v0.3.0 の 91f2559）。push / tag / main へのマージはしない。

## 棄却・保留した案（繰り返さない）

| 案 | 理由 | 日付 |
|---|---|---|
| presence（here/away）を廃止して permission_mode だけで判定 | 指示 2 章の要件。AGENT_QUEUE Q-014 で人間の判断待ち | 2026-11-01 |
| 承認の消費を PostToolUse へ移す | hook が 1 つ増える。失敗時は再キューで足りる（Q-015） | 2026-11-01 |

## サイクル

### 1. 2026-11-01 — Windows で Julia の run が削除できない
- 観点: 生成プロジェクトを Windows で動かす（Python と Julia の run を作り、消す）。
- 提案: LabKit.jl `freeze_run` のディレクトリ chmod を Windows では省く（1 行）。Python 版 `os.chmod` はディレクトリに実質何もしないため、挙動が揃う。
- 監査: 診断を実機で確認（Julia の chmod は libuv fork で DACL を書き換え、`(OI)(CI)(RX,WA)` のみになる）。全 OS でディレクトリ chmod を外す案は
  POSIX の不変性を弱めるので却下。mktempdir のクリーンアップ失敗は再現が不安定なので根拠から外す。回帰テストは run.dir のコピーを削除する形に。
- 結論: 採用（accept-with-changes）。CHANGELOG に凍結済み run の復旧手順。
- 規模: +4 行（コメント 2 行含む）、テスト +3 行、概念の増減なし。

### 2. 2026-11-01 — .lab/ 状態アクセスの二重実装を解消
- 観点: 重複。hooks の `_labstate.py` と `labkit/state.py` が同じファイル形式を別々に実装し、既に 4 か所でずれていた（find_scope、list_queue、diff_summary、タイムアウト）。
- 提案: plugin 側を正本にして labkit にバイト同一コピーを置き、テストで一致を強制。`state.py` は人間側の操作だけ残す。
- 監査: 代替（hooks が labkit CLI を呼ぶ／symlink／ビルド時コピー／現状維持）はいずれも劣る。`find_valid_approval(now=)` をテストが使うので
  正本側に引数を足す。壊れた JSON の表示が消える点と差分要約が常に付く点を CHANGELOG に。
- 結論: 採用。
- 規模: state.py 281 → 155 行、_labstate.py のコピー +213 行（生成物、手書き 0）、テスト +8 行。手書きの実装は 1 つに。

### 3. 2026-11-01 — plugin eval が公式仕様どおり読み込まれる形にする
- 観点: 外部仕様の未確認箇所。eval の `scaffold_script: ../_shared/project.sh`、`allowed_tools` の Bash/Write/Edit、grader のフィールド名を
  記憶で書いていた。公式ドキュメントを取得して確認（docs/notes/claude-code-spec.md に追記）。
- 提案: scaffold はケース内の `fixture.sh`（正本 `_shared/project.sh` のバイト同一コピー、テストで一致）、`--scaffold` を付ける、
  `allowed_tools` は読み取り系のみ。
- 監査: scaffold は一時 HOME・環境変数なしで走るので `$HOME/dev/lab-standards` も `LAB_STANDARDS_DEV` も使えない → スクリプト自身の
  パスから本体を求める形に修正。Windows ネイティブでは eval を実行できない旨を README に。`file_exists` が hook の書いたファイルを数えるかは
  仕様が曖昧（初回実行で確認、代替は `{source: file}` + llm）。
- 結論: 採用（accept-with-changes）。未実行のままだが「読み込みすら失敗する」状態は解消。
- 規模: fixture.sh ×7（生成物、各 35 行）、テスト +12 行、Makefile/CI に `--scaffold`。概念の増減なし。

### 4. 2026-11-01 — SessionStart hook が規約を繰り返すのをやめる
- 観点: 認知負荷と重複。規約の文が CLAUDE.md・skill lab-conventions・SessionStart hook の 3 か所にあり、ずれの原因だった。
- 提案: hook は CLAUDE.md に書けない「状態」（今日の開発ログの有無、link、presence、flow、キュー、最近の run）だけを出す。
- 監査: 公式 memory.md「Project-root CLAUDE.md survives compaction: after /compact, Claude re-reads it」で、hook の存在理由だった
  「compact で規約が抜ける」は誤り。矛盾する 2 つの指示は Claude が任意に片方を選ぶ（公式）ので、重複はむしろ害。
  v0.2.0 判定で GATE_LINES を出し分ける案は却下（load_lab のマージ後は区別できず、本体 CLAUDE.md にも gate の記述が無い）。
- 結論: 採用（accept-with-changes）。GATE_LINES 2 行は常に出す。
- 規模: session_context.py −12 行、hook 出力 −10 行。概念 −1（「hook が規約を再注入する」をやめた）。
