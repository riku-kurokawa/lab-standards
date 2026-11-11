"""図の共通スタイル。ここ以外で rcParams を変更しない."""

from __future__ import annotations

# Okabe–Ito: 色覚多様性に配慮した 8 色
OKABE_ITO = [
    "#0072B2",
    "#E69F00",
    "#009E73",
    "#D55E00",
    "#CC79A7",
    "#56B4E9",
    "#F0E442",
    "#000000",
]
LINESTYLES = ["-", "--", ":", "-."]

# 論文の段組みに合わせた幅（inch）。高さは黄金比
GOLDEN = 0.618
SIZES = {
    "single": (3.5, 3.5 * GOLDEN),
    "onehalf": (5.5, 5.5 * GOLDEN),
    "double": (7.2, 7.2 * GOLDEN * 0.75),
    "square": (3.5, 3.5),
    "slide": (8.0, 4.5),
}

RC = {
    "font.size": 8,
    "axes.titlesize": 8,
    "axes.labelsize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 7,
    "legend.frameon": False,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.linewidth": 0.6,
    "lines.linewidth": 1.0,
    "lines.markersize": 3,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "xtick.direction": "out",
    "ytick.direction": "out",
    "axes.grid": False,
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
    "pdf.fonttype": 42,  # フォント埋め込み（投稿規定対策）
    "ps.fonttype": 42,
    "image.cmap": "viridis",
}

CJK_FONTS = ["Noto Sans CJK JP", "IPAexGothic", "Hiragino Sans", "Yu Gothic", "Meiryo", "MS Gothic", "Noto Sans JP"]

SEQUENTIAL_CMAP = "viridis"
DIVERGING_CMAP = "RdBu_r"


def figsize(size: str | list | tuple) -> tuple[float, float]:
    if isinstance(size, (list, tuple)):
        return float(size[0]), float(size[1])
    if size not in SIZES:
        raise ValueError(f"size は {list(SIZES)} か [幅, 高さ]: {size!r}")
    return SIZES[size]


# 文字の大きさ（pt）。paper は実寸で論文に載せる大きさ、slide は投影で読める大きさ。これより小さい文字は描かない（render が検査する）
FONTS = {
    "paper": {"base": 8, "tick": 7, "min": 6},
    "slide": {"base": 16, "tick": 14, "min": 12},
}


def fonts(kind: str) -> dict:
    if kind not in FONTS:
        raise ValueError(f"style は {list(FONTS)} のいずれか: {kind!r}")
    return FONTS[kind]


def apply(kind: str = "paper") -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from cycler import cycler

    plt.rcParams.update(RC)
    f = fonts(kind)
    plt.rcParams.update(
        {
            "font.size": f["base"],
            "axes.titlesize": f["base"],
            "axes.labelsize": f["base"],
            "xtick.labelsize": f["tick"],
            "ytick.labelsize": f["tick"],
            "legend.fontsize": f["tick"],
        }
    )
    if kind == "slide":
        plt.rcParams.update({"lines.linewidth": 2.0, "lines.markersize": 6, "axes.linewidth": 1.0})
    plt.rcParams["axes.prop_cycle"] = cycler(color=OKABE_ITO)
    # 日本語のラベル: 欧文はこれまでの書体のまま、無い字だけ手元にある日本語の書体で描く（どれも無ければ何もしない）
    from matplotlib import font_manager

    have = {f.name for f in font_manager.fontManager.ttflist}
    cjk = next((n for n in CJK_FONTS if n in have), None)
    plt.rcParams["font.family"] = ["sans-serif", cjk] if cjk else ["sans-serif"]
