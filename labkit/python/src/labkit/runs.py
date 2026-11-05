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
        if self.lab["runs"].get("require_prediction") and not self.config.get("prediction"):
            raise ValueError(
                "lab.toml の runs.require_prediction が有効です。実行の前に、結果の予想（数値と根拠）を設定の "
                "`prediction` に書いてください（予想に自信があり主張の証拠として要らないなら、計算せず導出で確定させる）"
            )
        if self.lab["runs"].get("require_clean") and self.git and self.git["dirty"]:
            paths = ", ".join(self.git.get("dirty_paths", [])[:5])
            raise ValueError(
                f"lab.toml の runs.require_clean が有効です。未コミットの変更があります: {paths}"
                "（dirty な run は結果として引用できない）。commit してから実行するか、試行なら scratch/ で行ってください"
            )
        check_prediction(self.config.get("prediction"))
        check_pass(self.config.get("pass"))
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
            "prediction": self.config.get("prediction"),
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
        pred = self.meta["prediction"]
        if isinstance(pred, dict) and pred.get("expert_predictable"):
            self.log(
                "注意: expert_predictable=true（専門家なら計算せずに分かる結果）。なぜ計算が要るかは basis に書いてあること"
            )
        elif pred is not None and not isinstance(pred, str | dict):
            self.log("注意: prediction が表でも文字列でもないので自動判定しない（[prediction] の表に書く）")
        if self.meta["labkit_source"]["mode"] == "link":
            self.log("注意: labkit は手元の lab-standards を参照中（link）。この run は正式版の結果ではありません")
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        _current.reset(self._token)
        self.meta["finished"] = now_iso()
        self.meta["duration_s"] = round(time.time() - self._t0, 3)
        if exc_type is None:
            self.meta["status"] = "finished"
            # 事前に書いた合否（[[pass]]）と予想の判定。判定が失敗しても run は finished にする（結果は失われない）
            for i, crit in enumerate(self.config.get("pass") or [], 1):
                try:
                    ok = evaluate_pass(crit, self._last, self.dir)
                except Exception as e:  # 列名の誤りなど。不合格として残し、理由をログに
                    ok = False
                    self.log(f"pass_{i} を評価できない（不合格として記録）: {type(e).__name__}: {e}")
                self.log_metric(f"pass_{i}", float(ok))
            if self.config.get("pass"):
                self.log_metric(
                    "pass_all", float(all(self._last[f"pass_{i}"] for i in range(1, len(self.config["pass"]) + 1)))
                )
            if isinstance(self.meta.get("prediction"), dict):
                try:
                    self.meta["prediction_result"] = judge_prediction(self.meta["prediction"], self._last)
                except Exception as e:
                    self.meta["prediction_result"] = {
                        "verdict": "undeterminable",
                        "hit": 0,
                        "total": 0,
                        "error": str(e),
                    }
                self.log(f"予想の判定: {self.meta['prediction_result']['verdict']}")
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


# ---- 予想の関門と事前の合否 ----
def _num(x) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


def check_prediction(pred) -> None:
    """prediction は文字列（自由記述）か表 {basis, confidence?, expert_predictable?, claims=[{key, range|point+tol}]}。
    表のときだけ構造を検証する（run を作る前に止める。判定の最中に落ちると run が running のまま残るため）."""
    if not isinstance(pred, dict):
        return
    if not str(pred.get("basis", "")).strip():
        raise ValueError('prediction の表には basis（根拠）が必要です: [prediction] basis = "..."')
    for c in pred.get("claims") or []:
        rng = c.get("range") if isinstance(c, dict) else None
        ok_range = isinstance(rng, list | tuple) and len(rng) == 2 and all(_num(v) for v in rng)
        ok_point = isinstance(c, dict) and _num(c.get("point")) and _num(c.get("tol"))
        if not isinstance(c, dict) or not isinstance(c.get("key"), str) or not (ok_range or ok_point):
            raise ValueError(
                "[[prediction.claims]] には key（文字列）と、range = [lo, hi]（数値）か point + tol（数値）が必要です"
            )


def check_pass(criteria) -> None:
    """[[pass]] の構造を run を作る前に検証する（key は文字列、min/max は数値、table は文字列、where は表）."""
    for i, c in enumerate(criteria or [], 1):
        bad = (
            not isinstance(c, dict)
            or not isinstance(c.get("key"), str)
            or not ("min" in c or "max" in c)
            or any(k in c and not _num(c[k]) for k in ("min", "max"))
            or ("table" in c and not isinstance(c["table"], str))
            or ("where" in c and not isinstance(c["where"], dict))
        )
        if bad:
            raise ValueError(
                f'[[pass]] #{i}: key = "<metrics か列名>" と min / max（数値）が必要です（table は文字列、where は表）'
            )


def judge_prediction(pred: dict, metrics: dict) -> dict:
    """表形式の予想を metrics と照合する。key が無い主張は undeterminable（当たりにも外れにも数えない）."""
    rows = []
    for c in pred.get("claims") or []:
        v = metrics.get(c["key"])
        if v is None:
            rows.append({"key": c["key"], "value": None, "hit": None})
            continue
        lo, hi = c["range"] if c.get("range") else (c["point"] - c["tol"], c["point"] + c["tol"])
        rows.append({"key": c["key"], "value": v, "hit": bool(lo <= v <= hi)})
    hits = sum(1 for r in rows if r["hit"] is True)
    judged = [r for r in rows if r["hit"] is not None]
    verdict = "undeterminable" if not judged else "hit" if hits == len(judged) else "miss" if hits == 0 else "partial"
    return {"verdict": verdict, "hit": hits, "total": len(judged), "undeterminable": len(rows) - len(judged)}


def evaluate_pass(crit: dict, metrics: dict, run_dir: Path) -> bool:
    """[[pass]] key="e1" max=0.02 [min=] [table="results.parquet" where={wall="char"}]。
    table があれば Parquet の列、無ければ metrics。該当する値がすべて範囲内なら合格。値が無ければ不合格."""
    lo, hi = crit.get("min", float("-inf")), crit.get("max", float("inf"))
    if crit.get("table"):
        import pandas as pd

        f = run_dir / crit["table"]
        if not f.is_file():
            return False
        df = pd.read_parquet(f)
        for k, v in (crit.get("where") or {}).items():
            df = df[df[k] == v]
        vals = df[crit["key"]].tolist() if crit["key"] in df else []
    else:
        vals = [metrics[crit["key"]]] if crit.get("key") in metrics else []
    return bool(vals) and all(lo <= float(v) <= hi for v in vals)


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


def list_runs(root: Path | None = None, *, include_archived: bool = False) -> list[dict]:
    """runs/ の meta を作成順に。退避済み（archived）は既定で隠す（人間が見る一覧を根拠になり得る run だけにする）."""
    base = runs_root(root)
    out = []
    if not base.is_dir():
        return out
    for d in sorted(base.iterdir()):
        mf = d / "meta.json"
        if mf.is_file():
            try:
                m = read_json(mf)
            except json.JSONDecodeError:
                m = {"run_id": d.name, "status": "broken-meta"}
            if include_archived or not m.get("archived"):
                out.append(m)
    return out


def _rewrite_meta(d: Path, update: dict) -> dict:
    meta = read_json(d / "meta.json")
    freeze_run(d, writable=True)
    meta.update(update)
    write_json_atomic(d / "meta.json", meta)
    freeze_run(d)
    return meta


def archive_runs(run_ids: list[str], reason: str, *, undo: bool = False, root: Path | None = None) -> list[str]:
    """run を退避する: 削除せず meta.json に archived を書き、一覧と DIGEST から隠す。引用されると L032 が知らせる。
    Claude が実行してよい（running の run は対象外。取り消しは undo）."""
    done = []
    for rid in run_ids:
        d = find_run(rid, root)
        if not (d / "meta.json").is_file():
            raise ValueError(f"{d.name} に meta.json がありません（先に `labkit runs mark`）")
        meta = read_json(d / "meta.json")
        if meta.get("status") == "running":
            raise ValueError(f"{d.name} は running です（終わっていれば先に `labkit runs mark`）")
        if undo:
            _rewrite_meta(d, {"archived": None})
        elif not meta.get("archived"):
            _rewrite_meta(d, {"archived": {"when": now_iso(), "reason": reason}})
        done.append(d.name)
    return done


def archive_candidates(
    *,
    statuses: tuple[str, ...] = (),
    uncited: bool = False,
    older_than_days: float = 0,
    archived: bool = False,
    root: Path | None = None,
) -> list[dict]:
    """退避の候補: status が statuses のもの、または（uncited）文書・拍の記録に引用されず他の run の入力にもなっていない finished。
    archived=True なら退避済みの中から（--undo 用）."""
    from labkit.check import cited_run_ids
    from labkit.config import find_root

    r = root or find_root()
    runs = [m for m in list_runs(r, include_archived=True) if bool(m.get("archived")) == archived]
    cited = set(cited_run_ids(r)) if uncited else set()
    lineage = {i.get("run_id") for m in runs for i in m.get("inputs") or [] if i.get("run_id")}
    cutoff = (_dt.datetime.now() - _dt.timedelta(days=older_than_days)).isoformat() if older_than_days else None
    out = []
    for m in runs:
        if m.get("status") == "running":
            continue
        if cutoff and str(m.get("created", "")) > cutoff:
            continue
        by_status = m.get("status") in statuses
        by_uncited = uncited and m.get("status") == "finished" and m["run_id"] not in cited | lineage
        if by_status or by_uncited:
            out.append(m)
    return out


def verdict_run(run_id: str, *, say: str | None = None, note: str = "", root: Path | None = None) -> dict:
    """予想の判定を meta.json の prediction_result に書く。表形式の予想は metrics から判定し直す。
    自由記述の予想は --say hit|miss|partial の自己申告（self_reported=true が残る）."""
    d = find_run(run_id, root)
    meta = read_json(d / "meta.json")
    if meta.get("status") != "finished":
        raise ValueError(f"{d.name} は status={meta.get('status')}（finished の run だけ判定する）")
    pred = meta.get("prediction")
    if not pred:
        raise ValueError(f"{d.name} に予想（prediction）がありません")
    mf = d / "metrics.json"
    metrics = read_json(mf) if mf.is_file() else {}
    if isinstance(pred, dict):
        result = judge_prediction(pred, metrics)
    elif say in ("hit", "miss", "partial"):
        result = {"verdict": say, "self_reported": True, "note": note}
    else:
        raise ValueError("自由記述の予想は --say hit|miss|partial --note '理由' で自己申告する（表形式なら自動）")
    result["when"] = now_iso()
    return _rewrite_meta(d, {"prediction_result": result})["prediction_result"]


def runs_table(pattern: str, file: str = "results.parquet", *, include_all: bool = False, root: Path | None = None):
    """複数 run の同じ表を縦に連結する（集計スクリプトを毎回書かないため）。
    pattern は run の name か run_id の部分文字列。既定では clean な finished で退避されていない run だけ。
    除外した run は df.attrs["excluded"] に残し、実行中の run があれば入力として来歴に記録する."""
    import pandas as pd

    frames, excluded = [], []
    for m in list_runs(root, include_archived=include_all):
        if pattern not in m.get("name", "") and pattern not in m["run_id"]:
            continue
        d = runs_root(root) / m["run_id"]
        why = (
            f"status={m.get('status')}"
            if m.get("status") != "finished"
            else "dirty"
            if (m.get("git") or {}).get("dirty")
            else "archived"
            if m.get("archived")
            else ""
        )
        if why and not include_all or not (d / file).is_file():
            excluded.append((m["run_id"], why or f"{file} なし"))
            continue
        df = pd.read_parquet(d / file)
        df.insert(0, "run_id", m["run_id"])
        df.insert(1, "commit", (m.get("git") or {}).get("commit", "")[:7])
        frames.append(df)
        if (run := current_run()) is not None:
            run.add_input(d / file)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    out.attrs["excluded"] = excluded
    return out
