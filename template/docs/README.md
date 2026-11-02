# docs/

| パス | 中身 | 作り方 |
|---|---|---|
| `devlog/YYYY-MM-DD.md` | 開発ログ（1 日 1 ファイル。変更ファイルと run は自動、判断は人が書く） | `labkit devlog` |
| `decisions/NNNN-slug.md` | ADR（設計判断の記録） | `labkit adr "タイトル" --slug english-slug` |
| `reviews/YYYY-MM-DD_<flow>_<段階>.md` | 独立レビューの記録（frontmatter に commit と verdict） | lab-reviewer agent（`labkit review template`） |
| `data-dictionary.md` | 変数・列の意味と単位 | 手で更新 |
| `assets/` | 文書用の画像（模式図など、データ由来でないもの） | 手で配置 |

データ由来の図は `runs/<run_id>/figures/` に `labkit fig` で出力し、ここには置かない。
