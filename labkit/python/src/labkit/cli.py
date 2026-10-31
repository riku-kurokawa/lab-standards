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
    if a.json:
        print(json.dumps([vars(i) for i in issues], ensure_ascii=False, indent=2))
    else:
        for i in issues:
            print(i)
        print(f"\nlabkit check: {len(issues)} 件の違反（mode={mode}{', full' if a.full else ''}）"
              if issues else "labkit check: 違反なし ✓")
    return 1 if issues and mode == "strict" else 0


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
    p.write_text(_tpl("adr.md").replace("{{number}}", num).replace("{{title}}", a.title)
                 .replace("{{date}}", _dt.date.today().isoformat()), encoding="utf-8")
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
        p.write_text(_tpl("survey.md").replace("{{date}}", date).replace("{{question}}", a.question),
                     encoding="utf-8")
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
            print(f"{m.get('run_id')}  {m.get('status', '?'):11s} {m.get('language', '?'):6s} "
                  f"{m.get('duration_s') or '-':>8}s {dirty}")
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
