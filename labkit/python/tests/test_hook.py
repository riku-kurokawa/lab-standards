"""hooks の判定（labkit hook）: 承認ゲート・委任・成果物の保護・レビュアー・終了時の検証."""

import json
import subprocess

import pytest
from labkit.hook import handle

from labkit import state

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


def test_gate_queue_approve_and_delegate(git_project):
    p = git_project
    git(p, "switch", "-q", "-c", "feat/x")
    assert handle("pretool", bash("git push -u origin feat/x", p)) == (0, "", "")  # feat ブランチは自由
    code, out, err = handle("pretool", bash("git push origin main", p))
    assert code == 2 and "承認待ち #Q001" in err
    item = state.list_queue(p)[0]
    assert item["category"] == "git_push" and item["session_id"] == "s1" and item["branch"] == "feat/x"
    # 対話モードなら確認画面
    assert decision(handle("pretool", bash("git push origin main", p, mode="default"))[1]) == "ask"
    # 終了時: このセッションの承認待ちがあれば止めない
    assert "承認待ち #Q001" in json.loads(handle("stop", {"cwd": str(p), "session_id": "s1"})[1])["systemMessage"]
    # 承認 = そのカテゴリ・そのブランチの委任。commit しても有効で、期限内は何度でも通る
    state.approve(p, "Q001", ttl_hours=1)
    (p / "scripts" / "a.py").write_text("x = 1\n", encoding="utf-8", newline="\n")
    git(p, "add", "-A")
    git(p, "commit", "-q", "-m", "more")
    for _ in range(2):
        code, out, _ = handle("pretool", bash("git push origin main", p))
        assert code == 0 and decision(out) == "allow"
    git(p, "switch", "-q", "main")
    assert handle("pretool", bash("git push origin main", p))[0] == 2  # 別のブランチには効かない
    assert "承認済み #Q001" in handle("session", {"cwd": str(p)})[1]
    state.reject(p, "Q001", "やめる")
    assert "却下 #Q001" in json.loads(handle("prompt", {"cwd": str(p)})[1])["hookSpecificOutput"]["additionalContext"]
    state.add_delegation(p, ["release"], hours=1)
    assert decision(handle("pretool", bash("git tag v1 && git push --tags", p))[1]) == "allow"


def test_forbidden_and_state_protection(git_project):
    p = git_project
    assert handle("pretool", bash("uv run labkit approve Q001", p))[0] == 2
    assert "人間だけ" in handle("pretool", bash("labkit delegate release", p))[2]
    assert handle("pretool", bash("echo x > .lab/queue/Q009.json", p))[0] == 2
    assert handle("pretool", write(".lab/delegations.json", p))[0] == 2
    assert handle("pretool", bash("labkit delegate list", p)) == (0, "", "")


def test_artifact_protection(git_project):
    p = git_project
    for cmd in (
        "rm data/raw/x.bin",
        "cp a.h5 data/raw/",
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
    state.add_delegation(p, ["raw_write"], hours=1)
    assert decision(handle("pretool", bash("mv ~/dl/x.bin data/raw/", p))[1]) == "allow"
    assert handle("pretool", bash("rm data/raw/x.bin", p))[0] == 2  # 削除は委任しても拒否
    assert handle("pretool", write("data/raw/x.bin", p))[0] == 0
    assert handle("pretool", write("src/a.py", p))[0] == 0
    assert "matplotlib" in handle("pretool", write("src/a.py", p, "import matplotlib.pyplot as plt\n"))[2]
    assert "pickle" in handle("pretool", write("src/a.py", p, "import pickle\n"))[2]
    assert handle("pretool", write("src/a.md", p, "import pickle\n"))[0] == 0  # .py 以外は見ない


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


def test_standards_repo_scope(tmp_path, monkeypatch):
    (tmp_path / "copier.yml").write_text("", encoding="utf-8")
    (tmp_path / "labkit" / "python").mkdir(parents=True)
    git(tmp_path, "init", "-q", "-b", "main")
    assert handle("pretool", bash("git push origin main", tmp_path))[0] == 2  # ゲートは効く
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
        input=json.dumps(bash("labkit approve Q1", git_project)),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert r.returncode == 2 and "人間だけ" in r.stderr
    r = subprocess.run(
        [sys.executable, str(script), "session"],
        input=json.dumps({"cwd": str(git_project)}),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert r.returncode == 0 and "承認ゲート" in r.stdout
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
