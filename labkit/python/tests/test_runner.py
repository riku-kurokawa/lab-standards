"""labkit run: 設定の entry で実験を回す共通の入口."""

import json

import pytest

from labkit.runner import run_config
from labkit.runs import find_run


def write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture
def pkg(project):
    d = project / "src" / "mypkg"
    write(d / "__init__.py", "")
    write(
        d / "exp.py",
        "import numpy as np\n\n\n"
        "def run(cfg):\n"
        "    g = cfg['gain']\n"
        "    return {'snr_db': 10.0 * g, 'note': 'ok', 'x': np.arange(3) * g, 'tab': __import__('pandas').DataFrame({'a': [g]})}\n\n\n"
        "def curve(cfg, run):\n"
        "    for i in range(3):\n"
        "        run.log_metric('loss', 1.0 / (i + 1), step=i)\n"
        "    return {'final': 1.0 / 3}\n",
    )
    return project


def test_run_entry_saves_by_type_and_records_entry(pkg):
    pytest.importorskip("h5py")
    write(
        pkg / "configs" / "experiments" / "e.toml",
        'entry = "mypkg.exp:run"\nname = "e"\nseed = 0\ngain = 2\n[[pass]]\nkey = "snr_db"\nmin = 15\n',
    )
    rid = run_config(str(pkg / "configs" / "experiments" / "e.toml"), ["gain=3"], root=pkg)
    d = find_run(rid, pkg)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    metrics = json.loads((d / "metrics.json").read_text(encoding="utf-8"))
    assert meta["tags"]["entry"] == "mypkg.exp:run" and meta["status"] == "finished"
    assert metrics["snr_db"] == 30.0 and metrics["pass_1"] == 1.0 and metrics["pass_all"] == 1.0
    assert (
        (d / "tab.parquet").is_file()
        and (d / "arrays.h5").is_file()
        and "note: ok" in (d / "log.txt").read_text(encoding="utf-8")
    )


def test_run_sweep_writes_results_table(pkg):
    pytest.importorskip("pyarrow")
    import pandas as pd

    write(
        pkg / "configs" / "experiments" / "s.toml",
        'entry = "mypkg.exp:run"\nseed = 0\ngain = 1\n[sweep]\ngain = [1, 2]\nseed = [0, 1]\n',
    )
    rid = run_config(str(pkg / "configs" / "experiments" / "s.toml"), root=pkg)
    d = find_run(rid, pkg)
    df = pd.read_parquet(d / "results.parquet")
    assert (
        len(df) == 4
        and set(df.columns) == {"gain", "seed", "snr_db"}
        and df["snr_db"].tolist() == [10.0, 10.0, 20.0, 20.0]
    )
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    assert meta["tags"]["sweep"] == ["gain", "seed"] and meta["name"] == "s"
    assert (d / "tab_1.parquet").is_file() and (d / "arrays_4.h5").is_file()


def test_run_entry_with_run_argument_and_errors(pkg):
    write(pkg / "configs" / "experiments" / "c.toml", 'entry = "mypkg.exp:curve"\nseed = 0\n')
    rid = run_config(str(pkg / "configs" / "experiments" / "c.toml"), root=pkg)
    lines = (find_run(rid, pkg) / "metrics.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4 and json.loads(lines[0])["step"] == 0
    write(pkg / "configs" / "experiments" / "bad.toml", "seed = 0\n")
    with pytest.raises(ValueError, match="entry"):
        run_config(str(pkg / "configs" / "experiments" / "bad.toml"), root=pkg)
    write(pkg / "configs" / "experiments" / "bad2.toml", 'entry = "mypkg.exp:nope"\nseed = 0\n')
    with pytest.raises(ValueError, match="nope"):
        run_config(str(pkg / "configs" / "experiments" / "bad2.toml"), root=pkg)
    write(pkg / "configs" / "experiments" / "bad3.toml", 'entry = "mypkg.exp"\nseed = 0\n')
    with pytest.raises(ValueError, match="pkg.module:func"):
        run_config(str(pkg / "configs" / "experiments" / "bad3.toml"), root=pkg)
