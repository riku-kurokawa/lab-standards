"""run（実験1回 = 1ディレクトリ）の管理.

    cfg = load_config("configs/experiments/example.toml")
    with Run("example", cfg, inputs=[datapath("raw", "rec01.h5")]) as run:
        save(runpath(run, "signal.h5"), {"t": t, "x": x})
        log_metric(run, "snr_db", 12.3, step=0)

ディレクトリ構成（Julia 版も同一）:
    runs/<run_id>/
        meta.json        来歴: git, 環境, Slurm, 入力 hash, 出力一覧, 状態
        config.json      解決済み設定
        config/          元の設定ファイルのコピー
        metrics.jsonl    {"key","value","step","time"} を1行ずつ
        metrics.json     各メトリクスの最終値
        log.txt
        figures/         labkit fig の出力先（完了後も書き込み可）
完了後、figures/ 以外は読み取り専用になる。
"""

from __future__ import annotations

import contextvars
import datetime as _dt
import json
import os
import platform
import secrets
import shutil
import stat
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from labkit._util import (
    git_info,
    labkit_source,
    now_iso,
    rel_or_abs,
    sha256_file,
    sha256_tree,
    slugify,
    slurm_info,
    write_json_atomic,
)
from labkit._version import SCHEMA_VERSION, __version__
from labkit.config import find_root, load_lab
from labkit.paths import runs_root

_current: contextvars.ContextVar[Run | None] = contextvars.ContextVar("labkit_run", default=None)


def current_run() -> Run | None:
    return _current.get()


def make_run_id(name: str, commit: str | None) -> str:
    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    short = commit[:7] if commit else "nogit"
    return f"{ts}_{slugify(name)}_{short}_{secrets.token_hex(2)}"


def _manifest_lookup(root: Path) -> dict[str, str]:
    """data/raw/MANIFEST.sha256 を {絶対パス: sha256} で返す."""
    from labkit.paths import datapath

    raw = datapath("raw", root=root)
    mf = raw / "MANIFEST.sha256"
    out: dict[str, str] = {}
    if mf.is_file():
        for line in mf.read_text(encoding="utf-8").splitlines():
            parts = line.split(None, 2)
            if len(parts) == 3 and not line.startswith("#"):
                out[str((raw / parts[2].replace("\\", "/")).resolve())] = parts[0]
    return out


def describe_input(path: Path, root: Path, max_bytes: float, manifest: dict[str, str]) -> dict:
    p = Path(path).resolve()
    rec: dict[str, Any] = {"path": rel_or_abs(p, root), "exists": p.exists()}
    if not p.exists():
        return rec
    size = p.stat().st_size if p.is_file() else sum(q.stat().st_size for q in p.rglob("*") if q.is_file())
    rec.update(size=size, mtime=_dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"))
    sidecar = p.with_name(p.name + ".meta.json")
    if str(p) in manifest:
        rec.update(sha256=manifest[str(p)], sha256_source="manifest")
    elif sidecar.is_file():
        rec.update(sha256=json.loads(sidecar.read_text(encoding="utf-8"))["sha256"], sha256_source="sidecar")
    elif size <= max_bytes:
        rec.update(sha256=sha256_file(p) if p.is_file() else sha256_tree(p), sha256_source="computed")
    else:
        rec.update(sha256=None, sha256_source="skipped_too_large")
    return rec


class Run:
    def __init__(
        self,
        name: str,
        config: dict | None = None,
        *,
        inputs: list[str | os.PathLike] = (),
        tags: dict[str, Any] | None = None,
        root: str | os.PathLike | None = None,
    ):
        self.root = Path(root) if root else find_root()
        self.lab = load_lab(self.root)
        self.name = name
        self.config = dict(config or {})
        self.tags = dict(tags or {})
        self._input_paths = [Path(p) for p in inputs]
        self.git = git_info(self.root)
        self.run_id = make_run_id(name, self.git["commit"] if self.git else None)
        self.dir = runs_root(self.root) / self.run_id
        self._t0 = 0.0
        self._last: dict[str, Any] = {}
        self.meta: dict[str, Any] = {}

    # ---- 公開 API ----
    def path(self, *parts: str) -> Path:
        p = self.dir.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def log_metric(self, key: str, value: float, step: int | None = None) -> None:
        rec = {"key": key, "value": float(value), "step": step, "time": time.time()}
        with open(self.dir / "metrics.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        self._last[key] = rec["value"]

    def log(self, message: str) -> None:
        line = f"[{now_iso()}] {message}"
        print(line)
        with open(self.dir / "log.txt", "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def add_input(self, path: str | os.PathLike) -> None:
        rec = describe_input(Path(path), self.root, self._max_bytes(), _manifest_lookup(self.root))
        self.meta.setdefault("inputs", []).append(rec)
        write_json_atomic(self.dir / "meta.json", self.meta)

    # ---- コンテキスト ----
    def _max_bytes(self) -> float:
        return float(self.lab["runs"]["hash_inputs_max_gb"]) * 1024**3

    def __enter__(self) -> Run:
        self.dir.mkdir(parents=True, exist_ok=False)
        (self.dir / "figures").mkdir()
        self._t0 = time.time()
        files = self.config.pop("_files", [])
        overrides = self.config.pop("_overrides", [])
        if files:
            cdir = self.dir / "config"
            cdir.mkdir()
            for f in files:
                shutil.copy2(f, cdir / Path(f).name)
        write_json_atomic(self.dir / "config.json", self.config)
        manifest = _manifest_lookup(self.root)
        self.meta = {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "name": self.name,
            "status": "running",
            "language": "python",
            "language_version": platform.python_version(),
            "labkit_version": __version__,
            "labkit_source": labkit_source(),
            "created": now_iso(),
            "finished": None,
            "duration_s": None,
            "host": platform.node(),
            "lab_env": os.environ.get("LAB_ENV", "local"),
            "git": self.git,
            "slurm": slurm_info(),
            "command": [sys.executable, *sys.argv],
            "cwd": os.getcwd(),
            "config_files": [rel_or_abs(Path(f), self.root) for f in files],
            "config_overrides": overrides,
            "inputs": [describe_input(p, self.root, self._max_bytes(), manifest) for p in self._input_paths],
            "outputs": [],
            "tags": self.tags,
            "error": None,
        }
        write_json_atomic(self.dir / "meta.json", self.meta)
        self._token = _current.set(self)
        if self.git and self.git["dirty"]:
            self.log("警告: 未コミットの変更がある状態で実行しています（meta.json の git.dirty=true）")
        if self.meta["labkit_source"]["mode"] == "link":
            self.log("注意: labkit は手元の lab-standards を参照中（link）。この run は正式版の結果ではありません")
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        _current.reset(self._token)
        self.meta["finished"] = now_iso()
        self.meta["duration_s"] = round(time.time() - self._t0, 3)
        if exc_type is None:
            self.meta["status"] = "finished"
        elif exc_type is KeyboardInterrupt:
            self.meta["status"] = "interrupted"
        else:
            self.meta["status"] = "failed"
            self.meta["error"] = "".join(traceback.format_exception(exc_type, exc, tb))[-4000:]
        write_json_atomic(self.dir / "metrics.json", self._last)
        skip = {"meta.json"}
        self.meta["outputs"] = sorted(
            (
                {"path": p.relative_to(self.dir).as_posix(), "size": p.stat().st_size}
                for p in self.dir.rglob("*")
                if p.is_file() and p.name not in skip and "figures" not in p.relative_to(self.dir).parts
            ),
            key=lambda d: d["path"],
        )
        write_json_atomic(self.dir / "meta.json", self.meta)
        freeze_run(self.dir)
        return False


def freeze_run(run_dir: Path) -> None:
    """figures/ 以外を読み取り専用にする（run の不変性）."""
    ro = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
    for p in sorted(run_dir.rglob("*"), key=lambda q: len(q.parts), reverse=True):
        rel = p.relative_to(run_dir).parts
        if rel and rel[0] == "figures":
            continue
        if p.is_file():
            os.chmod(p, ro)
        elif p.is_dir():
            os.chmod(p, ro | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    # ルート自体は figures/ を書けるよう、ファイル追加だけ禁止しない（mode 0755 のまま）


def runpath(run: Run, *parts: str) -> Path:
    return run.path(*parts)


def log_metric(run: Run, key: str, value: float, step: int | None = None) -> None:
    run.log_metric(key, value, step)


def log_message(run: Run, message: str) -> None:
    run.log(message)


def add_input(run: Run, path: str | os.PathLike) -> None:
    run.add_input(path)


def find_run(run_id: str, root: Path | None = None) -> Path:
    base = runs_root(root)
    exact = base / run_id
    if exact.is_dir():
        return exact
    matches = sorted(p for p in base.iterdir() if p.is_dir() and run_id in p.name)
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise FileNotFoundError(f"run が見つかりません: {run_id}")
    raise ValueError(f"run ID が曖昧です（{len(matches)} 件一致）: {run_id}")


def list_runs(root: Path | None = None) -> list[dict]:
    base = runs_root(root)
    out = []
    if not base.is_dir():
        return out
    for d in sorted(base.iterdir()):
        mf = d / "meta.json"
        if mf.is_file():
            try:
                out.append(json.loads(mf.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                out.append({"run_id": d.name, "status": "broken-meta"})
    return out
