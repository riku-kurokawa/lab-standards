"""実験設定（TOML）の読み込み。extends による継承とコマンドライン上書きに対応.

configs/experiments/foo.toml:
    extends = "../base.toml"
    [filter]
    cutoff_hz = 50

上書き: load_config(path, ["filter.cutoff_hz=80", "seed=1"])
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from labkit._util import deep_merge


def _parse_value(text: str) -> Any:
    try:
        return tomllib.loads(f"v = {text}")["v"]
    except tomllib.TOMLDecodeError:
        return text


def _load_with_extends(path: Path, seen: set[Path]) -> tuple[dict, list[Path]]:
    path = path.resolve()
    if path in seen:
        raise ValueError(f"extends が循環しています: {path}")
    seen.add(path)
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    files = [path]
    parent = cfg.pop("extends", None)
    if parent:
        base, base_files = _load_with_extends((path.parent / parent), seen)
        cfg = deep_merge(base, cfg)
        files = base_files + files
    return cfg, files


def load_config(path: str | Path, overrides: list[str] | None = None) -> dict:
    """設定を読み込み、"_files" キーに読み込んだファイル一覧を入れて返す."""
    cfg, files = _load_with_extends(Path(path), set())
    for item in overrides or []:
        if "=" not in item:
            raise ValueError(f"上書きは key=value 形式: {item!r}")
        key, val = item.split("=", 1)
        node = cfg
        *heads, last = key.strip().split(".")
        for h in heads:
            node = node.setdefault(h, {})
        node[last] = _parse_value(val.strip())
    cfg["_files"] = [str(f) for f in files]
    cfg["_overrides"] = list(overrides or [])
    return cfg
