# docs/

| パス | 中身 | 作り方 |
|---|---|---|
| `DIGEST.md` | 人間の入口 1 枚（主張の変化・予想と結果・run の収支・新しい図・未解消のレビュー・主線と芽・資源の使い道・人間への連絡） | `labkit digest`（1 日 1 回。手で編集しない） |
| `mainline.md` | 主線（1 文）と項目（成果物・完了条件・期限・状態・根拠） | `labkit main set / add / done` |
| `seeds.md` | 芽の台帳（出どころ・最安の確かめ方・当たれば・状態） | `labkit seed add / decide` |
| `claims.md` | 主張の台帳（根拠の run・状態 open/retracted。根拠が崩れると L036） | `labkit claim add / retract` |
| `state.md` | 今の状態（前提・点検・乗り換え・次の一手）。H1 1 つ・150 行以内 | 拍ごとに上書き |
| `backlog.md` | 未着手（目標に効く順） | 手で更新 |
| `devlog/YYYY-MM-DD.md` | 開発ログ（1 日 1 ファイル。変更ファイル・run・コード量・拍は自動、判断は人が書く） | `labkit devlog` / `labkit beat end` |
| `decisions/NNNN-slug.md` | ADR（設計判断の記録） | `labkit adr "タイトル" --slug english-slug` |
| `reviews/YYYY-MM-DD_<flow>_<段階>.md` | 独立レビューの記録（frontmatter に commit・verdict・summary） | lab-reviewer agent（`labkit review template`） |
| `prereg/<slug>.md` | 事前登録（計算の前に固定する予想・合否・殺す条件。修正は番号を付けて追記） | 手で書き、計算の前に commit |
| `papers/<slug>/` | 草稿（引用は `labkit cite` の書式。L032/L033 が照合する） | 手で書く |
| `data-dictionary.md` | 変数・列の意味と単位 | 手で更新 |
| `assets/` | 文書用の画像（模式図など）。`assets/digest/` は DIGEST が写した図 | 手で配置 / `labkit digest` |

docs/ 直下に自由な名前の md を増やさない（上の置き場所のどれかに入れる）。データ由来の図は `runs/<run_id>/figures/` に `labkit fig` で出力する。
