"""独立レビューの記録（docs/reviews/YYYY-MM-DD_<flow>_<stage>.md）.

frontmatter:
    reviewer: lab-reviewer
    flow: migrate
    stage: reproduce
    commit: <レビュー対象の HEAD（完全な sha）>
    verdict: pass | changes-requested
    summary: <人間向けの 1 行（120 字以内）。無いと L035 の警告>
    resolves: docs/reviews/2026-11-04_adhoc_review.md   # 前回の記録への再レビューなら（任意）
    findings:
      - "must: src/x.py:12 ..."      # must:（要修正）/ should:（確認推奨）。接頭辞が無ければ must 扱い

書き込みは hooks が agent_type=lab-reviewer のときだけ許可する（メインのエージェントは書けない）。
`labkit review list [--open]` が 1 件 1 行で出す（--open は後続の pass が無い changes-requested だけ）。
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
SUMMARY_MAX = 120
SUMMARY_SINCE = "2026-11-05"  # これより前の記録に summary の警告は出さない（v1.6.0 で導入）


@dataclass
class Review:
    path: Path
    reviewer: str = ""
    flow: str = ""
    stage: str = ""
    commit: str = ""
    verdict: str = ""
    summary: str = ""
    resolves: str = ""
    findings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def date(self) -> str:
        m = NAME_RE.match(self.path.name)
        return m.group(1) if m else ""

    @property
    def counts(self) -> tuple[int, int]:
        """(must, should)。接頭辞の無い指摘は must."""
        should = sum(1 for f in self.findings if f.lower().startswith("should:"))
        return len(self.findings) - should, should


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
    r.summary = str(fm.get("summary") or "").strip()
    r.resolves = str(fm.get("resolves") or "").strip()
    if not r.summary and ("summary" in fm or r.date >= SUMMARY_SINCE):  # 古い記録（キーも無い）は責めない
        r.warnings.append(f"summary（人間向けの 1 行、{SUMMARY_MAX} 字以内）がありません")
    elif len(r.summary) > SUMMARY_MAX:
        r.warnings.append(f"summary が {len(r.summary)} 字（{SUMMARY_MAX} 字以内）")
    if r.resolves and not (path.parent.parent.parent / r.resolves).is_file():
        r.errors.append(f"resolves が指す記録 {r.resolves} がありません")
    return r


def list_reviews(root: Path, flow: str | None = None, stage: str | None = None) -> list[Review]:
    d = root / REVIEW_DIR
    if not d.is_dir():
        return []
    out = [load_review(p) for p in sorted(d.glob("*.md"))]
    return [r for r in out if (flow is None or r.flow == flow) and (stage is None or r.stage == stage)]


def open_reviews(root: Path) -> list[Review]:
    """未解消の changes-requested: 後続の記録に resolves で指されておらず、同じ flow/stage の後続の記録も無いもの
    （同じ対象を見直した新しい記録が、古い指摘の現在の状態。8 回のレビューの鎖を 8 行並べない）."""
    rs = list_reviews(root)
    resolved = {r.resolves for r in rs if r.resolves}
    out = []
    for i, r in enumerate(rs):
        if r.verdict != "changes-requested" or r.path.relative_to(root).as_posix() in resolved:
            continue
        if any((s.flow, s.stage) == (r.flow, r.stage) for s in rs[i + 1 :]):
            continue
        out.append(r)
    return out


def format_reviews(root: Path, rs: list[Review]) -> str:
    rows = []
    for r in rs:
        must, should = r.counts
        rows.append(
            f"{r.date}  {r.flow}/{r.stage:10s} {r.verdict:17s} must {must} should {should}  {r.summary or '（summary なし）'}"
            + (f"  ← {r.resolves}" if r.resolves else "")
            + f"  [{r.path.relative_to(root).as_posix()}]"
        )
    return "\n".join(rows) or "レビュー記録はありません"


def latest_pass(root: Path, flow: str, stage: str, head: str | None) -> Review | None:
    """現在の HEAD に対する verdict=pass のレビュー記録（最新）."""
    for r in reversed(list_reviews(root, flow, stage)):
        if not r.errors and r.verdict == "pass" and head and r.commit == head:
            return r
    return None


def template(flow: str, stage: str, commit: str, resolves: Review | None = None) -> str:
    prev = ""
    if resolves is not None:
        prev = "\n## 前回の指摘への対応\n\n| # | 前回の指摘 | 対応 |\n|---|---|---|\n" + "".join(
            f"| {i} | {f.replace('|', '/')} | |\n" for i, f in enumerate(resolves.findings, 1)
        )
    return (
        "---\n"
        "reviewer: lab-reviewer\n"
        f"flow: {flow}\n"
        f"stage: {stage}\n"
        f"commit: {commit}\n"
        "verdict: changes-requested   # pass | changes-requested\n"
        'summary: ""                   # 人間向けの 1 行（120 字以内）: 何を見て、何が主な問題か\n'
        + (f"resolves: {resolves.path.as_posix()}\n" if resolves is not None else "")
        + "findings:\n"
        '  - "must: <path>:<line> 要修正の指摘（根拠）"\n'
        '  - "should: <path>:<line> 確認推奨（人間の判断）"\n'
        "---\n\n"
        f"# レビュー: {flow} / {stage}\n\n"
        "## 概要\n\n## labkit check\n\n（`labkit check --claims` の出力をそのまま貼る）\n"
        + prev
        + "\n## 要修正\n\n## 確認推奨\n\n## 問題なし\n"
    )
