"""生データ（data/raw）の凍結と検証.

MANIFEST.sha256 の書式（1 行 1 ファイル、sha256sum 互換に size を追加）:
    <sha256>  <size>  <data/raw からの相対パス>
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from labkit._util import now_iso, sha256_file
from labkit.paths import datapath

MANIFEST = "MANIFEST.sha256"
IGNORE = {MANIFEST, ".gitkeep", "README.md"}


def _files(raw: Path) -> list[Path]:
    return sorted(p for p in raw.rglob("*") if p.is_file() and p.name not in IGNORE and not p.name.startswith("."))


def read_manifest(raw: Path) -> dict[str, tuple[str, int]]:
    mf = raw / MANIFEST
    out: dict[str, tuple[str, int]] = {}
    if not mf.is_file():
        return out
    for line in mf.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        digest, size, rel = line.split(None, 2)
        out[rel] = (digest, int(size))
    return out


def freeze(root: Path | None = None, chmod: bool = True, progress=print) -> Path:
    """未登録ファイルを MANIFEST に追加し、読み取り専用にする。既存行は変更しない."""
    raw = datapath("raw", root=root)
    raw.mkdir(parents=True, exist_ok=True)
    known = read_manifest(raw)
    lines = [f"{d}  {s}  {r}" for r, (d, s) in known.items()]
    added = 0
    for p in _files(raw):
        rel = str(p.relative_to(raw))
        if rel in known:
            continue
        progress(f"hash: {rel}")
        lines.append(f"{sha256_file(p)}  {p.stat().st_size}  {rel}")
        added += 1
    mf = raw / MANIFEST
    if mf.exists():
        os.chmod(mf, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    header = f"# labkit raw manifest — updated {now_iso()}\n"
    mf.write_text(header + "\n".join(sorted(lines, key=lambda s: s.split(None, 2)[2])) + "\n", encoding="utf-8")
    if chmod:
        ro = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
        for p in _files(raw):
            os.chmod(p, ro)
        os.chmod(mf, ro)
    progress(f"{added} 件を追加（合計 {len(lines)} 件）。読み取り専用化: {chmod}")
    return mf


def verify(root: Path | None = None, full: bool = False) -> list[tuple[str, str, str]]:
    """quick: ファイル集合とサイズ / full: sha256 まで照合."""
    raw = datapath("raw", root=root)
    issues: list[tuple[str, str, str]] = []
    if not raw.is_dir():
        return issues
    files = {str(p.relative_to(raw)): p for p in _files(raw)}
    if files and not (raw / MANIFEST).is_file():
        return [("L002", "data/raw", f"{MANIFEST} がありません。`labkit raw freeze` を実行してください")]
    known = read_manifest(raw)
    for rel in sorted(set(files) - set(known)):
        issues.append(("L002", f"data/raw/{rel}", "MANIFEST 未登録（`labkit raw freeze` で登録）"))
    for rel in sorted(set(known) - set(files)):
        issues.append(("L002", f"data/raw/{rel}", "MANIFEST にあるがファイルが消えています"))
    for rel in sorted(set(files) & set(known)):
        p = files[rel]
        digest, size = known[rel]
        if p.stat().st_size != size:
            issues.append(("L002", f"data/raw/{rel}", "サイズが MANIFEST と異なります（改変の疑い）"))
        elif full and sha256_file(p) != digest:
            issues.append(("L002", f"data/raw/{rel}", "sha256 が MANIFEST と異なります（改変の疑い）"))
        if p.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
            issues.append(("L003", f"data/raw/{rel}", "書き込み可能になっています（`labkit raw freeze`）"))
    return issues
