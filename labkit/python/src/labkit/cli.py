"""labkit コマンド."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from importlib import resources
from pathlib import Path

from labkit._version import __version__


def _tpl(name: str) -> str:
    return resources.files("labkit.templates").joinpath(name).read_text(encoding="utf-8")


def _scope_root() -> Path:
    from labkit.config import find_scope

    sc = find_scope()
    if sc is None:
        raise SystemExit("lab.toml のあるプロジェクトか lab-standards 本体の中で実行してください")
    return sc[0]


def cmd_check(a) -> int:
    from labkit.check import run_check

    issues, mode = run_check(full=a.full, ignore=set(a.ignore or []), claims=a.claims)
    mode = "warn" if a.warn else "strict" if a.strict else mode
    errors = [i for i in issues if i.severity == "error"]
    if a.json:
        print(json.dumps([vars(i) for i in issues], ensure_ascii=False, indent=2))
    else:
        for i in issues:
            print(i)
        print(
            f"\nlabkit check: {len(errors)} 件の違反、{len(issues) - len(errors)} 件の警告（mode={mode}）"
            if issues
            else "labkit check: 違反なし ✓"
        )
    return 1 if errors and mode == "strict" else 0


def cmd_fig(a) -> int:
    from labkit.viz import list_templates, render

    if a.spec == "list":
        print(list_templates())
        return 0
    for p in render(a.spec, run_id=a.run, out_dir=a.out_dir):
        print(p)
    return 0


def cmd_raw(a) -> int:
    from labkit.rawdata import freeze, verify

    if a.action == "freeze":
        freeze(chmod=not a.no_chmod)
        return 0
    issues = verify(full=a.full)
    for code, where, msg in issues:
        print(f"{code}  {where}  {msg}")
    print("data/raw: OK ✓" if not issues else f"{len(issues)} 件の問題")
    return 1 if issues else 0


def cmd_devlog(a) -> int:
    from labkit.config import find_root
    from labkit.devlog import update

    print(update(find_root(), a.date))
    return 0


def cmd_adr(a) -> int:
    from labkit._util import slugify
    from labkit.config import find_root, load_lab

    root = find_root()
    d = root / load_lab(root)["adr"]["dir"]
    d.mkdir(parents=True, exist_ok=True)
    nums = [int(m.group(1)) for p in d.glob("*.md") if (m := re.match(r"^(\d{4})-", p.name))]
    num = f"{(max(nums) + 1) if nums else 1:04d}"
    p = d / f"{num}-{a.slug or slugify(a.title)}.md"
    text = (
        _tpl("adr.md")
        .replace("{{number}}", num)
        .replace("{{title}}", a.title)
        .replace("{{date}}", _dt.date.today().isoformat())
    )
    p.write_text(text, encoding="utf-8", newline="\n")
    print(p)
    return 0


def cmd_lit(a) -> int:
    from labkit import literature as lit
    from labkit._util import slugify
    from labkit.config import find_root, load_lab

    root = find_root()
    lab = load_lab(root)
    if a.action == "add":
        if a.doi or a.arxiv:
            bib = lit.fetch_bibtex(doi=a.doi, arxiv=a.arxiv)  # 一次情報から取る（記憶から書誌を作らない）
        else:
            bib = Path(a.file).read_text(encoding="utf-8") if a.file else sys.stdin.read()
        key, note = lit.add_entry(root, lab, bib, tags=a.tags, pdf=Path(a.pdf) if a.pdf else None, key=a.key)
        lit.build_index(root, lab)
        print(f"{key}\n{note}")
    elif a.action == "read":
        if not a.key_or_citekey or not a.by:
            raise SystemExit("lit read <citekey> --by agent|human [--scope none|abstract|sections|full] [--status ...]")
        print(lit.mark_read(root, lab, a.key_or_citekey, by=a.by, scope=a.scope, status=a.status))
        lit.build_index(root, lab)
    elif a.action == "queue":
        print(lit.format_queue(lit.reading_queue(root, lab, min_relevance=a.min_relevance or 1)))
    elif a.action == "surveys":
        print(lit.format_surveys(lit.list_surveys(root, lab)))
    elif a.action == "survey":
        if not a.question:
            raise SystemExit("--question が必要です")
        date = _dt.date.today().isoformat()
        p = lit.lit_dir(root, lab) / "surveys" / f"{date}_{a.slug or slugify(a.question)[:40]}.md"
        if p.exists():
            raise SystemExit(f"既に存在します: {p}")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            _tpl("survey.md").replace("{{date}}", date).replace("{{question}}", a.question),
            encoding="utf-8",
            newline="\n",
        )
        print(p)
    else:
        print(lit.build_index(root, lab))
    return 0


def cmd_runs(a) -> int:
    from labkit.runs import archive_candidates, archive_runs, find_run, list_runs, mark_run, runs_table, verdict_run

    if a.action == "list":
        for m in list_runs(include_archived=a.all):
            if a.status and m.get("status") != a.status:
                continue
            flags = " ".join(
                f
                for f, on in (
                    ("dirty", (m.get("git") or {}).get("dirty")),
                    ("archived", m.get("archived")),
                    (f"予想:{(m.get('prediction_result') or {}).get('verdict', '')}", m.get("prediction_result")),
                )
                if on
            )
            print(f"{m.get('run_id')}  {m.get('status', '?'):11s} {m.get('duration_s') or '-':>8}s  {flags}")
    elif a.action == "show":
        d = find_run(a.run_id)
        print((d / "meta.json").read_text(encoding="utf-8"))
        if (d / "metrics.json").exists():
            print("metrics:", (d / "metrics.json").read_text(encoding="utf-8"))
    elif a.action == "mark":
        if not a.to:
            raise SystemExit("runs mark <run_id> --to failed|interrupted|finished [--reason ...]")
        m = mark_run(a.run_id, a.to, a.reason or "")
        print(f"{m['run_id']}: status={m['status']}")
    elif a.action == "archive":
        ids = [a.run_id] if a.run_id else []
        if a.status or a.uncited:
            statuses = tuple(a.status.split(",")) if a.status else ()
            ids += [
                m["run_id"]
                for m in archive_candidates(statuses=statuses, uncited=a.uncited, older_than_days=a.older_than or 0)
            ]
        if not ids:
            raise SystemExit(
                "runs archive <run_id> | --status failed,interrupted | --uncited [--older-than N] [--dry-run] [--undo]"
            )
        if a.dry_run:
            print("\n".join(ids) or "候補はありません")
            return 0
        done = archive_runs(ids, a.reason or "", undo=a.undo)
        print(
            f"{'退避を取り消し' if a.undo else '退避'}: {len(done)} 件（削除はしていない。一覧は `labkit runs list --all`）"
        )
    elif a.action == "verdict":
        r = verdict_run(a.run_id, say=a.say, note=a.note or "")
        print(
            f"{a.run_id}: 予想の判定 {r['verdict']}"
            + ("（自己申告）" if r.get("self_reported") else f" {r.get('hit')}/{r.get('total')}")
        )
    else:
        df = runs_table(a.run_id or "", file=a.file or "results.parquet", include_all=a.all)
        print(df.to_markdown(index=False) if a.md and hasattr(df, "to_markdown") else df.to_string(index=False))
        for rid, why in df.attrs.get("excluded", []):
            print(f"# 除外: {rid} ({why})", file=sys.stderr)
    return 0


def cmd_run(a) -> int:
    from labkit.runner import run_config

    run_config(a.config, a.overrides)
    return 0


def cmd_claim(a) -> int:
    from labkit import claims
    from labkit.config import find_root

    root = find_root()
    if a.action == "add":
        if not a.text:
            raise SystemExit('claim add "<主張 1 文>" --evidence <run_id>:<key>[:<unit>][:<digits>] ... [--note ...]')
        c = claims.add_claim(root, a.text, a.evidence or [], note=a.note or "")
        print(f"{c['id']}  {c['text']}  ← {c['evidence']}")
    elif a.action == "retract":
        c = claims.retract_claim(root, a.text or "", a.reason or "")
        print(f"{c['id']} を撤回しました: {c['note']}")
    else:
        print(claims.format_claims(claims.list_claims(root, a.status)))
    return 0


def cmd_digest(a) -> int:
    from labkit.config import find_root
    from labkit.digest import build

    print(build(find_root(), a.since))
    return 0


def cmd_beat(a) -> int:
    from labkit import beat
    from labkit.config import find_root

    root = find_root()
    if a.action == "start":
        print(beat.start(root))
    elif a.action == "end":
        r = beat.end(root, predicted=a.predicted or "", observed=a.observed or "", decided=a.decided or "", runs=a.runs)
        print(f"拍 {r['beat']} を記録しました（{r['time'][11:16]}）。開発ログの自動ブロックに写した")
    else:
        print(beat.log(root, a.date))
    return 0


def cmd_mirror(a) -> int:
    from labkit import mirror

    (mirror.push if a.action == "push" else mirror.pull)(to=a.to, paths=a.paths, verify=a.verify)
    return 0


def cmd_standards(a) -> int:
    from labkit import standards as std

    if a.action == "status":
        print(std.describe(std.status()))
    elif a.action == "link":
        std.link(a.path, do_sync=not a.no_sync)
    elif a.action == "unlink":
        if not a.to:
            raise SystemExit("--to vX.Y.Z（戻す先のリリースタグ）が必要です")
        std.unlink(a.to, do_sync=not a.no_sync)
    else:
        if not a.ref:
            raise SystemExit("--ref（タグ、または push 済みのブランチ名）が必要です")
        return std.template(a.ref)
    return 0


def cmd_paths(a) -> int:
    from labkit.paths import env_name, load_paths

    print(f"LAB_ENV={env_name()}")
    for k, v in load_paths().items():
        print(f"{k} = {v if v is not None else '(未設定)'}")
    return 0


# ---- ハーネス: キュー・承認・委任・手順・引用・レビュー・hook ----
def _print_item(it: dict) -> None:
    if it.get("kind") == "approval":
        print(f"{it['id']}  [{it.get('status')}]  {it.get('category')}  {it.get('command')}")
        print(
            f"      branch={it.get('branch')} head={(it.get('head') or '')[:7]} created={it.get('created')}  直近: {it.get('log')}"
        )
    else:
        print(f"{it['id']}  [{it.get('status')}]  質問: {it.get('question')}")
        if it.get("options"):
            print(f"      選択肢: {' / '.join(it['options'])}")
        print(
            f"      仮の判断: {it.get('assumed')}" + (f"（変更時の影響: {it['impact']}）" if it.get("impact") else "")
        )
        if it.get("answer"):
            print(f"      回答: {it['answer']}")


def cmd_queue(a) -> int:
    from labkit import state

    root = _scope_root()
    if a.action == "list":
        items = state.list_queue(root)
        if not a.all:
            items = [i for i in items if i.get("status") in ("pending", "approved", "open", "answered", "rejected")]
        for it in items:
            _print_item(it)
        if not items:
            print("キューは空です")
    elif a.action == "ask":
        if not a.text or not a.assumed:
            raise SystemExit("queue ask <質問> --assumed <仮の判断> [--options A B ...] [--impact ...]")
        it = state.ask_question(root, a.text, options=a.options or [], assumed=a.assumed, impact=a.impact or "")
        print(
            f'質問 #{it["id"]} を積みました。仮の判断（{a.assumed}）で先に進んでください。人間: `labkit answer {it["id"]} "..."`'
        )
    else:
        if not a.text:
            raise SystemExit("queue done <ID>")
        print(f"{state.mark_done(root, a.text)['id']} を done にしました")
    return 0


def cmd_approve(a) -> int:
    from labkit import state
    from labkit.config import load_lab

    root = _scope_root()
    d = state.approve(root, a.id, ttl_hours=float(a.hours or load_lab(root)["gate"]["approval_ttl_hours"]))
    print(f"承認しました: {a.id} → 委任 {state.describe_delegation(d)}")
    return 0


def cmd_reject(a) -> int:
    from labkit import state

    print(f"却下しました: {state.reject(_scope_root(), a.id, note=a.note or '')['id']}")
    return 0


def cmd_answer(a) -> int:
    from labkit import state

    it = state.answer_question(_scope_root(), a.id, a.text)
    print(
        f"回答を記録しました: {it['id']}（Claude は次のプロンプトで受け取り、取り込んだら `labkit queue done {it['id']}`）"
    )
    return 0


def cmd_delegate(a) -> int:
    from labkit import state

    root = _scope_root()
    if a.categories[:1] == ["list"]:
        lines = [state.describe_delegation(d) for d in state.active_delegations(root)]
        print("\n".join(lines) if lines else "有効な委任はありません")
        return 0
    if a.categories[:1] == ["revoke"]:
        if len(a.categories) < 2:
            raise SystemExit("delegate revoke <ID|all>")
        for d in state.revoke_delegation(root, a.categories[1]):
            print(f"取り消しました: {d['id']}  {', '.join(d['categories'])}")
        return 0
    if not a.categories:
        raise SystemExit(
            "delegate <カテゴリ...> [--hours N] [--branch B] [--note ...]  カテゴリ: "
            + ", ".join(state.DELEGATABLE)
            + "  グループ: "
            + ", ".join(state.GROUPS)
        )
    d = state.add_delegation(root, a.categories, hours=a.hours, branch=a.branch, note=a.note or "")
    print(f"委任しました: {state.describe_delegation(d)}\n  取り消し: labkit delegate revoke {d['id']}")
    return 0


def cmd_flow(a) -> int:
    from labkit import flow
    from labkit._util import git

    try:
        from labkit.config import find_root

        root = find_root()
    except FileNotFoundError:  # migrate は雛形適用前から始まる: git の最上位、なければ cwd
        root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel") or Path.cwd())
    if a.action == "start":
        print(flow.describe(root, flow.start(root, a.name or "migrate")))
    elif a.action == "status":
        flows = flow.active_flows(root)
        if not flows:
            print("進行中の flow はありません（`labkit flow start migrate`）")
        for st in flows:
            print(flow.describe(root, st))
    else:
        names = [a.name] if a.name else [f["flow"] for f in flow.active_flows(root)]
        if len(names) != 1:
            raise SystemExit(f"flow {a.action} <name>")
        if a.action == "advance":
            st, msg = flow.advance(root, names[0])
            print(msg)
            print(flow.describe(root, st))
        else:
            flow.abort(root, names[0])
            print(f"flow {names[0]} を中止しました")
    return 0


def cmd_cite(a) -> int:
    from labkit.check import cite

    print(cite(a.run_id, a.key, digits=a.digits, unit=a.unit or ""))
    return 0


def cmd_review(a) -> int:
    from labkit import flow, reviews
    from labkit._util import git

    root = _scope_root()
    if a.action == "list":
        rs = reviews.open_reviews(root) if a.open else reviews.list_reviews(root)
        print(reviews.format_reviews(root, rs))
        return 0
    if not a.flow or not a.stage:
        raise SystemExit("review template <flow|adhoc> <stage> [--resolves docs/reviews/<前回>.md]")
    stages = (
        {s["name"] for s in flow.definitions().get(a.flow, {"stage": []})["stage"]} if a.flow != "adhoc" else {a.stage}
    )
    if a.stage not in stages:
        raise SystemExit(f"flow '{a.flow}' に段階 '{a.stage}' はありません（flow が無いレビューは `adhoc <stage>`）")
    prev = reviews.load_review(root / a.resolves) if a.resolves else None
    if prev is not None:
        prev.path = Path(a.resolves)
    print(reviews.template(a.flow, a.stage, git(root, "rev-parse", "HEAD") or "", resolves=prev), end="")
    return 0


def cmd_hook(a) -> int:
    from labkit.hook import handle

    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        data = {}
    if a.plugin_version:
        data["plugin_version"] = a.plugin_version
    code, out, err = handle(a.event, data)
    if out:
        print(out)
    if err:
        print(err, file=sys.stderr)
    return code


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="labkit", description="研究プロジェクト規約ツール")
    p.add_argument("--version", action="version", version=f"labkit {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("check", help="規約チェック（--claims で成果物の検証だけ）")
    s.add_argument("--full", action="store_true", help="data/raw の sha256 まで照合（遅い）")
    s.add_argument("--claims", action="store_true", help="成果物の検証（raw・run・サイドカー・開発ログ・引用）だけ")
    s.add_argument("--warn", action="store_true", help="違反があっても終了コード 0")
    s.add_argument("--strict", action="store_true", help="lab.toml が warn でも失敗扱い")
    s.add_argument("--json", action="store_true")
    s.add_argument("--ignore", nargs="*", help="今回だけ無視するコード（例: --ignore L050）")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("fig", help="図テンプレートで図を作る（`labkit fig list` で一覧）")
    s.add_argument("spec", help="figspecs/*.toml または list")
    s.add_argument("--run", help="run ID（部分一致可）")
    s.add_argument("--out-dir", help="出力先（既定: runs/<id>/figures、run 無しは scratch/figures）")
    s.set_defaults(func=cmd_fig)

    s = sub.add_parser("raw", help="生データの凍結・検証")
    s.add_argument("action", choices=["freeze", "verify"])
    s.add_argument("--full", action="store_true")
    s.add_argument("--no-chmod", action="store_true")
    s.set_defaults(func=cmd_raw)

    s = sub.add_parser("devlog", help="今日の開発ログを作成し、変更ファイルと run の自動ブロックを更新する")
    s.add_argument("--date")
    s.set_defaults(func=cmd_devlog)

    s = sub.add_parser("adr", help="ADR を新規作成")
    s.add_argument("title")
    s.add_argument("--slug", help="ファイル名用の英語スラッグ")
    s.set_defaults(func=cmd_adr)

    s = sub.add_parser("lit", help="文献管理（add / read / queue / survey / surveys / index）")
    s.add_argument("action", choices=["add", "read", "queue", "survey", "surveys", "index"])
    s.add_argument("key_or_citekey", nargs="?", help="read: citekey")
    s.add_argument("--file", help="add: BibTeX ファイル（省略時は標準入力）")
    s.add_argument("--doi", help="add: DOI から書誌を取得する（doi.org。source が記録される）")
    s.add_argument("--arxiv", help="add: arXiv ID から書誌を取得する")
    s.add_argument("--pdf", help="add: 一緒に登録する PDF（literature/pdfs/<citekey>.pdf へ移動）")
    s.add_argument("--tags", nargs="*", default=[])
    s.add_argument("--key", help="add: citekey を明示")
    s.add_argument("--by", choices=["agent", "human"], help="read: 誰が読んだか")
    s.add_argument("--scope", choices=["none", "abstract", "sections", "full"], help="read: 読んだ範囲")
    s.add_argument("--status", help="read: status を更新（unread/skimmed/read/key）")
    s.add_argument("--min-relevance", type=int, help="queue: この relevance 以上だけ")
    s.add_argument("--question", help="survey: 調査の問い")
    s.add_argument("--slug", help="survey: ファイル名スラッグ")
    s.set_defaults(func=cmd_lit)

    s = sub.add_parser("run", help="設定の entry を実行して run を作る（scripts/run_*.py を書かない共通の入口）")
    s.add_argument("config", help='configs/experiments/<name>.toml（entry = "pkg.module:func" を持つ）')
    s.add_argument("overrides", nargs="*", help="key=value の上書き")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser(
        "runs",
        help="run の一覧・詳細・記録・退避・予想の判定・表の連結（list / show / mark / archive / verdict / table）",
    )
    s.add_argument("action", choices=["list", "show", "mark", "archive", "verdict", "table"])
    s.add_argument("run_id", nargs="?", help="table: run の name か ID の部分文字列")
    s.add_argument("--status", help="list: 絞り込み / archive: 退避する状態（failed,interrupted）")
    s.add_argument("--all", action="store_true", help="list/table: 退避済み（table は dirty・未完了も）を含める")
    s.add_argument("--to", choices=["failed", "interrupted", "finished"], help="mark: 記録する状態")
    s.add_argument("--reason", help="mark/archive: 理由")
    s.add_argument(
        "--uncited", action="store_true", help="archive: 文書に引用されず他の run の入力でもない finished を候補に"
    )
    s.add_argument("--older-than", type=float, help="archive: この日数より古い run だけ")
    s.add_argument("--dry-run", action="store_true", help="archive: 候補を表示するだけ")
    s.add_argument("--undo", action="store_true", help="archive: 退避を取り消す")
    s.add_argument("--say", choices=["hit", "miss", "partial"], help="verdict: 自由記述の予想の自己申告")
    s.add_argument("--note", help="verdict: 判定の理由")
    s.add_argument("--file", help="table: 連結するファイル名（既定 results.parquet）")
    s.add_argument("--md", action="store_true", help="table: Markdown で出す")
    s.set_defaults(func=cmd_runs)

    s = sub.add_parser("claim", help="主張の台帳 docs/claims.md（add / retract / list）")
    s.add_argument("action", choices=["add", "retract", "list"])
    s.add_argument("text", nargs="?", help="add: 主張 1 文 / retract: ID")
    s.add_argument("--evidence", nargs="*", help="add: <run_id>:<key>[:<unit>][:<digits>]")
    s.add_argument("--note", help="add: 備考（prereg:<slug> など）")
    s.add_argument("--reason", help="retract: 撤回の理由")
    s.add_argument("--status", choices=["open", "retracted"], help="list: 絞り込み")
    s.set_defaults(func=cmd_claim)

    s = sub.add_parser("digest", help="人間の入口 docs/DIGEST.md を台帳と run から生成する（1 日 1 回）")
    s.add_argument("--since", help="この日付（YYYY-MM-DD）か commit 以降。既定: DIGEST を最後に commit した時点")
    s.set_defaults(func=cmd_digest)

    s = sub.add_parser("beat", help="長い自律運用の 1 拍（start / end / log）。prompts/current.toml が現行の版を指す")
    s.add_argument("action", choices=["start", "end", "log"])
    s.add_argument("--predicted", help="end: この拍の予想")
    s.add_argument("--observed", help="end: 結果")
    s.add_argument("--decided", help="end: 判断")
    s.add_argument("--runs", nargs="*", help="end: この拍の run ID")
    s.add_argument("--date", help="log: 日付（既定 今日）")
    s.set_defaults(func=cmd_beat)

    s = sub.add_parser("mirror", help="正本（data/ runs/）の写し（push / pull）")
    s.add_argument("action", choices=["push", "pull"])
    s.add_argument("--to", help="写し先（既定: configs/paths/<LAB_ENV>.toml の mirror_root）")
    s.add_argument("--paths", nargs="*", help="対象ディレクトリ（既定: data runs）")
    s.add_argument("--verify", action="store_true", help="sha256 で比較する（遅い）")
    s.set_defaults(func=cmd_mirror)

    s = sub.add_parser("standards", help="lab-standards 本体との接続（status / link / unlink / template）")
    s.add_argument("action", choices=["status", "link", "unlink", "template"])
    s.add_argument("--path", help="link: 本体チェックアウト（既定: $LAB_STANDARDS_DEV か ~/dev/lab-standards）")
    s.add_argument("--to", help="unlink: 戻す先のリリースタグ")
    s.add_argument("--ref", help="template: copier update に使うタグまたは push 済みブランチ")
    s.add_argument("--no-sync", action="store_true", help="uv sync を実行しない")
    s.set_defaults(func=cmd_standards)

    s = sub.add_parser("paths", help="現在の LAB_ENV で解決されるパスを表示")
    s.set_defaults(func=cmd_paths)

    s = sub.add_parser("queue", help="承認待ち・質問のキュー（list / ask / done）")
    s.add_argument("action", choices=["list", "ask", "done"])
    s.add_argument("text", nargs="?", help="ask: 質問文 / done: ID")
    s.add_argument("--options", nargs="*", help="ask: 選択肢")
    s.add_argument("--assumed", help="ask: 仮に採用した判断とその理由")
    s.add_argument("--impact", help="ask: 後で変える場合の影響範囲")
    s.add_argument("--all", action="store_true", help="list: 完了済みも表示")
    s.set_defaults(func=cmd_queue)

    s = sub.add_parser("approve", help="承認（人間のみ）: その種類の操作をそのブランチで期限まで許可する")
    s.add_argument("id")
    s.add_argument("--hours", type=float, help="有効期間（既定: lab.toml の gate.approval_ttl_hours）")
    s.set_defaults(func=cmd_approve)

    s = sub.add_parser("reject", help="却下（人間のみ）")
    s.add_argument("id")
    s.add_argument("--note")
    s.set_defaults(func=cmd_reject)

    s = sub.add_parser("answer", help="質問に回答する（人間のみ）")
    s.add_argument("id")
    s.add_argument("text")
    s.set_defaults(func=cmd_answer)

    s = sub.add_parser(
        "delegate",
        help="委任（人間のみ）: `delegate <カテゴリ...> --hours N` / `delegate list` / `delegate revoke <ID|all>`",
    )
    s.add_argument("categories", nargs="*")
    s.add_argument("--hours", type=float, default=8.0, help="有効期間（既定 8 時間）")
    s.add_argument("--branch", help="このブランチに限る")
    s.add_argument("--note", help="目的（記録に残す）")
    s.set_defaults(func=cmd_delegate)

    s = sub.add_parser("flow", help="手順のチェックリスト（start / status / advance / abort）")
    s.add_argument("action", choices=["start", "status", "advance", "abort"])
    s.add_argument("name", nargs="?", help="migrate")
    s.set_defaults(func=cmd_flow)

    s = sub.add_parser("cite", help="run の指標を検証可能な書式で出す: 12.3 dB [run:<id>:<key>]")
    s.add_argument("run_id")
    s.add_argument("key")
    s.add_argument("--digits", type=int, help="小数点以下の桁数")
    s.add_argument("--unit", help="単位（例: dB）")
    s.set_defaults(func=cmd_cite)

    s = sub.add_parser("review", help="レビュー記録: template <flow|adhoc> <stage> [--resolves 前回] / list [--open]")
    s.add_argument("action", choices=["template", "list"])
    s.add_argument("flow", nargs="?")
    s.add_argument("stage", nargs="?")
    s.add_argument("--resolves", help="template: 再レビューする前回の記録（前回の指摘の対応表を差し込む）")
    s.add_argument("--open", action="store_true", help="list: 未解消の changes-requested だけ")
    s.set_defaults(func=cmd_review)

    s = sub.add_parser("hook", help="Claude Code hooks の判定（plugin が呼ぶ。stdin に hook 入力 JSON）")
    s.add_argument("event", choices=["pretool", "session", "prompt", "stop"])
    s.add_argument("--plugin-version")
    s.set_defaults(func=cmd_hook)
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):  # Windows（cp932）でもパイプ越しの日本語を壊さない
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    args = build_parser().parse_args(argv)
    if args.cmd == "runs" and args.action in ("show", "mark", "verdict") and not args.run_id:
        raise SystemExit("run_id が必要です")
    try:
        return int(args.func(args) or 0)
    except (OSError, ValueError) as e:  # 利用者の誤りは 1 行で伝える。traceback は内部エラーにだけ残す
        print(f"labkit: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
