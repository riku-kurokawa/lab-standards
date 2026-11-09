# セットアップ（別の PC / 新しいプロジェクト）

macOS / Linux / WSL2 / Windows ネイティブ。Windows では sandbox が無効で hooks（テキスト照合）だけの保護になる（`docs/harness.md`）。

## 0. 前提ツール

```bash
git --version
gh --version && gh auth login && gh auth setup-git   # GitHub CLI（git が gh の認証を使う）
curl -LsSf https://astral.sh/uv/install.sh | sh      # uv（Python 環境管理）
uv tool install copier                               # 雛形ツール
python3 --version                                    # hooks の入口用。3.11 以上。無ければ: uv python install 3.12 --default
make --version                                       # GNU make。Windows ネイティブは `winget install ezwinports.make`、Git Bash から実行
```

Windows ネイティブでは Python の既定の文字コードがコンソールのコードページ（cp932）になる。雛形の `.claude/settings.json` の `env` に
`PYTHONUTF8=1` が入っているので Claude Code のセッション内は既定で有効。自分の端末でも使うならユーザー環境変数にも設定する:

```powershell
[Environment]::SetEnvironmentVariable('PYTHONUTF8', '1', 'User')
```

## 1. 本体を手元に置く

```bash
git clone https://github.com/riku-kurokawa/lab-standards.git ~/dev/lab-standards
```

`~/dev/lab-standards` が本体を編集する場所（`labkit standards link`、skill improve-standards が参照する）。別の場所なら `export LAB_STANDARDS_DEV=/path`。

## 2. Claude Code に plugin を登録する

```
/plugin marketplace add riku-kurokawa/lab-standards
/plugin install lab-rules@lab-standards
```

plugin は `lab.toml` のあるプロジェクトと本体でだけ動く。判定は各プロジェクトの venv の labkit が行うので、新しい版を出したら
`/plugin marketplace update lab-standards` と各プロジェクトの `labkit standards unlink --to vX.Y.Z` の両方を行う（SessionStart が不一致を知らせる）。

## 3. GitHub 側の保護（最後の砦）

hooks は security boundary ではない。main への force push と削除、`v*` タグの付け替えと削除を ruleset で禁止する（公開リポジトリは無料。所有者にも適用される）:

```bash
gh api -X POST repos/<owner>/<repo>/rulesets --input - <<'JSON'
{"name":"protect-main","target":"branch","enforcement":"active","conditions":{"ref_name":{"include":["refs/heads/main"],"exclude":[]}},"rules":[{"type":"deletion"},{"type":"non_fast_forward"}]}
JSON
gh api -X POST repos/<owner>/<repo>/rulesets --input - <<'JSON'
{"name":"protect-release-tags","target":"tag","enforcement":"active","conditions":{"ref_name":{"include":["refs/tags/v*"],"exclude":[]}},"rules":[{"type":"deletion"},{"type":"update"}]}
JSON
```

## 4. 人間がすること（完全自律）

Claude は承認を待たない（v2.0.0 で承認・却下・回答・委任を廃止）。人間がするのは、目標と主線を渡し、短い生成物を読むことだけ:

```bash
uv run labkit main set "<主線を 1 文で>"                                   # Claude に頼んでもよい
uv run labkit main add "<成果物>" --done "<完了条件>" --due "YYYY-MM-DD HH:MM"
uv run labkit digest && less docs/DIGEST.md                                # 1 日 1 回
uv run labkit queue list                                                   # Claude からの連絡（決めたことと理由）
```

連絡への返事は会話か目標ファイル（`prompts/`）で伝える。規約（`lab.toml`）を変えるのは人間。

## 5. 正本の写し

`configs/paths/local.toml` の `mirror_root` に NAS・外付け・クラウドドライブのマウント先を書き、節目で `uv run labkit mirror push`。
機械が壊れても `runs/` と `data/` が残る。

## 6. 動作確認

README の「新しいプロジェクトを作る」を実行し、最後に `uv run labkit standards status` が release の同じタグになっていることを確かめる。
