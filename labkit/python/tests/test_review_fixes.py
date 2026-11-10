"""v1.5.0 の独立レビューで見つかった穴の回帰テスト（判定の失敗で run が残る、台帳の抜け穴、拍の閉じ忘れ、git の引用符など）."""

import json

import pytest

from labkit import Run, beat, claims
from labkit._util import git_info, git_status
from labkit.check import run_check
from labkit.hook import handle
from labkit.reviews import open_reviews
from labkit.runs import archive_candidates, archive_runs, list_runs

from .conftest import git
from .test_hook import bash, write


def issues(project, code):
    return [i for i in run_check(root=project)[0] if i.code == code]


def put(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


def test_unicode_minus_and_percent_in_citations(project):
    with Run("c", {"seed": 0}) as run:
        run.log_metric("lag", -0.4999)
        run.log_metric("share", 0.7429)
    put(
        project / "docs" / "papers" / "d.md",
        f"## 結果\n\n−0.5 mm [run:{run.run_id}:lag] と 74 % [run:{run.run_id}:share] と 値−0.5 [run:{run.run_id}:lag]\n",
    )
    assert not issues(project, "L033") and not issues(project, "L034")


def test_bad_pass_or_prediction_never_leaves_run_running(project):
    pytest.importorskip("pyarrow")
    import pandas as pd

    from labkit import runpath, save

    for bad in ([{"max": 0.5, "table": "r.parquet"}], [{"key": "e", "max": "0.5"}], [{"key": "e"}], ["e"]):
        with pytest.raises(ValueError, match=r"\[\[pass\]\]"):
            with Run("p", {"seed": 0, "pass": bad}):
                pass
    for pred in (
        {"basis": "x", "claims": [{"key": "e1", "range": ["0", "1"]}]},
        {"basis": "x", "claims": [{"key": 1, "range": [0, 1]}]},
    ):
        with pytest.raises(ValueError, match="claims"):
            with Run("p", {"seed": 0, "prediction": pred}):
                pass
    assert not list_runs(project)  # 検証で止まった run はディレクトリも残さない
    cfg = {"seed": 0, "pass": [{"key": "err", "max": 0.5, "table": "results.parquet", "where": {"nocol": "x"}}]}
    with Run("ok", cfg) as run:  # 列名の誤りは評価時にしか分からない → 不合格として run は finished
        save(runpath(run, "results.parquet"), pd.DataFrame({"err": [0.1]}))
    meta = json.loads((run.dir / "meta.json").read_text(encoding="utf-8"))
    metrics = json.loads((run.dir / "metrics.json").read_text(encoding="utf-8"))
    assert (
        meta["status"] == "finished"
        and metrics["pass_1"] == 0.0
        and "評価できない" in (run.dir / "log.txt").read_text(encoding="utf-8")
    )
    with Run("list", {"seed": 0, "prediction": [3.4, 4.0]}) as run:  # 表でも文字列でもない予想は従来どおり通す
        pass
    meta = json.loads((run.dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "finished" and meta["prediction"] == [3.4, 4.0] and "prediction_result" not in meta


def test_archive_undo_with_filter_and_uncited_age(project):
    with pytest.raises(RuntimeError):
        with Run("bad", {"seed": 0}):
            raise RuntimeError("x")
    with Run("fresh", {"seed": 0}):
        pass
    assert [
        m["name"] for m in archive_candidates(uncited=True, older_than_days=7, root=project)
    ] == []  # 新しい run は守る
    ids = [m["run_id"] for m in archive_candidates(statuses=("failed",), root=project)]
    archive_runs(ids, "x", root=project)
    assert archive_candidates(statuses=("failed",), root=project) == []
    back = [m["run_id"] for m in archive_candidates(statuses=("failed",), archived=True, root=project)]
    assert back == ids
    archive_runs(back, "誤り", undo=True, root=project)
    assert len(list_runs(project)) == 2


def test_state_headings_ignore_code_fences(project):
    put(
        project / "docs" / "state.md",
        "# 今\n\n## 前提\n```python\n# compute J\nx = 1\n```\n## 次の一手\n~~~sh\n# run\n~~~\n",
    )
    assert not issues(project, "L037")


def test_markdown_table_without_tabulate():
    import pandas as pd

    from labkit.cli import _markdown

    md = _markdown(pd.DataFrame({"a": [1, 2], "b": ["x", "y"]}))
    assert md.splitlines()[:3] == ["| a | b |", "|---|---|", "| 1 | x |"]


def test_hooks_protect_beats_claims_and_digest(git_project):
    p = git_project
    assert handle("pretool", bash("echo x >> .lab/beats/2026-11-05.jsonl", p))[0] == 2
    assert handle("pretool", bash("sed -i 's/a/b/' .lab/beats/2026-11-05.jsonl", p))[0] == 2
    assert handle("pretool", bash("echo '| C9 |' >> docs/claims.md", p))[0] == 2
    assert handle("pretool", write("docs/claims.md", p))[0] == 2
    assert handle("pretool", write("docs/DIGEST.md", p))[0] == 2
    assert handle("pretool", bash("uv run labkit claim add 'x' --evidence a:b", p)) == (0, "", "")
    assert handle("pretool", bash("cat docs/claims.md", p)) == (0, "", "")
    # v1.x の承認待ちが残っていても SessionStart は落ちず、もう扱わない（完全自律）
    from labkit import state

    state.save_item(p, {"id": "Q001", "kind": "approval", "status": "approved", "command": "x", "delegation": "D001"})
    code, out, _ = handle("session", {"cwd": str(p)})
    assert code == 0 and "Q001" not in out and "完全自律" in out


def test_session_survives_broken_current_toml(git_project):
    put(git_project / "prompts" / "current.toml", "goal = \n")
    code, out, _ = handle("session", {"cwd": str(git_project)})
    assert code == 0 and "current.toml" in out and "完全自律" in out


def test_claim_add_rejects_bad_evidence_and_parses_positionally(git_project):
    p = git_project
    with Run("good", {"seed": 0, "report": {"noncomparative": ["ratio"]}}) as good:
        good.log_metric("ratio", 0.21608)
    (p / "scripts" / "n.py").write_text("x = 1\n", encoding="utf-8", newline="\n")
    with Run("dirty", {"seed": 0}) as dirty:
        dirty.log_metric("ratio", 0.5)
    with pytest.raises(ValueError, match="dirty"):
        claims.add_claim(p, "x", [f"{dirty.run_id}:ratio"])
    archive_runs([good.run_id], "x", root=p)
    with pytest.raises(ValueError, match="退避済み"):
        claims.add_claim(p, "x", [f"{good.run_id}:ratio"])
    archive_runs([good.run_id], "誤り", undo=True, root=p)
    c = claims.add_claim(p, "無次元", [f"{good.run_id}:ratio:1", f"{good.run_id}:ratio::3", f"{good.run_id}:ratio:%:1"])
    assert (
        c["evidence"]
        == f"0.2161 1 [run:{good.run_id}:ratio]; 0.216 [run:{good.run_id}:ratio]; 0.2 % [run:{good.run_id}:ratio]"
    )
    assert not issues(p, "L033") and not issues(p, "L036")
    with pytest.raises(ValueError, match="桁数"):
        claims.add_claim(p, "x", [f"{good.run_id}:ratio:dB:x"])


def test_beat_end_requires_open_beat_and_decision(git_project):
    p = git_project
    put(
        p / "prompts" / "goal_v1.md",
        "# 目標\n\n## /goal に渡す文\n\n```\n/goal x\n```\n\n## 究極目標\n\n法則を見つける\n",
    )
    put(p / "prompts" / "beat_v1.md", "# 1 拍\n")
    beat.ensure_current(p, "goal_v1.md", "beat_v1.md", "15m")
    with pytest.raises(ValueError, match="start"):
        beat.end(p, decided="x")
    out = beat.start(p)
    assert "/loop 15m /lab-rules:beat" in out and "閉じていない" not in out
    with pytest.raises(ValueError, match="decided"):
        beat.end(p, predicted="a", observed="b")
    assert "未完" in beat.log(p)
    out2 = beat.start(p)  # 閉じずに次を始めると知らせる
    assert "拍 1 は閉じていない" in out2
    assert beat.end(p, decided="d")["beat"] == 2  # 閉じるのは最新の開いた拍、次に残っていた拍 1
    assert beat.end(p, decided="late")["beat"] == 1
    with pytest.raises(ValueError, match="閉じる拍"):
        beat.end(p, decided="again")
    s = handle("session", {"cwd": str(p), "source": "compact"})[1]
    assert "法則を見つける" in s and "/goal x" not in s  # 「目標」の節を再注入する


def test_open_reviews_closed_by_later_pass(project):
    def rv(name, verdict, extra=""):
        put(
            project / "docs" / "reviews" / name,
            f"---\nreviewer: lab-reviewer\nflow: adhoc\nstage: review\ncommit: {'a' * 40}\nverdict: {verdict}\nsummary: s\n{extra}findings: "
            + ('["must: x"]' if verdict != "pass" else "[]")
            + "\n---\n",
        )

    rv("2026-11-01_adhoc_review.md", "changes-requested")
    rv("2026-11-02_adhoc_review.md", "changes-requested")
    # 同じ対象（flow/stage）を見直した新しい記録が現在の状態。古い changes-requested は並べない
    assert [r.path.name for r in open_reviews(project)] == ["2026-11-02_adhoc_review.md"]
    rv("2026-11-03_adhoc_review.md", "pass")
    assert open_reviews(project) == []


def test_git_status_handles_spaces_and_non_ascii(git_project):
    p = git_project
    git(p, "config", "core.quotepath", "true")
    put(p / "docs" / "メモ.md", "x\n")
    put(p / "docs" / "sp ace.md", "x\n")
    assert git_info(p)["dirty"] is False
    put(p / "src" / "has space.py", "x = 1\n")
    put(p / "notebooks" / "n.ipynb", "{}")
    info = git_info(p)
    assert info["dirty"] and info["dirty_paths"] == ["notebooks/n.ipynb", "src/has space.py"]
    assert ("??", "docs/メモ.md") in git_status(p)


def test_sweep_rejects_nested_tables_and_isolates_conditions(project):
    from labkit.runner import run_config

    d = project / "src" / "pk"
    put(d / "__init__.py", "")
    put(
        d / "e.py",
        "SEEN = []\n\n\ndef run(cfg):\n    SEEN.append(cfg['filter'])\n    return {'v': float(cfg['filter']['c'])}\n",
    )
    put(project / "configs" / "bad.toml", 'entry = "pk.e:run"\nseed = 0\n[filter]\nc = 1\n[sweep.filter]\nc = [1, 2]\n')
    with pytest.raises(ValueError, match="sweep"):
        run_config(str(project / "configs" / "bad.toml"), root=project)
    put(
        project / "configs" / "ok.toml", 'entry = "pk.e:run"\nseed = 0\n[filter]\nc = 1\n[sweep]\n"filter.c" = [1, 2]\n'
    )
    run_config(str(project / "configs" / "ok.toml"), root=project)
    import pk.e as mod

    assert [s["c"] for s in mod.SEEN] == [1, 2] and mod.SEEN[0] is not mod.SEEN[1]


def test_digest_staleness_reads_generation_date(git_project):
    from labkit.digest import build, staleness

    build(git_project, since="2000-01-01")
    assert staleness(git_project) is None  # 未 commit でも今日作ったなら古くない
