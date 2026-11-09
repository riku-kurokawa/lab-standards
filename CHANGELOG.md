# Changelog

## v2.1.0 — 2026-11-10

accelerated-diff-pat で、腕のあいだで条件（駆動の自由度・与える入力・正規化など）がそろっていない比較が「同条件」と文章で書かれたまま
主張の根拠になり、ADR の監査で 10 件の主張を撤回した。比較の公平性を文章ではなく機械の関門にする（**ceteris paribus**: 比較が成り立つのは、
宣言した軸以外の条件がすべての腕で同一で、それを機械が確かめたときだけ）。条件のそろっていなかった run は、消さずに根拠から外す。

### 追加
- 比較は run の前に設定へ書く（凍結されて config.json に残る）:
  `[compare.<名>]` `vary = "<軸 1 つ>"`・`keys = [...]`・`objective`（任意）、`[compare.<名>.common]`、`[compare.<名>.arms.<腕>]`、
  `[compare.<名>.sweep]`（arm・param・values・metric（`{value}` を含む指標名）・direction。`[[...sweep]]` で複数）、`[compare.<名>.capability]`（腕 → 受け取れる目的）。
  1 run に名前つきの比較を複数置け、1 つの指標は 1 つの比較だけに属す。
- `labkit.compare`: `arm_conditions(cfg, name)`（腕の条件 = common ∪ 腕の表）、`chosen(run, name)`（掃引の最良を run の記録から）、`ConditionMismatch`。
  Run は開始前に `check_config` で検査し（vary が 1 軸でない・腕の表に軸と掃引の param 以外の鍵がある・`lab.toml` の `[compare] required` が common に
  無いか空・掃引の値の数が腕で違う・capability に objective が無い・対象外でない腕が 2 本未満・指標が 2 つの比較や noncomparative に重なる、のどれでも
  run を作らない）、終了時に 1 回だけ `comparisons.json` を書く（掃引のスコアは run の metrics から読み、腕の値が最良でなければ不一致）。
  不一致・2 回目の記録・running でない記録はすべて run を failed にする。
- 設定の `[report] noncomparative = ["<glob>"]`: 比較ではない指標の宣言。主張の根拠は既定で拒否し、matched な比較の keys か noncomparative だけを通す。
- check L027（error）: 凍結した config.json・metrics.json・comparisons.json（meta の outputs の hash を照合）から比較を計算し直す（記録の matched は信用しない）。
  台帳の open な主張の根拠の指標が宣言されていない、複数 run の根拠に axis が無い、軸以外の凍結した設定か commit が違う、も L027。
  他の文書の数値の引用は、そろわない比較の指標なら error、未宣言の指標は `check.undeclared_citation`（既定 warn）。
- `labkit claim add ... --axis <設定の鍵>`: 根拠が複数の run にまたがるときの比較の軸（根拠の欄の先頭に `axis=<鍵>;` が残る）。
- `labkit runs archive <run_id> [<run_id> ...] --reason "..."`: finished を含む run を名指しで複数退避する（削除はしない）。
  退避と取り消し（`--undo`）は理由が必須で、`meta.json` の `archive_log` に積む（取り消しても履歴は消えない）。
- 雛形 `lab.toml` の `[compare] required` に汎用の既定（degrees_of_freedom・inputs・objective・model・precision・scoring・eval_set・
  tuning_budget・compute_budget・normalisation）。分野の条件はプロジェクトがここに列挙する（人間が編集）。

### 変更
- L032: 退避済みの run の数値の引用 `値 [run:<id>:<key>]` は `check.archived_citation`（既定 error）。ID だけの言及は従来どおり警告。
  主張の台帳の撤回済みの行（状態の列で判定）は引用の照合から外した。
- 雛形 CLAUDE.md・`lab.toml`・example 設定（`[report] noncomparative`）、skill new-experiment・lab-conventions に「比較は 1 軸だけを変える（ceteris paribus）」。

### 2 回目のレビューで塞いだ抜け道（A–O。抜け道ごとに `tests/test_compare.py` の test_a〜test_o）
脅威モデル: 防ぐのは、善意だが雑な・近道をする著者やエージェントによる**偶然の・都合のよい不一致を引用できてしまうこと**。
完了した run の意図した偽造は手元の照合では防ぎきれない（安価な緩和だけを入れ、残る危険は docs/harness.md に明記）。
- A: `[report] noncomparative` のワイルドカードは前に 2 文字以上の固定の接頭辞が要る（`*`・`?*`・`*_db`・`[a-z]*` は拒否）。比べる語（vs・minus・over など）を含む指標は非比較にできない。
- B: 非比較の glob と、それに当たる指標は、腕の名前・比較の指標の語幹を含めない（`raw_ours_vs_flat` は引用できない。L027 の error）。
- C: `[compare]` の外（`[compare.<名>.common]` の中も）に腕の名前を含む鍵・表（`[solver.ours]`・`flat_steps`）があれば run を始めない。
- D: 軸の値は 1 語（`+ / , ; :` や空白で束ねない）で、腕の名前か `[compare.<名>] levels = [...]` の値。
- E: 調整の予算は腕ごとの**総試行数**で同じ。1 腕でも掃引するなら、対象外でない全腕を掃引する。
- F: `_git_commit` など `_` で始まる内部の鍵は実験間の軸にできない。
- G: 台帳の行の本文・備考の引用も根拠と同じ基準で照合する（`claim add` と L027）。
- H: 他の文書の未宣言の指標は error（開発ログだけ `check.undeclared_citation`、既定 warn）。run をまたぐ段落（空行・見出しで区切る）は、同じ段落の
  `axis=<鍵>` と軸以外の設定・commit の同一性を照合する（state・papers・reports は error、開発ログは警告）。
- I（緩和）: `labkit runs mark <id> finished` は、比較を宣言した run・comparisons.json のある run を拒否し（failed / interrupted で記録する）、
  開始時の config の hash と設定の検査をやり直す。
- J（緩和）: Run は開始時の config.json の hash を `meta.config_sha256` に残し、L027・`claim add` が照合する（outputs だけを直した改変を検出）。
  meta.json ごと書き換える偽造は検出できない（残る危険）。
- K: 対象外の独立した宣言は `lab.toml` の `[compare.capability]`（手法 = 受け取れる目的。人間が書く）。設定の capability は著者の宣言として
  comparisons.json（`not_applicable.<腕>.source`・`author_declared_not_applicable`）と L027 の警告に出る。`lab.toml` と食い違えば拒否。
- L: `[compare] required` の値に `n/a`・`none`・`null`・`-`・`tbd`・`unknown`・`?`・`未定` などのプレースホルダは空とみなす。
- M: entry が `run.config` や config.json を run の途中で書き換えると run は failed（メモリ上の設定と config.json の hash を終了時・記録時に照合）。
- N: 掃引があるなら比較に `better = "max" | "min"` が要り、掃引の direction は同じ。掃引の metric は比較の指標（keys の 1 つ）を含む名前。
- O: 実験間の照合は `[compare.<名>]` の common・arms・sweep なども比べる（除くのは keys とラベルだけ）。

### 移行
1. `labkit standards unlink --to v2.1.0`（Windows では続けて `uv sync --reinstall-package labkit`）、plugin は `/plugin marketplace update lab-standards`、
   雛形の差分は `labkit standards template --ref v2.1.0`。
2. **主張の根拠は既定で拒否になる**。v2.1.0 より前の run の設定には `[report] noncomparative` も `[compare.<名>]` も無いので、それを根拠にした
   open な主張はすべて L027 になる。比較でない指標は設定に `[report] noncomparative` を書いて clean に再実行し、根拠を差し替える。比較は
   `[compare.<名>]` を書いて再実行する。再実行しない主張は `labkit claim retract`。他の文書の未宣言の引用は警告（`check.undeclared_citation`）。
3. 条件のそろっていなかった run は `labkit runs archive <id> ... --reason "条件不一致: <何が違ったか>"` で退避する。
   退避済みの run の数値を引用している文書（開発ログを含む）は L032 の error になる。移行中に一時的に警告へ戻すなら `[check] archived_citation = "warn"`（人間が編集）。
4. `lab.toml` の `[compare] required` に分野の条件を列挙する（人間が編集）。既存の設定に無ければ既定は空で、required の照合は働かない。
   対象外を使うなら `[compare.capability]` に手法ごとの受け取れる目的を登録する（人間が編集。無ければ設定の capability は著者の宣言として警告）。
5. 掃引を使う比較は `better` を書き、掃引の metric に比較の指標を含め、全腕を同じ総試行数で掃引する。文書で別 run の数値を並べる段落には `axis=<鍵>` を書く。

## v2.0.0 — 2026-11-10

完全自律にし、**主線から絶対にずれず、しかし面白い芽を拾い続ける**ことと、**資源を必ずどれかの線に使う**ことを機械的な関門にした（ADR 0002）。
nla-solver の 2 週間の運用で、目標の版の乗り換え（20 版）、期限のある成果物の放置、壊れた計算の無監視の反復（18 本）、待つ拍が、与えられた資源を成果物に変えなかった。

### 削除（互換を壊す）
- 承認ゲート（`[gate]`）と `labkit approve / reject / answer / delegate`、委任（`.lab/delegations.json`）、UserPromptSubmit の差分注入。push・merge・tag・release・raw freeze も Claude が行う。
- migrate の flow から承認の段階を外した（inventory は CSV だけで進む）。

### 変更
- `labkit queue` は人間への一方通行の連絡（`ask` / `list` / `done`）。返事は待たない。v1.x の承認待ちは無視され、`queue done` で閉じられる。
- hooks: data/raw への新しいファイルの搬入（上書きしない cp / mv）を許す。既存ファイルの変更・削除・持ち出しは引き続き止める。
  lab.toml は migrate の apply-template・strict 段階のあいだだけ書ける。`docs/mainline.md`・`docs/seeds.md` の手書きを止める。
- SessionStart: 完全自律の 1 行、主線と芽・資源の使い道、人間への連絡を注入する。

### 追加（主線と芽・資源）
- `labkit main set / add / done / status`（`docs/mainline.md`）: 主線の 1 文と項目（成果物・完了条件・期限・状態・根拠）。完了は `--evidence` 必須。
- `labkit seed add / decide / list`（`docs/seeds.md`）: 芽（出どころ・最安の確かめ方・当たれば）。昇格は `--to promote --serves <主線の ID>` だけ。
- `labkit beat end --line main|seed:Sxxx|other`: 主線に open の項目があるあいだ必須。主線の割合（`autonomy.main_share` 0.7・`main_window` 10）、
  期限の守り（`main_guard_hours` 12）、芽の頻度（`seed_every` 8）を満たさない拍は記録しない。`beat start` が主線の残り時間・割合・芽・資源を出す。
- `labkit.Run`: 主線に open の項目があるあいだ設定の `serves`（Mxxx / Sxxx / `other:<理由>`）が必須。meta.json に `serves`。
  同じ名前の run が `fail_repeat`（既定 3）回続けて failed/interrupted で commit が進んでいなければ始まらない。
- digest に「主線と芽」の節（項目・芽・直近 24 時間の run 時間を線ごと・状態ごと）。
- check: L025（期限切れの open な主線の項目、警告）、L026（主線・芽の台帳の書式、error）。
- 雛形: `docs/mainline.md`・`docs/seeds.md`、lab.toml の `[autonomy]` の新しいキー、CLAUDE.md の「完全自律」「主線と芽」、beat_v1.md の手順（芽を残す・`--line`）、例の設定の `serves`。

### 移行
1. `labkit standards unlink --to v2.0.0`（Windows では続けて `uv sync --reinstall-package labkit`）、plugin は `/plugin marketplace update lab-standards`、
   雛形の差分は `labkit standards template --ref v2.0.0`。
2. `lab.toml` の `[gate]` は消してよい（無視される）。`[autonomy]` に新しいキーを足すかは任意（既定値で動く）。
3. 主線を置く: `labkit main set "<1 文>"`、`labkit main add "<成果物>" --done "<完了条件>" --due "YYYY-MM-DD HH:MM"`。置いた時点から関門が働く。
4. 以後の run の設定に `serves = "M001"`（または `S00N`・`other:<理由>`）を書く。拍は `labkit beat end --line ...`。
5. 開いている v1.x の承認待ちは `labkit queue list` で確かめ、`labkit queue done <ID>` で閉じる。

## v1.7.0 — 2026-11-09

accelerated-diff-pat で、メモリ不足で実行環境が計算を止めるたびに、エージェントが「人間の再開の指示まで起動しない」と同じ拍を
十数時間〜1 日以上くり返した（3 回、うち 1 回は自分の起動した重い計算が原因）。v1.5.0 のループ停止の拒否は、止まらずに何もしない拍をすり抜けさせていた。

### 変更
- `labkit beat end` は、判断と結果が（数字・空白・句読点を除いて）同じで run を伴わない拍が `[autonomy] stall_beats` 回（既定 3、0 で無効）続くと記録を拒む。
  メッセージは、資源の停止は人間の停止ではないこと、原因を外して自分で再開するか人間を要しない仕事を始めることを示す。待つしかないときは `--stall-reason` で記録でき、
  開発ログの拍の行に「停滞」として残る。`labkit beat start` は同じ拍が 2 回続いた時点で停滞を表示する。
- 雛形 CLAUDE.md・skill `beat`: 資源で止まった計算は自分で再開する、重い計算は上限を決めてから起動する。

### 移行
- `labkit standards unlink --to v1.7.0`（Windows では続けて `uv sync --reinstall-package labkit`）、plugin は `/plugin marketplace update lab-standards`。
- 既定で有効。無効にするなら `lab.toml` の `[autonomy]` に `stall_beats = 0`（人間が編集）。

## v1.6.0 — 2026-11-05

ボトルネックは人間のレビュー時間である。nla-solver・accelerated-diff-pat の 5 日間の自律運用で、人間が読まされていたもの
（1 日 300〜600 行の開発ログ、積み上がる state.md、100 行のレビュー記録、1000 行超のスクリプト、failed 66 本が混じる run 一覧、
見出しだけの文献ノート）を、機械が同じコードで作る短い生成物と台帳に置き換える。新しい規則は既定で警告か opt-in。

### 追加（人間の入口と台帳）
- `labkit digest [--since]`: 人間が 15 分で読む 1 枚 `docs/DIGEST.md`（主張の変化、予想と結果、run の収支、新しい図を `docs/assets/digest/` に写してリンク、
  未解消のレビュー、承認待ち・質問、check の集計、文献の追加と読書キュー、変更された文書とコード量）。SessionStart が古さを知らせる。DIGEST は引用照合の対象外。
- 主張の台帳 `docs/claims.md`: `labkit claim add "<1 文>" --evidence <run>:<key>[:<unit>][:<digits>]` / `claim retract <ID> --reason` / `claim list`。
  状態は open / retracted の 2 値。L036 が書式・撤回の理由・open な主張の根拠（run が無い・failed・dirty・退避済み）を error で知らせる。
- レビュー記録に `summary`（人間向け 1 行、120 字以内。2026-11-05 以降の記録で無いと L035 の警告）と `resolves`（前回の記録）、findings の接頭辞 `must:` / `should:`。
  `labkit review list [--open]`（未解消 = 後続に resolves も同じ flow/stage の pass も無い changes-requested）、`labkit review template ... --resolves <前回>` が前回の指摘の対応表を差し込む。
- 開発ログの自動ブロックに「コード量」の 1 行（src/scripts/tests の行数（空行を除く）、その日の増減、300 行超の本数）と「拍（自動）」。

### 追加（実験の共通の入口と予想の関門）
- `labkit run configs/experiments/<name>.toml [k=v]`: 設定の `entry = "pkg.module:func"`（`fn(cfg) -> dict`、2 引数なら `fn(cfg, run)`）を Run の中で呼び、
  戻り値を種類で保存する（数値 → metrics、DataFrame → Parquet、ndarray・配列の dict → HDF5、文字列 → ログ）。`inputs`、`[sweep]`（直積、`results.parquet` に 1 条件 1 行）。
  実験ごとの scripts/run_*.py を書かない。L017 は configs の entry を使用に数える。
- `[[pass]]`（key / min / max / table + where）: 事前に書いた合否を Run の終了時に判定し `pass_N` / `pass_all` を metrics に残す（事後に基準を動かさない）。
- 予想の表 `[prediction] basis confidence expert_predictable` + `[[prediction.claims]] key range|point+tol`: 終了時に自動判定し `prediction_result`（hit / miss / partial / undeterminable）。
  自由記述の予想は `labkit runs verdict <id> --say hit|miss|partial --note`（self_reported が残る）。L024（警告）: 予想のある finished run に判定が無い。
- `[runs] require_clean`（既定 false、雛形 true）: 未コミットの変更がある状態では run を始めない。`git.dirty` は計算に影響しない場所（docs/ literature/ prompts/ scratch/
  .lab/ README/CLAUDE.md）だけの変更を数えなくなり、何が dirty だったかは `git.dirty_paths` に残す（`git status -z` で読むので空白・非 ASCII のパスも正しく扱う）。
- `labkit runs table <name> [--file] [--all] [--md]`: 複数 run の同じ表を連結する（clean な finished だけ、除外を表示、実行中の run の入力に記録）。集計スクリプトを毎回書かない。

### 追加（視界から消す・読める大きさに保つ）
- `labkit runs archive <id> | --status failed,interrupted | --uncited [--older-than N（--uncited の既定 7）] [--dry-run] [--undo]`: 削除せず `meta.json` に `archived` を書く。
  `runs list` と DIGEST は既定で隠す（`--all`。開発ログの自動ブロックには archived の印つきで残る）。引用すると L032 の警告。Claude が実行してよい。
  `docs/claims.md`・`docs/DIGEST.md`・`.lab/beats/` は hooks が手書きを止める（labkit のコマンドだけが書く）。
- L018（警告）: src・scripts のファイルが `check.max_file_lines`（既定 300、空行を除く）を超える。`max_lines_allowed` で例外。雛形の ruff に C90 / PLR0915。
- L011 は scripts → scripts の import も警告。L037: `docs/state.md` は H1 1 つ・同じ H2 は 1 回（error）、`[state] max_lines`（150）超は警告（積み上げない）。
- L038（警告）: 結果・主張の節が `scratch/` のファイルを根拠にしている。L023（警告）: run を実行した labkit の版がプロジェクトの固定版と違う（環境の同期漏れ）。
- SessionStart が「無効のままの関門（require_prediction / require_clean）」を 1 行知らせる。

### 追加（長い自律運用の 1 拍）
- `prompts/current.toml`（goal / beat / interval）と `labkit beat start`（現行の目標と指示書の本文、終わった run・回答・主張の状態）、
  `labkit beat end --predicted --observed --decided [--runs]`（`.lab/beats/日付.jsonl`。時刻は機械）、`labkit beat log`。skill `beat`（`/loop 20m /lab-rules:beat`）。
- L005（警告）: current が指す版が無い、またはより新しい版がある。SessionStart が goal/beat の版と最後の拍の判断を出し、compact 後は目標の最初の節を原文で再注入する。
- 雛形: `prompts/goal_v1.md`（究極目標・前提・合格基準・メタ認知の問い）、`beat_v1.md` を `labkit beat` の流れに、`docs/state.md` を「今」だけの形に。

### 追加（文献: 何を読み、何を根拠にしたか）
- ノートの frontmatter に `read_by`（agent / human / both）、`read_scope`（none / abstract / sections / full）、`claims`（確立したこと 1〜3 行）。本文の見出しは 4 つ。
  L047（警告）: status が read/key なのに claims が空、または read_scope が abstract 以下。`labkit lit read <citekey> --by human [--scope full]`。
- `labkit lit add --doi 10.x | --arxiv 2606.09554`: 書誌を一次情報から取る（`source` フィールドが残る。記憶から書誌を作らない）。
- `labkit lit queue [--min-relevance N]`（人間の読書キュー）、`labkit lit surveys`、サーベイの frontmatter に `verdict`（novel / known / partly / inconclusive）と `n_opened`（L048、警告）。
  INDEX.md の先頭に要点（relevance ≥ 4）、表に 読んだ・使用 の列。

### 変更
- 引用の照合（L032/L033/L034）は `check.claim_docs`（既定 `docs/**/*.md` と `literature/surveys/*.md`）の全文書を見る。自動ブロックと DIGEST は見ない。
  dirty な run の引用は `check.dirty_citation`（既定 warn。claims.md は常に error）、退避済みは警告。L034 は引用を含む行を対象外にした（条件ラベルの数字の偽陽性）。
- `labkit runs list` は退避済みを隠し、dirty / archived / 予想の判定を列で出す。
- 雛形: `scripts/run_example.py` を削除し `src/<pkg>/experiments/example.py`（entry）と `[prediction]`・`[[pass]]` 入りの `example.toml` に。`make example` は `labkit run`。
  `lab.toml` は `require_prediction = true`・`require_clean = true`・`max_file_lines = 300`・`[state]`・`[digest]`。CLAUDE.md に「人間のレビューを軽くする」の 6 行。
  `.claude/settings.json` の許可ドメインに doi.org / crossref / datacite / arxiv。`docs/README.md` に prereg / papers / claims / DIGEST の置き場所。
- lab-reviewer: 手作業の引用照合をやめ `labkit check --claims` の出力を記録に写す。読み取りの許可に `runs table` `claim list` `review list` `beat log` `lit queue` `lit surveys`。
- 修正: `git status --porcelain` の 1 行目が " M" で始まるとき先頭 1 文字が欠けていた（開発ログの「未コミット: ocs/…」）。

### 移行
- `labkit standards unlink --to v1.6.0`（Windows では続けて `uv sync --reinstall-package labkit`）、plugin は `/plugin marketplace update lab-standards`、
  雛形は `labkit standards template --ref v1.6.0`（`docs/claims.md`・`prompts/current.toml`・`goal_v1.md` が増える。`scripts/run_example.py` は消してよい）。
- 既存プロジェクトで新たに error になり得るもの: L037（state.md に H1 が複数・同じ H2 が複数。古い節を消す。履歴は git にある）、
  L036（claims.md を使い始めたとき）、そして docs/** 全体が照合の対象になったことによる L033（docs/papers・reports・prereg・math の引用で、
  数値が `値 [単位] [run:<id>:<key>]` の書式どおりに cite の直前に無い、または metrics と合わない）。strict なら Stop hook が止まるので、
  `unlink` の前に新しい labkit で `labkit check --claims` を流し、文書を `labkit cite` の出力に直すか、`check.claim_docs` を狭める。
  他はすべて警告か opt-in。`require_prediction` / `require_clean` は人間が lab.toml で有効にする。
- `labkit standards template --ref v1.6.0` で lab.toml が雛形の既定（`require_prediction = true`・`require_clean = true`）に変わる
  （変わったときは template が 1 行知らせる）。使わないなら false に戻す。v1.4.0 以前の run は文書だけの変更でも dirty と記録されているので、
  結果として使う run は clean に再実行する。dirty の引用の警告が多すぎるなら `check.dirty_citation = "off"`。
- `configs/experiments/example.toml` は既存なら更新されない（`_skip_if_exists`）。`make example` を使うなら `entry = "<pkg>.experiments.example:run"` と
  `[prediction]`・`[[pass]]` を足す（雛形の example.toml.jinja を参照）。使わないなら `src/<pkg>/experiments/example.py` と `__init__.py` を消す
  （残すと L017 の警告）。`scripts/run_example.py` は消してよい。

## v1.5.0 — 2026-11-04

エージェントが「人間の実機・回答を待つ」と判断して `/loop` を自分で止め、夜の間なにもしなかった（accelerated-diff-pat）。
人間不在で走ることが前提なので、待つことを止まる理由にしない。

### 変更
- hooks: `/loop` の停止（`CronDelete`、`ScheduleWakeup` の `stop`）を拒否する。止めるのは人間だけ。`lab.toml` の
  `[claude] allow_self_stop`（既定 `false`）で切り替える。拒否のメッセージは、依存しない仕事か、人間なしで同じ問いに答える方法
  （計算・公開データ・独立実装による検証）への切り替え、目標を達したら次の問いを立てることを案内する。
- 雛形 CLAUDE.md・skill `lab-conventions` に「待って止まらない」を明記。`labkit queue ask` の出力と、承認待ちがあるときの Stop hook の
  メッセージも「待たずに進める」に改めた（承認待ちで終了時の検証を省く挙動は変えていない）。

### 移行
- `labkit standards unlink --to v1.5.0`（Windows では続けて `uv sync --reinstall-package labkit`）、plugin は `/plugin marketplace update lab-standards`
  （hooks.json の matcher が変わるので plugin の更新が要る）。
- 自分で止めてよいループを使うプロジェクトは `lab.toml` に `[claude] allow_self_stop = true`（人間が編集）。

## v1.4.0 — 2026-11-04

nla-solver で /goal・/loop を一晩回して効いたもの（記録を見ない点検、1 拍の指示書の再注入、予想の関門、撤回の記録）を、
skill・agent・雛形として標準に入れる。合わない規則（HPC のジョブ投入は人間だけ）を直し、要望の多かった図テンプレートを足す。

### 追加
- skill `autonomous-run`: 長い自律運用の手順（失敗の型、目標・1 拍の指示書・状態・backlog の置き方、/goal と /loop の書き方と間隔、
  1 拍の 5 手、予想の関門と事前登録の修正の順序、ぶっちゃけ点検、撤回と捨てる線、範囲を縮める判断は queue へ）。
- agent `candor-check`: ぶっちゃけ点検。目標・前提・主張の要約だけを読み（開発ログ・commit 履歴・backlog は読まない）、
  避けている当然の結論・捨てるべき線・最も大胆な一手を答える。道具は Read / Grep / Glob だけで、ファイルを書けない。
- 図テンプレート `boxplot`（群ごとの分布、中央値の注記）と `convergence`（両対数、系列ごとの最小二乗の次数を凡例に、基準勾配の補助線）。
- 雛形: `prompts/beat_v1.md`（1 拍の指示書）、`docs/state.md`（前提・点検・予想の当たり外れ・撤回・次の一手の表）。雛形の生成テストで存在を確かめる。

### 変更
- 雛形 CLAUDE.md の「長い自律運用」を、置き場所と 5 つの規則に縮め、詳細は skill に移した。
- skill `new-experiment` の「長い run を待つあいだ」は skill `autonomous-run` を指すだけにした（重複の削除）。
- skill `hpc-job`: PBS も対象と明記。運用で踏んだ罠（1 ノードあたりの GPU 数、PBS の作業ディレクトリ、手元の長い計算は setsid、
  一時ファイルの溢れ、複数キューへの投入）を足した。「ジョブの投入は人間だけ」をやめ、人間が計算資源の使用を任せたときは Claude が投入してよいとした
  （HPC 上の削除は引き続き人間）。
- skill `make-figure` と README の図テンプレートの一覧（13 種）。

### 移行
- `labkit standards unlink --to v1.4.0`（Windows では続けて `uv sync --reinstall-package labkit`）、plugin は `/plugin marketplace update lab-standards`。
- 雛形の新しいファイルは `labkit standards template --ref v1.4.0`。既存の `docs/state.md`・`prompts/` の版はそのまま使える（雛形の表は参考）。

## v1.3.0 — 2026-11-03

長い自律運用（/goal）で観察された失敗への対策（nla-solver の 2 日間の運用から）。v1.2.0 の skill（計算する前に予測する、
/loop で再注入）を機械的な検証で補う。対象: 計算の完了を待つだけで止まる、結果を計算する前に分かる結論を計算で確かめに行く、`python -` を入力なしで打って止まる、使われないコードが溜まる、
v0.x が積んだ承認待ちを `labkit approve` できない。すべて既定では無効か警告で、既存プロジェクトの動作は変わらない。

### 修正
- `labkit approve` が v0.x の承認待ち（`category` が無い）で `KeyError: 'category'` になっていた。記録されたコマンドから種類を引き直して承認する。
  判定できないときは、reject と delegate の手順を示すエラーにする。

### 追加
- PreToolUse: 入力の無い `python -`（行頭か `;` `&&` `||` の直後で、heredoc もパイプも無い）を止め、ファイルか heredoc を使うよう示す。
- `[autonomy] backlog / min_open`（既定は無効）: backlog の未着手の項目（`- [ ] ...`）が `min_open` 件未満なら Stop hook が終了を止める。
  計算待ちでターンを終えず、次の作業に移らせる。上限回数で人間に委ねる仕組み（`max_stop_blocks`）は同じ。
- `[runs] require_prediction`（既定 false）: true なら `Run` は設定の `prediction`（結果の予想と根拠）が無いと始まらず、run ディレクトリも作らない。
  予想は `meta.json` の `prediction` に残る（false でも設定にあれば残す）。
- check L017（警告）: `src/` のモジュールが src・scripts・tests・jobs・Makefile・pyproject.toml のどこからも import されていない。
- skill `new-experiment`: 予測を `prediction` に書く方法と `[autonomy]` の backlog を案内。
- 雛形: CLAUDE.md に「長い自律運用」（考えてから計算する・待たない・当然の結論から逃げない・活動量で測らない・/goal は prompts のファイルを指す）、
  `docs/backlog.md`、lab.toml に `[autonomy]` と `runs.require_prediction`、prompts/README に版の一覧と /goal の置き方。

### 移行
- `labkit standards unlink --to v1.3.0`、plugin は `/plugin marketplace update lab-standards`、雛形は `labkit standards template --ref v1.3.0`。
- 使うなら lab.toml に `[autonomy]`（例: `backlog = "docs/backlog.md"`, `min_open = 10`）と `[runs] require_prediction = true` を足す（人間が編集）。

## v1.2.0 — 2026-11-03

accelerated-diff-pat で丸 1 日、エージェントを自走させて分かった摩擦を直す。

### 変更
- 書き込み可能な場所（`layout.writable`）に `.claude/commands` を足した（既定と雛形）。プロジェクトのスラッシュコマンド
  （例: `prompts/` のゴールを読む `/goal`）を Claude が作れる。`.claude/settings.json` は引き続き書けない。
  writable の照合を前方一致にし、`a/b` のような複数段の項目が効くようにした（これまでは先頭の 1 段しか見ていなかった）。
- 承認ゲートのメッセージに、承認・委任をどのプロジェクトで行うかを書く。ゲートはセッションのプロジェクトで判定するので、
  別のリポジトリ（例: lab-standards 本体）を操作するときも、そのセッションのプロジェクトで `labkit approve` / `labkit delegate` する。
- `labkit standards link` / `unlink` は Windows で環境を同期しない（実行中の labkit.exe を uv が置き換えられず、labkit が中身の無い
  状態で残った）。代わりに `uv sync --reinstall-package labkit` を案内する。
- L035: lab-reviewer の記録でないものの置き場（docs/reports/ など）を案内する。
- skill `new-experiment`: 計算する前に結果を予測し、予測が確かな run は代表 1 本に絞る（第 0 段）。何時間も自走させるときは
  `/loop` で 1 拍の指示書を再注入する（量ではなく「予想と違った結果」を拍の中心にする）。開始直後の殻の片付け方。

### 移行
- `labkit standards unlink --to v1.2.0`（Windows では続けて `uv sync --reinstall-package labkit`）、plugin は `/plugin marketplace update lab-standards`。
- `lab.toml` で `layout.writable` を上書きしているプロジェクトは、`/goal` などを使うなら `".claude/commands"` を足す（人間が編集）。

## v1.1.0 — 2026-11-03

開始直後に止めた run が `meta.json` の無い殻（L020）として残り、`runs/` は Claude が消せないので人間の回答を待つしかなく、
Stop hook が無関係なセッションの終了まで止め続けた（accelerated-diff-pat で 1 日に十数件）。人手なしで片付くようにする。

### 変更
- `Run` は run ディレクトリを作った直後、入力の hash や環境の取得より先に、スキーマの必須項目だけの `meta.json`（status=running）を書く。
  開始中に止められても殻にならず、L021 → `labkit runs mark` で片付く。`created` は開始直後の時刻のまま。
- `labkit runs mark <id> --to interrupted|failed|finished --reason ...` が `meta.json` の無い殻にも効く。削除はせず、ディレクトリ名から
  分かる最小の `meta.json`（git は null）を書いて記録として残す。Claude が実行してよい。
- L020 の殻と L021 のメッセージに、実行できる `labkit runs mark` の書き方を示す（L021 の `failed --reason` は `--to failed` の誤記だった）。
- Stop hook: `max_stop_blocks` 回で人間に委ねた違反を覚え、同じ違反だけなら以後そのセッションの終了を止めない（新しい違反が出たら止める）。
  これまでは委ねた直後から数え直し、同じ違反で止め続けた。

### 移行
- `labkit standards unlink --to v1.1.0`、plugin は `/plugin marketplace update lab-standards`。既存の殻は `labkit runs mark <id> --to interrupted --reason ...`。

## v1.0.2 — 2026-11-02

### 修正
- テストの import 順（CI の lint が落ちていた）。動作に変更なし。

## v1.0.1 — 2026-11-02

### 修正
- plugin の入口: プロジェクトの labkit が古く `labkit hook` を知らない（v0.x）とき、すべての操作を止めてしまわず、SessionStart で更新方法を 1 行知らせる
  （plugin を先に更新し、プロジェクトの labkit を後から上げる順でも作業が止まらない）。

## v1.0.0 — 2026-11-02

「統制を入力側から成果物側へ」。2 プロジェクトでの実運用の監査（`docs/audit-2026-11-02.md`、ADR `docs/decisions/0001-artifact-first.md`）に基づく全面改訂。
互換を壊す変更を含むためメジャー。既存プロジェクトの `lab.toml`・figspec・run の meta.json はそのまま動く。

### 変更（統制の縮小）
- 承認は「種類＋ブランチ＋期限」の委任に統一（`labkit approve` = その種類をそのブランチで 24 時間許可）。HEAD・コマンド全文には結び付かない。
- 承認ゲートの対象を 保護ブランチへの push/merge・force push・tag・gh release/merge・raw freeze に限定。feat ブランチへの push、copier、lab.toml の mode 切替は自由。
- presence を削除。permission mode が default / acceptEdits / plan なら確認画面、それ以外はキュー。
- flow は完了条件のチェックリストだけに（段階による操作禁止を削除）。improve-standards flow は削除し、通常の PR 手順（skill）に。
- Stop hook は `labkit check --claims`（成果物の検証）と開発ログの判断欄だけで止める。ruff は pre-commit へ。

### 追加（来歴と保全）
- `meta.json`: `env`（OS・CPU・GPU・uv.lock の sha256・主要パッケージ版・スレッド変数）、`seed`、`pid`、`paths`、入力の生成元 `run_id`（系譜）、出力の `sha256`。
  dirty な run は `dirty.patch`（未追跡ファイルも dirty に数える）。run ID は UTC、衝突時は引き直す。`heartbeat` で最終活動時刻。
- `labkit runs mark <id> --to failed|interrupted|finished --reason`（異常終了した run の記録。Claude が実行してよい）。L021 は警告に。
- `labkit mirror push|pull`（`configs/paths/*.toml` の `mirror_root` へ差分コピー）。migrate の freeze 段階は写しを要求する。
- `labkit devlog` が変更ファイル・今日の commit・今日の run を自動ブロックで埋める。必須見出しは 目的・結果・観察・判断と理由・未解決 の 4 つ。
- `data/cache`（サイドカー不要の再生成可能な中間物）。L022 はサブディレクトリも検査。
- 図テンプレート `band`・`bar`・`panels`、`errorbar` の `xmode = "numeric"`、`options.aspect`。figmeta.json に commit。
- check: L016（np.save / np.savez / torch.save、警告）、L030（判断欄が空）、L034（結果節の数値に引用なし、警告）、`code_dirs` に jobs、
  絶対パスの既定に `/mnt/` と `(?<![A-Za-z])[A-Za-z]:[\/]`（raw 文字列・`/` 区切りの Windows パスも検出、`https://` は除外）。
- SessionStart が plugin と labkit の版の不一致を知らせる。
- 雛形: CLAUDE.md に「研究契約」欄、`.gitattributes`（`data/raw/** -text`）、pre-commit から `data/raw/` を除外、`configs/base.toml` の seed を必須に。

### 削除
- Julia 版（LabKit.jl）、MLflow 連携、plugin eval、`lit key` / `lit check`、`labkit mode`、`human_check`、OPTIMIZATION_LOG / AGENT_QUEUE / docs/notes、
  hooks の `_labstate.py` 重複（判定を labkit に一本化。plugin は標準ライブラリの入口 `scripts/hook.py` だけ）。

### 移行
1. 本体: `/plugin marketplace update lab-standards`（他の PC でも）。
2. 各プロジェクト: `uv run labkit standards unlink --to v1.0.0` → commit → `uv run labkit standards template --ref v1.0.0`（衝突を解消）→ `make check` → commit。
3. `configs/paths/local.toml` に `mirror_root` を書き、`uv run labkit mirror push`。
4. 開発ログの既存ファイルは 7 見出しのまま通る。空の見出しがあれば L030 になるので埋めるか消す。

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
