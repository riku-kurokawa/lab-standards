"""lab-standards（本体）との接続を切り替える.

通常（release）: プロジェクトは本体のタグで固定された labkit / LabKit.jl を使う。
開発（link）   : 手元の本体チェックアウトを直接参照し、本体の編集が即座に反映される。

    labkit standards status
    labkit standards link   [--path ~/dev/lab-standards]
    labkit standards unlink --to v0.2.0
    labkit standards template --ref v0.2.0        # copier update（git の作業ツリーが clean であること）

本体チェックアウトの場所: --path > 環境変数 LAB_STANDARDS_DEV > ~/dev/lab-standards
link 中は `labkit check` が L050 を出すので、その状態のまま commit できない。
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

from labkit.config import find_root

PY_LINE = re.compile(r"^labkit\s*=\s*\{.*\}[ \t]*$", re.M)
JL_LINE = re.compile(r"^LabKit\s*=\s*\{.*\}[ \t]*$", re.M)
TAG_RE = re.compile(r"^v\d+\.\d+\.\d+([.-][0-9A-Za-z.]+)?$")


@dataclass
class Status:
    python_mode: str  # release | link | unknown
    python_ref: str  # タグ or ローカルパス
    julia_mode: str | None  # release | link | unknown | None（Julia 不使用）
    julia_ref: str | None
    template_commit: str | None
    standards_repo: str | None
    standards_ref: str | None = None

    @property
    def linked(self) -> bool:
        return self.python_mode == "link" or self.julia_mode == "link"


def dev_checkout(path: str | os.PathLike | None = None) -> Path:
    p = Path(path or os.environ.get("LAB_STANDARDS_DEV") or "~/dev/lab-standards").expanduser().resolve()
    if not (p / "copier.yml").is_file() or not (p / "labkit" / "python" / "pyproject.toml").is_file():
        raise SystemExit(
            f"{p} は lab-standards のチェックアウトではありません。"
            "--path で指定するか、環境変数 LAB_STANDARDS_DEV を設定してください。"
        )
    return p


def _answers(root: Path) -> dict:
    f = root / ".copier-answers.yml"
    if not f.is_file():
        return {}
    return yaml.safe_load(f.read_text(encoding="utf-8")) or {}


def _source_of(line_match: re.Match | None) -> tuple[str, str]:
    if line_match is None:
        return "unknown", ""
    try:
        val = next(iter(tomllib.loads(line_match.group(0)).values()))
    except tomllib.TOMLDecodeError:
        return "unknown", line_match.group(0)
    if "path" in val:
        return "link", str(val["path"])
    return "release", str(val.get("tag") or val.get("rev") or val.get("branch") or "?")


def status(root: Path | None = None) -> Status:
    root = root or find_root()
    pyp = root / "pyproject.toml"
    py = pyp.read_text(encoding="utf-8") if pyp.is_file() else ""  # 雛形適用前のプロジェクトは unknown（link ではない）
    pm, pr = _source_of(PY_LINE.search(py))
    jm = jr = None
    jl = root / "jl" / "Project.toml"
    if jl.is_file():
        jm, jr = _source_of(JL_LINE.search(jl.read_text(encoding="utf-8")))
    a = _answers(root)
    return Status(pm, pr, jm, jr, a.get("_commit"), a.get("standards_repo"), a.get("standards_ref"))


def _replace(path: Path, pattern: re.Pattern, new_line: str, what: str) -> None:
    text = path.read_text(encoding="utf-8")
    if not pattern.search(text):
        raise SystemExit(f"{path} に {what} の参照行が見つかりません（雛形から生成したファイルか確認してください）")
    path.write_text(pattern.sub(lambda _m: new_line, text, count=1), encoding="utf-8", newline="\n")


def _run(cmd: list[str], cwd: Path, check: bool = True) -> int:
    print("$ " + " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd, check=check).returncode


def sync(root: Path, julia: bool = True) -> None:
    if shutil.which("uv"):
        _run(["uv", "sync"], root)
    else:
        print("uv が見つからないため Python 環境の同期を省略しました（uv sync を実行してください）")
    if julia and (root / "jl" / "Project.toml").is_file():
        if shutil.which("julia"):
            _run(["julia", "--project=jl", "-e", "using Pkg; Pkg.resolve(); Pkg.instantiate()"], root)
        else:
            print("julia が見つからないため Julia 環境の同期を省略しました")


def link(path: str | None = None, root: Path | None = None, do_sync: bool = True) -> Status:
    root = root or find_root()
    dev = dev_checkout(path)
    _replace(
        root / "pyproject.toml",
        PY_LINE,
        f'labkit = {{ path = "{(dev / "labkit" / "python").as_posix()}", editable = true }}',
        "labkit",
    )
    jl = root / "jl" / "Project.toml"
    if jl.is_file():
        _replace(jl, JL_LINE, f'LabKit = {{ path = "{(dev / "labkit" / "julia" / "LabKit").as_posix()}" }}', "LabKit")
    if do_sync:
        sync(root)
    st = status(root)
    print(
        f"\nlink しました: {dev}\n"
        "本体（labkit/python, labkit/julia/LabKit）の編集がこのプロジェクトに即座に反映されます。\n"
        "この状態では commit できません（labkit check L050）。リリース後に `labkit standards unlink --to vX.Y.Z`。"
    )
    return st


def unlink(to: str, root: Path | None = None, do_sync: bool = True) -> Status:
    root = root or find_root()
    if not TAG_RE.match(to):
        raise SystemExit(f"--to にはリリースタグ（例: v0.2.0）を指定してください: {to!r}")
    repo = _answers(root).get("standards_repo")
    if not repo:
        raise SystemExit(".copier-answers.yml に standards_repo がありません")
    _replace(
        root / "pyproject.toml",
        PY_LINE,
        f'labkit = {{ git = "https://github.com/{repo}.git", tag = "{to}", subdirectory = "labkit/python" }}',
        "labkit",
    )
    jl = root / "jl" / "Project.toml"
    if jl.is_file():
        _replace(
            jl,
            JL_LINE,
            f'LabKit = {{ url = "https://github.com/{repo}.git", subdir = "labkit/julia/LabKit", rev = "{to}" }}',
            "LabKit",
        )
    if do_sync:
        sync(root)
    print(
        f"\nリリース版 {to} を参照するように戻しました。\n"
        f"次: 変更を commit → `labkit standards template --ref {to}` で雛形の差分を取り込む → commit"
    )
    return status(root)


def template(ref: str, root: Path | None = None) -> int:
    """copier update で雛形の差分を取り込む。ref がタグなら standards_ref も更新する."""
    root = root or find_root()
    copier = shutil.which("copier")
    if copier is None:
        raise SystemExit("copier が見つかりません: uv tool install copier")
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace"
    ).stdout
    if dirty.strip():
        raise SystemExit("copier update は作業ツリーが clean である必要があります。先に commit してください。")
    cmd = [copier, "update", "--defaults", "--vcs-ref", ref]
    if TAG_RE.match(ref):
        cmd += ["--data", f"standards_ref={ref}"]
    rc = _run(cmd, root, check=False)
    if rc == 0:
        print("\n差分を確認し（git diff）、衝突（.rej や <<<<<<<）があれば解消してから commit してください。")
    return rc


def latest_local_tag(dev: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "tag", "--list", "v*", "--sort=-v:refname"],
            cwd=dev,
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
            errors="replace",
        ).stdout.split()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return out[0] if out else None


def describe(st: Status) -> str:
    lines = [
        f"Python labkit : {st.python_mode:8s} {st.python_ref}",
        f"Julia LabKit  : {st.julia_mode or '-':8s} {st.julia_ref or ''}",
        f"雛形（copier）: {st.template_commit or '-'}（standards_ref {st.standards_ref or '-'}）",
        f"本体リポジトリ: {st.standards_repo or '-'}",
    ]
    try:
        dev = dev_checkout(None)
        lines.append(f"本体の手元    : {dev.as_posix()}（最新タグ {latest_local_tag(dev) or '-'}）")
    except SystemExit:
        lines.append("本体の手元    : 未設定（LAB_STANDARDS_DEV か ~/dev/lab-standards）")
    if st.linked:
        lines.append("\n⚠ link 中: commit 前に `labkit standards unlink --to vX.Y.Z` が必要です")
    return "\n".join(lines)
