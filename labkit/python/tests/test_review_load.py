"""人間のレビュー負荷を下げる仕組み: 引用の照合の拡張、行数、台帳、state、退避、予想の判定、事前の合否."""

import json

import pytest

from labkit import Run, claims
from labkit.check import cited_run_ids, run_check
from labkit.runs import archive_candidates, archive_runs, list_runs, runs_table, verdict_run

from .conftest import git


def issues(project, code, **kw):
    return [i for i in run_check(root=project, **kw)[0] if i.code == code]


def write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


def test_citations_skip_auto_block_and_cover_docs_tree(git_project):
    p = git_project
    with Run("c", {"seed": 0}) as run:
        run.log_metric("e1", 0.0199)
    write(
        p / "docs" / "papers" / "draft.md",
        f"# 草稿\n\n## 結果\n\n0.02 rel [run:{run.run_id}:e1] と 0.03 rel [run:{run.run_id}:e1]\n見つからない 20260101-000000_x_abcdef0_0000\n",
    )
    write(
        p / "docs" / "devlog" / "2026-11-05.md",
        "## 目的\nx\n## 結果・観察\n\n誤差 0.5 % は 0.02 rel [run:" + run.run_id + ":e1] と同じ行\n裸の 1.5e-3\n"
        "## 判断と理由\ny\n## 未解決・次の作業\nz\n<!-- labkit:auto -->\n- 20260101-000000_auto_abcdef0_0000 finished\n<!-- /labkit:auto -->\n",
    )
    write(
        p / "docs" / "papers" / "units.md",
        f"## 結果\n\n比 0.0199 1 [run:{run.run_id}:e1]（1.99 % [run:{run.run_id}:e1]）。加速度 0.02 m/s^2 [run:{run.run_id}:e1]。"
        f"速さ（3.75 m/s）・0.02 [run:{run.run_id}:e1]\n",
    )  # 無次元の単位 "1"、% の換算、括弧で区切られた直前でない数値は拾わない
    got = run_check(root=p)[0]
    assert [i.where for i in got if i.code == "L033"] == ["docs/papers/draft.md:5"]  # docs/** も照合する
    assert [i.where for i in got if i.code == "L032" and "link" not in i.message] == [
        "docs/papers/draft.md:6"
    ]  # 自動ブロックの run は見ない
    assert [i.where for i in got if i.code == "L034"] == ["docs/devlog/2026-11-05.md:6"]  # 引用を含む行は対象外
    assert set(cited_run_ids(p)) == {run.run_id, "20260101-000000_x_abcdef0_0000"}


def test_dirty_and_archived_citations(git_project):
    p = git_project
    (p / "scripts" / "n.py").write_text("x = 1\n", encoding="utf-8", newline="\n")
    with Run("d", {"seed": 0}) as run:
        run.log_metric("a", 1.0)
    write(
        p / "docs" / "devlog" / "2026-11-05.md",
        f"## 目的\nx\n## 結果・観察\n\n1.0 x [run:{run.run_id}:a]\n## 判断と理由\ny\n## 未解決・次の作業\nz\n",
    )
    write(
        p / "docs" / "reviews" / "2026-11-05_adhoc_review.md",
        f"---\nreviewer: lab-reviewer\nflow: adhoc\nstage: review\ncommit: {'a' * 40}\nverdict: pass\nsummary: ok\nfindings: []\n---\nrun {run.run_id} は dirty\n",
    )
    dirty = [i for i in issues(p, "L032") if "dirty" in i.message]
    assert [i.where for i in dirty] == ["docs/devlog/2026-11-05.md:5"] and dirty[
        0
    ].severity == "warn"  # レビュー記録は対象外
    write(p / "lab.toml", '[lab]\nproject = "t"\n[check]\nmode = "strict"\ndirty_citation = "error"\n')
    assert [i.severity for i in issues(p, "L032") if "dirty" in i.message] == ["error"]
    archive_runs([run.run_id], "試行", root=p)
    assert any("退避済み" in i.message for i in issues(p, "L032"))
    assert not list_runs(p) and len(list_runs(p, include_archived=True)) == 1
    archive_runs([run.run_id], "", undo=True, root=p)
    assert len(list_runs(p)) == 1


def test_archive_candidates_and_running_guard(project):
    with Run("ok", {"seed": 0}) as a:
        a.log_metric("x", 1.0)
    with pytest.raises(RuntimeError):
        with Run("bad", {"seed": 0}):
            raise RuntimeError("x")
    with Run("child", {"seed": 0}, inputs=[a.dir / "metrics.json"]):
        pass
    r = Run("live", {"seed": 0})
    r.__enter__()
    from labkit.runs import _current

    _current.reset(r._token)
    cands = archive_candidates(statuses=("failed",), root=project)
    assert [m["name"] for m in cands] == ["bad"]
    write(project / "docs" / "note.md", f"引用 {a.run_id}")
    unc = archive_candidates(uncited=True, root=project)
    assert [m["name"] for m in unc] == ["child"]  # 引用された a と running は候補にならない
    with pytest.raises(ValueError, match="running"):
        archive_runs([r.run_id], "x", root=project)


def test_require_clean(git_project):
    with open(git_project / "lab.toml", "a", encoding="utf-8", newline="\n") as f:
        f.write("[runs]\nrequire_clean = true\n")
    git(git_project, "commit", "-qam", "clean gate")
    with Run("clean", {"seed": 0}):
        pass
    (git_project / "scripts" / "n.py").write_text("x = 1\n", encoding="utf-8", newline="\n")
    with pytest.raises(ValueError, match="require_clean"):
        with Run("dirty", {"seed": 0}):
            pass
    assert len(list_runs(git_project)) == 1


def test_structured_prediction_auto_verdict_and_self_report(project):
    pred = {
        "basis": "V2-c の模型差",
        "expert_predictable": False,
        "claims": [
            {"key": "e1", "range": [0.01, 0.03]},
            {"key": "e2", "point": 1.0, "tol": 0.1},
            {"key": "missing", "range": [0, 1]},
        ],
    }
    with Run("p", {"seed": 0, "prediction": pred}) as run:
        run.log_metric("e1", 0.02)
        run.log_metric("e2", 2.0)
    meta = json.loads((run.dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["prediction_result"] == {"verdict": "partial", "hit": 1, "total": 2, "undeterminable": 1}
    assert not issues(project, "L024")
    with pytest.raises(ValueError, match="basis"):
        with Run("nobasis", {"seed": 0, "prediction": {"claims": []}}):
            pass
    with Run("free", {"seed": 0, "prediction": "e1 は 0.02 くらい"}) as free:
        free.log_metric("e1", 0.5)
    assert [i.where for i in issues(project, "L024")] == [f"runs/{free.run_id}"]
    with pytest.raises(ValueError, match="--say"):
        verdict_run(free.run_id, root=project)
    r = verdict_run(free.run_id, say="miss", note="25 倍外れ", root=project)
    assert r["self_reported"] and r["verdict"] == "miss" and not issues(project, "L024")
    meta = json.loads((free.dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["prediction_result"]["note"] == "25 倍外れ"


def test_pass_criteria_in_config(project):
    pytest.importorskip("pyarrow")
    import pandas as pd

    from labkit import runpath, save

    cfg = {
        "seed": 0,
        "pass": [
            {"key": "snr_db", "min": 10},
            {"key": "err", "max": 0.5, "table": "results.parquet", "where": {"wall": "char"}},
            {"key": "nokey", "max": 1},
        ],
    }
    with Run("gate", cfg) as run:
        run.log_metric("snr_db", 12.0)
        save(runpath(run, "results.parquet"), pd.DataFrame({"wall": ["char", "char", "rigid"], "err": [0.1, 0.4, 9.0]}))
    m = json.loads((run.dir / "metrics.json").read_text(encoding="utf-8"))
    assert (m["pass_1"], m["pass_2"], m["pass_3"], m["pass_all"]) == (1.0, 1.0, 0.0, 0.0)


def test_runs_table_concatenates_clean_finished(git_project):
    pytest.importorskip("pyarrow")
    import pandas as pd

    from labkit import runpath, save

    for v in (1, 2):
        with Run("sweep", {"seed": 0}) as run:
            save(runpath(run, "results.parquet"), pd.DataFrame({"k": [v], "y": [v * 2.0]}))
    (git_project / "scripts" / "n.py").write_text("x = 1\n", encoding="utf-8", newline="\n")
    with Run("sweep", {"seed": 0}) as dirty:
        save(runpath(dirty, "results.parquet"), pd.DataFrame({"k": [3], "y": [6.0]}))
    with Run("agg", {"seed": 0}) as agg:
        df = runs_table("sweep", root=git_project)
    assert (
        sorted(df["k"]) == [1, 2]
        and df.attrs["excluded"][0][1] == "dirty"
        and list(df.columns[:2]) == ["run_id", "commit"]
    )
    meta = json.loads((agg.dir / "meta.json").read_text(encoding="utf-8"))
    assert len(meta["inputs"]) == 2 and all(i["sha256"] for i in meta["inputs"])
    assert runs_table("sweep", include_all=True, root=git_project)["k"].sort_values().tolist() == [1, 2, 3]


def test_file_length_and_scripts_imports(project):
    body = "\n".join(f"x{i} = {i}" for i in range(301)) + "\n"
    write(project / "scripts" / "long.py", body)
    write(project / "src" / "long.py", body)
    write(project / "tests" / "test_long.py", body)
    write(project / "scripts" / "b.py", "from scripts.long import x1\n")
    got = run_check(root=project)[0]
    assert sorted(i.where for i in got if i.code == "L018") == ["scripts/long.py", "src/long.py"]
    assert all(i.severity == "warn" for i in got if i.code == "L018")
    l011 = [i for i in got if i.code == "L011"]
    assert [i.where for i in l011] == ["scripts/b.py:1"] and l011[0].severity == "warn"
    write(project / "lab.toml", '[lab]\nproject = "t"\n[check]\nmax_file_lines = 400\nlong_file = "error"\n')
    assert not issues(project, "L018")
    write(project / "lab.toml", '[lab]\nproject = "t"\n[check]\nmax_file_lines = 0\n')
    assert not issues(project, "L018")


def test_entry_in_config_counts_as_used_module(project):
    pkg = project / "src" / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8", newline="\n")
    (pkg / "exp.py").write_text("def run(cfg):\n    return {}\n", encoding="utf-8", newline="\n")
    assert [i.where for i in issues(project, "L017")] == ["src/pkg/exp.py"]
    write(project / "configs" / "experiments" / "e.toml", 'entry = "pkg.exp:run"\n')
    assert not issues(project, "L017")


def test_labkit_version_mismatch(git_project, monkeypatch):
    p = git_project
    (p / "pyproject.toml").write_text(
        '[tool.uv.sources]\nlabkit = { git = "https://github.com/o/lab-standards.git", tag = "v9.9.9", subdirectory = "labkit/python" }\n',
        encoding="utf-8",
        newline="\n",
    )
    git(p, "add", "-A")
    git(p, "commit", "-q", "-m", "pin")
    with Run("new", {"seed": 0}):
        pass
    got = issues(p, "L023")
    assert len(got) == 1 and "9.9.9" in got[0].message and got[0].severity == "warn"


def test_claims_ledger(git_project):
    p = git_project
    with Run("c", {"seed": 0}) as run:
        run.log_metric("loss_pct", 13.21)
    with pytest.raises(ValueError, match="根拠"):
        claims.add_claim(p, "根拠なし", [])
    c = claims.add_claim(p, "焦点の損失は 13 %", [f"{run.run_id}:loss_pct:%:1"], note="prereg:design")
    assert c["id"] == "C001" and c["evidence"] == f"13.2 % [run:{run.run_id}:loss_pct]"
    assert not issues(p, "L036") and not issues(p, "L033")
    (p / "docs" / "claims.md").write_text(
        (p / "docs" / "claims.md").read_text(encoding="utf-8").replace("13.2 %", "99.9 %"),
        encoding="utf-8",
        newline="\n",
    )
    assert issues(p, "L033")  # 台帳の数値も実データと照合する
    archive_runs([run.run_id], "再実行した", root=p)
    bad = issues(p, "L036")
    assert len(bad) == 1 and "退避済み" in bad[0].message and bad[0].severity == "error"
    with pytest.raises(ValueError, match="理由"):
        claims.retract_claim(p, "C001", "")
    r = claims.retract_claim(p, "C001", "clean 再実行で 9 % に下がった")
    assert r["status"] == "retracted" and not issues(p, "L036")
    assert claims.list_claims(p, "retracted")[0]["note"].startswith("prereg:design; 撤回")
    with pytest.raises(ValueError, match="撤回済み"):
        claims.retract_claim(p, "C001", "x")


def test_state_file_structure_and_scratch_evidence(project):
    write(project / "docs" / "state.md", "# v8\n\n## 前提\n\n# v7\n\n## 前提\n\n" + "行\n" * 160)
    got = issues(project, "L037")
    assert sorted((i.severity, "H1" in i.message or "H2" in i.message) for i in got) == [
        ("error", True),
        ("error", True),
        ("warn", False),
    ]
    write(project / "docs" / "state.md", "# 今\n\n## 前提\n\n- a\n")
    assert not issues(project, "L037")
    write(
        project / "docs" / "devlog" / "2026-11-05.md",
        "## 目的\nx\n## 結果・観察\n\n証拠は scratch/betA/out.json を参照\n## 判断と理由\ny\n## 未解決・次の作業\nscratch/ を片付ける\n",
    )
    got = issues(project, "L038")
    assert [i.where for i in got] == ["docs/devlog/2026-11-05.md:5"] and got[0].severity == "warn"
