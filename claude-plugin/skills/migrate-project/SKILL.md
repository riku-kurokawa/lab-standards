---
name: migrate-project
description: 既存の研究プロジェクトを lab-standards の構造に移行するときの手順。`labkit flow start migrate` でチェックリストを開始し、段階ごとに完了条件・承認・独立レビューを経て進める（写し→凍結→棚卸し→承認→雛形→生データ→コード→再現→レビュー→厳格化）。
---

# 既存プロジェクトを lab-standards に移行する

手順は `labkit flow` のチェックリストが管理する。各段階の完了条件は機械的に検査される（操作の禁止はしない。
取り返しのつかない操作は承認ゲートが別に守る）。人間が不在でも止まらない: 承認が要る段階では `advance` が承認待ちをキューに積む。
人間が最初に `labkit delegate migrate --hours 8` を宣言していれば、承認・生データの搬入・freeze・lab.toml の編集も Claude が進められる。

雛形を適用する前（freeze・inventory）はプロジェクトに labkit が無いので、本体のチェックアウトの labkit を使う:

```bash
LABKIT="uv run --project ~/dev/lab-standards/labkit/python labkit"   # 雛形適用前。apply-template で uv sync した後は `uv run labkit`
$LABKIT flow start migrate / flow status / flow advance
```

## 段階と、その段階でやること

| 段階 | やること | 完了条件（advance が検査） |
|---|---|---|
| freeze | すべて commit。`git tag pre-migration`（承認ゲート）。**git 管理外のデータを先に写す**: `$LABKIT mirror push --to <写し先> --paths results data outputs ...`（配置替えの途中でデータを失わないため） | clean tree、タグ、写し（.lab/mirror.json） |
| inventory | 読み取りのみ。`scratch/migration-inventory.csv` を作る（`old_path, kind, new_path, size, note`。kind は raw/derived/code/config/figure/doc/literature/unknown） | CSV と必須列 **+ 人間の承認** |
| apply-template | `copier copy gh:<owner>/lab-standards .` で雛形を適用。`lab.toml` の `[check] mode = "warn"`（人間か lab_toml の委任）。`uv sync` → `uv run labkit check` の違反一覧を開発ログへ | lab.toml、.copier-answers.yml、mode=warn |
| raw-data | 棚卸し表の raw を `data/raw/` へ移す（`git mv` は管理外ファイルを巻き込む。`mv` で 1 つずつ）。`uv run labkit raw freeze`（承認ゲート） | MANIFEST.sha256 がある |
| code | 再利用する関数から `src/<pkg>/` へ切り出してテスト。入口は `scripts/`、パラメータは `configs/experiments/`、絶対パスは `configs/paths/`。手を付けないものは `legacy/` に `git mv` し README に「移行対象外・参照のみ」 | `labkit check` が通る（L050/L002/L003 は除く） |
| reproduce | 主要な結果を新パイプラインで生データから再生成し、旧結果と数値で比較（許容誤差を明記）。開発ログと ADR に `labkit cite` の書式で残す。**Agent ツールで lab-reviewer を起動**し、レビュー記録を書かせる | finished の run が 1 件以上 **+ 現在の HEAD に対する pass のレビュー記録** |
| strict | 違反が 0 なら mode を `"strict"` に戻す | mode=strict、`labkit check` が通る |
| done | 旧派生データの削除を人間に提案。来歴不明な旧結果は `legacy/outputs/` へ移し「来歴不明・引用禁止」と書く | — |

## レビューが changes-requested だったら

1. 指摘に対応して commit する（HEAD が変わる）。
2. もう一度 lab-reviewer を起動してレビュー記録を書かせる。
3. `labkit flow advance`。3 回繰り返しても pass しないときは、状況を `labkit queue ask` と開発ログに書いて止める。

## 止まらないための約束

- 承認待ち（`labkit flow advance` や `git tag` が返す ID）は終了時の報告に挙げ、他の段階の準備（ドキュメント、テスト、scratch での下書き）を続ける。
- 人間に判断を仰ぐ事項は `labkit queue ask` に積み、仮の判断で進む。
