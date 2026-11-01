"""ハーネスの状態（.lab/）: 在席状態・承認待ちキュー・承認記録.

    .lab/presence              "here" | "away"（既定 away）
    .lab/queue/<ID>.json       要求（kind=approval）と質問（kind=question）
    .lab/approvals/<ID>.json   承認記録（`labkit approve` だけが書く。Claude は書けない）
    .lab/flows/<name>.json     手順の状態機械（flow.py。git 管理）

読み書きの共通部分は labkit/_labstate.py（claude-plugin/scripts/_labstate.py のバイト同一コピー）。
ここには labkit 側だけが行う操作（人間の承認・却下・回答、質問の登録、presence の変更）を置く。
"""

from __future__ import annotations

import datetime as _dt
import getpass
import os
import sys
from pathlib import Path

from labkit._labstate import (  # noqa: F401  （cli / flow / tests が labkit.state 経由で使う）
    DELEGATABLE,
    DELEGATION_GROUPS,
    LAB_DIR,
    _iso,
    _now,
    active_delegations,
    active_flows,
    add_delegation,
    consume_approval,
    current_stage,
    describe_delegations,
    expand_delegation,
    find_delegation,
    find_valid_approval,
    get_presence,
    git_branch,
    git_head,
    lab_dir,
    list_delegations,
    list_queue,
    load_gate_conf,
    next_id,
    pending_summary,
    request_approval,
    revoke_delegation,
)
from labkit._labstate import find_scope as _find_scope
from labkit._util import write_json_atomic, write_text_atomic

PRESENCE_VALUES = ("here", "away")


def find_scope(start: str | os.PathLike | None = None) -> tuple[Path, str] | None:
    """(root, "project" | "standards")。省略時は cwd から探す."""
    return _find_scope(start or Path.cwd())


def set_presence(root: Path, value: str) -> str:
    if value not in PRESENCE_VALUES:
        raise ValueError(f"presence は {PRESENCE_VALUES} のいずれか: {value!r}")
    write_text_atomic(lab_dir(root) / "presence", value + "\n")
    return value


# ---- queue ----
def get_item(root: Path, qid: str) -> dict:
    import json

    p = root / LAB_DIR / "queue" / f"{qid}.json"
    if not p.is_file():
        raise FileNotFoundError(f"キューに {qid} がありません（`labkit queue list`）")
    return json.loads(p.read_text(encoding="utf-8"))


def save_item(root: Path, item: dict) -> Path:
    p = lab_dir(root) / "queue" / f"{item['id']}.json"
    write_json_atomic(p, item)
    return p


def ask_question(
    root: Path, question: str, *, options: list[str], assumed: str, impact: str = "", session_id: str = ""
) -> dict:
    item = {
        "id": next_id(root),
        "kind": "question",
        "status": "open",
        "question": question,
        "options": options,
        "assumed": assumed,
        "impact": impact,
        "answer": None,
        "created": _iso(_now()),
        "session_id": session_id or os.environ.get("CLAUDE_CODE_SESSION_ID", ""),
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
def human_check() -> dict:
    """承認の実行者の記録（誰が・端末か・Claude Code のシェルか）。

    Claude が承認を作れないことは hooks（guard_bash が `labkit approve` を拒否）で保証する。ここは記録だけで、
    確認の儀式（ID 再入力・--yes）は置かない: 再入力は Windows の非対話シェルで動かず、フラグは Claude も付けられる。
    """
    return {
        "by": getpass.getuser(),
        "tty": sys.stdin.isatty(),
        "claude_shell": bool(os.environ.get("CLAUDECODE")),
    }


def approve(root: Path, qid: str, *, ttl_hours: float, who: dict) -> dict:
    it = get_item(root, qid)
    if it.get("kind") != "approval":
        raise ValueError(f"{qid} は承認要求ではありません（kind={it.get('kind')}）")
    if it.get("status") != "pending":
        raise ValueError(f"{qid} は {it.get('status')} です（pending のみ承認できます）")
    now = _now()
    rec = {
        "id": qid,
        "command": it["command"],
        "head": it.get("head"),
        "cwd": it.get("cwd"),
        "approved_at": _iso(now),
        "expires_at": _iso(now + _dt.timedelta(hours=ttl_hours)),
        "used_at": None,
        **who,
    }
    d = lab_dir(root) / "approvals"
    d.mkdir(exist_ok=True)
    write_json_atomic(d / f"{qid}.json", rec)
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
    import json

    d = root / LAB_DIR / "approvals"
    if not d.is_dir():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("Q*.json"))]
