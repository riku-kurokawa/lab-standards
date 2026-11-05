---
name: autonomous-run
description: lab.toml のあるプロジェクトで、Claude を何時間〜何日も自走させて研究を進めるとき（/goal・/loop・長い計算の待ち）の手順。目標の置き方（prompts/current.toml）、1 拍の回し方（labkit beat）、予想の関門、ぶっちゃけ点検と採点、主張の台帳と撤回、人間の入口。
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

## 1 拍の回し方（skill: beat）
`labkit beat start`（現行の goal・beat の本文と状態が出る）→ beat ファイルの 5 手 → `labkit beat end --predicted --observed --decided [--runs]`。
5 手の正本は beat ファイルで、ここには書かない。拍の 3 行は `beat end` が `.lab/beats/` と開発ログの自動ブロックに写す（手で devlog に書き直さない）。

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

## 人間の入口（1 日 1 回）
人間が読むのは devlog ではなく `docs/DIGEST.md`。人間が読む前に 1 日 1 回 `labkit digest` で作り直す（SessionStart が古さを知らせる）。
failed/interrupted の run は `labkit runs archive --status failed,interrupted` で視界から消す。DIGEST に載る図には figspec の `labels.title` と `description` を書く。

## compact の後に戻るもの
SessionStart が goal/beat の現行の版、最後の拍の判断、目標ファイルの最初の節（原文）、承認待ち・委任・flow を再注入する。CLAUDE.md と skill は読み直される。
戻らないのは会話の途中の推論なので、判断は state.md と `beat end` の 3 行に残す。

## 範囲を縮める判断
目標の範囲を縮める・主線を変える判断は `labkit queue ask` に積み、仮の判断では範囲を保つ。決めるのは人間。
