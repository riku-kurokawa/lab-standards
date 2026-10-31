"""内部ユーティリティ（ハッシュ・原子的書き込み・git 情報など）."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import secrets
import subprocess
from pathlib import Path
from typing import Any

CHUNK = 8 * 1024 * 1024


def sha256_file(path: str | os.PathLike) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(CHUNK):
            h.update(block)
    return h.hexdigest()


def sha256_tree(path: str | os.PathLike) -> str:
    """ディレクトリ（Zarr など）を相対パス順に連結してハッシュする."""
    root = Path(path)
    h = hashlib.sha256()
    # 相対パスは / 区切りの文字列で並べ、ハッシュに入れる（OS と Julia 実装で同じ値になる）
    files = sorted(((q.relative_to(root).as_posix(), q) for q in root.rglob("*") if q.is_file()), key=lambda t: t[0])
    for rel, p in files:
        h.update(rel.encode())
        h.update(bytes.fromhex(sha256_file(p)))
    return h.hexdigest()


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def tmp_sibling(path: Path) -> Path:
    return path.with_name(f".{path.name}.tmp-{os.getpid()}-{secrets.token_hex(3)}")


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tmp_sibling(path)
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def write_json_atomic(path: Path, obj: Any) -> None:
    write_text_atomic(path, json.dumps(obj, ensure_ascii=False, indent=2, default=_json_default) + "\n")


def _json_default(o: Any) -> Any:
    try:
        import numpy as np

        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
    except ImportError:  # pragma: no cover
        pass
    return str(o)


def git_info(root: Path) -> dict | None:
    def _git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=True, encoding="utf-8", errors="replace"
        ).stdout.strip()

    try:
        commit = _git("rev-parse", "HEAD")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    try:
        branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    except subprocess.CalledProcessError:
        branch = ""
    dirty = bool(_git("status", "--porcelain", "--untracked-files=no"))
    return {"commit": commit, "branch": branch, "dirty": dirty}


def labkit_source() -> dict:
    """labkit がリリース版か、手元の本体チェックアウト（link）かを記録する."""
    from labkit._version import __version__

    here = Path(__file__).resolve()
    for d in here.parents:
        if (d / "copier.yml").is_file() and (d / "labkit" / "python").is_dir():
            return {"mode": "link", "version": __version__, "path": str(d), "git": git_info(d)}
    return {"mode": "release", "version": __version__}


def slurm_info() -> dict | None:
    if "SLURM_JOB_ID" not in os.environ:
        return None
    keys = {
        "job_id": "SLURM_JOB_ID",
        "array_job_id": "SLURM_ARRAY_JOB_ID",
        "array_task_id": "SLURM_ARRAY_TASK_ID",
        "partition": "SLURM_JOB_PARTITION",
        "nodelist": "SLURM_JOB_NODELIST",
    }
    return {k: os.environ.get(v) for k, v in keys.items()}


def slugify(text: str) -> str:
    s = re.sub(r"[^0-9A-Za-z]+", "-", text).strip("-").lower()
    return s or "run"


def flatten(d: dict, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(flatten(v, key))
        else:
            out[key] = v
    return out


from labkit._labstate import deep_merge  # noqa: E402,F401  （定義は hooks と共有する _labstate.py）


def rel_or_abs(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()  # 記録は / 区切り
    except ValueError:
        return str(path.resolve())
