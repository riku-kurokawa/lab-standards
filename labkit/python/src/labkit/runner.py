"""実験の共通の入口（labkit run）。実験ごとの scripts/run_*.py を書かずに済ませる.

    labkit run configs/experiments/<name>.toml [key=value ...]

設定に書くもの:
    entry = "mypkg.experiments.lowpass:run"   # src の関数。fn(cfg) -> dict（2 引数なら fn(cfg, run)）
    inputs = ["data:processed/features.parquet"]   # 任意。来歴（sha256・生成元 run）に記録する
    [sweep] "filter.cutoff_hz" = [20, 50, 100]      # 任意。直積で回し、1 条件 1 行の results.parquet を保存する
    [[pass]] key = "snr_db" min = 10                # 任意。事前に書いた合否（Run が pass_N / pass_all を metrics に残す）

戻り値の dict の保存先: 数値 → log_metric、DataFrame → <key>.parquet、ndarray か配列の dict → <key>.h5、文字列 → ログ。
step 付きの記録（学習曲線）が要るなら fn(cfg, run) で run.log_metric(..., step=) を呼ぶ。
"""

from __future__ import annotations

import importlib
import inspect
import itertools
import sys
from pathlib import Path
from typing import Any

from labkit.config import find_root
from labkit.paths import datapath
from labkit.runconfig import load_config
from labkit.runs import Run, runpath


def resolve_entry(spec: str, root: Path):
    """ "pkg.module:func" を関数に解決する。src/ が import パスに無ければ足す."""
    if ":" not in spec:
        raise ValueError(f'entry は "pkg.module:func" の形: {spec!r}')
    mod_name, func_name = spec.split(":", 1)
    src = root / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))
    try:
        mod = importlib.import_module(mod_name)
    except ImportError as e:
        raise ValueError(f"entry {spec!r} のモジュールを import できません: {e}") from e
    fn = getattr(mod, func_name, None)
    if not callable(fn):
        raise ValueError(f"entry {spec!r}: {mod_name} に関数 {func_name} がありません")
    return fn


def _resolve_input(ref: str, root: Path) -> Path:
    if ref.startswith("data:"):
        stage, _, rest = ref[5:].partition("/")
        return datapath(stage, rest, root=root)
    p = Path(ref)
    return p if p.is_absolute() else root / p


def _set(cfg: dict, dotted: str, value: Any) -> None:
    node = cfg
    *heads, last = dotted.split(".")
    for h in heads:
        node = node.setdefault(h, {})
    node[last] = value


def save_result(run: Run, result: Any, suffix: str = "") -> dict[str, float]:
    """戻り値を種類ごとに保存し、数値（metrics に入れたもの）を返す."""
    import numpy as np

    from labkit.io import save

    if result is None:
        return {}
    if not isinstance(result, dict):
        raise TypeError(f"entry の戻り値は dict にしてください（{type(result).__name__}）")
    scalars: dict[str, float] = {}
    arrays: dict[str, Any] = {}
    for k, v in result.items():
        if isinstance(v, bool | int | float | np.generic) and not isinstance(v, np.ndarray):
            scalars[k] = float(v)
            if not suffix:
                run.log_metric(k, float(v))
        elif isinstance(v, str):
            run.log(f"{k}: {v}")
        elif hasattr(v, "to_parquet"):
            save(runpath(run, f"{k}{suffix}.parquet"), v)
        elif isinstance(v, np.ndarray):
            arrays[k] = v
        elif isinstance(v, dict):
            save(runpath(run, f"{k}{suffix}.h5"), v)
        else:
            raise TypeError(f"{k}: 保存できない型 {type(v).__name__}（数値・str・DataFrame・ndarray・配列の dict）")
    if arrays:
        save(runpath(run, f"arrays{suffix}.h5"), arrays)
    return scalars


def run_config(config_path: str, overrides: list[str] | None = None, root: Path | None = None) -> str:
    root = root or find_root()
    cfg = load_config(config_path, overrides)
    entry = cfg.get("entry")
    if not entry:
        raise ValueError(f'{config_path}: entry（例: entry = "pkg.experiments.x:run"）がありません')
    fn = resolve_entry(entry, root)
    takes_run = len(inspect.signature(fn).parameters) >= 2
    inputs = [_resolve_input(r, root) for r in cfg.get("inputs") or []]
    sweep = dict(cfg.get("sweep") or {})
    name = cfg.get("name") or Path(config_path).stem
    with Run(
        name, cfg, inputs=inputs, tags={"entry": entry, **({"sweep": sorted(sweep)} if sweep else {})}, root=root
    ) as run:
        if not sweep:
            save_result(run, fn(run.config, run) if takes_run else fn(run.config))
        else:
            import pandas as pd

            keys, grids = zip(*sweep.items(), strict=True)
            rows = []
            for i, combo in enumerate(itertools.product(*grids)):
                sub = {k: v for k, v in run.config.items() if k not in ("sweep", "pass")}
                for k, v in zip(keys, combo, strict=True):
                    _set(sub, k, v)
                run.log(f"sweep {i + 1}: " + ", ".join(f"{k}={v}" for k, v in zip(keys, combo, strict=True)))
                res = save_result(run, fn(sub, run) if takes_run else fn(sub), suffix=f"_{i + 1}")
                rows.append({**dict(zip(keys, combo, strict=True)), **res})
            from labkit.io import save

            save(runpath(run, "results.parquet"), pd.DataFrame(rows), description="sweep の 1 条件 1 行")
        print(run.run_id)
    return run.run_id
