"""Python と Julia の対称性（HDF5 の軸順・サイドカー・meta.json）を実ファイルで確かめる: Julia が書き、Python が読む.

julia が PATH に無ければ skip（CI では julia ジョブで実行する）。
"""

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from labkit.check import run_check
from labkit.io import load
from labkit.runs import list_runs

JL = Path(__file__).resolve().parents[3] / "labkit" / "julia" / "LabKit"  # parents[3] = リポジトリのルート
pytestmark = pytest.mark.skipif(shutil.which("julia") is None, reason="julia not on PATH")

SCRIPT = """
using LabKit, DataFrames
Run("jl", Dict{String,Any}()) do run
    save(runpath(run, "a.h5"), Dict("x" => reshape(1.0:6.0, 2, 3)); attrs=Dict("fs" => 1.0))
    log_metric(run, "m", 1.5)
    log_metric(run, "n", 2.0)
end
save(datapath("processed", "t.parquet"), DataFrame(m=["a", "b"], v=[1.0, 2.0]))
"""


def test_julia_writes_python_reads(project):
    subprocess.run(["julia", f"--project={JL}", "-e", SCRIPT], check=True, cwd=project, timeout=600)
    run = next(project.glob("runs/*"))
    x = load(run / "a.h5", verify=True)["x"]
    # Julia の size (2, 3) は Python でも shape (2, 3)。reshape は列優先なので order="F" が期待値
    assert x.shape == (2, 3) and np.array_equal(x, np.arange(1.0, 7.0).reshape(2, 3, order="F"))
    assert load(project / "data/processed/t.parquet", verify=True)["v"].tolist() == [1.0, 2.0]
    assert not {i.code for i in run_check()[0]} & {"L020", "L022"}  # meta.json とサイドカーがスキーマどおり
    assert list_runs()[0]["language"] == "julia"
    metrics = json.loads((run / "metrics.json").read_text())
    assert isinstance(metrics["n"], float) and isinstance(metrics["m"], float)  # Julia の 2.0 は 2 ではなく 2.0
    assert isinstance(json.loads((run / "meta.json").read_text())["duration_s"], float)


def test_directory_hash_matches_julia(tmp_path):
    """ディレクトリ入力の sha256（相対パス順に連結）は OS と実装に依らず同じ。並び順の罠（a-b/ と a/、大文字）も含める."""
    from labkit._util import sha256_tree

    d = tmp_path / "tree"
    for rel, content in [("sub/b.bin", b"b"), ("a-b/x.bin", b"x"), ("a/y.bin", b"y"), ("B.bin", b"B")]:
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_bytes(content)
    jl = subprocess.run(
        ["julia", f"--project={JL}", "-e", "using LabKit; print(LabKit.sha256_tree(ARGS[1]))", str(d)],
        check=True,
        capture_output=True,
        text=True,
        timeout=600,
    ).stdout.strip()
    assert sha256_tree(d) == jl


def test_manifest_has_no_backslash(project):
    from labkit.rawdata import freeze, verify

    (project / "data" / "raw" / "sub").mkdir()
    (project / "data" / "raw" / "sub" / "r.bin").write_bytes(b"x")
    freeze(progress=lambda *_: None)
    text = (project / "data" / "raw" / "MANIFEST.sha256").read_text(encoding="utf-8")
    assert "sub/r.bin" in text and "\\" not in text
    assert verify(full=True) == []
