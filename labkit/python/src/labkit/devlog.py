"""開発ログ（docs/devlog/YYYY-MM-DD.md）。機械で埋まる欄は機械が埋める.

`labkit devlog` は今日のファイルを雛形から作り、`<!-- labkit:auto -->` 〜 `<!-- /labkit:auto -->` の間
（変更ファイル・今日の run・check の結果）を git と runs/ から作り直す。人が書くのは 目的 / 結果・観察 / 判断と理由 / 未解決 だけ。
"""

from __future__ import annotations

import datetime as _dt
import re
from importlib import resources
from pathlib import Path

from labkit._util import git, write_text_atomic
from labkit.config import load_lab

AUTO_START, AUTO_END = "<!-- labkit:auto -->", "<!-- /labkit:auto -->"


def devlog_path(root: Path, date: str | None = None) -> Path:
    return root / load_lab(root)["devlog"]["dir"] / f"{date or _dt.date.today().isoformat()}.md"


def auto_block(root: Path, date: str) -> str:
    from labkit.runs import list_runs

    commits = git(root, "log", "--oneline", f"--since={date} 00:00", f"--until={date} 23:59:59") or ""
    status = git(root, "status", "--porcelain", "--untracked-files=all") or ""
    lines = [AUTO_START, f"## 変更ファイル（自動、{_dt.datetime.now().strftime('%H:%M')} 時点）", ""]
    lines += [f"- commit: {c}" for c in commits.splitlines()] or ["- 今日の commit はありません"]
    lines += [f"- 未コミット: {s[3:]}" for s in status.splitlines()[:30]]
    if len(status.splitlines()) > 30:
        lines.append(f"- …ほか {len(status.splitlines()) - 30} 件")
    lines += ["", "## 実行した run（自動）", ""]
    runs = [m for m in list_runs(root) if str(m.get("created", "")).startswith(date)]
    for m in runs:
        keys = ", ".join(sorted((m.get("tags") or {}).keys()))
        dirty = " dirty" if (m.get("git") or {}).get("dirty") else ""
        lines.append(
            f"- {m['run_id']}  {m.get('status')}  {m.get('duration_s') or '-'} s{dirty}"
            + (f"  tags: {keys}" if keys else "")
        )
    if not runs:
        lines.append("- 今日の run はありません")
    lines += ["", AUTO_END]
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
