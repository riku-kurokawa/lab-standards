"""runs/ を MLflow（ローカル専用）へ同期して閲覧・比較する.

真の記録は常に runs/ のファイル。MLflow は閲覧用の索引にすぎないので、
.mlflow/ を消しても `labkit mlflow sync` で何度でも作り直せる。
Python の run も Julia の run も同じ形式なので、同じ画面に並ぶ。

外部送信を防ぐため:
    - 保存先はプロジェクト内の SQLite（.mlflow/mlflow.db）とローカルディレクトリだけ
    - MLflow の匿名利用統計（telemetry）を MLFLOW_DISABLE_TELEMETRY / DO_NOT_TRACK で無効化
    - UI は 127.0.0.1 にのみバインド
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from labkit._util import flatten
from labkit.config import find_root, load_lab

PRIVACY_ENV = {"MLFLOW_DISABLE_TELEMETRY": "true", "DO_NOT_TRACK": "true"}


def _setup(root: Path) -> tuple[str, Path]:
    os.environ.update(PRIVACY_ENV)
    store = root / ".mlflow"
    store.mkdir(exist_ok=True)
    return f"sqlite:///{store / 'mlflow.db'}", store / "artifacts"


def _ms(iso: str | None) -> int | None:
    return int(datetime.fromisoformat(iso).timestamp() * 1000) if iso else None


def sync(force: bool = False, root: Path | None = None, progress=print) -> int:
    root = root or find_root()
    uri, art = _setup(root)
    try:
        from mlflow.entities import Metric, Param, RunTag
        from mlflow.tracking import MlflowClient
    except ImportError as e:
        raise SystemExit("MLflow が未インストールです: uv add 'labkit[mlflow]' または pip install mlflow") from e
    from labkit.paths import runs_root
    from labkit.runs import list_runs

    client = MlflowClient(tracking_uri=uri)
    exp_name = load_lab(root)["lab"].get("project") or root.name
    exp = client.get_experiment_by_name(exp_name)
    exp_id = exp.experiment_id if exp else client.create_experiment(exp_name, artifact_location=art.as_uri())
    n = 0
    for meta in list_runs(root):
        rid = meta.get("run_id")
        if not rid or meta.get("status") == "running":
            continue
        found = client.search_runs([exp_id], filter_string=f"tags.`labkit.run_id` = '{rid}'")
        if found and not force:
            continue
        for r in found:
            client.delete_run(r.info.run_id)
        rdir = runs_root(root) / rid
        cfg = json.loads((rdir / "config.json").read_text()) if (rdir / "config.json").exists() else {}
        git = meta.get("git") or {}
        tags = {
            "labkit.run_id": rid, "labkit.name": meta.get("name", ""), "labkit.language": meta.get("language", ""),
            "labkit.status": meta.get("status", ""), "labkit.host": meta.get("host", ""),
            "labkit.lab_env": meta.get("lab_env", ""), "mlflow.source.git.commit": git.get("commit", ""),
            "labkit.git_dirty": str(git.get("dirty", "")),
            "labkit.slurm_job": str((meta.get("slurm") or {}).get("job_id", "")),
            **{f"tag.{k}": str(v) for k, v in (meta.get("tags") or {}).items()},
        }
        run = client.create_run(exp_id, run_name=rid, start_time=_ms(meta.get("created")),
                                tags={k: v for k, v in tags.items() if v != ""})
        params = [Param(k, str(v)[:6000]) for k, v in flatten(cfg).items()]
        metrics = []
        mfile = rdir / "metrics.jsonl"
        if mfile.exists():
            for line in mfile.read_text().splitlines():
                if line.strip():
                    r = json.loads(line)
                    metrics.append(Metric(r["key"], float(r["value"]), int(r["time"] * 1000), int(r["step"] or 0)))
        client.log_batch(run.info.run_id, tags=[RunTag("labkit.synced", "1")])
        for i in range(0, len(params), 100):  # MLflow の 1 回あたり上限: params 100, metrics 1000
            client.log_batch(run.info.run_id, params=params[i:i + 100])
        for i in range(0, len(metrics), 1000):
            client.log_batch(run.info.run_id, metrics=metrics[i:i + 1000])
        for name in ("meta.json", "config.json"):
            if (rdir / name).exists():
                client.log_artifact(run.info.run_id, str(rdir / name))
        figs = rdir / "figures"
        if figs.is_dir():
            for f in sorted(figs.glob("*")):
                if f.suffix in {".png", ".pdf", ".json"}:
                    client.log_artifact(run.info.run_id, str(f), artifact_path="figures")
        status = {"finished": "FINISHED", "failed": "FAILED", "interrupted": "KILLED"}.get(meta["status"], "FINISHED")
        client.set_terminated(run.info.run_id, status=status, end_time=_ms(meta.get("finished")))
        n += 1
        progress(f"synced {rid}")
    progress(f"{n} 件を同期（{uri}）")
    return n


def ui(port: int = 5000, root: Path | None = None) -> None:
    root = root or find_root()
    uri, art = _setup(root)
    env = {**os.environ, **PRIVACY_ENV}
    cmd = [sys.executable, "-m", "mlflow", "ui", "--backend-store-uri", uri,
           "--default-artifact-root", art.as_uri(), "--host", "127.0.0.1", "--port", str(port)]
    print(f"http://127.0.0.1:{port} （Ctrl-C で終了。外部には公開されません）")
    subprocess.run(cmd, env=env, check=False)
