"""hooks の単体テスト（標準ライブラリ + pytest）: pytest claude-plugin/tests"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def run(script: str, payload: dict) -> int:
    return subprocess.run([sys.executable, str(SCRIPTS / script)], input=json.dumps(payload),
                          capture_output=True, text=True).returncode


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "lab.toml").write_text('[lab]\nproject = "t"\n')
    for d in ("src", "scripts", "data/raw", "runs", "scratch"):
        (tmp_path / d).mkdir(parents=True)
    return tmp_path


@pytest.mark.parametrize("rel,content,code", [
    ("src/a.py", "import numpy", 0),
    ("scratch/a.txt", "x", 0),
    ("data/raw/a.csv", "x", 2),
    ("data/processed/a.csv", "x", 2),
    ("runs/r/meta.json", "x", 2),
    ("lab.toml", "x", 2),
    ("results/a.txt", "x", 2),
    ("scripts/p.py", "import matplotlib.pyplot as plt", 2),
    ("scripts/p.jl", "using LabKit, GLMakie", 2),
    ("src/s.py", "import pickle", 2),
])
def test_guard_write(proj, rel, content, code):
    assert run("guard_write.py", {"tool_name": "Write",
                                  "tool_input": {"file_path": str(proj / rel), "content": content}}) == code


def test_guard_write_ignores_other_projects(tmp_path):
    assert run("guard_write.py", {"tool_name": "Write",
                                  "tool_input": {"file_path": str(tmp_path / "x.py"), "content": "import pickle"}}) == 0


@pytest.mark.parametrize("cmd,code", [
    ("uv run pytest", 0),
    ("cp data/raw/a scratch/", 0),
    ("head data/raw/a > scratch/h", 0),
    ("rm data/raw/a", 2),
    ("echo 1 >> data/raw/a", 2),
    ("cp x data/raw/", 2),
    ("find data/raw -name '*.tmp' -delete", 2),
    ("git clean -fdx", 2),
    ("rm -rf runs/old", 2),
    ("sed -i s/a/b/ lab.toml", 2),
])
def test_guard_bash(proj, cmd, code):
    assert run("guard_bash.py", {"cwd": str(proj), "tool_input": {"command": cmd}}) == code
