"""人間の入口（labkit digest）: 研究代表者が 15 分で読む 1 枚 docs/DIGEST.md を、台帳と run から同じコードで作る.

    labkit digest [--since <YYYY-MM-DD | commit>]   既定: DIGEST.md を最後に commit した時点（無ければ 7 日前）

節は材料があるときだけ出す: 主張の変化 / 予想と結果 / run の収支 / 新しい図 / 未解消のレビュー / 承認待ち・質問 /
check の集計 / 文献 / 変更された文書とコード量。長い devlog・state・レビュー記録は読まずに済む。
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
    if since is None:
        since = (git(root, "log", "-1", "--format=%cI", "--", lab["digest"]["file"]) or "")[:19]
    if not since:
        since = (_dt.datetime.now() - _dt.timedelta(days=7)).isoformat(timespec="seconds")
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

    issues, mode = run_check(root=root)  # 1 回だけ走らせ、主張の節と check の節で使う

    # 主張
    claims = list_claims(root)
    new = [c for c in claims if c["date"] >= day]
    broken = [i for i in issues if i.code == "L036"]
    if claims:
        L += [
            f"## 主張（open {sum(c['status'] == 'open' for c in claims)} / 撤回 {sum(c['status'] == 'retracted' for c in claims)}）",
            "",
        ]
        L += [
            f"- {c['id']} {'撤回 ' if c['status'] == 'retracted' else ''}{c['text']} ← {c['evidence']}"
            for c in (new or claims)[-8:]
        ]
        L += [f"- ⚠ 根拠が崩れた: {i.where} {i.message}" for i in broken[:5]]
        L.append("")

    # 予想と結果
    runs = _runs_since(root, since_iso)
    judged = [m for m in runs if m.get("prediction_result")]
    if judged or any(m.get("prediction") for m in runs):
        tally: dict[str, int] = {}
        for m in judged:
            v = m["prediction_result"].get("verdict", "?")
            tally[v] = tally.get(v, 0) + 1
        selfrep = sum(1 for m in judged if m["prediction_result"].get("self_reported"))
        unjudged = [
            m for m in runs if m.get("prediction") and not m.get("prediction_result") and m.get("status") == "finished"
        ]
        trivial = sum(
            1 for m in runs if isinstance(m.get("prediction"), dict) and m["prediction"].get("expert_predictable")
        )
        L += ["## 予想と結果", ""]
        L.append(
            "- 判定: "
            + (", ".join(f"{k} {v}" for k, v in sorted(tally.items())) or "なし")
            + (f"（自己申告 {selfrep}）" if selfrep else "")
        )
        for m in [m for m in judged if m["prediction_result"].get("verdict") in ("miss", "partial")][:5]:
            pr = m["prediction_result"]
            basis = m["prediction"].get("basis", "") if isinstance(m["prediction"], dict) else str(m["prediction"])[:80]
            L.append(
                f"- ✗ {m['name']} `{m['run_id']}` {pr.get('verdict')} {pr.get('hit', '')}/{pr.get('total', '')} — 予想の根拠: {basis}"
            )
        if unjudged:
            L.append(f"- 未判定 {len(unjudged)} 件（`labkit runs verdict`）")
        if trivial:
            L.append(
                f"- 専門家なら予測できる（expert_predictable）と自認した run: {trivial} 件（なぜ計算したかは basis）"
            )
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

    # 図
    figs = _figures(root, since_iso, lab)
    if figs:
        L += ["## 新しい図", ""] + [f + "\n" for f in figs]

    # レビュー
    opens = open_reviews(root)
    if opens:
        L += ["## 未解消のレビュー", ""] + [f"- {ln}" for ln in format_reviews(root, opens[:8]).splitlines()]
        L += ([f"- …ほか {len(opens) - 8} 件（`labkit review list --open`）"] if len(opens) > 8 else []) + [""]

    # queue
    s = state.pending_summary(root)
    items = s["pending"] + s["open_questions"]
    if items:
        L += ["## 人間を待っているもの", ""]
        L += [f"- #{it['id']} 承認待ち: `{str(it.get('command'))[:100]}`" for it in s["pending"][:8]]
        L += [
            f"- #{it['id']} 質問: {str(it.get('question'))[:120]}（仮の判断: {str(it.get('assumed'))[:60]}）"
            for it in s["open_questions"][:8]
        ]
        L += [f"- …ほか {len(items) - 16} 件（`labkit queue list`）"] if len(items) > 16 else []
        L.append("")

    # check
    if issues:
        cnt: dict[str, int] = {}
        for i in issues:
            cnt[i.code] = cnt.get(i.code, 0) + 1
        errs = sum(1 for i in issues if i.severity == "error")
        L += ["## labkit check", ""]
        L.append(
            f"- 違反 {errs}、警告 {len(issues) - errs}（mode={mode}）: "
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

    # 文書とコード
    changed = _docs_changed(root, base)
    L += ["## 変更された文書とコード量", ""] + changed + [code_volume(root, base or since_iso), ""]

    out = root / lab["digest"]["file"]
    write_text_atomic(out, "\n".join(L).rstrip() + "\n")
    return out
