"""設定・run・check・生データ・文献（h5py / pyarrow が無くても動く部分）."""

import json
import os
import stat

import pytest

from labkit import Run, add_input, load_config, log_message, log_metric, runpath
from labkit.check import run_check
from labkit.config import load_lab
from labkit.literature import add_entry, make_citekey, parse_bib
from labkit.runs import list_runs, mark_run

from .conftest import git

BIB = """@article{whatever,
  author = {M{\\"u}ller, Anna and Tanaka, Taro},
  title = {A {Fast} Method for Denoising},
  journal = {J. Signal Proc.},
  year = {2023},
  doi = {10.1000/xyz123}
}"""


def codes(project, **kw) -> set[str]:
    return {i.code for i in run_check(root=project, **kw)[0]}


def test_config_extends_and_overrides(project):
    (project / "configs" / "base.toml").write_text(
        "seed = 0\n[filter]\ncutoff = 10\norder = 4\n", encoding="utf-8", newline="\n"
    )
    (project / "configs" / "exp.toml").write_text(
        'extends = "base.toml"\n[filter]\ncutoff = 50\n', encoding="utf-8", newline="\n"
    )
    cfg = load_config(project / "configs" / "exp.toml", ["filter.order=8", "name=abc"])
    assert cfg["filter"] == {"cutoff": 50, "order": 8} and cfg["seed"] == 0 and cfg["name"] == "abc"
    assert len(cfg["_files"]) == 2


def test_run_lifecycle_and_freeze(git_project):
    project = git_project
    (project / "configs" / "e.toml").write_text("a = 1\nseed = 3\n", encoding="utf-8", newline="\n")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "config")
    cfg = load_config(project / "configs" / "e.toml")
    with Run("My Exp", cfg) as run:
        log_metric(run, "loss", 1.0, step=0)
        log_metric(run, "loss", 0.5, step=1)
        runpath(run, "note.txt").write_text("x", encoding="utf-8", newline="\n")
        (project / "data" / "raw" / "in.bin").write_bytes(b"abc")
        add_input(run, project / "data" / "raw" / "in.bin")
        log_message(run, "hello")
    meta = json.loads((run.dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "finished" and meta["seed"] == 3 and meta["git"]["dirty"] is False
    assert meta["env"]["packages"]["numpy"] and "os" in meta["env"] and meta["pid"] == os.getpid()
    assert meta["inputs"][0]["sha256_source"] == "computed"
    assert json.loads((run.dir / "metrics.json").read_text(encoding="utf-8")) == {"loss": 0.5}
    outs = {o["path"]: o for o in meta["outputs"]}
    assert {"note.txt", "metrics.jsonl", "config.json", "config/e.toml"} <= set(outs) and len(
        outs["note.txt"]["sha256"]
    ) == 64
    assert not (run.dir / "note.txt").stat().st_mode & stat.S_IWUSR and os.access(run.dir / "figures", os.W_OK)
    assert not (run.dir / "dirty.patch").exists()
    assert not [i for i in run_check(root=project)[0] if i.code.startswith("L02")]


def test_dirty_run_records_patch_and_untracked_counts(git_project):
    (git_project / "scripts" / "new.py").write_text("x = 1\n", encoding="utf-8", newline="\n")  # 未追跡
    with Run("d", {"seed": 0}) as run:
        pass
    meta = json.loads((run.dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["git"]["dirty"] is True
    assert "scripts/new.py" in (run.dir / "dirty.patch").read_text(encoding="utf-8")


def test_run_failure_and_mark(project):
    with pytest.raises(RuntimeError):
        with Run("boom") as run:
            raise RuntimeError("bad")
    meta = json.loads((run.dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "failed" and "bad" in meta["error"]
    # 異常終了（__exit__ が走らない）を模す: running のまま残った run を mark する
    r = Run("stuck", {"seed": 1})
    r.__enter__()
    r.log_metric("acc", 0.9, step=0)
    from labkit.runs import _current

    _current.reset(r._token)
    assert "L021" in {i.code for i in run_check(root=project)[0]}
    m = mark_run(r.run_id, "failed", "OOM")
    assert m["status"] == "failed" and json.loads((r.dir / "metrics.json").read_text(encoding="utf-8")) == {"acc": 0.9}
    assert "L021" not in codes(project)
    with pytest.raises(ValueError):
        mark_run(r.run_id, "failed")
    assert len(list_runs(project)) == 2


def test_run_killed_during_start_leaves_meta_not_shell(project, monkeypatch):
    """入力の hash や環境の取得の最中に止められても、meta.json の無い殻（L020）を残さない."""
    import labkit.runs as runs_mod

    def killed(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(runs_mod, "env_info", killed)
    r = Run("slow", {"seed": 0})
    with pytest.raises(KeyboardInterrupt):
        r.__enter__()
    meta = json.loads((r.dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "running" and meta["run_id"] == r.run_id
    assert "L020" not in codes(project) and "L021" in codes(project)
    assert mark_run(r.run_id, "interrupted", "killed")["status"] == "interrupted"
    assert not {"L020", "L021"} & codes(project)


def test_mark_shell_without_meta(project):
    """古い版が残した殻（config だけで meta.json が無い）を、削除せずに記録として片付ける."""
    d = project / "runs" / "20261103-061807_atlas-table_b5fbf37_deb6"
    (d / "config").mkdir(parents=True)
    (d / "config.json").write_text("{}", encoding="utf-8")
    assert "L020" in codes(project)
    m = mark_run(d.name, "interrupted", "開始直後に停止")
    assert m["status"] == "interrupted" and m["name"] == "atlas-table" and "開始直後に停止" in m["error"]
    assert {o["path"] for o in m["outputs"]} == {"config.json", "metrics.json"}
    assert not {"L020", "L021"} & codes(project)
    with pytest.raises(ValueError):
        mark_run(d.name, "failed")


def test_lineage_from_sidecar(project):
    pytest.importorskip("h5py")
    import numpy as np

    from labkit import datapath, save

    with Run("a", {"seed": 0}) as a:
        save(datapath("processed", "x.h5"), {"x": np.ones(3)})
    with Run("b", {"seed": 0}, inputs=[datapath("processed", "x.h5")]) as b:
        pass
    meta = json.loads((b.dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["inputs"][0]["sha256_source"] == "sidecar" and meta["inputs"][0]["run_id"] == a.run_id


def test_check_detects_violations(project):
    (project / "stray.txt").write_text("x", encoding="utf-8", newline="\n")
    (project / "docs" / "notes.md").write_text(
        "a\n<<<<<<< HEAD\nb\n=======\nc\n>>>>>>> template\n", encoding="utf-8", newline="\n"
    )
    (project / "src" / "a.py").write_text(
        "import matplotlib.pyplot as plt\nimport pickle\nP='/home/me/x'\nQ=r'D:\\data\\x'\nR='C:/Users/me'\nU='https://x.org/a'\n"
        "np.savez('o.npz', a=1)\n",
        encoding="utf-8",
        newline="\n",
    )
    (project / "src" / "b.py").write_text("from scripts import run\n", encoding="utf-8", newline="\n")
    (project / "jobs").mkdir()
    (project / "jobs" / "j.sh").write_text("cd /mnt/d/src/x\n", encoding="utf-8", newline="\n")
    (project / "scripts" / "fig.png").write_bytes(b"x")
    (project / "docs" / "devlog" / "today.md").write_text("x", encoding="utf-8", newline="\n")
    (project / "data" / "raw" / "r.bin").write_bytes(b"123")
    (project / "data" / "processed" / "sub").mkdir()
    (project / "data" / "processed" / "sub" / "x.npy").write_bytes(b"0")
    issues = run_check(root=project)[0]
    got = {i.code for i in issues}
    assert {"L001", "L002", "L004", "L010", "L011", "L012", "L013", "L014", "L016", "L022", "L030"} <= got
    l012 = sorted(i.where for i in issues if i.code == "L012")
    assert l012 == ["jobs/j.sh:1", "src/a.py:3", "src/a.py:4", "src/a.py:5"], l012  # https:// は拾わない
    assert [i.where for i in issues if i.code == "L022"] == ["data/processed/sub/x.npy"]
    assert [i.where for i in issues if i.code == "L004"] == ["docs/notes.md:2"]
    # --claims は成果物の検証だけ
    assert {"L010", "L001"}.isdisjoint(codes(project, claims=True)) and {"L002", "L022", "L030"} <= codes(
        project, claims=True
    )


def test_devlog_empty_sections_and_bare_results(project):
    from labkit.devlog import update

    p = update(project, "2026-11-02")
    assert "<!-- labkit:auto -->" in p.read_text(encoding="utf-8")
    issues = [i for i in run_check(root=project)[0] if i.code == "L030"]
    assert issues and "目的" in issues[0].message
    text = p.read_text(encoding="utf-8")
    text = text.replace("## 目的\n", "## 目的\n\n速度を測る\n").replace("## 判断と理由\n", "## 判断と理由\n\n理由\n")
    text = text.replace("## 未解決・次の作業\n", "## 未解決・次の作業\n\n無し\n")
    text = text.replace("## 結果・観察\n", "## 結果・観察\n\n12 件中 3 件が収束。誤差は 1.5e-3 だった\n")
    p.write_text(text, encoding="utf-8", newline="\n")
    issues = run_check(root=project)[0]
    assert "L030" not in {i.code for i in issues}
    l034 = [i for i in issues if i.code == "L034"]
    assert len(l034) == 1 and l034[0].severity == "warn"  # 整数は対象外、小数だけ


def test_citation_check(project):
    with Run("c", {"seed": 0}) as run:
        run.log_metric("snr_db", 12.345)
    from labkit.check import cite

    good = cite(run.run_id, "snr_db", digits=1, unit="dB")
    assert good == f"12.3 dB [run:{run.run_id}:snr_db]"
    p = project / "docs" / "devlog" / "2026-11-02.md"
    p.write_text(
        f"## 目的\nx\n## 結果・観察\n{good} と 99.9 dB [run:{run.run_id}:snr_db] と 5 [run:{run.run_id}:nokey]\n"
        "## 判断と理由\ny\n## 未解決・次の作業\nz\n見つからない 20260101-000000_x_abcdef0_0000\n",
        encoding="utf-8",
        newline="\n",
    )
    issues = run_check(root=project)[0]
    msgs = [i.message for i in issues if i.code == "L033"]
    assert len(msgs) == 2 and any("99.9" in m for m in msgs) and any("nokey" in m for m in msgs)
    assert any(i.code == "L032" and "20260101" in i.message for i in issues)
    assert not [i for i in issues if i.code == "L034"]


def test_raw_freeze_verify(project):
    from labkit.rawdata import freeze, verify

    (project / "data" / "raw" / "r.bin").write_bytes(b"123")
    freeze(progress=lambda *_: None)
    assert verify(full=True) == []
    os.chmod(project / "data" / "raw" / "r.bin", 0o644)
    (project / "data" / "raw" / "r.bin").write_bytes(b"1234")
    assert any(code == "L002" for code, *_ in verify())


def test_raw_manifest_ignores_vcs_metadata(project):
    from labkit.rawdata import freeze, read_manifest, verify

    raw = project / "data" / "raw"
    (raw / "repo" / ".git").mkdir(parents=True)
    (raw / "repo" / ".git" / "index").write_bytes(b"idx")
    (raw / "repo" / "a.csv").write_text("1\n", encoding="utf-8", newline="\n")
    freeze(progress=lambda *_: None)
    assert set(read_manifest(raw)) == {"repo/a.csv"}
    (raw / "repo" / ".git" / "index").write_bytes(b"rewritten by git")
    assert verify(full=True) == []


def test_literature(project):
    fields = next(iter(parse_bib(BIB).values()))
    assert make_citekey(fields) == "muller2023fast"
    lab = load_lab(project)
    key, note = add_entry(project, lab, BIB, tags=["denoising"])
    assert key == "muller2023fast" and note.exists()
    with pytest.raises(ValueError):
        add_entry(project, lab, BIB.replace("whatever", "w2"), key="other2023x")  # 同じ DOI
    s = project / "literature" / "surveys" / "2026-10-30_test.md"
    s.write_text(
        '---\ndate: 2026-10-30\nquestion: "q"\nsearch: {}\n---\n見た [@muller2023fast] と [@ghost2020x]\n',
        encoding="utf-8",
        newline="\n",
    )
    assert [i.code for i in run_check(root=project)[0] if i.code.startswith("L04")] == ["L046"]


def test_shared_pdf_library_outside_project(project, tmp_path):
    lib = tmp_path.parent / f"{tmp_path.name}-lib"
    lib.mkdir()
    (lib / "someone2020else.pdf").write_bytes(b"%PDF")
    (project / "lab.toml").write_text(
        f'[lab]\nproject = "t"\n[literature]\npdf_dir = "{lib.as_posix()}"\n', encoding="utf-8", newline="\n"
    )
    assert "L044" not in codes(project)
