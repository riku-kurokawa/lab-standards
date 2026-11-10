---
name: migrate-project
description: 既存の研究プロジェクトを lab-standards の構造に移行するときの手順。`labkit flow start migrate` でチェックリストを開始し、段階ごとに完了条件と独立レビューを経て進める（写し→凍結→棚卸し→雛形→生データ→コード→再現→レビュー→厳格化）。
disable-model-invocation: true
---

# 既存プロジェクトを lab-standards に移行する

手順は `labkit flow` のチェックリストが管理する。各段階の完了条件は機械的に検査される。完全自律（v2.0.0）: 人間の承認を待つ段階は無い。
タグ・生データの搬入（上書きしない cp / mv）・freeze も Claude が行う。lab.toml は apply-template と strict の段階のあいだだけ書ける（hooks）。

雛形を適用する前（freeze・inventory）はプロジェクトに labkit が無いので、本体のチェックアウトの labkit を使う:

```bash
LABKIT="uv run --project ~/dev/lab-standards/labkit/python labkit"   # 雛形適用前。apply-template で uv sync した後は `uv run labkit`
$LABKIT flow start migrate / flow status / flow advance
```

## 段階と、その段階でやること

| 段階 | やること | 完了条件（advance が検査） |
|---|---|---|
| freeze | すべて commit。`git tag pre-migration`。**git 管理外のデータを先に写す**: `$LABKIT mirror push --to <写し先> --paths results data outputs ...`（配置替えの途中でデータを失わないため） | clean tree、タグ、写し（.lab/mirror.json） |
| inventory | 読み取りのみ。`scratch/migration-inventory.csv` を作る（`old_path, kind, new_path, size, note`。kind は raw/derived/code/config/figure/doc/literature/unknown） | CSV と必須列 |
| apply-template | `copier copy gh:<owner>/lab-standards .` で雛形を適用。`lab.toml` の `[check] mode = "warn"`（この段階のあいだだけ書ける）。`uv sync` → `uv run labkit check` の違反一覧を開発ログへ | lab.toml、.copier-answers.yml、mode=warn |
| raw-data | 棚卸し表の raw を `data/raw/` へ移す（`git mv` は管理外ファイルを巻き込む。`mv` で 1 つずつ、上書きしない）。`uv run labkit raw freeze` | MANIFEST.sha256 がある |
| code | 再利用する関数から `src/<pkg>/` へ切り出してテスト。入口は `scripts/`、パラメータは `configs/experiments/`、絶対パスは `configs/paths/`。手を付けないものは `legacy/` に `git mv` し README に「移行対象外・参照のみ」 | `labkit check` が通る（L050/L002/L003 は除く） |
| reproduce | 主要な結果を新パイプラインで生データから再生成し、旧結果と数値で比較（許容誤差を明記）。開発ログと ADR に `labkit cite` の書式で残す。**Agent ツールで lab-reviewer を起動**し、レビュー記録を書かせる | finished の run が 1 件以上 **+ 現在の HEAD に対する pass のレビュー記録** |
| strict | 違反が 0 なら mode を `"strict"` に戻す | mode=strict、`labkit check` が通る |
| done | 旧派生データの削除を人間に提案。来歴不明な旧結果は `legacy/outputs/` へ移し「来歴不明・引用禁止」と書く | — |

## レビューが changes-requested だったら

1. 指摘に対応して commit する（HEAD が変わる）。
2. もう一度 lab-reviewer を起動してレビュー記録を書かせる。
3. `labkit flow advance`。3 回繰り返しても pass しないときは、状況を `labkit queue ask` と開発ログに書いて止める。

## 止まらないための約束

- 判断の分かれる事項は自分で決めて根拠を残し、`labkit queue ask` で人間に知らせて進む（返事は待たない）。
