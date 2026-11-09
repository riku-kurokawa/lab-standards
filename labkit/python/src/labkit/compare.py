"""比較は 1 軸だけを変える（ceteris paribus）。腕の条件は設定から導出し、機械が凍結した設定で確かめる.

    # configs/experiments/design.toml（run の前に書き、config.json に凍結される）
    [compare.design]
    vary = "method"                  # 変える軸はちょうど 1 つ
    keys = ["gain_db"]               # この比較の指標（1 つの指標は 1 つの比較だけに属す）
    objective = "focus"              # capability を使うときに必要
    [compare.design.common]          # 全腕で同一の条件（lab.toml の [compare] required をすべて含む）
    dof = "PA"
    quant_bits = 8
    [compare.design.arms.ours]
    method = "ours"
    [compare.design.arms.flat]
    method = "flat"                  # 腕の表に書けるのは vary と、その腕の掃引の param だけ
    [compare.design.sweep]           # 比較対象の自由パラメータ（[[...sweep]] で複数可。同じ値の数＝同じ調整予算）
    arm = "flat"
    param = "height_mm"
    values = [10, 20, 30]
    metric = "flat_gain_h{value}"    # 値ごとに run が log_metric する指標（スコアは run の記録から読む）
    direction = "max"
    [compare.design.capability]      # 腕 → 受け取れる目的。objective が無い腕は「対象外」（負けではない）
    gs = ["focus_only"]
    [report]
    noncomparative = ["snr_*"]       # 比較ではない指標（glob）。主張の根拠はこれか matched な比較の指標だけ

entry は `arm_conditions(cfg, "design")` で腕の条件を同じ表から読み、掃引の後 `chosen(run, "design")` で最良の値を得る。
Run は開始前に設定を検査し（合わなければ run を作らない）、終了時に 1 回だけ comparisons.json を書く（掃引のスコアは
run の metrics から読む）。合わない・2 回目の記録・running でない記録は run を failed にする。check L027 は凍結した
config.json と metrics.json（meta の outputs の hash を照合）から比較を計算し直し、記録の matched を信用しない.
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
_FIELDS = {"vary", "keys", "objective", "common", "arms", "sweep", "capability"}
_SWEEP_FIELDS = {"arm", "param", "values", "metric", "direction"}
_DECLARATIVE = ("prediction", "pass", "compare", "report", "name", "serves")  # 実験間の照合で比べない宣言とラベル
_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")


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
    return v is None or v == "" or v == [] or v == {}


def noncomparative(cfg: dict) -> list[str] | None:
    """[report] noncomparative（glob の配列）。形が違えば None."""
    r = cfg.get("report")
    v = r.get("noncomparative", []) if isinstance(r, dict) else []
    return v if isinstance(v, list) and all(isinstance(p, str) for p in v) else None


def _sweeps(c: dict) -> list:
    s = c.get("sweep")
    return [] if s is None else [s] if isinstance(s, dict) else s if isinstance(s, list) else [s]


def arm_conditions(cfg: dict, name: str) -> dict[str, dict]:
    """腕ごとの条件 {腕: common ∪ 腕の表}。entry はこれで条件を読む（比較の照合と同じ出所）."""
    c = (cfg.get("compare") or {})[name]
    return {a: {**(c.get("common") or {}), **t} for a, t in (c.get("arms") or {}).items()}


def _excluded(c: dict) -> dict[str, str]:
    caps, obj = c.get("capability") or {}, c.get("objective")
    return {a: f"capability {caps[a]} に objective={obj!r} が無い（対象外）" for a in caps if obj not in caps[a]}


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
    if (
        not isinstance(common, dict)
        or not isinstance(arms, dict)
        or not all(isinstance(t, dict) for t in arms.values())
    ):
        return [*out, f"[compare.{name}] には [.common] と [.arms.<腕>] の表が要る"]
    if vary in common:
        out.append(f"[compare.{name}] vary={vary!r} が common にある（軸は腕の表にだけ書く）")
    caps = c.get("capability") or {}
    if not isinstance(caps, dict) or not all(isinstance(v, list) for v in caps.values()) or set(caps) - set(arms):
        out.append(f"[compare.{name}.capability] は 腕 = [受け取れる目的] の表（腕は arms にあるもの）")
        caps = {}
    if caps and not isinstance(c.get("objective"), str):
        out.append(f"[compare.{name}] capability を使うなら objective（この比較の目的）を書く")
    swept: dict[str, set[str]] = {}
    sweeps = _sweeps(c)
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
        if not bad:
            swept.setdefault(s["arm"], set()).add(s["param"])
    if len({len(s["values"]) for s in sweeps if isinstance(s, dict) and isinstance(s.get("values"), list)}) > 1:
        out.append(f"[compare.{name}.sweep] 掃引の値の数が違う（調整の予算は腕の間で同じにする）")
    for a, t in arms.items():
        if vary not in t:
            out.append(f"[compare.{name}.arms.{a}] に軸 {vary!r} が無い")
        elif not isinstance(t[vary], str | int | float | bool):
            out.append(f"[compare.{name}.arms.{a}] 軸 {vary!r} の値は 1 つのスカラー（表や配列で複数の条件を束ねない）")
        if extra := sorted(set(t) - {vary} - swept.get(a, set())):
            out.append(
                f"[compare.{name}.arms.{a}] の {extra} は腕ごとの条件。全腕で同じなら common に、比較対象の自由パラメータなら "
                f"[compare.{name}.sweep] を宣言する（変えてよいのは vary={vary!r} だけ）"
            )
    live = [a for a in arms if a not in _excluded(c)] if not out else list(arms)
    if len(live) < 2:
        out.append(f"[compare.{name}] 対象外でない腕が {len(live)} 本（比較には 2 本以上）")
    elif len({canonical(arms[a].get(vary)) for a in live}) < len(live):
        out.append(f"[compare.{name}] 軸 {vary!r} の値が同じ腕がある")
    for k in (lab.get("compare") or {}).get("required") or []:
        if k != vary and (k not in common or _empty(common[k])):
            out.append(f"lab.toml の [compare] required の条件 {k!r} が [compare.{name}.common] に無い・空")
    return out


def config_problems(cfg: dict, lab: dict) -> dict[str, list[str]]:
    """設定の比較の問題 {比較名（全体は ""）: [問題]}。空なら run を始めてよい."""
    comp, out = cfg.get("compare"), {}
    nc = noncomparative(cfg)
    if nc is None:
        out[""] = ["[report] noncomparative は指標名（glob 可）の配列"]
        nc = []
    if comp is None:
        return out
    if not isinstance(comp, dict) or not comp:
        return {**out, "": ["[compare] は [compare.<比較名>] の表を 1 つ以上持つ"]}
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
            conds, excl = arm_conditions(cfg, name), _excluded(c)
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
                common_sha256=hashlib.sha256(canonical(common).encode()).hexdigest(),
                arms={a: v for a, v in conds.items() if a not in excl},
                not_applicable=excl,
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


def record(run) -> list[str]:
    """Run の終了時に 1 回だけ comparisons.json を書く。問題（空なら一致）を返し、Run は問題があれば failed にする."""
    f = Path(run.dir) / COMPARISON_FILE
    if (run.meta or {}).get("status") != "running":
        return ["比較の記録は running の run の中だけ"]
    if f.exists():
        return [f"{COMPARISON_FILE} が既にある（比較の記録は run ごとに 1 回。labkit 以外が書いた記録は使わない）"]
    rec = evaluate(run.config, run.lab, run._last)
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
    try:
        return read_json(d / fname), ""
    except json.JSONDecodeError:
        return {}, f"{fname} が壊れている"


def run_status(d: Path, meta: dict, lab: dict) -> dict:
    """run の比較を凍結した設定から計算し直す: {problems, matched_keys, unmatched_keys, noncomparative}."""
    cfg, why = _frozen(d, meta, "config.json")
    st: dict = {"problems": [why] if why else [], "matched_keys": set(), "unmatched_keys": set()}
    st["noncomparative"] = noncomparative(cfg) or []
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
        if not r["matched"]:
            st["problems"] += [f"{name}: {p}" for p in r["diff"]]
        elif not ok and not (why_m or why_s):
            st["problems"].append(f"{name}: {COMPARISON_FILE} の記録が matched でない")
    return st


def key_problem(st: dict, key: str) -> tuple[str, str]:
    """(種類, 理由)。種類は "" | "unmatched"（条件のそろわない比較の指標）| "undeclared"（比較とも非比較とも宣言していない）."""
    if key in st["matched_keys"]:
        return "", ""
    if key in st["unmatched_keys"]:
        return "unmatched", f"{key} は比較の指標だが、条件がそろっていない: " + "; ".join(st["problems"][:3])
    if any(fnmatch.fnmatchcase(key, p) for p in st["noncomparative"]):
        return "", ""
    return "undeclared", (
        f"{key} は run の設定で比較（[compare.<名>] keys）とも非比較（[report] noncomparative）とも宣言されていない"
        + (f"（{st['problems'][0]}）" if st["problems"] else "")
    )


def _flat(d: Any, prefix: str = "") -> dict[str, str]:
    if isinstance(d, dict) and d:
        return {k: v for key, val in d.items() for k, v in _flat(val, f"{prefix}{key}.").items()}
    return {prefix.rstrip("."): canonical(d)}


def cross_run_problem(runs: dict, rids: list[str], axis: str | None) -> str:
    """複数の run にまたがる根拠: 軸（設定のドット区切りの鍵、または _git_commit）以外の凍結した設定と commit が同一か."""
    rids = sorted(set(rids))
    if len(rids) < 2:
        return ""
    if not axis:
        return f"根拠が {len(rids)} 個の run にまたがる。比較の軸を axis=<設定の鍵> で宣言する（--axis）"
    flats = {}
    for rid in rids:
        cfg, why = _frozen(runs[rid]["_dir"], runs[rid], "config.json")
        if why:
            return f"run {rid}: {why}"
        cfg = {k: v for k, v in cfg.items() if k not in _DECLARATIVE}
        cfg["_git_commit"] = (runs[rid].get("git") or {}).get("commit")
        flat = _flat(cfg)
        if axis not in flat or flat[axis].startswith(("{", "[")):
            return f"run {rid}: 軸 {axis!r} が設定の 1 つのスカラーの鍵ではない（表ごと変えると複数の条件が変わる）"
        flats[rid] = {k: v for k, v in flat.items() if k != axis}
    ref = flats[rids[0]]
    diff = sorted({k for f in flats.values() for k in set(f) | set(ref) if f.get(k) != ref.get(k)})
    if diff:
        return f"run の間で軸 {axis!r} 以外の条件が違う: {diff[:8]}（変えてよいのは 1 軸だけ）"
    return ""


def evidence_problems(runs: dict, lab: dict, cites: list[tuple[str, str]], axis: str | None) -> list[str]:
    """主張の根拠（既定で拒否）: 各指標は matched な比較の指標か非比較の宣言。複数 run は軸以外が同一."""
    out, cache = [], {}
    for rid, key in cites:
        if rid not in runs or runs[rid].get("status") is None:
            continue
        st = cache.setdefault(rid, run_status(runs[rid]["_dir"], runs[rid], lab))
        if kind := key_problem(st, key)[1]:
            out.append(f"run {rid}: {kind}")
    if why := cross_run_problem(runs, [r for r, _ in cites if r in runs], axis):
        out.append(why)
    return out
