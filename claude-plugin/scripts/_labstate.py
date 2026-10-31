"""hooks 用の .lab/ 状態アクセス（標準ライブラリのみ）。labkit/state.py と同じファイル形式.

ここでは「読む」ことと「承認待ち要求を積む」「承認を使用済みにする」だけを行う。
承認記録（.lab/approvals/）を新規に作るのは labkit approve（人間）だけ。
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
from pathlib import Path

LAB_DIR = ".lab"
DEFAULT_PRESENCE = "away"
STANDARDS_MARKER = ".lab-standards-root"
GITIGNORE = (
    "# labkit が生成。presence・queue・approvals は手元だけの状態（flows/ は git 管理）\n"
    "presence\nqueue/\napprovals/\n"
)


def find_scope(start: str | os.PathLike | None) -> tuple[Path, str] | None:
    """(root, "project" | "standards") を返す。どちらでもなければ None."""
    if start is None:
        return None
    p = Path(start).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    p = p.resolve()
    while not p.exists():
        p = p.parent
    if p.is_file():
        p = p.parent
    for d in (p, *p.parents):
        if (d / "lab.toml").is_file():
            return d, "project"
        if (d / STANDARDS_MARKER).is_file() or ((d / "copier.yml").is_file() and (d / "labkit" / "python").is_dir()):
            return d, "standards"
    return None


def _now() -> _dt.datetime:
    return _dt.datetime.now().astimezone()


def _iso(t: _dt.datetime) -> str:
    return t.isoformat(timespec="seconds")


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def lab_dir(root: Path) -> Path:
    d = root / LAB_DIR
    d.mkdir(exist_ok=True)
    gi = d / ".gitignore"
    if not gi.is_file():
        gi.write_text(GITIGNORE, encoding="utf-8")
    return d


def get_presence(root: Path) -> str:
    f = root / LAB_DIR / "presence"
    if f.is_file():
        v = f.read_text(encoding="utf-8").strip()
        if v in ("here", "away"):
            return v
    return DEFAULT_PRESENCE


def git(cwd: Path, *args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
                              timeout=10).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def git_head(cwd: Path) -> str | None:
    return git(cwd, "rev-parse", "HEAD")


def git_branch(cwd: Path) -> str | None:
    return git(cwd, "rev-parse", "--abbrev-ref", "HEAD")


def list_queue(root: Path) -> list[dict]:
    d = root / LAB_DIR / "queue"
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("Q*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return out


def next_id(root: Path) -> str:
    nums = []
    for d in (root / LAB_DIR / "queue", root / LAB_DIR / "approvals"):
        if d.is_dir():
            nums += [int(p.stem[1:]) for p in d.glob("Q*.json") if p.stem[1:].isdigit()]
    return f"Q{(max(nums) + 1) if nums else 1:03d}"


def request_approval(root: Path, command: str, *, cwd: Path, reason: str, session_id: str = "") -> dict:
    head = git_head(cwd)
    for it in list_queue(root):
        if (it.get("kind") == "approval" and it.get("status") == "pending" and it.get("command") == command
                and it.get("head") == head):
            return it
    diff = git(cwd, "diff", "--stat", "HEAD") or ""
    lines = diff.splitlines()
    summary = (lines[-1].strip() if lines else "変更なし")
    log = git(cwd, "log", "--oneline", "-3") or ""
    item = {
        "id": next_id(root), "kind": "approval", "status": "pending",
        "command": command, "cwd": str(cwd), "branch": git_branch(cwd), "head": head,
        "diff_summary": f"作業ツリー: {summary}; 直近の commit: {log.replace(chr(10), ' / ')}",
        "reason": reason, "created": _iso(_now()), "session_id": session_id,
    }
    _write_json(lab_dir(root) / "queue" / f"{item['id']}.json", item)
    return item


def find_valid_approval(root: Path, command: str, head: str | None) -> dict | None:
    d = root / LAB_DIR / "approvals"
    if not d.is_dir():
        return None
    now = _now()
    for p in sorted(d.glob("Q*.json")):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if rec.get("command") != command or rec.get("head") != head or rec.get("used_at"):
            continue
        try:
            if _dt.datetime.fromisoformat(rec["expires_at"]) < now:
                continue
        except (KeyError, ValueError):
            continue
        return rec
    return None


def consume_approval(root: Path, rec: dict) -> None:
    rec["used_at"] = _iso(_now())
    _write_json(root / LAB_DIR / "approvals" / f"{rec['id']}.json", rec)
    q = root / LAB_DIR / "queue" / f"{rec['id']}.json"
    if q.is_file():
        try:
            it = json.loads(q.read_text(encoding="utf-8"))
            it.update(status="executed", executed=rec["used_at"])
            _write_json(q, it)
        except (json.JSONDecodeError, OSError):
            pass


def active_flows(root: Path) -> list[dict]:
    d = root / LAB_DIR / "flows"
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        try:
            st = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if st.get("status") == "active":
            out.append(st)
    return out


def current_stage(st: dict) -> dict:
    for s in st.get("stages", []):
        if s.get("name") == st.get("stage"):
            return s
    return {"name": st.get("stage"), "forbid": [], "description": "", "approval": False}


def pending_summary(root: Path) -> dict[str, list[dict]]:
    q = list_queue(root)
    return {
        "pending": [i for i in q if i.get("kind") == "approval" and i.get("status") == "pending"],
        "approved": [i for i in q if i.get("kind") == "approval" and i.get("status") == "approved"],
        "open_questions": [i for i in q if i.get("kind") == "question" and i.get("status") == "open"],
        "answered": [i for i in q if i.get("kind") == "question" and i.get("status") == "answered"],
    }


def load_gate_conf(root: Path, kind: str) -> dict:
    conf = {"enabled": True, "protected_branches": ["main", "master"], "approval_ttl_hours": 24}
    if kind == "project":
        try:
            import tomllib

            with open(root / "lab.toml", "rb") as f:
                user = tomllib.load(f).get("gate", {})
            if isinstance(user, dict):
                conf.update(user)
        except (OSError, ValueError, ImportError):
            pass
    return conf
