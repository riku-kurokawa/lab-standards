"""ハーネスの状態（.lab/）: 在席状態・承認待ちキュー・承認記録.

    .lab/presence              "here" | "away"（既定 away）
    .lab/queue/<ID>.json       要求（kind=approval）と質問（kind=question）
    .lab/approvals/<ID>.json   承認記録（`labkit approve` だけが書く。Claude は書けない）
    .lab/flows/<name>.json     手順の状態機械（flow.py。git 管理）

ファイル形式は claude-plugin/scripts/_labstate.py（標準ライブラリのみ）と同一。
片方を変えたら両方を直し、claude-plugin/tests/test_gate.py の往復テストを通すこと。
"""

from __future__ import annotations

import datetime as _dt
import getpass
import json
import os
import subprocess
import sys
from pathlib import Path

from labkit._util import write_json_atomic, write_text_atomic

LAB_DIR = ".lab"
PRESENCE_VALUES = ("here", "away")
DEFAULT_PRESENCE = "away"
GITIGNORE = (
    "# labkit が生成。presence・queue・approvals は手元だけの状態（flows/ は git 管理）\n"
    "presence\nqueue/\napprovals/\n"
)
STANDARDS_MARKER = ".lab-standards-root"


# ---- スコープ（プロジェクト or lab-standards 本体） ----
def find_scope(start: str | os.PathLike | None = None) -> tuple[Path, str] | None:
    """lab.toml のあるプロジェクト（"project"）か、lab-standards 本体（"standards"）を上方向に探す."""
    p = Path(start or Path.cwd()).resolve()
    if p.is_file():
        p = p.parent
    for d in (p, *p.parents):
        if (d / "lab.toml").is_file():
            return d, "project"
        if (d / STANDARDS_MARKER).is_file() or ((d / "copier.yml").is_file() and (d / "labkit" / "python").is_dir()):
            return d, "standards"
    return None


def lab_dir(root: Path) -> Path:
    d = root / LAB_DIR
    if not d.is_dir():
        d.mkdir(parents=True)
    gi = d / ".gitignore"
    if not gi.is_file():
        gi.write_text(GITIGNORE, encoding="utf-8")
    return d


# ---- presence ----
def get_presence(root: Path) -> str:
    f = root / LAB_DIR / "presence"
    if f.is_file():
        v = f.read_text(encoding="utf-8").strip()
        if v in PRESENCE_VALUES:
            return v
    return DEFAULT_PRESENCE


def set_presence(root: Path, value: str) -> str:
    if value not in PRESENCE_VALUES:
        raise ValueError(f"presence は {PRESENCE_VALUES} のいずれか: {value!r}")
    write_text_atomic(lab_dir(root) / "presence", value + "\n")
    return value


# ---- queue ----
def _now() -> _dt.datetime:
    return _dt.datetime.now().astimezone()


def _iso(t: _dt.datetime) -> str:
    return t.isoformat(timespec="seconds")


def queue_dir(root: Path) -> Path:
    d = lab_dir(root) / "queue"
    d.mkdir(exist_ok=True)
    return d


def approvals_dir(root: Path) -> Path:
    d = lab_dir(root) / "approvals"
    d.mkdir(exist_ok=True)
    return d


def next_id(root: Path) -> str:
    nums = []
    for d in (root / LAB_DIR / "queue", root / LAB_DIR / "approvals"):
        if d.is_dir():
            nums += [int(p.stem[1:]) for p in d.glob("Q*.json") if p.stem[1:].isdigit()]
    return f"Q{(max(nums) + 1) if nums else 1:03d}"


def list_queue(root: Path) -> list[dict]:
    d = root / LAB_DIR / "queue"
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("Q*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            out.append({"id": p.stem, "kind": "broken", "status": "broken"})
    return out


def get_item(root: Path, qid: str) -> dict:
    p = root / LAB_DIR / "queue" / f"{qid}.json"
    if not p.is_file():
        raise FileNotFoundError(f"キューに {qid} がありません（`labkit queue list`）")
    return json.loads(p.read_text(encoding="utf-8"))


def save_item(root: Path, item: dict) -> Path:
    p = queue_dir(root) / f"{item['id']}.json"
    write_json_atomic(p, item)
    return p


def git_head(cwd: Path) -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def git_branch(cwd: Path) -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def request_approval(root: Path, command: str, *, cwd: Path, reason: str, session_id: str = "",
                     diff_summary: str = "") -> dict:
    """承認待ち要求を積む。同じコマンド・同じ HEAD の pending があればそれを返す（重複させない）."""
    head = git_head(cwd)
    for it in list_queue(root):
        if (it.get("kind") == "approval" and it.get("status") == "pending" and it.get("command") == command
                and it.get("head") == head):
            return it
    item = {
        "id": next_id(root), "kind": "approval", "status": "pending",
        "command": command, "cwd": str(cwd), "branch": git_branch(cwd), "head": head,
        "diff_summary": diff_summary, "reason": reason,
        "created": _iso(_now()), "session_id": session_id,
    }
    save_item(root, item)
    return item


def ask_question(root: Path, question: str, *, options: list[str], assumed: str, impact: str = "",
                 session_id: str = "") -> dict:
    item = {
        "id": next_id(root), "kind": "question", "status": "open",
        "question": question, "options": options, "assumed": assumed, "impact": impact,
        "answer": None, "created": _iso(_now()), "session_id": session_id,
    }
    save_item(root, item)
    return item


def answer_question(root: Path, qid: str, answer: str) -> dict:
    it = get_item(root, qid)
    if it.get("kind") != "question":
        raise ValueError(f"{qid} は質問ではありません（kind={it.get('kind')}）")
    it.update(status="answered", answer=answer, answered=_iso(_now()))
    save_item(root, it)
    return it


def mark_done(root: Path, qid: str) -> dict:
    """Claude が「対応済み」にする（質問の回答を取り込んだ／承認済み要求を実行した）."""
    it = get_item(root, qid)
    it.update(status="done", done=_iso(_now()))
    save_item(root, it)
    return it


# ---- 承認（人間だけ） ----
def human_check(allow_non_tty: bool) -> dict:
    """承認の実行者が人間であることを、できる範囲で確かめる。

    - 対話端末（TTY）なら ID の再入力を求める（呼び出し側）。
    - TTY でなければ --yes が必要。Claude Code のシェル（CLAUDECODE=1）からの実行は記録に残す。
    hooks（guard_bash）が `labkit approve` 自体を拒否するので、Claude の Bash からはここに到達しない。
    """
    return {
        "by": getpass.getuser(),
        "tty": sys.stdin.isatty(),
        "claude_shell": bool(os.environ.get("CLAUDECODE")),
        "non_tty_forced": allow_non_tty and not sys.stdin.isatty(),
    }


def approve(root: Path, qid: str, *, ttl_hours: float, who: dict) -> dict:
    it = get_item(root, qid)
    if it.get("kind") != "approval":
        raise ValueError(f"{qid} は承認要求ではありません（kind={it.get('kind')}）")
    if it.get("status") != "pending":
        raise ValueError(f"{qid} は {it.get('status')} です（pending のみ承認できます）")
    now = _now()
    rec = {
        "id": qid, "command": it["command"], "head": it.get("head"), "cwd": it.get("cwd"),
        "approved_at": _iso(now), "expires_at": _iso(now + _dt.timedelta(hours=ttl_hours)),
        "used_at": None, **who,
    }
    write_json_atomic(approvals_dir(root) / f"{qid}.json", rec)
    it.update(status="approved", approved=_iso(now))
    save_item(root, it)
    return rec


def reject(root: Path, qid: str, note: str = "") -> dict:
    it = get_item(root, qid)
    if it.get("status") not in ("pending", "approved"):
        raise ValueError(f"{qid} は {it.get('status')} です")
    if it.get("status") == "approved":
        (root / LAB_DIR / "approvals" / f"{qid}.json").unlink(missing_ok=True)
    it.update(status="rejected", rejected=_iso(_now()), note=note)
    save_item(root, it)
    return it


def list_approvals(root: Path) -> list[dict]:
    d = root / LAB_DIR / "approvals"
    if not d.is_dir():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("Q*.json"))]


def find_valid_approval(root: Path, command: str, head: str | None,
                        now: _dt.datetime | None = None) -> dict | None:
    """コマンド全文と HEAD が一致し、未使用かつ期限内の承認を返す."""
    now = now or _now()
    for rec in list_approvals(root):
        if rec.get("command") != command or rec.get("head") != head or rec.get("used_at"):
            continue
        try:
            exp = _dt.datetime.fromisoformat(rec["expires_at"])
        except (KeyError, ValueError):
            continue
        if exp < now:
            continue
        return rec
    return None


def consume_approval(root: Path, rec: dict) -> None:
    rec["used_at"] = _iso(_now())
    write_json_atomic(root / LAB_DIR / "approvals" / f"{rec['id']}.json", rec)
    try:
        it = get_item(root, rec["id"])
        it.update(status="executed", executed=rec["used_at"])
        save_item(root, it)
    except FileNotFoundError:
        pass


def pending_summary(root: Path) -> dict[str, list[dict]]:
    """SessionStart / UserPromptSubmit が文脈に入れる要約."""
    q = list_queue(root)
    return {
        "pending": [i for i in q if i.get("kind") == "approval" and i.get("status") == "pending"],
        "approved": [i for i in q if i.get("kind") == "approval" and i.get("status") == "approved"],
        "open_questions": [i for i in q if i.get("kind") == "question" and i.get("status") == "open"],
        "answered": [i for i in q if i.get("kind") == "question" and i.get("status") == "answered"],
    }
