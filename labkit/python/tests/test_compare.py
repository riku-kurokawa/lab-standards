"""比較は 1 軸だけを変える（ceteris paribus）。各テストはレビューで見つかった抜け道 1 つが塞がれていることを確かめる."""

import copy
import json

import pytest

from labkit import Run, claims
from labkit.check import run_check
from labkit.cli import main
from labkit.compare import COMPARISON_FILE, ConditionMismatch, arm_conditions, chosen, record
from labkit.runs import archive_runs, freeze_run, list_runs

COMMON = {"dof": "PA", "quant_bits": 8, "eval_set": "test-v1", "tuning_configs": 12, "scoring": "rmse"}
DESIGN = {
    "vary": "method",
    "keys": ["gain_db"],
    "common": COMMON,
    "arms": {"ours": {"method": "ours"}, "flat": {"method": "flat"}},
}


def cfg(**design):
    d = copy.deepcopy(DESIGN)
    d.update(copy.deepcopy(design))
    return {"seed": 0, "compare": {"design": d}}


def issues(p, code):
    return [i for i in run_check(root=p)[0] if i.code == code]


def write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


def status(run):
    return json.loads((run.dir / "meta.json").read_text(encoding="utf-8"))


def refused(project, config, match):
    """設定の関門: run ディレクトリを作らずに拒否する."""
    before = len(list((project / "runs").iterdir()))
    with pytest.raises(ConditionMismatch, match=match):
        with Run("x", config):
            pass
    assert len(list((project / "runs").iterdir())) == before


def test_matched_comparison_is_recorded_once_hashed_and_citable(project):
    with Run("ok", cfg()) as run:
        assert arm_conditions(run.config, "design")["flat"] == {**COMMON, "method": "flat"}
        run.log_metric("gain_db", 3.2)
    meta = status(run)
    assert meta["status"] == "finished"
    rec = json.loads((run.dir / COMPARISON_FILE).read_text(encoding="utf-8"))["design"]
    assert rec["matched"] and rec["keys"] == ["gain_db"] and set(rec["arms"]) == {"ours", "flat"}
    assert any(o["path"] == COMPARISON_FILE and o["sha256"] for o in meta["outputs"])
    assert claims.add_claim(project, "利得は 3.2 dB", [f"{run.run_id}:gain_db:dB:1"])["id"] == "C001"
    assert not issues(project, "L027")


def test_bypass_multi_axis_vary_is_refused(project):
    refused(project, cfg(vary=["method", "dof"]), "vary は変える軸 1 つ")
    bundled = {"ours": {"method": {"name": "ours", "dof": "P"}}, "flat": {"method": {"name": "flat", "dof": "PA"}}}
    refused(project, cfg(arms=bundled), "スカラー")  # 軸の値に複数の条件を束ねる


def test_bypass_arm_specific_condition_is_refused(project):
    # 腕の表に軸以外を書く（条件を腕ごとに変える）・common を腕で上書きする・許容差で近い値を通す、はすべて拒否
    refused(project, cfg(arms={"ours": {"method": "ours"}, "flat": {"method": "flat", "dof": "P"}}), "dof")
    refused(project, cfg(arms={"ours": {"method": "ours", "quant_bits": 8}, "flat": {"method": "flat"}}), "quant_bits")
    refused(project, cfg(arms={"ours": {"method": "ours"}, "flat": {"method": "ours"}}), "値が同じ")
    assert not hasattr(Run, "compare")  # 実行時に腕の dict や rel_tol を渡す API は無い


def test_bypass_tolerance_argument_does_not_exist(project):
    from labkit import compare

    assert not hasattr(compare, "declare") and not hasattr(compare, "Arm")
    # 実験間の照合は厳密（TOML の 1 と 1.0 だけを同じとみなす）。許容差は誰も渡せない
    with Run("a", {"seed": 0, "x": 8, "method": "a", "report": {"noncomparative": ["t"]}}) as a:
        a.log_metric("t", 1.0)
    with Run("b", {"seed": 0, "x": 8.0, "method": "b", "report": {"noncomparative": ["t"]}}) as b:
        b.log_metric("t", 2.0)
    with Run("c", {"seed": 0, "x": 8.0001, "method": "c", "report": {"noncomparative": ["t"]}}) as c:
        c.log_metric("t", 3.0)
    claims.add_claim(project, "a と b", [f"{a.run_id}:t", f"{b.run_id}:t"], axis="method")
    with pytest.raises(ValueError, match="'x'"):
        claims.add_claim(project, "a と c", [f"{a.run_id}:t", f"{c.run_id}:t"], axis="method")


def test_bypass_second_record_after_refusal_fails_the_run(project):
    with Run("twice", cfg()) as run:
        run.log_metric("gain_db", 1.0)
        assert record(run) == []  # 自分で記録しても、終了時の記録は 2 回目として拒否される
    assert status(run)["status"] == "failed" and "1 回" in status(run)["error"]
    with Run("forged", cfg()) as run2:
        write(run2.path(COMPARISON_FILE), json.dumps({"design": {"matched": True, "keys": ["gain_db"]}}))
    assert status(run2)["status"] == "failed"


def test_bypass_record_after_finish_or_forged_file_is_rejected(project):
    with Run("plain", {"seed": 0}) as run:
        run.log_metric("gain_db", 5.0)
    assert record(run) == ["比較の記録は running の run の中だけ"]
    freeze_run(run.dir, writable=True)  # 完了後に比較の記録を書き足す
    write(run.dir / COMPARISON_FILE, json.dumps({"design": {"matched": True, "keys": ["gain_db"], "diff": []}}))
    freeze_run(run.dir)
    assert any("comparisons.json" in i.message for i in issues(project, "L027"))
    with pytest.raises(ValueError, match="宣言されていない"):
        claims.add_claim(project, "利得は 5 dB", [f"{run.run_id}:gain_db:dB:1"])


def test_bypass_hand_edited_matched_flag_is_recomputed(project):
    sweep = {"arm": "flat", "param": "h", "values": [1, 2], "metric": "flat_h{value}", "direction": "max"}
    with Run("bad", cfg(sweep=sweep, arms={"ours": {"method": "ours"}, "flat": {"method": "flat", "h": 1}})) as run:
        run.log_metric("flat_h1", 0.1)
        run.log_metric("flat_h2", 0.9)  # 最良は h=2 なのに比較対象は h=1
        run.log_metric("gain_db", 3.0)
    assert status(run)["status"] == "failed"
    freeze_run(run.dir, writable=True)
    f = run.dir / COMPARISON_FILE
    rec = json.loads(f.read_text(encoding="utf-8"))
    rec["design"].update(matched=True, diff=[])
    write(f, json.dumps(rec))
    meta = status(run)
    meta["status"] = "finished"
    write(run.dir / "meta.json", json.dumps(meta))
    freeze_run(run.dir)
    got = issues(project, "L027")
    assert got and any("hash" in i.message or "最良" in i.message for i in got)


def test_bypass_undeclared_key_is_default_denied(project):
    with Run("adhoc", {"seed": 0}) as run:  # 比較を宣言しない run の任意の指標（win_R3c など）
        run.log_metric("ours_over_flat", 2.0)
        run.log_metric("snr_db", 12.0)
    with pytest.raises(ValueError, match="宣言されていない"):
        claims.add_claim(project, "ours は flat の 2 倍", [f"{run.run_id}:ours_over_flat"])
    write(
        project / "docs" / "claims.md",
        claims.HEADER + f"| C001 | 2026-11-10 | 2 倍 | 2.0 [run:{run.run_id}:ours_over_flat] | open | |\n",
    )
    write(project / "docs" / "papers" / "draft.md", f"# 草稿\n\n2.0 [run:{run.run_id}:ours_over_flat]\n")
    got = issues(project, "L027")
    assert {(i.where, i.severity) for i in got} == {("docs/claims.md:7", "error"), ("docs/papers/draft.md:3", "warn")}
    with Run("declared", {"seed": 0, "report": {"noncomparative": ["snr_*"]}}) as ok:
        ok.log_metric("snr_db", 12.0)
    assert claims.add_claim(project, "SNR は 12 dB", [f"{ok.run_id}:snr_db:dB:0"])


def test_bypass_key_bound_to_one_comparison_only(project):
    two = cfg()
    two["compare"]["solver"] = {
        "vary": "dof",
        "keys": ["gain_db"],
        "common": {**{k: v for k, v in COMMON.items() if k != "dof"}, "method": "ours"},
        "arms": {"p": {"dof": "P"}, "pa": {"dof": "PA"}},
    }
    refused(project, two, "両方")  # gain_db が 2 つの比較に属す
    two["compare"]["solver"]["keys"] = ["solver_gain"]
    with Run("multi", copy.deepcopy(two)) as run:  # 名前つきの比較を 2 つ
        run.log_metric("gain_db", 1.0)
        run.log_metric("solver_gain", 2.0)
    assert status(run)["status"] == "finished"
    nc = cfg()
    nc["report"] = {"noncomparative": ["gain_*"]}
    refused(project, nc, "noncomparative")


def test_bypass_cross_run_evidence_needs_axis_and_identical_configs(project):
    def one(name, method, seed=0):
        with Run(name, {"seed": seed, "method": method, "report": {"noncomparative": ["time_s"]}}) as r:
            r.log_metric("time_s", 1.0 if method == "ours" else 3.0)
        return r

    a, b, c = one("a", "ours"), one("b", "base"), one("c", "base", seed=1)
    with pytest.raises(ValueError, match="axis"):
        claims.add_claim(project, "3 倍速い", [f"{a.run_id}:time_s", f"{b.run_id}:time_s"])
    with pytest.raises(ValueError, match="seed"):
        claims.add_claim(project, "3 倍速い", [f"{a.run_id}:time_s", f"{c.run_id}:time_s"], axis="method")
    with Run("d", {"seed": 0, "solver": {"method": "x", "lr": 1}, "report": {"noncomparative": ["time_s"]}}) as d:
        d.log_metric("time_s", 1.0)
    with Run("e", {"seed": 0, "solver": {"method": "y", "lr": 9}, "report": {"noncomparative": ["time_s"]}}) as e:
        e.log_metric("time_s", 2.0)
    with pytest.raises(ValueError, match="スカラー"):  # 表ごとを軸にして複数の条件を変える
        claims.add_claim(project, "x", [f"{d.run_id}:time_s", f"{e.run_id}:time_s"], axis="solver")
    with pytest.raises(ValueError, match="solver.lr"):
        claims.add_claim(project, "x", [f"{d.run_id}:time_s", f"{e.run_id}:time_s"], axis="solver.method")
    got = claims.add_claim(project, "3 倍速い", [f"{a.run_id}:time_s", f"{b.run_id}:time_s"], axis="method")
    assert got["evidence"].startswith("axis=method; ")
    assert not issues(project, "L027")
    text = (project / "docs" / "claims.md").read_text(encoding="utf-8").replace("axis=method; ", "")
    write(project / "docs" / "claims.md", text)  # 手で axis を消す
    assert any("axis" in i.message for i in issues(project, "L027"))


def test_bypass_comparator_sweep_is_declared_and_read_from_metrics(project):
    free = {"ours": {"method": "ours"}, "flat": {"method": "flat", "h": 10}}
    refused(project, cfg(arms=free), "sweep")  # 自由パラメータを固定値で比べる（h=10 の平板）
    sweep = {"arm": "flat", "param": "h", "values": [10, 20, 30], "metric": "flat_h{value}", "direction": "max"}
    with Run("missing", cfg(arms=free, sweep=sweep)) as run:  # スコアを記録しない
        run.log_metric("gain_db", 1.0)
    assert status(run)["status"] == "failed" and "記録されていない" in status(run)["error"]
    auto = {"ours": {"method": "ours"}, "flat": {"method": "flat"}}
    with Run("best", cfg(arms=auto, sweep=sweep)) as run:
        for h, s in ((10, 0.1), (20, 0.5), (30, 0.3)):
            run.log_metric(f"flat_h{h}", s)
        assert chosen(run, "design") == {"flat": {"h": 20}}  # entry は比較対象をこの値で評価する
        run.log_metric("gain_db", 1.0)
    rec = json.loads((run.dir / COMPARISON_FILE).read_text(encoding="utf-8"))["design"]
    assert status(run)["status"] == "finished" and rec["arms"]["flat"]["h"] == 20
    ours_sweep = {"arm": "ours", "param": "lr", "values": [1, 2], "metric": "ours_lr{value}", "direction": "max"}
    refused(project, cfg(sweep=[sweep, ours_sweep]), "調整の予算")


def test_bypass_not_applicable_only_through_declared_capability(project):
    three = {"ours": {"method": "ours"}, "flat": {"method": "flat"}, "gs": {"method": "gs"}}
    refused(project, cfg(arms=three, capability={"gs": ["focus"]}), "objective")
    with Run("cap", cfg(arms=three, objective="nulls", capability={"gs": ["focus"]})) as run:
        run.log_metric("gain_db", 1.0)
    rec = json.loads((run.dir / COMPARISON_FILE).read_text(encoding="utf-8"))["design"]
    assert set(rec["arms"]) == {"ours", "flat"} and set(rec["not_applicable"]) == {"gs"}
    refused(project, cfg(objective="nulls", capability={"flat": ["focus"]}), "2 本以上")
    refused(project, cfg(not_applicable={"flat": "負けたので"}), "知らない項目")


def test_required_conditions_from_lab_toml(project):
    write(project / "lab.toml", '[lab]\nproject = "t"\n[compare]\nrequired = ["dof", "field_model"]\n')
    refused(project, cfg(), "field_model")
    refused(project, cfg(common={**COMMON, "field_model": ""}), "field_model")
    with Run("ok", cfg(common={**COMMON, "field_model": "rayleigh"})) as run:
        run.log_metric("gain_db", 1.0)
    assert status(run)["status"] == "finished"


def test_non_table_compare_and_retracted_status_column(project):
    refused(project, {"seed": 0, "compare": "x"}, r"\[compare\]")
    with Run("adhoc", {"seed": 0}) as run:
        run.log_metric("k", 1.0)
    # 状態の列が open なら、備考に "| retracted |" があっても照合する
    write(
        project / "docs" / "claims.md",
        claims.HEADER + f"| C001 | 2026-11-10 | x | 1.0 [run:{run.run_id}:k] | open | 旧 | retracted | 注 |\n",
    )
    assert [i.where for i in issues(project, "L027")] == ["docs/claims.md:7"]


def test_archive_undo_keeps_history_and_needs_reason(project):
    with Run("a", {"seed": 0}) as run:
        run.log_metric("e", 0.5)
    assert main(["runs", "archive", run.run_id, "--reason", "条件不一致: dof"]) == 0
    with pytest.raises(SystemExit, match="理由"):
        main(["runs", "archive", run.run_id, "--undo"])
    with pytest.raises(ValueError, match="理由"):
        archive_runs([run.run_id], "", undo=True, root=project)
    assert main(["runs", "archive", run.run_id, "--undo", "--reason", "誤り"]) == 0
    log = status(run)["archive_log"]
    assert [x["action"] for x in log] == ["archive", "unarchive"] and log[0]["reason"] == "条件不一致: dof"
    assert list_runs(project)


def test_archive_by_explicit_ids_and_l032_error(git_project):
    p = git_project
    runs = []
    for name in ("a", "b"):
        with Run(name, {"seed": 0, "report": {"noncomparative": ["e"]}}) as r:
            r.log_metric("e", 0.5)
        runs.append(r)
    write(p / "docs" / "papers" / "draft.md", f"0.5 [run:{runs[0].run_id}:e]\n言及だけ {runs[1].run_id}\n")
    with pytest.raises(SystemExit, match="理由"):
        main(["runs", "archive", runs[0].run_id, runs[1].run_id])
    assert main(["runs", "archive", runs[0].run_id, runs[1].run_id, "--reason", "条件不一致: dof が違う"]) == 0
    assert not list_runs(p) and all(r.dir.is_dir() for r in runs)  # 削除はしない
    got = issues(p, "L032")
    errors = [i for i in got if i.severity == "error"]
    assert [i.where for i in errors] == ["docs/papers/draft.md:1"] and "退避済み" in errors[0].message
    assert any(i.severity == "warn" and "退避済み" in i.message for i in got)  # ID だけの言及は警告
    with pytest.raises(SystemExit, match="1 つだけ"):
        main(["runs", "show", runs[0].run_id, runs[1].run_id])
