"""Bash コマンドの分類: 承認ゲートの対象、Claude が実行してはいけない操作、lab-reviewer に許す読み取り.

shlex でトークン化し、`command git push`、`git -c x=y -C dir push`、`uv run labkit raw freeze`、連結コマンドを見る。
限界: `sh -c "..."`、スクリプト経由、エイリアスは見えない（hooks は security boundary ではない）。
最後の砦は GitHub 側のブランチ保護（docs/harness.md）。
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

# 承認ゲートの対象 = 取り返しのつかない、または共有先を変える操作だけ。feat ブランチへの push は自由
GATED = {
    "git_push": "保護ブランチへの push（または force / 削除 / --all / --tags）",
    "git_tag": "git tag の作成・削除",
    "git_merge": "保護ブランチへの merge",
    "gh_merge": "gh pr merge",
    "gh_release": "gh release の作成・変更",
    "raw_freeze": "labkit raw freeze（生データの確定）",
}
FORBIDDEN = "labkit approve / reject / answer / delegate（承認・回答・委任は人間だけ）"

GIT_GLOBAL_WITH_ARG = {"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
PUSH_WITH_ARG = {"--repo", "--receive-pack", "--exec", "-o", "--push-option", "--recurse-submodules", "--signed"}
TAG_LIST = {"-l", "--list", "-n", "--contains", "--no-contains", "--points-at", "--merged", "--no-merged", "--sort"}
TAG_WRITE = {"-d", "--delete", "-a", "-s", "-u", "-f", "--force", "-m", "-F", "--annotate", "--sign"}
UV_RUN_WITH_ARG = {
    "--project",
    "-p",
    "--with",
    "-w",
    "--extra",
    "--python",
    "--package",
    "--directory",
    "--group",
    "--only-group",
    "--with-editable",
    "--with-requirements",
    "--index",
    "--env-file",
    "--module",
    "-m",
}
SPLIT_RE = re.compile(r"&&|\|\||;|\||&|\n")
WRAPPERS = (
    "command",
    "sudo",
    "time",
    "nohup",
    "exec",
    "builtin",
    "nice",
    "stdbuf",
    "doas",
    "xargs",
    "(",
    ")",
    "{",
    "}",
    "then",
    "do",
    "else",
)


@dataclass
class Hit:
    category: str
    segment: str
    detail: str = ""

    @property
    def description(self) -> str:
        return GATED.get(self.category, FORBIDDEN)


def segments(command: str) -> list[str]:
    return [s.strip() for s in SPLIT_RE.split(command) if s.strip()]


def tokens(segment: str) -> list[str]:
    try:
        toks = shlex.split(segment, posix=True)
    except ValueError:
        toks = segment.split()
    if toks and len(toks[-1]) > 1 and toks[-1].endswith(")"):
        toks = [*toks[:-1], toks[-1].rstrip(")")]  # `(git push)` のサブシェル
    while toks:  # 先頭の環境変数代入・ラッパー・括弧・予約語を外す
        t = toks[0]
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", t):
            toks = toks[1:]
        elif t.startswith("(") and len(t) > 1:
            toks = [t[1:], *toks[1:]]
        elif t in WRAPPERS or t == "env":
            toks = toks[1:]
            while toks and (toks[0].startswith("-") or (t == "env" and "=" in toks[0])):
                toks = toks[1:]
        else:
            break
    return [t for t in toks if t]


def _basename(t: str) -> str:
    return t.replace("\\", "/").rsplit("/", 1)[-1].lower().removesuffix(".exe")


def _git_subcommand(toks: list[str]) -> tuple[str | None, list[str]]:
    i = 1
    while i < len(toks):
        t = toks[i]
        if t in GIT_GLOBAL_WITH_ARG:
            i += 2
        elif t.startswith("-"):
            i += 1
        else:
            return t, toks[i + 1 :]
    return None, []


def labkit_args(toks: list[str]) -> list[str] | None:
    """`labkit ...` / `uv run [...] labkit ...` / `python -m labkit.cli ...` / `uvx labkit ...` → labkit の引数."""
    if not toks:
        return None
    b = _basename(toks[0])
    if b == "labkit":
        return toks[1:]
    if b == "uvx" and len(toks) > 1 and _basename(toks[1]).split("@")[0] == "labkit":
        return toks[2:]
    if b.startswith("python") and toks[1:3] in (["-m", "labkit.cli"], ["-m", "labkit"]):
        return toks[3:]
    if b == "uv" and len(toks) > 1 and (toks[1] == "run" or toks[1:3] == ["tool", "run"]):
        i = 2 if toks[1] == "run" else 3
        while i < len(toks) and toks[i].startswith("-"):
            if toks[i] in ("-m", "--module") and toks[i + 1 : i + 2] and toks[i + 1] in ("labkit.cli", "labkit"):
                return toks[i + 2 :]
            i += 2 if toks[i] in UV_RUN_WITH_ARG else 1
        return labkit_args(toks[i:])
    return None


def _push_targets(args: list[str]) -> tuple[list[str], bool]:
    """(push 先ブランチ名の一覧, 危険フラグ)。危険 = force / delete / --all / --mirror / --tags."""
    danger = False
    positional: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in PUSH_WITH_ARG:
            i += 2
            continue
        if a.startswith("-"):
            if a in ("-f", "--force", "-d", "--delete", "--all", "--mirror", "--tags", "--prune") or a.startswith(
                "--force"
            ):
                danger = True
        else:
            positional.append(a)
        i += 1
    targets = []
    for spec in positional[1:]:  # positional[0] はリモート
        src, _, dst = spec.lstrip("+").rpartition(":")
        if ":" in spec and not src:
            danger = True  # `:branch` はリモートブランチの削除
        targets.append(dst.removeprefix("refs/heads/"))
    if positional and len(positional) == 1 and "--delete" in args:
        danger = True
    return targets, danger


def classify_segment(seg: str, protected: list[str], current_branch: str | None) -> list[Hit]:
    toks = tokens(seg)
    if not toks:
        return []
    b = _basename(toks[0])
    if b == "git":
        sub, args = _git_subcommand(toks)
        if sub == "push":
            targets, danger = _push_targets(args)
            if not targets:
                targets = [current_branch or "?"]
            if danger or any(t in protected or t == "?" for t in targets):
                return [Hit("git_push", seg, " ".join(args))]
        elif sub == "tag":
            positional = [a for a in args if not a.startswith("-")]
            listing = any(a in TAG_LIST or a.startswith(("--sort", "--format", "--contains", "-l", "-n")) for a in args)
            if any(a in TAG_WRITE for a in args) or (positional and not listing):
                return [Hit("git_tag", seg, " ".join(args))]
        elif sub == "merge" and (current_branch is None or current_branch in protected):
            return [Hit("git_merge", seg, f"branch={current_branch or '?'}")]
        return []
    if b == "gh":
        if toks[1:3] == ["pr", "merge"]:
            return [Hit("gh_merge", seg)]
        if toks[1:2] == ["release"] and (toks[2:3] or [""])[0] not in ("list", "view", "download", ""):
            return [Hit("gh_release", seg, toks[2])]
        return []
    la = labkit_args(toks)
    if la is not None:
        if la[:2] == ["raw", "freeze"]:
            return [Hit("raw_freeze", seg)]
        if la[:1] in (["approve"], ["reject"], ["answer"]) or (la[:1] == ["delegate"] and la[1:2] != ["list"]):
            return [Hit("forbidden", seg, la[0])]
    return []


def classify(command: str, protected: list[str], current_branch: str | None) -> list[Hit]:
    return [h for seg in segments(command) for h in classify_segment(seg, protected, current_branch)]


# ---- lab-reviewer（レビュー agent）に許す読み取り専用コマンド（許可リスト。載っていないものは拒否） ----
REVIEWER_ALLOWED = {
    "cat",
    "head",
    "tail",
    "ls",
    "wc",
    "grep",
    "rg",
    "find",
    "diff",
    "stat",
    "file",
    "tree",
    "echo",
    "pwd",
    "date",
    "which",
    "sort",
    "uniq",
    "cut",
    "awk",
    "jq",
    "du",
    "cd",
    "true",
    "test",
    "[",
    "pytest",
}
GIT_READ = {"diff", "log", "status", "show", "rev-parse", "blame", "branch", "tag", "ls-files", "describe", "grep"}
LABKIT_READ = {
    ("check",),
    ("runs", "list"),
    ("runs", "show"),
    ("cite",),
    ("review", "template"),
    ("paths",),
    ("fig", "list"),
    ("queue", "list"),
    ("delegate", "list"),
    ("flow", "status"),
    ("standards", "status"),
}


def reviewer_allowed(seg: str) -> bool:
    if ">" in seg:  # リダイレクトはすべて拒否
        return False
    toks = tokens(seg)
    if not toks:
        return True
    b = _basename(toks[0])
    if b == "git":
        sub, args = _git_subcommand(toks)
        return sub in GIT_READ and not any(a in ("-d", "-D", "-m", "-M", "-f", "--delete", "--force") for a in args)
    la = labkit_args(toks)
    if la is not None:
        pos = tuple(a for a in la if not a.startswith("-"))
        return any(pos[: len(p)] == p for p in LABKIT_READ)
    if b == "uv" and toks[1:2] == ["run"]:
        i = 2
        while i < len(toks) and toks[i].startswith("-"):
            i += 2 if toks[i] in UV_RUN_WITH_ARG else 1
        rest = toks[i:]
        return bool(rest) and (_basename(rest[0]) == "pytest" or rest[:2] == ["ruff", "check"])
    if b == "sed":
        return not any(t == "-i" or t.startswith(("-i", "--in-place")) for t in toks[1:])
    if b == "ruff":
        return toks[1:2] == ["check"] or toks[1:3] == ["format", "--check"]
    return b in REVIEWER_ALLOWED


def reviewer_allowed_summary() -> str:
    return (
        "lab-reviewer が実行できるのは読み取りだけ: "
        + " ".join(sorted(REVIEWER_ALLOWED))
        + "; git {"
        + ",".join(sorted(GIT_READ))
        + "}; labkit {"
        + ", ".join(" ".join(p) for p in sorted(LABKIT_READ))
        + "}。リダイレクト（>）不可。レビュー記録は Write で docs/reviews/ に書く。"
    )
