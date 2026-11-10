# 1 拍の指示書 v1（`/loop 20m /lab-rules:beat` か `/loop 20m labkit beat start を実行し、その 1 拍を回せ` で再注入する）

1 拍 = `labkit beat start`（状態と、この目標・指示書の本文が出る）→ 下の 6 手 → `labkit beat end`。前の拍の作業が途中ならそれを続けてから。人間を待たない。

1. **状態を取る（短く）**: start の出力（主線の残り時間・主線の割合・芽・資源の使い道・終わった run・open な主張）と docs/backlog.md の先頭 3 件。
   主線の項目が期限に近いなら、この拍は主線だけ。資源が主線に使えていなければ、まずそれを正す。
   進められる項目（open）が 1 つしか無いなら、この拍のうちに次の項目を足す（出し方は目標の「尽きたときの出し方」）。人間待ちの項目は `labkit main block`。
2. **空きを埋める**: 資源が空いていれば、`[prediction]` と `serves`（どの線のためか）を書いた計算だけを `labkit run` で入れる。専門家なら分かる結果（expert_predictable）は回さず導出で確定する。
3. **考える（拍の中心）**: `labkit runs list` の 予想:miss / partial を 1 つ選び、なぜ外れたかと次の仮説を書く。hit しか無いなら、問いが易しすぎる。より大胆な問いを backlog の先頭に積む。
4. **進める**: backlog の先頭を 1 つ前進。確定した主張は `labkit claim add`、崩れた主張は `labkit claim retract`。独立な作業（一次文献・導出・執筆）はサブエージェントに並行で投げる。
5. **芽を残す**: 主線の作業中に見た外れた予想・妙な数字・別の説明がつく現象を 1 つ `labkit seed add` で残す（確かめるのは芽の枠で、最安の方法で）。
6. **記録する**: `labkit beat end --line main:Mxxx|seed:Sxxx|other --predicted "…" --observed "…" --decided "…" --runs <id>`（時刻は機械が入れる）。docs/state.md を上書き（H1 は 1 つ・150 行以内）、commit。

周期的な点検（candor-check）と `labkit digest` の頻度は CLAUDE.md と skill: autonomous-run に従う。

禁止: 計算の完了を待つだけで拍を終える / 人間の返事や保護の解除を待つだけの拍 / 進めていない項目を名指しする / 予想を書かずに run を投げる / 報告だけ書いて何も前進させずに終える / scratch のファイルを根拠にする。

## 当面の焦点
<!-- 目標の中で今いちばん効く問いを 2〜3 行で。焦点が変わったら beat_v2.md を作り prompts/current.toml を更新する -->
