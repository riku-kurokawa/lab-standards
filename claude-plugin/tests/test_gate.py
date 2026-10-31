"""承認ゲート・flow の禁止・レビュー記録の書き込み制御（hooks 側）: pytest claude-plugin/tests"""

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import _labgate as gate  # noqa: E402
import _labstate as st  # noqa: E402


def run(script: str, payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / script)], input=json.dumps(payload),
                          capture_output=True, text=True)


def bash(cwd: Path, cmd: str, **extra) -> subprocess.CompletedProcess:
    payload = {"cwd": str(cwd), "tool_name": "Bash", "tool_input": {"command": cmd}, "permission_mode": "default",
               "session_id": "s1"}
    payload.update(extra)
    return run("guard_bash.py", payload)


def decision(res: subprocess.CompletedProcess) -> str:
    if res.returncode == 2:
        return "deny"
    if res.stdout.strip():
        return json.loads(res.stdout)["hookSpecificOutput"]["permissionDecision"]
    return "pass"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.email=a@b", "-c", "user.name=t", *args], cwd=cwd, capture_output=True,
                          text=True, check=True).stdout.strip()


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "lab.toml").write_text('[lab]\nproject = "t"\n')
    for d in ("src", "scripts", "docs", "scratch", "data/raw", "runs"):
        (tmp_path / d).mkdir(parents=True)
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "commit", "-q", "--allow-empty", "-m", "init")
    return tmp_path


@pytest.fixture
def standards(tmp_path: Path) -> Path:
    (tmp_path / "copier.yml").write_text("_subdirectory: template\n")
    (tmp_path / "labkit" / "python").mkdir(parents=True)
    (tmp_path / ".lab-standards-root").write_text("")
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "commit", "-q", "--allow-empty", "-m", "init")
    return tmp_path


# ---- 分類 ----
@pytest.mark.parametrize("cmd,cats", [
    ("git push", {"git_push"}),
    ("git push origin main --tags", {"git_push"}),
    ("git -c core.x=1 -C /tmp/x push", {"git_push"}),
    ("command git push", {"git_push"}),
    ("sudo -u me git push", {"git_push"}),
    ("FOO=1 git push", {"git_push"}),
    ("env FOO=1 git push", {"git_push"}),
    ("/usr/bin/git push", {"git_push"}),
    ("ls && git push", {"git_push"}),
    ("git add -A; git commit -m x; git push", {"commit", "git_push"}),
    ("echo ok | git push", {"git_push"}),
    ("git tag v0.3.0", {"git_tag"}),
    ("git tag -a v1 -m msg", {"git_tag"}),
    ("git tag -d v1", {"git_tag"}),
    ("git tag", set()),
    ("git tag -l 'v*'", set()),
    ("git tag --list", set()),
    ("git merge feat/x", {"git_merge"}),            # 現在ブランチが main（保護）
    ("gh pr merge 12 --squash", {"gh_merge"}),
    ("gh release create v1", {"gh_release"}),
    ("gh release list", set()),
    ("labkit raw freeze", {"raw_freeze"}),
    ("uv run labkit raw freeze", {"raw_freeze"}),
    ("uv run --project ../x --quiet labkit raw freeze", {"raw_freeze"}),
    ("python -m labkit.cli raw freeze", {"raw_freeze"}),
    ("make raw-freeze", {"raw_freeze"}),
    ("copier copy gh:me/x .", {"template"}),
    ("uvx copier update", {"template"}),
    ("uv run labkit standards template --ref v1", {"template"}),
    ("make std-template REF=v1", {"template"}),
    ("labkit approve Q001", {"labkit_approve"}),
    ("uv run labkit reject Q001 --yes", {"labkit_approve"}),
    ("uv run labkit answer Q001 'x'", {"labkit_approve"}),
    ("uv run labkit standards link", {"link"}),
    ("uv run python scripts/run_example.py configs/e.toml", {"experiments"}),
    ("julia --project=jl jl/scripts/run_example.jl c.toml", {"experiments"}),
    ("sbatch jobs/x.sh", {"experiments"}),
    ("git status && git log --oneline", set()),
    ("uv run pytest -q", set()),
    ("labkit flow advance migrate", set()),
])
def test_classify(cmd, cats):
    hits = gate.classify(cmd, ["main", "master"], current_branch="main")
    assert {h.category for h in hits} == cats, hits


def test_merge_on_feature_branch_not_gated():
    assert gate.gated(gate.classify("git merge main", ["main"], current_branch="feat/x")) == []
    assert gate.gated(gate.classify("git -C ../other merge main", ["main"], current_branch="feat/x"))  # 不明は保護側


# ---- 承認ゲート（away / here / 承認済み） ----
def test_away_denies_and_queues(proj):
    res = bash(proj, "git push origin main")
    assert decision(res) == "deny" and "承認待ち #Q001" in res.stderr
    items = st.list_queue(proj)
    assert len(items) == 1 and items[0]["command"] == "git push origin main" and items[0]["head"] == st.git_head(proj)
    assert items[0]["branch"] == "main" and items[0]["session_id"] == "s1"
    # 同じコマンド・同じ HEAD は重複して積まない
    bash(proj, "git push origin main")
    assert len(st.list_queue(proj)) == 1
    assert (proj / ".lab" / ".gitignore").is_file()


def test_here_asks_but_not_in_bypass(proj):
    (proj / ".lab").mkdir()
    (proj / ".lab" / "presence").write_text("here\n")
    assert decision(bash(proj, "git push")) == "ask"
    for mode in ("bypassPermissions", "dontAsk", "auto"):
        assert decision(bash(proj, "git push", permission_mode=mode)) == "deny"
    assert len(st.list_queue(proj)) == 1


def _approve(root: Path, qid: str, *, command=None, head=None, hours=24.0, used=None):
    it = json.loads((root / ".lab" / "queue" / f"{qid}.json").read_text())
    now = dt.datetime.now().astimezone()
    rec = {"id": qid, "command": command or it["command"], "head": head or it["head"], "cwd": it["cwd"],
           "approved_at": now.isoformat(timespec="seconds"),
           "expires_at": (now + dt.timedelta(hours=hours)).isoformat(timespec="seconds"), "used_at": used}
    (root / ".lab" / "approvals").mkdir(exist_ok=True)
    (root / ".lab" / "approvals" / f"{qid}.json").write_text(json.dumps(rec))
    return rec


def test_approval_is_exact_once_and_bound_to_head(proj):
    bash(proj, "git push origin main")
    _approve(proj, "Q001")
    assert decision(bash(proj, "git push origin main --force")) == "deny"      # コマンドが違う
    assert decision(bash(proj, "git push origin main")) == "allow"             # 一致 → 通る
    rec = json.loads((proj / ".lab" / "approvals" / "Q001.json").read_text())
    assert rec["used_at"]                                                       # 使用済み
    assert json.loads((proj / ".lab" / "queue" / "Q001.json").read_text())["status"] == "executed"
    assert decision(bash(proj, "git push origin main")) == "deny"              # 2 回目は通らない


def test_approval_expired_or_other_head(proj):
    bash(proj, "git push")
    _approve(proj, "Q001", hours=-1)
    assert decision(bash(proj, "git push")) == "deny"
    git(proj, "commit", "-q", "--allow-empty", "-m", "more")
    bash(proj, "git tag v1")
    _approve(proj, "Q002", head="0" * 40)
    assert decision(bash(proj, "git tag v1")) == "deny"


def test_claude_cannot_approve(proj):
    for cmd in ("labkit approve Q001", "uv run labkit approve Q001 --yes", "labkit reject Q001", "labkit answer Q001 x",
                "echo x > .lab/approvals/Q001.json", "python -c 'open(\".lab/approvals/Q9.json\",\"w\")'",
                "sed -i s/pending/approved/ .lab/queue/Q001.json"):
        assert decision(bash(proj, cmd)) == "deny", cmd
    w = run("guard_write.py", {"tool_name": "Write", "cwd": str(proj),
                               "tool_input": {"file_path": str(proj / ".lab/approvals/Q001.json"), "content": "{}"}})
    assert w.returncode == 2
    w = run("guard_write.py", {"tool_name": "Write", "cwd": str(proj),
                               "tool_input": {"file_path": str(proj / ".lab/presence"), "content": "here"}})
    assert w.returncode == 0  # presence は Claude が切り替えてよい


def test_gate_disabled_in_lab_toml(proj):
    (proj / "lab.toml").write_text('[lab]\nproject = "t"\n[gate]\nenabled = false\n')
    assert decision(bash(proj, "git push")) == "pass"


# ---- lab-standards 本体 ----
def test_standards_root_gate_only(standards):
    assert decision(bash(standards, "git push origin main")) == "deny"
    assert (standards / ".lab" / "queue" / "Q001.json").is_file()
    assert decision(bash(standards, "rm -rf data/raw/x")) == "pass"  # 配置規約は適用しない
    w = run("guard_write.py", {"tool_name": "Write", "cwd": str(standards),
                               "tool_input": {"file_path": str(standards / "whatever/x.py"), "content": "import pickle"}})
    assert w.returncode == 0
    w = run("guard_write.py", {"tool_name": "Write", "cwd": str(standards),
                               "tool_input": {"file_path": str(standards / ".lab/queue/Q001.json"), "content": "{}"}})
    assert w.returncode == 2
    out = run("session_context.py", {"cwd": str(standards)}).stdout
    assert "承認待ち #Q001" in out and "本体" in out


# ---- flow の禁止 ----
def _flow(root: Path, stage: str, forbid: list[str]):
    (root / ".lab" / "flows").mkdir(parents=True, exist_ok=True)
    (root / ".lab" / "flows" / "migrate.json").write_text(json.dumps({
        "flow": "migrate", "status": "active", "stage": stage,
        "stages": [{"name": stage, "description": "d", "approval": False, "forbid": forbid,
                    "done": [{"type": "git_tag", "name": "pre-migration"}]}]}))


def test_flow_forbids(proj):
    _flow(proj, "freeze", ["code", "experiments", "release", "raw"])
    res = bash(proj, "uv run python scripts/run_example.py c.toml")
    assert res.returncode == 2 and "freeze" in res.stderr and "git_tag" in res.stderr
    assert bash(proj, "uv run pytest -q").returncode == 0
    w = run("guard_write.py", {"tool_name": "Write", "cwd": str(proj),
                               "tool_input": {"file_path": str(proj / "src/a.py"), "content": "x = 1"}})
    assert w.returncode == 2 and "freeze" in w.stderr
    w = run("guard_write.py", {"tool_name": "Write", "cwd": str(proj),
                               "tool_input": {"file_path": str(proj / "scratch/a.py"), "content": "x = 1"}})
    assert w.returncode == 0
    assert "flow=migrate" in run("prompt_context.py", {"cwd": str(proj)}).stdout


def test_flow_allows_after_stage(proj):
    _flow(proj, "code", ["raw", "release"])
    assert bash(proj, "uv run python scripts/run_example.py c.toml").returncode == 0
    assert bash(proj, "uv run labkit raw freeze").returncode == 2


# ---- レビュー記録（agent_type） ----
def _write(root: Path, rel: str, agent_type=None):
    payload = {"tool_name": "Write", "cwd": str(root), "tool_input": {"file_path": str(root / rel), "content": "---\n"}}
    if agent_type:
        payload["agent_type"] = agent_type
    return run("guard_write.py", payload).returncode


def test_review_records_only_by_reviewer(proj):
    assert _write(proj, "docs/reviews/2026-11-01_migrate_reproduce.md") == 2             # メインは書けない
    assert _write(proj, "docs/reviews/2026-11-01_migrate_reproduce.md", "lab-reviewer") == 0
    assert _write(proj, "docs/reviews/x.md", "lab-rules:lab-reviewer") == 0
    assert _write(proj, "src/a.py", "lab-reviewer") == 2                                 # reviewer は他を書けない
    assert _write(proj, "docs/devlog/2026-11-01.md", "lab-reviewer") == 2
    assert _write(proj, "docs/devlog/2026-11-01.md") == 0


def test_reviewer_bash_is_read_only(proj):
    for cmd in ("git commit -am x", "echo x > src/a.py", "uv run labkit flow advance", "rm -rf scratch/x"):
        assert bash(proj, cmd, agent_type="lab-reviewer").returncode == 2, cmd
    for cmd in ("git diff", "uv run labkit check", "uv run labkit runs list", "cat src/a.py"):
        assert bash(proj, cmd, agent_type="lab-reviewer").returncode == 0, cmd


# ---- Stop hook は承認待ちでは止め直さない ----
def test_stop_not_blocking_when_waiting_for_approval(proj, monkeypatch, tmp_path_factory):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path_factory.mktemp("plugin-data")))  # 止めた回数の保存先を隔離
    (proj / "src" / "a.py").write_text("x = 1\n")  # コード変更あり・開発ログ無し → 本来は止める
    res = run("stop_check.py", {"cwd": str(proj), "session_id": "s1"})
    assert res.returncode == 2
    bash(proj, "git push")  # 承認待ちを積む
    res = run("stop_check.py", {"cwd": str(proj), "session_id": "s1"})
    assert res.returncode == 0 and "承認待ち" in res.stdout
