"""hooks 共通処理（標準ライブラリのみ。Python 3.11 以上）."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python < 3.11: 規約を読めないので何もしない
    tomllib = None

FALLBACK = {
    "layout": {
        "writable": ["src", "scripts", "jl", "configs", "tests", "figspecs", "jobs", "docs", "literature",
                     "prompts", "scratch", "notebooks", "README.md", "CLAUDE.md", "pyproject.toml",
                     "Makefile", ".gitignore"],
        "readonly": ["data/raw", "legacy"],
    },
    "check": {
        "banned_plot_imports": ["matplotlib", "seaborn", "plotly", "bokeh", "altair", "pylab", "Plots",
                                "Makie", "CairoMakie", "GLMakie", "WGLMakie", "PyPlot", "Gadfly"],
        "plot_import_allowed": [],
        "banned_formats": ["pickle", "cPickle", "dill", "joblib", "cloudpickle", "JLD2", "BSON"],
        "format_allowed": [],
    },
    "devlog": {"dir": "docs/devlog"},
    "claude": {"require_devlog": True, "max_stop_blocks": 3},
}
PROTECTED_FILES = {"lab.toml", ".copier-answers.yml", ".claude/settings.json"}


def read_input() -> dict:
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}


def find_root(start: str | os.PathLike | None) -> Path | None:
    if start is None:
        return None
    p = Path(start).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    p = p.resolve()
    if not p.is_dir():
        p = p.parent
    while not p.exists():
        p = p.parent
    for d in (p, *p.parents):
        if (d / "lab.toml").is_file():
            return d
    return None


def load_lab(root: Path) -> dict:
    if tomllib is None:
        return {}
    with open(root / "lab.toml", "rb") as f:
        user = tomllib.load(f)
    out = {k: dict(v) for k, v in FALLBACK.items()}
    for k, v in user.items():
        if isinstance(v, dict):
            out.setdefault(k, {}).update(v)
        else:
            out[k] = v
    return out


def block(message: str) -> None:
    """操作を止め、理由を Claude に返す（exit 2）."""
    print(f"[lab-rules] {message}", file=sys.stderr)
    sys.exit(2)


def labkit_cmd(root: Path) -> list[str] | None:
    for cand in (root / ".venv" / "bin" / "labkit", root / ".venv" / "Scripts" / "labkit.exe"):
        if cand.is_file():
            return [str(cand)]
    if shutil.which("labkit"):
        return ["labkit"]
    if shutil.which("uv") and (root / "pyproject.toml").is_file():
        return ["uv", "run", "--quiet", "labkit"]
    return None


def rel(path: Path, root: Path) -> str | None:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None
