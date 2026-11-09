"""手順のチェックリスト（labkit flow）: 段階ごとの完了条件を機械的に検査して進める.

    labkit flow start migrate / status / advance / abort

状態は .lab/flows/<name>.json（git 管理）。定義は labkit/flows/<name>.toml。操作の禁止はしない。
"""

from __future__ import annotations

import csv
import json
import tomllib
from importlib import resources
from pathlib import Path

from labkit import state
from labkit._util import git, now_iso, read_json, write_json_atomic
from labkit.config import load_lab

ADVANCE = "labkit flow advance {name}"


def definitions() -> dict[str, dict]:
    out = {}
    for f in resources.files("labkit.flows").iterdir():
        if f.name.endswith(".toml"):
            d = tomllib.loads(f.read_text(encoding="utf-8"))
            out[d["name"]] = d
    return out


def _path(root: Path, name: str) -> Path:
    return state.lab_dir(root) / "flows" / f"{name}.json"


def load_state(root: Path, name: str) -> dict | None:
    p = _path(root, name)
    return read_json(p) if p.is_file() else None


def active_flows(root: Path) -> list[dict]:
    d = root / state.LAB_DIR / "flows"
    out = []
    for p in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            st = read_json(p)
        except (json.JSONDecodeError, OSError):
            continue
        if st.get("status") == "active":
            out.append(st)
    return out


def stage_def(st: dict, name: str | None = None) -> dict:
    return next(s for s in st["stages"] if s["name"] == (name or st["stage"]))


def next_stage(st: dict) -> dict | None:
    names = [s["name"] for s in st["stages"]]
    i = names.index(st["stage"])
    return st["stages"][i + 1] if i + 1 < len(names) else None


def start(root: Path, name: str) -> dict:
    defs = definitions()
    if name not in defs:
        raise SystemExit(f"flow {name!r} はありません。使える flow: {', '.join(sorted(defs))}")
    cur = load_state(root, name)
    if cur and cur.get("status") == "active":
        raise SystemExit(f"flow {name} は既に進行中（段階 {cur['stage']}）。`labkit flow status` / `labkit flow abort`")
    d = defs[name]
    st = {
        "flow": name,
        "description": d.get("description", ""),
        "status": "active",
        "stage": d["stage"][0]["name"],
        "started": now_iso(),
        "history": [{"stage": d["stage"][0]["name"], "at": now_iso(), "event": "start"}],
        "stages": [
            {
                "name": s["name"],
                "description": s.get("description", ""),
                "approval": bool(s.get("approval")),
                "done": list(s.get("done", [])),
            }
            for s in d["stage"]
        ],
    }
    write_json_atomic(_path(root, name), st)
    return st


def abort(root: Path, name: str) -> dict:
    st = load_state(root, name)
    if not st:
        raise SystemExit(f"flow {name} は開始されていません")
    st["status"] = "aborted"
    st["history"].append({"stage": st["stage"], "at": now_iso(), "event": "abort"})
    write_json_atomic(_path(root, name), st)
    return st


def unmet(root: Path, st: dict) -> list[str]:
    out = []
    for cond in stage_def(st)["done"]:
        fn = CONDITIONS.get(cond.get("type"))
        if fn is None:
            out.append(f"未知の条件 type={cond.get('type')!r}（flow 定義の誤り）")
            continue
        try:
            msg = fn(root, cond)
        except Exception as e:  # 条件の評価自体の失敗も「未達」として見せる
            msg = f"{cond.get('type')}: 評価に失敗（{type(e).__name__}: {e}）"
        if msg:
            out.append(msg)
    return out


def advance(root: Path, name: str) -> tuple[dict, str]:
    st = load_state(root, name)
    if not st or st.get("status") != "active":
        raise SystemExit(f"flow {name} は進行中ではありません（`labkit flow start {name}`）")
    cur, nxt = stage_def(st), next_stage(st)
    if nxt is None:
        raise SystemExit(f"flow {name} は最終段階 {cur['name']} です")
    if missing := unmet(root, st):
        raise SystemExit(
            f"段階 {cur['name']} の完了条件が満たされていません:\n" + "\n".join(f"  - {m}" for m in missing)
        )
    st["stage"] = nxt["name"]
    hist = {"stage": nxt["name"], "at": now_iso(), "event": "advance", "head": git(root, "rev-parse", "HEAD")}
    st["history"].append(hist)
    if next_stage(st) is None and not nxt["done"]:
        st["status"] = "finished"
    write_json_atomic(_path(root, name), st)
    return st, f"段階 {cur['name']} → {nxt['name']}"


def describe(root: Path, st: dict) -> str:
    cur = stage_def(st)
    lines = [f"flow {st['flow']}: 段階 {cur['name']}（{st['status']}）", f"  {cur['description']}"]
    missing = unmet(root, st) if st["status"] == "active" else []
    if missing:
        lines += ["  未達の条件:", *(f"    - {m}" for m in missing)]
    elif st["status"] == "active" and next_stage(st):
        lines.append(f"  完了条件はすべて満たしています → `labkit flow advance {st['flow']}`")
    names = [s["name"] for s in st["stages"]]
    lines.append("  段階: " + " → ".join(f"[{n}]" if n == cur["name"] else n for n in names))
    return "\n".join(lines)


# ---- 完了条件 ----
def c_clean_tree(root, c):
    out = git(root, "status", "--porcelain", "--untracked-files=no")
    if out is None:
        return "git リポジトリではありません（`git init` から始める）"
    return None if out == "" else "作業ツリーに未コミットの変更があります（すべて commit する）"


def c_git_tag(root, c):
    return (
        None
        if c["name"] in (git(root, "tag", "--list", c["name"]) or "").split()
        else (f"タグ {c['name']} がありません（`git tag {c['name']}` を打つ）")
    )


def c_file(root, c):
    return None if (root / c["path"]).is_file() else f"{c['path']} がありません"


def c_csv(root, c):
    p = root / c["path"]
    if not p.is_file():
        return f"{c['path']} がありません"
    with open(p, encoding="utf-8", newline="") as f:
        header = next(csv.reader(f), [])
    missing = [col for col in c.get("columns", []) if col not in header]
    return f"{c['path']} に必須列が不足: {missing}" if missing else None


def c_lab_mode(root, c):
    mode = load_lab(root)["check"]["mode"]
    return None if mode == c["value"] else f"lab.toml の [check] mode が {mode!r}（{c['value']!r} が必要。人間が編集）"


def c_manifest(root, c):
    from labkit.paths import datapath

    mf = datapath("raw", "MANIFEST.sha256", root=root)
    if not mf.is_file():
        return "data/raw/MANIFEST.sha256 がありません（`labkit raw freeze`）"
    lines = [ln for ln in mf.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    return None if lines else "MANIFEST.sha256 が空です（data/raw にデータを置いて `labkit raw freeze`）"


def c_check(root, c):
    from labkit.check import run_check

    errs = [i for i in run_check(root=root, ignore=set(c.get("ignore", [])))[0] if i.severity == "error"]
    return f"labkit check に {len(errs)} 件の違反（{', '.join(sorted({i.code for i in errs}))}）" if errs else None


def c_runs(root, c):
    from labkit.runs import list_runs

    n = len([m for m in list_runs(root) if m.get("status") == "finished"])
    return None if n >= int(c.get("min", 1)) else f"finished の run が {n} 件（{c.get('min', 1)} 件以上必要）"


def c_review(root, c):
    from labkit.reviews import latest_pass

    head = git(root, "rev-parse", "HEAD")
    if latest_pass(root, "migrate", c["stage"], head):
        return None
    return f"現在の HEAD（{(head or '')[:7]}）に対する lab-reviewer の pass 記録がありません（docs/reviews/<date>_migrate_{c['stage']}.md）"


def c_mirror(root, c):
    p = root / state.LAB_DIR / "mirror.json"
    if not p.is_file():
        return "写しがありません（`labkit mirror push --to <写し先> --paths <管理外データのディレクトリ...>`）"
    m = read_json(p)
    return None if Path(m["dest"]).is_dir() else f"写し先 {m['dest']} が見つかりません"


CONDITIONS = {
    "clean_tree": c_clean_tree,
    "git_tag": c_git_tag,
    "file": c_file,
    "csv": c_csv,
    "lab_mode": c_lab_mode,
    "manifest": c_manifest,
    "check": c_check,
    "runs": c_runs,
    "review": c_review,
    "mirror": c_mirror,
}
