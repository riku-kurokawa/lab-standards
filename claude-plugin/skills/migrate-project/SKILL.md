---
name: migrate-project
description: 既存の研究プロジェクトを lab-standards の構造に移行するときの段階的な手順（凍結→棚卸し→生データ確定→雛形適用→コード移行→再現確認→厳格化）。
---

# 既存プロジェクトを lab-standards に移行する

各段階の終わりで人間の確認を取る。一度に全部やらない。

## 0. 凍結
- すべてを commit し、`git tag pre-migration` を打つ。git 管理外の大きなデータのバックアップ有無を人間に確認する。

## 1. 棚卸し（読み取りのみ）
- ファイルをすべて調べ、`scratch/migration-inventory.csv` を作る:
  `old_path, kind(raw|derived|code|config|figure|doc|literature|unknown), new_path, size, note`
- 判定基準: 取得したままのデータ → raw、スクリプトの出力 → derived、手作り図 → figure（テンプレートで作り直す候補）。
- 判断がつかないものは unknown にして理由を note に書く。**この表を人間がレビューするまで先に進まない。**

## 2. 雛形の適用
- 人間がプロジェクトのルートで `copier copy gh:<owner>/lab-standards .` を実行する（既存ファイルとの衝突は人間が判断）。
- `lab.toml` の `[check] mode = "warn"` にしてもらう（移行中は違反を表示するだけ）。
- `uv sync` → `uv run labkit check` で違反一覧を出し、開発ログに記録する。

## 3. 生データの確定
- 棚卸し表の raw を `git mv`（管理外なら `mv`）で `data/raw/` へ移す。移動は人間の承認後に Claude が行ってよいが、data/raw 内では hooks が止めるので、移動コマンドは人間に提示して実行してもらう。
- 人間が `uv run labkit raw freeze` を実行する。

## 4. コードの移行
- 再利用する関数から順に `src/<pkg>/` に切り出し、テストを書く。I/O は scripts 側に残す。
- 入口スクリプトは `scripts/` に移し、パラメータを `configs/experiments/*.toml` に、絶対パスを `configs/paths/*.toml` に出す。
- 手を付けないスクリプトは `legacy/` に `git mv` し、`legacy/README.md` に「移行対象外・参照のみ」と書く（legacy はチェック対象外・読み取り専用）。
- 手作りの図は、対応する figspec を作ってテンプレートで再生成する。

## 5. 再現確認
- 主要な結果を新しいパイプラインで生データから再生成し、旧結果と数値で比較する（許容誤差を明記）。比較結果を開発ログと ADR に残す。
- 一致を確認したら、旧派生データの削除を人間に提案する。来歴が不明な旧結果は `legacy/outputs/` に移し、README に「来歴不明・引用禁止」と書く。

## 6. 厳格化
- 違反が 0 になったら、人間に `lab.toml` の mode を `"strict"` に戻してもらう。
