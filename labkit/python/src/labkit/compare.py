"""比較は 1 軸だけを変える（ceteris paribus）。腕の条件は設定から導出し、機械が凍結した設定で確かめる.

    # configs/experiments/design.toml（run の前に書き、config.json に凍結される）
    [compare.design]
    vary = "method"                  # 変える軸はちょうど 1 つ
    keys = ["gain_db"]               # この比較の指標（1 つの指標は 1 つの比較だけに属す）
    better = "max"                   # 指標の良い向き（掃引の direction はこれと同じ）
    objective = "focus"              # capability を使うときに必要
    levels = ["ours", "flat"]        # 軸の値の宣言（任意。軸の値は腕の名前かこの値。1 語）
    [compare.design.common]          # 全腕で同一の条件（lab.toml の [compare] required をすべて含む。n/a・未定などは空とみなす）
    dof = "PA"
    quant_bits = 8
    [compare.design.arms.ours]
    method = "ours"                  # 腕の表に書けるのは vary と、その腕の掃引の param だけ
    [compare.design.arms.flat]
    method = "flat"
    [[compare.design.sweep]]         # 自由パラメータの掃引。1 腕でも調整するなら対象外でない全腕を同じ総試行数で調整する
    arm = "flat"
    param = "height_mm"
    values = [10, 20, 30]
    metric = "gain_db_flat_h{value}" # 比較の指標（keys の 1 つ）を含む名前。値ごとに run が log_metric する
    direction = "max"                # = better
    [[compare.design.sweep]]
    arm = "ours"
    param = "lr"
    values = [0.01, 0.1, 1.0]
    metric = "gain_db_ours_lr{value}"
    direction = "max"
    [compare.design.capability]      # 著者の宣言（lab.toml の [compare.capability] があればそれが優先し、食い違えば拒否）
    gs = ["focus_only"]
    [report]
    noncomparative = ["snr_*"]       # 比較ではない指標（glob。2 文字以上の固定の接頭辞。腕の名前・比較の指標・比べる語を含まない）

entry は `arm_conditions(cfg, "design")` で腕の条件を同じ表から読み、掃引の後 `chosen(run, "design")` で最良の値を得る。
設定の [compare] の外に腕の名前を含む鍵（`[solver.ours]`・`ours_lr`）は置けない（腕ごとの条件は掃引か、存在しない）。

Run は開始前に設定を検査し（合わなければ run を作らない）、config.json の hash を meta.config_sha256 に残す。終了時に、設定が
途中で変わっていない（メモリ上の設定と config.json の hash）ことを確かめてから 1 回だけ comparisons.json を書く（掃引のスコアは run の
metrics から読む）。合わない・2 回目の記録・running でない記録は run を failed にする。check L027 は凍結した config.json と
metrics.json（meta の outputs と config_sha256 の hash を照合）から比較を計算し直し、記録の matched を信用しない。

脅威モデル: 防ぐのは、善意だが雑な、あるいは近道をする著者・エージェント（ワイルドカード・脇の指標・腕ごとの表・文字列に束ねた軸・
調整の不均等・古いか途中で変えた設定・文章の中の実験間の数値）による **偶然の・都合のよい不一致が引用できてしまうこと**。
完了した run のファイルを意図して偽造すること（chmod して meta・metrics を書き換える、kill してから偽造する）は手元のファイルの
照合だけでは防ぎきれない。安価な緩和（開始時の config の hash、`runs mark finished` が比較の run を拒否し同じ検査をやり直す）だけを入れ、
残る危険は docs/harness.md に明記する.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from labkit._util import _json_default, read_json, sha256_file, write_json_atomic

COMPARISON_FILE = "comparisons.json"
_FIELDS = {"vary", "keys", "objective", "better", "levels", "common", "arms", "sweep", "capability"}
_SWEEP_FIELDS = {"arm", "param", "values", "metric", "direction"}
_LABELS = (
    "prediction",
    "pass",
    "report",
    "name",
    "serves",
)  # 実験間の照合で比べない宣言とラベル（compare.<名>.keys も）
_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
_SEP_RE = re.compile(r"[\s+/,;:|&=]")  # 軸の値に複数の条件を束ねる区切り
_TOK_RE = re.compile(r"[\s_.\-/{}+,;:=*?!|&\[\]()]+")
_PLACEHOLDERS = {"n/a", "na", "none", "null", "-", "--", "tbd", "todo", "unknown", "?", "??", "未定", "不明"}
_COMPARATIVE = {"vs", "versus", "minus", "over", "speedup", "beats", "wins"}  # 非比較の指標に置けない比べる語


class ConditionMismatch(ValueError):
    """比較の条件がそろっていない（ceteris paribus）."""


def _norm(v: Any) -> Any:
    """正準化: numpy は Python の値に、整数値の浮動小数は整数に（TOML の 1 と 1.0 を同じ条件とみなす）."""
    v = json.loads(json.dumps(v, default=_json_default))

    def walk(x):
        if isinstance(x, float) and x.is_integer():
            return int(x)
        if isinstance(x, dict):
            return {k: walk(y) for k, y in x.items()}
        if isinstance(x, list):
            return [walk(y) for y in x]
        return x

    return walk(v)


def canonical(v: Any) -> str:
    return json.dumps(_norm(v), sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _empty(v: Any) -> bool:
    """空・プレースホルダ（n/a・none・null・-・tbd・unknown・?・未定 など）。表と配列は中身がすべて空なら空."""
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip().lower() in _PLACEHOLDERS or not v.strip()
    if isinstance(v, list):
        return all(_empty(x) for x in v)
    if isinstance(v, dict):
        return all(_empty(x) for x in v.values())
    return False


def _tokens(s: Any) -> list[str]:
    return [t for t in _TOK_RE.split(str(s).lower()) if t]


def _has(hay: list[str], needle: list[str]) -> bool:
    """needle の語の並びが hay に連続して現れる."""
    n = len(needle)
    return bool(n) and any(hay[i : i + n] == needle for i in range(len(hay) - n + 1))


def noncomparative(cfg: dict) -> list[str] | None:
    """[report] noncomparative（glob の配列）。形が違えば None."""
    r = cfg.get("report")
    v = r.get("noncomparative", []) if isinstance(r, dict) else []
    return v if isinstance(v, list) and all(isinstance(p, str) for p in v) else None


def _sweeps(c: dict) -> list:
    s = c.get("sweep")
    return [] if s is None else [s] if isinstance(s, dict) else s if isinstance(s, list) else [s]


def _comparisons(cfg: dict) -> dict[str, dict]:
    comp = cfg.get("compare")
    return {n: c for n, c in comp.items() if isinstance(c, dict)} if isinstance(comp, dict) else {}


def arm_labels(cfg: dict) -> dict[str, list[str]]:
    """腕を名指す語の並び {説明: 語}: 腕の名前、腕の軸の値、levels のすべての値（a/b という腕が method="proposed" を持つなら proposed も）."""
    out: dict[str, list[str]] = {}
    for n, c in _comparisons(cfg).items():
        arms = c.get("arms") if isinstance(c.get("arms"), dict) else {}
        for a, t in arms.items():
            out[f"腕 {a!r}（{n}）"] = _tokens(a)
            v = t.get(c.get("vary")) if isinstance(t, dict) and isinstance(c.get("vary"), str) else None
            if isinstance(v, str | int | float | bool) and _tokens(v):
                out.setdefault(f"軸の値 {v!r}（{n}）", _tokens(v))
        for v in c.get("levels") if isinstance(c.get("levels"), list) else []:
            if isinstance(v, str | int | float | bool) and _tokens(v):
                out.setdefault(f"軸の値 {v!r}（{n}）", _tokens(v))
    return out


def strip_arms(key: str, labels: list[list[str]]) -> str:
    """key から腕を名指す語（arm_labels の語の並び）を除いた残り（gain_ours と gain_flat は同じ gain）."""
    toks = _tokens(key)
    for t in sorted(labels, key=len, reverse=True):
        i = 0
        while t and i + len(t) <= len(toks):
            if toks[i : i + len(t)] == t:
                del toks[i : i + len(t)]
            else:
                i += 1
    return "_".join(toks)


def _names(cfg: dict) -> dict[str, list[str]]:
    """非比較の指標・設定の鍵に現れてはいけない語の並び {説明: 語}: 腕を名指す語（arm_labels）と、比較の指標の語幹（最後の語を除く）."""
    out = arm_labels(cfg)
    for n, c in _comparisons(cfg).items():
        for k in c.get("keys") if isinstance(c.get("keys"), list) else []:
            t = _tokens(k)
            out[f"比較 {n} の指標 {k!r} の語幹"] = t[:-1] if len(t) > 1 else t
    return out


def _named(key: str, names: dict[str, list[str]]) -> str:
    """key が腕の名前・比較の指標の語幹・比べる語を含むなら、その説明."""
    toks = _tokens(key)
    if hit := next((label for label, t in names.items() if _has(toks, t)), ""):
        return hit
    return f"比べる語 {sorted(set(toks) & _COMPARATIVE)}" if set(toks) & _COMPARATIVE else ""


def _nc_problems(nc: list[str], names: dict[str, list[str]]) -> list[str]:
    out = []
    for p in nc:
        if any(ch in p for ch in "*?[") and len(re.split(r"[*?\[]", p, maxsplit=1)[0]) < 2:
            out.append(
                f"[report] noncomparative {p!r} は広すぎる（ワイルドカードの前に 2 文字以上の固定の接頭辞が要る）"
            )
        if hit := _named(re.sub(r"\[[^\]]*\]", " ", p), names):
            out.append(f"[report] noncomparative {p!r} が {hit} を含む（腕どうしの数値は比較の keys で宣言する）")
    return out


def _arm_named_keys(cfg: dict) -> list[str]:
    """[compare] の腕の表の外で、腕を名指す語（腕の名前・軸の値・levels）を含む設定の鍵（[solver.ours] のような腕ごとの条件）."""
    arms = arm_labels(cfg)
    out: list[str] = []

    def walk(x: Any, path: str, skip: bool) -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                p = f"{path}.{k}" if path else str(k)
                if not skip and (hit := next((lb for lb, t in arms.items() if _has(_tokens(k), t)), "")):
                    out.append(
                        f"設定の鍵 {p!r} が {hit} を含む（腕ごとの条件は [compare.<名>.sweep] で掃引するか、置かない）"
                    )
                parts = p.split(".")
                walk(v, p, len(parts) == 3 and parts[0] == "compare" and parts[2] in ("arms", "capability"))
        elif isinstance(x, list):
            for i, y in enumerate(x):
                walk(y, f"{path}[{i}]", False)

    walk(cfg, "", False)
    return out


def arm_conditions(cfg: dict, name: str) -> dict[str, dict]:
    """腕ごとの条件 {腕: common ∪ 腕の表}。entry はこれで条件を読む（比較の照合と同じ出所）."""
    c = (cfg.get("compare") or {})[name]
    return {a: {**(c.get("common") or {}), **t} for a, t in (c.get("arms") or {}).items()}


def _capability(c: dict, lab: dict) -> tuple[dict[str, dict], list[str]]:
    """対象外の腕 {腕: {reason, source}} と問題。lab.toml の [compare.capability]（人間）が著者の宣言に優先する."""
    labcap = (lab.get("compare") or {}).get("capability") or {}
    caps, obj, arms, vary = c.get("capability") or {}, c.get("objective"), c.get("arms") or {}, c.get("vary")
    if not isinstance(labcap, dict) or not all(isinstance(v, list) for v in labcap.values()):
        return {}, ["lab.toml の [compare.capability] は 手法（軸の値）= [受け取れる目的] の表"]
    out, probs = {}, []
    for a, t in arms.items():
        v = t.get(vary) if isinstance(t, dict) else None
        lab_v = labcap.get(str(v), labcap.get(a))
        mine = caps.get(a) if isinstance(caps, dict) else None
        if lab_v is not None:
            if mine is not None and sorted(map(str, mine)) != sorted(map(str, lab_v)):
                probs.append(f"腕 {a} の capability {mine} が lab.toml の [compare.capability] {lab_v} と食い違う")
            if isinstance(obj, str) and obj not in lab_v:
                out[a] = {
                    "reason": f"lab.toml の capability {lab_v} に objective={obj!r} が無い（対象外）",
                    "source": "lab.toml",
                }
        elif mine is not None and isinstance(obj, str) and obj not in mine:
            if labcap:
                probs.append(
                    f"腕 {a} を著者の宣言だけで対象外にしている（lab.toml の [compare.capability] に {v!r} が無い）"
                )
            out[a] = {
                "reason": f"capability {mine} に objective={obj!r} が無い（対象外。著者の宣言）",
                "source": "author",
            }
    return out, probs


def _problems(name: str, c: Any, lab: dict) -> list[str]:
    """1 つの比較の設定の問題（run の前に分かるもの）."""
    if not isinstance(c, dict):
        return [f"[compare.{name}] は表"]
    out = (
        [f"[compare.{name}] に知らない項目 {sorted(set(c) - _FIELDS)}（{sorted(_FIELDS)}）"] if set(c) - _FIELDS else []
    )
    vary, keys, common, arms = c.get("vary"), c.get("keys"), c.get("common"), c.get("arms")
    if not isinstance(vary, str) or not vary:
        return [*out, f'[compare.{name}] vary は変える軸 1 つの文字列（vary = "method"）']
    if not isinstance(keys, list) or not keys or not all(isinstance(k, str) and _NAME_RE.match(k) for k in keys):
        out.append(f"[compare.{name}] keys はこの比較の指標名の配列（1 つ以上、glob 不可）")
        keys = []
    if (
        not isinstance(common, dict)
        or not isinstance(arms, dict)
        or not all(isinstance(t, dict) for t in arms.values())
    ):
        return [*out, f"[compare.{name}] には [.common] と [.arms.<腕>] の表が要る"]
    if vary in common:
        out.append(f"[compare.{name}] vary={vary!r} が common にある（軸は腕の表にだけ書く）")
    levels = c.get("levels", [])
    if not isinstance(levels, list) or not all(
        isinstance(x, str | int | float | bool) and not (isinstance(x, str) and (_SEP_RE.search(x) or not x))
        for x in levels
    ):
        out.append(f"[compare.{name}] levels は軸の値（1 語のスカラー）の配列")
        levels = []
    caps = c.get("capability") or {}
    if not isinstance(caps, dict) or not all(isinstance(v, list) for v in caps.values()) or set(caps) - set(arms):
        out.append(f"[compare.{name}.capability] は 腕 = [受け取れる目的] の表（腕は arms にあるもの）")
        caps = {}
    if caps and not isinstance(c.get("objective"), str):
        out.append(f"[compare.{name}] capability を使うなら objective（この比較の目的）を書く")
    excluded, cap_probs = _capability({**c, "capability": caps}, lab)
    out += [f"[compare.{name}] {p}" for p in cap_probs]
    better = c.get("better")
    if better is not None and better not in ("max", "min"):
        out.append(f'[compare.{name}] better は "max" | "min"')
    swept: dict[str, set[str]] = {}
    trials = {a: 0 for a in arms}
    sweeps = _sweeps(c)
    if sweeps and better not in ("max", "min"):
        out.append(
            f'[compare.{name}] 掃引があるなら better = "max" | "min"（指標の良い向き。掃引の direction はこれと同じ）'
        )
    for i, s in enumerate(sweeps, 1):
        if not isinstance(s, dict) or set(s) != _SWEEP_FIELDS:
            out.append(f"[compare.{name}.sweep] #{i} は {sorted(_SWEEP_FIELDS)} をちょうど持つ表")
            continue
        vals = s["values"]
        bad = (
            not isinstance(s["arm"], str)
            or s["arm"] not in arms
            or not isinstance(s["param"], str)
            or s["param"] in (vary, *common)
            or not isinstance(vals, list)
            or len(vals) < 2
            or len({canonical(v) for v in vals}) < len(vals)
            or not isinstance(s["metric"], str)
            or "{value}" not in s["metric"]
            or s["direction"] not in ("max", "min")
            or s["param"] in swept.get(s["arm"], set())
        )
        if bad:
            out.append(
                f"[compare.{name}.sweep] #{i}: arm は腕、param は vary・common に無い鍵（腕ごとに 1 回）、values は異なる値 2 つ以上、"
                'metric は "{value}" を含む指標名、direction は "max" | "min"'
            )
            continue
        if better in ("max", "min") and s["direction"] != better:
            out.append(f"[compare.{name}.sweep] #{i}: direction={s['direction']!r} が比較の better={better!r} と違う")
        mt = _tokens(s["metric"].replace("{value}", " "))
        if not any(_has(mt, _tokens(k)) for k in keys):
            out.append(
                f"[compare.{name}.sweep] #{i}: metric {s['metric']!r} が比較の指標 {keys} のどれも含まない"
                "（掃引は比較と同じ指標で採点する）"
            )
        swept.setdefault(s["arm"], set()).add(s["param"])
        trials[s["arm"]] += len(vals)
    for a, t in arms.items():
        v = t.get(vary)
        if vary not in t:
            out.append(f"[compare.{name}.arms.{a}] に軸 {vary!r} が無い")
        elif not isinstance(v, str | int | float | bool):
            out.append(f"[compare.{name}.arms.{a}] 軸 {vary!r} の値は 1 つのスカラー（表や配列で複数の条件を束ねない）")
        elif isinstance(v, str) and _SEP_RE.search(v):
            out.append(f"[compare.{name}.arms.{a}] 軸 {vary!r} の値 {v!r} は 1 語（+ / , ; 空白などで条件を束ねない）")
        elif canonical(v) not in {canonical(x) for x in [a, *levels]}:
            out.append(
                f"[compare.{name}.arms.{a}] 軸 {vary!r} の値 {v!r} は腕の名前 {a!r} か [compare.{name}] levels の値"
            )
        if extra := sorted(set(t) - {vary} - swept.get(a, set())):
            out.append(
                f"[compare.{name}.arms.{a}] の {extra} は腕ごとの条件。全腕で同じなら common に、比較対象の自由パラメータなら "
                f"[compare.{name}.sweep] を宣言する（変えてよいのは vary={vary!r} だけ）"
            )
    live = [a for a in arms if a not in excluded] if not out else list(arms)
    if len(live) < 2:
        out.append(f"[compare.{name}] 対象外でない腕が {len(live)} 本（比較には 2 本以上）")
    elif len({canonical(arms[a].get(vary)) for a in live}) < len(live):
        out.append(f"[compare.{name}] 軸 {vary!r} の値が同じ腕がある")
    if any(trials[a] for a in live) and len({trials[a] for a in live}) > 1:
        out.append(
            f"[compare.{name}.sweep] 腕ごとの総試行数が違う { ({a: trials[a] for a in live}) }"
            "（1 腕でも調整するなら、対象外でない全腕を同じ総試行数で調整する）"
        )
    for k in (lab.get("compare") or {}).get("required") or []:
        if k != vary and (k not in common or _empty(common[k])):
            out.append(f"lab.toml の [compare] required の条件 {k!r} が [compare.{name}.common] に無い・空・未定")
    return out


def config_problems(cfg: dict, lab: dict) -> dict[str, list[str]]:
    """設定の比較の問題 {比較名（全体は ""）: [問題]}。空なら run を始めてよい."""
    comp, out = cfg.get("compare"), {}
    nc = noncomparative(cfg)
    glob = [] if nc is not None else ["[report] noncomparative は指標名（glob 可）の配列"]
    nc = nc or []
    glob += _nc_problems(nc, _names(cfg))
    if comp is None:
        return {"": glob} if glob else {}
    if not isinstance(comp, dict) or not comp:
        return {"": [*glob, "[compare] は [compare.<比較名>] の表を 1 つ以上持つ"]}
    glob += _arm_named_keys(cfg)
    if glob:
        out[""] = glob
    owner: dict[str, str] = {}
    for name, c in comp.items():
        out[name] = _problems(name, c, lab)
        for k in (c.get("keys") or []) if isinstance(c, dict) and isinstance(c.get("keys"), list) else []:
            if k in owner:
                out[name].append(f"指標 {k!r} が比較 {owner[k]!r} と {name!r} の両方にある（1 つの比較だけに属す）")
            if any(fnmatch.fnmatchcase(str(k), p) for p in nc):
                out[name].append(f"指標 {k!r} が [report] noncomparative にも当たる")
            owner.setdefault(k, name)
    return {k: v for k, v in out.items() if v}


def check_config(cfg: dict, lab: dict) -> None:
    """run を作る前の関門。問題があれば ConditionMismatch（run ディレクトリは作られない）."""
    if probs := config_problems(cfg, lab):
        raise ConditionMismatch(
            "比較の設定が ceteris paribus を満たしません:\n  " + "\n  ".join(sum(probs.values(), []))
        )


def _sweep_result(s: dict, arm_value: Any, metrics: dict) -> tuple[dict, list[str]]:
    keys = [s["metric"].format(value=v) for v in s["values"]]
    if missing := [k for k in keys if not isinstance(metrics.get(k), int | float)]:
        return {}, [
            f"掃引 {s['arm']}.{s['param']}: 指標 {missing} が run に記録されていない（スコアは run の記録から読む）"
        ]
    scores = [float(metrics[k]) for k in keys]
    best = (max if s["direction"] == "max" else min)(scores)
    tied = [v for v, x in zip(s["values"], scores, strict=True) if x == best]
    chosen = tied[0] if arm_value is None else arm_value
    rec = {**s, "scores": scores, "best": best, "chosen": chosen}
    if canonical(chosen) not in {canonical(v) for v in tied}:
        return rec, [
            f"掃引 {s['arm']}.{s['param']}: 腕の値 {chosen!r} は掃引の最良ではない（{tied[0]!r} で {best}）。比較対象は宣言した掃引の最良"
        ]
    return rec, []


def evaluate(cfg: dict, lab: dict, metrics: dict) -> dict:
    """凍結した設定と run の metrics から比較を計算する（記録時と check で同じ関数）."""
    probs = config_problems(cfg, lab)
    out = {}
    for name, c in (cfg.get("compare") or {}).items() if isinstance(cfg.get("compare"), dict) else []:
        diff = list(probs.get("", [])) + list(probs.get(name, []))
        rec: dict = {"vary": c.get("vary") if isinstance(c, dict) else None, "keys": [], "diff": diff}
        if not diff:
            conds, excl = arm_conditions(cfg, name), _capability(c, lab)[0]
            sweeps = []
            for s in _sweeps(c):
                r, p = _sweep_result(s, conds[s["arm"]].get(s["param"]), metrics)
                sweeps.append(r)
                diff += p
                if r:
                    conds[s["arm"]][s["param"]] = r["chosen"]
            common = c.get("common") or {}
            rec.update(
                keys=list(c["keys"]),
                objective=c.get("objective"),
                better=c.get("better"),
                common_sha256=hashlib.sha256(canonical(common).encode()).hexdigest(),
                arms={a: v for a, v in conds.items() if a not in excl},
                not_applicable=excl,
                author_declared_not_applicable=sorted(a for a, e in excl.items() if e["source"] == "author"),
                sweeps=sweeps,
            )
        rec["matched"] = not diff
        out[name] = rec
    return out


def chosen(run, name: str) -> dict[str, dict]:
    """掃引の最良 {腕: {param: 値}}（run の記録から。entry が比較対象をこの値で評価する）."""
    c = run.config["compare"][name]
    conds = arm_conditions(run.config, name)
    return {
        s["arm"]: {s["param"]: _sweep_result(s, conds[s["arm"]].get(s["param"]), run._last)[0].get("chosen")}
        for s in _sweeps(c)
    }


def config_drift(run) -> str:
    """run の途中で設定が変わったか（メモリ上の設定・config.json の hash を開始時と比べる）。空なら変わっていない."""
    f = Path(run.dir) / "config.json"
    start = (run.meta or {}).get("config_sha256")
    if not start or not f.is_file() or sha256_file(f) != start:
        return "config.json が run の開始時の hash（meta.config_sha256）と違う（run の途中で設定を書き換えた）"
    if getattr(run, "_config0", None) is None or canonical(run.config) != run._config0:
        return "run.config が run の途中で変わった（設定は開始時に凍結される。条件を変えるなら別の run）"
    return ""


def record(run) -> list[str]:
    """Run の終了時に 1 回だけ comparisons.json を書く。問題（空なら一致）を返し、Run は問題があれば failed にする."""
    f = Path(run.dir) / COMPARISON_FILE
    if (run.meta or {}).get("status") != "running":
        return ["比較の記録は running の run の中だけ"]
    if f.exists():
        return [f"{COMPARISON_FILE} が既にある（比較の記録は run ごとに 1 回。labkit 以外が書いた記録は使わない）"]
    if why := config_drift(run):
        return [why]
    cfg = json.loads(run._config0)
    if not cfg.get("compare"):
        return []
    rec = evaluate(cfg, run.lab, run._last)
    write_json_atomic(f, json.loads(canonical(rec)))
    return [f"{n}: {p}" for n, r in rec.items() for p in r["diff"]]


# ---- 凍結した成果物からの照合（check L027・claim add）----
def _hashed(d: Path, meta: dict, fname: str) -> str:
    """fname が meta の outputs に hash 付きで載り、中身が一致する（run の後から書いた・書き換えた物を拒む）."""
    rec = next((o for o in meta.get("outputs") or [] if o.get("path") == fname), None)
    if rec is None or not rec.get("sha256"):
        return f"{fname} が meta.json の outputs に hash 付きで無い（run の中で書かれた記録ではない）"
    if not (d / fname).is_file() or sha256_file(d / fname) != rec["sha256"]:
        return f"{fname} の hash が meta.json の outputs と違う（run の後に書き換えられた）"
    return ""


def _frozen(d: Path, meta: dict, fname: str) -> tuple[dict, str]:
    if why := _hashed(d, meta, fname):
        return {}, why
    if fname == "config.json" and meta.get("config_sha256") != sha256_file(d / fname):
        return {}, "config.json が run の開始時の hash（meta.config_sha256）と違う・記録が無い"
    try:
        return read_json(d / fname), ""
    except json.JSONDecodeError:
        return {}, f"{fname} が壊れている"


def nc_key_problem(cfg: dict, key: str) -> str:
    """非比較と宣言した指標が腕どうしの数値に見える（腕の名前・比較の指標の語幹・比べる語を含む）なら理由."""
    if hit := _named(key, _names(cfg)):
        return f"{key} は非比較の宣言に当たるが {hit} を含む（腕どうしの数値は比較の keys で宣言し、matched な run で出す）"
    return ""


def run_status(d: Path, meta: dict, lab: dict) -> dict:
    """run の比較を凍結した設定から計算し直す: {problems, matched_keys, unmatched_keys, noncomparative, author_excluded}."""
    cfg, why = _frozen(d, meta, "config.json")
    st: dict = {
        "problems": [why] if why else [],
        "matched_keys": set(),
        "unmatched_keys": set(),
        "cfg": cfg,
        "owner": {},
    }
    st["author_excluded"] = []
    glob = config_problems(cfg, lab).get("", []) if not why else []
    st["problems"] += glob
    st["noncomparative"] = [] if glob or why else noncomparative(cfg) or []
    if why or not cfg.get("compare"):
        if not why and (d / COMPARISON_FILE).exists():
            st["problems"].append(f"設定に [compare] が無いのに {COMPARISON_FILE} がある")
        return st
    metrics, why_m = _frozen(d, meta, "metrics.json")
    stored, why_s = _frozen(d, meta, COMPARISON_FILE)
    st["problems"] += [w for w in (why_m, why_s) if w]
    for name, r in evaluate(cfg, lab, metrics).items():
        ok = r["matched"] and not why_m and not why_s and (stored.get(name) or {}).get("matched") is True
        c = cfg["compare"][name]
        ks = c.get("keys") if isinstance(c, dict) and isinstance(c.get("keys"), list) else []
        st["matched_keys" if ok else "unmatched_keys"] |= {k for k in ks if isinstance(k, str)}
        st["owner"].update({k: name for k in ks if isinstance(k, str)} if ok else {})
        st["author_excluded"] += [f"{name}.{a}" for a in r.get("author_declared_not_applicable", [])]
        if not r["matched"]:
            st["problems"] += [f"{name}: {p}" for p in r["diff"] if p not in glob]
        elif not ok and not (why_m or why_s):
            st["problems"].append(f"{name}: {COMPARISON_FILE} の記録が matched でない")
    return st


def key_problem(st: dict, key: str) -> tuple[str, str]:
    """(種類, 理由)。種類は "" | "unmatched"（条件のそろわない比較の指標・腕どうしの数値に見える非比較）| "undeclared"."""
    if key in st["matched_keys"]:
        return "", ""
    if key in st["unmatched_keys"]:
        return "unmatched", f"{key} は比較の指標だが、条件がそろっていない: " + "; ".join(st["problems"][:3])
    if any(fnmatch.fnmatchcase(key, p) for p in st["noncomparative"]):
        if why := nc_key_problem(st.get("cfg") or {}, key):
            return "unmatched", why
        return "", ""
    return "undeclared", (
        f"{key} は run の設定で比較（[compare.<名>] keys）とも非比較（[report] noncomparative）とも宣言されていない"
        + (f"（{st['problems'][0]}）" if st["problems"] else "")
    )


def _flat(d: Any, prefix: str = "") -> dict[str, str]:
    if isinstance(d, dict) and d:
        return {k: v for key, val in d.items() for k, v in _flat(val, f"{prefix}{key}.").items()}
    return {prefix.rstrip("."): canonical(d)}


def _cross_cfg(cfg: dict, meta: dict) -> dict:
    """実験間で照合する設定: ラベル以外のすべて（[compare.<名>] の common・arms・sweep なども。keys だけ除く）と commit."""
    out = {k: v for k, v in cfg.items() if k not in _LABELS}
    if isinstance(out.get("compare"), dict):
        out["compare"] = {
            n: {k: v for k, v in c.items() if k != "keys"} if isinstance(c, dict) else c
            for n, c in out["compare"].items()
        }
    out["_git_commit"] = (meta.get("git") or {}).get("commit")
    return out


def cross_run_problem(runs: dict, rids: list[str], axis: str | None) -> str:
    """複数の run にまたがる根拠: 軸（設定のドット区切りの鍵。_ で始まる内部の鍵は不可）以外の凍結した設定と commit が同一か."""
    rids = sorted(set(rids))
    if len(rids) < 2:
        return ""
    if not axis:
        return f"根拠が {len(rids)} 個の run にまたがる。比較の軸を axis=<設定の鍵> で宣言する（--axis）"
    if any(seg.startswith("_") for seg in axis.split(".")):
        return f"軸 {axis!r} は内部の鍵（_git_commit など。commit は何本もの条件を同時に変える）。設定の鍵を 1 つ選ぶ"
    flats = {}
    for rid in rids:
        cfg, why = _frozen(runs[rid]["_dir"], runs[rid], "config.json")
        if why:
            return f"run {rid}: {why}"
        flat = _flat(_cross_cfg(cfg, runs[rid]))
        if axis not in flat or flat[axis].startswith(("{", "[")):
            return f"run {rid}: 軸 {axis!r} が設定の 1 つのスカラーの鍵ではない（表ごと変えると複数の条件が変わる）"
        v = json.loads(flat[axis])
        if isinstance(v, str) and (_SEP_RE.search(v) or not v.strip()):
            return f"run {rid}: 軸 {axis!r} の値 {v!r} は 1 語（+ / , ; 空白などで条件を束ねない）"
        flats[rid] = {k: v for k, v in flat.items() if k != axis}
    ref = flats[rids[0]]
    diff = sorted({k for f in flats.values() for k in set(f) | set(ref) if f.get(k) != ref.get(k)})
    if diff:
        return f"run の間で軸 {axis!r} 以外の条件が違う: {diff[:8]}（変えてよいのは 1 軸だけ）"
    return ""


def evidence_problems(runs: dict, lab: dict, cites: list[tuple[str, str]], axis: str | None) -> list[str]:
    """主張の根拠（既定で拒否）: 各指標は matched な比較の指標か非比較の宣言。複数 run は軸以外が同一.

    主張は既定で比較とみなす: 2 つ以上の値を引くなら、1 つの run の中の値は 1 つの matched な比較の keys だけで、
    非比較の指標は 1 つまで（同じ run の非比較の値を 2 つ並べると、宣言していない比較になる）。
    """
    out, cache, keys = [], {}, {}
    for rid, key in cites:
        if rid not in runs or runs[rid].get("status") is None:
            continue
        st = cache.setdefault(rid, run_status(runs[rid]["_dir"], runs[rid], lab))
        keys.setdefault(rid, set()).add(key)
        if kind := key_problem(st, key)[1]:
            out.append(f"run {rid}: {kind}")
    if len({(r, k) for r, ks in keys.items() for k in ks}) > 1:
        for rid, ks in keys.items():
            owners = sorted({cache[rid]["owner"][k] for k in ks if k in cache[rid]["owner"]})
            nc = sorted(k for k in ks if k not in cache[rid]["owner"])
            if len(owners) > 1:
                out.append(
                    f"run {rid}: 1 つの主張が別々の比較 {owners} の指標を並べている（1 つの matched な比較の keys だけ）"
                )
            if len(nc) > 1:
                out.append(
                    f"run {rid}: 1 つの主張が同じ run の比較でない値 {nc} を並べている（主張は既定で比較。"
                    "腕どうしの数値は [compare.<名>] keys で宣言し matched な run で出す）"
                )
    if why := cross_run_problem(runs, [r for r, _ in cites if r in runs], axis):
        out.append(why)
    return out
