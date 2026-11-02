"""データの保存・読み込み。保存経路はここに一本化する.

対応形式:
    .h5 / .hdf5   多次元配列（dict -> データセット、入れ子 dict -> グループ）
    .parquet      表（pandas / polars / pyarrow / 列の dict）
    その他        writer() で任意ライブラリの書き込みを包む（TB 級・Zarr など）

保存のたびに:
    1. 一時ファイルに書いて rename（原子的書き込み）
    2. sha256 を計算
    3. サイドカー <file>.meta.json に来歴（run_id, git, 入力, attrs）を記録
読み取り専用領域（data/raw など）への保存は拒否する。
"""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from labkit._util import (
    git_info,
    now_iso,
    rel_or_abs,
    sha256_file,
    sha256_tree,
    tmp_sibling,
    write_json_atomic,
)
from labkit._version import SCHEMA_VERSION, __version__
from labkit.config import find_root

ARRAY_EXT = {".h5", ".hdf5"}
TABLE_EXT = {".parquet"}


class ReadOnlyAreaError(PermissionError):
    pass


def _check_writable(path: Path, root: Path) -> None:
    from labkit.paths import readonly_roots

    p = path.resolve()
    for ro in readonly_roots(root):
        if p == ro or ro in p.parents:
            raise ReadOnlyAreaError(f"{p} は読み取り専用領域（{ro}）です。派生データは interim/processed か run へ。")


def _sidecar(path: Path) -> Path:
    return path.with_name(path.name + ".meta.json")


def _write_sidecar(path: Path, fmt: str, root: Path, attrs: dict, inputs, description: str) -> dict:
    from labkit.runs import current_run, describe_input

    run = current_run()
    digest = sha256_file(path) if path.is_file() else sha256_tree(path)
    size = path.stat().st_size if path.is_file() else sum(q.stat().st_size for q in path.rglob("*") if q.is_file())
    meta = {
        "schema_version": SCHEMA_VERSION,
        "file": path.name,
        "format": fmt,
        "sha256": digest,
        "size": size,
        "created": now_iso(),
        "created_by": f"labkit-python {__version__}",
        "run_id": run.run_id if run else None,
        "git": run.git if run else git_info(root),
        "inputs": [describe_input(Path(p), root) for p in (inputs or [])],
        "attrs": attrs or {},
        "description": description,
    }
    write_json_atomic(_sidecar(path), meta)
    return meta


def _attr_value(v: Any) -> Any:
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False)
    return v


def _write_h5(tmp: Path, data: dict, attrs: dict) -> None:
    import h5py
    import numpy as np

    def put(group, d: dict) -> None:
        for k, v in d.items():
            if isinstance(v, dict):
                put(group.create_group(k), v)
            elif isinstance(v, str):
                group.create_dataset(k, data=v, dtype=h5py.string_dtype())
            else:
                arr = np.asarray(v)
                kw = {"compression": "gzip", "compression_opts": 4, "chunks": True} if arr.size > 1024 else {}
                # bool は HDF5 に無い型。uint8 + 属性 labkit_dtype="bool" で書き、読む側が bool に戻す
                is_bool = arr.dtype == np.bool_
                ds = group.create_dataset(k, data=arr.astype(np.uint8) if is_bool else arr, **kw)
                if is_bool:
                    ds.attrs["labkit_dtype"] = "bool"

    with h5py.File(tmp, "w") as f:
        f.attrs["labkit_array_order"] = "C"
        f.attrs["labkit_version"] = __version__
        for k, v in (attrs or {}).items():
            f.attrs[k] = _attr_value(v)
        put(f, data)


def _to_arrow(data: Any):
    import pyarrow as pa

    if isinstance(data, pa.Table):
        return data
    if hasattr(data, "to_arrow"):  # polars
        return data.to_arrow()
    try:
        import pandas as pd

        if isinstance(data, pd.DataFrame):
            return pa.Table.from_pandas(data, preserve_index=False)
    except ImportError:  # pragma: no cover
        pass
    if isinstance(data, dict):
        return pa.table(data)
    raise TypeError(f"parquet に保存できない型です: {type(data)}")


def save(
    path: str | os.PathLike,
    data: Any,
    *,
    attrs: dict | None = None,
    inputs: list[str | os.PathLike] | None = None,
    description: str = "",
    overwrite: bool = False,
) -> Path:
    """data を path に保存し、サイドカーを書く。拡張子で形式を決める."""
    p = Path(path)
    root = find_root(p.parent if p.parent.exists() else None)
    _check_writable(p, root)
    if p.exists() and not overwrite:
        raise FileExistsError(f"{p} は既に存在します。再生成なら overwrite=True を明示してください。")
    p.parent.mkdir(parents=True, exist_ok=True)
    ext = p.suffix.lower()
    tmp = tmp_sibling(p)
    try:
        if ext in ARRAY_EXT:
            if not isinstance(data, dict):
                raise TypeError("HDF5 には {名前: 配列} の dict を渡してください")
            _write_h5(tmp, data, attrs or {})
            fmt = "hdf5"
        elif ext in TABLE_EXT:
            import pyarrow.parquet as pq

            pq.write_table(_to_arrow(data), tmp, compression="zstd")
            fmt = "parquet"
        else:
            raise ValueError(f"save() が扱わない拡張子です: {ext}（.h5 / .parquet）。それ以外は writer() を使う。")
        os.replace(tmp, p)
    finally:
        if tmp.exists():
            tmp.unlink()
    _write_sidecar(p, fmt, root, attrs or {}, inputs, description)
    _register_output(p)
    return p


@contextlib.contextmanager
def writer(
    path: str | os.PathLike,
    *,
    fmt: str | None = None,
    attrs: dict | None = None,
    inputs: list[str | os.PathLike] | None = None,
    description: str = "",
    overwrite: bool = False,
) -> Iterator[Path]:
    """任意のライブラリで書く大規模ファイル用。一時パスを渡し、成功時に rename + サイドカー.

    with writer(datapath("interim", "big.h5")) as tmp:
        with h5py.File(tmp, "w") as f:
            ds = f.create_dataset("x", shape=(n, m), chunks=(1, m))
            for i in range(n): ds[i] = compute(i)
    """
    p = Path(path)
    root = find_root(p.parent if p.parent.exists() else None)
    _check_writable(p, root)
    if p.exists() and not overwrite:
        raise FileExistsError(f"{p} は既に存在します（overwrite=True で再生成）")
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = tmp_sibling(p)
    try:
        yield tmp
        if not tmp.exists():
            raise FileNotFoundError(f"writer の一時パス {tmp} に何も書かれていません")
        if p.exists():
            import shutil

            shutil.rmtree(p) if p.is_dir() else p.unlink()
        os.replace(tmp, p)
    except BaseException:
        if tmp.exists():
            import shutil

            shutil.rmtree(tmp) if tmp.is_dir() else tmp.unlink()
        raise
    _write_sidecar(p, fmt or p.suffix.lstrip(".") or "unknown", root, attrs or {}, inputs, description)
    _register_output(p)


def _register_output(p: Path) -> None:
    from labkit.runs import current_run

    run = current_run()
    if run is not None and run.dir not in p.resolve().parents:
        run.meta.setdefault("external_outputs", []).append(rel_or_abs(p, run.root))


def _read_h5(path: Path) -> dict:
    import h5py

    def get(group) -> dict:
        out = {}
        for k, v in group.items():
            if isinstance(v, h5py.Group):
                out[k] = get(v)
            else:
                val = v[()]
                tag = v.attrs.get("labkit_dtype")
                if (tag.decode() if isinstance(tag, bytes) else tag) == "bool":
                    val = val.astype(bool)
                out[k] = val.decode() if isinstance(val, bytes) else val
        return out

    with h5py.File(path, "r") as f:
        return get(f)


def load(path: str | os.PathLike, *, verify: bool = False, backend: str = "pandas") -> Any:
    """保存したデータを読む。verify=True でサイドカーの sha256 と照合する.

    HDF5 -> dict[str, ndarray]、Parquet -> backend ("pandas" | "polars" | "arrow")
    """
    p = Path(path)
    # 先に確かめる: verify ではサイドカーの不在が先に見つかり、原因を取り違えさせる
    if not p.exists():
        raise FileNotFoundError(f"{p} がありません")
    if verify:
        meta = load_meta(p)
        actual = sha256_file(p) if p.is_file() else sha256_tree(p)
        if actual != meta["sha256"]:
            raise ValueError(f"{p} の sha256 がサイドカーと一致しません（改変または破損）")
    ext = p.suffix.lower()
    if ext in ARRAY_EXT:
        return _read_h5(p)
    if ext in TABLE_EXT:
        import pyarrow.parquet as pq

        table = pq.read_table(p)
        if backend == "arrow":
            return table
        if backend == "polars":
            import polars as pl

            return pl.from_arrow(table)
        return table.to_pandas()
    raise ValueError(f"load() が扱わない拡張子です: {ext}")


def load_attrs(path: str | os.PathLike) -> dict:
    return load_meta(path).get("attrs", {})


def load_meta(path: str | os.PathLike) -> dict:
    sc = _sidecar(Path(path))
    if not sc.is_file():
        raise FileNotFoundError(f"サイドカー {sc} がありません（labkit.save 以外で作られたファイル？）")
    return json.loads(sc.read_text(encoding="utf-8"))


__all__ = ["save", "load", "load_meta", "load_attrs", "writer", "ReadOnlyAreaError"]
