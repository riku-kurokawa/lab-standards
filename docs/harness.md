# ハーネス: 成果物を検証し、取り返しのつかない操作だけを止める（v1.0.0）

目的は「人間が不在でも Claude が止まらず、研究記録が検証可能で、取り返しのつかない操作はしない」こと。
v0.3/v0.4 は入力側（Claude が打つコマンド）の統制に投資し、実運用で迂回され、迂回のたびに記録が歪んだ（`docs/audit-2026-11-02.md`）。
v1.0.0 は成果物側（run・データ・文書が検証できるか）に軸を移し、統制は最小にした。

```
人間                          Claude Code                       .lab/（プロジェクト直下）
labkit approve Q001  ──→  delegations.json  ←── labkit hook が照合 ──  git push origin main
labkit answer Q002   ──→  queue/Q002.json   ←── SessionStart / UserPromptSubmit が文脈へ
                          flows/migrate.json ←── labkit flow start/advance（チェックリスト）
                          mirror.json        ←── labkit mirror push（正本の写し）
docs/reviews/*.md    ←── lab-reviewer agent だけが書く（agent_type で判定）
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
| 数値の主張 | `12.3 dB [run:<id>:<key>]` が runs/ の `metrics.json` と一致（L032/L033）。「結果・観察」節の小数に引用が無ければ警告（L034） |

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

SessionStart（compact 含む）: 今日の開発ログの有無、承認ゲートの 1 行、有効な委任、承認待ち・質問・却下、進行中の flow、plugin と labkit の版の不一致。
UserPromptSubmit: 人間の操作で生じた差分（承認済み・回答あり・却下）だけ。何も無ければ 0 行。

## 後方互換

- v0.x のプロジェクトの `lab.toml` はそのまま読める（無くなったキー `cite_bare_numbers`・`presence`・`[runs] hash_inputs_max_gb` は無視）。
- `.lab/approvals/`・`.lab/presence` は使わない（残っていても害は無い）。承認は `.lab/delegations.json` に記録される。
- v0.x の run の meta.json は新しい schema でも通る（追加フィールドはすべて任意）。
