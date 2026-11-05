"""開発ログ（docs/devlog/YYYY-MM-DD.md）。機械で埋まる欄は機械が埋める.

`labkit devlog` は今日のファイルを雛形から作り、`<!-- labkit:auto -->` 〜 `<!-- /labkit:auto -->` の間
（変更ファイル・今日の run・check の結果）を git と runs/ から作り直す。人が書くのは 目的 / 結果・観察 / 判断と理由 / 未解決 だけ。
"""

from __future__ import annotations

import datetime as _dt
import re
from importlib import resources
from pathlib import Path

from labkit._util import git, git_status, write_text_atomic
from labkit.config import load_lab

AUTO_START, AUTO_END = "<!-- labkit:auto -->", "<!-- /labkit:auto -->"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # git の空の tree（差分の基準が無いとき）


def devlog_path(root: Path, date: str | None = None) -> Path:
    return root / load_lab(root)["devlog"]["dir"] / f"{date or _dt.date.today().isoformat()}.md"


def code_volume(root: Path, since: str) -> str:
    """コード量の 1 行: src/scripts/tests の行数（空行を除く）、since（日付か commit）からの増減（同じく空行を除く）、上限超えの数."""
    from labkit.check import SKIP_DIRS, count_code_lines

    lab = load_lab(root)
    limit = int(lab["check"]["max_file_lines"])
    base = (
        git(root, "rev-list", "-1", f"--before={since}", "HEAD")
        if not re.fullmatch(r"[0-9a-f]{7,40}", since)
        else since
    )
    base = base or EMPTY_TREE  # その日より前の commit が無い（新しいリポジトリ）なら全部が増分
    diff = git(root, "diff", "-U0", "--no-color", base, "--", "src", "scripts", "tests") or ""
    delta: dict[str, int] = {}
    top = ""
    for ln in diff.splitlines():  # 増減も空行を除いて数える（総行数と同じ定義）
        if ln.startswith("+++ "):
            path = ln[6:] if ln.startswith("+++ b/") else ""
            top = path.split("/", 1)[0] if path.endswith(".py") else ""
        elif top and ln[:1] in "+-" and not ln.startswith(("+++", "---")) and ln[1:].strip():
            delta[top] = delta.get(top, 0) + (1 if ln[0] == "+" else -1)
    for xy, path in git_status(root):  # 未追跡の .py は diff に出ない
        if xy == "??" and path.endswith(".py") and path.split("/", 1)[0] in ("src", "scripts", "tests"):
            delta[path.split("/", 1)[0]] = delta.get(path.split("/", 1)[0], 0) + count_code_lines(root / path)
    parts, over = [], 0
    for d in ("src", "scripts", "tests"):
        files = [p for p in (root / d).rglob("*.py") if not set(p.parts) & SKIP_DIRS] if (root / d).is_dir() else []
        n = sum(count_code_lines(p) for p in files)
        if d != "tests" and limit > 0:
            over += sum(1 for p in files if count_code_lines(p) > limit)
        parts.append(f"{d} {n:,} 行（{delta.get(d, 0):+d}、{len(files)} ファイル）")
    return "- コード量: " + " / ".join(parts) + (f"、{limit} 行超 {over} 本" if limit > 0 else "")


def auto_block(root: Path, date: str) -> str:
    from labkit.beat import beats_block
    from labkit.runs import list_runs

    commits = git(root, "log", "--oneline", f"--since={date} 00:00", f"--until={date} 23:59:59") or ""
    status = git_status(root)
    lines = [AUTO_START, f"## 変更ファイル（自動、{_dt.datetime.now().strftime('%H:%M')} 時点）", ""]
    lines += [f"- commit: {c}" for c in commits.splitlines()] or ["- 今日の commit はありません"]
    lines += [f"- 未コミット: {p}" for _, p in status[:30]]
    if len(status) > 30:
        lines.append(f"- …ほか {len(status) - 30} 件")
    lines.append(code_volume(root, f"{date} 00:00"))
    lines += ["", "## 実行した run（自動）", ""]
    runs = [m for m in list_runs(root, include_archived=True) if str(m.get("created", "")).startswith(date)]
    for m in runs:  # 退避した run もその日の記録としては残す（印を付ける）
        keys = ", ".join(sorted((m.get("tags") or {}).keys()))
        dirty = (" dirty" if (m.get("git") or {}).get("dirty") else "") + (" archived" if m.get("archived") else "")
        pr = m.get("prediction_result") or {}
        verdict = f"  予想: {pr.get('verdict')}" + ("（自己申告）" if pr.get("self_reported") else "") if pr else ""
        lines.append(
            f"- {m['run_id']}  {m.get('status')}  {m.get('duration_s') or '-'} s{dirty}"
            + (f"  tags: {keys}" if keys else "")
            + verdict
        )
    if not runs:
        lines.append("- 今日の run はありません")
    lines += ["", *beats_block(root, date), AUTO_END]
    return "\n".join(lines)


def update(root: Path, date: str | None = None) -> Path:
    date = date or _dt.date.today().isoformat()
    p = devlog_path(root, date)
    if p.exists():
        text = p.read_text(encoding="utf-8")
    else:
        text = (
            resources.files("labkit.templates")
            .joinpath("devlog.md")
            .read_text(encoding="utf-8")
            .replace("{{date}}", date)
        )
    block = auto_block(root, date)
    pat = re.compile(re.escape(AUTO_START) + r".*?" + re.escape(AUTO_END), re.S)
    text = pat.sub(lambda _m: block, text, count=1) if pat.search(text) else text.rstrip("\n") + "\n\n" + block + "\n"
    write_text_atomic(p, text)
    return p


def section_bodies(text: str) -> dict[str, str]:
    """## 見出し → 本文（HTML コメントと自動ブロックを除いた、人が書いた部分）."""
    text = re.sub(re.escape(AUTO_START) + r".*?" + re.escape(AUTO_END), "", text, flags=re.S)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    out: dict[str, str] = {}
    cur = None
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            cur = m.group(1)
            out.setdefault(cur, "")
        elif cur is not None:
            out[cur] += line.strip() + "\n" if line.strip() else ""
    return out
