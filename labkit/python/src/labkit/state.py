"""ハーネスの状態（.lab/）: 人間への連絡のキュー.

    .lab/queue/<ID>.json      人間への連絡（kind=question）。`labkit queue ask` が積む。返事は待たない（完全自律）:
                              エージェントは仮の判断で進み、人間は会話か queue の項目を読んで必要なら指示を変える
    .lab/flows/<name>.json    手順の状態（flow.py。git 管理）

v2.0.0 で承認・却下・回答・委任（approve / reject / answer / delegate）と承認ゲートを廃止した。
v1.x が積んだ承認待ち（kind=approval）は読むだけで扱わない（`labkit queue done <ID>` で閉じられる）。
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path

from labkit._util import git, read_json, write_json_atomic

LAB_DIR = ".lab"
GITIGNORE = "# labkit が生成。queue は手元だけの状態（flows/ と beats/ は git 管理）\nqueue/\n"


def _now() -> _dt.datetime:
    return _dt.datetime.now().astimezone()


def _iso(t: _dt.datetime) -> str:
    return t.isoformat(timespec="seconds")


def lab_dir(root: Path) -> Path:
    d = root / LAB_DIR
    d.mkdir(exist_ok=True)
    gi = d / ".gitignore"
    if not gi.is_file():
        gi.write_text(GITIGNORE, encoding="utf-8", newline="\n")
    return d


def git_branch(cwd: Path) -> str | None:
    return git(cwd, "rev-parse", "--abbrev-ref", "HEAD")


def session_id(explicit: str = "") -> str:
    return explicit or os.environ.get("CLAUDE_CODE_SESSION_ID", "")


# ---- queue ----
def list_queue(root: Path) -> list[dict]:
    d = root / LAB_DIR / "queue"
    out = []
    for p in sorted(d.glob("Q*.json")) if d.is_dir() else []:
        try:
            out.append(read_json(p))
        except (json.JSONDecodeError, OSError):
            continue
    return out


def get_item(root: Path, qid: str) -> dict:
    p = root / LAB_DIR / "queue" / f"{qid}.json"
    if not p.is_file():
        raise FileNotFoundError(f"キューに {qid} がありません（`labkit queue list`）")
    return read_json(p)


def save_item(root: Path, item: dict) -> None:
    write_json_atomic(lab_dir(root) / "queue" / f"{item['id']}.json", item)


def _next_id(root: Path) -> str:
    nums = [int(i["id"][1:]) for i in list_queue(root) if i.get("id", "Q")[1:].isdigit()]
    return f"Q{(max(nums) + 1) if nums else 1:03d}"


def ask_question(root: Path, question: str, *, options: list[str], assumed: str, impact: str = "") -> dict:
    item = {
        "id": _next_id(root),
        "kind": "question",
        "status": "open",
        "question": question,
        "options": options,
        "assumed": assumed,
        "impact": impact,
        "created": _iso(_now()),
        "session_id": session_id(),
    }
    save_item(root, item)
    return item


def mark_done(root: Path, qid: str) -> dict:
    """対応済みにする（連絡が不要になった、v1.x の承認待ちを閉じる）."""
    it = get_item(root, qid)
    it.update(status="done", done=_iso(_now()))
    save_item(root, it)
    return it


def pending_summary(root: Path) -> dict[str, list[dict]]:
    """開いている人間への連絡（v1.x の承認待ちは含めない）."""
    q = list_queue(root)
    return {"open_questions": [i for i in q if i.get("kind") == "question" and i.get("status") == "open"]}
