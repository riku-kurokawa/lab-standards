# ハーネス: 成果物を検証し、取り返しのつかない操作だけを止める（v1.0.0）

目的は「人間が不在でも Claude が止まらず、研究記録が検証可能で、取り返しのつかない操作はしない」こと。
v0.3/v0.4 は入力側（Claude が打つコマンド）の統制に投資し、実運用で迂回され、迂回のたびに記録が歪んだ（`docs/audit-2026-11-02.md`）。
v1.0.0 は成果物側（run・データ・文書が検証できるか）に軸を移し、統制は最小にした。
v1.5.0 はボトルネックが人間のレビュー時間だと分かって、人間が読むものを機械が同じコードで作る短い生成物（DIGEST・台帳・一覧）に変え、
不要な run・コードを視界から消し、1 拍の入口を機械が持つようにした（8・9 節）。

```
人間                          Claude Code                       .lab/（プロジェクト直下）
labkit approve Q001  ──→  delegations.json  ←── labkit hook が照合 ──  git push origin main
labkit answer Q002   ──→  queue/Q002.json   ←── SessionStart / UserPromptSubmit が文脈へ
                          flows/migrate.json ←── labkit flow start/advance（チェックリスト）
                          mirror.json        ←── labkit mirror push（正本の写し）
docs/reviews/*.md    ←── lab-reviewer agent だけが書く（agent_type で判定）
docs/claims.md       ←── labkit claim add/retract（主張の台帳。L036 が根拠の run を見張る）
docs/DIGEST.md       ←── labkit digest（人間が読む 1 枚。台帳・run・レビュー・queue から生成）
                          beats/日付.jsonl   ←── labkit beat start/end（1 拍の 3 行。prompts/current.toml が現行の版）
```

部品は 4 つ: 成果物の検証、承認ゲート、独立レビュー、手順のチェックリスト。判定はすべて `labkit`（`labkit hook`）にあり、plugin は stdin を渡す入口だけ。

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
| 退避 | `labkit runs archive` は削除せず meta.json に `archived` を書く。`runs list`・DIGEST・`runs table` から隠れ、引用すると警告（L032）。`--undo` で戻る |

## 2. 承認ゲート

対象は取り返しのつかない、または共有先を変える操作だけ: **保護ブランチ**（`[gate] protected_branches`）への push と merge、
force push・リモートブランチの削除・`--tags`、`git tag` の作成・削除、`gh pr merge`、`gh release`、`labkit raw freeze`。
**feat ブランチへの push は自由**。copier / lab.toml の mode 切替はゲートの対象外（git で戻せる）。

| 状態 | 挙動 |
|---|---|
| 委任あり（`labkit delegate` / `labkit approve` の結果。期限内・ブランチ一致） | 許可（理由に委任 ID） |
| permission mode が default / acceptEdits / plan（確認画面が人間に届く） | `ask`（通常の確認画面） |
| それ以外（auto / bypassPermissions / dontAsk） | 拒否し、`.lab/queue/<ID>.json` に記録（種類・ブランチ・コマンド・HEAD・理由・session） |

承認 = `labkit approve <ID>` が、その承認待ちの**種類をそのブランチで `approval_ttl_hours`（既定 24 時間）許可する委任**を作ること。
コマンド全文や HEAD には結び付かないので、承認後に commit しても無効にならず、同じ種類の操作は期限内なら何度でも通る。
`labkit delegate <カテゴリ...> [--branch B] [--hours N]` は人間が先に宣言する形（カテゴリ: git_push git_tag git_merge gh_merge gh_release raw_freeze flow raw_write lab_toml、グループ release / migrate / all）。

Claude が承認を作れないようにする層: (1) `labkit hook` が `labkit approve|reject|answer|delegate` と `.lab/` への直接書き込みを拒否、
(2) 雛形の `permissions.deny` と sandbox の `denyWrite`（対応 OS のみ）。

**脅威モデル**: hooks はテキスト照合であり security boundary ではない（`sh -c`、スクリプト経由、エイリアスは見えない）。
Windows ネイティブでは sandbox が無効で、chmod は読み取り専用属性だけ。**最後の砦は GitHub 側の main のブランチ保護**（`docs/SETUP.md`）。
ゲートの目的は「うっかり」と「無人時の暴走」を止めることで、敵対的な回避を止めることではない。

## 3. 成果物の保護（hooks）

`data/raw` への書き込み・削除（搬入は `raw_write` の委任があれば移動だけ可）、`runs/` の削除・権限変更、`lab.toml` の編集（`lab_toml` の委任があれば可）、
`.lab/` の直接編集、`git clean -x`、`git checkout -- data/raw`、`layout.writable` 以外への Write、描画ライブラリ・pickle の import を止める。
いずれも成果物（原本・run・規約・状態）を壊す操作であり、作業の手順は縛らない。

## 4. 独立レビュー

`lab-reviewer` agent がレビューし、`docs/reviews/YYYY-MM-DD_<flow>_<段階>.md` に frontmatter（reviewer, flow, stage, commit, verdict, findings）付きで保存する。
`docs/reviews/` は hook 入力の `agent_type` が lab-reviewer のときだけ書ける（自己採点の防止）。lab-reviewer の Bash は読み取りの許可リストだけ。
migrate の reproduce 段階は、現在の HEAD に対する verdict=pass の記録が無いと進めない。

## 5. 手順のチェックリスト（labkit flow）

定義は `labkit/flows/migrate.toml`。段階ごとの完了条件（clean tree、タグ、写し、CSV、lab.toml の mode、MANIFEST、check、run、レビュー）を
`labkit flow advance` が機械的に検査する。**段階による操作の禁止はしない**（v0.3 の forbid は守られず、記録だけが矛盾した）。
承認が要る段階（inventory）はカテゴリ `flow` の委任（`labkit approve` / `labkit delegate flow`）で進む。
freeze 段階は `labkit mirror push` 済みであることを要求する（配置替えの途中でデータを失わないため）。

## 6. 正本の写し（labkit mirror）

`runs/` と `data/` は git 管理外なので、`configs/paths/<LAB_ENV>.toml` の `mirror_root` に `labkit mirror push` で差分コピーする
（size と mtime で比較、`--verify` で sha256。削除はしない）。写し先には `MIRROR.json`、手元には `.lab/mirror.json`。
外部ツール不要で、NAS・外付け・クラウドドライブのマウントに使える。

## 7. 文脈への注入

SessionStart（compact 含む）: 今日の開発ログの有無、承認ゲートの 1 行、無効のままの関門（`require_prediction` / `require_clean`）、
goal/beat の現行の版と最後の拍の判断（`prompts/current.toml`）、DIGEST の古さ、有効な委任、承認待ち・質問・却下、進行中の flow、plugin と labkit の版の不一致。
compact 後はさらに、目標ファイルの最初の節を原文で再注入する（要約で薄れた指示を戻す）。
UserPromptSubmit: 人間の操作で生じた差分（承認済み・回答あり・却下）だけ。何も無ければ 0 行。

## 8. 人間の入口（DIGEST・台帳・一覧）

人間は devlog 600 行を読まない。読むのは機械が同じコードで作る短い生成物だけ:

| 入口 | 作るもの | 中身 |
|---|---|---|
| `labkit digest [--since]` | `docs/DIGEST.md` 1 枚（1 日 1 回、人間が読む前に。SessionStart が古さを知らせる） | 主張の変化、予想と結果、run の収支、新しい図（`docs/assets/digest/` に写してリンク）、未解消のレビュー、承認待ち・質問、check の集計、文献の追加と読書キュー、変更された文書とコード量。材料がある節だけ出す |
| `labkit claim list` | 主張の台帳 `docs/claims.md` | 何を主張し（根拠は `labkit cite` の書式）、何を撤回したか（理由つき）。根拠が崩れると L036 |
| `labkit runs list` / `runs table <name>` | run の一覧・同名の表の連結 | 退避済みは既定で隠す（`--all`）。table は clean な finished だけを連結し、除外した run と理由を出す |
| `labkit review list [--open]` | レビュー記録 1 件 1 行 | `summary`（120 字以内）、must/should の件数、`resolves` の鎖。`--open` は後続の pass が無い changes-requested |
| `labkit beat log` / `lit queue` / `lit surveys` | 拍の 3 行 / 人間の読書キュー / サーベイの判定 | エージェントが何を考え（予想・結果・判断）、何を読んだか（`read_by`・`claims`・`verdict`・`n_opened`） |

生成物の元は台帳・meta.json・frontmatter なので、エージェントが文章で盛ることはできない（盛るには run か台帳を変える必要があり、check が見る）。

## 9. 1 拍（current.toml と beat）

長い自律運用（/goal・/loop）で指示が薄れないよう、現行の目標と指示書の版を `prompts/current.toml`（goal / beat / interval）に機械が持つ。
`labkit beat start` がその本文と状態（今日の run・回答・open な主張・前の拍の判断）を出し、`labkit beat end --predicted --observed --decided [--runs]` が
拍の 3 行を `.lab/beats/日付.jsonl` に記録して開発ログの自動ブロック「拍（自動）」に写す（時刻は機械が入れる）。`/loop 20m /lab-rules:beat`（skill `beat`）で回す。
L005 は current が指す版が無い・より新しい版があるときに知らせる。目標の改訂は版を上げて current を更新する（過去の拍が使った版を残す）。

## 後方互換

- v0.x のプロジェクトの `lab.toml` はそのまま読める（無くなったキー `cite_bare_numbers`・`presence`・`[runs] hash_inputs_max_gb` は無視）。
- `.lab/approvals/`・`.lab/presence` は使わない（残っていても害は無い）。承認は `.lab/delegations.json` に記録される。
- v0.x の run の meta.json は新しい schema でも通る（追加フィールドはすべて任意）。
- v1.5.0 で足した検査はすべて警告か opt-in: L005・L018・L023・L024・L038・L047・L048 と dirty の引用は warn、`require_clean` は既定 false（雛形だけ true）。
  error になるのは L036（`docs/claims.md` の台帳の構造）と L037（`docs/state.md` の H1・H2 の重複）だけで、どちらもファイルが無ければ何も出ない。
  `prompts/current.toml` が無ければ `labkit beat` は使えないが、他は変わらない。`prediction` の文字列（自由記述）は引き続き受け付ける。
