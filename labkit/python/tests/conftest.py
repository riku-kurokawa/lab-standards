import os
from pathlib import Path

import pytest


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
    ]:
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / "literature" / "references.bib").write_text("", encoding="utf-8", newline="\n")
    (tmp_path / "literature" / "tags.toml").write_text(
        '[method]\ndenoising = "雑音除去"\n', encoding="utf-8", newline="\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LAB_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("LAB_ENV", raising=False)
    os.environ.pop("SLURM_JOB_ID", None)
    return tmp_path
