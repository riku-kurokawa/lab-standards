"""h5py / pyarrow が無くても動く部分のテスト."""

import json
import os
import stat

import pytest

from labkit import Run, add_input, load_config, log_message, log_metric, runpath
from labkit.check import run_check
from labkit.config import load_lab
from labkit.literature import add_entry, make_citekey, parse_bib

BIB = """@article{whatever,
  author = {M{\\"u}ller, Anna and Tanaka, Taro},
  title = {A {Fast} Method for Denoising},
  journal = {J. Signal Proc.},
  year = {2023},
  doi = {10.1000/xyz123}
}"""


def test_config_extends_and_overrides(project):
    (project / "configs" / "base.toml").write_text("seed = 0\n[filter]\ncutoff = 10\norder = 4\n")
    (project / "configs" / "exp.toml").write_text('extends = "base.toml"\n[filter]\ncutoff = 50\n')
    cfg = load_config(project / "configs" / "exp.toml", ["filter.order=8", "name=abc"])
    assert cfg["filter"] == {"cutoff": 50, "order": 8}
    assert cfg["seed"] == 0 and cfg["name"] == "abc"
    assert len(cfg["_files"]) == 2


def test_run_lifecycle_and_freeze(project):
    (project / "configs" / "e.toml").write_text("a = 1\n")
    cfg = load_config(project / "configs" / "e.toml")
    with Run("My Exp", cfg) as run:
        log_metric(run, "loss", 1.0, step=0)
        log_metric(run, "loss", 0.5, step=1)
        runpath(run, "note.txt").write_text("x")
        (project / "data" / "raw" / "in.bin").write_bytes(b"abc")
        add_input(run, project / "data" / "raw" / "in.bin")
        log_message(run, "hello")
    meta = json.loads((run.dir / "meta.json").read_text())
    assert meta["status"] == "finished"
    assert "hello" in (run.dir / "log.txt").read_text(encoding="utf-8")
    assert len(meta["inputs"]) == 1 and meta["inputs"][0]["sha256_source"] == "computed"
    assert meta["language"] == "python"
    assert json.loads((run.dir / "metrics.json").read_text()) == {"loss": 0.5}
    assert {o["path"] for o in meta["outputs"]} >= {"note.txt", "metrics.jsonl", "config.json"}
    assert not (run.dir / "note.txt").stat().st_mode & stat.S_IWUSR  # 読み取り専用
    assert os.access(run.dir / "figures", os.W_OK)  # figures は書ける
    issues, _ = run_check()
    assert not [i for i in issues if i.code.startswith("L02")], issues


def test_run_failure_recorded(project):
    with pytest.raises(RuntimeError):
        with Run("boom") as run:
            raise RuntimeError("bad")
    meta = json.loads((run.dir / "meta.json").read_text())
    assert meta["status"] == "failed" and "bad" in meta["error"]


def test_check_detects_violations(project):
    (project / "stray.txt").write_text("x")
    (project / "src" / "a.py").write_text("import matplotlib.pyplot as plt\nimport pickle\nP='/home/me/x'\n")
    (project / "src" / "b.py").write_text("from scripts import run\n")
    (project / "scripts" / "c.jl").write_text("using CairoMakie\n")
    (project / "scripts" / "fig.png").write_bytes(b"x")
    (project / "docs" / "devlog" / "today.md").write_text("x")
    (project / "data" / "raw" / "r.bin").write_bytes(b"123")
    codes = {i.code for i in run_check()[0]}
    assert {"L001", "L002", "L010", "L011", "L012", "L013", "L014", "L030"} <= codes


def test_raw_freeze_verify(project):
    from labkit.rawdata import freeze, verify

    (project / "data" / "raw" / "r.bin").write_bytes(b"123")
    freeze(progress=lambda *_: None)
    assert verify(full=True) == []
    os.chmod(project / "data" / "raw" / "r.bin", 0o644)
    (project / "data" / "raw" / "r.bin").write_bytes(b"1234")
    assert any(code == "L002" for code, *_ in verify())


def test_literature(project):
    fields = next(iter(parse_bib(BIB).values()))
    assert make_citekey(fields) == "muller2023fast"
    lab = load_lab(project)
    key, note = add_entry(project, lab, BIB, tags=["denoising"])
    assert key == "muller2023fast" and note.exists()
    with pytest.raises(ValueError):
        add_entry(project, lab, BIB.replace("whatever", "w2"), key="other2023x")  # 同じ DOI
    with pytest.raises(ValueError):
        add_entry(project, lab, BIB.replace("10.1000/xyz123", "10.1/2"), key="b2023b", tags=["nope"])
    s = project / "literature" / "surveys" / "2026-10-30_test.md"
    s.write_text('---\ndate: 2026-10-30\nquestion: "q"\nsearch: {}\n---\n見た [@muller2023fast] と [@ghost2020x]\n')
    codes = [i for i in run_check()[0] if i.code.startswith("L04")]
    assert [i.code for i in codes] == ["L046"], codes
    assert all("\\" not in i.where for i in codes), codes  # 位置は literature/surveys/... の / 区切り


def test_check_paths_are_posix_and_ok_dirs_apply(project):
    """違反の位置は OS に依らず / 区切り。figure_ok_dirs / data_ok_dirs の除外が Windows でも効く（以前は \\ 比較で L014 誤検出）."""
    (project / "docs" / "assets").mkdir(parents=True)
    (project / "docs" / "assets" / "diagram.png").write_bytes(b"x")
    (project / "scripts" / "stray.png").write_bytes(b"x")
    issues, _ = run_check()
    assert all("\\" not in i.where for i in issues), [i.where for i in issues]
    l014 = [i.where for i in issues if i.code == "L014"]
    assert l014 == ["scripts/stray.png"]


def test_legacy_windows_manifest_lines_verify(project):
    """旧版が Windows で書いた `sub\\r.bin` 形式の MANIFEST 行も検証できる."""
    import hashlib

    from labkit.rawdata import verify

    raw = project / "data" / "raw"
    (raw / "sub").mkdir()
    (raw / "sub" / "r.bin").write_bytes(b"x")
    digest = hashlib.sha256(b"x").hexdigest()
    (raw / "MANIFEST.sha256").write_text(f"# legacy\n{digest}  1  sub\\r.bin\n", encoding="utf-8")
    assert [i for i in verify(full=True) if i[0] == "L002"] == []
