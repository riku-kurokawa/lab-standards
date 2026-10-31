# 初期設定：GitHub への push と手元の準備

macOS / Linux（Windows は WSL）を想定。`<user>` は自分の GitHub ユーザー名に置き換える。
所要時間の目安は 20〜30 分（Julia のパッケージ取得を含む）。

## 0. 前提ツール

```bash
git --version                     # git
gh --version || echo "GitHub CLI が必要: https://cli.github.com/"
gh auth login                     # 初回のみ。HTTPS + ブラウザ認証でよい
gh auth setup-git                 # git が gh の認証を使うようにする（非公開 repo の取得に必要）

curl -LsSf https://astral.sh/uv/install.sh | sh     # uv（Python 環境管理）
uv tool install copier                              # 雛形ツール
curl -fsSL https://install.julialang.org | sh       # juliaup（Julia 1.11 以上）
```

`MLFLOW_DISABLE_TELEMETRY=true` と `DO_NOT_TRACK=true` をシェルの起動ファイル（`~/.zshrc` など）にも書いておくとより確実:

```bash
echo 'export MLFLOW_DISABLE_TELEMETRY=true DO_NOT_TRACK=true' >> ~/.zshrc
```

## 1. 決まった場所に展開する

```bash
mkdir -p ~/dev
unzip lab-standards-v0.2.0.zip -d ~/dev
cd ~/dev/lab-standards
```

ここ（`~/dev/lab-standards`）が本体を編集する唯一の場所になる。別の場所に置く場合は
`export LAB_STANDARDS_DEV=/path/to/lab-standards` を起動ファイルに書く。

## 2. 自分のリポジトリ名を入れる

```bash
perl -pi -e 's/YOUR_GITHUB/<user>/g' copier.yml
grep -n "standards_repo" -A3 copier.yml          # default: "<user>/lab-standards" になっていること
```

## 3. git に記録し、テストする

```bash
git init -b main
git add -A
git commit -m "lab-standards v0.2.0"
python3 tools/release.py --check                       # 版の整合性

(cd labkit/python && uv run --extra dev pytest -q)     # labkit（HDF5・Parquet・図を含む）
uv run --with pytest pytest -q claude-plugin/tests     # hooks
julia --project=labkit/julia/LabKit -e 'using Pkg; Pkg.instantiate(); Pkg.test()'   # LabKit.jl
```

テストが失敗したら、**タグを打つ前に**直す（Claude Code にこのディレクトリで「テストが失敗したので直して」と頼んでよい）。
初版は h5py・pyarrow・Julia を実機で動かしていないので、特に次を確認する:
- Julia の依存 UUID（`labkit/julia/LabKit/Project.toml`）。エラーなら `julia --project=labkit/julia/LabKit -e 'using Pkg; Pkg.add(["HDF5","JSON3","Parquet2","DataFrames"])'` で書き直る
- HDF5.jl の `create_dataset(...; chunk=..., deflate=...)` のキーワード名

直したら commit し、テストが通ることを確認する。

## 4. タグを打って GitHub に push する

```bash
git tag v0.2.0
gh repo create <user>/lab-standards --private --source . --remote origin --push
git push origin --tags
gh run list --limit 3          # CI（GitHub Actions）の結果。数分後に success になること
```

非公開リポジトリでよい。各プロジェクトは `gh auth setup-git` 済みの git 認証で取得する。

## 5. Claude Code に plugin を登録する

自分の PC では**手元のパス**から登録する（本体の hooks・skills の編集が再起動後すぐ効く）。Claude Code の中で:

```
/plugin marketplace add ~/dev/lab-standards
/plugin install lab-rules@lab-standards
```

他の PC（HPC のログインノードなど）で使う場合は `/plugin marketplace add <user>/lab-standards`。

## 6. 動作確認（小さなプロジェクトを 1 つ作る）

```bash
copier copy gh:<user>/lab-standards ~/research/trial
cd ~/research/trial
git init -b main && git add -A && git commit -m "init from lab-standards v0.2.0"
uv sync
julia --project=jl -e 'using Pkg; Pkg.instantiate()'
uv run pre-commit install
make check && make example
uv run labkit standards status          # Python・Julia とも release v0.2.0 になっていること
```

---

## エージェント（Claude Code）に任せる場合

手順 0 の `gh auth login` と juliaup のインストールだけ人間が済ませ、zip を `~/dev` に展開してから
`cd ~/dev/lab-standards && claude` で起動し、次のプロンプトを渡す（`<user>` を書き換える）。

```text
このディレクトリ（~/dev/lab-standards）は研究プロジェクト用の標準リポジトリ lab-standards v0.2.0 です。
GitHub ユーザー <user> の非公開リポジトリとして公開するところまで進めてください。

前提: gh は認証済み。docs/SETUP.md と CLAUDE.md を最初に読むこと。

手順:
1. 環境確認: git, gh（`gh auth status`）, uv, copier, julia(>=1.11) の有無とバージョンを確認する。
   uv か copier が無ければインストールしてよい（uv: 公式インストーラ、copier: `uv tool install copier`）。
   julia が無ければ止まって私に知らせる。`gh auth setup-git` を実行する。
2. copier.yml の YOUR_GITHUB を <user> に置き換える。他のファイルは変えない。
3. `git init -b main` → 全ファイルを commit（メッセージ "lab-standards v0.2.0"）。
4. 検査とテスト（すべて通るまで次に進まない）:
   - python3 tools/release.py --check
   - (cd labkit/python && uv run --extra dev pytest -q)
   - uv run --with pytest pytest -q claude-plugin/tests
   - julia --project=labkit/julia/LabKit -e 'using Pkg; Pkg.instantiate(); Pkg.test()'
   失敗したら原因を特定して最小限の修正をする。Python と Julia の API・ファイル形式の対称性を壊さないこと
   （CLAUDE.md の規約）。修正内容は CHANGELOG.md の v0.2.0 の節に「### 修正」として追記し、commit する。
   同じ失敗に 3 回対処しても解決しないときは、止まって状況を報告する。
5. 動作確認（タグ未公開なので、生成したプロジェクトを手元の本体に link して試す）:
   - 一時ディレクトリに `copier copy --defaults --vcs-ref HEAD -d project_name="trial" -d author=<user> . <tmp>/trial` で生成
   - <tmp>/trial で `git init -b main && git add -A && git commit -m init`
   - <tmp>/trial を作業ディレクトリにして
     `uv run --project ~/dev/lab-standards/labkit/python labkit standards link --path ~/dev/lab-standards`
     （本体側の labkit で link し、続けて uv sync と Julia の instantiate まで行われる）
   - `uv run pytest -q`、`make example`、`uv run labkit check --ignore L050` が通ること、
     `uv run labkit runs list` に run が出ること、`runs/*/figures/*.png` が開けることを確認
   - Julia: `julia --project=jl jl/scripts/run_example.jl configs/experiments/example.toml` が通ること
   - 確認後は一時ディレクトリを削除する
6. 手順 4・5 が通ったら、`git tag v0.2.0` を打つ。
7. `gh repo create <user>/lab-standards --private --source . --remote origin --push` と `git push origin --tags` で公開する。
   既に同名リポジトリがある場合は push せず止まって知らせる。
8. `gh run list --limit 3` で CI の結果を確認する（完了まで待つ）。失敗したらログを読んで報告する（勝手に直して再 push しない）。
9. 最後に次を報告する: リポジトリ URL、タグ、テスト結果、加えた修正の一覧、CI の結果、
   私が Claude Code で実行すべきコマンド（/plugin marketplace add ~/dev/lab-standards と /plugin install lab-rules@lab-standards）。

してはいけないこと: 公開リポジトリにすること、force push、main 以外への push、copier.yml 以外の YOUR_GITHUB 以外の置換、
テストを通すためにテスト自体を弱めること。
```
