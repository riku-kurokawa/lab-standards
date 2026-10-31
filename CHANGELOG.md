# Changelog

## v0.2.0 — 2026-10-30

プロジェクトで作業しながら本体を改良し、そのプロジェクトへ反映するフローを追加。

### 追加
- `labkit standards status | link | unlink --to vX.Y.Z | template --ref <ref>`:
  プロジェクトの labkit / LabKit.jl を手元の本体チェックアウト（`$LAB_STANDARDS_DEV` か `~/dev/lab-standards`）に
  つなぎ替える（link）／リリースタグに戻す（unlink）／`copier update` で雛形を取り込む（template）
- `labkit check` L050: link したままの状態を違反にする（pre-commit で commit を止める。作業終了時の hook では止めない）
- `labkit check --ignore <codes>`
- run の `meta.json` に `labkit_source`（release / link、link なら本体の commit と dirty）を記録（Python・Julia）
- skill `improve-standards`（振り分け → ブランチ → link → 改良と試用 → リリース → unlink と取り込み）
- 本体用 `CLAUDE.md`（メンテナンス規約）、`tools/release.py`（版の一括更新と整合性検査）
- SessionStart hook: link 中であることと improve-standards の存在を文脈に入れる

### 移行（v0.1.0 のプロジェクト）
```bash
uv run labkit standards unlink --to v0.2.0 && git commit -am "lab-standards v0.2.0"
uv run labkit standards template --ref v0.2.0
```
v0.1.0 の labkit には `standards` コマンドが無いので、初回だけ `pyproject.toml` と `jl/Project.toml` のタグを手で
`v0.2.0` に書き換えて `uv sync` してもよい。

## v0.1.0 — 2026-10-30

初版。

- labkit（Python）/ LabKit.jl（Julia）: 設定（TOML + extends）、run 管理、HDF5/Parquet の保存と来歴サイドカー、環境別パス
- labkit CLI: check, fig（8 テンプレート）, raw freeze/verify, devlog, adr, lit, runs, mlflow sync/ui, paths
- copier テンプレート: ディレクトリ構造、lab.toml、CLAUDE.md、Makefile、pre-commit、HPC ジョブ雛形、文献管理
- Claude Code plugin（lab-rules）: パス保護・Bash 保護・自動整形・終了時チェック・compact 後の規約再注入、10 skills、レビュー agent

### 既知の制限

- Zarr の `save()` は未対応（v0.2 予定）。`writer()` で包めば保存・来歴記録は可能
- 図は Python（matplotlib）で描画。Julia からは `LabKit.fig()` が labkit CLI を呼ぶ
