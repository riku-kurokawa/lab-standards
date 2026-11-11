"""レビュー板（labkit view）: 人間がエージェントの仕事を、証拠つきのカードとタイムラインで確認し、1 クリックで返信する.

    labkit view [--days 3] [--port 8765]     手元の 127.0.0.1 で開く（返信できる）
    labkit view --out review.html            1 枚の HTML に書き出す（図は埋め込み。返信はできない）

エージェントは報告を書かない。板は、エージェントが仕事のために残した記録（拍の 3 行・run・図・主張の台帳・人間への連絡・commit）から
同じコードで作る（盛れない。文脈も使わない）。並びは 2 つ:
  要確認      人間の判断が要るもの。主線の項目（成果物）ごとの束 1 枚に、新しい主張・撤回・外れた予想・代表の図・生んだコードを持つ。
              人間への連絡は 1 件 1 枚。返信（OK / 質問 / 違う + 一言）を付けたカードは「確認済み」に移り、新しい主張が足されると戻る。
              残りの枚数が、人間のレビューの残り。
  タイムライン 拍ごとの予想・結果・判断と、その拍の run・図・commit（差分は開くと出る）。記録の確認用。
人間の返信は `.lab/notes/`（git 管理）に残り、次の `labkit beat start` の先頭に出る。エージェントは `labkit note done <ID> --reply ...` で答える。
"""

from __future__ import annotations

import base64
import datetime as _dt
import json
import re
from importlib import resources
from pathlib import Path

from labkit._util import git, read_json

MAX_EMBED = 40  # --out で埋め込む図の上限（超えた分は図なしで出す）
FIG_BYTES = 600_000
DIFF_LINES = 400


def _fig(reg: list[Path], p: Path) -> int:
    reg.append(p)
    return len(reg) - 1


def _run_figs(reg: list[Path], d: Path, limit: int = 3) -> list[dict]:
    out = []
    for png in sorted((d / "figures").glob("*.png"))[:limit] if (d / "figures").is_dir() else []:
        fm = png.with_name(png.stem + ".figmeta.json")
        spec = (read_json(fm).get("spec") or {}) if fm.is_file() else {}
        title = (spec.get("labels") or {}).get("title") or spec.get("name") or png.stem
        out.append({"i": _fig(reg, png), "title": str(title), "desc": str(spec.get("description", ""))[:200]})
    return out


def _entry_code(root: Path, d: Path, meta: dict) -> dict | None:
    """根拠の run を生んだ entry の関数（その commit の版）の冒頭."""
    try:
        entry = str(read_json(d / "config.json").get("entry") or "")
    except Exception:  # noqa: BLE001
        return None
    commit = (meta.get("git") or {}).get("commit") or ""
    if ":" not in entry or not commit:
        return None
    mod, func = entry.split(":", 1)
    path = "src/" + mod.replace(".", "/") + ".py"
    text = git(root, "show", f"{commit}:{path}")
    if not text:
        return None
    lines = text.splitlines()
    start = next((k for k, ln in enumerate(lines) if re.match(rf"def {re.escape(func)}\b", ln)), None)
    if start is None:
        return None
    end = next((k for k in range(start + 1, len(lines)) if re.match(r"(def |class |@)", lines[k])), len(lines))
    body = lines[start : min(end, start + 40)]
    return {"label": f"{path}:{start + 1} @ {commit[:7]}", "text": "\n".join(body).rstrip()}


def _commits(root: Path, since: str) -> list[dict]:
    out = git(root, "log", f"--since={since}", "--format=%x1e%H%x1f%cI%x1f%s", "--numstat") or ""
    rows = []
    for block in out.split("\x1e")[1:]:
        head, _, stat = block.partition("\n")
        h, when, subject = head.split("\x1f", 2)
        add = dele = 0
        files = []
        for ln in stat.splitlines():
            parts = ln.split("\t")
            if len(parts) == 3:
                add += int(parts[0]) if parts[0].isdigit() else 0
                dele += int(parts[1]) if parts[1].isdigit() else 0
                files.append(parts[2])
        code = [f for f in files if f.startswith(("src/", "tests/", "scripts/", "configs/"))]
        rows.append({"h": h[:10], "time": when[:19], "subject": subject, "add": add, "del": dele, "files": code[:8]})
        rows[-1]["n_files"] = len(files)
    return rows


def commit_diff(root: Path, h: str) -> str:
    """commit の差分（コードと設定だけ、先頭 DIFF_LINES 行）."""
    if not re.fullmatch(r"[0-9a-f]{7,40}", h):
        return ""
    text = git(root, "show", "--format=%h %s", "--stat", "--patch", h, "--", "src", "tests", "scripts", "configs") or ""
    lines = text.splitlines()
    more = f"\n… ほか {len(lines) - DIFF_LINES} 行（git show {h}）" if len(lines) > DIFF_LINES else ""
    return "\n".join(lines[:DIFF_LINES]) + more


def collect(root: Path, days: float = 3) -> tuple[dict, list[Path]]:
    """板に出す状態（JSON にできる dict）と、図のファイルの一覧（番号で引く）."""
    from labkit import focus, state
    from labkit.beat import read_beats
    from labkit.check import RUN_ID_RE
    from labkit.claims import list_claims
    from labkit.config import load_lab
    from labkit.paths import runs_root
    from labkit.runs import list_runs

    now = _dt.datetime.now()
    since = (now - _dt.timedelta(days=days)).isoformat(timespec="seconds")
    day = since[:10]
    reg: list[Path] = []
    rr = runs_root(root)
    runs = {m["run_id"]: m for m in list_runs(root, include_archived=True) if m.get("run_id")}

    def run_brief(rid: str) -> dict:
        m = runs.get(rid) or {}
        pr = m.get("prediction_result") or {}
        return {
            "id": rid,
            "name": m.get("name", rid),
            "status": m.get("status", "?"),
            "verdict": pr.get("verdict", ""),
            "hit": f"{pr.get('hit')}/{pr.get('total')}" if pr.get("total") else "",
            "serves": m.get("serves", ""),
            "min": round(float(m.get("duration_s") or 0) / 60, 1),
        }

    main = focus.read_main(root)
    main_what = {i["id"]: i["what"] for i in main["items"]}

    def group_key(rids: list[str]) -> str:
        """束の単位: run が紐づく主線の項目（serves）。無ければ run の名前の先頭 2 語（同じ実験の系列）."""
        ms = [runs[r] for r in rids if r in runs]
        for m in ms:
            if re.fullmatch(r"M\d{3,}", str(m.get("serves") or "")):
                return str(m["serves"])
        return ("-".join(str(ms[0].get("name", "")).split("-")[:2]) if ms else "") or "その他"

    # 主張 1 件 1 枚では人間は捌けない（1 日に 200 件を超える台帳がある）。成果物（主線の項目）ごとに束ね、束に 1 回で返信する
    groups: dict[str, dict] = {}

    def put(item: dict, rids: list[str]) -> None:
        g = groups.setdefault(group_key(rids), {"items": [], "rids": []})
        g["items"].append(item)
        g["rids"] += [r for r in rids if r in runs and r not in g["rids"]]

    for c in list_claims(root):
        retracted = c["status"] == "retracted"
        when = (re.search(r"撤回 (\d{4}-\d{2}-\d{2})", c["note"]) or [None, c["date"]])[1] if retracted else c["date"]
        if when < day:
            continue
        item = {"id": f"claim:{c['id']}", "kind": "retract" if retracted else "claim", "time": when}
        item.update(text=f"{c['id']} {c['text']}", evidence=c["evidence"], note=c["note"])
        put(item, list(dict.fromkeys(RUN_ID_RE.findall(c["evidence"]))))
    missed: dict[tuple, list[dict]] = {}
    for m in runs.values():
        pr = m.get("prediction_result") or {}
        if str(m.get("created", "")) >= since and pr.get("verdict") in ("miss", "partial") and not m.get("archived"):
            pred = m.get("prediction")
            basis = pred.get("basis", "") if isinstance(pred, dict) else str(pred)
            missed.setdefault((pr["verdict"], basis[:160]), []).append(m)
    for (verdict, basis), ms in missed.items():
        m = ms[-1]
        rows = [r for r in (m["prediction_result"].get("rows") or []) if r.get("hit") is False][:4]
        item = {"id": f"miss:{m['run_id']}", "kind": "miss", "time": str(m.get("created", ""))[:10]}
        item["text"] = f"外れた予想（{verdict}）: {m.get('name')}" + (f" ほか {len(ms) - 1} 本" if len(ms) > 1 else "")
        item.update(evidence=f"予想の根拠: {basis}", note="、".join(f"{r['key']} = {r['value']:.4g}" for r in rows))
        put(item, [m["run_id"]])
    order = {"retract": 0, "miss": 1, "claim": 2}
    cards = []
    for key, g in groups.items():
        rids = sorted(g["rids"], reverse=True)  # 新しい run から
        figs: list[dict] = []
        codes: list[dict] = []
        for rid in rids[:8]:
            if len(figs) < 3:
                figs += _run_figs(reg, rr / rid, 2)
            code = _entry_code(root, rr / rid, runs[rid]) if len(codes) < 2 else None
            if code and code["label"].split(":")[0] not in {c["label"].split(":")[0] for c in codes}:
                codes.append(code)
        items = sorted(g["items"], key=lambda i: (order[i["kind"]], i["id"]))
        card = {"id": f"group:{key}", "kind": "group", "time": max(i["time"] for i in items), "items": items}
        card["title"] = f"{key} {main_what[key]}" if key in main_what else f"{key}（主線の項目に紐づかない run）"
        card["counts"] = {k: sum(i["kind"] == k for i in items) for k in order}
        card.update(figs=figs[:3], codes=codes, runs=[run_brief(r) for r in rids[:6]], n_runs=len(rids))
        cards.append(card)
    cards.sort(key=lambda c: c["time"], reverse=True)
    cards.sort(
        key=lambda c: c["counts"]["retract"] + c["counts"]["miss"] == 0
    )  # 撤回・外れのある束を先に（安定ソート）
    questions = state.pending_summary(root)["open_questions"]
    old_q = [q for q in questions if str(q.get("created", "")) < since]  # 古い連絡は件数だけ（`labkit queue list`）
    for q in reversed([q for q in questions if str(q.get("created", "")) >= since]):
        card = {"id": f"queue:{q['id']}", "kind": "question", "time": str(q.get("created", ""))[:19]}
        card.update(title=f"{q['id']} {q.get('question')}", body=f"仮の判断で進行中: {q.get('assumed')}")
        card.update(meta=[f"変更時の影響: {q['impact']}"] if q.get("impact") else [], options=q.get("options") or [])
        cards.append(card)

    # タイムライン: 拍ごとに、その拍の窓（前の拍の終わり〜この拍の終わり）の run と commit を束ねる
    ends = []
    d0 = _dt.date.fromisoformat(day)
    while d0 <= now.date():
        ends += [b for b in read_beats(root, d0.isoformat()) if b.get("event") == "end" and b.get("time", "") >= since]
        d0 += _dt.timedelta(days=1)
    commits = _commits(root, since)
    recent = sorted((m for m in runs.values() if str(m.get("created", "")) >= since), key=lambda m: str(m["created"]))
    timeline, prev = [], since
    for b in ends:
        t = b["time"][:19]
        rids = list(
            dict.fromkeys(
                [*(b.get("runs") or []), *(m["run_id"] for m in recent if prev < str(m["created"])[:19] <= t)]
            )
        )
        figs = [f for rid in rids if rid in runs for f in _run_figs(reg, rr / rid, 2)][:4]
        item = {"id": f"beat:{t[:10]}#{b.get('beat')}", "time": t, "line": b.get("line", ""), "beat": b.get("beat")}
        item.update(predicted=b.get("predicted", ""), observed=b.get("observed", ""), decided=b.get("decided", ""))
        item.update(stall=b.get("stall_reason", ""), runs=[run_brief(r) for r in rids[:8]], figs=figs)
        item["commits"] = [c for c in commits if prev < c["time"] <= t]
        timeline.append(item)
        prev = t
    loose = [c for c in commits if c["time"] > prev]
    if loose:
        item = {
            "id": f"loose:{prev}",
            "time": loose[0]["time"],
            "line": "",
            "beat": None,
            "predicted": "",
            "observed": "",
        }
        item.update(decided="（拍の外の commit）", stall="", runs=[], figs=[], commits=loose)
        timeline.append(item)

    notes: dict[str, list[dict]] = {}
    for n in state.list_notes(root):
        notes.setdefault(n["target"], []).append(n)
    data = {
        "project": load_lab(root)["lab"].get("project") or root.name,
        "generated": now.strftime("%Y-%m-%d %H:%M"),
        "since": since[:16].replace("T", " "),
        "head": (git(root, "rev-parse", "--short", "HEAD") or "?"),
        "mainline": {
            "sentence": main["sentence"],
            "items": [{k: i[k] for k in ("id", "what", "due", "status")} for i in main["items"]],
        },
        "cards": cards,
        "timeline": list(reversed(timeline)),
        "notes": notes,
        "old_questions": len(old_q),
        "writable": False,
    }
    return data, reg


def render(data: dict, reg: list[Path], *, embed: bool) -> str:
    """1 枚の HTML。embed なら図を data URI で埋め込む（--out）。そうでなければ図は /fig/<番号> から読む."""
    if embed:
        uris = []
        for k, p in enumerate(reg):
            ok = k < MAX_EMBED and p.is_file() and p.stat().st_size <= FIG_BYTES
            uris.append("data:image/png;base64," + base64.b64encode(p.read_bytes()).decode() if ok else "")
        data = {**data, "fig_uris": uris}
    page = resources.files("labkit.templates").joinpath("view.html").read_text(encoding="utf-8")
    return page.replace("/*STATE*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))


def serve(root: Path, port: int = 8765, days: float = 3) -> None:
    """127.0.0.1 だけで待ち受ける。状態は読むたびに作り直す（常に最新）。返信は .lab/notes/ に書く."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from labkit import state

    figs: list[Path] = []

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            nonlocal figs
            if self.path in ("/", "/index.html"):
                data, figs = collect(root, days)
                data["writable"] = True
                self._send(200, render(data, figs, embed=False).encode("utf-8"), "text/html; charset=utf-8")
            elif m := re.fullmatch(r"/fig/(\d+)", self.path):
                k = int(m.group(1))
                if k < len(figs) and figs[k].is_file():
                    self._send(200, figs[k].read_bytes(), "image/png")
                else:
                    self._send(404, b"", "text/plain")
            elif m := re.fullmatch(r"/diff/([0-9a-f]{7,40})", self.path):
                self._send(200, commit_diff(root, m.group(1)).encode("utf-8"), "text/plain; charset=utf-8")
            else:
                self._send(404, b"", "text/plain")

        def do_POST(self) -> None:  # noqa: N802
            host = (self.headers.get("Host") or "").split(":")[0]
            if self.path != "/note" or host not in ("127.0.0.1", "localhost"):
                return self._send(403, b"", "text/plain")
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                note = state.add_note(
                    root,
                    str(body["target"]),
                    str(body.get("verdict", "")),
                    str(body.get("text", "")),
                    covers=[str(x) for x in body.get("covers") or []],
                )
            except (ValueError, KeyError) as e:
                return self._send(400, str(e).encode("utf-8"), "text/plain; charset=utf-8")
            self._send(200, json.dumps(note, ensure_ascii=False).encode("utf-8"), "application/json")

        def log_message(self, *a) -> None:  # 端末を埋めない
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"レビュー板: http://127.0.0.1:{port}/  （Ctrl+C で止める。返信は .lab/notes/ に残り、次の拍の先頭に出る）")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
