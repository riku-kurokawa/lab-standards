import os
import subprocess
from pathlib import Path

import pytest


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True, encoding="utf-8"
    ).stdout.strip()


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> Path:
    """最小のプロジェクト（lab.toml + 標準ディレクトリ）を作り、そこへ cd する."""
    (tmp_path / "lab.toml").write_text(
        '[lab]\nproject = "t"\n[check]\nmode = "strict"\n', encoding="utf-8", newline="\n"
    )
    for d in [
        "src",
        "scripts",
        "configs/paths",
        "data/raw",
        "data/interim",
        "data/processed",
        "runs",
        "figspecs",
        "docs/devlog",
        "docs/decisions",
        "literature/notes",
        "literature/surveys",
        "literature/pdfs",
        "scratch",
    ]:
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / "literature" / "references.bib").write_text("", encoding="utf-8", newline="\n")
    (tmp_path / "literature" / "tags.toml").write_text(
        '[method]\ndenoising = "雑音除去"\n', encoding="utf-8", newline="\n"
    )
    monkeypatch.chdir(tmp_path)
    for k in ("LAB_PROJECT_ROOT", "LAB_ENV", "SLURM_JOB_ID", "CLAUDE_CODE_SESSION_ID"):
        monkeypatch.delenv(k, raising=False)
    os.environ.pop("CLAUDE_PLUGIN_DATA", None)
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / ".plugin-data"))
    return tmp_path


@pytest.fixture
def git_project(project: Path) -> Path:
    """project を git リポジトリにして 1 commit 入れる（ブランチ main）."""
    git(project, "init", "-q", "-b", "main")
    git(project, "config", "user.email", "t@example.com")
    git(project, "config", "user.name", "t")
    (project / ".gitignore").write_text(
        "/runs/*\n/data/*/*\n/scratch/*\n/.lab/queue/\n", encoding="utf-8", newline="\n"
    )
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "init")
    return project
