"""主張の台帳（docs/claims.md）。何を主張し、何を撤回し、根拠が今も立っているかを 1 表で持つ.

    labkit claim add "焦点の損失は 13 % で既知の則と一致" --evidence <run>:loss_pct:%:1 --note prereg:design-rule
    labkit claim retract C003 --reason "dirty な run の再実行で 9 % に下がった"
    labkit claim list [--status open|retracted]

| ID | 日付 | 主張 | 根拠 | 状態 | 備考 |
根拠は `labkit cite` の書式（L033 が metrics と照合する）。状態は open / retracted の 2 値。
「支持されているか」は保存せず、check のたびに根拠の run の状態（dirty・failed・退避・欠落）から判定する（L036）。
"""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path

from labkit._util import write_text_atomic

CLAIMS_FILE = "docs/claims.md"
HEADER = (
    "# 主張の台帳\n\n`labkit claim add / retract` で書く（手で編集しない）。根拠は `値 [run:<id>:<key>]`、"
    "状態は open / retracted。根拠の run が dirty・failed・退避済みになると `labkit check` L036 が知らせる。\n\n"
    "| ID | 日付 | 主張 | 根拠 | 状態 | 備考 |\n|---|---|---|---|---|---|\n"
)
ROW_RE = re.compile(r"^\|\s*(C\d{3,})\s*\|\s*(\S*)\s*\|(.*?)\|(.*?)\|\s*(\w[\w-]*)\s*\|(.*)\|\s*$")
STATUSES = ("open", "retracted")


def _path(root: Path) -> Path:
    return root / CLAIMS_FILE


def _cell(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("|", "/")).strip()


def list_claims(root: Path, status: str | None = None) -> list[dict]:
    p = _path(root)
    out = []
    for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if p.is_file() else []:
        if m := ROW_RE.match(line):
            cid, date, text, evidence, st, note = m.groups()
            row = {"id": cid, "date": date, "text": text.strip(), "evidence": evidence.strip()}
            row.update(status=st, note=note.strip(), line=n)
            if status is None or st == status:
                out.append(row)
    return out


def run_problem(meta: dict | None) -> str:
    """根拠にできない理由（空なら使える）: runs/ に無い / status / 退避済み / dirty。add_claim と L036 が同じ基準を使う."""
    if meta is None or meta.get("status") is None:
        return "runs/ に無い"
    if meta.get("status") != "finished":
        return f"status={meta['status']}"
    if meta.get("archived"):
        return "退避済み"
    if (meta.get("git") or {}).get("dirty"):
        return "dirty"
    return ""


def _evidence(root: Path, spec: str, runs: dict, comp_keys: set[str] = frozenset()) -> str:
    """ "<run>:<key>[:<unit>][:<digits>]" → `値 単位 [run:<id>:<key>]`（labkit cite）。位置で読む（単位を省くなら `::<digits>`）."""
    from labkit.check import cite
    from labkit.runs import find_run

    parts = spec.split(":", 3)
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError(f"根拠は <run_id>:<key>[:<unit>][:<digits>] の形: {spec!r}")
    run_id, key, *rest = parts
    unit = rest[0] if rest else ""
    if len(rest) > 1 and rest[1] and not rest[1].isdigit():
        raise ValueError(f"桁数は整数: {spec!r}（単位を省くなら <run>:<key>::<digits>）")
    digits = int(rest[1]) if len(rest) > 1 and rest[1] else None
    rid = find_run(run_id, root).name
    if bad := run_problem(runs.get(rid)):
        raise ValueError(
            f"根拠 run {rid} は {bad}。clean に再実行してから主張にする（dirty・failed・退避済みの結果は主張にしない）"
        )
    if key in comp_keys:
        from labkit.compare import comparison_problem

        if why := comparison_problem(runs[rid]["_dir"], key):
            raise ValueError(f"根拠 run {rid}: {why}。比較は 1 軸だけを変える（run.compare で宣言して再実行）")
    return cite(rid, key, digits=digits, unit=unit, root=root)


def add_claim(root: Path, text: str, evidence: list[str], *, note: str = "") -> dict:
    if not text.strip():
        raise ValueError("主張の文が空です")
    if not evidence:
        raise ValueError("根拠（--evidence <run_id>:<key>）を 1 つ以上付ける。run に無い量は主張にしない")
    from labkit.check import run_index
    from labkit.compare import comparison_keys
    from labkit.config import load_lab

    runs = run_index(root)
    comp_keys = comparison_keys(root, load_lab(root), runs)
    cells = "; ".join(_evidence(root, e, runs, comp_keys) for e in evidence)
    rows = list_claims(root)
    cid = f"C{(max((int(r['id'][1:]) for r in rows), default=0) + 1):03d}"
    p = _path(root)
    text_all = p.read_text(encoding="utf-8") if p.is_file() else HEADER
    if "| ID | 日付 |" not in text_all:
        raise ValueError(f"{CLAIMS_FILE} に台帳の表（| ID | 日付 | …）がありません。別の文書なら移してから使う")
    row = f"| {cid} | {_dt.date.today().isoformat()} | {_cell(text)} | {_cell(cells)} | open | {_cell(note)} |"
    write_text_atomic(p, text_all.rstrip("\n") + "\n" + row + "\n")
    return {"id": cid, "text": text, "evidence": cells, "status": "open", "note": note}


def retract_claim(root: Path, cid: str, reason: str) -> dict:
    if not reason.strip():
        raise ValueError("撤回の理由（--reason）が必要です。撤回は成果なので理由を残す")
    p = _path(root)
    rows = {r["id"]: r for r in list_claims(root)}
    if cid not in rows:
        raise ValueError(f"{cid} は台帳にありません（`labkit claim list`）")
    if rows[cid]["status"] == "retracted":
        raise ValueError(f"{cid} は撤回済みです")
    lines = p.read_text(encoding="utf-8").splitlines()
    r = rows[cid]
    note = "; ".join(x for x in (r["note"], f"撤回 {_dt.date.today().isoformat()}: {_cell(reason)}") if x)
    lines[r["line"] - 1] = f"| {cid} | {r['date']} | {r['text']} | {r['evidence']} | retracted | {note} |"
    write_text_atomic(p, "\n".join(lines) + "\n")
    return {**r, "status": "retracted", "note": note}


def format_claims(rows: list[dict]) -> str:
    return "\n".join(f"{r['id']}  [{r['status']}]  {r['text']}  ← {r['evidence']}" for r in rows) or "主張はありません"


def check_claims(root: Path, lab: dict) -> list[tuple[str, str, str, str]]:
    """L036: 行の書式、撤回の理由、open な主張の根拠（欠落・dirty・failed・退避済みは error）."""
    from labkit.check import CITE_RE, RUN_ID_RE, run_index

    p = _path(root)
    if not p.is_file():
        return []
    issues: list[tuple[str, str, str, str]] = []
    runs = None
    for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not line.startswith("| C"):
            continue
        m = ROW_RE.match(line)
        where = f"{CLAIMS_FILE}:{n}"
        if not m:
            issues.append(("L036", where, "行の書式が台帳と違います（`labkit claim add` で書く）", "error"))
            continue
        cid, _, _, evidence, st, note = m.groups()
        if st not in STATUSES:
            issues.append(("L036", where, f"{cid} の状態は {STATUSES} のいずれか: {st!r}", "error"))
        if st == "retracted" and "撤回" not in note:
            issues.append(
                ("L036", where, f"{cid} は撤回の理由がありません（`labkit claim retract --reason`）", "error")
            )
        if st != "open":
            continue
        if not CITE_RE.search(evidence):
            issues.append(("L036", where, f"{cid} の根拠が `値 [run:<id>:<key>]` の書式ではありません", "error"))
        runs = run_index(root) if runs is None else runs
        for rid in set(RUN_ID_RE.findall(evidence)):
            if bad := run_problem(runs.get(rid)):
                issues.append(
                    (
                        "L036",
                        where,
                        f"{cid} の根拠 run {rid} は {bad}。clean に再実行して根拠を差し替えるか `labkit claim retract`",
                        "error",
                    )
                )
    return issues
