""".lab/ 状態（presence・承認待ちキュー・承認記録・flow の状態）の読み書き。標準ライブラリのみ.

正本はこのファイル（claude-plugin/scripts/_labstate.py）。labkit/python/src/labkit/_labstate.py はそのバイト同一のコピーで、
テスト（test_harness.py::test_vendored_labstate_is_identical）が一致を検査する。
hooks はここで「読む」「承認待ちを積む」「承認を使用済みにする」だけを行う。承認記録を新規に作るのは labkit approve（人間）だけ。
委任（.lab/delegations.json）も同じ: 作る・取り消すのは labkit delegate（人間）だけで、hooks は読んで照合するだけ。
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
from pathlib import Path

LAB_DIR = ".lab"
DEFAULT_PRESENCE = "away"
GITIGNORE = (
    "# labkit が生成。presence・queue・approvals・delegations は手元だけの状態（flows/ は git 管理）\n"
    "presence\nqueue/\napprovals/\ndelegations.json\n"
)

# ---- 委任（delegation）----
# 人間が `labkit delegate <category...> --hours N` で宣言する。期間内はそのカテゴリの操作を承認待ちに積まず通す
# （承認ゲートの対象、flow の承認段階、data/raw への搬入、lab.toml の mode 切替）。承認と違い、コマンド全文や
# HEAD には結び付かない。取り返しのつかない操作を「人間が不在でも進めてよい」と決めるのは人間だけ（Claude は実行できない）。
DELEGATABLE = {
    "git_push": "git push（リモートの変更）",
    "git_tag": "git tag の作成・削除",
    "git_merge": "保護ブランチへの merge",
    "gh_merge": "gh pr merge",
    "gh_release": "gh release の作成・変更",
    "raw_freeze": "labkit raw freeze（生データの確定）",
    "template": "copier copy/update・labkit standards template（雛形の適用）",
    "flow": "labkit flow advance の承認段階（承認を待たずに進む）",
    "raw_write": "data/raw へのファイルの移動・追加（生データの搬入。削除は含まない）",
    "lab_toml": "lab.toml の変更（`labkit mode warn|strict` と編集）",
}
DELEGATION_GROUPS = {
    "release": ["git_push", "git_tag", "git_merge", "gh_merge", "gh_release"],
    "migrate": ["flow", "raw_write", "raw_freeze", "lab_toml", "template"],
    "all": list(DELEGATABLE),
}
DELEGATIONS_FILE = "delegations.json"


# ---- lab.toml の既定値（唯一の定義。labkit の config.load_lab と hooks の load_lab が共有する） ----
DEFAULTS: dict = {
    "lab": {"project": ""},
    "layout": {
        "allowed": [
            "README.md",
            "CLAUDE.md",
            "lab.toml",
            "pyproject.toml",
            "uv.lock",
            "Makefile",
            ".gitignore",
            ".gitattributes",
            ".pre-commit-config.yaml",
            ".copier-answers.yml",
            ".python-version",
            ".claude",
            ".git",
            ".venv",
            ".mlflow",
            ".pytest_cache",
            ".ruff_cache",
            "src",
            "scripts",
            "jl",
            "configs",
            "tests",
            "data",
            "runs",
            "notebooks",
            "figspecs",
            "jobs",
            "docs",
            "literature",
            "prompts",
            "scratch",
            "legacy",
            ".lab",
        ],
        "writable": [
            "src",
            "scripts",
            "jl",
            "configs",
            "tests",
            "figspecs",
            "jobs",
            "docs",
            "literature",
            "prompts",
            "scratch",
            "notebooks",
            "README.md",
            "CLAUDE.md",
            "pyproject.toml",
            "Makefile",
            ".gitignore",
        ],
        "readonly": ["data/raw", "legacy"],
    },
    "check": {
        "mode": "strict",
        "banned_plot_imports": [
            "matplotlib",
            "seaborn",
            "plotly",
            "bokeh",
            "altair",
            "pylab",
            "Plots",
            "Makie",
            "CairoMakie",
            "GLMakie",
            "WGLMakie",
            "PyPlot",
            "Gadfly",
            "UnicodePlots",
            "PlotlyJS",
        ],
        "plot_import_allowed": [],
        "banned_formats": ["pickle", "cPickle", "dill", "joblib", "cloudpickle", "JLD2", "BSON"],
        "format_allowed": [],
        "abs_path_patterns": [
            r"/home/\w",
            r"/Users/\w",
            r"[A-Za-z]:\\\\",
            r"/lustre",
            r"/gpfs",
            r"/scratch/",
            r"/work/",
            r"/groups/",
        ],
        "code_dirs": ["src", "scripts", "jl", "tests", "notebooks"],
        "figure_ok_dirs": ["docs/assets", "literature/pdfs", "literature/inbox", "scratch"],
        "data_ok_dirs": ["tests/fixtures", "scratch"],
        "skip": [],
        # L033: run ID と同じ行にある書式なしの数値を警告する（"warn" | "off"）
        "cite_bare_numbers": "warn",
    },
    "devlog": {
        "dir": "docs/devlog",
        "required_headings": [
            "目的",
            "実施内容",
            "変更ファイル",
            "実行した run",
            "結果・観察",
            "判断と理由",
            "未解決・次の作業",
        ],
    },
    "adr": {
        "dir": "docs/decisions",
        "required_headings": ["背景", "決定", "理由と検討した代替案", "影響"],
    },
    "runs": {"hash_inputs_max_gb": 2.0},
    "literature": {"dir": "literature", "pdf_dir": "literature/pdfs"},
    "claude": {"require_devlog": True, "max_stop_blocks": 3},
    # 承認ゲート（claude-plugin の hooks と labkit flow / approve が読む）
    "gate": {
        "enabled": True,
        "protected_branches": ["main", "master"],
        "approval_ttl_hours": 24,
    },
}


def deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def find_scope(start: str | os.PathLike | None) -> tuple[Path, str] | None:
    """(root, "project" | "standards") を返す。どちらでもなければ None."""
    if start is None:
        return None
    p = Path(start).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    p = p.resolve()
    while not p.exists():
        p = p.parent
    if p.is_file():
        p = p.parent
    for d in (p, *p.parents):
        if (d / "lab.toml").is_file():
            return d, "project"
        if (d / "copier.yml").is_file() and (
            d / "labkit" / "python"
        ).is_dir():  # lab-standards 本体（labkit_source と同じ判定）
            return d, "standards"
    return None


def _now() -> _dt.datetime:
    return _dt.datetime.now().astimezone()


def _iso(t: _dt.datetime) -> str:
    return t.isoformat(timespec="seconds")


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def lab_dir(root: Path) -> Path:
    d = root / LAB_DIR
    d.mkdir(exist_ok=True)
    gi = d / ".gitignore"
    if not gi.is_file():
        gi.write_text(GITIGNORE, encoding="utf-8", newline="\n")
    return d


def get_presence(root: Path) -> str:
    f = root / LAB_DIR / "presence"
    if f.is_file():
        v = f.read_text(encoding="utf-8").strip()
        if v in ("here", "away"):
            return v
    return DEFAULT_PRESENCE


def git(cwd: Path, *args: str) -> str | None:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def git_head(cwd: Path) -> str | None:
    return git(cwd, "rev-parse", "HEAD")


def git_branch(cwd: Path) -> str | None:
    return git(cwd, "rev-parse", "--abbrev-ref", "HEAD")


def list_queue(root: Path) -> list[dict]:
    d = root / LAB_DIR / "queue"
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("Q*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return out


def next_id(root: Path) -> str:
    nums = []
    for d in (root / LAB_DIR / "queue", root / LAB_DIR / "approvals"):
        if d.is_dir():
            nums += [int(p.stem[1:]) for p in d.glob("Q*.json") if p.stem[1:].isdigit()]
    return f"Q{(max(nums) + 1) if nums else 1:03d}"


def request_approval(
    root: Path, command: str, *, cwd: Path, reason: str, session_id: str = "", head: str | None = None
) -> dict:
    """承認待ちを積む。head を渡すと HEAD の代わりにそれに結び付ける（flow の承認は段階に結び付ける: `flow:<name>:<stage>`）."""
    head = head or git_head(cwd)
    for it in list_queue(root):
        if (
            it.get("kind") == "approval"
            and it.get("status") == "pending"
            and it.get("command") == command
            and it.get("head") == head
        ):
            return it
    diff = git(cwd, "diff", "--stat", "HEAD") or ""
    lines = diff.splitlines()
    summary = lines[-1].strip() if lines else "変更なし"
    log = git(cwd, "log", "--oneline", "-3") or ""
    item = {
        "id": next_id(root),
        "kind": "approval",
        "status": "pending",
        "command": command,
        "cwd": str(cwd),
        "branch": git_branch(cwd),
        "head": head,
        "diff_summary": f"作業ツリー: {summary}; 直近の commit: {log.replace(chr(10), ' / ')}",
        "reason": reason,
        "created": _iso(_now()),
        "session_id": session_id,
    }
    _write_json(lab_dir(root) / "queue" / f"{item['id']}.json", item)
    return item


def find_valid_approval(root: Path, command: str, head: str | None, now: _dt.datetime | None = None) -> dict | None:
    """コマンド全文と HEAD が一致し、未使用かつ期限内の承認を返す."""
    d = root / LAB_DIR / "approvals"
    if not d.is_dir():
        return None
    now = now or _now()
    for p in sorted(d.glob("Q*.json")):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if rec.get("command") != command or rec.get("head") != head or rec.get("used_at"):
            continue
        try:
            if _dt.datetime.fromisoformat(rec["expires_at"]) < now:
                continue
        except (KeyError, ValueError):
            continue
        return rec
    return None


def consume_approval(root: Path, rec: dict) -> None:
    rec["used_at"] = _iso(_now())
    _write_json(root / LAB_DIR / "approvals" / f"{rec['id']}.json", rec)
    q = root / LAB_DIR / "queue" / f"{rec['id']}.json"
    if q.is_file():
        try:
            it = json.loads(q.read_text(encoding="utf-8"))
            it.update(status="executed", executed=rec["used_at"])
            _write_json(q, it)
        except (json.JSONDecodeError, OSError):
            pass


def expand_delegation(names: list[str]) -> list[str]:
    """グループ名（release / migrate / all）を展開し、未知の名前は ValueError."""
    out: list[str] = []
    for n in names:
        if n in DELEGATION_GROUPS:
            out += DELEGATION_GROUPS[n]
        elif n in DELEGATABLE:
            out.append(n)
        else:
            raise ValueError(
                f"委任できないカテゴリ: {n!r}（使えるもの: {', '.join([*DELEGATABLE, *DELEGATION_GROUPS])}）"
            )
    return list(dict.fromkeys(out))


def list_delegations(root: Path) -> list[dict]:
    p = root / LAB_DIR / DELEGATIONS_FILE
    if not p.is_file():
        return []
    try:
        return list(json.loads(p.read_text(encoding="utf-8")).get("items", []))
    except (json.JSONDecodeError, OSError, AttributeError):
        return []


def _save_delegations(root: Path, items: list[dict]) -> None:
    _write_json(lab_dir(root) / DELEGATIONS_FILE, {"items": items})


def delegation_active(d: dict, now: _dt.datetime | None = None) -> bool:
    now = now or _now()
    if d.get("revoked_at"):
        return False
    try:
        return _dt.datetime.fromisoformat(d["expires_at"]) >= now
    except (KeyError, ValueError):
        return False


def active_delegations(root: Path, now: _dt.datetime | None = None) -> list[dict]:
    return [d for d in list_delegations(root) if delegation_active(d, now)]


def find_delegation(root: Path, category: str, now: _dt.datetime | None = None) -> dict | None:
    """category を含む有効な委任（期限内・未取り消し）。無ければ None."""
    for d in active_delegations(root, now):
        if category in d.get("categories", []):
            return d
    return None


def add_delegation(root: Path, categories: list[str], *, hours: float, note: str = "", who: dict | None = None) -> dict:
    items = list_delegations(root)
    now = _now()
    d = {
        "id": f"D{len(items) + 1:03d}",
        "categories": expand_delegation(categories),
        "note": note,
        "granted_at": _iso(now),
        "expires_at": _iso(now + _dt.timedelta(hours=hours)),
        "revoked_at": None,
        **(who or {}),
    }
    items.append(d)
    _save_delegations(root, items)
    return d


def revoke_delegation(root: Path, did: str) -> list[dict]:
    """`all` で全部。取り消した委任を返す."""
    items = list_delegations(root)
    hit = []
    for d in items:
        if (did == "all" or d.get("id") == did) and not d.get("revoked_at"):
            d["revoked_at"] = _iso(_now())
            hit.append(d)
    if not hit:
        raise FileNotFoundError(f"有効な委任 {did} がありません（`labkit delegate list`）")
    _save_delegations(root, items)
    return hit


def describe_delegations(root: Path) -> list[str]:
    return [
        f"{d['id']}: {', '.join(d['categories'])}（期限 {d['expires_at']}"
        + (f"、{d['note']}" if d.get("note") else "")
        + "）"
        for d in active_delegations(root)
    ]


def active_flows(root: Path) -> list[dict]:
    d = root / LAB_DIR / "flows"
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        try:
            st = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if st.get("status") == "active":
            out.append(st)
    return out


def current_stage(st: dict) -> dict:
    for s in st.get("stages", []):
        if s.get("name") == st.get("stage"):
            return s
    return {"name": st.get("stage"), "forbid": [], "description": "", "approval": False}


def pending_summary(root: Path) -> dict[str, list[dict]]:
    q = list_queue(root)
    return {
        "pending": [i for i in q if i.get("kind") == "approval" and i.get("status") == "pending"],
        "approved": [i for i in q if i.get("kind") == "approval" and i.get("status") == "approved"],
        "open_questions": [i for i in q if i.get("kind") == "question" and i.get("status") == "open"],
        "answered": [i for i in q if i.get("kind") == "question" and i.get("status") == "answered"],
        "rejected": [i for i in q if i.get("kind") == "approval" and i.get("status") == "rejected"],
    }


def load_gate_conf(root: Path, kind: str) -> dict:
    conf = dict(DEFAULTS["gate"])
    if kind == "project":
        try:
            import tomllib

            with open(root / "lab.toml", "rb") as f:
                user = tomllib.load(f).get("gate", {})
            if isinstance(user, dict):
                conf = deep_merge(conf, user)
        except (OSError, ValueError):  # ImportError は握りつぶさない（3.11 未満は _labcommon が止める）
            pass
    return conf
