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
| Stop hook（labkit check + ruff check）を軽くする | 実測: 生成プロジェクトで初回 0.9 s、以後 0.3 s。十分に軽い | 2026-11-01 |
| 雛形の Slurm ジョブ（jobs/slurm_example.sh）を skill hpc-job の要件に合わせて直す | 読み合わせた結果、`set -euo pipefail`・未コミット検査・`LAB_ENV=hpc`・配列ジョブの上書き引数が揃っていて差異なし | 2026-11-01 |
| Julia の `read_json`（JSON3.read）が Python 製 JSON の `100.0` を Int に読む非対称を直す | JSON3 は数値型を保持できず（`numbertype=Float64` は逆に整数を浮動小数にする）、Julia 側の利用は数値比較だけで実害なし。書き込み側はサイクル 32 で修正済み | 2026-11-01 |
| 図の figmeta.json と literature/INDEX.md のパス区切りも直す | figmeta は `rel_or_abs`（サイクル 34 で `/` 化済み）、INDEX はファイル名のみ。追加の修正箇所なし | 2026-11-01 |
| 日本語を含むパスのプロジェクト（`日本語 研究/`）への対応を足す | 実測: check・Python/Julia の run・hooks（拒否・キュー記録・文脈・書き込み保護）すべて正常。hooks の UTF-8 固定（v0.3.0）で足りている | 2026-11-01 |
| README と雛形 CLAUDE.md を通読して矛盾を直す | README に削除済み手順番号「⑥」と旧 link 条件が残っていたので修正（docs commit）。雛形 CLAUDE.md は現状と一致 | 2026-11-01 |
| 文献管理（lit add --pdf / survey / index / L04x）の Windows 対応を直す | 実測: 生成プロジェクトで一連の操作が正常（citekey 生成、PDF の移動、INDEX 生成、check 違反なし）| 2026-11-01 |
| 雛形コードが推移的依存（labkit 経由の numpy/scipy）に頼っていないか | pyproject.toml.jinja は numpy と scipy を明示。問題なし | 2026-11-01 |
| skills の説明文（Claude の選択基準）の重複・曖昧さを直す | 11 件を読み合わせ、対象と場面が互いに重ならない。変更なし | 2026-11-01 |
| CLI の help 文言をサブコマンド削除後に見直す | queue / flow / approve / review / cite / presence の help は現状と一致。変更なし | 2026-11-01 |
| 大配列（4×10^6 Float64）の save を Python と Julia で揃える | 実測: 両者 gzip レベル 4、サイズ 30.8 MB で同一、相互に読める。違うのはチャンク形状だけ（Python 自動 (1,7813)、Julia (4,4096)）で形式の差ではない。Julia の 3.0 s は JIT 込み | 2026-11-01 |
| 承認ゲートの `make raw-freeze` / `make std-*` 検出を削る（現行の雛形に無い target） | サイクル 10 で意図的に残した互換（v0.2.0 の Makefile を持つプロジェクトで生データ凍結がゲートを素通りしないため） | 2026-11-01 |
| HEAD から生成したプロジェクトの通し実行（link → Python/Julia の例 → 図 3 枚 → Pkg.test / pytest / ruff / check --strict）で直す点を探す | すべて正常（違反は link 中の L050 のみで、Stop hook は無視する）。初回に見えた `ruff format --check` の失敗は copier が既定で最新タグ v0.2.0 を使ったため。HEAD を試すには `--vcs-ref HEAD` で、CI と skill improve-standards に記載済み | 2026-11-01 |
| 参照されない labkit サブコマンドを削る（全 18 サブコマンド × 動作を skills/docs/雛形/hooks で照合） | 参照ゼロは `lit key` / `lit check` のみで Q-019 として人間に確認中（仮: 残す）。`paths` は README 1 か所で現役 | 2026-11-01 |
| skills/docs/雛形に書かれた `labkit <sub> <action> --opt` 46 形をパーサと機械照合し、存在しない形を直す | 不一致 3 件はすべて偽陽性（AGENT_QUEUE の過去報告・仮定の文、rawdata.py のヘッダ文字列）。ドリフトなし | 2026-11-01 |
| hooks が Claude に見せる文面（SessionStart / flow の拒否 / 承認待ち / Stop）を生成プロジェクトで実際に出して直す | 文面は明確で重複なし。flow の拒否が条件を内部名（`clean_tree; git_tag(name=...)`）で示すが `labkit flow status` を案内しており、hooks は標準ライブラリのみで評価器を持てない。表示パスの `\` は Windows の自然な表記 | 2026-11-01 |
| use_julia=false のプロジェクトで Julia 由来の設定（sandbox の ~/.julia と julialang ドメイン）を条件分岐で消す | Python のみの生成を実測: jl/ 無し、link・status・pytest・check・example すべて正常。残るのは settings.json の 2 エントリで無害。JSON 内の jinja 分岐はカンマの扱いが脆いので見送り | 2026-11-01 |
| 図テンプレート（8 種）の整理・統合 | `labkit fig list` の説明・必須 data・例が揃っていて重複なし。変更なし | 2026-11-01 |
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

### 28. 2026-11-01 — `labkit standards link` だけで開発ログを要求されていた
- 観点: Stop hook の所要時間を測る過程で発見。link が書き換える `jl/Project.toml` が「コード変更」に数えられ、コードを触っていなくても
  開発ログが無いと終了できなかった（Python 側の pyproject.toml / uv.lock はコードディレクトリ外なので数えられず、非対称だった）。
- 提案: `changed_code` で Julia の環境ファイル（Project.toml / Manifest.toml）を除外。
- 監査: 採用。拡張子の許可リストにする案は jobs/*.sh や configs/*.yaml 等を取りこぼすので却下。手で依存を足した場合も数えないが、
  それは Python 側と同じ扱い（環境の変更は研究の変更ではない）。
- 結論: 採用。
- 実装で判明: 未追跡のディレクトリを git は `jl/` とだけ報告するので、`--untracked-files=all` でファイル単位に見る必要があった。
- 規模: stop_check.py +8 行、テスト +12 行。

### 29. 2026-11-01 — 一連の作業後に git が見るもの（変更なし）
- 観点: 生成プロジェクトで run・図・開発ログ・質問・flow 開始を行った後の `git status -uall`。
- 観察: 見えるのは link による pyproject / jl/Project.toml の変更、開発ログ、`.lab/.gitignore` と `.lab/flows/`、uv.lock / Manifest.toml
  （再現性のため追跡対象）だけ。runs/・data/・.lab/queue・presence は出ない。
- 結論: 変更なし。

### 30. 2026-11-01 — 本体の判定を 1 つの規則に（マーカーファイルを削除）
- 観点: 同じ事実の 2 つの表現。「ここは lab-standards 本体」は、マーカー `.lab-standards-root`（find_scope だけが見る）と
  `copier.yml` + `labkit/python` の経験則（labkit_source の Python / Julia、flow が使う）の 2 通りで判定していた。
- 提案: マーカーを削除し、経験則に統一（Julia からも同じ規則が使える唯一の方法）。
- 監査: 採用。生成プロジェクトは copier.yml も labkit/ も持たないので誤判定しない。既存クローンは既に OR 側で動いていたため互換の問題なし。
- 結論: 採用。
- 規模: 追跡ファイル −1、_labstate.py −1 行、guard_write/state/test 各 −1 箇所、docs 4 か所の言い換え。

### 31. 2026-11-01 — 雛形の Julia 例を、雛形自身の規約に従わせる
- 観点: 雛形の例は規約の手本。Julia の例は窓幅 `[3, 9, 27, 81]` と `27` をスクリプトに直書きし、SNR を inline で計算していた
  （Python 例は configs の `cutoffs_hz` を読み、src の `snr_db` を呼ぶ）。CLAUDE.md 雛形の「パラメータは configs」「スクリプトは薄く」に反する。
- 提案: base.toml `[filter]` に `windows`、Julia モジュールに `snr_db`（Python と同じ定義）とテスト、スクリプトは設定を読んで src を呼ぶだけに。
- 監査: 採用。configs は言語中立なので `[filter]` に置く（`[filter.julia]` のような分割は設計に反する）。既存プロジェクトでは
  copier update が base.toml に 1 行足すだけ。
- 結論: 採用。
- 規模: base.toml +1 行、Julia モジュール +7 行、テスト +2 行、スクリプト ±0。直書きの数値 5 個が 0 に。

### 32. 2026-11-01 — Julia が書く JSON で 2.0 が 2 になっていた
- 観点: Julia の run から図を作る（初めて）。図は 3 枚とも出たが、サイドカーの `fs` が Julia では `1000`、Python では `1000.0`。
- 原因: `JSON3.pretty` は文字列を読み直して整数化できる浮動小数を Int にする（JSON3 1.14.4 の read.jl、`numbertype=nothing`）。
  オブジェクトを直接渡しても内部で同じ経路。`numbertype=Float64` は逆に整数を 5.0 にする。標準ライブラリ JSON は無い。
- 提案: `JSON3.write` の出力を再パースせずに字下げする 30 行の関数に置き換える（一行 JSON は人間と git diff の可読性を落とすので不採用）。
  meta.json / metrics.json / サイドカーすべてが `write_json_atomic` を通るので 1 か所の修正で済む。
- 監査: 採用（上記は監査がソースで確認）。Julia 側のテキスト検査と、往復テストに「2.0 が Python で float になる」assert を追加。
  既存の Julia 製 run のディスク上の `2` はそのまま（読む側は数値比較なので実害なし）。
- 結論: 採用。
- 規模: util.jl +30 行、テスト +9 行。対称性の実害 1 件を解消。

### 33. 2026-11-01 — `labkit check` の位置表示と除外ディレクトリを OS 非依存に
- 観点: 違反メッセージを読む研究者。典型的な違反 8 種を作って出力を読んだ。文言は行動につながるが、位置が Windows では `src\vi\bad.py:1`
  と OS 区切りで、文書や hooks の `/` と食い違い、file:line リンクにもならない。
- 発見（実測）: `figure_ok_dirs` の `docs/assets/` に置いた図が Windows では L014 になる（`startswith("docs/assets/")` を `\` 区切りと比較）。
  `format_allowed` の glob は fnmatch が区切りを正規化するので効いていた。
- 提案: 5 か所を `.as_posix()` に。POSIX では挙動不変。
- 監査: 採用。既存テストは位置の行番号しか見ていないので影響なし。
- 結論: 採用。
- 規模: 5 行の置換、テスト +10 行。Windows の誤検出 1 件を解消。

### 34. 2026-11-01 — 記録に書くパスとディレクトリのハッシュを OS 非依存に
- 観点: サイクル 33 の続きで、`relative_to` / `relpath` が永続する記録に入る場所を洗い出した。
- 発見（実測）: Windows で凍結した MANIFEST.sha256 は `sub\r.bin` となり、HPC（Linux）では別名のファイルを探す。ディレクトリ入力の
  sha256 は相対パス文字列を含むので OS で値が変わる（同一 OS では Python と Julia は一致）。Julia の `rel_or_abs` は Windows で常に絶対パスを返し、
  meta.json の inputs が Python と非対称だった。
- 提案: 永続パスはすべて `/` 区切り（Python `as_posix`、Julia `posixrel`）。ハッシュは `/` 区切りの相対パス文字列で並べて連結（並び順の罠も統一）。
  旧 `\` 区切りの MANIFEST 行は読む側で正規化。
- 監査: 採用。POSIX 製の記録はバイト単位で不変。Windows 製のディレクトリハッシュは変わるが元々移植不能。往復テストに
  「同じディレクトリの sha256 が Python と Julia で一致（a-b/ と a/、大文字の並び順を含む）」と MANIFEST に `\` が無いことを追加。
- 結論: 採用。
- 規模: Python 6 行の置換、Julia +6 行（posixrel）、テスト +33 行。

### 35. 2026-11-01 — `labkit cite` の既定表示を 1 規則に
- 観点: 研究者が引用する数値。大小さまざまな値で既定表示を見ると、12.345 は 4 桁（12.35）なのに 123456.789 は全桁、という不揃いがあった
  （`.4g` が指数になると全桁に戻す分岐のため）。
- 提案: 既定は `f"{v:.4g}"` の 1 行に（`--digits` は従来どおり）。
- 監査: 採用。全ての出力が L033 の照合を通ることを実測で確認。`repr` の最短表現は 0.30000000000000004 のような雑音を論文に持ち込むので不採用。
  1 万以上の整数が指数表示になる点は CHANGELOG に明記。
- 結論: 採用。
- 規模: check.py −7 行、テスト +12 行（9 値を固定）。

### 36. 2026-11-01 — 種ファイルを copier update の対象から外す
- 観点: 実プロジェクトが `labkit standards template --ref` で更新するとき。v0.2.0 から生成して README を研究者として書き換え、HEAD へ update すると
  README に `<<<<<<< before updating` の衝突マーカーが入った（この枝で README.md.jinja を変えたため）。copier の更新は git apply ベースで、
  種ファイルへの雛形側の変更は常に雑音になる。
- 提案: `_skip_if_exists` に README.md / data-dictionary.md / 初期 ADR / references.bib / tags.toml を列挙。例のコード・設定は管理対象のまま。
- 監査: 採用。copier ソースで「存在する skip ファイルは update でも patch から除外される」ことを確認。`data/raw/MANIFEST.sha256`（labkit が書く）も追加。
  新しい雛形の設定が使われるので、次の update から効く。
- 結論: 採用。
- 規模: copier.yml +8 行。概念の追加なし（copier の標準機能）。
- 確認: 同じ実験を再実行し、書き換えた README / data-dictionary にマーカーが入らず、lab.toml の [gate] と Makefile は更新された。

### 38. 2026-11-01 — CI の GitHub Actions を現行メジャーに
- 観点: モダンさ。ci.yml の 4 つの action が 2〜5 メジャー遅れ（checkout v4 → v7、setup-uv v5 → v10、setup-julia v2 → v3、upload-artifact v4 → v7）。
- 根拠（一次情報）: 固定していた版はすべて Node 20 前提。GitHub の changelog（2026-09-23）で Node 20 はランナーから撤去され、
  現状は暗黙の Node 24 強制で動いているだけ。各 action のリリースノートを監査が確認し、既定値だけ使う本リポジトリの用法に破壊的変更なし。
- 注意: setup-uv は v8 以降メジャーだけのタグを出さないので `@v10.3.3` と完全な版で固定。
- 結論: 採用。
- 規模: ci.yml 7 行の置換。

### 39. 2026-11-01 — python3 が古い環境で hooks が黙って無効になるのをやめる
- 観点: 別の PC（特に macOS 標準の python3 = 3.9）で hooks がどう振る舞うか。`tomllib` が無いと `load_lab` が `{}` を返し、
  パス保護・禁止 import・開発ログ・文脈注入がすべて静かに無効化されていた（承認ゲートだけ既定値で動く）。SETUP に python3 の要件も無かった。
- 提案: `_labcommon` の先頭で `sys.version_info < (3, 11)` なら説明を stderr に出して exit 1（公式: 非ブロックの通知として人間に見える）。
  黙って `{}` を返す分岐と `ImportError` の握りつぶしを削除。SETUP に 1 行。
- 監査: 採用（A）。uv 経由で python を保証する案（+9 ms）は uv を全 hook の必須依存にし、初回ダウンロードが hook の timeout に掛かり、
  uv 不在でもやはり静かに失敗するので不採用。通知は非準拠の機械でだけ出るので騒がしさは正当。
- 結論: 採用。
- 規模: _labcommon.py +6 行 −4 行、テスト +12 行、SETUP +1 行。

### 40. 2026-11-01 — hooks が頼る `python3` の正確な用意方法を書く（文書）
- 観点: サイクル 39 の続き。この PC の `python3` は uv が `~/.local/bin` に置いた実行ファイルで、python.org の Windows 版には `python3.exe` が無い。
  hooks.json は `python3` 固定なので、用意する正確なコマンドが要る。
- 提案: SETUP の 1 行を `uv python install 3.12 --default`（`--default` は uv 0.13 の help で確認。python/python3 の実行ファイルを置く）に。
- 結論: 文書の精密化のみ（監査省略）。

### 41. 2026-11-01 — `labkit approve` の確認の儀式（ID 再入力・--yes）を撤去
- 観点: 無くせないか。承認の「人間確認」は TTY なら ID 再入力、非 TTY なら `--yes` だったが、サイクル 20 の実測で Windows の
  Claude Code シェルでは再入力が EOF で動かず、`--yes` は Claude が付けられるフラグに過ぎない。実際の防壁は hooks が `labkit approve` を拒否すること。
- 提案: `_confirm_human` と `--yes` を削除。`human_check` は記録（by / tty / claude_shell）だけに。
- 監査: 採用。元の指示で TTY 再入力は「候補」であり、要件は「Claude が承認を作れない」と脅威モデルの文書化。
  人間が間違った ID を貼る失敗には、承認の中身（コマンド全文・HEAD・期限・1 回限り）が対処している。
- 結論: 採用。
- 規模: cli.py −20 行、state.py −3 行、フラグ 1 つ削除。docs 4 か所を簡潔に。

### 45. 2026-11-01 — heatmap テンプレートが文書どおりの向きの配列を描けなかった
- 観点: Julia が書いた 2 次元配列から図を作る（軸順の約束と描画コードが出会う場所）。
- 発見: `u[i, j] = f(x_i, y_j)`（shape (nx, ny)、Julia の size と同じ）を `labkit fig list` の例どおりに渡すと matplotlib の
  `pcolormesh` が (len(y), len(x)) を期待して TypeError。正方配列なら黙って転置が描かれる。Python で作った配列でも同じ。
  原因が残っていたのは、テストが 8 テンプレート中 4 つしか描いていなかったため（CLAUDE.md 規約 3 に反する状態）。
- 提案: 規約を「z[i, j] は (x[i], y[j]) の値」と明示し、形を検査して `z.T` を渡す（形からの推測はしない）。x, y 省略時も同じ規則。
  テストに heatmap（正方でない 4×6）・histogram・scatter・errorbar を追加し、転置した配列が拒否されることも固定。spectrogram は scipy の
  出力形 (len(f), len(t)) を消費するので変更なし（説明に形を明記）。
- 監査: 採用（上記のとおり）。利用者ゼロのテンプレートなので互換性の懸念なし。
- 結論: 採用。
- 規模: templates.py +8 行、テスト +14 行。8 テンプレートすべてがテストで描かれる。

### 46. 2026-11-01 — CLI の誤用を traceback ではなく 1 行で伝える
- 観点: 利用者が間違えたとき（無い run、無い figspec、template 名の誤り、[data] 不足、TOML 文法エラー、無い queue ID、プロジェクト外で check）。
  生成プロジェクトで 16 通りの誤用を実行し、11 通りが Python の traceback（メッセージ自体は良い日本語だが末尾に埋もれる）。
  `flow` だけは SystemExit で 1 行だった。`review template` は無い flow/段階を黙って受け付けていた。TOML 文法エラーにはファイル名が無い。
- 提案: `cli.main` で `(OSError, ValueError)` を捕まえ `labkit: <理由>` を stderr に出して 1 で終える（内部エラーの traceback は残る）。
  `config.read_toml` が文法エラーにファイル名を付け、lab.toml / paths / figspec / tags.toml / configs で使う。`review template` は flow・段階を検証。
- 監査: 採用（変更付き）。`cite` の無いキーだけ KeyError で traceback が残る → ValueError に。利用者が編集する TOML すべてに read_toml を。
  CHANGELOG に記載。hooks（stop_check）は終了コードと末尾の文字列しか見ないので挙動不変。Julia 側は Python CLI を呼ぶだけで対称性の問題なし。
  デバッグ用の環境変数は「必要が示されていない仕組み」として不採用。
- 結論: 採用。同じ 16 通りを再実行して traceback 0。
- 規模: cli.py +13 行、config.py +8 行、呼び出し側 3 か所で −6 行、テスト +20 行。labkit 59 passed。

### 47. 2026-11-01 — `load()` が無いファイルをサイドカーの不在と報告していた
- 観点: サイクル 46 と同じ「誤用」を Julia 側で。10 通り（raw への save、無いファイルの load、未対応拡張子、無い run、壊れた TOML、
  プロジェクト外）を実行。メッセージは日本語で明確、Stacktrace が付くのは Julia の慣習。公開名は Python の `__all__` と Julia の export が一致。
- 発見: 両言語とも `load(path, verify=true)` で path が無いと「サイドカー ... がありません（labkit の save 以外で作られたファイル？）」と
  サイドカーを疑わせる。verify なしでは h5py / HDF5.jl 内部の英語メッセージ。
- 提案: `load` の先頭で存在を確かめ `<path> がありません`（Python は FileNotFoundError、Julia は error）。ディレクトリ（Parquet 分割）も exists/ispath が真。
- 監査: 採用（Julia のテストに verify なしの場合を追加、CHANGELOG、正規表現の `.` をエスケープ）。
- 結論: 採用。
- 規模: 各言語 +3 行、テスト +8 行。labkit 60 passed、LabKit.jl 15/15。

### 48. 2026-11-01 — 前提ツールに GNU make が無かった（文書）
- 観点: 生成プロジェクトを雛形の Makefile で動かす。この PC（Windows ネイティブ、Git Bash）に `make` が無く、雛形の CLAUDE.md が
  「`make check` が通るまで完了ではない」と求めるのに、SETUP.md 0 節の前提ツールに make が無い（Git for Windows は make を含まない）。
- 提案: SETUP.md に make を追加（macOS: Xcode CLT、Debian/Ubuntu: build-essential、Windows: `winget install ezwinports.make` 4.4.1 を
  winget の索引で確認）。Makefile は sh 構文（`$$(...)`、for/do、単引用符）なので Git Bash から実行すると明記。
  Makefile 自体の廃止は、`example` の手順を labkit に移す必要と文書 10 か所の書き換えに対し、make 1 つの導入の方が軽いので見送り。
  Stop hook は make を使わず labkit check / ruff を直接呼ぶ（サイクル 26）ので、hooks は make 無しでも動く。
- 監査: 採用（版は 4.4.1 と書く、Git for Windows に make が無いことを一言）。
- 結論: 採用。文書のみ。
- ついで: ゲートの `make raw-freeze` 検出の削除を再検討したが、v0.2.0 互換のため残す（棄却表に追記）。

### 51. 2026-11-01 — `_labgate._git_subcommand` の冗長な分岐を削除
- 観点: 無くせないか。hooks で最大の `_labgate.py`（446 行）を、文脈を持たないサブエージェントに「テストで守られた挙動を変えずに削れる所」を探させた。
- 発見: git のグローバルオプションを飛ばすループで、`-c<KEY=VAL>` の分岐と `GIT_GLOBAL_FLAGS`（13 個の集合）の分岐は、
  直後の `t.startswith("-")` に完全に含まれる（`--git-dir=`/`--work-tree=` も `GIT_GLOBAL_WITH_ARG` の `=` 分岐で先に処理済み）。
  公開 API・FLOW_CATEGORY の各値・make 検出はすべて参照されており、それ以外に死んだ表面は無い。
- 提案: 2 分岐と集合を削除（−19 行）。uv run のオプション飛ばしの共通化（±5 行）は見送り。
- 監査: 提案自体が独立のエージェントによる読み合わせ。私が該当箇所を読んで包含関係を確認。hooks 91 passed、挙動の差なし。
- 結論: 採用。
- 規模: _labgate.py −19 行。

### 52. 2026-11-01 — check / literature / flow の重複と未使用を削除
- 観点: サイクル 51 と同じ読み合わせを、check.py + literature.py と flow.py + state.py + _labstate.py に対して 2 つの独立エージェントで並行。
- 発見: (1) `Checker.errors` プロパティは参照ゼロ（cli / flow は同じフィルタを行内で書く）。(2) `check_literature` は位置を OS 区切りの str で
  返していた（サイクル 33 の「位置は / 区切り」から漏れていた唯一の箇所。Windows で `literature\surveys\...` と出る）。
  (3) `flow.active_flows` は `_labstate.active_flows` の行単位の写し（_labstate 側は OSError も握る分だけ安全）。
  それ以外（CONDITIONS 16 種、EXPENSIVE、DEFAULTS["check"] の全キー、pending_summary の 5 キー、L032/L033 の関係）はすべて現役。
- 提案: (1) 削除、(2) 絶対 Path のまま返して `Checker.add` に正規化させる（lambda 削除）、(3) flow から `state.active_flows` を再公開。
  見送り: root 直下の L015（L001 と重複するが `layout.allowed` に図を加えた利用者への警告が消える＝弱化）、`flow._git` の統合（timeout が増える挙動変更）。
- 監査: 提案は独立エージェント 2 体。私が各箇所を読んで確認。テストに literature の位置に `\` が無いことを追加。labkit 60 / hooks 91 passed。
- 結論: 採用。
- 規模: −33 行 +15 行（check.py −4、literature.py −1 と型注釈、flow.py −13、テスト +1）。

### 53. 2026-11-01 — 残りのモジュール（cli/io/runs/viz、Julia、hooks）の未使用・冗長を削除
- 観点: サイクル 51–52 の読み合わせを残り全部に（独立エージェント 2 体、並行）。
- 発見と採用: `Context.used_files`（読み書きゼロ）、`io.describe`（呼び出しゼロ・Julia にも無い）、`_json_default` の Path 分岐（既定と同じ）、
  `io.__all__` の `rel_or_abs`（_util のもの）、hooks の `if not lab: return` 3 か所（load_lab は dict を返すか例外）、`decide(extra=)`（渡す側なし）、
  `harness_state_write` の if/return、関数内 import 2 つ。`.zarr` の「v0.2 予定」分岐は 0.3.0 で古い約束になっていたので Python/Julia とも削除
  （一般の「扱わない拡張子」に落ちる）。Julia の export に `current_run` を追加（Python の `__all__` にあり Julia にも定義済みだったが未 export）。
- 見送り: `labkit_cli` の un-export（Julia の fig/check の実装基盤）、cli.jl `cite` の 2 行、io の save 前段の重複（Python と同じ構造を保つ）、
  stop_check の CODE_DIRS との差（tests の編集では devlog を要求しない意図）、session_context の行順。
- 監査: 提案は独立エージェント。各箇所を読んで確認。labkit 60 / hooks 91 / LabKit.jl 15 passed。
- 結論: 採用。
- 規模: 10 ファイル、−34 行 +13 行。サイクル 51–53 の合計で約 −70 行、挙動の差なし。

### 54. 2026-11-01 — CHANGELOG v0.3.0 と docs/harness.md を現在のコードと突き合わせ
- 観点: リリース時に人間が読む 2 文書を、独立エージェント 2 体がコード（argparse、_labstate、hooks、雛形）と照合。約 50 項目中、食い違い 10。
- 発見（文書側を直した。コードはいずれも過去のサイクルの意図どおり）: 承認の照合に cwd は含まれない（コマンド全文・HEAD・期限・未使用の 4 点。
  `-C` のリポジトリの HEAD を使う）— harness.md・skill lab-conventions・SessionStart の文も「同じリポジトリ・同じ HEAD」に。
  `auto` は確認画面が出る（NO_PROMPT_MODES は bypassPermissions / dontAsk）。denyWrite に `.lab/flows` が抜けていた。`make std-link|unlink` は
  ゲートではなく flow の link カテゴリ。Stop hook が許すのは「このセッションが積んだ」承認待ちのみ。CHANGELOG: flow 定義のパス、`labkit.cite` が
  関数であること、`--digits` が小数点以下の桁数であること、skills は雛形でなく plugin。migrate.toml のコメントに実装の無い `commit` カテゴリ。
- 監査: 照合自体が独立エージェント。各箇所を私が確認。
- 結論: 採用（文書のみ）。
- 規模: 5 ファイル、±14 行。

### 55. 2026-11-01 — README / SETUP / 雛形 CLAUDE.md と 10 の skills をコードと照合。improve-standards の test 段階が advance できない欠陥を修正
- 観点: サイクル 54 の続き（独立エージェント 2 体）。
- 発見: (1) **機能の欠陥**: improve-standards の test 段階は完了条件 `review repo="standards"` で本体の HEAD に対する pass を要求するが、
  `labkit review template` はプロジェクトの HEAD を入れ、lab-reviewer も `git rev-parse HEAD` をプロジェクトで実行する指示だった。
  記録は常に不一致で、この段階は advance できなかった（evals・テストとも未検出）。(2) lab-reviewer の「単発は `adhoc review`」は
  `review template` が拒否する。(3) add-figure-template の取り込み手順が旧式（pyproject の tag を手で更新）。(4) 文書 3 件: 雛形 CLAUDE.md の
  「同じディレクトリ」、README/SETUP のゲート対象に gh pr merge / gh release が無い、presence=here は permission mode によってはキューのまま。
- 提案: `cmd_review` が段階の review 条件を見て、`repo="standards"` なら `_standards_dev` の HEAD を入れる（advance と同じ関数）。
  lab-reviewer の手順と skills の文を直す。テスト: improve-standards/test は本体 HEAD、migrate/reproduce はプロジェクト HEAD。
- 監査: 発見は独立エージェント。私が flow.py の c_review と cli.py を読んで確認。labkit 61 / hooks 91 passed。
- 結論: 採用。
- 規模: cli.py +10 行、テスト +18 行、文書 6 ファイル。

### 56. 2026-11-01 — improve-standards を最後まで進めるテスト（サイクル 55 の欠陥が見つかるはずだった経路）
- 観点: サイクル 55 の欠陥は「flow を実際に最後まで進めるテストが無い」ことが原因。migrate には途中までの遷移テストがあるが improve-standards には無かった。
- 提案: triage → done を実物の条件で進めるテストを追加。代替するのは高価・外部の 2 条件（本体のテスト実行、origin のタグ）だけ。
  承認の要る 2 段階（triage, release）、本体のブランチ・commit 数、link の要否、本体 HEAD に対するレビュー記録、adopt での「link が残っている」拒否と
  その解消、check を通る。
- 発見: adopt の条件 `linked` は `pyproject.toml` の無いプロジェクトで `standards.status` の FileNotFoundError をそのまま「評価に失敗」にしていた。
  `status()` が無い pyproject を unknown として扱うようにし、flow 側の 2 つの try/except を削除（`labkit standards link` は pyproject を先に書くので、
  pyproject 無しで link 状態になることは無い）。
- 監査: 採用（変更付き）: 例外を 2 か所で握るのではなく `status()` 側で扱う。adopt で link したままだと止まる否定の場合をテストに追加。
- 結論: 採用。
- 規模: テスト +60 行、standards.py +2 行、flow.py −6 行。labkit 62 passed。

### 57. 2026-11-01 — migrate も最後まで進めるテスト
- 観点: サイクル 56 と同じ。migrate の遷移テストは apply-template で abort していた。
- 提案: freeze → done を実物の条件で進める（.copier-answers.yml、lab.toml の warn→strict、`labkit raw freeze` による MANIFEST と L002/L003、
  check、finished な run、プロジェクト HEAD に対するレビュー記録）。done に達した flow は finished になり進行中でないことも固定。abort は冒頭で検査。
- 発見: 欠陥なし（migrate の配線は正しい）。テスト側では freeze() の進捗出力が capsys に残り、レビュー雛形の前に混ざる罠があった。
- 監査: 採用（変更付き）: レビュー記録の write_text に encoding="utf-8"（PYTHONUTF8 無しの Windows で cp932 になる）。code 段階の無視リストはこの最小
  プロジェクトでは効いていない旨をコメント。
- 結論: 採用。
- 規模: テスト +43 行。labkit 62 passed。

### 58. 2026-11-01 — cp932 既定の Windows でも壊れないように（encoding の明示と、それを守るテスト）
- 観点: サイクル 57 の監査の一言「この PC は PYTHONUTF8=1 だから通っている」。`PYTHONUTF8=0` で両スイートを実行すると 16 件失敗。
- 発見: 製品側は読み取りに utf-8 を明示していたが、6 か所の read_text()/write_text()（run のサイドカー、session_context の meta.json、stop_check の
  状態ファイル、mlflow_sync）と、子プロセス出力の復号（git / labkit check / ruff、計 11 か所、hooks と labkit の両方）が既定ロケール任せだった。
  hooks の UTF-8 固定は python 版の検査の後にあり、その日本語メッセージだけ cp932 で出ていた。テスト側は約 70 か所。
- 提案: すべてに `encoding="utf-8"`（子プロセスは `errors="replace"` も）。`_labstate.py` は両コピーを同時に。
  守る仕組み: ruff の PLW1514 は preview 専用で、しかも `(root / "x").write_text(...)` を見ない（実測 0 件）ので、AST を歩く小さなテスト
  `test_encoding_guard.py` を追加（open / read_text / write_text / subprocess の text=True で encoding 無しを検出。バイナリと os.open 等は除外）。
- 監査: 採用（変更付き）: 最初の正規表現版は複数行の呼び出しを見逃し、文字列中の open( を誤検出していた → AST 版に。製品側の subprocess も対象に。
- 結論: 採用。`PYTHONUTF8=0` で labkit 63 / hooks 91 passed（既定でも同じ）。CI に Windows ランナーは無いので、この再現はテストで担保する。
- 規模: 19 ファイル、+175 −97 行（うちテスト追加 55 行）。
