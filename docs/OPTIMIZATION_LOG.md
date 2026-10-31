# OPTIMIZATION_LOG — lab-standards を磨くサイクルの記録

1 サイクル = 1 commit。観点、提案、監査の要点、結論、規模の増減を数行で。棄却した案も残し、同じ案を繰り返さない。
ブランチ feat/optimize（起点: feat/harness-v0.3.0 の 91f2559）。push / tag / main へのマージはしない。

## 棄却・保留した案（繰り返さない）

| 案 | 理由 | 日付 |
|---|---|---|
| presence（here/away）を廃止して permission_mode だけで判定 | 指示 2 章の要件。AGENT_QUEUE Q-014 で人間の判断待ち | 2026-11-01 |
| 承認の消費を PostToolUse へ移す | hook が 1 つ増える。失敗時は再キューで足りる（Q-015） | 2026-11-01 |
| README の「人間が不在のときの動き」節を harness.md へのポインタに縮める | README（物語）・SETUP（操作）・harness.md（設計）で読者が違う。重複ではなく役割分担 | 2026-11-01 |
| 雛形の各ディレクトリ README（docs/data/literature/notebooks/prompts、8〜24 行）を統合・削除 | 各々が配置だけでは分からない規則（不変性、citekey、nbstripout）を 1 画面で述べていて重複が無い。読む場所が増える害の方が大きい | 2026-11-01 |
| guard_bash が毎回呼ぶ `git rev-parse`（ブランチ取得）を merge のときだけに遅延 | 実測: hook 全体 83 ms のうち git は 14 ms。効果が小さく分岐が増える | 2026-11-01 |

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

### 5. 2026-11-01 — lab.toml の既定値を 1 か所に
- 観点: データの二重定義。hooks の FALLBACK と labkit の DEFAULTS がずれていた（禁止 plot ライブラリの一覧に UnicodePlots/PlotlyJS が無い等）。
  さらに `_labstate.load_gate_conf` にも gate の既定値が 3 つ目として直書きされていた。
- 提案: DEFAULTS と deep_merge を正本 `_labstate.py` に置き、config.py / _labcommon.py / load_gate_conf から重複を消す。
- 監査: 新しい第 3 のベンダーファイルは不要（既存の 1 ファイルに同居）。浅いマージと deep_merge は現在の lab.toml では同値。
  `tomllib` が無いときの `{}` 早期 return と `.lab/presence` の追加行は残す。
- 結論: 採用（accept-with-changes）。両者の load_lab が一致するテストを追加。
- 規模: 手書きの既定値 3 → 1。_labcommon.py −25 行、config.py −45 行、_labstate.py +70 行（正本）。

### 6. 2026-11-01 — 質問の置き場を .lab/queue の 1 つにする
- 観点: 概念の数。プロジェクトでは `labkit queue ask`（hooks が文脈に再注入、人間は `labkit answer`）と自由形式の AGENT_QUEUE.md の
  2 か所に質問を書く指示が残り、layout.allowed/writable など 6 か所に使われない許可があった。
- 提案: AGENT_QUEUE.md は本リポジトリ自身の開発ログに限り、プロジェクトからは全て除く。
- 監査: CLAUDE.md 雛形と skill は既に queue だけを指していて、hook の GATE_LINES と eval の採点だけが残っていた（指示源のずれ）。
  `.lab/queue` は gitignore されて PC を跨がないが、承認が HEAD・24 時間に結び付く設計と整合。終了時の報告は最後のメッセージで、ファイルは不要。
- 結論: 採用（accept-with-changes）。
- 規模: 7 か所から文字列を削除、追加なし。概念 −1。

### 7. 2026-11-01 — `labkit review` を雛形出力だけに
- 観点: 無くせないか。`review list` は `labkit check`（L035）と `ls docs/reviews` の重複、`review_path` の同日連番生成は読む側が無い。
- 提案: review サブコマンドを全廃。
- 監査: `template` だけは残す。理由は、レビュー agent が `commit:` に 7 桁の短い sha を写す失敗を防ぎ、既定 verdict を changes-requested に
  しておくことで書きかけの記録が flow を通さない（半端な記録は fail-closed）。`list` と `review_path` は削除、引数は位置引数に。
- 結論: 採用（accept-with-changes）。
- 規模: cli.py −22 行、reviews.py −14 行、テスト ±0。CLI のサブ動作 2 → 1。

### 8. 2026-11-01 — 雛形の Makefile から単発コマンドのラッパーを削除
- 観点: 同じ操作に 2 つの語彙。Makefile の 16 ターゲットのうち 9 つは `uv run labkit <同じ語>` の薄いラッパーで、README・skills は
  既に `uv run labkit ...` を使っていた（Makefile だけが矛盾）。ゲートはその語彙を不完全に鏡写しにしていた。
- 提案: 複数手順をまとめる check / test / lint / fmt / example / mlflow-* だけ残す。
- 監査: 全ターゲットが uv 経由なので HPC でも利点なし。ただし古いプロジェクトは古い Makefile を持ち続けるので、ゲートの
  `make raw-freeze` / `make std-*` 検出は互換のため残す（削ると生データ凍結がゲートを素通りする）。`make -C dir raw-freeze` のテストを追加。
- 結論: 採用（accept-with-changes）。
- 規模: Makefile.jinja 60 → 29 行。ゲート ±0（コメント +1）。概念 −1（Makefile は「まとめ」専用）。

### 9. 2026-11-01 — improve-standards の link 段階を削除し、必要なときだけ要求する条件に
- 観点: 段階の数。`link` 段階は hooks・skills・雛形だけの改良でも uv sync + Julia instantiate と L050 の commit 禁止を強いていた。
- 提案: 段階を削り、`implement` の説明に「labkit を変えるなら link」と書く。
- 監査: 文章だけにすると「本体の labkit を変えたのに、プロジェクトはリリース版のまま『確認』する」失敗を機械的に防げなくなる。
  → 本体の差分（main...HEAD）が labkit/ に触れているときだけ link を要求する条件 `linked_if_touched`（12 行）で置き換える。
  進行中の flow は開始時に段階を写しているので影響なし。実装中に pyproject.toml の無いプロジェクトで status() が例外になる抜けも直した。
- 結論: 採用（accept-with-changes）。
- 規模: 段階 8 → 7。TOML −7 行、flow.py +16 行（条件 1 つ）、テスト +22 行。文章の規約 1 つが機械的検証に変わった。
