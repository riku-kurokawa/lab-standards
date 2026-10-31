---
name: improve-standards
description: プロジェクトで作業中に、lab-standards 本体（雛形・labkit/LabKit.jl・図テンプレート・check のルール・hooks・skills）を改良したくなったときの手順。本体を同じセッションで直し、link で試し、リリースしてからプロジェクトに取り込む。
---

# lab-standards 本体を改良してプロジェクトに反映する

プロジェクトの中のコピーは直さない。本体（既定 `~/dev/lab-standards`、環境変数 `LAB_STANDARDS_DEV`）を直し、
タグを打ってからプロジェクトに取り込む。各ステップで人間の確認が要る箇所は **【確認】** と書いた。

## ① 振り分け

| ケース | 対応 |
|---|---|
| このプロジェクトだけの事情（特定ファイルだけ pickle を許す、一時的にチェックを外す） | 本体は直さない。`lab.toml` の `format_allowed` / `plot_import_allowed` / `skip` の変更案を人間に提示して終わり（lab.toml は人間が編集） |
| 他のプロジェクトでも役立つ（新しい図テンプレート、check の改善、新しい skill、雛形の改善） | ②へ |
| 判断がつかない | 人間に尋ねる |

**【確認】** 改良の内容（何を・なぜ・どの部品か）を 3〜5 行で示し、進めてよいか確認する。

## ② 本体を作業対象に加え、ブランチを切る

1. 人間に `/add-dir ~/dev/lab-standards`（実際のパス）の実行を依頼する。
2. 本体の `CLAUDE.md`（メンテナンス規約）を読む。
3. 本体で作業ブランチを作る:
   ```bash
   git -C ~/dev/lab-standards switch main && git -C ~/dev/lab-standards pull --ff-only
   git -C ~/dev/lab-standards switch -c feat/<短い名前>
   ```
4. 開発ログに「lab-standards 改良開始: feat/<名前>（理由）」と書く。

## ③ link（プロジェクトが手元の本体を参照するようにする）

labkit / LabKit.jl / 図テンプレート / check を変えるときに行う。hooks・skills だけの変更なら不要
（手元の本体を marketplace に登録していれば、Claude Code の再起動で反映される）。

```bash
uv run labkit standards link            # --path で場所を指定可
uv run labkit standards status
```
link 中は `labkit check` が L050 を出し、commit できない（作業終了時のチェックでは止めない）。
link 中の run の meta.json には `labkit_source.mode = "link"` が記録される。

## ④ 本体を直し、プロジェクトで試す

- 本体の `CLAUDE.md` の規約（テスト、後方互換、CHANGELOG）に従って本体を直す。
- プロジェクトで実際に使って確かめる（例: 新しい図テンプレートで図を出し、png を確認する）。
- 本体のテストを書き、通す:
  ```bash
  cd ~/dev/lab-standards
  (cd labkit/python && uv run --extra dev pytest -q)
  uv run --with pytest pytest -q claude-plugin/tests
  ```
- **雛形（template/）を変えた場合**: プロジェクトには ⑥ で正式に取り込む。ここでは本体のブランチを commit したうえで、
  使い捨ての場所に生成して確かめる:
  ```bash
  TRY=$(mktemp -d)/try
  uvx copier copy --defaults --vcs-ref HEAD -d project_name="try" -d author=me ~/dev/lab-standards "$TRY"
  ```
  生成物（`$TRY`）の該当ファイルを確認する（プロジェクト内には生成しない）。

## ⑤ リリース 【確認】

1. 人間に差分（`git -C ~/dev/lab-standards diff main --stat` と要点）を示し、リリースしてよいか、版をどう上げるか確認する。
   - 後方互換の追加・修正 → マイナー/パッチ（v0.2.0 → v0.3.0 / v0.2.1）
   - 互換性を壊す変更 → メジャー。本体の `docs/decisions/` に ADR を書く
2. 本体で:
   ```bash
   python tools/release.py X.Y.Z          # 全ファイルの版を更新し、CHANGELOG と整合性を検査
   git add -A && git commit -m "release vX.Y.Z: <要約>"
   git switch main && git merge --ff-only feat/<名前>   # または PR を作ってマージ
   git tag vX.Y.Z && git push origin main --tags
   ```
   push は人間の承認を得てから行う。

## ⑥ プロジェクトをリリース版に戻し、取り込む

```bash
uv run labkit standards unlink --to vX.Y.Z      # labkit / LabKit.jl をタグ参照に戻して同期
uv run labkit check                             # L050 が消えたことを確認
git add -A && git commit -m "lab-standards vX.Y.Z に更新"
uv run labkit standards template --ref vX.Y.Z   # 雛形の差分を取り込む（衝突は人間と解消）
git add -A && git commit -m "雛形を lab-standards vX.Y.Z に追従"
```
hooks・skills を変えた場合、他の PC では `/plugin marketplace update lab-standards` が必要と人間に伝える。
開発ログに「lab-standards vX.Y.Z に更新（変更点・理由）」と書き、本体の作業ブランチを削除する。

## 他のプロジェクト

自動では更新しない。各プロジェクトの都合のよいときに ⑥ と同じ手順で取り込む
（`labkit standards unlink --to vX.Y.Z` は link していなくても「参照タグの更新」として使える）。
