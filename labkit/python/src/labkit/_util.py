"""内部ユーティリティ（ハッシュ・原子的書き込み・git と環境の情報）."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import subprocess
from importlib import metadata
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
    for rel, p in sorted((q.relative_to(root).as_posix(), q) for q in root.rglob("*") if q.is_file()):
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


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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


def deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def git(cwd: Path, *args: str) -> str | None:
    """git コマンドの標準出力。git が無い・リポジトリ外・失敗なら None."""
    try:
        return (
            subprocess.run(
                ["git", *args],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
            )
            .stdout.rstrip()
            .lstrip("\r\n")
        )  # 先頭の空白は残す（`git status --porcelain` の " M path" の 1 行目が欠けていた）
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


# 計算結果に影響しない場所。ここだけの未コミットは dirty に数えない（文書を書くたびに run が dirty になるのを防ぐ）。
# notebooks/ はコード（check.code_dirs）なので数える
DIRTY_IGNORE = ("docs/", "literature/", "prompts/", "scratch/", ".lab/", "README.md", "CLAUDE.md")


def git_status(root: Path) -> list[tuple[str, str]]:
    """`git status --porcelain -z` を [(XY, path)] で返す。-z なら空白・非 ASCII のパスも引用符で囲まれない."""
    out = git(root, "status", "--porcelain", "-z", "--untracked-files=all")
    if not out:
        return []
    items, entries = [e for e in out.split("\0") if e], []
    i = 0
    while i < len(items):
        xy, path = items[i][:2], items[i][3:]
        entries.append((xy, path))
        i += 2 if xy[0] in "RC" else 1  # rename/copy は次の要素が旧パス
    return entries


def git_info(root: Path) -> dict | None:
    """commit・branch・dirty。dirty は未追跡ファイル（コードになりうる）も数えるが、文書だけの変更は数えない。
    何が dirty だったかは dirty_paths（先頭 20 件）に残す."""
    commit = git(root, "rev-parse", "HEAD")
    if commit is None:
        return None
    paths = [p for _, p in git_status(root) if p and not p.startswith(DIRTY_IGNORE)]
    info = {"commit": commit, "branch": git(root, "rev-parse", "--abbrev-ref", "HEAD") or "", "dirty": bool(paths)}
    if paths:
        info["dirty_paths"] = paths[:20]
    return info


def git_dirty_patch(root: Path) -> str:
    """未コミットの状態を再現できる記録: 状態一覧 + 追跡ファイルの差分（未追跡は名前だけ）."""
    status = git(root, "status", "--porcelain", "--untracked-files=all") or ""
    diff = git(root, "diff", "HEAD", "--", ".", ":(exclude)uv.lock") or ""
    return f"# git status --porcelain --untracked-files=all\n{status}\n\n# git diff HEAD\n{diff}\n"


PACKAGES = ("numpy", "scipy", "pandas", "h5py", "pyarrow", "torch", "jax", "cupy", "polars", "scikit-learn")
THREAD_VARS = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "CUDA_VISIBLE_DEVICES")


def env_info(root: Path) -> dict:
    """run の環境: OS・CPU・GPU・ロックファイルの hash・主要パッケージの版・スレッド設定."""
    pkgs = {}
    for name in PACKAGES:
        try:
            pkgs[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    lock = root / "uv.lock"
    gpu = None
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=10,
                encoding="utf-8",
                errors="replace",
            ).stdout.strip()
            gpu = out.splitlines() or None
        except (subprocess.SubprocessError, OSError):
            gpu = None
    return {
        "os": platform.platform(),
        "cpu": platform.processor() or platform.machine(),
        "gpu": gpu,
        "lockfile_sha256": sha256_file(lock) if lock.is_file() else None,
        "packages": pkgs,
        "threads": {k: os.environ[k] for k in THREAD_VARS if k in os.environ},
    }


def labkit_source() -> dict:
    """labkit がリリース版か、手元の本体チェックアウト（link）かを記録する."""
    from labkit._version import __version__

    for d in Path(__file__).resolve().parents:
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
    return re.sub(r"[^0-9A-Za-z]+", "-", text).strip("-").lower() or "run"


def rel_or_abs(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()  # 記録は / 区切り
    except ValueError:
        return str(path.resolve())
