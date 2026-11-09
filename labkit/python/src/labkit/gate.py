"""Bash コマンドの分類: lab-reviewer（レビュー agent）に許す読み取り専用コマンドの判定.

shlex でトークン化し、`command git log`、`git -c x=y -C dir diff`、`uv run labkit check`、連結コマンドを見る。
限界: `sh -c "..."`、スクリプト経由、エイリアスは見えない（hooks は security boundary ではない）。
v2.0.0 で承認ゲート（GATED・classify・FORBIDDEN）を廃止した。
"""

from __future__ import annotations

import re
import shlex

GIT_GLOBAL_WITH_ARG = {"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
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
    ("runs", "table"),
    ("cite",),
    ("claim", "list"),
    ("review", "template"),
    ("review", "list"),
    ("paths",),
    ("fig", "list"),
    ("queue", "list"),
    ("flow", "status"),
    ("standards", "status"),
    ("beat", "log"),
    ("lit", "queue"),
    ("lit", "surveys"),
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
