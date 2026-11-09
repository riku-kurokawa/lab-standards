"""図の体裁の機械的な検査（render が保存の前に呼ぶ）: 文字どうしの重なり、凡例とデータの重なり、小さすぎる文字、はみ出し.

論文・発表の図として読めないものを保存させない（lab.toml の [fig] overlap = "error"）。検査は描画後の表示座標の外接矩形で行う。
"""

from __future__ import annotations

TOL_PX = 1.0  # 外接矩形がこれ以上重なったら重なりとみなす（表示の画素）


def _texts(fig):
    """描かれる文字だけ（目盛りは表示範囲の中のものだけ。findobj は範囲外の目盛りの文字も返す）."""
    out = list(fig.texts)
    if getattr(fig, "_suptitle", None) is not None:
        out.append(fig._suptitle)
    for ax in fig.axes:
        if not ax.get_visible():
            continue
        out += [ax.title, ax._left_title, ax._right_title, ax.xaxis.label, ax.yaxis.label, *ax.texts]
        out += [ax.xaxis.get_offset_text(), ax.yaxis.get_offset_text()]
        for axis in (ax.xaxis, ax.yaxis):
            for tick in axis._update_ticks():
                out += [tick.label1, tick.label2]
        leg = ax.get_legend()
        if leg is not None and leg.get_visible():
            out += list(leg.get_texts())
            if leg.get_title() is not None:
                out.append(leg.get_title())
    return [t for t in dict.fromkeys(out) if t is not None and t.get_visible() and t.get_text().strip()]


def _label(t) -> str:
    s = t.get_text().strip().replace("\n", " ")
    return s[:30]


def _overlap(a, b) -> bool:
    w = min(a.x1, b.x1) - max(a.x0, b.x0)
    h = min(a.y1, b.y1) - max(a.y0, b.y0)
    return w > TOL_PX and h > TOL_PX


def problems(fig, min_pt: float) -> list[str]:
    """重なり・小さい文字・はみ出しの一覧（空なら良い）."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    out: list[str] = []
    texts = _texts(fig)
    boxes = []
    for t in texts:
        try:
            bb = t.get_window_extent(renderer=r)
        except (RuntimeError, ValueError):
            continue
        if t.get_fontsize() < min_pt - 1e-6:
            out.append(f"文字が小さい（{t.get_fontsize():g} pt < {min_pt:g} pt）: '{_label(t)}'")
        boxes.append((t, bb))
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            (ta, a), (tb, b) = boxes[i], boxes[j]
            if _overlap(a, b):
                out.append(f"文字が重なっている: '{_label(ta)}' と '{_label(tb)}'")
    # 凡例がデータ（線・点）に重なる
    for ax in fig.axes:
        leg = ax.get_legend()
        if leg is None or not leg.get_visible():
            continue
        lb = leg.get_window_extent(renderer=r)
        hit = 0
        for line in ax.get_lines():
            xy = ax.transData.transform(line.get_xydata()) if len(line.get_xydata()) else []
            hit += sum(1 for x, y in xy if lb.x0 < x < lb.x1 and lb.y0 < y < lb.y1)
        for coll in ax.collections:
            offs = coll.get_offsets()
            if len(offs) and coll.get_transform() is not None:
                xy = coll.get_offset_transform().transform(offs)
                hit += sum(1 for x, y in xy if lb.x0 < x < lb.x1 and lb.y0 < y < lb.y1)
        if hit:
            out.append(f'凡例がデータ点 {hit} 個に重なっている（options.legend_loc = "outside" か別の位置に）')
    return list(dict.fromkeys(out))
