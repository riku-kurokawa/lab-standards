"""図の生成。プロジェクトから使う入口は render()（CLI: labkit fig）だけ.

    labkit fig figspecs/raw_signal.toml --run <run_id>

出力: runs/<run_id>/figures/<name>.pdf, <name>.png, <name>.figmeta.json（来歴）
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from labkit._util import now_iso, rel_or_abs, sha256_file, write_json_atomic
from labkit._version import __version__
from labkit.config import find_root
from labkit.viz.templates import REGISTRY, Context

COMMON_KEYS = {"template", "name", "size", "data", "labels", "options", "description"}


def load_spec(path: str | Path) -> dict:
    with open(path, "rb") as f:
        spec = tomllib.load(f)
    unknown = set(spec) - COMMON_KEYS
    if unknown:
        raise ValueError(f"{path}: 未知のキー {sorted(unknown)}（使えるのは {sorted(COMMON_KEYS)}）")
    if spec.get("template") not in REGISTRY:
        raise ValueError(f"{path}: template は {sorted(REGISTRY)} のいずれか（{spec.get('template')!r}）")
    tpl = REGISTRY[spec["template"]]
    missing = [k for k in tpl.required_data if k not in spec.get("data", {})]
    if missing:
        raise ValueError(f"{path}: [data] に {missing} が必要です。例: {tpl.example}")
    spec.setdefault("name", Path(path).stem)
    return spec


def render(spec_path: str | Path, run_id: str | None = None, out_dir: str | Path | None = None) -> list[Path]:
    from labkit import io
    from labkit.paths import datapath
    from labkit.runs import find_run
    from labkit.viz import style

    root = find_root()
    spec = load_spec(spec_path)
    run_dir = find_run(run_id, root) if run_id else None
    if run_dir is None and out_dir is None:
        out = root / "scratch" / "figures"
    else:
        out = Path(out_dir) if out_dir else run_dir / "figures"
    out.mkdir(parents=True, exist_ok=True)

    used: list[Path] = []

    def resolve(ref: str) -> Path:
        if ref.startswith("data:"):
            stage, _, rest = ref[5:].partition("/")
            return datapath(stage, rest, root=root)
        p = Path(ref)
        if p.is_absolute():
            raise ValueError("figspec に絶対パスは書けません。run 内の相対パスか data:<stage>/... を使う")
        if run_dir is None:
            raise ValueError(f"{ref} は run 内の相対パスです。--run を指定してください")
        return run_dir / p

    def load(ref: str):
        p = resolve(ref)
        used.append(p)
        return io.load(p)

    def metrics() -> list[dict]:
        if run_dir is None:
            raise ValueError("learning_curve には --run が必要です")
        mf = run_dir / "metrics.jsonl"
        used.append(mf)
        return [json.loads(line) for line in mf.read_text(encoding="utf-8").splitlines() if line.strip()]

    style.apply()
    import matplotlib.pyplot as plt

    fig = REGISTRY[spec["template"]].func(spec, Context(load=load, metrics=metrics))
    name = spec["name"]
    paths = []
    for ext in ("pdf", "png"):
        p = out / f"{name}.{ext}"
        tmp = out / f".{name}.tmp.{ext}"
        fig.savefig(tmp, format=ext, metadata={"Creator": f"labkit {__version__}"} if ext == "pdf" else None)
        tmp.replace(p)
        paths.append(p)
    plt.close(fig)
    write_json_atomic(
        out / f"{name}.figmeta.json",
        {
            "template": spec["template"],
            "spec_file": rel_or_abs(Path(spec_path), root),
            "spec": spec,
            "run_id": run_dir.name if run_dir else None,
            "data": [{"path": rel_or_abs(p, root), "sha256": sha256_file(p)} for p in dict.fromkeys(used)],
            "created": now_iso(),
            "labkit_version": __version__,
        },
    )
    return paths


def list_templates() -> str:
    lines = []
    for t in REGISTRY.values():
        lines.append(f"{t.name:15s} {t.description}\n{'':15s} 必須 data: {t.required_data}\n{'':15s} 例: {t.example}")
    return "\n".join(lines)
