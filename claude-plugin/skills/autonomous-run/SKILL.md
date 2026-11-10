---
name: autonomous-run
description: lab.toml のあるプロジェクトで、Claude を何時間〜何日も自走させて研究を進めるとき（/goal・/loop・長い計算の待ち）の手順。目標の置き方（prompts/current.toml）、1 拍の回し方（labkit beat）、主線と芽（主線から絶対にずれず芽を拾い続ける関門）と資源の紐付け、予想の関門、ぶっちゃけ点検と採点、主張の台帳と撤回、人間の入口。
---

# 長い自律運用

nla-solver・accelerated-diff-pat での数日間の運用で、効いたものと逆効果だったものから作った手順。

## 失敗の型（これを防ぐための手順）
- **待つ**: 計算を投げて完了を待ち、ターンを終える。通知が来るまで何もしない。
- **薄れる**: 長い会話が要約され、最初に渡した目標や規則が消える。
- **計算で確かめに行く**: 計算する前に分かる結論を、時間と資源を使って確かめる。
- **活動量に最適化する**: commit 数・行数・サーベイ本数のノルマを与えると、手は増えるが考えは増えない。
- **安全な回り道**: 主線を問い直さず、確かめやすい小さな一歩を積み続ける。当然の結論を避ける。
- **人間が読めない**: 600 行の devlog と state の積層。人間のレビュー時間がボトルネックになり、判断が止まる。
- **主線からずれる**: 新しさを追って目標の版を何度も替え、期限のある成果物が空欄のまま残る。
- **ずれないだけになる**: 主線だけを機械的に回し、外れた予想や妙な数字を拾わない。発見が生まれない。
- **資源を捨てる**: 壊れた計算を監視なしで何十本も回す。どの線のための計算か分からない run が積み上がる。

## 置き方（4 つのファイル + current.toml）
| 何 | どこ | 役割 |
|---|---|---|
| 目標 | `prompts/goal_v<N>.md` | 究極の目標、前提（計算せずに分かる結論）、合格基準の表（各 10 点）、メタ認知の問い。改訂は版を上げる |
| 1 拍の指示書 | `prompts/beat_v<N>.md` | 1 拍でやる 5 手と当面の焦点（雛形あり）。短く保つ |
| 現行の版 | `prompts/current.toml` | `goal` / `beat` / `interval`。`labkit beat` と SessionStart が読む。古い版を指すと L005 |
| 状態 | `docs/state.md` | 前提の表、ぶっちゃけ点検の表、乗り換えの記録、次の一手。毎拍、該当欄を上書き（H1 は 1 つ・同じ H2 は 1 回・150 行以内: L037） |
| 未着手 | `docs/backlog.md` | `- [ ] ...`。目標に最も効く順。前提に反する項目は理由を書いて消す |

```
/goal prompts/current.toml が指す目標を達成する。毎拍 `labkit beat start` から始める。
/loop 20m /lab-rules:beat
```
- /goal の本文はファイルを指す短い文にする（本文を貼ると要約で消える）。/loop は skill `beat` を毎回呼び直す。
- 間隔は、1 拍に新しい結果が 1 つ以上届く長さ（計算 1 本の所要時間の 1.5 倍程度）。短すぎると状態を取るだけで拍が終わる。
- 規則（予想の関門など）は CLAUDE.md に置く。ループを止めるのは人間だけ（`claude.allow_self_stop = false` の既定では hooks が CronDelete・ScheduleWakeup の stop を拒否する）。CLAUDE.md は要約の後も読まれる。

## 主線と芽
研究者が普段やっているマルチタスク（期限のある主線を追いながら、面白い芽を拾う）を台帳に残し、`labkit beat end` と `labkit run` が照合する。
止められたら、メッセージに理由と次にやることが出る。

| 何 | 仕組み（機械が止める） |
|---|---|
| 主線 | `docs/mainline.md`: 1 文（`labkit main set`）と項目（成果物・完了条件・期限。`main add`）。完了は根拠つき（`main done --evidence`） |
| 空回りしない | 進められる項目（open）が `keep_open`（既定 1）を下回る主線では、どの拍も記録されない。最後の open の項目は、次の項目を足すまで done にも blocked にもできない。人間の行為が無いと進められない項目は `main block <ID> --on <Q番号> --reason`（open に数えない。解けたら `main unblock`）。次の項目の出し方は目標の「尽きたときの出し方」 |
| 主線からずれない | 拍ごとに `beat end --line main:Mxxx\|seed:Sxxx\|other`（主線の拍は、進めた open の項目を名指しする）。直近 `main_window` 拍で主線以外が `(1-main_share)` を超える拍、期限まで `main_guard_hours` 以内（または期限切れ）の項目があるのに主線以外を進めた拍は記録されない |
| 芽を拾い続ける | `docs/seeds.md`: `labkit seed add "<芽>" --from --test --value`。`seed_every` 拍のあいだ芽が 1 つも無いと拍を閉じられない |
| 芽を育てる | 芽は主線以外の枠で、最安の方法で確かめる（`--line seed:S00N`、run は `serves = "S00N"`）。主線のどの項目に効くかを言えたら `seed decide --to promote --serves M00N`。言えなければ park か drop（理由つき） |
| 資源の紐付け | 主線に open の項目があるあいだ、run の設定に `serves` が無いと始まらない。`beat start`・digest が直近 24 時間の run 時間を線ごと・状態ごとに出す |
| 壊れた計算を回し続けない | 同じ名前の run が `fail_repeat` 回続けて failed/interrupted で commit が進んでいなければ、次は始まらない。原因を直して commit してから |

芽の良い出どころ: 予想の miss / partial、桁の合わない数字、2 つの手法で順位が入れ替わる条件、文献と食い違う点、「なぜこれが効くのか説明できない」もの。
芽の悪い出どころ: 主線が詰まったときの逃げ道、確かめ方が書けない思いつき、当たっても主線にも論文にも何も変えないもの。

## 1 拍の回し方（skill: beat）
`labkit beat start`（現行の goal・beat の本文と状態が出る）→ beat ファイルの手順 → `labkit beat end --line --predicted --observed --decided [--runs]`。
手順の正本は beat ファイルで、ここには書かない。
- 計算を投入したら同じターンで次の作業に移る。独立な作業（一次文献・導出・執筆）はサブエージェントに並行で投げる。
- メモリ不足・時間切れで止まった計算は人間の停止ではない。原因を外し（メモリとスレッドの上限を決め）、自分で再開する。
- 専門家なら計算せずに分かる結果は回さず、導出で確定として開発ログに書く。計算するのは予想が割れるときだけ。
拍の 3 行は `beat end` が `.lab/beats/` と開発ログの自動ブロックに写す（手で devlog に書き直さない）。

## 予想の関門
- run の前に、桁の見積もり・既知の理論・既存の結果から結果を数値で予想し、設定の `[prediction]`（`basis`、`confidence`、`expert_predictable`、`[[prediction.claims]]` の key と range か point+tol）に書く。
  finished 時に metrics と照合され `prediction_result`（hit/miss/partial/undeterminable）が meta.json に残る。自由記述の予想は `labkit runs verdict <id> --say ... --note` で自己申告する（L024 が判定の無い run を知らせる）。
- `lab.toml` の `runs.require_prediction = true` で予想の無い run を、`runs.require_clean = true` で dirty な run を始めない（人間が有効にする。SessionStart が無効のままなら知らせる）。
- 予想に自信があり（`expert_predictable = true`）、主張の証拠として必須でない計算は回さない。「導出で確定」として devlog に書く。
- 事前登録の修正は、結果を見る前に「amendment N（pre-computation）」として commit する。結果を見た後に基準（`[[pass]]`・range）を動かさない。

## ぶっちゃけ点検（4 拍に 1 回）と採点
`candor-check` agent を Agent ツールで起動し、目標・前提・主張（`labkit claim list`）・最新の結果の要約だけを渡す（作業の記録を渡さない）。
答え（避けている当然の結論 / 捨てるべき線 / 最も大胆な一手）を state.md の表に貼り、1 つずつ「受け入れ」か「根拠つきで退ける」を書く。受け入れた「捨てる線」は backlog から理由つきで消す。
目標の合格基準の表で採点させるときは **3 回起動して項目ごとの中央値**を取る（1 回の点は揺れる）。採点が 2 回続けて上がらなければ主線を替える。

## 主張の台帳と撤回
- 確定した主張は `labkit claim add "<1 文>" --evidence <run>:<key>[:<unit>][:<digits>] --note prereg:<slug>`。文章に書くだけでは主張にならない。
- 誤りを見つけたら `labkit claim retract C00N --reason "..."`。要旨・表・結論を直し、旧値を消さずに「撤回: 理由」と併記する。撤回は成果である。
- 根拠の run が dirty・failed・退避済みになると L036 が知らせる。clean に再実行して根拠を差し替えるか、撤回する。
- 価値は「主張を支える結果」「撤回した主張」「捨てた線」で測る。commit 数・行数・本数のノルマは置かない。

## 人間の入口
自律開発のボトルネックは人間のレビューなので、人間が読むものは短く、判断が要る順に、機械が作る。人間が読むのは devlog ではなく `docs/DIGEST.md` で、
`labkit beat end` が `digest.refresh_hours`（既定 6 時間）より古ければ作り直す（手で回す必要は無い。今すぐ作るなら `labkit digest`）。
DIGEST の先頭の「先に見るもの」に載るのは、違反・根拠の崩れた主張・撤回・期限切れ・外れた予想・新しい連絡・失敗した計算。人間に伝えたいことは、文章ではなくこれらの台帳と run に入れる。
- 主張には根拠の run を生んだコード（entry と commit）が付き、「レビューするコード」に src の変更と試験の変更の有無が載る。試験なしで src を増やすと、人間のレビューが遅くなる。
- failed/interrupted の run は `labkit runs archive --status failed,interrupted` で視界から消す。DIGEST に載る図には figspec の `labels.title` と `description` を書く。
- 警告は、主線で触るファイルから 0 に近づける。放置した警告が 100 件あると、人間は新しい 1 件に気づけない。

## compact の後に戻るもの
SessionStart が goal/beat の現行の版、最後の拍の判断、目標ファイルの最初の節（原文）、主線と芽・資源の使い道・人間への連絡・flow を再注入する。CLAUDE.md と skill は読み直される。
戻らないのは会話の途中の推論なので、判断は state.md と `beat end` の 3 行に残す。

## 範囲を縮める判断
目標の範囲を縮める・主線を変える判断は自分で行わない: 主線の項目は done（根拠つき）にするまで残る。項目を足すのは範囲の変更ではない（目標の問いの中で、残っている穴を項目にする）。範囲の変更案は `labkit queue ask` で知らせ、
その間も今の主線を進める。目標ファイルの版を替えても主線の台帳は変わらない（新しさのために主線を替えない）。
