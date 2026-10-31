"""Bash コマンドの分類（承認ゲートの対象・flow の禁止カテゴリ・Claude が実行してはいけない操作）.

正規表現ではなく shlex でトークン化し、`command git push`、`git -c x=y -C dir push`、`uv run labkit raw freeze`、
`&&`/`;`/`|`/改行で連結されたものを検出する。限界: `sh -c "..."`、スクリプト経由、エイリアスは見えない。
最後の砦は GitHub 側のブランチ保護とサンドボックス（docs/harness.md）。
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

# 承認ゲートの対象（category -> 説明）
GATED = {
    "git_push": "git push（リモートの変更）",
    "git_tag": "git tag の作成・削除",
    "git_merge": "保護ブランチへの merge",
    "gh_merge": "gh pr merge",
    "gh_release": "gh release の作成・変更",
    "raw_freeze": "labkit raw freeze（生データの確定）",
    "template": "copier copy/update・labkit standards template（雛形の適用）",
}
# Claude 自身が決して実行してはいけない（承認を作る側の操作）
FORBIDDEN = {"labkit_approve": "labkit approve / reject / answer（承認・回答は人間だけ）"}

# flow の forbid カテゴリ（stage.forbid）への対応
FLOW_CATEGORY = {
    "git_push": "release", "git_tag": "release", "git_merge": "release", "gh_merge": "release", "gh_release": "release",
    "raw_freeze": "raw", "template": "template",
    "link": "link", "experiments": "experiments",
}

GIT_GLOBAL_WITH_ARG = {"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix",
                       "--config-env", "--list-cmds"}
GIT_GLOBAL_FLAGS = {"-p", "--paginate", "-P", "--no-pager", "--bare", "--no-replace-objects", "--literal-pathspecs",
                    "--glob-pathspecs", "--noglob-pathspecs", "--icase-pathspecs", "--no-optional-locks",
                    "--no-lazy-fetch", "--no-advice"}
TAG_LIST_FLAGS = {"-l", "--list", "-n", "--contains", "--no-contains", "--points-at", "--merged", "--no-merged",
                  "--sort", "--format", "--column", "--no-column", "-i", "--ignore-case", "--omit-empty"}
UV_RUN_WITH_ARG = {"--project", "-p", "--with", "-w", "--extra", "--python", "--package", "--directory", "--group",
                   "--only-group", "--with-editable", "--with-requirements", "--index", "--env-file", "--color",
                   "--cache-dir", "--config-file", "--module", "-m"}
SPLIT_RE = re.compile(r"&&|\|\||;|\||&|\n")
WRAPPERS = ("command", "sudo", "time", "nohup", "exec", "builtin", "nice", "stdbuf", "caffeinate", "doas", "xargs",
            "(", ")", "{", "}", "then", "do", "else")


@dataclass
class Hit:
    category: str
    segment: str
    detail: str = ""
    repo_dir: str | None = None  # git -C <dir> のとき、承認を結び付けるリポジトリ

    @property
    def description(self) -> str:
        return GATED.get(self.category) or FORBIDDEN.get(self.category) or self.category


def segments(command: str) -> list[str]:
    return [s.strip() for s in SPLIT_RE.split(command) if s.strip()]


def tokens(segment: str) -> list[str]:
    try:
        toks = shlex.split(segment, posix=True)
    except ValueError:
        toks = segment.split()
    if toks and toks[-1] in (")", "}") or (toks and len(toks[-1]) > 1 and toks[-1].endswith(")")):
        toks = [*toks[:-1], toks[-1].rstrip(")")]  # `(git push)` のサブシェル
        toks = [t for t in toks if t]
    # 先頭の環境変数代入・ラッパー・括弧・if/for の予約語を外す
    while toks:
        t = toks[0]
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", t):
            toks = toks[1:]
        elif t.startswith("(") and len(t) > 1:
            toks = [t[1:], *toks[1:]]
        elif t in WRAPPERS:
            toks = toks[1:]
            # sudo -u user など単純なオプションは読み飛ばす
            while toks and toks[0].startswith("-") and t in ("sudo", "nice", "stdbuf", "doas"):
                toks = toks[2:] if toks[0] in ("-u", "-g", "-n", "-o", "-e", "-i") and len(toks) > 1 else toks[1:]
        elif t == "env":
            toks = toks[1:]
            while toks and (re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", toks[0]) or toks[0].startswith("-")):
                toks = toks[1:]
        else:
            break
    return toks


def _basename(t: str) -> str:
    return t.replace("\\", "/").rsplit("/", 1)[-1].lower().removesuffix(".exe")


def _git_subcommand(toks: list[str]) -> tuple[str | None, list[str], str | None]:
    """git のグローバルオプションを飛ばし (subcommand, 残り引数, -C のディレクトリ) を返す."""
    i = 1
    cdir = None
    while i < len(toks):
        t = toks[i]
        if t in GIT_GLOBAL_WITH_ARG:
            if t == "-C" and i + 1 < len(toks):
                cdir = toks[i + 1]
            i += 2
        elif any(t.startswith(k + "=") for k in GIT_GLOBAL_WITH_ARG):
            if t.startswith("-C="):
                cdir = t[3:]
            i += 1
        elif t.startswith("-C") and len(t) > 2:
            cdir = t[2:]
            i += 1
        elif t.startswith("-c") and len(t) > 2:
            i += 1
        elif t in GIT_GLOBAL_FLAGS or t.startswith("--git-dir") or t.startswith("--work-tree"):
            i += 1
        elif t.startswith("-"):
            i += 1
        else:
            return t, toks[i + 1:], cdir
    return None, [], cdir


def _labkit_args(toks: list[str]) -> list[str] | None:
    """`labkit ...` / `uv run [...] labkit ...` / `python -m labkit.cli ...` / `uvx labkit ...` → labkit の引数."""
    if not toks:
        return None
    b = _basename(toks[0])
    if b == "labkit":
        return toks[1:]
    if b == "uv" and len(toks) > 1 and (toks[1] == "run" or toks[1:3] == ["tool", "run"]):
        i = 2 if toks[1] == "run" else 3
        while i < len(toks):
            t = toks[i]
            if t in ("-m", "--module") and i + 1 < len(toks) and toks[i + 1] in ("labkit.cli", "labkit"):
                return toks[i + 2:]
            if t in UV_RUN_WITH_ARG:
                i += 2
            elif t.startswith("-"):
                i += 1
            else:
                break
        rest = toks[i:]
        if rest and _basename(rest[0]).split("@")[0] == "labkit":
            return rest[1:]
        if len(rest) > 2 and _basename(rest[0]).startswith("python") and rest[1] == "-m" and rest[2] in ("labkit.cli", "labkit"):
            return rest[3:]
        return None
    if b == "uvx" and len(toks) > 1 and _basename(toks[1]).split("@")[0] == "labkit":
        return toks[2:]
    if b.startswith("python") and len(toks) > 2 and toks[1] == "-m" and toks[2] in ("labkit.cli", "labkit"):
        return toks[3:]
    return None


def classify_segment(seg: str, protected: list[str], current_branch: str | None) -> list[Hit]:
    toks = tokens(seg)
    if not toks:
        return []
    hits: list[Hit] = []
    b = _basename(toks[0])

    if b == "git":
        sub, args, cdir = _git_subcommand(toks)
        if sub == "push":
            hits.append(Hit("git_push", seg, " ".join(args), cdir))
        elif sub == "tag":
            positional = [a for a in args if not a.startswith("-")]
            listing = any(a in TAG_LIST_FLAGS or a.startswith(("--sort", "--format", "--contains", "--points-at",
                                                                "--merged", "--no-merged", "-l", "-n"))
                          for a in args)
            writing = any(a in ("-d", "--delete", "-a", "-s", "-u", "-f", "--force", "-m", "-F", "--annotate", "--sign")
                          for a in args)
            # `git tag` / `git tag -l 'v*'` は一覧表示なので通す。引数付き（作成）や -d（削除）は対象
            if writing or (positional and not listing):
                hits.append(Hit("git_tag", seg, " ".join(args), cdir))
        elif sub == "merge":
            br = current_branch
            if cdir:
                br = None  # 別ディレクトリの merge は分からないので保護側に倒す
            if br is None or br in protected:
                hits.append(Hit("git_merge", seg, f"branch={br or '?'}", cdir))
        return hits

    if b == "gh":
        if len(toks) > 2 and toks[1] == "pr" and toks[2] == "merge":
            hits.append(Hit("gh_merge", seg))
        elif len(toks) > 1 and toks[1] == "release":
            sub = toks[2] if len(toks) > 2 else ""
            if sub not in ("list", "view", "download", ""):
                hits.append(Hit("gh_release", seg, sub))
        return hits

    if b == "copier" or (b == "uvx" and len(toks) > 1 and _basename(toks[1]).split("@")[0] == "copier"):
        sub = toks[1] if b == "copier" else (toks[2] if len(toks) > 2 else "")
        if sub in ("copy", "update", "recopy"):
            hits.append(Hit("template", seg, sub))
        return hits

    if b == "make":
        targets = [t for t in toks[1:] if not t.startswith("-") and "=" not in t]
        if "raw-freeze" in targets:
            hits.append(Hit("raw_freeze", seg, "make raw-freeze"))
        if "std-template" in targets:
            hits.append(Hit("template", seg, "make std-template"))
        if "std-link" in targets or "std-unlink" in targets:
            hits.append(Hit("link", seg))
        if "example" in targets:
            hits.append(Hit("experiments", seg))
        return hits

    la = _labkit_args(toks)
    if la is not None:
        if la[:2] == ["raw", "freeze"]:
            hits.append(Hit("raw_freeze", seg))
        elif la[:2] == ["standards", "template"]:
            hits.append(Hit("template", seg))
        elif la[:1] == ["approve"] or la[:1] == ["reject"] or la[:1] == ["answer"]:
            hits.append(Hit("labkit_approve", seg, la[0]))
        elif la[:2] in (["standards", "link"], ["standards", "unlink"]):
            hits.append(Hit("link", seg))
        return hits

    # 実験の実行（flow の experiments カテゴリ）
    if b in ("sbatch", "srun"):
        hits.append(Hit("experiments", seg))
        return hits
    if b.startswith("python") or b == "julia" or (b == "uv" and len(toks) > 1 and toks[1] == "run"):
        if re.search(r"(?:^|[\s/])(?:scripts|jl/scripts)/\S+\.(?:py|jl)\b", seg):
            hits.append(Hit("experiments", seg))
    return hits


def classify(command: str, protected: list[str] | None = None, current_branch: str | None = None) -> list[Hit]:
    out: list[Hit] = []
    for seg in segments(command):
        out += classify_segment(seg, protected or ["main", "master"], current_branch)
    return out


def gated(hits: list[Hit]) -> list[Hit]:
    return [h for h in hits if h.category in GATED]


def forbidden(hits: list[Hit]) -> list[Hit]:
    return [h for h in hits if h.category in FORBIDDEN]


def flow_hits(hits: list[Hit], forbid: list[str]) -> list[Hit]:
    return [h for h in hits if FLOW_CATEGORY.get(h.category) in forbid]
