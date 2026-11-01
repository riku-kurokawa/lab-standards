"""図テンプレート。プロジェクトの図はすべてここに登録されたテンプレートで作る.

新しい図種が必要になったら、プロジェクト側で描画コードを書かずに、
lab-standards の labkit にテンプレートを追加する（skill: add-figure-template）。

各テンプレートは (spec: dict, ctx: Context) -> Figure。
spec は figspecs/*.toml の内容。共通キー:
    template, name, size, [data], [labels], [options]
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from labkit.viz.style import DIVERGING_CMAP, LINESTYLES, SEQUENTIAL_CMAP, figsize


@dataclass
class Template:
    name: str
    func: Callable
    required_data: list[str]
    description: str
    example: str = ""


REGISTRY: dict[str, Template] = {}


def template(name: str, required_data: list[str], description: str, example: str = ""):
    def deco(func):
        REGISTRY[name] = Template(name, func, required_data, description, example)
        return func

    return deco


@dataclass
class Context:
    load: Callable[[str], Any]  # data.file -> 読み込んだデータ
    metrics: Callable[[], list[dict]]  # run の metrics.jsonl


# ---------- 共通ヘルパ ----------
def _fig(spec, nrows=1, ncols=1, **kw):
    import matplotlib.pyplot as plt

    return plt.subplots(nrows, ncols, figsize=figsize(spec.get("size", "single")), **kw)


def _labels(ax, spec, default_x="", default_y=""):
    lab = spec.get("labels", {})
    ax.set_xlabel(lab.get("x", default_x))
    ax.set_ylabel(lab.get("y", default_y))
    if lab.get("title"):
        ax.set_title(lab["title"])


def _options(ax, spec):
    opt = spec.get("options", {})
    if "xlim" in opt:
        ax.set_xlim(*opt["xlim"])
    if "ylim" in opt:
        ax.set_ylim(*opt["ylim"])
    if opt.get("logx"):
        ax.set_xscale("log")
    if opt.get("logy"):
        ax.set_yscale("log")
    if opt.get("grid"):
        ax.grid(True, linewidth=0.3, alpha=0.5)


def _get(d: dict, key: str):
    node = d
    for part in key.split("/"):
        try:
            node = node[part]
        except KeyError:
            raise KeyError(f"{key}（ある名前: {sorted(node)}）") from None
    return np.asarray(node)


def _as_list(v) -> list:
    return v if isinstance(v, list) else [v]


def _legend(ax, spec, n):
    if n > 1 or spec.get("options", {}).get("legend"):
        ax.legend(loc=spec.get("options", {}).get("legend_loc", "best"))


# ---------- テンプレート ----------
@template(
    "timeseries",
    ["file", "x", "y"],
    "時系列（複数系列可）。HDF5 の x と y（配列名、/ で階層）を描く",
    'data = {file = "signal.h5", x = "t", y = ["x_raw", "x_filt"], legend = ["raw", "filtered"]}',
)
def timeseries(spec, ctx):
    d = spec["data"]
    data = ctx.load(d["file"])
    fig, ax = _fig(spec)
    x = _get(data, d["x"])
    ys = _as_list(d["y"])
    names = d.get("legend", ys)
    for i, (y, nm) in enumerate(zip(ys, names, strict=False)):
        ax.plot(x, _get(data, y), label=nm, linestyle=LINESTYLES[(i // 8) % 4])
    _labels(ax, spec, d["x"], ys[0] if len(ys) == 1 else "")
    _options(ax, spec)
    _legend(ax, spec, len(ys))
    return fig


@template(
    "spectrogram",
    ["file"],
    "スペクトログラム。f, t, S（パワー、S.shape = (len(f), len(t))）があればそれを描き、無ければ signal と fs から計算",
    'data = {file = "signal.h5", signal = "x", fs = 1000.0, nperseg = 256, db = true}',
)
def spectrogram(spec, ctx):
    from scipy import signal as sps

    d = spec["data"]
    data = ctx.load(d["file"])
    if all(k in data for k in ("f", "t", "S")):
        f, t, S = np.asarray(data["f"]), np.asarray(data["t"]), np.asarray(data["S"])
    else:
        x = _get(data, d["signal"])
        fs = float(d["fs"])
        f, t, S = sps.spectrogram(x, fs=fs, nperseg=int(d.get("nperseg", 256)))
    if d.get("db", True):
        S = 10 * np.log10(np.maximum(S, 1e-20))
    fig, ax = _fig(spec)
    m = ax.pcolormesh(t, f, S, shading="auto", cmap=SEQUENTIAL_CMAP, rasterized=True)
    cb = fig.colorbar(m, ax=ax)
    cb.set_label(spec.get("labels", {}).get("colorbar", "Power [dB]" if d.get("db", True) else "Power"))
    _labels(ax, spec, "Time [s]", "Frequency [Hz]")
    _options(ax, spec)
    return fig


@template(
    "psd",
    ["file"],
    "パワースペクトル密度（Welch）。f と P があればそれを、無ければ signal(s) と fs から計算",
    'data = {file = "signal.h5", signal = ["x_raw", "x_filt"], fs = 1000.0, nperseg = 1024}',
)
def psd(spec, ctx):
    from scipy import signal as sps

    d = spec["data"]
    data = ctx.load(d["file"])
    fig, ax = _fig(spec)
    if "f" in data and "P" in data:
        series = [("P", np.asarray(data["f"]), np.asarray(data["P"]))]
    else:
        series = []
        for s in _as_list(d["signal"]):
            f, P = sps.welch(_get(data, s), fs=float(d["fs"]), nperseg=int(d.get("nperseg", 1024)))
            series.append((s, f, P))
    names = d.get("legend", [s[0] for s in series])
    for (_, f, P), nm in zip(series, names, strict=False):
        ax.semilogy(f, P, label=nm)
    _labels(ax, spec, "Frequency [Hz]", "PSD [unit²/Hz]")
    _options(ax, spec)
    _legend(ax, spec, len(series))
    return fig


@template(
    "learning_curve",
    ["metrics"],
    "run の metrics.jsonl から指定キーを step に対して描く（学習曲線・収束履歴）",
    'data = {metrics = ["train_loss", "val_loss"]}',
)
def learning_curve(spec, ctx):
    d = spec["data"]
    rows = ctx.metrics()
    fig, ax = _fig(spec)
    keys = _as_list(d["metrics"])
    for k in keys:
        pts = [(r["step"], r["value"]) for r in rows if r["key"] == k and r["step"] is not None]
        if not pts:
            raise ValueError(f"metrics.jsonl に step 付きの {k!r} がありません")
        s, v = zip(*sorted(pts), strict=True)
        ax.plot(s, v, label=k)
    _labels(ax, spec, "Step", "Value")
    _options(ax, spec)
    _legend(ax, spec, len(keys))
    return fig


@template(
    "errorbar",
    ["file", "x", "y"],
    "条件比較（平均±誤差）。Parquet の x 列ごとに y を集計（err = sd | se | ci95）、hue で系列分け",
    'data = {file = "results.parquet", x = "method", y = "rmse", hue = "noise", err = "se"}',
)
def errorbar(spec, ctx):
    import pandas as pd

    d = spec["data"]
    df: pd.DataFrame = ctx.load(d["file"])
    err = d.get("err", "se")
    if err not in ("sd", "se", "ci95"):
        raise ValueError(f"errorbar: err は sd | se | ci95 のいずれか（{err!r}）")
    hue = d.get("hue")
    groups = [(None, df)] if not hue else list(df.groupby(hue, sort=True))
    cats = list(dict.fromkeys(df[d["x"]]))
    fig, ax = _fig(spec)
    width = 0.8 / max(len(groups), 1)
    for i, (h, g) in enumerate(groups):
        agg = g.groupby(d["x"])[d["y"]].agg(["mean", "std", "count"]).reindex(cats)
        se = agg["std"] / np.sqrt(agg["count"])
        e = {"sd": agg["std"], "se": se, "ci95": 1.96 * se}[err]
        pos = np.arange(len(cats)) + (i - (len(groups) - 1) / 2) * width
        ax.errorbar(pos, agg["mean"], yerr=e, fmt="o", capsize=2, label=None if h is None else str(h))
    ax.set_xticks(np.arange(len(cats)), [str(c) for c in cats])
    _labels(ax, spec, d["x"], f"{d['y']} (mean ± {err})")
    _options(ax, spec)
    _legend(ax, spec, len(groups))
    return fig


@template(
    "scatter",
    ["file", "x", "y"],
    "散布図。Parquet（列名）または HDF5（配列名）。hue（Parquet のみ）で色分け、identity で y=x 線",
    'data = {file = "pred.parquet", x = "true", y = "pred", hue = "split", identity = true}',
)
def scatter(spec, ctx):
    d = spec["data"]
    data = ctx.load(d["file"])
    fig, ax = _fig(spec)
    if hasattr(data, "columns"):
        groups = [(None, data)] if not d.get("hue") else list(data.groupby(d["hue"], sort=True))
        for h, g in groups:
            ax.scatter(g[d["x"]], g[d["y"]], s=4, alpha=0.7, label=None if h is None else str(h), edgecolors="none")
        n = len(groups)
        xs = np.asarray(data[d["x"]])
        ys = np.asarray(data[d["y"]])
    else:
        xs, ys = _get(data, d["x"]), _get(data, d["y"])
        ax.scatter(xs, ys, s=4, alpha=0.7, edgecolors="none")
        n = 1
    if d.get("identity"):
        lo, hi = float(np.nanmin([xs.min(), ys.min()])), float(np.nanmax([xs.max(), ys.max()]))
        ax.plot([lo, hi], [lo, hi], color="0.5", linewidth=0.6, linestyle="--")
    _labels(ax, spec, d["x"], d["y"])
    _options(ax, spec)
    _legend(ax, spec, n)
    return fig


@template(
    "heatmap",
    ["file", "z"],
    "2 次元配列のヒートマップ。z[i, j] は (x[i], y[j]) の値（shape = (len(x), len(y))。Julia の size と同じ）。"
    "x, y 省略時は添字 i が横軸、j が縦軸。diverging = true で 0 中心の発散カラーマップ",
    'data = {file = "field.h5", z = "u", x = "xgrid", y = "ygrid", diverging = false}',
)
def heatmap(spec, ctx):
    d = spec["data"]
    data = ctx.load(d["file"])
    z = _get(data, d["z"])
    if z.ndim != 2:
        raise ValueError(f"heatmap の z は 2 次元配列が必要です（shape={z.shape}）")
    fig, ax = _fig(spec)
    kw: dict[str, Any] = {"shading": "auto", "rasterized": True}
    if d.get("diverging"):
        lim = float(np.nanmax(np.abs(z)))
        kw.update(cmap=DIVERGING_CMAP, vmin=-lim, vmax=lim)
    else:
        kw.update(cmap=SEQUENTIAL_CMAP)
    # 規約: z[i, j] は (x[i], y[j]) の値。matplotlib は C[row=y, col=x] を期待するので転置して渡す（形は検査し、推測しない）
    if "x" in d and "y" in d:
        x, y = _get(data, d["x"]), _get(data, d["y"])
        if z.shape != (len(x), len(y)):
            raise ValueError(
                f"heatmap: z.shape={z.shape} は (len(x), len(y))=({len(x)}, {len(y)}) である必要があります"
                "（z[i, j] は (x[i], y[j]) の値）"
            )
        m = ax.pcolormesh(x, y, z.T, **kw)
    else:
        m = ax.pcolormesh(z.T, **kw)
    cb = fig.colorbar(m, ax=ax)
    cb.set_label(spec.get("labels", {}).get("colorbar", d["z"]))
    _labels(ax, spec, "x", "y")
    _options(ax, spec)
    return fig


@template(
    "histogram",
    ["file", "values"],
    "ヒストグラム（複数系列は重ね描き）。Parquet の列名または HDF5 の配列名",
    'data = {file = "results.parquet", values = ["err_a", "err_b"], bins = 50, density = true}',
)
def histogram(spec, ctx):
    d = spec["data"]
    data = ctx.load(d["file"])
    fig, ax = _fig(spec)
    vals = _as_list(d["values"])
    for v in vals:
        arr = np.asarray(data[v]) if hasattr(data, "columns") else _get(data, v)
        ax.hist(
            arr[np.isfinite(arr)], bins=d.get("bins", 50), density=d.get("density", False), histtype="step", label=v
        )
    _labels(ax, spec, vals[0] if len(vals) == 1 else "value", "density" if d.get("density") else "count")
    _options(ax, spec)
    _legend(ax, spec, len(vals))
    return fig
