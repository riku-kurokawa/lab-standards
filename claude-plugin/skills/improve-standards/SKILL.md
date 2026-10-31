---
name: improve-standards
description: プロジェクトで作業中に、lab-standards 本体（雛形・labkit/LabKit.jl・図テンプレート・check のルール・hooks・skills）を改良したくなったときの手順。`labkit flow start improve-standards` で状態機械を開始し、振り分け→承認→ブランチ→実装（必要なら link）→テスト→レビュー→リリース（承認）→取り込み、と進める。
---

# lab-standards 本体を改良してプロジェクトに反映する

プロジェクトの中のコピーは直さない。本体（既定 `~/dev/lab-standards`、環境変数 `LAB_STANDARDS_DEV`）を直し、
タグを打ってからプロジェクトに取り込む。手順は `labkit flow`（状態は**プロジェクト側**の `.lab/flows/improve-standards.json`）。

```bash
uv run labkit flow start improve-standards
uv run labkit flow status
uv run labkit flow advance
```

## 段階

| 段階 | やること | 完了条件 | 禁止 |
|---|---|---|---|
| triage | 振り分け（下表）。共通の改良なら、内容（何を・なぜ・どの部品か）を 3〜5 行で今日の開発ログに書く | 今日の開発ログがある **+ 人間の承認** | link, template, release, raw |
| branch | 人間に `/add-dir ~/dev/lab-standards` を依頼（無くても本体のパスを直接指定して進める）。本体の `CLAUDE.md` を読む。本体で `git switch -c feat/<短い名前>`（`git -C` は使わず、本体に cd して実行） | 本体のブランチが `feat/*` | link, template, release, raw |
| implement | 本体を直す（テスト・後方互換・CHANGELOG は本体の CLAUDE.md）。labkit / LabKit.jl / 図テンプレート / check を変えるなら `uv run labkit standards link` でこのプロジェクトから試す（hooks・skills・雛形だけなら不要。labkit/ を触ったのに link が無いと advance が止める）。本体に commit を積む。雛形を変えたら使い捨ての場所に `copier copy --vcs-ref HEAD` で生成して確認（プロジェクト内には生成しない） | 本体のブランチが main より進んでいる + labkit/ を変えたなら link 状態 | template, release, raw |
| test | 本体のテストを通す（labkit・hooks、Julia を変えたら Julia も）。**Agent ツールで lab-reviewer を起動**し、本体の差分のレビュー記録をプロジェクトの `docs/reviews/` に書かせる | 本体のテストが通る **+ 本体の HEAD に対する pass のレビュー記録**（`labkit review template improve-standards test` が本体の HEAD を入れる） | template, release, raw |
| release | 本体の CHANGELOG に `## vX.Y.Z` の節を書き、`python tools/release.py X.Y.Z`、commit。人間の承認後に `git switch main && git merge --ff-only feat/<名前>`、`git tag vX.Y.Z`、`git push origin main --tags`（merge・tag・push は承認ゲートの対象。away なら承認待ちに積まれるので、コマンドを提示して待つ） | 本体の版のタグが origin にある **+ 人間の承認** | template, raw |
| adopt | `uv run labkit standards unlink --to vX.Y.Z` → `labkit check` で L050 が消えたことを確認 → commit。`uv run labkit standards template --ref vX.Y.Z`（承認ゲート対象）→ 衝突を解消して commit | link 解除、`labkit check` が通る | release, raw |
| done | 開発ログに「lab-standards vX.Y.Z に更新（変更点・理由）」。他の PC では `/plugin marketplace update lab-standards` が必要と伝える | — | — |

### triage の振り分け

| ケース | 対応 |
|---|---|
| このプロジェクトだけの事情（特定ファイルだけ pickle を許す、一時的にチェックを外す） | 本体は直さない。`lab.toml` の `format_allowed` / `plot_import_allowed` / `skip` の変更案を人間に提示し、flow は `labkit flow abort` |
| 他のプロジェクトでも役立つ（新しい図テンプレート、check の改善、新しい skill、雛形の改善） | 進める |
| 判断がつかない | `labkit queue ask` に積み、「共通の改良」と仮定して進める（本体の変更は branch 上なので取り消せる） |

## 止まらないための約束

- 承認待ち（triage・release の `advance`、本体の merge/tag/push）は終了時の報告に挙げ、依存しない作業（テスト、ドキュメント、CHANGELOG の下書き）を続ける。
- レビューが changes-requested なら、指摘に対応して本体に commit → lab-reviewer を再起動 → advance。
- 版の付け方: 互換を保つ追加はマイナー、修正のみはパッチ、互換を壊すならメジャー + 本体に ADR。

## 他のプロジェクト

自動では更新しない。各プロジェクトの都合のよいときに adopt と同じ手順で取り込む
（`labkit standards unlink --to vX.Y.Z` は link していなくても「参照タグの更新」として使える）。
