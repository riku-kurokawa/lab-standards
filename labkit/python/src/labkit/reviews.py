"""独立レビューの記録（docs/reviews/YYYY-MM-DD_<flow>_<stage>.md）.

frontmatter:
    reviewer: lab-reviewer
    flow: migrate
    stage: reproduce
    commit: <レビュー対象の HEAD（完全な sha）>
    verdict: pass | changes-requested
    findings:
      - "src/x.py:12 ..."

書き込みは hooks が agent_type=lab-reviewer のときだけ許可する（メインのエージェントは書けない）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REVIEW_DIR = "docs/reviews"
NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_([a-z0-9-]+)_([a-z0-9-]+)(?:_(\d+))?\.md$")
VERDICTS = ("pass", "changes-requested")
REQUIRED = ("reviewer", "flow", "stage", "commit", "verdict", "findings")


@dataclass
class Review:
    path: Path
    reviewer: str = ""
    flow: str = ""
    stage: str = ""
    commit: str = ""
    verdict: str = ""
    findings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def parse_frontmatter(text: str) -> dict | None:
    m = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.S)
    if not m:
        return None
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def load_review(path: Path) -> Review:
    r = Review(path)
    m = NAME_RE.match(path.name)
    if not m:
        r.errors.append("ファイル名は YYYY-MM-DD_<flow>_<stage>.md")
    fm = parse_frontmatter(path.read_text(encoding="utf-8"))
    if fm is None:
        r.errors.append("frontmatter（--- ... ---）がありません")
        return r
    missing = [k for k in REQUIRED if k not in fm]
    if missing:
        r.errors.append(f"frontmatter に不足: {missing}")
    r.reviewer = str(fm.get("reviewer", ""))
    r.flow = str(fm.get("flow", ""))
    r.stage = str(fm.get("stage", ""))
    r.commit = str(fm.get("commit", ""))
    r.verdict = str(fm.get("verdict", ""))
    f = fm.get("findings") or []
    r.findings = [str(x) for x in f] if isinstance(f, list) else [str(f)]
    if r.verdict not in VERDICTS:
        r.errors.append(f"verdict は {VERDICTS} のいずれか: {r.verdict!r}")
    if not re.fullmatch(r"[0-9a-f]{40}", r.commit):
        r.errors.append("commit は完全な 40 桁の sha（git rev-parse HEAD）")
    if m and (m.group(2) != r.flow or m.group(3) != r.stage):
        r.errors.append("ファイル名の flow/stage と frontmatter が一致しません")
    if r.verdict == "changes-requested" and not r.findings:
        r.errors.append("changes-requested には findings が必要です")
    return r


def list_reviews(root: Path, flow: str | None = None, stage: str | None = None) -> list[Review]:
    d = root / REVIEW_DIR
    if not d.is_dir():
        return []
    out = [load_review(p) for p in sorted(d.glob("*.md"))]
    return [r for r in out if (flow is None or r.flow == flow) and (stage is None or r.stage == stage)]


def latest_pass(root: Path, flow: str, stage: str, head: str | None) -> Review | None:
    """現在の HEAD に対する verdict=pass のレビュー記録（最新）."""
    for r in reversed(list_reviews(root, flow, stage)):
        if not r.errors and r.verdict == "pass" and head and r.commit == head:
            return r
    return None


def template(flow: str, stage: str, commit: str) -> str:
    return (
        "---\n"
        "reviewer: lab-reviewer\n"
        f"flow: {flow}\n"
        f"stage: {stage}\n"
        f"commit: {commit}\n"
        "verdict: changes-requested   # pass | changes-requested\n"
        "findings:\n"
        "  - \"<path>:<line> 指摘（根拠）\"\n"
        "---\n\n"
        f"# レビュー: {flow} / {stage}\n\n"
        "## 概要\n\n## labkit check\n\n## 要修正\n\n## 確認推奨\n\n## 問題なし\n"
    )
