"""lab-standards（本体）との接続.

通常（release）: プロジェクトは本体のタグで固定された labkit を使う。
開発（link）   : 手元の本体チェックアウトを直接参照し、本体の編集が即座に反映される（`labkit check` L050。commit しない）。

    labkit standards status
    labkit standards link   [--path ~/dev/lab-standards]
    labkit standards unlink --to v1.0.0
    labkit standards template --ref v1.0.0        # copier update（作業ツリーが clean であること）
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

import yaml

from labkit._util import git
from labkit.config import find_root

PY_LINE = re.compile(r"^labkit\s*=\s*\{.*\}[ \t]*$", re.M)
TAG_RE = re.compile(r"^v\d+\.\d+\.\d+([.-][0-9A-Za-z.]+)?$")


@dataclass
class Status:
    mode: str  # release | link | unknown
    ref: str  # タグ or ローカルパス
    template_commit: str | None
    standards_repo: str | None
    standards_ref: str | None = None


def dev_checkout(path: str | os.PathLike | None = None) -> Path:
    p = Path(path or os.environ.get("LAB_STANDARDS_DEV") or "~/dev/lab-standards").expanduser().resolve()
    if not (p / "copier.yml").is_file() or not (p / "labkit" / "python" / "pyproject.toml").is_file():
        raise SystemExit(
            f"{p} は lab-standards のチェックアウトではありません。--path か環境変数 LAB_STANDARDS_DEV で指定してください。"
        )
    return p


def _answers(root: Path) -> dict:
    f = root / ".copier-answers.yml"
    return (yaml.safe_load(f.read_text(encoding="utf-8")) or {}) if f.is_file() else {}


def status(root: Path | None = None) -> Status:
    root = root or find_root()
    pyp = root / "pyproject.toml"
    m = PY_LINE.search(pyp.read_text(encoding="utf-8")) if pyp.is_file() else None
    mode, ref = "unknown", ""
    if m:
        try:
            val = next(iter(tomllib.loads(m.group(0)).values()))
            mode, ref = (
                ("link", str(val["path"]))
                if "path" in val
                else ("release", str(val.get("tag") or val.get("rev") or "?"))
            )
        except tomllib.TOMLDecodeError:
            ref = m.group(0)
    a = _answers(root)
    return Status(mode, ref, a.get("_commit"), a.get("standards_repo"), a.get("standards_ref"))


def _replace(path: Path, new_line: str) -> None:
    text = path.read_text(encoding="utf-8")
    if not PY_LINE.search(text):
        raise SystemExit(f"{path} に labkit の参照行が見つかりません（雛形から生成したファイルか確認してください）")
    path.write_text(PY_LINE.sub(lambda _m: new_line, text, count=1), encoding="utf-8", newline="\n")


def _sync(root: Path) -> None:
    if shutil.which("uv"):
        subprocess.run(["uv", "sync"], cwd=root, check=True)
    else:
        print("uv が見つからないため環境の同期を省略しました（uv sync を実行してください）")


def link(path: str | None = None, root: Path | None = None, do_sync: bool = True) -> Status:
    root = root or find_root()
    dev = dev_checkout(path)
    _replace(
        root / "pyproject.toml", f'labkit = {{ path = "{(dev / "labkit" / "python").as_posix()}", editable = true }}'
    )
    if do_sync:
        _sync(root)
    print(f"link しました: {dev}（本体の編集が即座に反映される。この状態では commit しない: labkit check L050）")
    return status(root)


def unlink(to: str, root: Path | None = None, do_sync: bool = True) -> Status:
    root = root or find_root()
    if not TAG_RE.match(to):
        raise SystemExit(f"--to にはリリースタグ（例: v1.0.0）を指定してください: {to!r}")
    repo = _answers(root).get("standards_repo")
    if not repo:
        raise SystemExit(".copier-answers.yml に standards_repo がありません")
    _replace(
        root / "pyproject.toml",
        f'labkit = {{ git = "https://github.com/{repo}.git", tag = "{to}", subdirectory = "labkit/python" }}',
    )
    if do_sync:
        _sync(root)
    print(f"リリース版 {to} を参照するように戻しました。次: commit → `labkit standards template --ref {to}` → commit")
    return status(root)


def template(ref: str, root: Path | None = None) -> int:
    """copier update で雛形の差分を取り込む。ref がタグなら standards_ref も更新する."""
    root = root or find_root()
    copier = shutil.which("copier")
    if copier is None:
        raise SystemExit("copier が見つかりません: uv tool install copier")
    if (git(root, "status", "--porcelain") or "").strip():
        raise SystemExit("copier update は作業ツリーが clean である必要があります。先に commit してください。")
    cmd = [
        copier,
        "update",
        "--defaults",
        "--vcs-ref",
        ref,
        *(["--data", f"standards_ref={ref}"] if TAG_RE.match(ref) else []),
    ]
    print("$ " + " ".join(cmd))
    rc = subprocess.run(cmd, cwd=root, check=False).returncode
    if rc == 0:
        from labkit.check import Checker

        ch = Checker(root)
        ch.conflict_markers()
        conflicted = sorted({i.where.split(":")[0] for i in ch.issues if i.code == "L004"})
        print(
            "差分を確認し（git diff）、衝突があれば解消してから commit してください（残った衝突マーカーは `labkit check` L004 が検出）。"
        )
        if conflicted:
            print("衝突したファイル:\n  " + "\n  ".join(conflicted))
    return rc


def describe(st: Status) -> str:
    lines = [
        f"labkit        : {st.mode:8s} {st.ref}",
        f"雛形（copier）: {st.template_commit or '-'}（standards_ref {st.standards_ref or '-'}）",
        f"本体リポジトリ: {st.standards_repo or '-'}",
    ]
    if st.mode == "link":
        lines.append("⚠ link 中: commit 前に `labkit standards unlink --to vX.Y.Z` が必要です")
    return "\n".join(lines)
