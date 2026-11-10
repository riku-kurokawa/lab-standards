"""hooks の判定（labkit hook）: 成果物の保護・レビュアー・終了時の検証（v2.0.0: 承認ゲートは無い）."""

import json
import subprocess

import pytest

from labkit import state
from labkit.hook import handle

from .conftest import git


def bash(cmd, cwd, mode="auto", **kw):
    return {
        "tool_name": "Bash",
        "tool_input": {"command": cmd},
        "cwd": str(cwd),
        "permission_mode": mode,
        "session_id": "s1",
        **kw,
    }


def write(path, cwd, content="x = 1\n", **kw):
    return {
        "tool_name": "Write",
        "tool_input": {"file_path": str(cwd / path), "content": content},
        "cwd": str(cwd),
        **kw,
    }


def decision(out: str) -> str | None:
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out else None


def test_outside_project_does_nothing(tmp_path):
    assert handle("pretool", bash("git push origin main", tmp_path)) == (0, "", "")


def test_no_approval_gate(git_project):
    """v2.0.0: 承認ゲートを廃止。push・merge・tag・release・raw freeze も止めない（完全自律）."""
    p = git_project
    for cmd in (
        "git push origin main",
        "git push --force origin main",
        "git tag v1 && git push --tags",
        "git merge --ff-only feat/x",
        "gh pr merge 3",
        "gh release create v1",
        "uv run labkit raw freeze",
    ):
        assert handle("pretool", bash(cmd, p)) == (0, "", ""), cmd
    assert not state.list_queue(p)  # 承認待ちは積まれない
    assert handle("prompt", {"cwd": str(p)}) == (0, "", "")  # UserPromptSubmit は何もしない
    assert "完全自律" in handle("session", {"cwd": str(p)})[1]


def test_state_protection(git_project):
    p = git_project
    assert handle("pretool", bash("echo x > .lab/queue/Q009.json", p))[0] == 2
    # 読み取りだけ（出力を捨てるリダイレクト）は止めない。捨てる先以外への書き込みは止める
    assert handle("pretool", bash("find .lab/queue -name 'Q*.json' 2>/dev/null", p))[0] == 0
    assert handle("pretool", bash("ls .lab/beats 2>&1", p))[0] == 0
    assert handle("pretool", bash("cat x 2>/dev/null > .lab/queue/Q009.json", p))[0] == 2
    assert handle("pretool", write(".lab/flows/x.json", p))[0] == 2
    assert handle("pretool", bash("uv run labkit queue list", p)) == (0, "", "")


def test_artifact_protection(git_project):
    p = git_project
    for cmd in (
        "rm data/raw/x.bin",
        "mv data/raw/x.bin elsewhere/",
        "git clean -fdx",
        "rm -rf runs/2026",
        "echo 1 > lab.toml",
        "git checkout -- data/raw",
    ):
        assert handle("pretool", bash(cmd, p))[0] == 2, cmd
    assert handle("pretool", bash("ls data/raw && cat lab.toml", p)) == (0, "", "")
    for path in (
        "data/raw/x.bin",
        "runs/x/meta.json",
        "data/processed/x.h5",
        "lab.toml",
        "legacy/a.py",
        "elsewhere/x.py",
    ):
        assert handle("pretool", write(path, p))[0] == 2, path
    # 新しい生データの搬入はできる（上書きしない）。既存のファイルへの上書きは止める
    assert handle("pretool", bash("mv ~/dl/x.bin data/raw/", p)) == (0, "", "")
    assert handle("pretool", bash("cp a.h5 b.h5 data/raw/", p)) == (0, "", "")
    (p / "data" / "raw").mkdir(parents=True, exist_ok=True)
    (p / "data" / "raw" / "x.bin").write_bytes(b"1")
    assert handle("pretool", bash("cp ~/dl/x.bin data/raw/", p))[0] == 2
    assert handle("pretool", bash("cp new.bin data/raw/x.bin", p))[0] == 2
    assert handle("pretool", write("src/a.py", p))[0] == 0
    assert handle("pretool", write(".claude/commands/goal.md", p))[0] == 0  # 複数段の writable（既定）
    assert handle("pretool", write(".claude/settings.json", p))[0] == 2  # 同じ親でも settings は書けない
    assert "matplotlib" in handle("pretool", write("src/a.py", p, "import matplotlib.pyplot as plt\n"))[2]
    assert "pickle" in handle("pretool", write("src/a.py", p, "import pickle\n"))[2]
    assert handle("pretool", write("src/a.md", p, "import pickle\n"))[0] == 0  # .py 以外は見ない


def test_loop_self_stop_is_denied(git_project):
    p = git_project
    cron = {"tool_name": "CronDelete", "tool_input": {"id": "abc"}, "cwd": str(p), "session_id": "s1"}
    code, _, err = handle("pretool", cron)
    assert code == 2 and "人間だけ" in err
    wake = {"tool_name": "ScheduleWakeup", "cwd": str(p), "session_id": "s1"}
    assert handle("pretool", {**wake, "tool_input": {"stop": True}})[0] == 2
    assert handle("pretool", {**wake, "tool_input": {"delaySeconds": 900, "prompt": "x"}}) == (0, "", "")
    lab = (p / "lab.toml").read_text(encoding="utf-8")
    (p / "lab.toml").write_text(lab + "\n[claude]\nallow_self_stop = true\n", encoding="utf-8")
    assert handle("pretool", cron) == (0, "", "")


def test_reviewer_rules(git_project):
    p = git_project
    rv = {"agent_type": "lab-rules:lab-reviewer"}
    assert handle("pretool", bash("git diff && uv run labkit check", p, **rv))[0] == 0
    assert handle("pretool", bash("uv run python scripts/x.py", p, **rv))[0] == 2
    assert handle("pretool", write("docs/reviews/2026-11-02_migrate_reproduce.md", p, **rv))[0] == 0
    assert handle("pretool", write("src/a.py", p, **rv))[0] == 2
    assert "lab-reviewer" in handle("pretool", write("docs/reviews/2026-11-02_migrate_reproduce.md", p))[2]


def test_stop_requires_judgment_in_devlog(git_project):
    p = git_project
    assert handle("stop", {"cwd": str(p), "session_id": "s9"}) == (0, "", "")  # コードを変えていない
    (p / "src" / "m.py").write_text("x = 1\n", encoding="utf-8", newline="\n")
    code, _, err = handle("stop", {"cwd": str(p), "session_id": "s9"})
    assert code == 2 and "目的" in err and "今作成した" in err
    import datetime as _dt

    f = p / "docs" / "devlog" / f"{_dt.date.today().isoformat()}.md"
    text = f.read_text(encoding="utf-8")
    assert "未コミット: src/m.py" in text
    for h in ("目的", "判断と理由", "未解決・次の作業"):
        text = text.replace(f"## {h}\n", f"## {h}\n\n書いた\n")
    f.write_text(text, encoding="utf-8", newline="\n")
    assert handle("stop", {"cwd": str(p), "session_id": "s9"}) == (0, "", "")
    # 上限回数を超えたら人間に委ねる
    (f).write_text(text.replace("書いた", ""), encoding="utf-8", newline="\n")
    results = [handle("stop", {"cwd": str(p), "session_id": "s9"})[0] for _ in range(4)]
    assert results == [2, 2, 2, 0]
    # 委ねた同じ違反では以後止めない（止め続けると、関係のない作業のセッションが終われない）
    assert handle("stop", {"cwd": str(p), "session_id": "s9"}) == (0, "", "")
    # 新しい違反が出たら、また止める
    (p / "runs" / "shell").mkdir()
    code, _, err = handle("stop", {"cwd": str(p), "session_id": "s9"})
    assert code == 2 and "L020" in err and "runs mark shell" in err


def test_standards_repo_scope(tmp_path, monkeypatch):
    (tmp_path / "copier.yml").write_text("", encoding="utf-8")
    (tmp_path / "labkit" / "python").mkdir(parents=True)
    git(tmp_path, "init", "-q", "-b", "main")
    assert handle("pretool", bash("git push origin main", tmp_path)) == (0, "", "")  # 承認ゲートは無い
    assert handle("pretool", write("data/raw/x", tmp_path))[0] == 0  # プロジェクト規約は適用しない
    assert handle("stop", {"cwd": str(tmp_path)}) == (0, "", "")
    assert "本体" in handle("session", {"cwd": str(tmp_path)})[1]


def test_plugin_entry_script(git_project, tmp_path):
    """claude-plugin/scripts/hook.py が stdin を labkit に渡し、判定を返す（python3 だけで動く）."""
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parents[3] / "claude-plugin" / "scripts" / "hook.py"
    r = subprocess.run(
        [sys.executable, str(script), "pretool"],
        input=json.dumps(bash("echo x > .lab/queue/Q1.json", git_project)),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert r.returncode == 2 and ".lab/" in r.stderr
    r = subprocess.run(
        [sys.executable, str(script), "session"],
        input=json.dumps({"cwd": str(git_project)}),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert r.returncode == 0 and "完全自律" in r.stdout
    other = tmp_path.parent / f"{tmp_path.name}-other"
    other.mkdir()
    r = subprocess.run(
        [sys.executable, str(script), "session"],
        input=json.dumps({"cwd": str(other)}),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert r.returncode == 0 and r.stdout == ""


@pytest.fixture(autouse=True)
def _path_labkit(monkeypatch):
    """plugin の入口が PATH の labkit（このテスト環境の venv）を見つけられるようにする."""
    import os
    import sys
    from pathlib import Path

    monkeypatch.setenv("PATH", str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"])


def test_plugin_entry_tolerates_old_labkit(capsys):
    """plugin が新しく labkit が古い（`labkit hook` が無い）とき、すべての操作を止めてしまわない."""
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[3] / "claude-plugin" / "scripts" / "hook.py"
    spec = importlib.util.spec_from_file_location("plugin_hook", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    err = "usage: labkit ... labkit: error: argument cmd: invalid choice: 'hook' (choose from check, fig)"
    assert mod.relay("pretool", 2, "", err, "1.0.1") == 0
    assert mod.relay("session", 2, "", err, "1.0.1") == 0 and "unlink --to v1.0.1" in capsys.readouterr().out
    assert mod.relay("pretool", 2, "", "[lab-rules] 拒否", "1.0.1") == 2 and "拒否" in capsys.readouterr().err


def test_python_stdin_without_input_is_blocked(git_project):
    p = git_project
    for cmd in ("python3 - 2>/dev/null; ls", "cd x && python -", "uv run true || py -"):
        code, _, err = handle("pretool", bash(cmd, p))
        assert code == 2 and "標準入力" in err, cmd
    for cmd in ("python3 - <<'EOF'\nprint(1)\nEOF", "cat a.py | python -", "python -m pytest", "python a.py -"):
        assert handle("pretool", bash(cmd, p))[0] == 0, cmd


def test_removed_backlog_gate_is_ignored(git_project):
    """v2.3.0 で廃止した [autonomy] backlog / min_open が lab.toml に残っていても、終了を止めない."""
    p = git_project
    with open(p / "lab.toml", "a", encoding="utf-8", newline="\n") as f:
        f.write('[autonomy]\nbacklog = "docs/backlog.md"\nmin_open = 2\n')
    assert handle("stop", {"cwd": str(p), "session_id": "s7"}) == (0, "", "")


def test_archive_allowed_and_reviewer_read_commands(git_project):
    p = git_project
    assert handle("pretool", bash("uv run labkit runs archive --status failed,interrupted", p)) == (0, "", "")
    rv = {"agent_type": "lab-rules:lab-reviewer"}
    for cmd in (
        "labkit review list --open",
        "uv run labkit claim list",
        "labkit lit queue",
        "labkit runs table sweep --md",
    ):
        assert handle("pretool", bash(cmd, p, **rv)) == (0, "", ""), cmd
    assert handle("pretool", bash("labkit claim add x --evidence a:b", p, **rv))[0] == 2
    assert handle("pretool", bash("labkit runs archive abc", p, **rv))[0] == 2
