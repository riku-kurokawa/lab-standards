"""プロジェクトルートと lab.toml（規約の唯一の設定源）の読み込み."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from labkit._util import deep_merge

# lab.toml に書かれていない項目の既定値。テンプレートの lab.toml は全項目を明示する。
DEFAULTS: dict = {
    "lab": {"standards_version": "0.2.0", "project": ""},
    "layout": {
        "allowed": [
            "README.md", "CLAUDE.md", "lab.toml", "pyproject.toml", "uv.lock", "Makefile",
            ".gitignore", ".gitattributes", ".pre-commit-config.yaml", ".copier-answers.yml",
            ".python-version", ".claude", ".git", ".venv", ".mlflow", ".pytest_cache",
            ".ruff_cache", "src", "scripts", "jl", "configs", "tests", "data", "runs",
            "notebooks", "figspecs", "jobs", "docs", "literature", "prompts", "scratch", "legacy",
        ],
        "writable": [
            "src", "scripts", "jl", "configs", "tests", "figspecs", "jobs", "docs",
            "literature", "prompts", "scratch", "notebooks", "README.md", "CLAUDE.md",
            "pyproject.toml", "Makefile", ".gitignore",
        ],
        "readonly": ["data/raw", "legacy"],
    },
    "check": {
        "mode": "strict",
        "banned_plot_imports": [
            "matplotlib", "seaborn", "plotly", "bokeh", "altair", "pylab",
            "Plots", "Makie", "CairoMakie", "GLMakie", "WGLMakie", "PyPlot", "Gadfly",
            "UnicodePlots", "PlotlyJS",
        ],
        "plot_import_allowed": [],
        "banned_formats": ["pickle", "cPickle", "dill", "joblib", "cloudpickle", "JLD2", "BSON"],
        "format_allowed": [],
        "abs_path_patterns": [
            r"/home/\w", r"/Users/\w", r"[A-Za-z]:\\\\", r"/lustre", r"/gpfs", r"/scratch/",
            r"/work/", r"/groups/",
        ],
        "code_dirs": ["src", "scripts", "jl", "tests", "notebooks"],
        "figure_ok_dirs": ["docs/assets", "literature/pdfs", "literature/inbox", "scratch"],
        "data_ok_dirs": ["tests/fixtures", "scratch"],
        "skip": [],
    },
    "devlog": {
        "dir": "docs/devlog",
        "required_headings": [
            "目的", "実施内容", "変更ファイル", "実行した run", "結果・観察", "判断と理由",
            "未解決・次の作業",
        ],
    },
    "adr": {
        "dir": "docs/decisions",
        "required_headings": ["背景", "決定", "理由と検討した代替案", "影響"],
    },
    "runs": {"hash_inputs_max_gb": 2.0},
    "literature": {"dir": "literature", "pdf_dir": "literature/pdfs"},
    "claude": {"require_devlog": True, "max_stop_blocks": 3},
}


def find_root(start: str | os.PathLike | None = None) -> Path:
    """lab.toml を含むディレクトリを上方向に探す（環境変数 LAB_PROJECT_ROOT が優先）."""
    env = os.environ.get("LAB_PROJECT_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    p = Path(start or Path.cwd()).resolve()
    if p.is_file():
        p = p.parent
    for d in (p, *p.parents):
        if (d / "lab.toml").is_file():
            return d
    raise FileNotFoundError(
        f"lab.toml が {p} から上位に見つかりません。lab-standards で生成したプロジェクト内で実行してください。"
    )


def load_lab(root: str | os.PathLike | None = None) -> dict:
    r = Path(root) if root else find_root()
    with open(r / "lab.toml", "rb") as f:
        user = tomllib.load(f)
    return deep_merge(DEFAULTS, user)
