"""v0.3.0 ハーネス: presence / queue / approve / flow / reviews / L032・L033・L035 / cite."""

import datetime as dt
import subprocess
import sys
from pathlib import Path

import pytest

from labkit import Run, flow, log_metric, reviews, state
from labkit.check import cite, num_matches, run_check

PLUGIN_SCRIPTS = Path(__file__).resolve().parents[3] / "claude-plugin" / "scripts"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=a@b", "-c", "user.name=t", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def repo(project: Path) -> Path:
    git(project, "init", "-q", "-b", "main")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "init")
    return project


def issues(root, **kw):
    # テストは本体チェックアウト（link）の labkit で走るので、その警告は除いて見る
    return [i for i in run_check(root=root, **kw)[0] if "link 中" not in i.message]


def codes(root, **kw):
    return {(i.code, i.severity) for i in issues(root, **kw)}


# ---- presence / queue / approve ----
def test_presence_default_and_switch(repo):
    assert state.get_presence(repo) == "away"
    assert state.set_presence(repo, "here") == "here" and state.get_presence(repo) == "here"
    with pytest.raises(ValueError):
        state.set_presence(repo, "maybe")
    assert (repo / ".lab" / ".gitignore").read_text().splitlines()[1:] == ["presence", "queue/", "approvals/"]
    assert ("L001", "error") not in codes(repo)  # .lab はトップレベルに置いてよい


def test_question_roundtrip(repo):
    it = state.ask_question(repo, "gzip or lz4?", options=["gzip", "lz4"], assumed="gzip", impact="1 constant")
    assert it["id"] == "Q001" and it["status"] == "open"
    assert state.pending_summary(repo)["open_questions"][0]["id"] == "Q001"
    state.answer_question(repo, "Q001", "lz4")
    assert state.pending_summary(repo)["answered"][0]["answer"] == "lz4"
    state.mark_done(repo, "Q001")
    assert state.pending_summary(repo) == {
        "pending": [],
        "approved": [],
        "open_questions": [],
        "answered": [],
        "rejected": [],
    }
    with pytest.raises(ValueError):
        state.approve(repo, "Q001", ttl_hours=1, who={})  # 質問は承認できない


def test_approval_once_ttl_head(repo):
    head = state.git_head(repo)
    it = state.request_approval(repo, "git push origin main", cwd=repo, reason="r", session_id="s")
    assert it["id"] == "Q001" and it["head"] == head and it["branch"] == "main"
    assert state.request_approval(repo, "git push origin main", cwd=repo, reason="r")["id"] == "Q001"  # 重複しない
    assert state.find_valid_approval(repo, "git push origin main", head) is None
    rec = state.approve(repo, "Q001", ttl_hours=24, who={"by": "me", "tty": True})
    assert rec["expires_at"] > rec["approved_at"] and state.get_item(repo, "Q001")["status"] == "approved"
    assert state.find_valid_approval(repo, "git push origin main --force", head) is None  # コマンド全文
    assert state.find_valid_approval(repo, "git push origin main", "0" * 40) is None  # HEAD
    later = dt.datetime.now().astimezone() + dt.timedelta(hours=25)
    assert state.find_valid_approval(repo, "git push origin main", head, now=later) is None  # 期限
    got = state.find_valid_approval(repo, "git push origin main", head)
    assert got and got["id"] == "Q001"
    state.consume_approval(repo, got)
    assert state.find_valid_approval(repo, "git push origin main", head) is None  # 1 回限り
    assert state.get_item(repo, "Q001")["status"] == "executed"
    with pytest.raises(ValueError):
        state.approve(repo, "Q001", ttl_hours=1, who={})


def test_reject_removes_approval(repo):
    state.request_approval(repo, "git tag v1", cwd=repo, reason="r")
    state.approve(repo, "Q001", ttl_hours=1, who={})
    state.reject(repo, "Q001", "no")
    assert state.list_approvals(repo) == [] and state.get_item(repo, "Q001")["status"] == "rejected"


def test_vendored_labstate_is_identical():
    """labkit/_labstate.py は claude-plugin/scripts/_labstate.py（正本）のバイト同一コピー."""
    import labkit._labstate as vendored

    src = (PLUGIN_SCRIPTS / "_labstate.py").read_bytes()
    assert Path(vendored.__file__).read_bytes() == src, (
        "cp claude-plugin/scripts/_labstate.py labkit/python/src/labkit/_labstate.py"
    )


def test_hook_and_labkit_load_lab_agree(project):
    """hooks の load_lab（_labcommon）と labkit の load_lab は同じ既定値を使う（writable の v0.3.0 追加分を除き同一）."""
    sys.path.insert(0, str(PLUGIN_SCRIPTS))
    import _labcommon

    from labkit.config import load_lab

    (project / "lab.toml").write_text(
        '[lab]\nproject = "t"\n[check]\nbanned_formats = ["pickle"]\n[gate]\napproval_ttl_hours = 1\n', encoding="utf-8"
    )
    a, b = _labcommon.load_lab(project), load_lab(project)
    a["layout"]["writable"] = [w for w in a["layout"]["writable"] if w != ".lab/presence"]
    assert a == b and b["check"]["banned_formats"] == ["pickle"] and b["gate"]["approval_ttl_hours"] == 1


def test_hook_and_labkit_share_formats(repo):
    """hook（_labstate, 標準ライブラリ）が積んだ要求を labkit が承認し、hook が受理する往復."""
    sys.path.insert(0, str(PLUGIN_SCRIPTS))
    import _labstate as hs

    assert hs.find_scope(repo) == (repo, "project") and state.find_scope(repo) == (repo, "project")
    it = hs.request_approval(repo, "git push", cwd=repo, reason="r", session_id="s")
    assert state.get_item(repo, it["id"])["command"] == "git push"
    assert hs.get_presence(repo) == state.get_presence(repo) == "away"
    state.approve(repo, it["id"], ttl_hours=24, who={"by": "me"})
    rec = hs.find_valid_approval(repo, "git push", hs.git_head(repo))
    assert rec and rec["id"] == it["id"]
    hs.consume_approval(repo, rec)
    assert state.find_valid_approval(repo, "git push", state.git_head(repo)) is None
    assert hs.pending_summary(repo) == state.pending_summary(repo)


def test_queue_list_shows_rejected_and_summary(repo, capsys, monkeypatch):
    """人間向けの一覧: 却下は Claude が done にするまで表示、承認要求には記録時点の差分要約を出す."""
    from labkit.cli import main

    monkeypatch.chdir(repo)
    state.request_approval(repo, "git push origin main", cwd=repo, reason="r")
    state.reject(repo, "Q001", "まだ早い")
    assert main(["queue", "list"]) == 0
    out = capsys.readouterr().out
    assert "[rejected]" in out and "記録時点:" in out and "直近の commit" in out
    state.mark_done(repo, "Q001")
    main(["queue", "list"])
    assert "Q001" not in capsys.readouterr().out


# ---- flow ----
def test_flow_definitions_are_consistent():
    defs = flow.definitions()
    assert set(defs) == {"migrate", "improve-standards"}
    for d in defs.values():
        names = [s["name"] for s in d["stage"]]
        assert names[-1] == "done" and len(names) == len(set(names))
        for s in d["stage"]:
            for c in s.get("done", []):
                assert c["type"] in flow.CONDITIONS, c
            assert set(s.get("forbid", [])) <= {"code", "experiments", "raw", "template", "link", "release", "commit"}


def test_clean_tree_outside_git(project):
    """git リポジトリでないときは「未コミット」ではなく「リポジトリではない」と言う."""
    msg = flow.c_clean_tree(project, {}, {})
    assert msg and "git リポジトリではありません" in msg


def test_flow_migrate_transitions_and_approval(repo):
    st = flow.start(repo, "migrate")
    assert st["stage"] == "freeze" and (repo / ".lab" / "flows" / "migrate.json").is_file()
    with pytest.raises(SystemExit, match="pre-migration"):
        flow.advance(repo, "migrate")
    git(repo, "tag", "pre-migration")
    st, _ = flow.advance(repo, "migrate")
    assert st["stage"] == "inventory"
    with pytest.raises(SystemExit, match="migration-inventory"):
        flow.advance(repo, "migrate")
    (repo / "scratch").mkdir(exist_ok=True)
    (repo / "scratch" / "migration-inventory.csv").write_text("old_path,kind,new_path,size,note\n")
    with pytest.raises(SystemExit, match="承認待ち #Q001"):  # 承認が要る段階 → キューへ
        flow.advance(repo, "migrate")
    assert state.get_item(repo, "Q001")["command"] == "labkit flow advance migrate"
    with pytest.raises(SystemExit, match="承認待ち #Q001"):  # 再実行しても同じ ID
        flow.advance(repo, "migrate")
    state.approve(repo, "Q001", ttl_hours=1, who={})
    st, _ = flow.advance(repo, "migrate")
    assert st["stage"] == "apply-template" and state.get_item(repo, "Q001")["status"] == "executed"
    assert "apply-template" in flow.describe(repo, st)
    with pytest.raises(SystemExit):
        flow.start(repo, "migrate")  # 二重開始不可
    flow.abort(repo, "migrate")
    assert flow.active_flows(repo) == []


def test_flow_review_condition(repo):
    st = flow.start(repo, "migrate")
    st["stage"] = "reproduce"
    flow.save_state(repo, st)
    with Run("r", {}) as run:
        log_metric(run, "snr_db", 12.345)
    missing = flow.unmet(repo, st)
    assert len(missing) == 1 and "pass 記録" in missing[0]
    head = state.git_head(repo)
    p = repo / "docs" / "reviews" / "2026-11-01_migrate_reproduce.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        reviews.template("migrate", "reproduce", head)
        .replace("verdict: changes-requested", "verdict: pass")
        .replace('  - "<path>:<line> 指摘（根拠）"\n', "")
    )
    assert flow.unmet(repo, st) == []
    git(repo, "commit", "-q", "--allow-empty", "-m", "new head")  # HEAD が変わると無効
    assert len(flow.unmet(repo, st)) == 1


def test_linked_if_touched(repo, monkeypatch, tmp_path):
    """本体の差分が labkit/ に触れていれば link が要る。触れていなければ不要."""
    dev = tmp_path / "dev"
    (dev / "labkit" / "python").mkdir(parents=True)
    (dev / "copier.yml").write_text("x: 1")
    git(dev, "init", "-q", "-b", "main")
    git(dev, "add", "-A")
    git(dev, "commit", "-q", "-m", "init")
    git(dev, "switch", "-q", "-c", "feat/x")
    monkeypatch.setenv("LAB_STANDARDS_DEV", str(dev))
    st = {"flow": "improve-standards", "stage": "implement", "stages": []}
    c = {"type": "linked_if_touched", "paths": ["labkit/"]}
    (dev / "claude-plugin").mkdir()
    (dev / "claude-plugin" / "h.py").write_text("x")
    git(dev, "add", "-A")
    git(dev, "commit", "-q", "-m", "hooks only")
    assert flow.c_linked_if_touched(repo, st, c) is None  # hooks だけなら link 不要
    (dev / "labkit" / "python" / "x.py").write_text("y")
    git(dev, "add", "-A")
    git(dev, "commit", "-q", "-m", "labkit change")
    assert "link" in flow.c_linked_if_touched(repo, st, c)  # labkit/ を変えたら必要


def test_flow_cli_works_before_lab_toml(tmp_path, monkeypatch, capsys):
    """migrate は雛形適用前（lab.toml 無し）から始まる: flow の CLI は git の最上位を root にする."""
    from labkit.cli import main

    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "commit", "-q", "--allow-empty", "-m", "legacy")
    (tmp_path / "sub").mkdir()
    monkeypatch.chdir(tmp_path / "sub")
    monkeypatch.delenv("LAB_PROJECT_ROOT", raising=False)
    assert main(["flow", "start", "migrate"]) == 0
    assert (tmp_path / ".lab" / "flows" / "migrate.json").is_file()
    assert "freeze" in capsys.readouterr().out


# ---- reviews ----
def test_review_parsing_and_l035(repo):
    head = state.git_head(repo)
    d = repo / "docs" / "reviews"
    d.mkdir(parents=True)
    (d / "2026-11-01_migrate_test.md").write_text(reviews.template("migrate", "test", head))
    (d / "bad.md").write_text("no frontmatter\n")
    (d / "2026-11-01_migrate_x.md").write_text(
        "---\nreviewer: me\nflow: migrate\nstage: y\ncommit: abc\nverdict: maybe\nfindings: []\n---\n"
    )
    rs = reviews.list_reviews(repo)
    assert [r.path.name for r in rs if not r.errors] == ["2026-11-01_migrate_test.md"]
    assert ("L035", "error") in codes(repo)
    assert reviews.latest_pass(repo, "migrate", "test", head) is None  # changes-requested
    assert reviews.NAME_RE.match("2026-11-01_migrate_test_2.md")  # 同日同段階の再レビューは _2


# ---- L032 / L033 / cite ----
def test_citations(repo):
    with Run("exp", {}) as run:
        log_metric(run, "snr_db", 12.345)
        log_metric(run, "n", 2000)
    rid = run.run_id
    dev = repo / "docs" / "devlog" / "2026-11-01.md"
    body = "\n".join(
        f"## {h}"
        for h in ["目的", "実施内容", "変更ファイル", "実行した run", "結果・観察", "判断と理由", "未解決・次の作業"]
    )
    ok = cite(rid, "snr_db", unit="dB")
    assert ok == f"{12.345:.4g} dB [run:{rid}:snr_db]"  # format_value と num_matches は同じ丸め
    assert cite(rid, "snr_db", digits=1) == f"12.3 [run:{rid}:snr_db]"
    assert cite(rid, "n") == f"2000 [run:{rid}:n]"
    dev.write_text(body + f"\n- {rid}: SNR は {cite(rid, 'snr_db', digits=1, unit='dB')} だった\n")
    assert not {c for c in codes(repo) if c[0] in ("L032", "L033")}
    dev.write_text(
        body + f"\n- 12.9 dB [run:{rid}:snr_db]\n- 1.0 [run:{rid}:missing]\n- {rid} で SNR 12.3 dB\n"
        f"- 20260101-000000_ghost_abcdef0_0000 の結果\n"
    )
    found = {(i.code, i.severity, i.where.split(":")[-1]) for i in issues(repo) if i.code in ("L032", "L033")}
    assert ("L033", "error", "8") in found  # 値が一致しない
    assert ("L033", "error", "9") in found  # キーが無い
    assert ("L033", "warn", "10") in found  # 書式のない数値
    assert ("L032", "error", "11") in found  # 存在しない run
    (repo / "lab.toml").write_text('[lab]\nproject = "t"\n[check]\nmode = "strict"\ncite_bare_numbers = "off"\n')
    assert ("L033", "warn", "10") not in {(i.code, i.severity, i.where.split(":")[-1]) for i in issues(repo)}
    # failed run の引用は警告
    with pytest.raises(RuntimeError):
        with Run("bad", {}) as r2:
            raise RuntimeError("x")
    dev.write_text(body + f"\n- {r2.run_id} は失敗\n")
    assert ("L032", "warn") in codes(repo)
    with pytest.raises(ValueError):
        cite(rid, "nope")


@pytest.mark.parametrize(
    "text,value,ok",
    [
        ("12.3", 12.34, True),
        ("12.3", 12.36, False),
        ("12.30", 12.3, True),
        ("12.30", 12.34, False),
        ("2000", 2000.0, True),
        ("2000", 2000.4, True),
        ("2001", 2000.4, False),
        ("1.2e-3", 0.00123, True),
        ("1.2e-3", 0.00131, False),
        ("-0.5", -0.49, True),
        ("x", 1, False),
    ],
)
def test_num_matches(text, value, ok):
    assert num_matches(text, value) is ok


@pytest.mark.parametrize(
    "value,shown",
    [
        (12.345, "12.35"),
        (0.000123456, "0.0001235"),
        (123456.789, "1.235e+05"),
        (2000, "2000"),
        (2.0, "2"),
        (20000, "2e+04"),
        (1e-7, "1e-07"),
        (0.1 + 0.2, "0.3"),
        (0, "0"),
    ],
)
def test_format_value_is_four_significant_digits(value, shown):
    """cite の既定は有効数字 4 桁の 1 規則。どの出力も L033 の照合を通る."""
    from labkit.check import format_value

    assert format_value(value, None) == shown and num_matches(shown, value)


def test_check_severity_exit_code(repo, capsys):
    from labkit.cli import main

    with Run("exp", {}) as run:
        log_metric(run, "a", 1.0)
    dev = repo / "docs" / "devlog" / "2026-11-01.md"
    body = "\n".join(
        f"## {h}"
        for h in ["目的", "実施内容", "変更ファイル", "実行した run", "結果・観察", "判断と理由", "未解決・次の作業"]
    )
    dev.write_text(body + f"\n- {run.run_id} で 3 回試した\n")  # 警告のみ
    assert main(["check"]) == 0  # 警告だけなら strict でも成功
    out = capsys.readouterr().out
    assert "L033  (warn)" in out and "0 件の違反" in out and "件の警告" in out


# ---- CLI の誤用は traceback ではなく 1 行で伝える ----
def test_cli_user_errors_are_one_line(repo, capsys):
    from labkit.cli import main

    assert main(["approve", "Q999"]) == 1
    err = capsys.readouterr().err
    assert "Q999" in err and "Traceback" not in err
    assert main(["fig", "figspecs/missing.toml"]) == 1
    assert "missing.toml" in capsys.readouterr().err
    (repo / "figspecs").mkdir(exist_ok=True)
    (repo / "figspecs" / "broken.toml").write_text('template = "timeseries\n[data\n')
    assert main(["fig", "figspecs/broken.toml", "--run", "latest"]) == 1
    err = capsys.readouterr().err
    assert "broken.toml" in err and "TOML" in err  # tomllib の例外には位置しかないのでファイル名を付ける
    with pytest.raises(SystemExit, match="段階"):
        main(["review", "template", "migrate", "nosuchstage"])
    with pytest.raises(SystemExit, match="flow 'nosuchflow'"):
        main(["review", "template", "nosuchflow", "test"])


def test_review_template_uses_the_head_that_advance_checks(repo, tmp_path, monkeypatch, capsys):
    """improve-standards の test は本体の HEAD に対する pass を要求する。template も同じ HEAD を入れる（以前はプロジェクトの HEAD で、advance が永遠に通らなかった）."""
    from labkit.cli import main

    dev = tmp_path / "dev"
    (dev / "labkit" / "python").mkdir(parents=True)
    (dev / "copier.yml").write_text("x: 1")
    git(dev, "init", "-q", "-b", "main")
    git(dev, "add", "-A")
    git(dev, "commit", "-q", "-m", "init")
    monkeypatch.setenv("LAB_STANDARDS_DEV", str(dev))
    dev_head, proj_head = state.git_head(dev), state.git_head(repo)
    assert dev_head != proj_head
    assert main(["review", "template", "improve-standards", "test"]) == 0
    assert f"commit: {dev_head}" in capsys.readouterr().out
    assert main(["review", "template", "migrate", "reproduce"]) == 0
    assert f"commit: {proj_head}" in capsys.readouterr().out


def test_flow_improve_standards_walkthrough(repo, tmp_path_factory, monkeypatch, capsys):
    """improve-standards を triage → done まで進める。本体のテスト実行と origin のタグ確認（高価・外部）だけ代替し、他の条件は実物.

    段階の配線（どの HEAD に結び付くか、承認の要る段階、adopt の条件）を固定する。サイクル 55 の欠陥はこの経路で見つかるはずだった。
    """
    from labkit.cli import main

    dev = tmp_path_factory.mktemp("dev")  # プロジェクトの外（中に置くと L001）
    (dev / "labkit" / "python").mkdir(parents=True)
    (dev / "copier.yml").write_text("x: 1")
    git(dev, "init", "-q", "-b", "main")
    git(dev, "add", "-A")
    git(dev, "commit", "-q", "-m", "init")
    monkeypatch.setenv("LAB_STANDARDS_DEV", str(dev))
    monkeypatch.setitem(flow.CONDITIONS, "standards_tests", lambda root, st, c: None)
    monkeypatch.setitem(flow.CONDITIONS, "standards_released", lambda root, st, c: None)
    name = "improve-standards"

    def approve_and_advance(qid):
        with pytest.raises(SystemExit, match=f"承認待ち #{qid}"):
            flow.advance(repo, name)
        state.approve(repo, qid, ttl_hours=1, who={})
        return flow.advance(repo, name)[0]

    st = flow.start(repo, name)
    assert st["stage"] == "triage"
    with pytest.raises(SystemExit, match="開発ログ"):
        flow.advance(repo, name)
    body = "\n".join(
        f"## {h}"
        for h in ["目的", "実施内容", "変更ファイル", "実行した run", "結果・観察", "判断と理由", "未解決・次の作業"]
    )
    (repo / "docs" / "devlog" / f"{dt.date.today().isoformat()}.md").write_text(body + "\n")
    assert approve_and_advance("Q001")["stage"] == "branch"
    with pytest.raises(SystemExit, match="feat/"):
        flow.advance(repo, name)
    git(dev, "switch", "-q", "-c", "feat/x")
    assert flow.advance(repo, name)[0]["stage"] == "implement"
    with pytest.raises(SystemExit, match="commit"):
        flow.advance(repo, name)
    (dev / "claude-plugin").mkdir()
    (dev / "claude-plugin" / "h.py").write_text("x")  # hooks だけの変更 → link 不要
    git(dev, "add", "-A")
    git(dev, "commit", "-q", "-m", "hooks")
    assert flow.advance(repo, name)[0]["stage"] == "test"
    with pytest.raises(SystemExit, match="本体の HEAD"):
        flow.advance(repo, name)
    assert main(["review", "template", name, "test"]) == 0
    tpl = capsys.readouterr().out
    d = repo / "docs" / "reviews"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{dt.date.today().isoformat()}_{name}_test.md").write_text(
        tpl.replace("verdict: changes-requested", "verdict: pass").replace('  - "<path>:<line> 指摘（根拠）"\n', "")
    )
    assert flow.advance(repo, name)[0]["stage"] == "release"
    assert approve_and_advance("Q002")["stage"] == "adopt"
    pyp = repo / "pyproject.toml"
    src = (dev / "labkit" / "python").as_posix()
    pyp.write_text(f'[tool.uv.sources]\nlabkit = {{ path = "{src}", editable = true }}\n')
    with pytest.raises(SystemExit, match="link が残っています"):  # link したままでは adopt を終えられない
        flow.advance(repo, name)
    pyp.write_text(
        '[tool.uv.sources]\nlabkit = { git = "https://github.com/x/lab-standards", subdirectory = "labkit/python", tag = "v0.3.0" }\n'
    )
    assert flow.advance(repo, name)[0]["stage"] == "done"
