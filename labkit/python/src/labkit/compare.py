"""比較は 1 軸だけを変える（ceteris paribus）。腕（手法・設計・設定）の条件の同一性を機械で確かめる.

    with Run("design", cfg) as run:          # cfg の [compare] vary = ["method"], keys = ["gain_db"]
        arms = [Arm("ours", {"method": "ours", "dof": "PA", "quant_bits": 8, ...}),
                Arm("flat", {"method": "flat", "dof": "PA", "quant_bits": 8, ...})]
        run.compare(arms, comparator_sweep={"flat": {"height_mm": [10, 20, 30], "chosen": 20, "scores": [.1, .5, .3]}})
        run.log_metric("gain_db", 3.2)

比較が成り立つのは、宣言した軸（vary）以外の条件がすべての腕で同一で、それを機械が確かめたときだけ。
`declare` は条件の鍵の集合・vary 以外の値（正準 JSON で比較。浮動小数は厳密、または rel_tol）・lab.toml の
`[compare] required`・比較対象の自由パラメータの掃引（chosen が最良か）を確かめ、run に comparison.json を書く。
合わなければ comparison.json（matched=false と差分）を書いて ConditionMismatch を送出する。
比較の鍵（comparison.json の keys・設定の [compare] keys・lab.toml の [compare] keys）を引用・主張できるのは
matched=true の run だけ（check L027、`labkit claim add`）。目的を受け取れない腕は Arm(..., not_applicable="理由")
で「対象外」とし、負けとして数えない（照合から外し comparison.json に別に記録する）.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from labkit._util import _json_default, read_json, write_json_atomic

COMPARISON_FILE = "comparison.json"
_SWEEP_META = {"chosen", "scores", "minimize"}


class ConditionMismatch(ValueError):
    """腕の条件が vary 以外で一致しない、必須の条件が無い、比較対象が最良でない."""


@dataclass
class Arm:
    name: str
    conditions: dict
    not_applicable: str = ""  # 目的を受け取れない腕の理由（「対象外」。負けではない）


def canonical(value: Any) -> str:
    """正準 JSON（鍵の順を固定、numpy は Python の値に）。比較と指紋の基準."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=_json_default)


def fingerprint(conditions: dict, vary: list[str]) -> str:
    return hashlib.sha256(canonical({k: v for k, v in conditions.items() if k not in vary}).encode()).hexdigest()


def _same(a: Any, b: Any, rel_tol: float) -> bool:
    a, b = json.loads(canonical(a)), json.loads(canonical(b))
    if rel_tol <= 0:
        return canonical(a) == canonical(b)
    num = (int, float)
    if isinstance(a, num) and isinstance(b, num) and not isinstance(a, bool) and not isinstance(b, bool):
        return math.isclose(a, b, rel_tol=rel_tol, abs_tol=0.0)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k], rel_tol) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y, rel_tol) for x, y in zip(a, b, strict=True))
    return canonical(a) == canonical(b)


def condition_diff(arms: list[Arm], vary: list[str], rel_tol: float = 0.0) -> list[str]:
    """基準の腕（最初の腕）と比べた不一致を、腕ごと・鍵ごとに 1 行で返す（空なら一致）."""
    ref, out = arms[0], []
    for arm in arms[1:]:
        for k in sorted(set(ref.conditions) | set(arm.conditions)):
            if k not in arm.conditions or k not in ref.conditions:
                missing = arm.name if k not in arm.conditions else ref.name
                out.append(f"{arm.name}: 条件 {k!r} が腕 {missing} に無い（鍵の集合が違う）")
            elif k not in vary and not _same(ref.conditions[k], arm.conditions[k], rel_tol):
                out.append(
                    f"{arm.name}: 条件 {k!r} が違う（{ref.name}={canonical(ref.conditions[k])} / "
                    f"{arm.name}={canonical(arm.conditions[k])}）。変えてよいのは vary={vary} だけ"
                )
    return out


def sweep_problems(arms: list[Arm], sweep: dict | None) -> list[str]:
    """比較対象の自由パラメータ（平板の高さなど）は宣言した掃引の最良でなければならない."""
    out, by_name = [], {a.name: a for a in arms}
    for name, s in (sweep or {}).items():
        params = [k for k in s if k not in _SWEEP_META]
        if name not in by_name or len(params) != 1 or "chosen" not in s or "scores" not in s:
            out.append(f"掃引 {name!r}: 腕の名前と {{<param>: [値], chosen: 値, scores: [...]}} が必要")
            continue
        param, values, scores = params[0], list(s[params[0]]), list(s["scores"])
        if len(values) != len(scores) or not values or s["chosen"] not in values:
            out.append(f"掃引 {name!r}: {param} の値と scores の長さが違う、または chosen={s['chosen']!r} が値に無い")
            continue
        best = (min if s.get("minimize") else max)(scores)
        got = scores[values.index(s["chosen"])]
        if got != best:
            goal = "最小" if s.get("minimize") else "最大"
            out.append(
                f"掃引 {name!r}: chosen {param}={s['chosen']!r} のスコア {got} は{goal}ではない"
                f"（{param}={values[scores.index(best)]!r} で {best}）。比較対象は宣言した掃引の最良にする"
            )
        cond = by_name[name].conditions
        if param in cond and not _same(cond[param], s["chosen"], 0.0):
            out.append(f"掃引 {name!r}: 腕の条件 {param}={cond[param]!r} が chosen={s['chosen']!r} と違う")
    return out


def check_compare_config(cfg: dict | None) -> None:
    """設定の [compare] の構造（run を作る前に止める）: vary は 1 つ以上の文字列、keys は文字列の配列."""
    if cfg is None:
        return
    vary, keys = cfg.get("vary"), cfg.get("keys", [])
    ok = (
        isinstance(cfg, dict)
        and isinstance(vary, list)
        and vary
        and all(isinstance(v, str) for v in vary)
        and isinstance(keys, list)
        and all(isinstance(k, str) for k in keys)
    )
    if not ok:
        raise ValueError('[compare] には vary = ["<変える軸>"]（1 つ以上）と keys = ["<比較の指標>"] を書く')


def _target(run_or_dir) -> tuple[Path, Path, dict, dict]:
    """(run ディレクトリ, root, lab, 設定の [compare])."""
    from labkit.config import find_root, load_lab

    if hasattr(run_or_dir, "dir") and hasattr(run_or_dir, "lab"):
        return Path(run_or_dir.dir), run_or_dir.root, run_or_dir.lab, run_or_dir.config.get("compare") or {}
    d = Path(run_or_dir)
    root = find_root(d)
    cfg = read_json(d / "config.json").get("compare") or {} if (d / "config.json").is_file() else {}
    return d, root, load_lab(root), cfg


def declare(
    run_or_dir,
    arms: list[Arm],
    vary: list[str] | None = None,
    comparator_sweep: dict | None = None,
    *,
    keys: list[str] | None = None,
    rel_tol: float = 0.0,
) -> dict:
    """腕の条件の同一性を確かめて comparison.json を書く。合わなければ matched=false で書いて ConditionMismatch."""
    d, _, lab, cfg = _target(run_or_dir)
    problems: list[str] = []
    if cfg.get("vary") and vary is not None and sorted(vary) != sorted(cfg["vary"]):
        problems.append(f"vary={vary} が設定の [compare] vary={cfg['vary']}（事前の宣言）と違う")
    vary = list(vary if vary is not None else cfg.get("vary") or [])
    if cfg.get("keys") and keys is not None and sorted(keys) != sorted(cfg["keys"]):
        problems.append(f"keys={keys} が設定の [compare] keys={cfg['keys']}（事前の宣言）と違う")
    keys = list(keys if keys is not None else cfg.get("keys") or [])
    live = [a for a in arms if not a.not_applicable]
    if len({a.name for a in arms}) != len(arms):
        problems.append("腕の名前が重複している")
    if not vary:
        problems.append("vary（変える軸）が空。比較は 1 軸を宣言して変える")
    if len(live) < 2:
        problems.append(f"対象外でない腕が {len(live)} 本（比較には 2 本以上）")
    else:
        problems += condition_diff(live, vary, rel_tol)
        common = set(live[0].conditions)
        if missing := [v for v in vary if v not in common]:
            problems.append(f"vary の軸 {missing} が腕の条件に無い")
        required = list((lab.get("compare") or {}).get("required") or [])
        if absent := [k for k in required if k not in common]:
            problems.append(f"lab.toml の [compare] required の条件 {absent} が腕に無い（明示して揃える）")
        if not missing and len({canonical([a.conditions[v] for v in vary]) for a in live}) < len(live):
            problems.append(f"vary={vary} の値が同じ腕がある（同じ条件の腕は比較にならない）")
    problems += sweep_problems(live, comparator_sweep)
    record = {
        "matched": not problems,
        "vary": vary,
        "keys": keys,
        "rel_tol": rel_tol,
        "arms": [
            {"name": a.name, "conditions": a.conditions, "fingerprint": fingerprint(a.conditions, vary)} for a in live
        ],
        "not_applicable": [{"name": a.name, "reason": a.not_applicable} for a in arms if a.not_applicable],
        "comparator_sweep": comparator_sweep or {},
        "diff": problems,
    }
    write_json_atomic(d / COMPARISON_FILE, json.loads(canonical(record)))
    if problems:
        raise ConditionMismatch("比較の条件がそろっていません（ceteris paribus）:\n  " + "\n  ".join(problems))
    return record


# ---- 引用と主張の照合（check L027・claim add）----
def read_comparison(run_dir: Path) -> dict | None:
    f = Path(run_dir) / COMPARISON_FILE
    try:
        return read_json(f) if f.is_file() else None
    except json.JSONDecodeError:
        return {"matched": False, "keys": [], "diff": ["comparison.json が壊れている"]}


def comparison_keys(root: Path, lab: dict, runs: dict[str, dict]) -> set[str]:
    """比較の鍵: lab.toml の [compare] keys、各 run の comparison.json の keys と設定の [compare] keys."""
    keys = set((lab.get("compare") or {}).get("keys") or [])
    for meta in runs.values():
        d = meta["_dir"]
        if c := read_comparison(d):
            keys |= set(c.get("keys") or [])
        if (d / "config.json").is_file():
            try:
                keys |= set((read_json(d / "config.json").get("compare") or {}).get("keys") or [])
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass
    return keys


def comparison_problem(run_dir: Path, key: str) -> str:
    """比較の鍵 key を run_dir から引用できない理由（空なら引用できる）."""
    c = read_comparison(run_dir)
    if c is None:
        return f"{key} は比較の指標だが、run に comparison.json が無い（run.compare で条件の同一性を宣言していない）"
    if c.get("matched") is not True:
        return f"{key} は比較の指標だが、run の比較は条件がそろっていない: " + "; ".join(
            c.get("diff") or ["matched=false"]
        )
    if key not in (c.get("keys") or []):
        return f"{key} はこの run の比較（keys={c.get('keys')}）で宣言された指標ではない"
    return ""
