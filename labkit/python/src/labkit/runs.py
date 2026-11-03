"""run（実験 1 回 = 1 ディレクトリ）の管理.

    cfg = load_config("configs/experiments/example.toml")
    with Run("example", cfg, inputs=[datapath("raw", "rec01.h5")]) as run:
        save(runpath(run, "signal.h5"), {"t": t, "x": x})
        log_metric(run, "snr_db", 12.3, step=0)

runs/<run_id>/
    meta.json        来歴: git（commit, dirty）, 環境（lockfile, パッケージ, GPU）, seed, 入力の hash と系譜, 出力の hash, 状態
    dirty.patch      git.dirty=true のときだけ: 未コミットの差分（これが無いと dirty な run は再現できない）
    config.json      解決済み設定、config/ に元ファイルの写し
    metrics.jsonl    {"key","value","step","time"} を 1 行ずつ。metrics.json は各指標の最終値
    log.txt、heartbeat（最後に生きていた時刻）、figures/（labkit fig の出力先。完了後も書き込み可）
完了後、figures/ 以外は読み取り専用になる。異常終了で running のまま残った run は `labkit runs mark <id> failed`。
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
    env_info,
    git_dirty_patch,
    git_info,
    labkit_source,
    now_iso,
    read_json,
    rel_or_abs,
    sha256_file,
    sha256_tree,
    slugify,
    slurm_info,
    write_json_atomic,
    write_text_atomic,
)
from labkit._version import SCHEMA_VERSION, __version__
from labkit.config import find_root, load_lab
from labkit.paths import datapath, load_paths, runs_root

_current: contextvars.ContextVar[Run | None] = contextvars.ContextVar("labkit_run", default=None)
STATUSES = ("running", "finished", "failed", "interrupted")


def current_run() -> Run | None:
    return _current.get()


def make_run_id(name: str, commit: str | None) -> str:
    """UTC の秒 + 名前 + commit7 + 乱数 4 桁。衝突したら Run が乱数を引き直す."""
    ts = _dt.datetime.now(_dt.UTC).strftime("%Y%m%d-%H%M%S")
    return f"{ts}_{slugify(name)}_{commit[:7] if commit else 'nogit'}_{secrets.token_hex(2)}"


def _manifest_lookup(root: Path) -> dict[str, str]:
    """data/raw/MANIFEST.sha256 を {絶対パス: sha256} で返す."""
    raw = datapath("raw", root=root)
    mf = raw / "MANIFEST.sha256"
    out: dict[str, str] = {}
    if mf.is_file():
        for line in mf.read_text(encoding="utf-8").splitlines():
            parts = line.split(None, 2)
            if len(parts) == 3 and not line.startswith("#"):
                out[str((raw / parts[2].replace("\\", "/")).resolve())] = parts[0]
    return out


def describe_input(path: Path, root: Path, max_bytes: float | None = None, manifest: dict | None = None) -> dict:
    """入力の来歴: 存在・サイズ・sha256（台帳 → サイドカー → 計算）と、サイドカーにあれば生成元の run_id（系譜）."""
    p = Path(path).resolve()
    rec: dict[str, Any] = {"path": rel_or_abs(p, root), "exists": p.exists()}
    if not p.exists():
        return rec
    if max_bytes is None:
        max_bytes = float(load_lab(root)["runs"]["hash_max_gb"]) * 1024**3
    manifest = _manifest_lookup(root) if manifest is None else manifest
    size = p.stat().st_size if p.is_file() else sum(q.stat().st_size for q in p.rglob("*") if q.is_file())
    rec.update(size=size, mtime=_dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"))
    sidecar = p.with_name(p.name + ".meta.json")
    if str(p) in manifest:
        rec.update(sha256=manifest[str(p)], sha256_source="manifest")
    elif sidecar.is_file():
        sc = read_json(sidecar)
        rec.update(sha256=sc.get("sha256"), sha256_source="sidecar", run_id=sc.get("run_id"))
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
        with open(self.dir / "metrics.jsonl", "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec) + "\n")
        self._last[key] = rec["value"]
        self._beat()

    def log(self, message: str) -> None:
        line = f"[{now_iso()}] {message}"
        print(line)
        with open(self.dir / "log.txt", "a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
        self._beat()

    def add_input(self, path: str | os.PathLike) -> None:
        self.meta.setdefault("inputs", []).append(describe_input(Path(path), self.root, self._max_bytes()))
        write_json_atomic(self.dir / "meta.json", self.meta)

    # ---- 内部 ----
    def _max_bytes(self) -> float:
        return float(self.lab["runs"]["hash_max_gb"]) * 1024**3

    def _beat(self) -> None:
        write_text_atomic(self.dir / "heartbeat", now_iso() + "\n")

    def _mkdir(self) -> None:
        for _ in range(5):  # 同じ秒に始まる配列ジョブなどで ID が衝突したら乱数を引き直す
            try:
                self.dir.mkdir(parents=True, exist_ok=False)
                return
            except FileExistsError:
                self.run_id = make_run_id(self.name, self.git["commit"] if self.git else None)
                self.dir = self.dir.with_name(self.run_id)
        raise FileExistsError(f"run ディレクトリを作れません: {self.dir}")

    def __enter__(self) -> Run:
        self._mkdir()
        self._t0 = time.time()
        # 入力の hash や環境の取得は遅い。その間に止められても meta.json の無い殻（L020）を残さないよう、
        # 最小の meta を先に書く（running のまま残れば L021 → `labkit runs mark` で片付く）
        self.meta = minimal_meta(self.run_id, self.name, git=self.git, command=[sys.executable, *sys.argv])
        write_json_atomic(self.dir / "meta.json", self.meta)
        self._beat()
        (self.dir / "figures").mkdir()
        files = self.config.pop("_files", [])
        overrides = self.config.pop("_overrides", [])
        if files:
            cdir = self.dir / "config"
            cdir.mkdir()
            for f in files:
                shutil.copy2(f, cdir / rel_or_abs(Path(f), self.root / "configs").replace("/", "__"))
        write_json_atomic(self.dir / "config.json", self.config)
        manifest = _manifest_lookup(self.root)
        paths = load_paths(self.root)
        self.meta = {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "name": self.name,
            "status": "running",
            "language": "python",
            "language_version": platform.python_version(),
            "labkit_version": __version__,
            "labkit_source": labkit_source(),
            "created": self.meta["created"],
            "finished": None,
            "duration_s": None,
            "host": platform.node(),
            "pid": os.getpid(),
            "lab_env": os.environ.get("LAB_ENV", "local"),
            "paths": {k: str(v) for k, v in paths.items() if v is not None},
            "git": self.git,
            "env": env_info(self.root),
            "seed": self.config.get("seed"),
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
        self._beat()
        self._token = _current.set(self)
        if self.git and self.git["dirty"]:
            write_text_atomic(self.dir / "dirty.patch", git_dirty_patch(self.root))
            self.log("警告: 未コミットの変更がある状態で実行（git.dirty=true。差分は dirty.patch）")
        if self.meta["seed"] is None:
            self.log("警告: 設定に seed がありません（乱数を使うなら seed を設定に入れる）")
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
        self.meta["outputs"] = _outputs(self.dir, self._max_bytes())
        write_json_atomic(self.dir / "meta.json", self.meta)
        freeze_run(self.dir)
        return False


def _outputs(run_dir: Path, max_bytes: float) -> list[dict]:
    out = []
    for p in sorted(run_dir.rglob("*")):
        rel = p.relative_to(run_dir)
        if not p.is_file() or p.name in ("meta.json", "heartbeat") or rel.parts[0] == "figures":
            continue
        size = p.stat().st_size
        out.append({"path": rel.as_posix(), "size": size, "sha256": sha256_file(p) if size <= max_bytes else None})
    return out


def freeze_run(run_dir: Path, writable: bool = False) -> None:
    """figures/ 以外を読み取り専用にする（run の不変性）。writable=True で戻す（mark 用）."""
    ro = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
    mode = (ro | stat.S_IWUSR) if writable else ro
    for p in sorted(run_dir.rglob("*"), key=lambda q: len(q.parts), reverse=True):
        if p.relative_to(run_dir).parts[0] == "figures":
            continue
        os.chmod(p, mode | (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH if p.is_dir() else 0))


def minimal_meta(run_id: str, name: str, *, git: dict | None, command: list[str], created: str | None = None) -> dict:
    """スキーマの必須項目だけの meta（Run の開始直後と、meta の無い殻の mark に使う）."""
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "name": name,
        "status": "running",
        "language": "python",
        "labkit_version": __version__,
        "created": created or now_iso(),
        "finished": None,
        "host": platform.node(),
        "pid": os.getpid(),
        "git": git,
        "command": command,
        "inputs": [],
        "outputs": [],
        "error": None,
    }


def _shell_meta(d: Path) -> dict:
    """meta.json の無い run ディレクトリ（開始直後に止められた殻）の最小の meta。分かることだけを書く."""
    created = _dt.datetime.fromtimestamp(d.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    parts = d.name.split("_")  # <日時>_<name>_<commit>_<乱数>（make_run_id）
    name = "_".join(parts[1:-2]) if len(parts) >= 4 else d.name
    meta = minimal_meta(d.name, name, git=None, command=[], created=created)
    meta.pop("pid")
    meta["host"] = ""
    return meta


def mark_run(run_id: str, status: str, reason: str = "", root: Path | None = None) -> dict:
    """異常終了（OOM・kill・時間切れ）で running のまま残った run、または meta.json の無い殻の状態を記録する。
    Claude が実行してよい（削除はしない。殻は最小の meta を書いて記録として残す）."""
    if status not in STATUSES[1:]:
        raise ValueError(f"status は {STATUSES[1:]} のいずれか: {status!r}")
    d = find_run(run_id, root)
    meta = read_json(d / "meta.json") if (d / "meta.json").is_file() else _shell_meta(d)
    if meta.get("status") != "running":
        raise ValueError(f"{d.name} は status={meta.get('status')}（running の run だけ mark できる）")
    freeze_run(d, writable=True)
    meta.update(status=status, finished=now_iso(), error=f"marked {status} by labkit runs mark: {reason}".strip())
    if not (d / "metrics.json").exists():
        last: dict[str, float] = {}
        mf = d / "metrics.jsonl"
        if mf.is_file():
            for line in mf.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    last[rec["key"]] = rec["value"]
        write_json_atomic(d / "metrics.json", last)
    meta["outputs"] = _outputs(d, float(load_lab(root or find_root())["runs"]["hash_max_gb"]) * 1024**3)
    write_json_atomic(d / "meta.json", meta)
    freeze_run(d)
    return meta


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
                out.append(read_json(mf))
            except json.JSONDecodeError:
                out.append({"run_id": d.name, "status": "broken-meta"})
    return out
