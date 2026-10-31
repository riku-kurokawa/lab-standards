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
| 生成プロジェクト直下に現れた `uv-<hash>.lock` を .gitignore / L001 で除外する | 原因は検証用シェルで `TMP=`（Windows の一時ディレクトリ変数）を上書きしたこと。uv はロックを `env::temp_dir()` に置く（uv ソースで確認、TMP 上書きで再現）。雛形の問題ではない | 2026-11-01 |
| run が多いプロジェクトで `labkit check`（Stop hook が毎回実行）を速くする | 実測: run 0 件 0.23 s、300 件 3.0 s（約 9 ms/run）。Stop hook の timeout 300 s に対して十分速く、最適化は複雑さの追加になる | 2026-11-01 |
| skills のうち他から参照されない data-pipeline / new-experiment / migrate-project を統合・削除 | skill は説明文で選ばれるので参照数は指標にならない。読むと手順が互いに重複せず、lab-conventions（参照表）とも役割が違う | 2026-11-01 |
| hooks の拒否を exit 2（stderr）と JSON の permissionDecision の 2 方式から 1 方式に統一 | ask / allow は JSON でしか表せず、Stop hook は exit 2 が必要。公式ドキュメント上 exit 2 は deny と同じ扱いで、統一しても挙動は変わらず、テスト 80 件以上の書き換えだけが残る | 2026-11-01 |
| 既存（v0.2.0）プロジェクトの .gitignore に .lab の除外を足す移行作業 | labkit が初回に書く `.lab/.gitignore` で、実リポジトリでも `presence` と `queue/` は ignored、`flows/` と `.gitignore` だけが追跡対象になることを確認。追加の移行作業は不要 | 2026-11-01 |
| labkit の実行時依存（numpy, scipy, pandas, h5py, pyarrow, matplotlib, jsonschema, pyyaml）を減らす | 全て実際に import されている（yaml は literature/reviews/standards、jsonschema は check のスキーマ検証）。削れるものは無い | 2026-11-01 |
| Julia の DEFAULT_LAB（readonly と hash_inputs_max_gb だけ）を Python の DEFAULTS と同じ内容に揃える | Julia が読むのはその 2 キーだけで、読まないキーの既定値を持つ方がずれの元。現状が最小で正しい | 2026-11-01 |
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
- 追記（サイクル 10 の後）: `tools/release.py --check` が config.py の standards_version を探して失敗していた。TARGETS を
  正本とコピーの両方に向けて修正。CI の最初のステップで落ちるところだった。サイクルの終わりに `release.py --check` も回す。

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

### 10. 2026-11-01 — migrate flow を雛形適用前に始められるようにする
- 観点: 状態機械を実際に最初から最後まで動かす（legacy プロジェクトで freeze → … → reproduce）。
- 発見: migrate の freeze / inventory は雛形適用前の段階なのに、`labkit flow start migrate` が lab.toml 無しで traceback。
  この flow は自分の対象プロジェクトで開始できなかった。
- 提案: `cmd_flow` だけ、lab.toml が無ければ git の最上位（なければ cwd）を root にする。
- 監査: 段階の並べ替え（apply-template を先に）は pre-migration タグの意味と承認ゲートの順序を壊すので却下。hooks に `.lab/flows` を
  スコープとして見せる案は、両コピーの load_lab が lab.toml を開いて落ちるため保留。skill の実行形は SETUP と同じ
  `uv run --project ~/dev/lab-standards/labkit/python labkit` に統一。
- 結論: 採用。他コマンドの find_root は厳格なまま。
- 規模: cli.py +7 行、テスト +13 行、skill に 3 行。

### 11. 2026-11-01 — 読まれない `lab.standards_version` を削除
- 観点: 書かれているが読まれない値。lab.toml の `standards_version` は Python・Julia・hooks のどこも読まず、release.py が 3 ファイルで
  同期していた（サイクル 5 の追従漏れの原因でもあった）。版は `.copier-answers.yml`（standards_ref, _commit）と pyproject/Project.toml にある。
- 提案: 既定値・雛形・release.py から削除。
- 監査: 読み手なし（`[lab]` を読むのは mlflow_sync の project だけ）。未知キーは deep_merge が素通しするので既存プロジェクトは無害。
  `labkit standards status` に standards_ref を表示して人間向けの情報を補う。
- 結論: 採用（accept-with-changes）。
- 規模: release.py の対象 10 → 7、_labstate.py −1 行、lab.toml.jinja −1 行、standards.py +2 行。

### 12. 2026-11-01 — lab-reviewer の Bash 制限を拒否リストから許可リストへ
- 観点: 機械的に間違えられないこと。レビュー agent の読み取り専用化は 4 行の正規表現の拒否リストで、
  `python - <<EOF`、`uv run python x.py`、`git worktree add`、`perl -i`、`curl -o` などが素通りしていた（fail-open）。
- 提案: 読み取りコマンドの許可リスト（単語の集合 3 つ + 関数）に置き換え、載っていないものは拒否（fail-closed）。
- 監査: agent の手順が使うのは git diff/status/rev-parse、labkit runs/check/review template のみで全て収まる。`cd`、`sed`（-i 以外）、
  pytest、`ruff check` を追加。agent は人間に尋ねられないので、拒否メッセージに許可一覧を（集合から生成して）載せる。
  `>` は引用符内でも拒否（レビューには不要）。
- 結論: 採用（accept-with-changes）。
- 規模: 正規表現 4 行（約 600 文字）→ 集合 3 つ + 関数 約 30 行。行数は増えるが「X は実行できるか」が集合の参照で答えられる。
  テストは拒否 14 件・許可 12 件に拡充。

### 13. 2026-11-01 — 雛形の pre-commit を uv.lock の ruff に一本化
- 観点: モダンさと同期。雛形は ruff-pre-commit v0.8.0（2024）を固定し、venv は ruff 0.17.3。同じツールの版が 2 か所にあり、
  `make lint` と commit 時の ruff が別物だった（今回のコードでは差は出なかったが、揃える仕組みが無い）。
- 提案: ruff / nbstripout を `repo: local` + `uv run` で動かし（labkit check と同じ方式）、pre-commit-hooks を v6.0.0 に上げる。
- 監査: 一次情報で確認（pre-commit-hooks v6 は Python 3.9 以上・未使用の hook の削除のみ、nbstripout 0.9 は 3.10 以上）。
  pre-commit 自体が dev 依存なので venv への依存は増えない。鏡写しの `--force-exclude`、`require_serial`、`types_or: jupyter` を踏襲。
- 結論: 採用。
- 規模: 版の固定 3 → 1（pre-commit-hooks のみ）。YAML は +9 行だが同期すべき場所が減った。
- 追記（サイクル 22 の後）: 本体 labkit の dev 依存も `ruff>=0.5` のままだったので `>=0.17` に揃えた（uv.lock は 1 行の変更）。

### 14. 2026-11-01 — 本体に雛形と同じ lint 基準（ruff check + format）を課す
- 観点: 統一。雛形は各プロジェクトに `ruff check` と `ruff format --check` を要求するが、本体の CI と Makefile は ruff を一切回しておらず、
  31 ファイル・1667 行が format 違反。claude-plugin/ と tools/ には ruff 設定が無く、既定（88 桁・E4/E7/E9/F）で解釈されていた
  （同じリポジトリで「format」の意味が場所により違う、が具体的な失敗）。
- 提案: ルートに ruff.toml（labkit と同じ値。ruff は最も近い設定を使うので labkit/python の pyproject と干渉しない）、
  一度だけ機械的に `ruff format`、Makefile に `lint` を足して `make test` と CI で回す。
- 監査: 採用。git blame のコスト（2 週間・1 人の履歴）は無視できる。`.git-blame-ignore-revs` は追加の仕組みなので入れない。
  uvx ではなく labkit の venv の ruff を使う（サイクル 13 と同じ「1 つの ruff」）。
- 結論: 採用。機械的な整形は別 commit にして差分を読めるようにした（1 サイクル 2 commit）。
- 規模: ruff.toml +6 行、Makefile +6 行、CI +2 行。コード自体は整形のみ（意味の変更なし）。

### 15. 2026-11-01 — venv のツール探索を 1 関数に（post_edit が Windows で無動作だった）
- 観点: 機械的に間違えられないこと / Windows 対称性。`post_edit.py` の ruff 探索は `.venv/bin/ruff` だけを見て、Windows の
  `.venv/Scripts/ruff.exe` を見ないため、生成プロジェクトでは編集後の整形が黙って動いていなかった。同じ探索は `labkit_cmd` に
  正しく実装済み（2 つの実装 → 片方がずれる、の再発）。
- 提案: `_labcommon.tool_cmd(root, name)` に統一し、`labkit_cmd` と post_edit の両方がそれを使う。
- 監査: 1 行修正より統一の方が小さい（正味 −7 行）。雛形の dev は dependency-group なので `uv sync` で ruff が venv に入り、
  `uv run ruff` の経路はまれ。ruff が無い場合も hook は従来どおり黙って何もしない。
- 結論: 採用。
- 規模: −7 行、テスト +18 行。「venv のツールを探す」実装 2 → 1。

### 16. 2026-11-01 — 生成直後のプロジェクトが自分の `make lint` に落ちていた
- 観点: 雛形から生成して実際に `make check` 相当を全部回す（サイクル 8・13 の後の回帰確認）。
- 発見: `scripts/run_example.py.jinja` の `save(...)` 1 か所が ruff format 違反で、新規プロジェクトは生成直後から `make lint` が赤。
  同時に見えた `uv-<hash>.lock` は検証シェルの `TMP=` 上書きが原因で雛形の問題ではなかった（棄却表に記録）。
- 提案: 雛形を整形（ruff の出力どおり 1 ハンク）。再発防止は CI の既存の copier レンダリング工程に
  `ruff format --check --config <生成 pyproject>` を 1 行足す（生成された設定を使い、第 2 の設定源を作らない）。
- 監査: 採用。pytest で jinja を自前展開する案は第 2 のレンダラになるので却下。`ruff check` は first-party 判定で誤検出するため format のみ。
- 結論: 採用。
- 規模: 雛形 ±0（整形のみ）、CI +2 行。

### 17. 2026-11-01 — UserPromptSubmit の注入を「人間の操作による差分」だけに
- 観点: 認知負荷と毎プロンプトのコスト。flow 1 つ + キュー 2 件の状態で、毎回の入力に 425 文字・6 行（承認待ち・未回答の質問・
  flow の段階と条件）が繰り返し添えられていた。いずれもセッションが既に知っている情報。
- 提案: UserPromptSubmit は承認済み・未実行 / 回答あり だけ（人間が `labkit approve` / `answer` したことで生じた差分）。
  承認待ち・未回答・flow は SessionStart（compact 含む）と拒否時の hook が伝える。
- 監査: 採用。加えて「却下」がどこにも表示されない穴を発見（人間が `labkit reject` しても Claude は待ち続ける）。
  却下も差分に含め、`labkit queue done` で確認済みにする。外部からの flow advance は hooks の forbid が守るので省いてよい。
- 結論: 採用（accept-with-changes）。
- 規模: 通常のプロンプトの注入は 0 行に。_labcommon +12 行（却下の表示）、prompt_context −3 行、テスト +18 行。

### 18. 2026-11-01 — `labkit queue list` を「戻った人間」の視点で直す
- 観点: 人間が戻って最初に見る画面。却下した要求が既定の一覧から消え（Claude が確認したか分からない）、承認の判断材料になる
  差分の要約（記録はしていた）が表示されていなかった。
- 提案: rejected は Claude が `queue done` するまで表示。承認要求に `記録時点: <差分要約>` を 1 行出す。
- 監査: 採用。要約は記録時の HEAD に結び付いた証拠なので再計算せず「記録時点」と明示する（再計算は別マシンや変化した作業ツリーで誤る）。
- 結論: 採用。
- 規模: cli.py +3 行、テスト +14 行。

### 19. 2026-11-01 — git リポジトリ外でのメッセージを正直にする
- 観点: 生成直後（`git init` 前）の lab プロジェクトで hooks と flow を動かす。
- 発見: flow の `clean_tree` が git 失敗を「未コミットの変更あり」と報告、ゲートの拒否文が `HEAD（）` と空で出る。
  承認が HEAD=None に結び付く点は、リポジトリ外には結び付ける状態が無いので穴ではない（コマンド全文・cwd・期限・1 回限りで照合）。
- 提案: 2 つのメッセージを直し、harness.md に 1 文。ゲートにリポジトリ判定を足す案は、copier / raw freeze をまさに使う場面を塞ぐので却下。
- 監査: 採用。`c_standards_*` の `or ""` は本体チェックアウト相手なので触らない。
- 結論: 採用。
- 規模: flow.py +2 行、guard_bash.py ±0、docs +1 行、テスト +5 行。

### 20. 2026-11-01 — 雛形 README の、検査の無い規約を削る・明示する
- 観点: 本体 CLAUDE.md 規約 5「文章だけの規約を増やさない」を、既存の文章規約に当てはめる。
- 発見: prompts/README の frontmatter 項目（purpose, inputs, output_format, created, changelog）と `{{変数名}}` は何も読まない死んだ仕様。
  notebooks の「必ず scripts 化」は L032/L033 が下流で実質的に強制している。data/external の来歴記録は検査が無い。
- 提案: prompts は「1 ファイル 1 プロンプト」「版を上げて上書きしない（検査なし）」だけに。notebooks は検査への参照に言い換え。
  data/external は「検査なし」と明示。新しい check は足さない。
- 監査: 採用（規約 5 は「増やさない」であり既存の削除は「減らす」価値で判断、各規約ごとに失敗の有無で判断）。
- 結論: 採用。
- 規模: prompts/README 8 → 6 行、他 2 行の言い換え。概念 −1（プロンプトの frontmatter 仕様）。

### 21. 2026-11-01 — どこにも書かれていない labkit サブコマンドを棚卸し
- 観点: 無くせないか。skills・docs・雛形のどこからも参照されないサブコマンドを列挙（raw verify, lit key, lit check, runs show, paths,
  queue show, flow list）。
- 提案: 未リリースの v0.3.0 で足した `queue show`（`cat .lab/queue/<ID>.json` と同じ）と `flow list`（`flow start` の名前無しが同じ一覧を出す）を削除。
  人間に有用な `runs show` と `paths` は README の表に載せる。`raw verify --full` は `labkit check --full` が同じ検査なので README はそちらに統一。
  v0.1 からの `lit key` / `lit check` は互換のため残し、削除可否を質問（Q-019）。
- 監査: 採用（上記のとおり）。
- 結論: 採用。
- 規模: cli.py −9 行、CLI の動作 2 つ削除、README +2 行。

### 22. 2026-11-01 — Python と Julia の対称性を実ファイルで検査する
- 観点: 規約 2「Python と Julia を揃える」は文章だけで、両実装を同じファイルで突き合わせるテストが無かった（Julia は Julia で読み戻すだけ）。
- 提案: pytest を 1 つ追加（julia が無ければ skip）。Julia が run・HDF5・Parquet を書き、Python が shape (2,3)・値・サイドカー検証・
  `labkit check`（L020/L022）・language=julia を確かめる。CI の julia ジョブで実行、Makefile に test-cross。
- 監査: 採用。既存の工程に同等物なし。`cite`/`list_runs` の追加検証は冗長なので削る。slow マーカーは新しい規約になるので付けない。
  手で往復させた結果は一致（row0 = [1,3,5]、check 違反なし）。
- 結論: 採用。
- 規模: テスト +35 行、CI +4 行、Makefile +3 行。文章だけだった規約 1 つが機械的検証に。

### 23. 2026-11-01 — 編集ごとの ruff hook を廃止し、終了時に 1 回
- 観点: 同じ lint が 3 層（編集ごとの PostToolUse hook、pre-commit、make lint）で走っていた。
- 発見: 編集ごとの自動整形は、Claude が直後に行う Edit の old_string を外す原因になる（整形後の本文と食い違う）。
  一方、自動修正できない違反（F821 未定義名、禁止 API）を Stop 前に捕まえる価値は残る。
- 提案: post_edit.py と PostToolUse を削除し、Stop hook（既に labkit check を回す）で `ruff check` を 1 回。整形は pre-commit / make fmt。
- 監査: 採用（move-to-Stop）。`make lint` を hook から呼ぶと make と Makefile に依存するので ruff を直接呼ぶ。
- 結論: 採用。
- 規模: −42 行 + 8 行。hook の数 5 → 4。ruff の実行回数は編集ごと → ターンごと。

### 24. 2026-11-01 — v0.2.0 プロジェクトの更新経路を実際に通す（変更なし）
- 観点: CHANGELOG が約束する移行（`labkit standards template --ref v0.3.0` = copier update）を一度も動かしていなかった。
- 観察: v0.2.0 タグから生成 → commit → `copier update --vcs-ref HEAD --data standards_ref=v0.3.0`。衝突（.rej）なし、15 ファイル変更、
  差分は意図した v0.3.0 の内容だけ（lab.toml の [gate] と .lab、standards_version 削除、pyproject のタグと dev 下限、settings の Edit ルール、
  Makefile、pre-commit、README 群）。プロジェクト固有値（project 名）は保持。`.lab/` は labkit が初回に作る。
  注意: copier の `_src_path` が相対（`.` から生成）だと update が失敗する。実運用の `gh:` URL / 絶対パスでは問題ない。
- 結論: 変更なし。移行手順は CHANGELOG の記述どおりに動く。

### 25. 2026-11-01 — writer / add_input / log_message を両言語でテストする
- 観点: 安定性。Julia 側の `writer`、`add_input`、`log_message` はテストが無く、サイクル 1 の `fmt` スコープのような
  実行時にしか出ないバグが潜みうる。手で動かした結果は正常。
- 提案: runtests.jl に 3 呼び出しと 4 つの assert を追加。
- 監査: 採用。ただし Python 側も `add_input` / `log` は未テストだったので、規約 2（対称性）に従い同じ assert を test_core.py に足す。
  `cite` は Python CLI 依存なので Julia テストからは除外（往復テストが代替）。
- 結論: 採用。
- 規模: Julia テスト +7 行、Python テスト +5 行。

### 26. 2026-11-01 — SETUP.md を「初回公開の台本」から「別の PC / 新規プロジェクトの手順」に
- 観点: 新しい PC でこの文書を読む人。SETUP.md の 1〜4 節と末尾のエージェント用プロンプトは v0.2.0 の初回公開（zip 展開、
  YOUR_GITHUB 置換、git init、tag v0.2.0、gh repo create）で、既に実行済み。再実行すると害がある（copier.yml の既定値は設定済み）。
- 提案: 0 前提ツール / 1 clone / 2 plugin 登録 / 3 承認ゲート / 4 動作確認（README へのポインタ + standards status）に絞る。
  README の初期設定も 3 行にして SETUP へ誘導。リリース手順は CLAUDE.md のみ。
- 監査: 採用。残すべきは `~/dev/lab-standards` の正規位置と `LAB_STANDARDS_DEV`、`gh auth setup-git`。エージェント用プロンプトは
  git 履歴で再現でき、フォークには別の文言が必要なので削除。Julia UUID 等の v0.2.0 事前注意はテストが通った今は不要。
- 結論: 採用。
- 規模: SETUP.md 164 → 72 行、README −8 行。版固有のコマンドが文書から消えた。

### 27. 2026-11-01 — 生成プロジェクトの README と docs/README に v0.3.0 の置き場所を載せる（文書同期）
- 観点: 新規プロジェクトの README を最初に読む人。`docs/reviews/` と `.lab/` が表に無かった。本体 CLAUDE.md 規約 7 も
  「lab.toml が無ければ何もしない」のままで、本体でのゲート動作と矛盾していた。
- 結論: 表に 2 行、docs/README に 1 行、規約 7 を実態に合わせる。設計変更なし（監査省略）。
