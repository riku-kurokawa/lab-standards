"""人間への投稿（labkit post）: エージェントが「これは人間に伝える価値がある」と判断したことだけを、1 件ずつ書く.

    labkit post "<結論の 1 行>" --body "<何が分かり、なぜ重要で、何を見ればよいか>" \\
        [--fig <png>::<図で見るところ>] [--code src/pkg/x.py:40-62] [--run <id>] [--detail "<折りたたむ補足>"] \\
        [--kind finding|retract|ask|milestone] [--option "A 案" --option "B 案"]
    labkit post list

記録（拍・run・台帳）は機械が検証するためのもので、人間は読まない。人間が読むのは投稿だけ（`labkit view` のフィード）。
だから投稿は少なく、短く、根拠つきに保つ。それを文章の規約ではなくコマンドの拒否で守る:
  - 見出しは TITLE_MAX 字、本文は BODY_MAX 字まで（長い補足は --detail。折りたたまれる）
  - 見出しと本文に台帳の番号（M012・C185 など）を書かない（人間は覚えていない。中身を言葉で書く）
  - 発見と撤回には根拠が要る: 図・run・本文の引用 `値 [run:<id>:<key>]` のどれか
  - 本文と補足の引用は、その場で metrics.json と照合する（合わない数値は投稿できない）
  - 図には「見るところ」の一言が要る。図とコードの抜粋は投稿の時点の写しを持つ（後から変わらない）
  - 1 日の本数に上限（lab.toml の [post] per_day。既定 5）。超えるなら、どれが重要かを選び直す
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from labkit._util import git, read_json, write_json_atomic

POSTS_DIR = ".lab/posts"
KINDS = {"finding": "発見", "retract": "撤回", "ask": "相談", "milestone": "節目"}
TITLE_MAX = 60
BODY_MAX = 700
# 台帳の番号（M012・C185・Q031 など）。人間はこの番号を覚えていないので、見出しと本文では中身を言葉で書く
LEDGER_ID_RE = re.compile(r"(?<![A-Za-z0-9])[MCQSNP]\d{3,}(?![A-Za-z0-9])")
DETAIL_MAX = 3000
FIG_MAX = 3
FIG_BYTES = 1_500_000
CODE_LINES = 60
CITE_STRIP = re.compile(r"\[run:[^\]]*\]")
FIG_EXT = {".png", ".jpg", ".jpeg", ".svg", ".gif"}


def list_posts(root: Path) -> list[dict]:
    d = root / POSTS_DIR
    out = []
    for p in sorted(d.glob("P*.json")) if d.is_dir() else []:
        try:
            out.append(read_json(p))
        except (ValueError, OSError):
            continue
    return out


def _cites(root: Path, text: str) -> list[dict]:
    """本文の引用を metrics.json と照合する（L033 と同じ丸め）。合わなければ ValueError."""
    from labkit.check import CITE_RE, num_matches
    from labkit.runs import find_run

    out = []
    for m in CITE_RE.finditer(text):
        d = find_run(m.group("run"), root)
        vals = read_json(d / "metrics.json") if (d / "metrics.json").is_file() else {}
        key, num = m.group("key"), m.group("num").replace("−", "-")
        if key not in vals:
            raise ValueError(f"run {d.name} の metrics.json に {key} がありません（`labkit cite <run> <key>` で書く）")
        if not num_matches(num, vals[key]) and not (m.group("unit") == "%" and num_matches(num, vals[key] * 100)):
            raise ValueError(f"{num} は run {d.name} の {key} = {vals[key]} と一致しません（`labkit cite` で書く）")
        out.append({"run": d.name, "key": key, "value": vals[key]})
    if re.search(r"\[run:", CITE_RE.sub("", text)):
        raise ValueError("引用 [run:…] の直前に数値がありません（`値 [単位] [run:<id>:<key>]`。`labkit cite` で書く）")
    return out


def _code(root: Path, ref: str) -> dict:
    m = re.fullmatch(r"(.+?):(\d+)(?:-(\d+))?", ref)
    if not m:
        raise ValueError(f"--code は <path>:<開始行>-<終了行>（例 src/pkg/x.py:40-62）: {ref}")
    path, a = m.group(1).replace("\\", "/"), int(m.group(2))
    b = int(m.group(3) or a + CODE_LINES - 1)
    f = root / path
    if not f.is_file() or a < 1 or b < a:
        raise ValueError(f"--code のファイルか行の範囲がありません: {ref}")
    lines = f.read_text(encoding="utf-8", errors="replace").splitlines()[a - 1 : min(b, a + CODE_LINES - 1)]
    if not lines:
        raise ValueError(f"--code の行の範囲が空です: {ref}")
    commit = (git(root, "rev-parse", "--short", "HEAD") or "").strip()
    dirty = bool((git(root, "status", "--porcelain", "--", path) or "").strip())
    label = (
        f"{path}:{a}-{a + len(lines) - 1}" + (f" @ {commit}" if commit else "") + ("（未コミット）" if dirty else "")
    )
    return {"label": label, "text": "\n".join(lines).rstrip()}


def add_post(
    root: Path,
    title: str,
    body: str,
    *,
    kind: str = "finding",
    figs: list[str] | None = None,
    runs: list[str] | None = None,
    code: list[str] | None = None,
    options: list[str] | None = None,
    detail: str = "",
) -> dict:
    from labkit.config import load_lab
    from labkit.runs import find_run
    from labkit.state import _iso, _now, lab_dir

    title, body, detail = title.strip(), body.strip(), detail.strip()
    figs, runs, code, options = figs or [], runs or [], code or [], options or []
    if kind not in KINDS:
        raise ValueError(f"--kind は {' / '.join(KINDS)} のどれか")
    if not title or len(title) > TITLE_MAX or "\n" in title:
        raise ValueError(
            f"見出しは 1 行、{TITLE_MAX} 字まで（今 {len(title)} 字）。結論を書く（「〜を調べた」ではなく「〜だった」）"
        )
    shown = len(CITE_STRIP.sub("", body))  # 引用の記号は画面では ✓ になるので、字数に数えない
    if not body or shown > BODY_MAX:
        raise ValueError(f"本文は {BODY_MAX} 字まで（今 {shown} 字）。重要なことだけを残し、補足は --detail に回す")
    if ids := sorted(set(LEDGER_ID_RE.findall(title + "\n" + CITE_STRIP.sub("", body)))):
        raise ValueError(
            f"見出しと本文に台帳の番号（{'・'.join(ids)}）があります。人間は番号を覚えていません。"
            "中身を言葉で書きます（番号は --detail に書ける）"
        )
    if len(detail) > DETAIL_MAX:
        raise ValueError(f"--detail は {DETAIL_MAX} 字まで。それより長い内容は文書に書いて場所を示す")
    if len(figs) > FIG_MAX:
        raise ValueError(f"図は {FIG_MAX} 枚まで。いちばん伝わる図を選ぶ（足りなければ 1 枚にまとめた図を作る）")
    if options and kind != "ask":
        raise ValueError("--option は --kind ask（人間に選んでもらう相談）のときだけ")
    now = _now()
    day = _iso(now)[:10]
    posts = list_posts(root)
    limit = int(load_lab(root).get("post", {}).get("per_day", 5))
    today = [p for p in posts if str(p.get("created", "")).startswith(day)]
    if limit and len(today) >= limit:
        raise ValueError(
            f"今日の投稿は {len(today)} 本で上限（[post] per_day = {limit}）です。"
            "人間が読める量には限りがあります。次の投稿は明日にするか、より重要なことだけにします"
        )
    cites = _cites(root, body + "\n" + detail)
    run_ids = list(dict.fromkeys([find_run(r, root).name for r in runs] + [c["run"] for c in cites]))
    if kind in ("finding", "retract") and not (figs or run_ids):
        raise ValueError("根拠がありません。図（--fig）か run（--run）か、本文に引用 `値 [run:<id>:<key>]` を付けます")
    nums = [int(p["id"][1:]) for p in posts if str(p.get("id", "P"))[1:].isdigit()]
    pid = f"P{(max(nums) + 1) if nums else 1:03d}"
    parsed = []
    for k, spec in enumerate(figs):
        path, sep, caption = spec.partition("::")
        src = (root / path) if not Path(path).is_absolute() else Path(path)
        if not sep or not caption.strip():
            raise ValueError(f"図には見るところの一言が要ります: --fig {path}::<この図で何を見ればよいか>")
        if not src.is_file() or src.suffix.lower() not in FIG_EXT or src.stat().st_size > FIG_BYTES:
            raise ValueError(f"図がありません（{'・'.join(sorted(FIG_EXT))}、{FIG_BYTES // 1000} kB まで）: {path}")
        parsed.append((src, f"{k + 1}{src.suffix.lower()}", caption.strip()))
    snippets = [_code(root, c) for c in code]
    post = {"id": pid, "created": _iso(now), "kind": kind, "title": title, "body": body, "detail": detail}
    post.update(figs=[{"file": f"{pid}/{name}", "caption": cap} for _, name, cap in parsed])
    post.update(runs=run_ids, cites=cites, code=snippets, options=[o.strip() for o in options if o.strip()])
    for src, name, _ in parsed:  # 図は写しを持つ（scratch の図でも、後から描き直されても、投稿は変わらない）
        dest = lab_dir(root) / "posts" / pid / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
    write_json_atomic(lab_dir(root) / "posts" / f"{pid}.json", post)
    return post
