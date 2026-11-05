"""長い自律運用の 1 拍の入口（labkit beat）。要約で指示が薄れても、現行の目標と指示書を機械が指す.

    prompts/current.toml      goal = "goal_v8.md"  beat = "beat_v3.md"  interval = "20m"（現行の版。人かエージェントが更新）
    labkit beat start         現行の goal / beat の本文と状態（終わった run・queue・主張）を出し、拍の開始を記録する
    labkit beat end --predicted ... --observed ... --decided ...   拍の 3 行を記録し、開発ログの自動ブロックに写す
    labkit beat log [--date]  その日の拍（人間が思考の流れを追う）

記録は .lab/beats/YYYY-MM-DD.jsonl（git 管理）。時刻は機械が入れる（手書きの時刻はずれる）。
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path

from labkit._util import now_iso, sha256_file, write_text_atomic
from labkit.config import read_toml

CURRENT = "prompts/current.toml"
BEATS_DIR = ".lab/beats"
VERSION_RE = re.compile(r"^(.*)_v(\d+)\.md$")


def current(root: Path) -> dict | None:
    p = root / CURRENT
    return read_toml(p) if p.is_file() else None


def newer_version(root: Path, name: str) -> str | None:
    """同じ用途でより大きい版番号のファイルがあればその名前."""
    m = VERSION_RE.match(name)
    if not m:
        return None
    stem, v = m.group(1), int(m.group(2))
    cands = [
        (int(mm.group(2)), p.name) for p in (root / "prompts").glob(f"{stem}_v*.md") if (mm := VERSION_RE.match(p.name))
    ]
    best = max(cands, default=(v, name))
    return best[1] if best[0] > v else None


def check_current(root: Path) -> list[tuple[str, str, str]]:
    """L005: current.toml が指すファイルが無い、またはより新しい版がある（警告）."""
    cur = current(root)
    if cur is None:
        return []
    issues = []
    for key in ("goal", "beat"):
        name = cur.get(key)
        if not name:
            issues.append(("L005", CURRENT, f"{key} がありません"))
            continue
        if not (root / "prompts" / name).is_file():
            issues.append(("L005", CURRENT, f"{key} = {name} が prompts/ にありません"))
        elif newer := newer_version(root, name):
            issues.append(("L005", CURRENT, f"{key} = {name} より新しい {newer} があります（現行ならそちらを指す）"))
    return issues


def _beats_file(root: Path, date: str | None = None) -> Path:
    return root / BEATS_DIR / f"{date or _dt.date.today().isoformat()}.jsonl"


def read_beats(root: Path, date: str | None = None) -> list[dict]:
    p = _beats_file(root, date)
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()] if p.is_file() else []


def _append(root: Path, rec: dict) -> None:
    p = _beats_file(root)
    text = p.read_text(encoding="utf-8") if p.is_file() else ""
    write_text_atomic(p, text + json.dumps(rec, ensure_ascii=False) + "\n")


def status_lines(root: Path) -> list[str]:
    """拍の最初に見る状態（既存の一覧を再利用する）."""
    from labkit import state
    from labkit.claims import list_claims
    from labkit.runs import list_runs

    today = _dt.date.today().isoformat()
    runs = [m for m in list_runs(root) if str(m.get("created", "")).startswith(today)]
    by = {}
    for m in runs:
        by[m.get("status")] = by.get(m.get("status"), 0) + 1
    s = state.pending_summary(root)
    lines = ["- 今日の run: " + (", ".join(f"{k} {v}" for k, v in sorted(by.items())) or "なし")]
    running = [m for m in list_runs(root) if m.get("status") == "running"]
    if running:
        lines.append("- 実行中: " + ", ".join(m["run_id"] for m in running[:5]))
    lines += [f"- 回答あり #{it['id']}: {it.get('answer')}" for it in s["answered"]]
    lines += [f"- 未回答 #{it['id']}: {it.get('question')}（仮: {it.get('assumed')}）" for it in s["open_questions"]]
    claims = list_claims(root, "open")
    lines.append(f"- open な主張: {len(claims)} 件（`labkit claim list`）")
    return lines


def start(root: Path) -> str:
    cur = current(root)
    if cur is None:
        raise FileNotFoundError(f'{CURRENT} がありません（goal = "goal_v1.md"、beat = "beat_v1.md" を書く）')
    beats = read_beats(root)
    n = len([b for b in beats if b.get("event") == "start"]) + 1
    last = next((b for b in reversed(beats) if b.get("event") == "end"), None)
    parts = []
    for key in ("goal", "beat"):
        p = root / "prompts" / str(cur.get(key, ""))
        if not p.is_file():
            raise FileNotFoundError(f"{CURRENT} の {key} = {cur.get(key)} が prompts/ にありません")
        parts.append((key, p))
    _append(root, {"event": "start", "beat": n, "time": now_iso(), **{f"{k}_file": p.name for k, p in parts}})
    out = [
        f"# 拍 {n}（{_dt.datetime.now().strftime('%H:%M')}）: "
        + " / ".join(f"{k} {p.name} {sha256_file(p)[:7]}" for k, p in parts)
    ]
    if last:
        out.append(f"- 前の拍 {last.get('beat')} の判断: {last.get('decided') or '（未記入）'}")
    out += status_lines(root)
    for k, p in parts:
        out += ["", f"## {k}: prompts/{p.name}", "", p.read_text(encoding="utf-8").rstrip()]
    return "\n".join(out)


def end(
    root: Path, *, predicted: str = "", observed: str = "", decided: str = "", runs: list[str] | None = None
) -> dict:
    beats = read_beats(root)
    n = max((b.get("beat", 0) for b in beats), default=0) or 1
    rec = {"event": "end", "beat": n, "time": now_iso(), "predicted": predicted, "observed": observed}
    rec.update(decided=decided, runs=runs or [])
    _append(root, rec)
    from labkit.devlog import update

    update(root)
    return rec


def beats_block(root: Path, date: str) -> list[str]:
    """開発ログの自動ブロックに入れる「拍（自動）」: 1 拍 3 行."""
    ends = [b for b in read_beats(root, date) if b.get("event") == "end"]
    if not ends:
        return []
    lines = ["## 拍（自動。`labkit beat end` の記録）", ""]
    for b in ends:
        t = b.get("time", "")[11:16]
        lines.append(
            f"- 拍 {b.get('beat')}（{t}）予想: {b.get('predicted') or '—'} / 結果: {b.get('observed') or '—'} / 判断: {b.get('decided') or '—'}"
        )
        if b.get("runs"):
            lines.append("  run: " + ", ".join(b["runs"]))
    return lines + [""]


def log(root: Path, date: str | None = None) -> str:
    lines = beats_block(root, date or _dt.date.today().isoformat())
    return "\n".join(lines[2:]) if lines else "拍の記録はありません"


def session_lines(root: Path, *, compact: bool = False) -> list[str]:
    """SessionStart に入れる 1〜2 行。compact 後は目標の最初の節を原文で戻す（要約で薄れた指示の再注入）."""
    cur = current(root)
    if cur is None:
        return []
    goal = root / "prompts" / str(cur.get("goal", ""))
    beat = root / "prompts" / str(cur.get("beat", ""))
    line = f"- 自律運用: goal {goal.name}、beat {beat.name}、間隔 {cur.get('interval', '?')}（{CURRENT}。拍は `labkit beat start` → `labkit beat end`）"
    lines = [line]
    last = next((b for b in reversed(read_beats(root)) if b.get("event") == "end"), None)
    if last:
        lines.append(
            f"- 最後の拍 {last.get('beat')}（{last.get('time', '')[11:16]}）の判断: {last.get('decided') or '（未記入）'}"
        )
    if compact and goal.is_file():
        text = goal.read_text(encoding="utf-8")
        m = re.search(r"^##\s.+?$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
        body = (m.group(0) if m else text).strip().splitlines()[:20]
        lines.append("- 目標の冒頭（要約で消えないよう原文）:\n  " + "\n  ".join(body))
    return lines


def ensure_current(root: Path, goal: str, beat: str, interval: str = "20m") -> Path:
    p = root / CURRENT
    write_text_atomic(
        p,
        f'# 現行の版（labkit beat が読む。改訂したらここを更新する）\ngoal = "{goal}"\nbeat = "{beat}"\ninterval = "{interval}"\n',
    )
    return p


__all__ = [
    "check_current",
    "current",
    "start",
    "end",
    "log",
    "read_beats",
    "beats_block",
    "session_lines",
    "ensure_current",
]
