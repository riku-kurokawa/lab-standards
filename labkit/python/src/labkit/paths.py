"""環境ごとのパス解決。コード中に絶対パスを書かないための仕組み.

configs/paths/<LAB_ENV>.toml（既定 local）:
    data_root = "data"              # 相対パスはプロジェクトルート基準
    runs_root = "runs"
    # HPC 例: data_root = "/lustre/$USER/myproj/data"
"""

from __future__ import annotations

import os
from pathlib import Path

from labkit.config import find_root, read_toml

STAGES = ("raw", "external", "interim", "processed")


def env_name() -> str:
    return os.environ.get("LAB_ENV", "local")


def load_paths(root: Path | None = None) -> dict[str, Path]:
    r = root or find_root()
    cfg = {"data_root": "data", "runs_root": "runs"}
    f = r / "configs" / "paths" / f"{env_name()}.toml"
    if f.is_file():
        cfg.update(read_toml(f))
    elif env_name() != "local":
        raise FileNotFoundError(f"LAB_ENV={env_name()} ですが {f} がありません")
    out = {}
    for k, v in cfg.items():
        p = Path(os.path.expandvars(os.path.expanduser(str(v))))
        out[k] = p if p.is_absolute() else (r / p)
    return out


def datapath(stage: str, *parts: str, root: Path | None = None) -> Path:
    """datapath("processed", "features.parquet") -> <data_root>/processed/features.parquet"""
    if stage not in STAGES:
        raise ValueError(f"stage は {STAGES} のいずれか: {stage!r}")
    return load_paths(root)["data_root"].joinpath(stage, *parts)


def runs_root(root: Path | None = None) -> Path:
    return load_paths(root)["runs_root"]


def readonly_roots(root: Path | None = None) -> list[Path]:
    r = root or find_root()
    from labkit.config import load_lab

    lab = load_lab(r)
    ro = [(r / p).resolve() for p in lab["layout"]["readonly"]]
    ro.append(datapath("raw", root=r).resolve())
    return ro
