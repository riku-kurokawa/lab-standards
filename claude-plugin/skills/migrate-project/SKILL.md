---
name: migrate-project
description: 既存の研究プロジェクトを lab-standards の構造に移行するときの手順。`labkit flow start migrate` で状態機械を開始し、段階ごとに完了条件・承認・独立レビューを経て進める（凍結→棚卸し→承認→雛形→生データ→コード→再現→レビュー→厳格化）。
---

# 既存プロジェクトを lab-standards に移行する

手順は状態機械 `labkit flow` が管理する。各段階の完了条件は機械的に検査され、禁止操作は hooks が止める。
人間が不在でも止まらない: 承認が要る段階では `advance` が承認待ちをキューに積むので、依存しない作業を続ける。

雛形を適用する前（freeze・inventory）はプロジェクトに labkit が無いので、本体のチェックアウト（`~/dev/lab-standards`）の labkit を使う。
apply-template で `uv sync` した後は `uv run labkit ...` でよい。

```bash
LABKIT="uv run --project ~/dev/lab-standards/labkit/python labkit"   # 雛形適用前
$LABKIT flow start migrate           # 開始（.lab/flows/migrate.json に状態。git 管理。lab.toml が無くても git の最上位で動く）
$LABKIT flow status                  # 今の段階・禁止操作・未達の条件
$LABKIT flow advance                 # 条件を満たしたら次へ（承認が要る段階はキューへ）
```

## 段階と、その段階でやること

| 段階 | やること | 完了条件（advance が検査） | 禁止 |
|---|---|---|---|
| freeze | すべて commit。`git tag pre-migration`（承認ゲート: away なら承認待ち）。管理外データのバックアップ有無を `labkit queue ask` で質問 | 作業ツリーが clean、タグ pre-migration | code, experiments, raw, template, release |
| inventory | 読み取りのみ。`scratch/migration-inventory.csv` を作る（`old_path, kind, new_path, size, note`。kind は raw/derived/code/config/figure/doc/literature/unknown。迷ったら unknown + note） | CSV と必須列 **+ 人間の承認** | 同上 |
| apply-template | 人間が `copier copy gh:<owner>/lab-standards .` を実行（承認ゲート対象。コマンドを提示する）。`lab.toml` の `[check] mode = "warn"` にしてもらう。`uv sync` → `uv run labkit check` の違反一覧を開発ログへ | lab.toml、.copier-answers.yml、mode=warn | experiments, raw, release |
| raw-data | 棚卸し表の raw を `data/raw/` へ移す（移動コマンドは人間に提示。data/raw 内は hooks が止める）。人間が `uv run labkit raw freeze`（承認ゲート） | MANIFEST.sha256 がある | experiments, template, release |
| code | 再利用する関数から `src/<pkg>/` へ切り出してテスト。入口は `scripts/`、パラメータは `configs/experiments/`、絶対パスは `configs/paths/`。手を付けないものは `legacy/` に `git mv` し README に「移行対象外・参照のみ」 | `labkit check` が通る（L050/L021/L002/L003 は除く） | raw, template, release |
| reproduce | 主要な結果を新パイプラインで生データから再生成し、旧結果と数値で比較（許容誤差を明記）。開発ログと ADR に `labkit cite` の書式で残す。**Agent ツールで lab-reviewer を起動**し、レビュー記録を書かせる | finished の run が 1 件以上 **+ 現在の HEAD に対する pass のレビュー記録** | raw, template, release |
| strict | 違反が 0 なら人間に mode を `"strict"` に戻してもらう | mode=strict、`labkit check` が通る | raw, template, release |
| done | 旧派生データの削除を人間に提案。来歴不明な旧結果は `legacy/outputs/` へ移し「来歴不明・引用禁止」と書く | — | — |

## レビューが changes-requested だったら

1. レビュー記録の「要修正」に対応し、commit する（HEAD が変わる）。
2. もう一度 lab-reviewer を起動してレビュー記録を書かせる（新しい HEAD に対する記録になる）。
3. `labkit flow advance`。pass でなければ 1 に戻る。3 回繰り返しても pass しないときは、状況を `labkit queue ask` と開発ログに書いて止める。

## 止まらないための約束

- 承認待ち（`labkit flow advance` や `git tag` が返す ID）は終了時の報告に挙げ、他の段階の準備（ドキュメント、テスト、scratch での下書き）を続ける。
- 人間に判断を仰ぐ事項は `labkit queue ask` に積み、仮の判断で進む。
- hooks に「今は <段階>。先に <条件> が必要」と止められたら、`labkit flow status` を見て条件を満たす作業に切り替える。
