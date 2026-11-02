"""HDF5 / Parquet の保存・読込・図テンプレート（h5py, pyarrow が必要）."""

import json

import numpy as np
import pandas as pd
import pytest

h5py = pytest.importorskip("h5py")
pytest.importorskip("pyarrow")

from labkit.check import run_check  # noqa: E402
from labkit.io import ReadOnlyAreaError  # noqa: E402

from labkit import Run, datapath, load, load_meta, runpath, save, writer  # noqa: E402


def test_h5_roundtrip_and_sidecar(project):
    x = np.arange(12.0).reshape(3, 4)
    mask = np.array([True, False, True])
    p = save(
        datapath("processed", "a.h5"),
        {"x": x, "grp": {"y": np.ones(3)}, "label": "ok", "mask": mask},
        attrs={"fs": 1000.0},
    )
    d = load(p, verify=True)
    assert np.array_equal(d["x"], x) and d["grp"]["y"].shape == (3,) and d["label"] == "ok"
    assert d["mask"].dtype == np.bool_ and np.array_equal(d["mask"], mask)
    assert load_meta(p)["format"] == "hdf5" and load_meta(p)["attrs"]["fs"] == 1000.0
    with pytest.raises(FileExistsError):
        save(p, {"x": x})
    save(p, {"x": x * 2}, overwrite=True)
    (project / "data" / "processed" / "sub").mkdir()
    save(datapath("processed", "sub", "b.parquet"), pd.DataFrame({"v": [1.0]}))
    assert not [i for i in run_check(root=project)[0] if i.code == "L022"]


def test_parquet_roundtrip(project):
    df = pd.DataFrame({"m": ["a", "a", "b"], "v": [1.0, 2.0, 3.0]})
    assert load(save(datapath("processed", "t.parquet"), df), verify=True).equals(df)


def test_cache_stage_needs_no_sidecar(project):
    (project / "data" / "cache").mkdir()
    (project / "data" / "cache" / "x.npy").write_bytes(b"0")
    assert "L022" not in {i.code for i in run_check(root=project)[0]}


def test_load_missing_file_names_the_file(project):
    with pytest.raises(FileNotFoundError, match=r"nope\.h5 がありません"):
        load(datapath("processed", "nope.h5"), verify=True)


def test_raw_is_readonly(project):
    with pytest.raises(ReadOnlyAreaError):
        save(datapath("raw", "x.h5"), {"x": np.ones(2)})


def test_writer_and_run_outputs(project):
    with Run("w") as run:
        with writer(runpath(run, "big.h5")) as tmp:
            with h5py.File(tmp, "w") as f:
                f.create_dataset("x", data=np.zeros((10, 10)))
    meta = json.loads((run.dir / "meta.json").read_text(encoding="utf-8"))
    assert (
        any(o["path"] == "big.h5" and o["sha256"] for o in meta["outputs"]) and (run.dir / "big.h5.meta.json").exists()
    )


def test_figure_templates(project):
    from labkit.viz import REGISTRY, render

    t = np.linspace(0, 1, 1000)
    with Run("fig") as run:
        save(runpath(run, "s.h5"), {"t": t, "x": np.sin(2 * np.pi * 5 * t), "sd": 0.1 + 0 * t})
        for i in range(5):
            run.log_metric("loss", 1 / (i + 1), step=i)
        xg, yg = np.arange(4.0), np.arange(6.0)
        u = xg[:, None] * 10 + yg[None, :]
        save(runpath(run, "field.h5"), {"u": u, "uT": u.T, "xgrid": xg, "ygrid": yg})
        save(
            runpath(run, "res.parquet"),
            pd.DataFrame(
                {
                    "method": ["a", "a", "b", "b"],
                    "n": [10, 10, 100, 100],
                    "rmse": [1.0, 1.2, 2.0, 2.1],
                    "dev": ["c", "g", "c", "g"],
                }
            ),
        )
    specs = {
        "ts.toml": 'template = "timeseries"\n[data]\nfile = "s.h5"\nx = "t"\ny = ["x"]\n',
        "band.toml": 'template = "band"\n[data]\nfile = "s.h5"\nx = "t"\ny = "x"\nerr = "sd"\n',
        "lc.toml": 'template = "learning_curve"\n[data]\nmetrics = ["loss"]\n',
        "psd.toml": 'template = "psd"\n[data]\nfile = "s.h5"\nsignal = "x"\nfs = 1000.0\nnperseg = 256\n',
        "sp.toml": 'template = "spectrogram"\n[data]\nfile = "s.h5"\nsignal = "x"\nfs = 1000.0\nnperseg = 64\n',
        "hm.toml": 'template = "heatmap"\n[data]\nfile = "field.h5"\nz = "u"\nx = "xgrid"\ny = "ygrid"\n',
        "hist.toml": 'template = "histogram"\n[data]\nfile = "s.h5"\nvalues = ["x"]\nbins = 20\n',
        "sc.toml": 'template = "scatter"\n[data]\nfile = "s.h5"\nx = "t"\ny = "x"\n',
        "eb.toml": 'template = "errorbar"\n[data]\nfile = "res.parquet"\nx = "method"\ny = "rmse"\nhue = "dev"\n',
        "ebn.toml": 'template = "errorbar"\n[data]\nfile = "res.parquet"\nx = "n"\ny = "rmse"\nxmode = "numeric"\n[options]\nlogx = true\n',
        "bar.toml": 'template = "bar"\n[data]\nfile = "res.parquet"\nx = "method"\ny = "rmse"\nhue = "dev"\nerr = "sd"\n',
        "pan.toml": (
            'template = "panels"\nlayout = [1, 2]\nsize = "double"\n'
            '[[panel]]\ntemplate = "timeseries"\ndata = {file = "s.h5", x = "t", y = "x"}\nlabels = {title = "signal"}\n'
            '[[panel]]\ntemplate = "psd"\ndata = {file = "s.h5", signal = "x", fs = 1000.0}\n'
        ),
    }
    assert {s.split(".")[0] for s in specs} >= {"ts", "band", "bar", "pan"} and len(REGISTRY) == 11
    for name, text in specs.items():
        (project / "figspecs" / name).write_text(text, encoding="utf-8", newline="\n")
        assert all(p.exists() for p in render(project / "figspecs" / name, run_id=run.run_id)), name
    fm = json.loads((run.dir / "figures" / "pan.figmeta.json").read_text(encoding="utf-8"))
    assert fm["template"] == "panels" and "git" in fm and len(fm["data"]) == 1
    for text, pat in (
        (
            'template = "heatmap"\n[data]\nfile = "field.h5"\nz = "uT"\nx = "xgrid"\ny = "ygrid"\n',
            r"len\(x\), len\(y\)",
        ),
        ('template = "timeseries"\n[data]\nfile = "s.h5"\nx = "t"\ny = "xx"\n', r"typo\.toml: 'xx（ある名前"),
        (
            'template = "errorbar"\n[data]\nfile = "res.parquet"\nx = "methodd"\ny = "rmse"\n',
            r"typo\.toml: 'methodd' がありません",
        ),
        ('template = "psd"\n[data]\nfile = "s.h5"\nfs = 1000.0\n', r"'signal' がありません"),
        ('template = "panels"\n[[panel]]\ntemplate = "panels"\n', r"入れ子"),
    ):
        (project / "figspecs" / "typo.toml").write_text(text, encoding="utf-8", newline="\n")
        with pytest.raises(ValueError, match=pat):
            render(project / "figspecs" / "typo.toml", run_id=run.run_id)


def test_written_text_files_use_lf(project):
    with Run("lf") as run:
        save(runpath(run, "x.h5"), {"x": np.ones(2)})
        run.log_metric("m", 1.0, step=0)
        run.log("hello")
    from labkit.rawdata import freeze

    (project / "data" / "raw" / "in.bin").write_bytes(b"abc")
    for f in [*run.dir.glob("*.json"), *run.dir.glob("*.jsonl"), run.dir / "log.txt", freeze(chmod=False)]:
        assert b"\r\n" not in f.read_bytes(), f.name
