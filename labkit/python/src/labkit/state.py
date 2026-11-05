"""ハーネスの状態（.lab/）: 承認待ち・質問のキューと委任.

    .lab/queue/<ID>.json      承認待ち（kind=approval）と質問（kind=question）。hooks と `labkit queue ask` が積む
    .lab/delegations.json     委任: 「このカテゴリの操作をこの期間（このブランチで）任せる」。人間の `labkit delegate` と
                              `labkit approve`（= 承認待ちの 1 件をカテゴリ＋ブランチの委任に変える）だけが書く
    .lab/flows/<name>.json    手順の状態（flow.py。git 管理）

承認は HEAD やコマンド全文には結び付かない。commit しても無効にならず、同じ種類の操作は期限内なら何度でも通る。
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path

from labkit._util import git, read_json, write_json_atomic

LAB_DIR = ".lab"
GITIGNORE = (
    "# labkit が生成。queue と delegations は手元だけの状態（flows/ と beats/ は git 管理）\nqueue/\ndelegations.json\n"
)
DELEGATABLE = {
    "git_push": "保護ブランチへの push・force push・リモートの削除",
    "git_tag": "git tag の作成・削除",
    "git_merge": "保護ブランチへの merge",
    "gh_merge": "gh pr merge",
    "gh_release": "gh release の作成・変更",
    "raw_freeze": "labkit raw freeze（生データの確定）",
    "flow": "labkit flow advance の承認段階（承認を待たずに進む）",
    "raw_write": "data/raw へのファイルの移動・追加（生データの搬入。削除は含まない）",
    "lab_toml": "lab.toml の編集",
}
GROUPS = {
    "release": ["git_push", "git_tag", "git_merge", "gh_merge", "gh_release"],
    "migrate": ["flow", "raw_write", "raw_freeze", "lab_toml"],
    "all": list(DELEGATABLE),
}


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


def request(root: Path, category: str, command: str, *, cwd: Path, reason: str, session: str = "") -> dict:
    """承認待ちを積む（同じカテゴリ・同じコマンドが pending ならそれを返す）."""
    for it in list_queue(root):
        if it.get("kind") == "approval" and it.get("status") == "pending" and it.get("command") == command:
            return it
    item = {
        "id": _next_id(root),
        "kind": "approval",
        "status": "pending",
        "category": category,
        "command": command,
        "cwd": str(cwd),
        "branch": git_branch(cwd),
        "head": git(cwd, "rev-parse", "HEAD"),
        "log": (git(cwd, "log", "--oneline", "-3") or "").replace("\n", " / "),
        "reason": reason,
        "created": _iso(_now()),
        "session_id": session_id(session),
    }
    save_item(root, item)
    return item


def ask_question(root: Path, question: str, *, options: list[str], assumed: str, impact: str = "") -> dict:
    item = {
        "id": _next_id(root),
        "kind": "question",
        "status": "open",
        "question": question,
        "options": options,
        "assumed": assumed,
        "impact": impact,
        "answer": None,
        "created": _iso(_now()),
        "session_id": session_id(),
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
    """Claude が「対応済み」にする（回答を取り込んだ／承認済みの操作を実行した／却下を確認した）."""
    it = get_item(root, qid)
    it.update(status="done", done=_iso(_now()))
    save_item(root, it)
    return it


def approve(root: Path, qid: str, *, ttl_hours: float) -> dict:
    """承認 = その承認待ちのカテゴリを、そのブランチで ttl の間だけ委任する."""
    it = get_item(root, qid)
    if it.get("kind") != "approval" or it.get("status") != "pending":
        raise ValueError(
            f"{qid} は pending の承認待ちではありません（kind={it.get('kind')}, status={it.get('status')}）"
        )
    category = it.get("category") or _infer_category(root, it)
    d = add_delegation(root, [category], hours=ttl_hours, branch=it.get("branch"), note=f"approve {qid}")
    it.update(status="approved", approved=_iso(_now()), delegation=d["id"], category=category)
    save_item(root, it)
    return d


def _infer_category(root: Path, it: dict) -> str:
    """v0.x の承認待ち（category が無い）は、記録されたコマンドから種類を引き直す."""
    from labkit import gate
    from labkit.config import load_lab

    protected = load_lab(root)["gate"]["protected_branches"]
    hits = [h for h in gate.classify(it.get("command", ""), protected, it.get("branch")) if h.category in gate.GATED]
    if not hits:
        raise ValueError(
            f"{it['id']} の操作の種類をコマンドから判定できません: `{it.get('command', '')}`。"
            f"`labkit reject {it['id']}` で閉じ、必要なら `labkit delegate <カテゴリ> --hours N` で委任してください"
            f"（カテゴリ: {', '.join(gate.GATED)}）"
        )
    return hits[0].category


def reject(root: Path, qid: str, note: str = "") -> dict:
    it = get_item(root, qid)
    if it.get("status") not in ("pending", "approved"):
        raise ValueError(f"{qid} は {it.get('status')} です")
    if it.get("delegation"):
        revoke_delegation(root, it["delegation"])
    it.update(status="rejected", rejected=_iso(_now()), note=note)
    save_item(root, it)
    return it


def pending_summary(root: Path) -> dict[str, list[dict]]:
    q = list_queue(root)
    return {
        "pending": [i for i in q if i.get("kind") == "approval" and i.get("status") == "pending"],
        "approved": [i for i in q if i.get("kind") == "approval" and i.get("status") == "approved"],
        "rejected": [i for i in q if i.get("kind") == "approval" and i.get("status") == "rejected"],
        "open_questions": [i for i in q if i.get("kind") == "question" and i.get("status") == "open"],
        "answered": [i for i in q if i.get("kind") == "question" and i.get("status") == "answered"],
    }


# ---- 委任 ----
def expand(names: list[str]) -> list[str]:
    out: list[str] = []
    for n in names:
        if n in GROUPS:
            out += GROUPS[n]
        elif n in DELEGATABLE:
            out.append(n)
        else:
            raise ValueError(f"委任できないカテゴリ: {n!r}（使えるもの: {', '.join([*DELEGATABLE, *GROUPS])}）")
    return list(dict.fromkeys(out))


def list_delegations(root: Path) -> list[dict]:
    p = root / LAB_DIR / "delegations.json"
    try:
        return list(read_json(p)["items"]) if p.is_file() else []
    except (json.JSONDecodeError, OSError, KeyError):
        return []


def _active(d: dict) -> bool:
    try:
        return not d.get("revoked_at") and _dt.datetime.fromisoformat(d["expires_at"]) >= _now()
    except (KeyError, ValueError):
        return False


def active_delegations(root: Path) -> list[dict]:
    return [d for d in list_delegations(root) if _active(d)]


def find_delegation(root: Path, category: str, branch: str | None = None) -> dict | None:
    """category を含み、ブランチ限定なら branch が一致する有効な委任."""
    for d in active_delegations(root):
        if category in d["categories"] and (not d.get("branch") or d["branch"] == branch):
            return d
    return None


def add_delegation(
    root: Path, categories: list[str], *, hours: float, branch: str | None = None, note: str = ""
) -> dict:
    items = list_delegations(root)
    now = _now()
    d = {
        "id": f"D{len(items) + 1:03d}",
        "categories": expand(categories),
        "branch": branch,
        "note": note,
        "granted_at": _iso(now),
        "expires_at": _iso(now + _dt.timedelta(hours=hours)),
        "revoked_at": None,
    }
    write_json_atomic(lab_dir(root) / "delegations.json", {"items": [*items, d]})
    return d


def revoke_delegation(root: Path, did: str) -> list[dict]:
    items = list_delegations(root)
    hit = [d for d in items if (did == "all" or d["id"] == did) and _active(d)]
    if not hit:
        raise FileNotFoundError(f"有効な委任 {did} がありません（`labkit delegate list`）")
    for d in hit:
        d["revoked_at"] = _iso(_now())
    write_json_atomic(lab_dir(root) / "delegations.json", {"items": items})
    return hit


def describe_delegation(d: dict) -> str:
    scope = f"、ブランチ {d['branch']}" if d.get("branch") else ""
    return f"{d['id']}: {', '.join(d['categories'])}（期限 {d['expires_at']}{scope}" + (
        f"、{d['note']}）" if d.get("note") else "）"
    )
