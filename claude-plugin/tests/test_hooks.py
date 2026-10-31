"""hooks の単体テスト（標準ライブラリ + pytest）: pytest claude-plugin/tests"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def run(script: str, payload: dict) -> int:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).returncode


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "lab.toml").write_text('[lab]\nproject = "t"\n', encoding="utf-8")
    for d in ("src", "scripts", "data/raw", "runs", "scratch"):
        (tmp_path / d).mkdir(parents=True)
    return tmp_path


@pytest.mark.parametrize(
    "rel,content,code",
    [
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
    ],
)
def test_guard_write(proj, rel, content, code):
    assert (
        run("guard_write.py", {"tool_name": "Write", "tool_input": {"file_path": str(proj / rel), "content": content}})
        == code
    )


def test_guard_write_ignores_other_projects(tmp_path):
    assert (
        run(
            "guard_write.py",
            {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "x.py"), "content": "import pickle"}},
        )
        == 0
    )


@pytest.mark.parametrize(
    "cmd,code",
    [
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
    ],
)
def test_guard_bash(proj, cmd, code):
    assert run("guard_bash.py", {"cwd": str(proj), "tool_input": {"command": cmd}}) == code


def test_hook_output_is_utf8(proj, monkeypatch):
    """Windows の既定コードページでも hook の出力（日本語）は UTF-8（Claude Code は UTF-8 として読む）."""
    import os

    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    res = subprocess.run(
        [sys.executable, str(SCRIPTS / "guard_write.py")],
        input=json.dumps(
            {"tool_name": "Write", "tool_input": {"file_path": str(proj / "lab.toml"), "content": "x"}}
        ).encode(),
        capture_output=True,
        env=env,
    )
    assert res.returncode == 2
    assert "規約ファイル" in res.stderr.decode("utf-8")


def test_eval_fixtures_match_shared_script():
    """各 eval ケースの fixture.sh は evals/_shared/project.sh のバイト同一コピー（公式仕様: scaffold はケース内のスクリプト）."""
    evals = SCRIPTS.parent / "evals"
    src = (evals / "_shared" / "project.sh").read_bytes()
    cases = [d for d in evals.iterdir() if d.is_dir() and not d.name.startswith("_") and d.name != "results"]
    assert len(cases) >= 7
    for c in cases:
        assert (c / "fixture.sh").read_bytes() == src, f"cp claude-plugin/evals/_shared/project.sh {c}/fixture.sh"
        assert "scaffold_script: fixture.sh" in (c / "case.yaml").read_text(encoding="utf-8")
        fm = (c / "prompt.md").read_text(encoding="utf-8").split("---")[1]
        assert not (
            {"Bash", "Write", "Edit"} & set(re.findall(r"[A-Za-z]+", fm.split("allowed_tools:")[1].split("]")[0]))
        )


def test_tool_cmd_finds_venv_on_both_layouts(tmp_path, monkeypatch):
    """venv のツール探索は POSIX（.venv/bin）と Windows（.venv/Scripts/*.exe）の両方を見る（stop_check と labkit_cmd で共有）."""
    sys.path.insert(0, str(SCRIPTS))
    import shutil

    import _labcommon

    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert _labcommon.tool_cmd(tmp_path, "ruff") is None
    win = tmp_path / ".venv" / "Scripts" / "ruff.exe"
    win.parent.mkdir(parents=True)
    win.write_text("", encoding="utf-8")
    assert _labcommon.tool_cmd(tmp_path, "ruff") == [str(win)]
    posix = tmp_path / ".venv" / "bin" / "ruff"
    posix.parent.mkdir(parents=True)
    posix.write_text("", encoding="utf-8")
    assert _labcommon.tool_cmd(tmp_path, "ruff") == [str(posix)]
    assert _labcommon.labkit_cmd(tmp_path) is None


def test_stop_runs_ruff_once(proj, monkeypatch, tmp_path_factory):
    """Stop hook は src/scripts/tests を ruff check し、自動修正できない違反（未定義名など）で止める."""
    import datetime
    import os

    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path_factory.mktemp("plugin-data")))
    (proj / "src" / "bad.py").write_text("def f():\n    return undefined_name\n", encoding="utf-8")
    (proj / "docs" / "devlog").mkdir(parents=True)
    (proj / "docs" / "devlog" / f"{datetime.date.today()}.md").write_text("x", encoding="utf-8")
    # ruff は本体 labkit の venv のものを PATH 経由で使う（tool_cmd の PATH 探索）
    venv = SCRIPTS.parents[1] / "labkit" / "python" / ".venv"
    bindir = next(d for d in (venv / "Scripts", venv / "bin") if d.is_dir())
    env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"}
    res = subprocess.run(
        [sys.executable, str(SCRIPTS / "stop_check.py")],
        input=json.dumps({"cwd": str(proj), "session_id": "s9"}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert res.returncode == 2 and "ruff check" in res.stderr and "F821" in res.stderr


def test_old_python_fails_loudly(proj):
    """python3 が 3.11 未満なら黙って無効化せず exit 1 と説明（非ブロックの通知）。version_info を偽装して確かめる."""
    code = (
        "import sys, runpy; sys.version_info = (3, 9, 6, 'final', 0); "
        "sys.argv = [sys.argv[1]]; sys.path.insert(0, __import__('os').path.dirname(sys.argv[0])); runpy.run_path(sys.argv[0], run_name='__main__')"
    )
    res = subprocess.run(
        [sys.executable, "-c", code, str(SCRIPTS / "guard_write.py")],
        input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(proj / "lab.toml"), "content": "x"}}),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert res.returncode == 1 and "3.11" in res.stderr.splitlines()[0]
