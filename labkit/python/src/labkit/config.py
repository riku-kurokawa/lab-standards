"""プロジェクトルートと lab.toml（規約の唯一の設定源）の読み込み。既定値もここが唯一の定義."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from labkit._util import deep_merge

DEFAULTS: dict = {
    "lab": {"project": ""},
    "layout": {
        "allowed": [
            "README.md",
            "CLAUDE.md",
            "lab.toml",
            "pyproject.toml",
            "uv.lock",
            "Makefile",
            ".gitignore",
            ".gitattributes",
            ".pre-commit-config.yaml",
            ".copier-answers.yml",
            ".python-version",
            ".claude",
            ".git",
            ".venv",
            ".pytest_cache",
            ".ruff_cache",
            ".lab",
            "src",
            "scripts",
            "configs",
            "tests",
            "data",
            "runs",
            "notebooks",
            "figspecs",
            "jobs",
            "docs",
            "literature",
            "prompts",
            "scratch",
            "legacy",
        ],
        "writable": [
            "src",
            "scripts",
            "configs",
            "tests",
            "figspecs",
            "jobs",
            "docs",
            "literature",
            "prompts",
            "scratch",
            "notebooks",
            "README.md",
            "CLAUDE.md",
            "pyproject.toml",
            "Makefile",
            ".gitignore",
            ".gitattributes",
            ".claude/commands",
        ],
        "readonly": ["data/raw", "legacy"],
    },
    "check": {
        "mode": "strict",
        "banned_plot_imports": ["matplotlib", "seaborn", "plotly", "bokeh", "altair", "pylab"],
        "plot_import_allowed": [],
        "banned_formats": ["pickle", "cPickle", "dill", "joblib", "cloudpickle"],
        "format_allowed": [],
        # 絶対パス: POSIX の home / HPC の共有領域 / Windows のドライブ（"C:/", r"D:\"。"https://" は除く）
        "abs_path_patterns": [
            r"/home/\w",
            r"/Users/\w",
            r"/mnt/\w",
            r"(?<![A-Za-z])[A-Za-z]:[\\/]",
            r"/lustre",
            r"/gpfs",
            r"/scratch/",
            r"/work/",
            r"/groups/",
        ],
        "code_dirs": ["src", "scripts", "tests", "notebooks", "jobs"],
        "figure_ok_dirs": ["docs/assets", "literature/pdfs", "literature/inbox", "scratch"],
        "data_ok_dirs": ["tests/fixtures", "scratch"],
        "skip": [],
        # 引用（run ID・`値 [run:<id>:<key>]`）を照合する文書（ルート基準の glob）。自動ブロックと DIGEST は除く
        "claim_docs": ["docs/**/*.md", "literature/surveys/*.md"],
        "dirty_citation": "warn",  # dirty な run を結果として引用したとき: "warn" | "error" | "off"（claims.md は常に error）
        # L018: src・scripts のファイルの行数（空行を除く）の上限。人間が一度に読める大きさ。0 で無効
        "max_file_lines": 300,
        "long_file": "warn",
        "max_lines_allowed": [],
    },
    # L037: 状態ファイルは「今」だけを持つ（H1 は 1 つ、同じ H2 は 1 回、max_lines 以内）。履歴は git
    "state": {"file": "docs/state.md", "max_lines": 150},
    "devlog": {
        "dir": "docs/devlog",
        "required_headings": ["目的", "結果・観察", "判断と理由", "未解決・次の作業"],
        # 空だと L030（Stop hook が止める）。機械で埋まる欄（変更ファイル・run）は `labkit devlog` が自動生成する
        "must_fill": ["目的", "判断と理由", "未解決・次の作業"],
    },
    "adr": {"dir": "docs/decisions", "required_headings": ["背景", "決定", "理由と検討した代替案", "影響"]},
    # require_prediction: 正式な run の前に結果の予想を設定（config の prediction）に書かせ、meta.json に残す
    # require_clean: 未コミットの変更がある状態（git.dirty）では run を始めない（dirty な run は結果として引用できない）
    "runs": {"hash_max_gb": 2.0, "require_prediction": False, "require_clean": False},
    # note_body: L047（status が read/key なのに claims が空）、survey_verdict: L048（done なのに verdict/n_opened が無い）
    "literature": {"dir": "literature", "pdf_dir": "literature/pdfs", "note_body": "warn", "survey_verdict": "warn"},
    # 人間の入口（labkit digest）: 図は assets に写す（git で見える）。max_figures を超える分はリンクだけ
    "digest": {"file": "docs/DIGEST.md", "assets": "docs/assets/digest", "max_figures": 12},
    "claude": {"require_devlog": True, "max_stop_blocks": 3},
    # 長い自律運用: backlog（"- [ ] ..." の行）に未着手の項目が min_open 件未満なら Stop hook が終了を止める。空文字で無効
    "autonomy": {"backlog": "", "min_open": 0},
    "gate": {"enabled": True, "protected_branches": ["main", "master"], "approval_ttl_hours": 24},
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
        f"lab.toml が {p} から上位に見つかりません。lab-standards のプロジェクト内で実行してください。"
    )


def find_scope(start: str | os.PathLike | None = None) -> tuple[Path, str] | None:
    """(root, "project" | "standards")。lab.toml のあるプロジェクトか lab-standards 本体。どちらでもなければ None."""
    p = Path(start or Path.cwd()).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    p = p.resolve()
    while not p.exists():
        p = p.parent
    if p.is_file():
        p = p.parent
    for d in (p, *p.parents):
        if (d / "lab.toml").is_file():
            return d, "project"
        if (d / "copier.yml").is_file() and (d / "labkit" / "python").is_dir():
            return d, "standards"
    return None


def read_toml(path: str | os.PathLike) -> dict:
    """TOML を読む。文法エラーにはファイル名を付ける（tomllib の例外には位置しか無い）."""
    with open(path, "rb") as f:
        try:
            return tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"{path}: TOML の文法エラー: {e}") from e


def load_lab(root: str | os.PathLike | None = None) -> dict:
    """lab.toml を既定値に重ねる。本体（lab.toml 無し）では既定値だけ."""
    r = Path(root) if root else find_root()
    f = r / "lab.toml"
    return deep_merge(DEFAULTS, read_toml(f)) if f.is_file() else dict(DEFAULTS)
