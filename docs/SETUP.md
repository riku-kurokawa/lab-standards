# セットアップ（別の PC / 新しいプロジェクト）

macOS / Linux（Windows は WSL2 推奨。ネイティブでも動くがサンドボックスは無効）。所要 20〜30 分（Julia のパッケージ取得を含む）。
本体のリリース手順（版の更新・タグ・push）は `CLAUDE.md`。

## 0. 前提ツール

```bash
git --version                     # git
gh --version || echo "GitHub CLI が必要: https://cli.github.com/"
gh auth login                     # 初回のみ。HTTPS + ブラウザ認証でよい
gh auth setup-git                 # git が gh の認証を使うようにする（非公開 repo の取得に必要）

curl -LsSf https://astral.sh/uv/install.sh | sh     # uv（Python 環境管理）
uv tool install copier                              # 雛形ツール
python3 --version                                   # hooks 用。3.11 以上。無い／古いなら: uv python install 3.12 --default（python3 の実行ファイルを ~/.local/bin に置く）
curl -fsSL https://install.julialang.org | sh       # juliaup（Julia 1.11 以上）
```

`MLFLOW_DISABLE_TELEMETRY=true` と `DO_NOT_TRACK=true` をシェルの起動ファイル（`~/.zshrc` など）にも書いておくとより確実:

```bash
echo 'export MLFLOW_DISABLE_TELEMETRY=true DO_NOT_TRACK=true' >> ~/.zshrc
```

## 1. 本体を手元に置く

```bash
git clone https://github.com/riku-kurokawa/lab-standards.git ~/dev/lab-standards
```

`~/dev/lab-standards` が本体を編集する唯一の場所になる（`labkit standards link`、flow improve-standards、skill が参照する）。
別の場所に置くなら `export LAB_STANDARDS_DEV=/path/to/lab-standards` を起動ファイルに書く。

## 2. Claude Code に plugin を登録する

自分の PC では**手元のパス**から登録する（本体の hooks・skills の編集が再起動後すぐ効く）。Claude Code の中で:

```
/plugin marketplace add ~/dev/lab-standards
/plugin install lab-rules@lab-standards
```

他の PC（HPC のログインノードなど）で使う場合は `/plugin marketplace add riku-kurokawa/lab-standards`。
plugin は `lab.toml` のあるプロジェクトと lab-standards 本体でだけ動き、他のディレクトリでは何もしない。

## 3. 承認ゲートの使い方

Claude が `git push` / `git tag` / main への merge / `labkit raw freeze` / `copier` を実行しようとすると hooks が止め、
承認待ちとして `.lab/queue/` に記録する（既定 `presence=away`）。戻ったら:

```bash
uv run labkit queue list              # 承認待ち・質問・却下の一覧（ID、コマンド全文、HEAD、理由、記録時点の差分）
uv run labkit approve Q001            # 対話端末なら ID の再入力を求める。24 時間・1 回限り・同じ HEAD にのみ有効
uv run labkit reject Q001 --note "理由"
uv run labkit answer Q002 "lz4 で"     # 質問への回答（Claude は次の入力で受け取る）
uv run labkit presence here           # 在席中は拒否ではなく通常の確認画面にする
```

Claude Code の `!` 実行（`! uv run labkit approve Q001 --yes`）でも承認できる。
**GitHub 側で main のブランチ保護（直接 push 禁止・PR 必須）を設定しておく**ことを強く勧める（hooks は security boundary ではない）。

サンドボックス（雛形の `.claude/settings.json` の `sandbox`）は macOS / Linux / WSL2 で有効。Linux と WSL2 では
`bubblewrap` と `socat` が必要。Windows ネイティブでは無効（hooks と chmod のみ）。詳細は `docs/harness.md`。

## 4. 動作確認

README の「新しいプロジェクトを作る」を実行し、最後に:

```bash
uv run labkit standards status          # Python・Julia とも release の同じタグになっていること
uv run labkit presence status           # away（既定）
```
