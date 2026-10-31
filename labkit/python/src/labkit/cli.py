"""labkit コマンド。Python でも Julia でも、操作はすべてこの CLI に揃える."""

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


def cmd_check(a) -> int:
    from labkit.check import run_check

    issues, mode = run_check(full=a.full, ignore=set(a.ignore or []))
    if a.warn:
        mode = "warn"
    if a.strict:
        mode = "strict"
    errors = [i for i in issues if i.severity == "error"]
    warns = [i for i in issues if i.severity != "error"]
    if a.json:
        print(json.dumps([vars(i) for i in issues], ensure_ascii=False, indent=2))
    else:
        for i in issues:
            print(i)
        if issues:
            print(
                f"\nlabkit check: {len(errors)} 件の違反、{len(warns)} 件の警告（mode={mode}{', full' if a.full else ''}）"
            )
        else:
            print("labkit check: 違反なし ✓")
    return 1 if errors and mode == "strict" else 0


# ---- v0.3.0 ハーネス: 在席状態・承認キュー・手順・引用・レビュー ----
def _scope_root():
    from labkit.state import find_scope

    sc = find_scope()
    if sc is None:
        raise SystemExit("lab.toml のあるプロジェクトか lab-standards 本体の中で実行してください")
    return sc[0]


def _gate_conf(root) -> dict:
    from labkit.config import DEFAULTS, load_lab

    if (root / "lab.toml").is_file():
        return load_lab(root)["gate"]
    return dict(DEFAULTS["gate"])


def cmd_presence(a) -> int:
    from labkit import state

    root = _scope_root()
    if a.value == "status":
        print(f"presence = {state.get_presence(root)}（既定 away。here: 確認画面を出す / away: 拒否してキューに積む）")
    else:
        print(f"presence = {state.set_presence(root, a.value)}")
    return 0


def _print_item(it: dict) -> None:
    if it.get("kind") == "approval":
        print(f"{it['id']}  [{it.get('status')}]  {it.get('command')}")
        print(
            f"      cwd={it.get('cwd')} branch={it.get('branch')} head={(it.get('head') or '')[:7]} "
            f"created={it.get('created')}"
        )
        if it.get("reason"):
            print(f"      理由: {it['reason']}")
    elif it.get("kind") == "question":
        print(f"{it['id']}  [{it.get('status')}]  質問: {it.get('question')}")
        if it.get("options"):
            print(f"      選択肢: {' / '.join(it['options'])}")
        print(
            f"      仮の判断: {it.get('assumed')}" + (f"（変更時の影響: {it['impact']}）" if it.get("impact") else "")
        )
        if it.get("answer"):
            print(f"      回答: {it['answer']}")
    else:
        print(f"{it.get('id')}  [{it.get('status')}]")


def cmd_queue(a) -> int:
    from labkit import state

    root = _scope_root()
    if a.action == "list":
        items = state.list_queue(root)
        if a.all is False:
            items = [i for i in items if i.get("status") in ("pending", "approved", "open", "answered")]
        if not items:
            print("キューは空です")
        for it in items:
            _print_item(it)
    elif a.action == "ask":
        if not a.text or not a.assumed:
            raise SystemExit("queue ask <質問> --assumed <仮の判断> [--options A B ...] [--impact ...]")
        it = state.ask_question(root, a.text, options=a.options or [], assumed=a.assumed, impact=a.impact or "")
        print(
            f'質問 #{it["id"]} を積みました。仮の判断（{a.assumed}）で先に進んでください。人間: `labkit answer {it["id"]} "..."`'
        )
    elif a.action == "done":
        if not a.text:
            raise SystemExit("queue done <ID>")
        it = state.mark_done(root, a.text)
        print(f"{it['id']} を done にしました")
    elif a.action == "show":
        if not a.text:
            raise SystemExit("queue show <ID>")
        print(json.dumps(state.get_item(root, a.text), ensure_ascii=False, indent=2))
    return 0


def _confirm_human(qid: str, yes: bool) -> dict:
    from labkit import state

    who = state.human_check(yes)
    if who["tty"] and not yes:
        try:
            typed = input(f"承認する ID を再入力してください [{qid}]: ").strip()
        except EOFError:  # isatty が真でも入力が無い環境（一部の Windows シェル）
            typed = None
        if typed is None:
            raise SystemExit("入力を受け取れません。人間が実行していることを示すため --yes を付けてください")
        if typed != qid:
            raise SystemExit("ID が一致しません。中止")
    elif not yes:
        raise SystemExit(
            "対話端末ではありません。人間が実行していることを示すため --yes を付けてください"
            "（Claude Code の `!` 実行からも可）"
        )
    return who


def cmd_approve(a) -> int:
    from labkit import state

    root = _scope_root()
    who = _confirm_human(a.id, a.yes)
    rec = state.approve(root, a.id, ttl_hours=float(_gate_conf(root)["approval_ttl_hours"]), who=who)
    print(
        f"承認しました: {rec['id']}  {rec['command']}\n  HEAD={(rec['head'] or '')[:7]}  期限={rec['expires_at']}  1 回限り"
    )
    if who["claude_shell"] and not who["tty"]:
        print("  注意: Claude Code のシェル環境から承認しました（記録に claude_shell=true）")
    return 0


def cmd_reject(a) -> int:
    from labkit import state

    root = _scope_root()
    _confirm_human(a.id, a.yes)
    it = state.reject(root, a.id, note=a.note or "")
    print(f"却下しました: {it['id']}")
    return 0


def cmd_answer(a) -> int:
    from labkit import state

    root = _scope_root()
    it = state.answer_question(root, a.id, a.text)
    print(
        f"回答を記録しました: {it['id']}（Claude は次のプロンプトで文脈に受け取り、取り込んだら `labkit queue done {it['id']}`）"
    )
    return 0


def cmd_flow(a) -> int:
    from labkit import flow
    from labkit.config import find_root

    try:
        root = find_root()
    except FileNotFoundError:
        # migrate は lab.toml が無い段階（freeze / inventory）から始まる: git の最上位、なければ cwd を使う
        import subprocess

        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        root = Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else Path.cwd()
    if a.action == "start":
        if not a.name:
            raise SystemExit(f"flow start <name>  （{', '.join(sorted(flow.definitions()))}）")
        st = flow.start(root, a.name)
        print(flow.describe(root, st))
    elif a.action == "status":
        flows = flow.active_flows(root)
        if a.name:
            st = flow.load_state(root, a.name)
            flows = [st] if st else []
        if not flows:
            print("進行中の flow はありません（`labkit flow start migrate|improve-standards`）")
        for st in flows:
            print(flow.describe(root, st))
    elif a.action == "advance":
        names = [a.name] if a.name else [f["flow"] for f in flow.active_flows(root)]
        if len(names) != 1:
            raise SystemExit("flow advance <name>（進行中の flow が 1 つなら省略可）")
        st, msg = flow.advance(root, names[0])
        print(msg)
        print(flow.describe(root, st))
    elif a.action == "abort":
        names = [a.name] if a.name else [f["flow"] for f in flow.active_flows(root)]
        if len(names) != 1:
            raise SystemExit("flow abort <name>")
        flow.abort(root, names[0])
        print(f"flow {names[0]} を中止しました")
    elif a.action == "list":
        for name, d in sorted(flow.definitions().items()):
            print(f"{name}: {d.get('description', '')}")
            print("  " + " → ".join(s["name"] + ("【承認】" if s.get("approval") else "") for s in d["stage"]))
    return 0


def cmd_cite(a) -> int:
    from labkit.check import cite

    print(cite(a.run_id, a.key, digits=a.digits, unit=a.unit or ""))
    return 0


def cmd_review(a) -> int:
    """レビュー記録の frontmatter 雛形（現在の HEAD 入り）。lab-reviewer が docs/reviews/<date>_<flow>_<stage>.md に書く."""
    from labkit import reviews, state
    from labkit.config import find_root

    print(reviews.template(a.flow, a.stage, state.git_head(find_root()) or ""), end="")
    return 0


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
    from labkit.config import find_root, load_lab

    root = find_root()
    lab = load_lab(root)
    date = a.date or _dt.date.today().isoformat()
    p = root / lab["devlog"]["dir"] / f"{date}.md"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_tpl("devlog.md").replace("{{date}}", date), encoding="utf-8")
    print(p)
    return 0


def cmd_adr(a) -> int:
    from labkit._util import slugify
    from labkit.config import find_root, load_lab

    root = find_root()
    d = root / load_lab(root)["adr"]["dir"]
    d.mkdir(parents=True, exist_ok=True)
    nums = [int(m.group(1)) for p in d.glob("*.md") if (m := re.match(r"^(\d{4})-", p.name))]
    num = f"{(max(nums) + 1) if nums else 1:04d}"
    slug = a.slug or slugify(a.title)
    p = d / f"{num}-{slug}.md"
    p.write_text(
        _tpl("adr.md")
        .replace("{{number}}", num)
        .replace("{{title}}", a.title)
        .replace("{{date}}", _dt.date.today().isoformat()),
        encoding="utf-8",
    )
    print(p)
    return 0


def cmd_lit(a) -> int:
    from labkit import literature as lit
    from labkit.config import find_root, load_lab

    root = find_root()
    lab = load_lab(root)
    if a.action == "add":
        bib = Path(a.file).read_text(encoding="utf-8") if a.file else sys.stdin.read()
        key, note = lit.add_entry(root, lab, bib, tags=a.tags, pdf=Path(a.pdf) if a.pdf else None, key=a.key)
        lit.build_index(root, lab)
        print(f"{key}\n{note}")
    elif a.action == "survey":
        date = _dt.date.today().isoformat()
        from labkit._util import slugify

        p = lit.lit_dir(root, lab) / "surveys" / f"{date}_{a.slug or slugify(a.question)[:40]}.md"
        if p.exists():
            raise SystemExit(f"既に存在します: {p}")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_tpl("survey.md").replace("{{date}}", date).replace("{{question}}", a.question), encoding="utf-8")
        print(p)
    elif a.action == "index":
        print(lit.build_index(root, lab))
    elif a.action == "key":
        bib = Path(a.file).read_text(encoding="utf-8") if a.file else sys.stdin.read()
        for _, f in lit.parse_bib(bib).items():
            print(lit.make_citekey(f))
    elif a.action == "check":
        issues = lit.check_literature(root, lab)
        for i in issues:
            print("  ".join(i))
        return 1 if issues else 0
    return 0


def cmd_runs(a) -> int:
    from labkit.runs import find_run, list_runs

    if a.action == "list":
        for m in list_runs():
            if a.status and m.get("status") != a.status:
                continue
            dirty = "*" if (m.get("git") or {}).get("dirty") else ""
            print(
                f"{m.get('run_id')}  {m.get('status', '?'):11s} {m.get('language', '?'):6s} "
                f"{m.get('duration_s') or '-':>8}s {dirty}"
            )
    else:
        d = find_run(a.run_id)
        print((d / "meta.json").read_text(encoding="utf-8"))
        if (d / "metrics.json").exists():
            print("metrics:", (d / "metrics.json").read_text(encoding="utf-8"))
    return 0


def cmd_mlflow(a) -> int:
    from labkit import mlflow_sync

    if a.action == "sync":
        mlflow_sync.sync(force=a.force)
    else:
        mlflow_sync.ui(port=a.port)
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
    elif a.action == "template":
        if not a.ref:
            raise SystemExit("--ref（タグ、または push 済みのブランチ名）が必要です")
        return std.template(a.ref)
    return 0


def cmd_paths(a) -> int:
    from labkit.paths import env_name, load_paths

    print(f"LAB_ENV={env_name()}")
    for k, v in load_paths().items():
        print(f"{k} = {v}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="labkit", description="研究プロジェクト規約ツール")
    p.add_argument("--version", action="version", version=f"labkit {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("check", help="規約チェック")
    s.add_argument("--full", action="store_true", help="data/raw の sha256 まで照合（遅い）")
    s.add_argument("--warn", action="store_true", help="違反があっても終了コード 0")
    s.add_argument("--strict", action="store_true", help="lab.toml が warn でも失敗扱い")
    s.add_argument("--json", action="store_true")
    s.add_argument("--ignore", nargs="*", help="今回だけ無視するコード（例: --ignore L050）")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("fig", help="図テンプレートで図を作る（`labkit fig list` で一覧）")
    s.add_argument("spec", help="figspecs/*.toml または list")
    s.add_argument("--run", help="run ID（前方一致・部分一致可）")
    s.add_argument("--out-dir", help="出力先（既定: runs/<id>/figures、run 無しは scratch/figures）")
    s.set_defaults(func=cmd_fig)

    s = sub.add_parser("raw", help="生データの凍結・検証")
    s.add_argument("action", choices=["freeze", "verify"])
    s.add_argument("--full", action="store_true")
    s.add_argument("--no-chmod", action="store_true")
    s.set_defaults(func=cmd_raw)

    s = sub.add_parser("devlog", help="今日の開発ログを作成（既存ならパスを表示）")
    s.add_argument("--date")
    s.set_defaults(func=cmd_devlog)

    s = sub.add_parser("adr", help="ADR を新規作成")
    s.add_argument("title")
    s.add_argument("--slug", help="ファイル名用の英語スラッグ（日本語タイトル時に推奨）")
    s.set_defaults(func=cmd_adr)

    s = sub.add_parser("lit", help="文献管理")
    s.add_argument("action", choices=["add", "survey", "index", "key", "check"])
    s.add_argument("--file", help="BibTeX ファイル（省略時は標準入力）")
    s.add_argument("--pdf", help="add: 一緒に登録する PDF（literature/pdfs/<citekey>.pdf へ移動）")
    s.add_argument("--tags", nargs="*", default=[])
    s.add_argument("--key", help="add: citekey を明示（重複回避など）")
    s.add_argument("--question", help="survey: 調査の問い")
    s.add_argument("--slug", help="survey: ファイル名スラッグ")
    s.set_defaults(func=cmd_lit)

    s = sub.add_parser("runs", help="run の一覧・詳細")
    s.add_argument("action", choices=["list", "show"])
    s.add_argument("run_id", nargs="?")
    s.add_argument("--status")
    s.set_defaults(func=cmd_runs)

    s = sub.add_parser("mlflow", help="runs/ をローカル MLflow に同期・閲覧")
    s.add_argument("action", choices=["sync", "ui"])
    s.add_argument("--force", action="store_true")
    s.add_argument("--port", type=int, default=5000)
    s.set_defaults(func=cmd_mlflow)

    s = sub.add_parser("standards", help="lab-standards 本体との接続（status / link / unlink / template）")
    s.add_argument("action", choices=["status", "link", "unlink", "template"])
    s.add_argument("--path", help="link: 本体チェックアウト（既定: $LAB_STANDARDS_DEV か ~/dev/lab-standards）")
    s.add_argument("--to", help="unlink: 戻す先のリリースタグ（例: v0.2.0）")
    s.add_argument("--ref", help="template: copier update に使うタグまたは push 済みブランチ")
    s.add_argument("--no-sync", action="store_true", help="uv sync / Pkg.instantiate を実行しない")
    s.set_defaults(func=cmd_standards)

    s = sub.add_parser("paths", help="現在の LAB_ENV で解決されるパスを表示")
    s.set_defaults(func=cmd_paths)

    # --- v0.3.0 ハーネス ---
    s = sub.add_parser("presence", help="在席状態（here: 確認画面 / away: 拒否してキューへ。既定 away）")
    s.add_argument("value", choices=["here", "away", "status"])
    s.set_defaults(func=cmd_presence)

    s = sub.add_parser("queue", help="承認待ち・質問のキュー（list / ask / done / show）")
    s.add_argument("action", choices=["list", "ask", "done", "show"])
    s.add_argument("text", nargs="?", help="ask: 質問文 / done, show: ID")
    s.add_argument("--options", nargs="*", help="ask: 選択肢")
    s.add_argument("--assumed", help="ask: 仮に採用した判断とその理由")
    s.add_argument("--impact", help="ask: 後で変える場合の影響範囲")
    s.add_argument("--all", action="store_true", help="list: 完了・却下済みも表示")
    s.set_defaults(func=cmd_queue)

    s = sub.add_parser("approve", help="承認（人間のみ。Claude の Bash からは hooks が拒否する）")
    s.add_argument("id")
    s.add_argument("--yes", action="store_true", help="対話端末でないときに人間の実行であることを明示")
    s.set_defaults(func=cmd_approve)

    s = sub.add_parser("reject", help="却下（人間のみ）")
    s.add_argument("id")
    s.add_argument("--note")
    s.add_argument("--yes", action="store_true")
    s.set_defaults(func=cmd_reject)

    s = sub.add_parser("answer", help="質問に回答する（人間のみ）")
    s.add_argument("id")
    s.add_argument("text")
    s.set_defaults(func=cmd_answer)

    s = sub.add_parser("flow", help="手順の状態機械（start / status / advance / abort / list）")
    s.add_argument("action", choices=["start", "status", "advance", "abort", "list"])
    s.add_argument("name", nargs="?", help="migrate | improve-standards")
    s.set_defaults(func=cmd_flow)

    s = sub.add_parser("cite", help="run の指標を検証可能な書式で出す: 12.3 dB [run:<id>:<key>]")
    s.add_argument("run_id")
    s.add_argument("key")
    s.add_argument("--digits", type=int, help="小数点以下の桁数")
    s.add_argument("--unit", help="単位（例: dB）")
    s.set_defaults(func=cmd_cite)

    s = sub.add_parser("review", help="レビュー記録の frontmatter 雛形を出す: labkit review template <flow> <stage>")
    s.add_argument("action", choices=["template"])
    s.add_argument("flow")
    s.add_argument("stage")
    s.set_defaults(func=cmd_review)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "lit" and args.action == "survey" and not args.question:
        raise SystemExit("--question が必要です")
    if args.cmd == "runs" and args.action == "show" and not args.run_id:
        raise SystemExit("run_id が必要です")
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
