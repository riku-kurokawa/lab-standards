# ハーネス: 成果物を検証し、主線から外れず、芽を拾い続ける

目的は「人間の承認なしに Claude が完全自律で動き、研究記録が検証可能で、主線から絶対にずれず、しかし面白い芽を拾い続ける」こと。
v0.3/v0.4 は入力側（Claude が打つコマンド）の統制に投資し、実運用で迂回され、迂回のたびに記録が歪んだ（`docs/audit-2026-11-02.md`）。
v1.0.0 は成果物側（run・データ・文書が検証できるか）に軸を移し、統制は最小にした。
v1.6.0 はボトルネックが人間のレビュー時間だと分かって、人間が読むものを機械が同じコードで作る短い生成物（DIGEST・台帳・一覧）に変え、
不要な run・コードを視界から消し、1 拍の入口を機械が持つようにした（8・9 節）。
v2.0.0 は承認ゲートと承認・却下・回答・委任を廃止して完全自律にし、主線と芽の台帳・拍の関門・資源の紐付けを足した（2 節、ADR 0002）。
v2.3.0 は 3 つのプロジェクトの実運用の監査（`docs/audit-2026-11-10.md`）から、人間のレビューを速く正確にすることに絞って磨いた:
常に文脈に載る文を半分にし、検証を速くし、DIGEST を判断が要る順に並べて自動で作り直し、使われていない部品を削った（10 節）。

```
人間                          Claude Code                       .lab/（プロジェクト直下）
docs/mainline.md     ←── labkit main set/add/done（主線と期限。beat end と Run の関門が読む）
docs/seeds.md        ←── labkit seed add/decide（芽の台帳）
                          queue/Q002.json    ←── labkit queue ask（人間への一方通行の連絡）
                          flows/migrate.json ←── labkit flow start/advance（チェックリスト）
                          mirror.json        ←── labkit mirror push（正本の写し）
docs/reviews/*.md    ←── lab-reviewer agent だけが書く（agent_type で判定）
docs/claims.md       ←── labkit claim add/retract（主張の台帳。L036 が根拠の run を見張る）
docs/DIGEST.md       ←── labkit digest（人間が読む 1 枚。台帳・run・レビュー・queue から生成）
                          beats/日付.jsonl   ←── labkit beat start/end（1 拍の 3 行。prompts/current.toml が現行の版）
```

部品は 4 つ: 成果物の検証、主線と芽の関門、独立レビュー、手順のチェックリスト。判定はすべて `labkit`（`labkit hook`）にあり、plugin は stdin を渡す入口だけ。

## 1. 成果物の検証（labkit check --claims）

Stop hook が毎回見るのはこれだけ（体裁の検査は pre-commit と CI）:

| 何を | どう |
|---|---|
| run | `meta.json` がスキーマどおり（L020）。commit・dirty（dirty なら `dirty.patch`）・環境・seed・入力の hash と生成元 run・出力の hash。running のまま残った run は警告（L021）→ `labkit runs mark` |
| 派生データ | `data/interim`・`processed` の全ファイル（サブディレクトリも）にサイドカー（L022）。`data/cache` は対象外 |
| 生データ | MANIFEST との一致・読み取り専用（L002/L003） |
| 開発ログ | 目的・判断と理由・未解決 が空でない（L030）。変更ファイルと run は `labkit devlog` が自動で埋めるので、人が書くのは判断だけ |
| 数値の主張 | `12.3 dB [run:<id>:<key>]` が runs/ の `metrics.json` と一致（L032/L033）。「結果・観察」節の小数に引用が無ければ警告（L034。引用を含む行は対象外）。対象の文書は `[check] claim_docs`（既定 docs/**/*.md と literature/surveys/*.md）。自動ブロックと DIGEST は見ない。結果・主張の節の scratch/ 参照は警告（L038） |
| dirty の引用 | 未コミットの差分で実行した run を結果として引用すると `[check] dirty_citation`（既定 warn）。`[runs] require_clean = true` なら dirty では run を始めない（雛形は true） |
| 主張の台帳 | `docs/claims.md` の各行の書式、撤回の理由、open な主張の根拠（L036。根拠の run が無い・failed・dirty・退避済みなら違反）。台帳は `labkit claim` だけが書く |
| 予想の判定 | `[prediction]` の表（basis・claims の key と range/point+tol）は finished 時に metrics と照合され `prediction_result`（hit/miss/partial/undeterminable）が meta.json に残る。自由記述の予想は `labkit runs verdict --say`（self_reported）。判定の無い run は警告（L024） |
| 退避 | `labkit runs archive` は削除せず meta.json に `archived` を書く。`runs list`・DIGEST・`runs table` から隠れ、ID の言及は警告・数値の引用は error（L032、`check.archived_citation`）。名指しは `runs archive <id> ... --reason`。`--undo --reason` で戻る（`archive_log` に履歴が残る） |
| 比較の条件 | 設定の `[compare.<名>]`（vary は 1 軸で値は 1 語、腕の条件は common ∪ 腕の表から導出、`[compare]` の外に腕を名指す語（腕の名前・軸の値・levels）の鍵を置かない、掃引は比較の指標と `better` で全腕同じ総試行数、対象外は `lab.toml` の `[compare.capability]` か著者の宣言）を Run が開始前に検査し、config.json の hash を `meta.config_sha256` に残し、終了時に設定が変わっていないことを確かめてから 1 回だけ `comparisons.json` を書く（hash は meta の outputs）。L027 は凍結した設定から計算し直す。主張の根拠は matched な比較の指標か `[report] noncomparative`（広い glob・腕を名指す語・比べる語は不可）だけ（既定で拒否）。主張は既定で比較: 2 つ以上の値を引くなら、1 つの run の値は 1 つの matched な比較の keys だけ（非比較は 1 つまで）。複数 run の主張と、同じ指標（腕を名指す語を除いて同じ指標も）を 2 つ以上の run から引く文書（段落・表を区別しない文書ごと）は axis（値は 1 語）と軸以外の設定（`[compare]` の common・arms を含む）・commit の同一性。**比較は台帳（`claim add`）を通す**: 文書（state・papers・reports など。開発ログを除く）の 1 行（表の行も）に 2 つ以上の run の値か、1 つの matched な比較の keys ではない同じ run の 2 つ以上の値を並べる行は L027 の警告だけ（同じ行に根拠がその引用を覆う open な主張の ID、または run をまたぐだけで通る `axis=<鍵>` があれば出さない） |

### 比較の脅威モデルと残る危険

比較の関門（compare.py・L027・`claim add`）が防ぐのは、**善意だが雑な、あるいは近道をする著者・エージェント**が設定・コード・主張を書くときの
**偶然の・都合のよい不一致を引用できてしまうこと**である。具体的には: `noncomparative = ["*"]` のようなワイルドカード、宣言した比較の外に置いた
腕どうしの脇の指標（`raw_ours_vs_flat`）、`[solver.ours]` のような腕ごとの表、`"ours+lr0.1+fp64"` のように文字列に束ねた軸、腕ごとに違う調整の量や向き、
`n/a`・`未定` で埋めた必須の条件、著者だけの「対象外」、古い・run の途中で変えた設定、`_git_commit` を軸にした実験間の比較、文書の中で同じ指標を別 run から並べること（名前の違う指標・同じ run の 2 つの値を 1 行に並べるのは警告だけ。下の残る危険）。
これらは run を始めない・failed にする・L027 の error・`claim add` の拒否のどれかになる（`labkit/python/tests/test_compare.py` に抜け道ごとのテスト）。

**防げないもの（残る危険）**: 完了した run のファイルを意図して偽造すること。run のディレクトリは chmod で書き込み可能に戻せ、`meta.json` 自体は
どこにも hash が固定されていない。config.json・metrics.json・comparisons.json を書き換え、`meta.json` の outputs と `config_sha256` まで計算し直せば、
手元のファイルの照合（L027）は通る。kill してから running の run を書き換えることも同じ。入れた緩和は安価なものだけ:
開始時の config.json の hash（`meta.config_sha256`）を終了時・記録時・check で照合する（outputs だけを直した改変は検出する）、`labkit runs mark ... finished` は
比較を宣言した run・comparisons.json のある run を拒否し、開始時の hash と設定の検査をやり直す。意図した偽造を防ぐには、meta.json の hash を run の外
（git に commit した台帳・追記だけの記録・別の計算機）に固定する必要があり、本体はまだそれを持たない。比較の結論を外に出す前には、人間か
独立した再実行が run を再現すること。また、entry のコードが `arm_conditions`・`chosen` の値を本当にソルバに渡したかは機械では証明できない
（設定が唯一の出所であることまでを保証する）。

**legacy run（v2.2.1）**: labkit < 2.2.0 の run（`meta.config_sha256` が無く `labkit_version` が 2.2.0 より前）は比較の宣言を持たないので、その 1 つの値の引用は警告に下げる（2 つ以上の値を並べる主張と run をまたぐ同じ指標は error のまま）。新しい run の `meta.json` から `config_sha256` を消し `labkit_version` まで古く書き換えれば legacy に見せられる（上と同じ meta.json の偽造で、手元の照合では防げない）。履歴の文書（`check.history_docs`）では引用の L027・L032 を警告にするので、現在の主張は台帳・state・papers・reports に書く。

残る危険はほかに 3 つある（どれも機械では閉じられないので、レビューで見る）:

- **文書の並置は警告だけ**: 比較は主張の台帳（`labkit claim add`）を通すことで強制する（ceteris paribus を確かめ、拒否する）。
  state.md・papers・reports の文章は意味を機械が読めないので、1 行に別々の run の値や、同じ run の比較でない 2 つの値を並べた行は
  L027 の**警告**にとどめる（同じ行に、根拠がその引用を覆う open な主張の ID を書けば消える）。同じ指標を run をまたいで引く文書だけは
  error のまま（腕ごとに run を分けて同じ指標名で並べる形）。行を分けて名前の違う指標を並べた文章（`gain` と `gain_x` を別の段落に）、
  警告を無視して出した文書は、機械では止まらない。外に出す比較の文は台帳の主張の ID を引く。

- **比べる語の一覧は経験則である**: 非比較の指標の名前の検査は、腕を名指す語（腕の名前・軸の値・levels）・比較の指標の語幹・
  比べる語の一覧（`vs`・`minus`・`over`・`speedup`・`beats`・`wins`）だけを見る。`delta_db`・`improvement_ratio`・`gap`・`rel_*` のような、
  一覧に無い語で名づけた 1 つの非比較の指標が、中で複数の腕から計算した差や比であっても機械は見抜けない（1 つの主張・文書に並べた 2 つの値は
  上の既定で比較とみなして照合するが、1 つの値の中に畳み込んだ比較は名前でしか分からない）。
- **entry が arm_conditions を無視しうる**: entry のコードが腕の条件を `arm_conditions`・`chosen` から読まず、腕の順番で引く配列・
  設定の値（鍵ではなく）・コードの定数に腕ごとの条件を埋めれば、設定の照合は通る。比較対象の自由パラメータを全腕共通の定数として
  トップレベルに置けば、掃引も強制されない。設定に書いた条件が実際に使われたことは、コードを読むか独立に再実行して確かめる。

## 2. 主線と芽（完全自律の中で、主線から絶対にずれず、芽を拾い続ける）

nla-solver の 2 週間の運用で、資源と時間が消えた原因はエージェントの行動と意思決定の計画にあった: 新しさを追って目標の版を 20 回替え、
期限のある成果物（発表の表）が空欄のまま残り、壊れた計算を監視なしで 18 本続けて回し、どの線のためか分からない run が積み上がった。
文章の規則では止まらなかったので、台帳と関門で機械的に止める（ADR 0002）。関門は `docs/mainline.md` に open の項目があるあいだだけ働く。

| 関門 | どこで | 何を止めるか |
|---|---|---|
| 線の宣言 | `labkit beat end --line main\|seed:Sxxx\|other` | どの線を進めたか言えない拍 |
| 主線の割合 | 同上（`autonomy.main_share` 0.7・`main_window` 10） | 直近 10 拍で主線以外が 3 拍を超える拍 |
| 期限の守り | 同上（`main_guard_hours` 12） | 期限切れか期限まで 12 時間以内の項目があるのに主線以外を進めた拍 |
| 芽の頻度 | 同上（`seed_every` 8） | 8 拍のあいだ芽が 1 つも記録されない拍（主線だけを回して考えるのをやめない） |
| 芽の昇格 | `labkit seed decide --to promote --serves Mxxx` | 主線のどの項目に効くかを言えない芽を主線に入れること |
| 資源の紐付け | `labkit.Run` の開始 | 設定に `serves`（open の Mxxx・確かめ中の Sxxx・`other:<理由>`）が無い run |
| 失敗の反復 | 同上（`fail_repeat` 3） | 同じ名前の run が 3 回続けて failed/interrupted で、そのあいだ commit が進んでいないときの 4 回目 |
| 完了の根拠 | `labkit main done --evidence` | 根拠（run・ファイル・commit）の無い完了 |

台帳は labkit だけが書く（hooks が手書きを止める。期限を延ばして関門を逃げない）。L025 が期限切れの open な項目を警告し、L026 が台帳の書式を検査する。
`labkit beat start`・SessionStart・digest が、主線の残り時間・主線の割合・芽の数・直近 24 時間の run 時間（線ごと・状態ごと）を出す。

**承認は無い**: push・merge・tag・release・raw freeze も Claude が行う。人間への連絡は `labkit queue ask`（決めたことと理由。返事は待たない）。
取り返しのつかなさは成果物の保護（3 節）と、GitHub 側の main のブランチ保護（`docs/SETUP.md`）で守る。
hooks はテキスト照合であり security boundary ではない（`sh -c`、スクリプト経由は見えない）。目的は「うっかり」と「無人時の暴走」を止めること。

## 3. 成果物の保護（hooks）

`data/raw` の既存ファイルの変更・削除・持ち出し（新しいファイルの搬入は上書きしない cp / mv で可）、`runs/` の削除・権限変更、
`lab.toml` の編集（migrate の apply-template・strict の段階のあいだだけ可）、`.lab/` と台帳（claims・DIGEST・mainline・seeds）の直接編集、`git clean -x`、`git checkout -- data/raw`、`layout.writable` 以外への Write、描画ライブラリ・pickle の import を止める。
いずれも成果物（原本・run・規約・台帳）を壊す操作であり、作業の手順は縛らない。エージェントは自分を縛る規約（lab.toml）を変えない。

## 4. 独立レビュー

`lab-reviewer` agent がレビューし、`docs/reviews/YYYY-MM-DD_<flow>_<段階>.md` に frontmatter（reviewer, flow, stage, commit, verdict, summary, findings[, resolves]。summary は人間向け 1 行で無いと L035 の警告、resolves の先が無いと違反）付きで保存する。
`docs/reviews/` は hook 入力の `agent_type` が lab-reviewer のときだけ書ける（自己採点の防止）。lab-reviewer の Bash は読み取りの許可リストだけ。
migrate の reproduce 段階は、現在の HEAD に対する verdict=pass の記録が無いと進めない。

## 5. 手順のチェックリスト（labkit flow）

定義は `labkit/flows/migrate.toml`。段階ごとの完了条件（clean tree、タグ、写し、CSV、lab.toml の mode、MANIFEST、check、run、レビュー）を
`labkit flow advance` が機械的に検査する。**段階による操作の禁止はしない**（v0.3 の forbid は守られず、記録だけが矛盾した）。
freeze 段階は `labkit mirror push` 済みであることを要求する（配置替えの途中でデータを失わないため）。

## 6. 正本の写し（labkit mirror）

`runs/` と `data/` は git 管理外なので、`configs/paths/<LAB_ENV>.toml` の `mirror_root` に `labkit mirror push` で差分コピーする
（size と mtime で比較、`--verify` で sha256。削除はしない）。写し先には `MIRROR.json`、手元には `.lab/mirror.json`。
外部ツール不要で、NAS・外付け・クラウドドライブのマウントに使える。

## 7. 文脈への注入

SessionStart（compact 含む）: 今日の開発ログの有無、完全自律の 1 行、無効のままの関門（`require_prediction` / `require_clean`）、
goal/beat の現行の版と最後の拍の判断（`prompts/current.toml`）、主線と芽・資源の使い道、DIGEST の古さ、人間への連絡、進行中の flow、plugin と labkit の版の不一致。
compact 後はさらに、目標ファイルの最初の節を原文で再注入する（要約で薄れた指示を戻す）。
UserPromptSubmit: hook を登録しない（v2.3.0。v2.0.0 から何も注入していなかった）。
人間への連絡は新しい 3 件と残りの件数だけを出す（返事を待たない連絡を毎拍すべて読み直させない）。

## 8. 人間の入口（DIGEST・台帳・一覧）

人間は devlog 600 行を読まない。読むのは機械が同じコードで作る短い生成物だけ:

| 入口 | 作るもの | 中身 |
|---|---|---|
| `labkit digest [--since]` | `docs/DIGEST.md` 1 枚（既定は直近 `digest.days` 日。`labkit beat end` が `digest.refresh_hours` より古ければ作り直す） | 先頭に「先に見るもの」（違反・根拠の崩れた主張・撤回と理由・期限切れ・外れた予想・新しい連絡・失敗した計算）、主張と根拠の run を生んだコード（entry @ commit）、予想と結果（同じ根拠の外れは 1 行）、新しい図、レビューするコード（src の変更と試験の変更の有無）、主線と芽・資源、人間への連絡、run の収支、未解消のレビュー、check の集計、文献、文書。材料がある節だけ出す |
| `labkit claim list` | 主張の台帳 `docs/claims.md` | 何を主張し（根拠は `labkit cite` の書式）、何を撤回したか（理由つき）。根拠が崩れると L036 |
| `labkit runs list` / `runs table <name>` | run の一覧・同名の表の連結 | 退避済みは既定で隠す（`--all`）。table は clean な finished だけを連結し、除外した run と理由を出す |
| `labkit review list [--open]` | レビュー記録 1 件 1 行 | `summary`（120 字以内）、must/should の件数、`resolves` の鎖。`--open` は後続の pass が無い changes-requested |
| `labkit beat log` / `lit queue` / `lit surveys` | 拍の 3 行 / 人間の読書キュー / サーベイの判定 | エージェントが何を考え（予想・結果・判断）、何を読んだか（`read_by`・`claims`・`verdict`・`n_opened`） |

生成物の元は台帳・meta.json・frontmatter なので、エージェントが文章で盛ることはできない（盛るには run か台帳を変える必要があり、check が見る）。

## 9. 1 拍（current.toml と beat）

長い自律運用（/goal・/loop）で指示が薄れないよう、現行の目標と指示書の版を `prompts/current.toml`（goal / beat / interval）に機械が持つ。
`labkit beat start` がその本文と状態（主線と芽・資源・今日の run・open な主張・前の拍の判断）を出し、`labkit beat end --line --predicted --observed --decided [--runs]` が
拍の 3 行を `.lab/beats/日付.jsonl` に記録して開発ログの自動ブロック「拍（自動）」に写す（時刻は機械が入れる）。`/loop 20m /lab-rules:beat`（skill `beat`）で回す。
L005 は current が指す版が無い・より新しい版があるときに知らせる。目標の改訂は版を上げて current を更新する（過去の拍が使った版を残す）。

## 10. 文脈と検証の軽さ（v2.3.0）

エージェントの性能は、常に載っている文の量で下がる（Claude Code の公式の目安は CLAUDE.md 200 行以内、skill は一覧に載るだけで毎ターンの文脈になる）。
人間のレビューは、読むものの量と、検証を待つ時間で遅くなる。どちらも「足さない」ことで守る。

| 何を | どう |
|---|---|
| 規則は 1 か所 | 雛形 CLAUDE.md は常に要ること（研究契約・完了条件・検証できる記録にする理由・置き場所）だけ。手順は skill、止められたときの直し方は labkit と hooks のメッセージ。同じ規則を CLAUDE.md・skill・指示書に重ねて書かない（比較の規則は `skills/new-experiment/compare.md` だけ） |
| 強調より理由 | 「必ず」「絶対」ではなく、なぜそうするかを 1 行添える。例外の無い規則だけを hooks と check にする |
| 規則より仕組み | 「1 日 1 回 `labkit digest`」のように守られなかった規則は、機械がやる（`labkit beat end` が作り直す） |
| 検証は速く | Stop hook の `labkit check --claims` は run 550 本・引用 1400 件で十数秒（run の比較の状態を使い回す）。check は `.claude/worktrees`・scratch・読み取り専用領域に降りない |
| 警告は少なく | 実行中の run（直近 10 分に記録がある）に L021 を出さない。tests/ の `np.save` に L016 を出さない。同じ対象の新しいレビューがあれば古い changes-requested は open に数えない |
| 使われないものは削る | 3 プロジェクトで使用 0 だった backlog の件数の関門、何も注入しない UserPromptSubmit hook、雛形の notebooks/、skill 2 つ（統合）を削った |

## 後方互換

- v0.x のプロジェクトの `lab.toml` はそのまま読める（無くなったキー `cite_bare_numbers`・`presence`・`[runs] hash_inputs_max_gb` は無視）。
- `.lab/approvals/`・`.lab/presence`・`.lab/delegations.json` は使わない（残っていても害は無い）。v1.x の承認待ち（kind=approval）は無視され、`labkit queue done <ID>` で閉じられる。
- v2.3.0: `lab.toml` の `[autonomy] backlog`・`min_open` は無視される。`notebooks/` は `layout.allowed` に残るので、既にあるプロジェクトはそのまま。
- v2.0.0: `lab.toml` の `[gate]` は無視される。`docs/mainline.md` が無いか open の項目が無ければ、主線と芽の関門は何も強制しない（既存プロジェクトはそのまま動く）。
- v0.x の run の meta.json は新しい schema でも通る（追加フィールドはすべて任意）。
- v1.6.0 で足した検査はすべて警告か opt-in: L005・L018・L023・L024・L038・L047・L048 と dirty の引用は warn、`require_clean` は既定 false（雛形だけ true）。
  error になるのは L036（`docs/claims.md` の台帳の構造）と L037（`docs/state.md` の H1・H2 の重複）だけで、どちらもファイルが無ければ何も出ない。
  `prompts/current.toml` が無ければ `labkit beat` は使えないが、他は変わらない。`prediction` の文字列（自由記述）は引き続き受け付ける。
