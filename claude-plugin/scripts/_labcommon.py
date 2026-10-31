"""hooks 共通処理（標準ライブラリのみ。Python 3.11 以上）."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python < 3.11: 規約を読めないので何もしない
    tomllib = None

# Claude Code との入出力は UTF-8。Windows では既定がコンソールのコードページ（cp932 など）になり、
# 日本語のメッセージが文字化けし、日本語を含むパスの JSON 入力が読めなくなるので固定する
for _stream in (sys.stdin, sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

PROTECTED_FILES = {"lab.toml", ".copier-answers.yml", ".claude/settings.json"}
# Claude が Write/Edit で触れないハーネスの状態（labkit のコマンド経由でのみ変わる）
HARNESS_STATE_DIRS = (".lab/approvals", ".lab/queue", ".lab/flows")
REVIEW_DIR = "docs/reviews"
REVIEWER = "lab-reviewer"
# hook の `ask` が人間に届くとは限らない permission mode（docs/notes/claude-code-spec.md。auto では ask は確認画面に出る）
NO_PROMPT_MODES = {"bypassPermissions", "dontAsk"}
CODE_DIRS = {"src", "scripts", "jl", "configs", "tests", "figspecs", "jobs"}


def read_input() -> dict:
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}


def find_root(start: str | os.PathLike | None) -> Path | None:
    """lab.toml のあるプロジェクトのルート（プロジェクト以外では None）."""
    from _labstate import find_scope

    sc = find_scope(start)
    return sc[0] if sc and sc[1] == "project" else None


def load_lab(root: Path) -> dict:
    """lab.toml を既定値（_labstate.DEFAULTS、labkit と同一）に重ねる。tomllib が無ければ {}（hooks は何もしない）."""
    if tomllib is None:
        return {}
    from _labstate import DEFAULTS, deep_merge

    with open(root / "lab.toml", "rb") as f:
        out = deep_merge(DEFAULTS, tomllib.load(f))
    # v0.3.0 で増えた書き込み先は、古い lab.toml が writable を列挙していても許す
    out["layout"]["writable"] = list(dict.fromkeys([*out["layout"]["writable"], ".lab/presence"]))
    return out


def block(message: str) -> None:
    """操作を止め、理由を Claude に返す（exit 2）."""
    print(f"[lab-rules] {message}", file=sys.stderr)
    sys.exit(2)


def decide(decision: str, reason: str, extra: dict | None = None) -> None:
    """PreToolUse の JSON 出力（allow / ask / deny）で終了する."""
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": f"[lab-rules] {reason}",
        }
    }
    if extra:
        out.update(extra)
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(0)


def is_reviewer(data: dict) -> bool:
    t = str(data.get("agent_type") or "")
    return t == REVIEWER or t.endswith(":" + REVIEWER)


def labkit_cmd(root: Path) -> list[str] | None:
    for cand in (root / ".venv" / "bin" / "labkit", root / ".venv" / "Scripts" / "labkit.exe"):
        if cand.is_file():
            return [str(cand)]
    if shutil.which("labkit"):
        return ["labkit"]
    if shutil.which("uv") and (root / "pyproject.toml").is_file():
        return ["uv", "run", "--quiet", "labkit"]
    return None


def rel(path: Path, root: Path) -> str | None:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def describe_condition(c: dict) -> str:
    t = c.get("type", "?")
    params = ", ".join(f"{k}={v}" for k, v in c.items() if k != "type")
    return f"{t}({params})" if params else t


def flow_context(root: Path) -> list[str]:
    """進行中の flow の段階・禁止・残り条件（SessionStart / UserPromptSubmit 用）."""
    from _labstate import active_flows, current_stage

    lines = []
    for st in active_flows(root):
        s = current_stage(st)
        lines.append(f"- 進行中の手順 flow={st['flow']}: 段階「{s['name']}」— {s.get('description', '')}")
        if s.get("forbid"):
            lines.append(f"  この段階で禁止の操作: {', '.join(s['forbid'])}（hooks が拒否する）")
        if s.get("done"):
            lines.append(
                "  次へ進む条件: "
                + "; ".join(describe_condition(c) for c in s["done"])
                + "。`labkit flow status` で未達を確認し、満たしたら `labkit flow advance`"
            )
        if s.get("approval"):
            lines.append("  この段階から進むには人間の承認が要る（advance がキューに積む）")
    return lines


def queue_context(root: Path) -> list[str]:
    from _labstate import pending_summary

    s = pending_summary(root)
    lines = []
    for it in s["approved"]:
        lines.append(
            f"- 承認済み・未実行 #{it['id']}: `{it['command']}`（cwd {it.get('cwd')}, HEAD {(it.get('head') or '')[:7]}）"
            "→ 同じディレクトリ・同じ HEAD で、同じコマンド全文をそのまま実行する（1 回限り）"
        )
    for it in s["pending"]:
        lines.append(
            f"- 承認待ち #{it['id']}: `{it['command']}` — 人間の `labkit approve {it['id']}` を待つ。"
            "依存しない作業を続け、終了時の報告に挙げる"
        )
    for it in s["answered"]:
        lines.append(
            f"- 回答あり #{it['id']}: 質問「{it.get('question')}」→ 回答「{it.get('answer')}」"
            f"（仮の判断は「{it.get('assumed')}」）。取り込んだら `labkit queue done {it['id']}`"
        )
    for it in s["open_questions"]:
        lines.append(f"- 未回答の質問 #{it['id']}: 「{it.get('question')}」仮の判断「{it.get('assumed')}」で進行中")
    return lines
