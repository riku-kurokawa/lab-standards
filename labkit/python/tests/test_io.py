"""HDF5 / Parquet の保存・読込・図テンプレート（h5py, pyarrow が必要）."""

import json

import numpy as np
import pytest

h5py = pytest.importorskip("h5py")
pytest.importorskip("pyarrow")

from labkit import Run, datapath, load, load_meta, runpath, save, writer  # noqa: E402
from labkit.check import run_check  # noqa: E402
from labkit.io import ReadOnlyAreaError  # noqa: E402


def test_h5_roundtrip_and_sidecar(project):
    x = np.arange(12.0).reshape(3, 4)
    p = save(
        datapath("processed", "a.h5"),
        {"x": x, "grp": {"y": np.ones(3)}, "label": "ok"},
        attrs={"fs": 1000.0, "unit": "V"},
    )
    d = load(p, verify=True)
    assert np.array_equal(d["x"], x) and d["grp"]["y"].shape == (3,) and d["label"] == "ok"
    meta = load_meta(p)
    assert meta["format"] == "hdf5" and meta["attrs"]["fs"] == 1000.0
    with h5py.File(p) as f:
        assert f.attrs["labkit_array_order"] == "C"
    with pytest.raises(FileExistsError):
        save(p, {"x": x})
    save(p, {"x": x * 2}, overwrite=True)
    assert not [i for i in run_check()[0] if i.code == "L022"]


def test_parquet_roundtrip(project):
    import pandas as pd

    df = pd.DataFrame({"m": ["a", "a", "b"], "v": [1.0, 2.0, 3.0]})
    p = save(datapath("processed", "t.parquet"), df)
    assert load(p, verify=True).equals(df)


def test_raw_is_readonly(project):
    with pytest.raises(ReadOnlyAreaError):
        save(datapath("raw", "x.h5"), {"x": np.ones(2)})


def test_writer_and_run_outputs(project):
    with Run("w") as run:
        with writer(runpath(run, "big.h5")) as tmp:
            with h5py.File(tmp, "w") as f:
                f.create_dataset("x", data=np.zeros((10, 10)))
    meta = json.loads((run.dir / "meta.json").read_text())
    assert any(o["path"] == "big.h5" for o in meta["outputs"])
    assert (run.dir / "big.h5.meta.json").exists()


def test_figure_templates(project):
    from labkit.viz import render

    t = np.linspace(0, 1, 1000)
    with Run("fig") as run:
        save(runpath(run, "s.h5"), {"t": t, "x": np.sin(2 * np.pi * 5 * t)})
        for i in range(5):
            run.log_metric("loss", 1 / (i + 1), step=i)
    specs = {
        "ts.toml": 'template = "timeseries"\n[data]\nfile = "s.h5"\nx = "t"\ny = ["x"]\n',
        "lc.toml": 'template = "learning_curve"\n[data]\nmetrics = ["loss"]\n',
        "psd.toml": 'template = "psd"\n[data]\nfile = "s.h5"\nsignal = "x"\nfs = 1000.0\nnperseg = 256\n',
        "sp.toml": 'template = "spectrogram"\n[data]\nfile = "s.h5"\nsignal = "x"\nfs = 1000.0\nnperseg = 64\n',
    }
    for name, text in specs.items():
        (project / "figspecs" / name).write_text(text)
        out = render(project / "figspecs" / name, run_id=run.run_id)
        assert all(p.exists() for p in out)
    assert (run.dir / "figures" / "ts.figmeta.json").exists()
