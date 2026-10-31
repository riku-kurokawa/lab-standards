"""labkit: 研究用計算プロジェクトの共通ライブラリ.

Python と Julia (LabKit.jl) で同じ関数名・同じファイル形式を提供する。

    from labkit import load_config, Run, runpath, log_metric, save, load, datapath
"""

from labkit._version import __version__
from labkit.config import find_root, load_lab
from labkit.io import load, load_meta, save, writer
from labkit.paths import datapath, runs_root
from labkit.runconfig import load_config
from labkit.runs import Run, add_input, current_run, log_message, log_metric, runpath


def fig(spec: str, run: "Run | str | None" = None) -> list:
    """図テンプレートで図を作る（labkit fig と同じ。Julia の LabKit.fig と同名）."""
    from labkit.viz import render

    return render(spec, run_id=run.run_id if isinstance(run, Run) else run)


def cite(run_id: str, key: str, digits: int | None = None, unit: str = "") -> str:
    """run の指標を検証可能な書式で返す（labkit cite と同じ。Julia の LabKit.cite と同名）."""
    from labkit.check import cite as _cite

    return _cite(run_id, key, digits=digits, unit=unit)


def check(full: bool = False) -> int:
    from labkit.cli import main

    return main(["check", "--full"] if full else ["check"])


__all__ = [
    "fig",
    "cite",
    "check",
    "log_message",
    "add_input",
    "__version__",
    "find_root",
    "load_lab",
    "load_config",
    "Run",
    "current_run",
    "runpath",
    "log_metric",
    "save",
    "load",
    "load_meta",
    "writer",
    "datapath",
    "runs_root",
]
