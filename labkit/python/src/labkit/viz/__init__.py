"""図の生成。プロジェクトから使う入口は render()（CLI: labkit fig）だけ.

    labkit fig figspecs/raw_signal.toml --run <run_id>

出力: runs/<run_id>/figures/<name>.pdf, <name>.png, <name>.figmeta.json（来歴: spec、使ったデータの sha256、commit）
"""

from __future__ import annotations

import json
from pathlib import Path

from labkit._util import git_info, now_iso, rel_or_abs, sha256_file, write_json_atomic
from labkit._version import __version__
from labkit.config import find_root, read_toml
from labkit.viz.templates import REGISTRY, Context

COMMON_KEYS = {
    "template",
    "name",
    "size",
    "data",
    "labels",
    "options",
    "description",
    "layout",
    "panel",
    "style",
    "share",
    "clim",
}
SHARE = {"x": ("all", False), "y": (False, "all"), "both": ("all", "all")}


def _validate(spec: dict, where: str) -> None:
    tpl = REGISTRY.get(spec.get("template"))
    if tpl is None:
        raise ValueError(f"{where}: template は {sorted(REGISTRY)} のいずれか（{spec.get('template')!r}）")
    missing = [k for k in tpl.required_data if k not in spec.get("data", {})]
    if missing:
        raise ValueError(f"{where}: [data] に {missing} が必要です。例: {tpl.example}")


def load_spec(path: str | Path) -> dict:
    spec = read_toml(path)
    if unknown := set(spec) - COMMON_KEYS:
        raise ValueError(f"{path}: 未知のキー {sorted(unknown)}（使えるのは {sorted(COMMON_KEYS)}）")
    _validate(spec, str(path))
    if spec["template"] == "panels":
        if not spec.get("panel"):
            raise ValueError(f"{path}: panels には [[panel]] が 1 つ以上必要です")
        for i, p in enumerate(spec["panel"]):
            if p.get("template") == "panels":
                raise ValueError(f"{path}: panel の入れ子はできません")
            _validate(p, f"{path} panel[{i}]")
    if spec.get("share", "x") not in SHARE:
        raise ValueError(f"{path}: share は {sorted(SHARE)} のいずれか")
    if "clim" in spec and spec["clim"] != "shared":
        raise ValueError(f'{path}: clim は "shared" だけ（各パネルの範囲は options.clim = [下, 上]）')
    spec.setdefault("name", Path(path).stem)
    return spec


def _shared_clim(spec: dict, ctx) -> None:
    """panels の clim = "shared": ヒートマップのパネルの色の範囲を全パネルの最小・最大（diverging は絶対値の最大）にそろえる."""
    import numpy as np

    from labkit.viz.templates import _get

    hm = [p for p in spec["panel"] if p["template"] == "heatmap" and "clim" not in p.get("options", {})]
    if not hm:
        return
    zs = [np.asarray(_get(ctx.load(p["data"]["file"]), p["data"]["z"]), dtype=float) for p in hm]
    for kind in (True, False):
        group = [(p, z) for p, z in zip(hm, zs, strict=True) if bool(p["data"].get("diverging")) is kind]
        if not group:
            continue
        if kind:
            lim = max(float(np.nanmax(np.abs(z))) for _, z in group)
            clim = [-lim, lim]
        else:
            clim = [min(float(np.nanmin(z)) for _, z in group), max(float(np.nanmax(z)) for _, z in group)]
        for p, _ in group:
            p.setdefault("options", {})["clim"] = clim


def render(spec_path: str | Path, run_id: str | None = None, out_dir: str | Path | None = None) -> list[Path]:
    from labkit import io
    from labkit.paths import datapath
    from labkit.runs import find_run
    from labkit.viz import style

    root = find_root()
    spec = load_spec(spec_path)
    run_dir = find_run(run_id, root) if run_id else None
    out = Path(out_dir) if out_dir else (run_dir / "figures" if run_dir else root / "scratch" / "figures")
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

    from labkit.config import load_lab
    from labkit.viz import layout

    kind = spec.get("style", "paper")
    style.apply(kind)
    import matplotlib.pyplot as plt

    ctx = Context(load=load, metrics=metrics)
    if spec["template"] == "panels":
        rows, cols = spec.get("layout", [1, len(spec["panel"])])
        sx, sy = SHARE[spec["share"]] if "share" in spec else (False, False)
        fig, axes = plt.subplots(
            rows,
            cols,
            figsize=style.figsize(spec.get("size", "double")),
            squeeze=False,
            sharex=sx,
            sharey=sy,
            layout="constrained",
        )
        parts = list(zip(spec["panel"], axes.ravel(), strict=False))
        for ax in axes.ravel()[len(spec["panel"]) :]:
            ax.set_visible(False)
        if spec.get("clim") == "shared":
            _shared_clim(spec, ctx)
    else:
        fig, ax = plt.subplots(figsize=style.figsize(spec.get("size", "single")), layout="constrained")
        parts = [(spec, ax)]
    try:
        for i, (sub, ax) in enumerate(parts):
            REGISTRY[sub["template"]].func(sub, ctx, ax)
            if len(parts) > 1:  # 見出しは左に (a) と題の 1 つだけ（中央の題と二重にしない）
                ax.set_title("")
                ax.set_title(f"({chr(97 + i)}) {sub.get('labels', {}).get('title', '')}".strip(), loc="left")
        if spec["template"] == "panels" and spec.get("share") in SHARE:
            for ax in axes.ravel():  # そろえた軸の内側の目盛りの文字と軸名は外側の 1 つだけ
                if ax.get_visible():
                    ax.label_outer()
    except KeyError as e:  # [data] のキー、配列名、列名の打ち間違い
        raise ValueError(
            f"{spec_path}: '{e.args[0] if e.args else e}' がありません（[data] の指定、またはデータの配列名・列名を確認）"
        ) from e
    name = spec["name"]
    issues = layout.problems(fig, style.fonts(kind)["min"])
    if issues:
        mode = load_lab(root).get("fig", {}).get("overlap", "warn")
        msg = f"{spec_path}: 図の体裁の問題 {len(issues)} 件:\n  " + "\n  ".join(issues)
        if mode == "error":
            plt.close(fig)
            raise ValueError(
                msg + '\n（size を大きく、ラベルを短く、legend_loc を変える。lab.toml の [fig] overlap = "error"）'
            )
        import sys

        print(msg, file=sys.stderr)
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
            "git": git_info(root),
            "data": [{"path": rel_or_abs(p, root), "sha256": sha256_file(p)} for p in dict.fromkeys(used)],
            "created": now_iso(),
            "labkit_version": __version__,
            "layout_issues": issues,
        },
    )
    return paths


def list_templates() -> str:
    return "\n".join(
        f"{t.name:15s} {t.description}\n{'':15s} 必須 data: {t.required_data}\n{'':15s} 例: {t.example}"
        for t in REGISTRY.values()
    )
