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


def sw(arm, param, values, direction="max"):
    """掃引（比較の指標 gain_db で採点する）."""
    return {
        "arm": arm,
        "param": param,
        "values": values,
        "metric": f"gain_db_{arm}_{param}{{value}}",
        "direction": direction,
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
    sweeps = [sw("flat", "h", [1, 2]), sw("ours", "lr", [1, 2])]
    arms = {"ours": {"method": "ours"}, "flat": {"method": "flat", "h": 1}}
    with Run("bad", cfg(sweep=sweeps, better="max", arms=arms)) as run:
        run.log_metric("gain_db_flat_h1", 0.1)
        run.log_metric("gain_db_flat_h2", 0.9)  # 最良は h=2 なのに比較対象は h=1
        run.log_metric("gain_db_ours_lr1", 0.5)
        run.log_metric("gain_db_ours_lr2", 0.4)
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
    assert {(i.where, i.severity) for i in got} == {("docs/claims.md:7", "error"), ("docs/papers/draft.md:3", "error")}
    write(project / "docs" / "papers" / "draft.md", "# 草稿\n")
    write(project / "docs" / "devlog" / "2026-11-10.md", f"# x\n\n2.0 [run:{run.run_id}:ours_over_flat]\n")
    assert any(i.severity == "warn" and "devlog" in i.where for i in issues(project, "L027"))  # 開発ログだけ警告
    with Run("declared", {"seed": 0, "report": {"noncomparative": ["snr_*"]}}) as ok:
        ok.log_metric("snr_db", 12.0)
    assert claims.add_claim(project, "SNR は 12 dB", [f"{ok.run_id}:snr_db:dB:0"])


def test_bypass_key_bound_to_one_comparison_only(project):
    two = cfg()
    two["compare"]["solver"] = {
        "vary": "dof",
        "keys": ["gain_db"],
        "common": {**{k: v for k, v in COMMON.items() if k != "dof"}, "method": "ours"},
        "arms": {"P": {"dof": "P"}, "PA": {"dof": "PA"}},
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
    sweeps = [sw("flat", "h", [10, 20, 30]), sw("ours", "lr", [1, 2, 3])]
    with Run("missing", cfg(arms=free, sweep=sweeps, better="max")) as run:  # スコアを記録しない
        run.log_metric("gain_db", 1.0)
    assert status(run)["status"] == "failed" and "記録されていない" in status(run)["error"]
    auto = {"ours": {"method": "ours"}, "flat": {"method": "flat"}}
    with Run("best", cfg(arms=auto, sweep=sweeps, better="max")) as run:
        for h, s in ((10, 0.1), (20, 0.5), (30, 0.3)):
            run.log_metric(f"gain_db_flat_h{h}", s)
        for lr, s in ((1, 0.2), (2, 0.1), (3, 0.6)):
            run.log_metric(f"gain_db_ours_lr{lr}", s)
        assert chosen(run, "design") == {"flat": {"h": 20}, "ours": {"lr": 3}}  # entry は比較対象をこの値で評価する
        run.log_metric("gain_db", 1.0)
    rec = json.loads((run.dir / COMPARISON_FILE).read_text(encoding="utf-8"))["design"]
    assert status(run)["status"] == "finished" and rec["arms"]["flat"]["h"] == 20


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


# ---- 2 回目のレビュー（A–O）の抜け道。各テストは抜け道 1 つが塞がれていることを確かめる ----
def plain(name, metrics, **config):
    with Run(name, {"seed": 0, **config}) as r:
        for k, v in metrics.items():
            r.log_metric(k, v)
    return r


def test_a_wildcard_noncomparative_is_refused(project):
    for pat in ("*", "?*", "*_db", "[a-z]*", "s*"):
        refused(project, {"seed": 0, "report": {"noncomparative": [pat]}}, "広すぎる")
    # 比較を宣言しない run でも、比べる語（minus・vs・over…）を含む指標は非比較にできない
    refused(project, {"seed": 0, "report": {"noncomparative": ["ours_minus_flat_db"]}}, "比べる語")
    r = plain("x", {"ours_minus_flat_db": 2.0}, report={"noncomparative": ["ours_*"]})
    with pytest.raises(ValueError, match="比べる語"):
        claims.add_claim(project, "ours は flat より 2 dB 上", [f"{r.run_id}:ours_minus_flat_db"])


def test_b_comparative_side_key_in_compare_run_is_not_citable(project):
    refused(project, {**cfg(), "report": {"noncomparative": ["flat_*"]}}, "腕 'flat'")
    refused(project, {**cfg(), "report": {"noncomparative": ["gain_raw"]}}, "語幹")
    with Run("side", {**cfg(), "report": {"noncomparative": ["raw_*"]}}) as run:
        run.log_metric("gain_db", 1.0)
        run.log_metric("raw_ours_fixed_h10", 9.0)  # 宣言した比較が見ていない条件での腕どうしの数値
        run.log_metric("raw_power_w", 1.0)
    assert status(run)["status"] == "finished"
    with pytest.raises(ValueError, match="腕 'ours'"):
        claims.add_claim(project, "ours は 9", [f"{run.run_id}:raw_ours_fixed_h10"])
    assert claims.add_claim(project, "電力は 1 W", [f"{run.run_id}:raw_power_w:W:0"])


def test_c_arm_named_tables_outside_compare_are_refused(project):
    per_arm = {**cfg(), "solver": {"ours": {"lr": 0.1, "steps": 1000}, "flat": {"lr": 0.001, "steps": 10}}}
    refused(project, per_arm, "solver.ours")
    refused(project, {**cfg(), "flat_steps": 10}, "flat_steps")
    c = cfg()
    c["compare"]["design"]["common"] = {**COMMON, "lr": {"ours": 0.1, "flat": 0.001}}  # common の中の腕ごとの表
    refused(project, c, "common.lr.ours")


def test_d_axis_value_is_one_token_naming_the_arm_or_a_level(project):
    bundled = {"ours": {"method": "ours+lr0.1+fp64"}, "flat": {"method": "flat+lr0.001+fp16"}}
    refused(project, cfg(arms=bundled), "1 語")
    refused(project, cfg(arms={"ours": {"method": "ours lr"}, "flat": {"method": "flat"}}), "1 語")
    renamed = {"ours": {"method": "ours_lr01_fp64"}, "flat": {"method": "flat"}}
    refused(project, cfg(arms=renamed), "腕の名前")
    bits = {"b8": {"quant_bits": 8}, "b16": {"quant_bits": 16}}
    common = {k: v for k, v in COMMON.items() if k != "quant_bits"} | {"method": "ours"}
    refused(project, cfg(vary="quant_bits", common=common, arms=bits), "levels")
    with Run("bits", cfg(vary="quant_bits", common=common, arms=bits, levels=[8, 16])) as run:
        run.log_metric("gain_db", 1.0)
    assert status(run)["status"] == "finished"


def test_e_equal_total_tuning_trials_per_arm(project):
    four = [sw("ours", p, [1, 2, 3]) for p in ("a", "b", "c", "d")]
    refused(project, cfg(better="max", sweep=[*four, sw("flat", "h", [1, 2, 3])]), "総試行数")
    refused(project, cfg(better="max", sweep=[sw("ours", "lr", [1, 2, 3, 4, 5])]), "総試行数")  # 比較対象は調整なし
    refused(project, cfg(better="max", sweep=[sw("flat", "h", [1, 2, 3])]), "総試行数")  # ours は調整なし
    ok = [sw("ours", "a", [1, 2]), sw("ours", "b", [1, 2]), sw("flat", "h", [1, 2, 3, 4])]
    with Run("eq", cfg(better="max", sweep=ok)) as run:
        for m in ["gain_db_ours_a1", "gain_db_ours_a2", "gain_db_ours_b1", "gain_db_ours_b2"]:
            run.log_metric(m, 1.0)
        for h in (1, 2, 3, 4):
            run.log_metric(f"gain_db_flat_h{h}", float(h))
        run.log_metric("gain_db", 1.0)
    assert status(run)["status"] == "finished"


def test_f_internal_key_is_not_a_cross_run_axis(project):
    from labkit.check import run_index
    from labkit.compare import cross_run_problem

    a = plain("a", {"t": 1.0}, report={"noncomparative": ["t"]})
    b = plain("b", {"t": 2.0}, report={"noncomparative": ["t"]})
    with pytest.raises(ValueError, match="内部の鍵"):
        claims.add_claim(project, "a と b", [f"{a.run_id}:t", f"{b.run_id}:t"], axis="_git_commit")
    assert "内部の鍵" in cross_run_problem(run_index(project), [a.run_id, b.run_id], "_git_commit")


def test_g_claim_text_and_note_citations_are_checked(project):
    r = plain("g", {"ours_minus_flat": 3.0, "snr_db": 12.0}, report={"noncomparative": ["snr_*"]})
    bad = f"ours は flat より 3.0 [run:{r.run_id}:ours_minus_flat] 上"
    with pytest.raises(ValueError, match="ours_minus_flat"):
        claims.add_claim(project, bad, [f"{r.run_id}:snr_db:dB:0"])
    with pytest.raises(ValueError, match="ours_minus_flat"):
        claims.add_claim(project, "SNR", [f"{r.run_id}:snr_db:dB:0"], note=f"3.0 [run:{r.run_id}:ours_minus_flat]")
    row = f"| C001 | 2026-11-10 | {bad} | 12 dB [run:{r.run_id}:snr_db] | open | |\n"
    write(project / "docs" / "claims.md", claims.HEADER + row)
    assert any("ours_minus_flat" in i.message and i.severity == "error" for i in issues(project, "L027"))


def test_h_cross_run_numbers_in_other_docs(project):
    def state_issues():
        return [i for i in issues(project, "L027") if i.where.startswith("docs/state.md")]

    a = plain("a", {"gain": 3.0}, lr=0.1, report={"noncomparative": ["gain"]})
    b = plain("b", {"gain": 1.0}, lr=0.001, report={"noncomparative": ["gain"]})
    line = f"ours 3.0 [run:{a.run_id}:gain] > flat 1.0 [run:{b.run_id}:gain]"
    write(project / "docs" / "state.md", f"# 状態\n\n{line}\n")
    got = state_issues()
    assert any(i.severity == "error" and "axis" in i.message for i in got)
    write(project / "docs" / "state.md", f"# 状態\n\naxis=lr {line}\n")
    assert not state_issues()  # 軸 lr だけが違う行は通る（行の並置の警告も同じ行の axis で消える）
    c = plain("c", {"gain": 1.0}, lr=0.001, extra=1, report={"noncomparative": ["gain"]})
    write(project / "docs" / "state.md", f"# 状態\n\naxis=lr\n3.0 [run:{a.run_id}:gain] > 1.0 [run:{c.run_id}:gain]\n")
    assert any("extra" in i.message and i.severity == "error" for i in state_issues())
    write(project / "docs" / "state.md", "# 状態\n")
    write(project / "docs" / "devlog" / "2026-11-10.md", f"# x\n\n{line}\n")
    got = [i for i in issues(project, "L027") if "devlog" in i.where]
    assert got and all(i.severity == "warn" for i in got)


def test_i_kill_then_forge_then_mark_finished_is_refused(project):
    from labkit.runs import _current, mark_run

    def killed(config):
        r = Run("k", config)
        r.__enter__()
        _current.reset(r._token)  # __exit__ を通らずに止まった run（kill）
        return r

    r = killed(cfg())
    r.log_metric("gain_db", 3.0)
    with pytest.raises(ValueError, match="比較"):
        mark_run(r.run_id, "finished", root=project)
    write(r.dir / COMPARISON_FILE, json.dumps({"design": {"matched": True, "keys": ["gain_db"], "diff": []}}))
    with pytest.raises(ValueError, match=COMPARISON_FILE):
        mark_run(r.run_id, "finished", root=project)
    assert mark_run(r.run_id, "failed", "kill", root=project)["status"] == "failed"
    r2 = killed({"seed": 0, "report": {"noncomparative": ["snr_db"]}})
    r2.log_metric("ours_vs_flat", 2.0)
    write(r2.dir / "config.json", json.dumps({"seed": 0, "report": {"noncomparative": ["ours_vs_flat"]}}))
    with pytest.raises(ValueError, match="hash"):
        mark_run(r2.run_id, "finished", root=project)


def test_j_hand_edited_config_with_updated_outputs_is_caught_by_start_hash(project):
    from labkit._util import sha256_file

    r = plain("j", {"gain_db_x": 2.0}, report={"noncomparative": ["snr_db"]})
    freeze_run(r.dir, writable=True)  # 完了後に設定を書き換え、outputs の hash も更新する（config_sha256 は残る）
    write(r.dir / "config.json", json.dumps({"seed": 0, "report": {"noncomparative": ["gain_db_x"]}}))
    meta = status(r)
    for o in meta["outputs"]:
        if o["path"] == "config.json":
            o["sha256"] = sha256_file(r.dir / "config.json")
    write(r.dir / "meta.json", json.dumps(meta))
    freeze_run(r.dir)
    with pytest.raises(ValueError, match="config_sha256"):
        claims.add_claim(project, "2", [f"{r.run_id}:gain_db_x"])
    # meta.config_sha256 まで書き換える偽造は手元の照合では検出できない（docs/harness.md の残る危険）


LAB_CAP = '[lab]\nproject = "t"\n[compare.capability]\ngs = ["focus"]\nflat = ["focus", "nulls"]\n'


def test_k_not_applicable_is_checked_against_lab_toml(project):
    three = {"ours": {"method": "ours"}, "flat": {"method": "flat"}, "gs": {"method": "gs"}}
    with Run("author", cfg(arms=three, objective="focus", capability={"gs": ["not_focus"]})) as run:
        run.log_metric("gain_db", 1.0)
    rec = json.loads((run.dir / COMPARISON_FILE).read_text(encoding="utf-8"))["design"]
    assert rec["author_declared_not_applicable"] == ["gs"] and rec["not_applicable"]["gs"]["source"] == "author"
    assert any(i.severity == "warn" and "著者の宣言" in i.message for i in issues(project, "L027"))
    write(project / "lab.toml", LAB_CAP)  # 人間の登録では gs は focus を受け取れる
    refused(project, cfg(arms=three, objective="focus", capability={"gs": ["not_focus"]}), "食い違う")
    assert any(i.severity == "error" and "食い違う" in i.message for i in issues(project, "L027"))
    with Run("lab", cfg(arms=three, objective="nulls")) as run2:  # lab.toml だけで gs は対象外
        run2.log_metric("gain_db", 1.0)
    rec = json.loads((run2.dir / COMPARISON_FILE).read_text(encoding="utf-8"))["design"]
    assert rec["not_applicable"]["gs"]["source"] == "lab.toml" and not rec["author_declared_not_applicable"]


def test_l_placeholder_values_for_required_conditions(project):
    write(project / "lab.toml", '[lab]\nproject = "t"\n[compare]\nrequired = ["field_model"]\n')
    for v in ("n/a", "None", "null", "-", "TBD", "unknown", "?", "未定", " ", ["n/a"]):
        refused(project, cfg(common={**COMMON, "field_model": v}), "field_model")


def test_m_config_changed_mid_run_fails_the_run(project):
    with Run("pop", cfg()) as run:
        run.config.pop("compare")
        run.config["report"] = {"noncomparative": ["gain_*"]}
        run.log_metric("gain_db", 3.0)
    assert status(run)["status"] == "failed" and "途中" in status(run)["error"]
    with Run("rewrite", cfg()) as run2:
        write(run2.dir / "config.json", json.dumps({"seed": 0, "report": {"noncomparative": ["gain_db"]}}))
        run2.log_metric("gain_db", 3.0)
    assert status(run2)["status"] == "failed" and "hash" in status(run2)["error"]
    with Run("nc", {"seed": 0, "report": {"noncomparative": ["snr_db"]}}) as run3:
        run3.config["report"]["noncomparative"].append("gain_db")
        run3.log_metric("gain_db", 3.0)
    assert status(run3)["status"] == "failed"
    with pytest.raises(ValueError, match="failed"):
        claims.add_claim(project, "3", [f"{run3.run_id}:gain_db"])


def test_n_sweep_direction_and_metric_are_tied_to_the_comparison(project):
    both = [sw("ours", "lr", [1, 2]), sw("flat", "h", [1, 2], direction="min")]
    refused(project, cfg(better="max", sweep=both), "direction='min'")
    refused(project, cfg(sweep=[sw("ours", "lr", [1, 2]), sw("flat", "h", [1, 2])]), "better")
    other = {**sw("flat", "h", [1, 2]), "metric": "flat_worst_h{value}"}
    refused(project, cfg(better="max", sweep=[sw("ours", "lr", [1, 2]), other]), "含まない")


def test_o_cross_run_compares_compare_common_and_arms(project):
    def one(name, **common):
        with Run(name, cfg(common={**COMMON, **common})) as r:
            r.log_metric("gain_db", 1.0)
        assert status(r)["status"] == "finished"
        return r

    a = one("a", dof="PA", quant_bits=8, eval_set="test-v1")
    b = one("b", dof="P", quant_bits=16, eval_set="easy")
    with pytest.raises(ValueError, match="compare.design.common"):
        claims.add_claim(project, "a と b", [f"{a.run_id}:gain_db", f"{b.run_id}:gain_db"], axis="seed")


# ---- 3 回目のレビューの抜け道。各テストは抜け道 1 つが塞がれていることを確かめる ----
def test_p_axis_values_in_levels_name_the_arms(project):
    ab = {"a": {"method": "proposed"}, "b": {"method": "baseline"}}
    base = cfg(arms=ab, levels=["proposed", "baseline"])
    refused(project, {**base, "solver": {"proposed": {"steps": 1000}, "baseline": {"steps": 10}}}, "solver.proposed")
    refused(project, {**base, "report": {"noncomparative": ["score_proposed", "score_baseline"]}}, "proposed")
    with Run("lv", {**base, "report": {"noncomparative": ["score_*"]}}) as run:
        run.log_metric("gain_db", 1.0)
        run.log_metric("score_proposed", 2.0)
    with pytest.raises(ValueError, match="proposed"):
        claims.add_claim(project, "proposed は 2", [f"{run.run_id}:score_proposed"])


def test_q_claims_are_comparative_by_default(project):
    r = plain("noc", {"gain_ours": 3.0, "gain_flat": 1.0}, report={"noncomparative": ["gain_ours", "gain_flat"]})
    with pytest.raises(ValueError, match="比較でない値"):
        claims.add_claim(project, "ours > flat", [f"{r.run_id}:gain_ours", f"{r.run_id}:gain_flat"])
    with pytest.raises(ValueError, match="比較でない値"):  # 本文に書いても同じ
        claims.add_claim(project, f"ours > flat 1.0 [run:{r.run_id}:gain_flat]", [f"{r.run_id}:gain_ours"])
    assert claims.add_claim(project, "ours は 3", [f"{r.run_id}:gain_ours"])  # 1 つだけなら引ける
    with Run("m", {**cfg(), "report": {"noncomparative": ["snr_*"]}}) as m:
        m.log_metric("gain_db", 2.0)
        m.log_metric("snr_db", 12.0)
    assert claims.add_claim(project, "利得 2 dB（SNR 12 dB）", [f"{m.run_id}:gain_db", f"{m.run_id}:snr_db"])


def test_r_cross_run_check_is_per_document(project):
    def state_issues():
        return [i for i in issues(project, "L027") if i.where.startswith("docs/state.md")]

    a = plain("a", {"gain": 3.0}, lr=0.1, report={"noncomparative": ["gain"]})
    b = plain("b", {"gain": 1.0}, lr=0.001, extra=5, report={"noncomparative": ["gain"]})
    write(
        project / "docs" / "state.md", f"# 状態\n\nours 3.0 [run:{a.run_id}:gain]\n\nflat 1.0 [run:{b.run_id}:gain]\n"
    )
    assert any("axis" in i.message for i in state_issues())
    text = f"# 状態\n\naxis=lr\n\n## ours\n\n3.0 [run:{a.run_id}:gain]\n\n## flat\n\n1.0 [run:{b.run_id}:gain]\n"
    write(project / "docs" / "state.md", text)
    assert any("extra" in i.message for i in state_issues())
    c = plain("c", {"gain_x": 1.0}, lr=0.001, extra=5, report={"noncomparative": ["gain_x"]})
    write(project / "docs" / "state.md", f"# 状態\n\n3.0 [run:{a.run_id}:gain]\n\n1.0 [run:{c.run_id}:gain_x]\n")
    assert not state_issues()  # 別の行の違う指標は機械には比較と分からない（残る危険。同じ行なら test_u の警告）


def test_s_cross_run_axis_value_is_one_word(project):
    a = plain("a", {"t": 1.0}, preset="ours+fp64+lr0.1", report={"noncomparative": ["t"]})
    b = plain("b", {"t": 2.0}, preset="flat+fp16+lr0.001", report={"noncomparative": ["t"]})
    with pytest.raises(ValueError, match="1 語"):
        claims.add_claim(project, "a と b", [f"{a.run_id}:t", f"{b.run_id}:t"], axis="preset")


# ---- 4 回目のレビュー: 文書の並置は行ごとの警告（文の意味は機械に読めない。比較は台帳で強制する） ----
def state_l027(project):
    return [i for i in issues(project, "L027") if i.where.startswith("docs/state.md")]


def state(project, text):
    write(project / "docs" / "state.md", f"# 状態\n\n{text}\n")


def matched_run():
    with Run("m", {**cfg(), "report": {"noncomparative": ["snr_*"]}}) as m:
        m.log_metric("gain_db", 2.0)
        m.log_metric("snr_db", 12.0)
    return m


def test_u_document_lines_juxtaposing_values_are_warned(project):
    # 1: 設定の違う 2 run の、名前の違う非比較の指標を 1 行に並べる
    a = plain("a", {"gain_ours": 3.0}, lr=0.1, report={"noncomparative": ["gain_ours"]})
    b = plain("b", {"gain_flat": 1.0}, lr=0.001, extra=5, report={"noncomparative": ["gain_flat"]})
    state(project, f"ours 3.0 [run:{a.run_id}:gain_ours] は flat 1.0 [run:{b.run_id}:gain_flat] より良い")
    got = state_l027(project)
    assert got and all(i.severity == "warn" for i in got) and "台帳" in got[0].message
    # 2: matched な比較の run の値を、設定の違う別の run の値の隣に置く
    m = matched_run()
    o = plain("o", {"gain_db_x": 1.0}, lr=9, report={"noncomparative": ["gain_db_x"]})
    state(project, f"2.0 [run:{m.run_id}:gain_db] vs 1.0 [run:{o.run_id}:gain_db_x]")
    got = state_l027(project)
    assert got and all(i.severity == "warn" for i in got)
    # 3: 1 つの run の 2 つの非比較の値（台帳なら拒否される並置）。表の行も 1 行
    r = plain("noc", {"gain_ours": 3.0, "gain_flat": 1.0}, report={"noncomparative": ["gain_ours", "gain_flat"]})
    state(project, f"| ours | 3.0 [run:{r.run_id}:gain_ours] | flat | 1.0 [run:{r.run_id}:gain_flat] |")
    got = state_l027(project)
    assert got and all(i.severity == "warn" for i in got) and "gain_flat" in got[0].message
    # 同じ指標の run またぎは文書ごとの error のまま（行の警告も出る）
    c = plain("c", {"gain": 3.0}, lr=0.1, report={"noncomparative": ["gain"]})
    d = plain("d", {"gain": 1.0}, lr=0.001, extra=5, report={"noncomparative": ["gain"]})
    state(project, f"ours 3.0 [run:{c.run_id}:gain] > flat 1.0 [run:{d.run_id}:gain]")
    got = state_l027(project)
    assert any(i.severity == "error" for i in got) and any(i.severity == "warn" for i in got)
    # 1 つの値だけの行は出さない
    state(project, f"利得 2.0 [run:{m.run_id}:gain_db]\n\nSNR 12 [run:{m.run_id}:snr_db]")
    assert not state_l027(project)
    # 開発ログは行の警告を出さない
    state(project, "")
    devlog = project / "docs" / "devlog" / "2026-11-10.md"
    write(devlog, f"# x\n\n2.0 [run:{m.run_id}:gain_db] vs 1.0 [run:{o.run_id}:gain_db_x]\n")
    assert not [i for i in issues(project, "L027") if "devlog" in i.where and "台帳" in i.message]


def test_u_claim_id_exempts_the_line_only_when_its_evidence_covers_it(project):
    m = matched_run()
    line = f"利得 2.0 [run:{m.run_id}:gain_db]（SNR 12 [run:{m.run_id}:snr_db]）"
    state(project, line)
    assert state_l027(project) and all(i.severity == "warn" for i in state_l027(project))
    cid = claims.add_claim(project, "利得 2 dB（SNR 12 dB）", [f"{m.run_id}:gain_db", f"{m.run_id}:snr_db"])["id"]
    state(project, f"{cid}: {line}")
    assert not state_l027(project)  # 台帳を通した主張の ID がある行は出さない
    one = claims.add_claim(project, "利得 2 dB", [f"{m.run_id}:gain_db"])["id"]
    state(project, f"{one}: {line}")
    assert state_l027(project)  # 根拠が行の引用を覆わない主張の ID では消えない
    claims.retract_claim(project, cid, reason="test")
    state(project, f"{cid}: {line}")
    assert state_l027(project)  # 撤回した主張の ID では消えない


def test_t_residual_risks_are_documented():
    from pathlib import Path

    doc = (Path(__file__).resolve().parents[3] / "docs" / "harness.md").read_text(encoding="utf-8")
    assert "比べる語の一覧は経験則" in doc and "entry が arm_conditions を無視しうる" in doc
    assert "文書の並置は警告だけ" in doc
