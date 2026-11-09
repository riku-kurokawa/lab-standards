"""比較は 1 軸だけを変える（ceteris paribus）: 腕の条件の照合、比較対象の掃引、L027、claim add、名指しの退避と L032."""

import json

import pytest

from labkit import Run, claims
from labkit.check import run_check
from labkit.cli import main
from labkit.compare import Arm, ConditionMismatch, declare
from labkit.runs import list_runs

BASE = {"dof": "PA", "quant_bits": 8, "eval_set": "test-v1", "tuning_configs": 12, "scoring": "rmse"}


def arms(**override_b):
    return [
        Arm("ours", {**BASE, "method": "ours"}),
        Arm("flat", {**BASE, "method": "flat", **override_b}),
    ]


def issues(p, code):
    return [i for i in run_check(root=p)[0] if i.code == code]


def write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


def test_matched_arms_pass_and_write_comparison(project):
    d = project / "runs" / "x"
    d.mkdir()
    rec = declare(d, arms(), ["method"], keys=["gain_db"])
    on_disk = json.loads((d / "comparison.json").read_text(encoding="utf-8"))
    assert rec["matched"] and on_disk["matched"] and on_disk["keys"] == ["gain_db"]
    fps = {a["fingerprint"] for a in on_disk["arms"]}
    assert len(fps) == 1 and len(next(iter(fps))) == 64  # vary 以外が同一なら指紋も同一
    declare(d, arms(quant_bits=8.0 + 1e-12), ["method"], rel_tol=1e-9)  # 許容差は明示したときだけ


def test_differing_non_varied_key_fails_with_diff(project):
    d = project / "runs" / "x"
    d.mkdir()
    with pytest.raises(ConditionMismatch, match=r"'dof'.*ours=\"PA\" / flat=\"P\""):
        declare(d, arms(dof="P"), ["method"])
    with pytest.raises(ConditionMismatch, match="quant_bits"):
        declare(d, arms(quant_bits=8.0 + 1e-12), ["method"])  # 浮動小数は既定で厳密
    rec = json.loads((d / "comparison.json").read_text(encoding="utf-8"))
    assert rec["matched"] is False and rec["diff"]
    # 目的を受け取れない腕は対象外（照合から外し、負けにしない）
    rec = declare(d, [*arms(), Arm("gs-pat", {"method": "gs"}, not_applicable="null 行を受け取れない")], ["method"])
    assert rec["not_applicable"] == [{"name": "gs-pat", "reason": "null 行を受け取れない"}]


def test_missing_key_and_required_fail(project):
    d = project / "runs" / "x"
    d.mkdir()
    a = arms()
    del a[1].conditions["eval_set"]
    with pytest.raises(ConditionMismatch, match="eval_set.*鍵の集合"):
        declare(d, a, ["method"])
    write(project / "lab.toml", '[lab]\nproject = "t"\n[compare]\nrequired = ["dof", "field_model"]\n')
    with pytest.raises(ConditionMismatch, match="field_model"):
        declare(d, arms(), ["method"])
    with pytest.raises(ConditionMismatch, match="vary"):
        declare(d, arms(), [])


def test_comparator_not_best_fails(project):
    d = project / "runs" / "x"
    d.mkdir()
    a = [Arm("ours", {**BASE, "method": "ours", "height_mm": None}), Arm("flat", {**BASE, "method": "flat"})]
    a[1].conditions["height_mm"] = 10
    a[0].conditions["height_mm"] = 10
    good = {"flat": {"height_mm": [10, 20, 30], "chosen": 20, "scores": [0.1, 0.5, 0.3]}}
    with pytest.raises(ConditionMismatch, match="height_mm=10 が chosen=20"):  # 腕の条件と chosen が違う
        declare(d, a, ["method"], good)
    a[0].conditions["height_mm"] = a[1].conditions["height_mm"] = 20
    declare(d, a, ["method"], good)
    bad = {"flat": {"height_mm": [10, 20, 30], "chosen": 20, "scores": [0.1, 0.5, 0.9]}}
    with pytest.raises(ConditionMismatch, match="最良"):
        declare(d, a, ["method"], bad)
    declare(d, a, ["method"], {"flat": {**bad["flat"], "scores": [0.9, 0.1, 0.5], "minimize": True}})


def test_run_compare_check_rule_and_claim_add(git_project):
    p = git_project
    cfg = {"seed": 0, "compare": {"vary": ["method"], "keys": ["gain_db"]}}
    with Run("ok", dict(cfg)) as ok:
        ok.compare(arms())
        ok.log_metric("gain_db", 3.2)
    with pytest.raises(ConditionMismatch):
        with Run("bad", dict(cfg)) as bad:
            bad.compare(arms(dof="P"))
    with Run("forgot", dict(cfg)) as forgot:  # [compare] を宣言して run.compare を呼ばない → failed
        forgot.log_metric("gain_db", 9.9)
    with Run("plain", {"seed": 0}) as plain:  # 比較を宣言しない run の比較の指標
        plain.log_metric("gain_db", 5.0)
    status = {m["name"]: m["status"] for m in list_runs(p)}
    assert status == {"ok": "finished", "bad": "failed", "forgot": "failed", "plain": "finished"}
    assert "run.compare" in json.loads((forgot.dir / "meta.json").read_text(encoding="utf-8"))["error"]

    c = claims.add_claim(p, "利得は 3.2 dB", [f"{ok.run_id}:gain_db:dB:1"])
    assert c["id"] == "C001"
    with pytest.raises(ValueError, match="comparison.json が無い"):
        claims.add_claim(p, "利得は 5 dB", [f"{plain.run_id}:gain_db:dB:1"])

    write(
        p / "docs" / "papers" / "draft.md",
        f"# 草稿\n\n5.0 dB [run:{plain.run_id}:gain_db]\n3.2 dB [run:{ok.run_id}:gain_db]\n",
    )
    got = issues(p, "L027")
    assert [i.where for i in got] == ["docs/papers/draft.md:3"] and got[0].severity == "error"
    # lab.toml で比較の指標と宣言した鍵は、比較を宣言しなかった run から引用できない
    with Run("other", {"seed": 0}) as other:
        other.log_metric("speedup", 2.0)
    write(p / "docs" / "papers" / "speed.md", f"2.0 x [run:{other.run_id}:speedup]\n")
    assert not [i for i in issues(p, "L027") if "speed.md" in i.where]
    write(p / "lab.toml", '[lab]\nproject = "t"\n[check]\nmode = "strict"\n[compare]\nkeys = ["speedup"]\n')
    assert [i.where for i in issues(p, "L027") if "speed.md" in i.where] == ["docs/papers/speed.md:1"]


def test_run_level_l027_for_unmatched_comparison(project):
    with Run("x", {"seed": 0}) as run:
        run.log_metric("a", 1.0)
    d = run.dir
    from labkit.runs import freeze_run

    freeze_run(d, writable=True)
    write(d / "comparison.json", json.dumps({"matched": False, "keys": ["a"], "diff": ["flat: 条件 'dof' が違う"]}))
    freeze_run(d)
    got = issues(project, "L027")
    assert len(got) == 1 and "dof" in got[0].message
    assert main(["runs", "archive", run.run_id, "--reason", "条件不一致"]) == 0
    assert not issues(project, "L027")  # 退避した run は対象外


def test_archive_by_explicit_ids_and_l032_error(git_project, capsys):
    p = git_project
    runs = []
    for name in ("a", "b"):
        with Run(name, {"seed": 0}) as r:
            r.log_metric("e", 0.5)
        runs.append(r)
    write(p / "docs" / "papers" / "draft.md", f"0.5 [run:{runs[0].run_id}:e]\n言及だけ {runs[1].run_id}\n")
    with pytest.raises(SystemExit, match="理由"):
        main(["runs", "archive", runs[0].run_id, runs[1].run_id])
    assert main(["runs", "archive", runs[0].run_id, runs[1].run_id, "--reason", "条件不一致: dof が違う"]) == 0
    assert not list_runs(p) and all(
        m["archived"]["reason"] == "条件不一致: dof が違う" for m in list_runs(p, include_archived=True)
    )
    assert all(r.dir.is_dir() for r in runs)  # 削除はしない
    got = issues(p, "L032")
    errors = [i for i in got if i.severity == "error"]
    assert [i.where for i in errors] == ["docs/papers/draft.md:1"] and "退避済み" in errors[0].message
    assert any(i.severity == "warn" and "退避済み" in i.message for i in got)  # ID だけの言及は警告
    with pytest.raises(SystemExit, match="1 つだけ"):
        main(["runs", "show", runs[0].run_id, runs[1].run_id])
