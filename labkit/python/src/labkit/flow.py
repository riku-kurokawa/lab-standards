"""手順の状態機械（labkit flow）.

    labkit flow start migrate | improve-standards
    labkit flow status
    labkit flow advance        # 完了条件を検査し、満たしていれば次の段階へ（承認が要る段階はキューへ）
    labkit flow abort

状態は .lab/flows/<name>.json（git 管理）。定義は labkit/flows/<name>.toml（宣言的）。
start 時に定義を状態ファイルへ写すので、hooks（claude-plugin/scripts/_labstate.py）は状態ファイルだけを読めばよい。
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import tomllib
from importlib import resources
from pathlib import Path

from labkit import state
from labkit._util import now_iso, write_json_atomic
from labkit.config import load_lab
from labkit.state import active_flows  # noqa: F401  （cli が flow.active_flows として参照。実体は _labstate）

ADVANCE_COMMAND = "labkit flow advance {name}"


def approval_key(name: str, stage: str) -> str:
    """承認を結び付ける鍵。HEAD ではなく段階に結び付ける（承認後に commit しても承認が無効にならない）."""
    return f"flow:{name}:{stage}"


# ---- 定義 ----
def definitions() -> dict[str, dict]:
    out = {}
    for f in resources.files("labkit.flows").iterdir():
        if f.name.endswith(".toml"):
            d = tomllib.loads(f.read_text(encoding="utf-8"))
            out[d["name"]] = d
    return out


def _flows_dir(root: Path) -> Path:
    d = state.lab_dir(root) / "flows"
    d.mkdir(exist_ok=True)
    return d


def _state_path(root: Path, name: str) -> Path:
    return _flows_dir(root) / f"{name}.json"


def load_state(root: Path, name: str) -> dict | None:
    p = _state_path(root, name)
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save_state(root: Path, st: dict) -> None:
    write_json_atomic(_state_path(root, st["flow"]), st)


def stage_def(st: dict, name: str | None = None) -> dict:
    name = name or st["stage"]
    for s in st["stages"]:
        if s["name"] == name:
            return s
    raise KeyError(name)


def next_stage(st: dict) -> dict | None:
    names = [s["name"] for s in st["stages"]]
    i = names.index(st["stage"])
    return st["stages"][i + 1] if i + 1 < len(names) else None


# ---- 操作 ----
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
                "approval": bool(s.get("approval", False)),
                "forbid": list(s.get("forbid", [])),
                "done": list(s.get("done", [])),
            }
            for s in d["stage"]
        ],
    }
    save_state(root, st)
    return st


def abort(root: Path, name: str) -> dict:
    st = load_state(root, name)
    if not st:
        raise SystemExit(f"flow {name} は開始されていません")
    st["status"] = "aborted"
    st["history"].append({"stage": st["stage"], "at": now_iso(), "event": "abort"})
    save_state(root, st)
    return st


EXPENSIVE = {"standards_tests", "standards_released"}  # テスト実行・ネットワーク。status では省く


def unmet(root: Path, st: dict, quick: bool = False) -> list[str]:
    """現在の段階の、まだ満たしていない完了条件（人間が読める文）."""
    out = []
    for cond in stage_def(st)["done"]:
        if quick and cond.get("type") in EXPENSIVE:
            out.append(f"{cond['type']}: advance 時に検査（status では省略）")
            continue
        fn = CONDITIONS.get(cond.get("type"))
        if fn is None:
            out.append(f"未知の条件 type={cond.get('type')!r}（flow 定義の誤り）")
            continue
        try:
            msg = fn(root, st, cond)
        except Exception as e:  # 条件の評価自体の失敗も「未達」として見せる
            msg = f"{cond.get('type')}: 評価に失敗（{type(e).__name__}: {e}）"
        if msg:
            out.append(msg)
    return out


def advance(root: Path, name: str, session_id: str = "") -> tuple[dict, str]:
    """次の段階へ。戻り値 (状態, メッセージ)。進めないときは SystemExit."""
    st = load_state(root, name)
    if not st or st.get("status") != "active":
        raise SystemExit(f"flow {name} は進行中ではありません（`labkit flow start {name}`）")
    cur = stage_def(st)
    nxt = next_stage(st)
    if nxt is None:
        raise SystemExit(f"flow {name} は最終段階 {cur['name']} です")
    missing = unmet(root, st)
    if missing:
        raise SystemExit(
            f"段階 {cur['name']} の完了条件が満たされていません:\n" + "\n".join(f"  - {m}" for m in missing)
        )
    via = None
    if cur["approval"]:
        cmd = ADVANCE_COMMAND.format(name=name)
        key = approval_key(name, cur["name"])
        rec = state.find_valid_approval(root, cmd, key)
        deleg = state.find_delegation(root, "flow")
        if rec is not None:
            state.consume_approval(root, rec)
            via = f"approval:{rec['id']}"
        elif deleg is not None:
            via = f"delegation:{deleg['id']}"
        else:
            session_id = session_id or os.environ.get("CLAUDE_CODE_SESSION_ID", "")
            item = state.request_approval(
                root,
                cmd,
                cwd=root,
                session_id=session_id,
                reason=f"flow {name}: 段階 {cur['name']} → {nxt['name']} の承認",
                head=key,
            )
            raise SystemExit(
                f"段階 {cur['name']} から進むには人間の承認が必要です。承認待ち #{item['id']} として記録しました。\n"
                f"この操作に依存しない作業を続け、終了時の報告に挙げてください。人間: `labkit approve {item['id']}`"
                f"（この承認は段階に結び付き、commit しても無効になりません）。`labkit delegate flow` で委任することもできます"
            )
    st["stage"] = nxt["name"]
    hist = {"stage": nxt["name"], "at": now_iso(), "event": "advance", "head": state.git_head(root)}
    if via:
        hist["via"] = via
    st["history"].append(hist)
    if next_stage(st) is None and not nxt["done"]:
        st["status"] = "finished"
    save_state(root, st)
    return st, f"段階 {cur['name']} → {nxt['name']}"


def describe(root: Path, st: dict) -> str:
    cur = stage_def(st)
    lines = [f"flow {st['flow']}: 段階 {cur['name']}（{st['status']}）", f"  {cur['description']}"]
    if cur["forbid"]:
        lines.append(f"  この段階で禁止: {', '.join(cur['forbid'])}")
    if cur["approval"]:
        lines.append("  次へ進むには人間の承認が必要（labkit flow advance → キュー → labkit approve）")
    missing = unmet(root, st, quick=True) if st["status"] == "active" else []
    if missing:
        lines.append("  未達の条件:")
        lines += [f"    - {m}" for m in missing]
    elif st["status"] == "active" and next_stage(st):
        lines.append(f"  完了条件はすべて満たしています → `labkit flow advance {st['flow']}`")
    names = [s["name"] for s in st["stages"]]
    lines.append("  段階: " + " → ".join(f"[{n}]" if n == cur["name"] else n for n in names))
    return "\n".join(lines)


# ---- 完了条件 ----
def _git(root: Path, *args: str) -> str | None:
    try:
        return subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=True, encoding="utf-8", errors="replace"
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _standards_dev(root: Path) -> Path | None:
    from labkit.standards import status

    st = status(root)
    if st.python_mode == "link" and st.python_ref:
        p = Path(st.python_ref)
        for d in (p, *p.parents):
            if (d / "copier.yml").is_file():
                return d
    env = os.environ.get("LAB_STANDARDS_DEV")
    cand = Path(env).expanduser() if env else Path.home() / "dev" / "lab-standards"
    return cand if (cand / "copier.yml").is_file() else None


def c_clean_tree(root, st, c):
    out = _git(root, "status", "--porcelain", "--untracked-files=no")
    if out is None:
        return "git リポジトリではありません（`git init` から始める）"
    return None if out == "" else "作業ツリーに未コミットの変更があります（すべて commit する）"


def c_git_tag(root, st, c):
    tags = (_git(root, "tag", "--list", c["name"]) or "").split()
    return None if c["name"] in tags else f"タグ {c['name']} がありません（`git tag {c['name']}` は承認ゲートの対象）"


def c_file(root, st, c):
    return None if (root / c["path"]).is_file() else f"{c['path']} がありません"


def c_csv(root, st, c):
    p = root / c["path"]
    if not p.is_file():
        return f"{c['path']} がありません"
    with open(p, encoding="utf-8", newline="") as f:
        header = next(csv.reader(f), [])
    missing = [col for col in c.get("columns", []) if col not in header]
    return f"{c['path']} に必須列が不足: {missing}" if missing else None


def c_lab_mode(root, st, c):
    mode = load_lab(root)["check"]["mode"]
    return None if mode == c["value"] else f"lab.toml の [check] mode が {mode!r}（{c['value']!r} が必要。人間が編集）"


def c_manifest(root, st, c):
    from labkit.paths import datapath

    mf = datapath("raw", "MANIFEST.sha256", root=root)
    if not mf.is_file():
        return "data/raw/MANIFEST.sha256 がありません（人間が `labkit raw freeze`）"
    lines = [ln for ln in mf.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    return None if lines else "MANIFEST.sha256 が空です（data/raw にデータを置いて `labkit raw freeze`）"


def c_check(root, st, c):
    from labkit.check import run_check

    issues, _ = run_check(root=root, ignore=set(c.get("ignore", [])))
    errs = [i for i in issues if i.severity == "error"]
    return f"labkit check に {len(errs)} 件の違反（{', '.join(sorted({i.code for i in errs}))}）" if errs else None


def c_runs(root, st, c):
    from labkit.runs import list_runs

    n = len([m for m in list_runs(root) if m.get("status") == "finished"])
    return None if n >= int(c.get("min", 1)) else f"finished の run が {n} 件（{c.get('min', 1)} 件以上必要）"


def c_review(root, st, c):
    from labkit.reviews import latest_pass

    stage = c.get("stage", st["stage"])
    target = root
    if c.get("repo") == "standards":  # レビュー対象が本体の差分なら本体の HEAD に結び付ける
        target = _standards_dev(root)
        if target is None:
            return "lab-standards 本体のチェックアウトが見つかりません"
    head = state.git_head(target)
    r = latest_pass(root, st["flow"], stage, head)
    return (
        None
        if r
        else (
            f"{'本体' if target != root else '現在'}の HEAD（{(head or '')[:7]}）に対する lab-reviewer の pass 記録がありません"
            f"（docs/reviews/<date>_{st['flow']}_{stage}.md）"
        )
    )


def c_devlog_today(root, st, c):
    import datetime as _dt

    lab = load_lab(root)
    p = root / lab["devlog"]["dir"] / f"{_dt.date.today().isoformat()}.md"
    return None if p.is_file() else f"今日の開発ログ {p.relative_to(root)} がありません（`labkit devlog`）"


def c_linked(root, st, c):
    from labkit.standards import status

    want = bool(c.get("value", True))
    if status(root).linked == want:
        return None
    return (
        "labkit standards link が必要です" if want else "link が残っています（`labkit standards unlink --to vX.Y.Z`）"
    )


def c_linked_if_touched(root, st, c):
    """本体の差分が labkit/ などに触れているなら、プロジェクトが link していること（試さずに済ませる失敗を防ぐ）."""
    from labkit.standards import status

    dev = _standards_dev(root)
    if dev is None:
        return "lab-standards 本体のチェックアウトが見つかりません（$LAB_STANDARDS_DEV か ~/dev/lab-standards）"
    files = (_git(dev, "diff", "--name-only", "main...HEAD") or "").splitlines()
    prefixes = tuple(c.get("paths", ["labkit/"]))
    if not any(f.startswith(prefixes) for f in files):
        return None
    try:
        linked = status(root).linked
    except (FileNotFoundError, OSError):  # pyproject.toml が無い＝link していない
        linked = False
    return (
        None
        if linked
        else f"本体の {'/'.join(prefixes)} を変えているので `labkit standards link` でこのプロジェクトから試す必要があります"
    )


def c_standards_branch(root, st, c):
    dev = _standards_dev(root)
    if dev is None:
        return "lab-standards 本体のチェックアウトが見つかりません（$LAB_STANDARDS_DEV か ~/dev/lab-standards）"
    br = _git(dev, "rev-parse", "--abbrev-ref", "HEAD") or ""
    return (
        None
        if br.startswith(c.get("prefix", "feat/"))
        else f"本体のブランチが {br!r}（{c.get('prefix', 'feat/')}* で作業する）"
    )


def c_standards_ahead(root, st, c):
    dev = _standards_dev(root)
    if dev is None:
        return "lab-standards 本体のチェックアウトが見つかりません"
    n = _git(dev, "rev-list", "--count", "main..HEAD")
    try:
        n = int(n or 0)
    except ValueError:
        n = 0
    return None if n >= int(c.get("min", 1)) else f"本体のブランチに main から {n} commit（{c.get('min', 1)} 以上必要）"


def c_standards_tests(root, st, c):
    dev = _standards_dev(root)
    if dev is None:
        return "lab-standards 本体のチェックアウトが見つかりません"
    cmds = [
        (
            [
                "uv",
                "run",
                "--project",
                str(dev / "labkit" / "python"),
                "--extra",
                "dev",
                "pytest",
                "-q",
                str(dev / "labkit" / "python" / "tests"),
            ],
            dev,
        ),
        (["uv", "run", "--with", "pytest", "pytest", "-q", str(dev / "claude-plugin" / "tests")], dev),
    ]
    for cmd, cwd in cmds:
        r = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, check=False, encoding="utf-8", errors="replace"
        )
        if r.returncode != 0:
            return "本体のテストが失敗: " + " ".join(cmd[-2:]) + "\n" + (r.stdout + r.stderr).strip()[-1500:]
    return None


def c_standards_released(root, st, c):
    dev = _standards_dev(root)
    if dev is None:
        return "lab-standards 本体のチェックアウトが見つかりません"
    import re

    text = (dev / "labkit" / "python" / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version = "([^"]+)"', text, re.M)
    if not m:
        return "本体の版が読めません"
    tag = f"v{m.group(1)}"
    tags = (_git(dev, "tag", "--list", tag) or "").split()
    if tag not in tags:
        return f"本体にタグ {tag} がありません（人間が承認してから git tag / push）"
    remote = _git(dev, "ls-remote", "--tags", "origin", tag) or ""
    return None if remote else f"タグ {tag} が origin に push されていません"


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
    "devlog_today": c_devlog_today,
    "linked": c_linked,
    "linked_if_touched": c_linked_if_touched,
    "standards_branch": c_standards_branch,
    "standards_ahead": c_standards_ahead,
    "standards_tests": c_standards_tests,
    "standards_released": c_standards_released,
}
