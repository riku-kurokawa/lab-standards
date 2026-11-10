"""人間の入口（labkit digest）: 研究代表者が 15 分で読む 1 枚 docs/DIGEST.md を、台帳と run から同じコードで作る.

    labkit digest [--since <YYYY-MM-DD | commit>]   既定: 直近 digest.days 日（既定 2）

自律開発のボトルネックは人間のレビューなので、人間の判断が要る順に並べる:
先に見るもの（違反・崩れた主張・撤回・期限切れ・外れた予想・新しい連絡・失敗に使った計算）/ 主張（根拠の値と、それを生んだコード）/
予想と結果 / 新しい図 / レビューするコード / 主線と芽・資源 / 人間への連絡 / run の収支 / 未解消のレビュー / check / 文献 / 文書。
節は材料があるときだけ出す。`labkit beat end` が digest.refresh_hours ごとに作り直すので、人間が開いたときに古くない。
図は docs/assets/digest/ に写す（git で見える。上限 digest.max_figures）。DIGEST 自身は引用の照合（L032）の対象外。
"""

from __future__ import annotations

import datetime as _dt
import re
import shutil
from pathlib import Path

from labkit._util import git, read_json, write_text_atomic
from labkit.config import load_lab


def _since(root: Path, since: str | None) -> tuple[str, str]:
    """(日付 ISO, 基準 commit)。--since は日付か commit."""
    lab = load_lab(root)
    if since and re.fullmatch(r"[0-9a-f]{7,40}", since):
        return (git(root, "log", "-1", "--format=%cI", since) or "")[:19], since
    if not since:  # 自動で作り直すので「前回の DIGEST 以降」では窓が数時間に縮む。人間が読む間隔（日）で切る
        days = float(lab["digest"].get("days", 2))
        since = (_dt.datetime.now() - _dt.timedelta(days=days)).isoformat(timespec="seconds")
    base = git(root, "rev-list", "-1", f"--before={since}", "HEAD") or ""
    return since, base


def staleness(root: Path, *, announce_missing: bool = True) -> str | None:
    """SessionStart の 1 行: DIGEST が古ければ知らせる（無ければ案内）。日付は DIGEST の 1 行目（生成時刻）から読む."""
    lab = load_lab(root)
    p = root / lab["digest"]["file"]
    if not p.is_file():
        if not announce_missing:
            return None
        return f"- 人間の入口 {lab['digest']['file']} がまだ無い（1 日 1 回、人間が読む前に `labkit digest`）"
    with open(p, encoding="utf-8", errors="replace") as f:
        m = re.match(r"# DIGEST（(\d{4}-\d{2}-\d{2})", f.readline())
    when = m.group(1) if m else (git(root, "log", "-1", "--format=%cI", "--", lab["digest"]["file"]) or "")[:10]
    today = _dt.date.today().isoformat()
    return (
        None if when == today else f"- {lab['digest']['file']} は {when or '未 commit'} 版。今日の分は `labkit digest`"
    )


def refresh_if_stale(root: Path) -> Path | None:
    """DIGEST が digest.refresh_hours（既定 6、0 で無効）より古ければ作り直す。`labkit beat end` が呼ぶ
    （「1 日 1 回作る」という規則は守られず、人間が開くと数日前の版だった）."""
    lab = load_lab(root)
    hours = float(lab["digest"].get("refresh_hours", 6) or 0)
    if hours <= 0:
        return None
    p = root / lab["digest"]["file"]
    if p.is_file():
        with open(p, encoding="utf-8", errors="replace") as f:
            m = re.match(r"# DIGEST（(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", f.readline())
        if m:
            age = _dt.datetime.now() - _dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M")
            if age.total_seconds() < hours * 3600:
                return None
    return build(root)


def _claim_code(root: Path, evidence: str) -> str:
    """主張の根拠の run を生んだコード: entry と commit（人間がレビューするのは、主張を支えるこのコード）."""
    from labkit.check import RUN_ID_RE
    from labkit.runs import find_run

    seen, out = set(), []
    for rid in RUN_ID_RE.findall(evidence):
        if rid in seen:
            continue
        seen.add(rid)
        try:
            d = find_run(rid, root)
            meta, cfg = read_json(d / "meta.json"), read_json(d / "config.json")
        except Exception:  # noqa: BLE001 - 根拠の run が無い・壊れているのは L036 が知らせる
            continue
        commit = ((meta.get("git") or {}).get("commit") or "")[:7]
        out.append(f"`{cfg.get('entry') or meta.get('name')}` @ {commit or '?'}")
    return "、".join(out[:3])


def _code_to_review(root: Path, base: str) -> list[str]:
    """レビューするコード: src の変更をファイルごとに（増減の大きい順）。対応する試験が同じ期間に変わっていないものに印."""
    stat = git(root, "diff", "--numstat", base, "--", "src", "tests") if base else ""
    rows, tests = [], []
    for ln in (stat or "").splitlines():
        a, d, path = ln.split("\t", 2)
        if path.endswith(".py"):
            row = (int(a) if a.isdigit() else 0, int(d) if d.isdigit() else 0, path)
            (tests if path.startswith("tests/") else rows).append(row)
    if not rows:
        return []
    rows.sort(key=lambda r: -(r[0] + r[1]))
    tested = " ".join(Path(p).stem for _, _, p in tests)
    out = []
    for a, d, path in rows[:10]:
        stem = Path(path).stem
        mark = "" if stem == "__init__" or stem in tested else " — **試験の変更なし**"
        out.append(f"- `{path}` +{a} −{d}{mark}")
    if len(rows) > 10:
        out.append(f"- …ほか {len(rows) - 10} ファイル")
    out.append(f"- 差分を見る: `git diff {base[:7]} HEAD -- src tests`")
    return out


def _runs_since(root: Path, since: str) -> list[dict]:
    from labkit.runs import list_runs

    return [m for m in list_runs(root, include_archived=True) if str(m.get("created", "")) >= since]


def _figures(root: Path, since: str, lab: dict) -> list[str]:
    from labkit.paths import runs_root

    out, n, seen = [], 0, set()
    assets = root / lab["digest"]["assets"]
    shutil.rmtree(assets, ignore_errors=True)  # 前回の写しは消す（原本は run に、過去の写しは git の履歴にある）
    for fm in sorted(runs_root(root).glob("*/figures/*.figmeta.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            meta = read_json(fm)
            run_meta = read_json(fm.parent.parent / "meta.json")
        except Exception:
            continue
        if str(meta.get("created", "")) < since or run_meta.get("archived") or fm.name in seen:
            continue  # 退避した run の図と、同じ図の古い版（同名は最新の run だけ）は載せない
        seen.add(fm.name)
        png = fm.with_name(fm.name.replace(".figmeta.json", ".png"))
        if not png.is_file():
            continue
        rid = fm.parent.parent.name
        title = ((meta.get("spec") or {}).get("labels") or {}).get("title") or meta.get("spec", {}).get(
            "name", png.stem
        )
        desc = (meta.get("spec") or {}).get("description", "")
        n += 1
        if n <= int(lab["digest"]["max_figures"]):
            assets.mkdir(parents=True, exist_ok=True)
            dst = assets / f"{rid[-4:]}_{png.name}"
            shutil.copy2(png, dst)
            rel = dst.relative_to(root).as_posix()
            out.append(f"![{title}]({rel})\n*{title}* — run `{rid}`" + (f"。{desc}" if desc else ""))
    if n > int(lab["digest"]["max_figures"]):
        out.append(f"- …ほか {n - int(lab['digest']['max_figures'])} 枚（runs/*/figures。digest.max_figures）")
    return out


def _days(day: str) -> list[str]:
    """day（YYYY-MM-DD）から今日までの日付（撤回の備考にある日付と突き合わせる）."""
    d0, out = _dt.date.fromisoformat(day), []
    while d0 <= _dt.date.today() and len(out) < 60:
        out.append(d0.isoformat())
        d0 += _dt.timedelta(days=1)
    return out


def _docs_changed(root: Path, base: str) -> list[str]:
    stat = git(root, "diff", "--numstat", base, "--", "docs", "prompts", "literature/surveys") if base else ""
    rows = []
    for ln in (stat or "").splitlines():
        a, d, path = ln.split("\t", 2)
        if path.endswith(".md") and not path.endswith("DIGEST.md"):
            rows.append((int(a) if a.isdigit() else 0, int(d) if d.isdigit() else 0, path))
    rows.sort(key=lambda r: -(r[0] + r[1]))
    return [f"- `{p}` +{a} −{d}" for a, d, p in rows[:15]] + (
        [f"- …ほか {len(rows) - 15} 件"] if len(rows) > 15 else []
    )


def build(root: Path, since: str | None = None) -> Path:
    from labkit import state
    from labkit.check import run_check
    from labkit.claims import list_claims
    from labkit.devlog import code_volume
    from labkit.literature import list_surveys, read_frontmatter, reading_queue
    from labkit.reviews import format_reviews, open_reviews
    from labkit.runs import archive_candidates

    lab = load_lab(root)
    since_iso, base = _since(root, since)
    day = since_iso[:10]
    head = (git(root, "rev-parse", "--short", "HEAD") or "?") + ("*" if git(root, "status", "--porcelain") else "")
    L = [f"# DIGEST（{_dt.datetime.now().strftime('%Y-%m-%d %H:%M')}、{day} 以降、HEAD {head}）", ""]
    L += ["> `labkit digest` が台帳と run から生成。手で編集しない。詳細は各ファイルへ。", ""]

    issues, mode = run_check(root=root)  # 1 回だけ走らせ、各節で使う
    errs = [i for i in issues if i.severity == "error"]
    claims = list_claims(root)
    new = [c for c in claims if c["date"] >= day]
    broken = [i for i in issues if i.code == "L036"]
    runs = _runs_since(root, since_iso)
    judged = [m for m in runs if m.get("prediction_result")]
    missed: dict[tuple, list[dict]] = {}  # 同じ根拠の外れは 1 行にまとめる（配列ジョブの 5 本が 5 行にならない）
    for m in judged:
        pr = m["prediction_result"]
        if pr.get("verdict") in ("miss", "partial"):
            basis = m["prediction"].get("basis", "") if isinstance(m["prediction"], dict) else str(m["prediction"])
            missed.setdefault((pr.get("verdict"), basis[:120]), []).append(m)
    items = state.pending_summary(root)["open_questions"]
    fresh_q = [it for it in items if str(it.get("created", "")) >= since_iso]
    from labkit.focus import digest_lines, spend

    failed_h = sum(d.get("failed", 0) for d in spend(root).values())

    # 先に見るもの: 人間の判断が要る順。ここが空なら、残りは流し読みでよい
    top = []
    if errs:
        top.append(f"- **違反 {len(errs)} 件**（{', '.join(sorted({i.code for i in errs}))}）: `labkit check`")
    top += [f"- **根拠が崩れた主張**: {i.where} {i.message}" for i in broken[:5]]
    retract_re = re.compile(r"撤回 (?:" + "|".join(_days(day)) + r"): ?(.*)$")
    retracted = [
        (c, m.group(1).strip()) for c in claims if c["status"] == "retracted" and (m := retract_re.search(c["note"]))
    ]
    top += [f"- **撤回** {c['id']} {c['text'][:70]}… — 理由: {why[:120]}" for c, why in retracted[:5]]
    if len(retracted) > 5:
        top.append(f"- **撤回** ほか {len(retracted) - 5} 件（`labkit claim list --status retracted`）")
    top += [f"- **期限切れ**: {i.message}" for i in issues if i.code == "L025"][:5]
    if missed:
        top.append(f"- 外れた予想 {sum(len(v) for v in missed.values())} 件（{len(missed)} 種。下の「予想と結果」）")
    if fresh_q:
        top.append(f"- 新しい連絡 {len(fresh_q)} 件（仮の判断で進行中。下の「人間への連絡」）")
    if failed_h >= 1:
        top.append(f"- 直近 24 時間に失敗した計算 {failed_h:.1f} 時間（下の「主線と芽」）")
    none = "- 特になし（違反・崩れた主張・撤回・期限切れ・外れた予想・新しい連絡は無い）"
    L += ["## 先に見るもの", "", *(top or [none]), ""]

    # 主張: 新しい主張と、その根拠を生んだコード
    if claims:
        n_open = sum(c["status"] == "open" for c in claims)
        L += [f"## 主張（open {n_open} / 撤回 {len(claims) - n_open}）", ""]
        for c in (new or claims)[-8:]:
            L.append(f"- {c['id']} {'撤回 ' if c['status'] == 'retracted' else ''}{c['text']} ← {c['evidence']}")
            if c["status"] == "open" and (code := _claim_code(root, c["evidence"])):
                L.append(f"  - コード: {code}")
        if len(new) > 8:
            L.append(f"- …ほか {len(new) - 8} 件（`labkit claim list`）")
        L.append("")

    # 予想と結果
    if judged or any(m.get("prediction") for m in runs):
        tally: dict[str, int] = {}
        for m in judged:
            v = m["prediction_result"].get("verdict", "?")
            tally[v] = tally.get(v, 0) + 1
        selfrep = sum(1 for m in judged if m["prediction_result"].get("self_reported"))
        unjudged = [
            m for m in runs if m.get("prediction") and not m.get("prediction_result") and m.get("status") == "finished"
        ]
        L += ["## 予想と結果", ""]
        L.append(
            "- 判定: "
            + (", ".join(f"{k} {v}" for k, v in sorted(tally.items())) or "なし")
            + (f"（自己申告 {selfrep}）" if selfrep else "")
        )
        for (verdict, basis), ms in list(missed.items())[:6]:
            pr = ms[0]["prediction_result"]
            L.append(
                f"- ✗ {ms[0]['name']}"
                + (f" ほか {len(ms) - 1} 本" if len(ms) > 1 else "")
                + f" `{ms[0]['run_id']}` {verdict} {pr.get('hit', '')}/{pr.get('total', '')} — 予想の根拠: {basis}"
            )
        if unjudged:
            L.append(f"- 未判定 {len(unjudged)} 件（`labkit runs verdict`）")
        if tally.get("undeterminable"):
            L.append(f"- 判定できなかった予想 {tally['undeterminable']} 件（予想の key が metrics に無い。L024）")
        L.append("")

    # 図
    figs = _figures(root, since_iso, lab)
    if figs:
        L += ["## 新しい図", ""] + [f + "\n" for f in figs]

    # コード
    code = _code_to_review(root, base)
    if code:
        L += ["## レビューするコード", "", *code, code_volume(root, base or since_iso), ""]

    # 主線と芽・人間への連絡
    L += digest_lines(root, day)
    if items:
        L += ["## 人間への連絡（返事は待たずに進めている。新しい順）", ""]
        L += [
            f"- #{it['id']} {str(it.get('question'))[:120]}（判断: {str(it.get('assumed'))[:60]}）"
            for it in reversed(items[-8:])
        ]
        L += [f"- …ほか {len(items) - 8} 件（`labkit queue list`）"] if len(items) > 8 else []
        L.append("")

    # run の収支
    if runs:
        by: dict[str, int] = {}
        for m in runs:
            by[m.get("status", "?")] = by.get(m.get("status", "?"), 0) + 1
        dirty = sum(1 for m in runs if (m.get("git") or {}).get("dirty"))
        archived = sum(1 for m in runs if m.get("archived"))
        cands = archive_candidates(statuses=("failed", "interrupted"), root=root)
        L += ["## run の収支", ""]
        L.append("- " + ", ".join(f"{k} {v}" for k, v in sorted(by.items())) + f"、dirty {dirty}、退避 {archived}")
        if cands:
            L.append(
                f"- 退避の候補（failed/interrupted）{len(cands)} 件: `labkit runs archive --status failed,interrupted`"
            )
        L.append("")

    # レビュー
    opens = open_reviews(root)
    if opens:
        L += ["## 未解消のレビュー", ""] + [f"- {ln}" for ln in format_reviews(root, opens[-8:]).splitlines()]
        L += ([f"- …ほか {len(opens) - 8} 件（`labkit review list --open`）"] if len(opens) > 8 else []) + [""]

    # check
    if issues:
        cnt: dict[str, int] = {}
        for i in issues:
            cnt[i.code] = cnt.get(i.code, 0) + 1
        L += ["## labkit check", ""]
        L.append(
            f"- 違反 {len(errs)}、警告 {len(issues) - len(errs)}（mode={mode}）: "
            + ", ".join(f"{k} {v}" for k, v in sorted(cnt.items()))
        )
        L.append("")

    # 文献
    notes_dir = root / lab["literature"]["dir"] / "notes"
    added = []
    for n in sorted(notes_dir.glob("*.md")) if notes_dir.is_dir() else []:
        fm = read_frontmatter(n)[0] or {}
        if str(fm.get("added", "")) >= day:
            added.append(f"{n.stem}（{fm.get('status')}, {fm.get('read_by', 'agent')}）")
    queue = reading_queue(root, lab, min_relevance=4)[:5]
    surveys = [sv for sv in list_surveys(root, lab) if str(sv.get("date", "")) >= day]
    if added or queue or surveys:
        L += ["## 文献", ""]
        if added:
            L.append(f"- 追加 {len(added)} 件: " + ", ".join(added[:8]) + ("…" if len(added) > 8 else ""))
        L += [
            f"- サーベイ {sv['date']} {sv['question']}: {sv.get('verdict') or '判定なし'}（{sv.get('n_opened', 0)} 件を開いた）"
            for sv in surveys
        ]
        if queue:
            L.append(
                "- 人間の読書キュー（relevance ≥ 4）: "
                + "; ".join(f"{q['citekey']} — {q['claim'] or q['title'][:40]}" for q in queue)
            )
        L.append("")

    # 文書
    changed = _docs_changed(root, base)
    if changed:
        L += ["## 変更された文書", "", *changed, ""]
    if not code:
        L += [code_volume(root, base or since_iso), ""]

    out = root / lab["digest"]["file"]
    write_text_atomic(out, "\n".join(L).rstrip() + "\n")
    return out
