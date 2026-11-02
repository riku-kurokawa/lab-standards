"""図テンプレート。プロジェクトの図はすべてここに登録されたテンプレートで作る.

各テンプレートは (spec: dict, ctx: Context, ax) -> None で、渡された軸に描く。figspec の共通キー:
    template, name, size, description, [data], [labels], [options]
複数パネルは template = "panels" と [[panel]]（各パネルに template / data / labels / options）。
新しい図種が必要なら lab-standards にテンプレートを追加する（skill: add-figure-template）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from labkit.viz.style import DIVERGING_CMAP, LINESTYLES, SEQUENTIAL_CMAP


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
    if opt.get("aspect"):
        ax.set_aspect(opt["aspect"])


def _get(d: dict, key: str):
    node = d
    for part in key.split("/"):
        try:
            node = node[part]
        except KeyError:
            raise KeyError(f"{key}（ある名前: {sorted(node)}）") from None
    return np.asarray(node)


def _col(data, key: str):
    """Parquet（列名）でも HDF5（配列名）でも 1 次元配列を返す."""
    return np.asarray(data[key]) if hasattr(data, "columns") else _get(data, key)


def _as_list(v) -> list:
    return v if isinstance(v, list) else [v]


def _legend(ax, spec, n):
    opt = spec.get("options", {})
    if n > 1 or opt.get("legend"):
        ax.legend(loc=opt.get("legend_loc", "best"))


def _groups(df, hue):
    return [(None, df)] if not hue else list(df.groupby(hue, sort=True))


def _colorbar(ax, m, spec, default):
    cb = ax.figure.colorbar(m, ax=ax)
    cb.set_label(spec.get("labels", {}).get("colorbar", default))


# ---------- テンプレート ----------
@template(
    "timeseries",
    ["file", "x", "y"],
    "時系列（複数系列可）。HDF5 の x と y（配列名、/ で階層）を描く",
    'data = {file = "signal.h5", x = "t", y = ["x_raw", "x_filt"], legend = ["raw", "filtered"]}',
)
def timeseries(spec, ctx, ax):
    d = spec["data"]
    data = ctx.load(d["file"])
    x = _col(data, d["x"])
    ys = _as_list(d["y"])
    for i, (y, nm) in enumerate(zip(ys, d.get("legend", ys), strict=False)):
        ax.plot(x, _col(data, y), label=nm, linestyle=LINESTYLES[(i // 8) % 4])
    _labels(ax, spec, d["x"], ys[0] if len(ys) == 1 else "")
    _options(ax, spec)
    _legend(ax, spec, len(ys))


@template(
    "band",
    ["file", "x", "y"],
    "平均線と帯（y ± err、または lo〜hi）。複数系列可。学習曲線の seed 平均や信頼区間に",
    'data = {file = "curves.h5", x = "epoch", y = ["mean_a", "mean_b"], err = ["sd_a", "sd_b"]}',
)
def band(spec, ctx, ax):
    d = spec["data"]
    data = ctx.load(d["file"])
    x = _col(data, d["x"])
    ys, errs = _as_list(d["y"]), _as_list(d.get("err", []))
    los, his = _as_list(d.get("lo", [])), _as_list(d.get("hi", []))
    for i, (y, nm) in enumerate(zip(ys, d.get("legend", ys), strict=False)):
        yv = _col(data, y)
        (line,) = ax.plot(x, yv, label=nm)
        if i < len(errs):
            e = _col(data, errs[i])
            lo, hi = yv - e, yv + e
        elif i < len(los):
            lo, hi = _col(data, los[i]), _col(data, his[i])
        else:
            continue
        ax.fill_between(x, lo, hi, color=line.get_color(), alpha=0.2, linewidth=0)
    _labels(ax, spec, d["x"], ys[0] if len(ys) == 1 else "")
    _options(ax, spec)
    _legend(ax, spec, len(ys))


@template(
    "spectrogram",
    ["file"],
    "スペクトログラム。f, t, S（パワー、S.shape = (len(f), len(t))）があればそれを描き、無ければ signal と fs から計算",
    'data = {file = "signal.h5", signal = "x", fs = 1000.0, nperseg = 256, db = true}',
)
def spectrogram(spec, ctx, ax):
    from scipy import signal as sps

    d = spec["data"]
    data = ctx.load(d["file"])
    if all(k in data for k in ("f", "t", "S")):
        f, t, S = np.asarray(data["f"]), np.asarray(data["t"]), np.asarray(data["S"])
    else:
        f, t, S = sps.spectrogram(_get(data, d["signal"]), fs=float(d["fs"]), nperseg=int(d.get("nperseg", 256)))
    db = d.get("db", True)
    if db:
        S = 10 * np.log10(np.maximum(S, 1e-20))
    m = ax.pcolormesh(t, f, S, shading="auto", cmap=SEQUENTIAL_CMAP, rasterized=True)
    _colorbar(ax, m, spec, "Power [dB]" if db else "Power")
    _labels(ax, spec, "Time [s]", "Frequency [Hz]")
    _options(ax, spec)


@template(
    "psd",
    ["file"],
    "パワースペクトル密度（Welch）。f と P があればそれを、無ければ signal(s) と fs から計算",
    'data = {file = "signal.h5", signal = ["x_raw", "x_filt"], fs = 1000.0, nperseg = 1024}',
)
def psd(spec, ctx, ax):
    from scipy import signal as sps

    d = spec["data"]
    data = ctx.load(d["file"])
    if "f" in data and "P" in data:
        series = [("P", np.asarray(data["f"]), np.asarray(data["P"]))]
    else:
        series = [
            (s, *sps.welch(_get(data, s), fs=float(d["fs"]), nperseg=int(d.get("nperseg", 1024))))
            for s in _as_list(d["signal"])
        ]
    for (_, f, P), nm in zip(series, d.get("legend", [s[0] for s in series]), strict=False):
        ax.semilogy(f, P, label=nm)
    _labels(ax, spec, "Frequency [Hz]", "PSD [unit²/Hz]")
    _options(ax, spec)
    _legend(ax, spec, len(series))


@template(
    "learning_curve",
    ["metrics"],
    "run の metrics.jsonl から指定キーを step に対して描く（学習曲線・収束履歴）",
    'data = {metrics = ["train_loss", "val_loss"]}',
)
def learning_curve(spec, ctx, ax):
    rows = ctx.metrics()
    keys = _as_list(spec["data"]["metrics"])
    for k in keys:
        pts = [(r["step"], r["value"]) for r in rows if r["key"] == k and r["step"] is not None]
        if not pts:
            raise ValueError(f"metrics.jsonl に step 付きの {k!r} がありません")
        s, v = zip(*sorted(pts), strict=True)
        ax.plot(s, v, label=k)
    _labels(ax, spec, "Step", "Value")
    _options(ax, spec)
    _legend(ax, spec, len(keys))


def _agg(df, x, y, err):
    agg = df.groupby(x, sort=False)[y].agg(["mean", "std", "count"])
    se = agg["std"] / np.sqrt(agg["count"])
    return agg["mean"], {"sd": agg["std"], "se": se, "ci95": 1.96 * se}[err]


@template(
    "errorbar",
    ["file", "x", "y"],
    "条件比較（平均±誤差）。Parquet の x 列ごとに y を集計（err = sd | se | ci95）、hue で系列分け。"
    'x が数値なら xmode = "numeric"（log 軸可）',
    'data = {file = "results.parquet", x = "method", y = "rmse", hue = "noise", err = "se"}',
)
def errorbar(spec, ctx, ax):
    d = spec["data"]
    df = ctx.load(d["file"])
    err = d.get("err", "se")
    if err not in ("sd", "se", "ci95"):
        raise ValueError(f"errorbar: err は sd | se | ci95 のいずれか（{err!r}）")
    groups = _groups(df, d.get("hue"))
    numeric = d.get("xmode") == "numeric"
    cats = sorted(dict.fromkeys(df[d["x"]])) if numeric else list(dict.fromkeys(df[d["x"]]))
    width = 0.8 / max(len(groups), 1)
    for i, (h, g) in enumerate(groups):
        mean, e = _agg(g, d["x"], d["y"], err)
        mean, e = mean.reindex(cats), e.reindex(cats)
        pos = np.asarray(cats, dtype=float) if numeric else np.arange(len(cats)) + (i - (len(groups) - 1) / 2) * width
        ax.errorbar(pos, mean, yerr=e, fmt="o-" if numeric else "o", capsize=2, label=None if h is None else str(h))
    if not numeric:
        ax.set_xticks(np.arange(len(cats)), [str(c) for c in cats])
    _labels(ax, spec, d["x"], f"{d['y']} (mean ± {err})")
    _options(ax, spec)
    _legend(ax, spec, len(groups))


@template(
    "bar",
    ["file", "x", "y"],
    "棒グラフ（Parquet: x 列ごとの y の平均。hue で並べる。err = sd | se | ci95 | none）",
    'data = {file = "results.parquet", x = "method", y = "time_s", hue = "device", err = "sd"}',
)
def bar(spec, ctx, ax):
    d = spec["data"]
    df = ctx.load(d["file"])
    err = d.get("err", "none")
    groups = _groups(df, d.get("hue"))
    cats = list(dict.fromkeys(df[d["x"]]))
    width = 0.8 / max(len(groups), 1)
    for i, (h, g) in enumerate(groups):
        mean, e = _agg(g, d["x"], d["y"], err if err != "none" else "sd")
        pos = np.arange(len(cats)) + (i - (len(groups) - 1) / 2) * width
        ax.bar(
            pos,
            mean.reindex(cats),
            width=width * 0.9,
            yerr=None if err == "none" else e.reindex(cats),
            capsize=2,
            label=None if h is None else str(h),
        )
    ax.set_xticks(np.arange(len(cats)), [str(c) for c in cats])
    _labels(ax, spec, d["x"], d["y"])
    _options(ax, spec)
    _legend(ax, spec, len(groups))


@template(
    "scatter",
    ["file", "x", "y"],
    "散布図。Parquet（列名）または HDF5（配列名）。hue（Parquet のみ）で色分け、identity で y=x 線",
    'data = {file = "pred.parquet", x = "true", y = "pred", hue = "split", identity = true}',
)
def scatter(spec, ctx, ax):
    d = spec["data"]
    data = ctx.load(d["file"])
    groups = _groups(data, d.get("hue")) if hasattr(data, "columns") else [(None, data)]
    for h, g in groups:
        ax.scatter(
            _col(g, d["x"]), _col(g, d["y"]), s=4, alpha=0.7, label=None if h is None else str(h), edgecolors="none"
        )
    if d.get("identity"):
        xs, ys = _col(data, d["x"]), _col(data, d["y"])
        lo, hi = float(np.nanmin([xs.min(), ys.min()])), float(np.nanmax([xs.max(), ys.max()]))
        ax.plot([lo, hi], [lo, hi], color="0.5", linewidth=0.6, linestyle="--")
    _labels(ax, spec, d["x"], d["y"])
    _options(ax, spec)
    _legend(ax, spec, len(groups))


@template(
    "heatmap",
    ["file", "z"],
    "2 次元配列のヒートマップ。z[i, j] は (x[i], y[j]) の値（shape = (len(x), len(y))）。"
    "x, y 省略時は添字 i が横軸、j が縦軸。diverging = true で 0 中心の発散カラーマップ",
    'data = {file = "field.h5", z = "u", x = "xgrid", y = "ygrid", diverging = false}',
)
def heatmap(spec, ctx, ax):
    d = spec["data"]
    data = ctx.load(d["file"])
    z = _get(data, d["z"])
    if z.ndim != 2:
        raise ValueError(f"heatmap の z は 2 次元配列が必要です（shape={z.shape}）")
    kw: dict[str, Any] = {"shading": "auto", "rasterized": True}
    if d.get("diverging"):
        lim = float(np.nanmax(np.abs(z)))
        kw.update(cmap=DIVERGING_CMAP, vmin=-lim, vmax=lim)
    else:
        kw.update(cmap=SEQUENTIAL_CMAP)
    if "x" in d and "y" in d:  # 規約 z[i, j] = (x[i], y[j])。matplotlib は C[row=y, col=x] なので転置（形は検査する）
        x, y = _get(data, d["x"]), _get(data, d["y"])
        if z.shape != (len(x), len(y)):
            raise ValueError(
                f"heatmap: z.shape={z.shape} は (len(x), len(y))=({len(x)}, {len(y)}) である必要があります"
            )
        m = ax.pcolormesh(x, y, z.T, **kw)
    else:
        m = ax.pcolormesh(z.T, **kw)
    _colorbar(ax, m, spec, d["z"])
    _labels(ax, spec, "x", "y")
    _options(ax, spec)


@template(
    "histogram",
    ["file", "values"],
    "ヒストグラム（複数系列は重ね描き）。Parquet の列名または HDF5 の配列名",
    'data = {file = "results.parquet", values = ["err_a", "err_b"], bins = 50, density = true}',
)
def histogram(spec, ctx, ax):
    d = spec["data"]
    data = ctx.load(d["file"])
    vals = _as_list(d["values"])
    for v in vals:
        arr = _col(data, v)
        ax.hist(
            arr[np.isfinite(arr)], bins=d.get("bins", 50), density=d.get("density", False), histtype="step", label=v
        )
    _labels(ax, spec, vals[0] if len(vals) == 1 else "value", "density" if d.get("density") else "count")
    _options(ax, spec)
    _legend(ax, spec, len(vals))


@template(
    "panels",
    [],
    "複数パネル。layout = [行, 列]、[[panel]] に各パネルの template / data / labels / options（(a)(b)… の見出しを付ける）",
    'layout = [1, 2]\n[[panel]]\ntemplate = "timeseries"\ndata = {file = "s.h5", x = "t", y = "x"}\n[[panel]]\ntemplate = "psd"\ndata = {file = "s.h5", signal = "x", fs = 1000.0}',
)
def panels(spec, ctx, ax):
    raise RuntimeError("panels は render() が直接扱う")
