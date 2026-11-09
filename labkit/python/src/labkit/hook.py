"""Claude Code hooks の判定。plugin の claude-plugin/scripts/hook.py が stdin の JSON をそのまま渡して呼ぶ.

    labkit hook pretool | session | prompt | stop      （stdin: Claude Code の hook 入力 JSON）

PreToolUse(Bash):
  0. 入力の無い `python -`（標準入力待ちで止まる）→ 拒否
  1. lab-reviewer（レビュー agent）は許可リストの読み取りコマンドだけ
  2. 成果物の保護: data/raw・runs/・lab.toml・.lab/ を壊す操作
  （v2.0.0 で承認ゲートと承認・却下・回答・委任を廃止。push・merge・tag・release・raw freeze も止めない。完全自律）
PreToolUse(Write/Edit): .lab/ と規約ファイルの保護、docs/reviews/ は lab-reviewer だけ、docs/claims.md と DIGEST.md は labkit だけ、置き場所、禁止 import
SessionStart: 状態（主線と芽・拍・人間への連絡・flow・今日の開発ログ）を文脈に入れる。UserPromptSubmit は何もしない
Stop: 主張の検証（labkit check --claims）、コードを変えた日の開発ログの判断欄が空でないこと、
      [autonomy] を設定したら backlog の未着手が min_open 件以上あること
lab-standards 本体では 0〜1 と .lab/ の保護だけ。
"""

from __future__ import annotations

import datetime as _dt
import fnmatch
import json
import os
import re
from pathlib import Path

from labkit import gate, state
from labkit._util import read_json, write_json_atomic
from labkit.config import find_scope, load_lab

REVIEWER = "lab-reviewer"
REVIEW_DIR = "docs/reviews"
PROTECTED_FILES = {"lab.toml", ".copier-answers.yml", ".claude/settings.json"}
CODE_PREFIXES = ("src/", "scripts/", "configs/", "figspecs/", "jobs/")
DESTRUCTIVE = r"^\s*(?:sudo\s+)?(?:rm|mv|chmod|chown|chattr|truncate|shred|unlink|ln|dd)\b|\bsed\s+-i|\bfind\b.*-(?:delete|exec\s+rm)"
DELETING = r"^\s*(?:sudo\s+)?(?:rm|shred|unlink|truncate)\b|\bfind\b.*-(?:delete|exec\s+rm)"
# 入力の無い `python -`（行頭か ; && || & の直後。パイプの後ろは入力があるので対象外）
STDIN_PYTHON = r"(?:^|[;&\n]|\|\|)\s*(?:\S*/)?(?:python[0-9.]*|py)(?:\.exe)?\s+-(?=\s|$)"
WRITE_OPS = r">{1,2}|\btee\b|\bsed\s+-i|\b(?:rm|mv|cp|touch|truncate|python[0-9.]*\s+-c|perl|node\s+-e)\b"
GENERATED = {
    "docs/claims.md": "`labkit claim add / retract`",
    "docs/DIGEST.md": "`labkit digest`",
    "docs/mainline.md": "`labkit main set / add / done`",
    "docs/seeds.md": "`labkit seed add / decide`",
}


# 移行の手順（labkit flow）の中で、lab.toml を書くことが段階の仕事であるもの（mode を warn にする / strict に戻す）
LAB_TOML_STAGES = {"apply-template", "strict"}


def _lab_toml_stage(root: Path) -> bool:
    from labkit import flow

    try:
        return any(st.get("stage") in LAB_TOML_STAGES for st in flow.active_flows(root))
    except Exception:  # noqa: BLE001 - 壊れた flow 状態で hooks を落とさない
        return False


class Block(Exception):
    """操作を止め、理由を Claude に返す（exit 2）."""


def _is_reviewer(data: dict) -> bool:
    t = str(data.get("agent_type") or "")
    return t == REVIEWER or t.endswith(":" + REVIEWER)


def _raw_intake(s: str, root: Path) -> bool:
    """data/raw への新しいファイルの搬入（cp / mv / rsync / install で、既存のファイルを上書きせず、data/raw から持ち出さない）."""
    m = re.match(r"^\s*(cp|mv|rsync|install)\b", s)
    if not m:
        return False
    args = [a for a in s.split()[1:] if not a.startswith("-")]
    if len(args) < 2 or "data/raw" not in args[-1] or any("data/raw" in a for a in args[:-1]):
        return False
    dest = root / args[-1]
    if args[-1].endswith("/") or dest.is_dir() or len(args) > 2:
        targets = [dest / Path(a.rstrip("/")).name for a in args[:-1]]
    else:
        targets = [dest]
    return not any(t.exists() for t in targets)


def _raw_write(s: str) -> bool:
    if re.search(DESTRUCTIVE, s) or re.search(r">{1,2}\s*\S*data/raw", s) or re.search(r"\btee\b[^|]*data/raw", s):
        return True
    if re.match(r"^\s*(?:cp|rsync|install)\b", s):
        args = [a for a in s.split()[1:] if not a.startswith("-")]
        return bool(args) and "data/raw" in args[-1]
    return False


# ---- PreToolUse: Bash ----
def pretool_bash(data: dict, root: Path, kind: str) -> dict | None:
    cmd = (data.get("tool_input") or {}).get("command", "")
    if not cmd:
        return None
    segs = gate.segments(cmd)
    if re.search(STDIN_PYTHON, cmd) and "<<" not in cmd:
        raise Block(
            "`python -` は標準入力からスクリプトを読むので、入力が無いとその場で止まります（パイプも heredoc も無い）。"
            "スクリプトはファイルに書いて `python path.py` で実行するか、`python - <<'EOF' ... EOF` で渡してください。"
        )
    if _is_reviewer(data):
        for seg in segs:
            if not gate.reviewer_allowed(seg):
                raise Block(f"許可されていないコマンドです: `{seg[:80]}`。{gate.reviewer_allowed_summary()}")
    for seg in segs:
        if re.search(r"\.lab/(?:queue|flows|delegations|beats)", seg) and re.search(WRITE_OPS, seg):
            raise Block(".lab/ は直接書き換えません（labkit queue / flow / beat を使う）。")
        if (
            kind == "project"
            and re.search(r"docs/(?:claims|DIGEST|mainline|seeds)\.md", seg)
            and re.search(WRITE_OPS, seg)
        ):
            raise Block(
                "docs/claims.md・DIGEST.md・mainline.md・seeds.md は手で書きません（`labkit claim` / `digest` / `main` / `seed`）。"
            )

    lab = load_lab(root)

    if kind == "project":
        readonly = lab["layout"]["readonly"]
        for seg in segs:
            s = seg.strip()
            if re.search(r"\bgit\s+clean\b[^|]*-[a-zA-Z]*x", s):
                raise Block("git clean -x は管理外の data/・runs/・literature/pdfs を消します。実行しないでください。")
            if re.search(r"\bgit\s+(?:checkout|restore)\b.*\bdata/raw\b", s):
                raise Block("data/raw を git で書き換える操作は禁止です。")
            if "data/raw" in s and _raw_write(s) and not _raw_intake(s, root):
                raise Block(
                    "data/raw の既存ファイルを変更・削除・持ち出す操作は禁止です（生データは不変）。新しいファイルの搬入"
                    "（cp / mv で、上書きしない）はできます。搬入したら `labkit raw freeze` で登録します。"
                )
            for ro in readonly:
                if ro != "data/raw" and ro in s and _raw_write(s):
                    raise Block(f"{ro} は読み取り専用領域です。変更・削除はしません。")
            if re.search(r"\b(?:rm|chmod)\b[^|]*\bruns/", s):
                raise Block(
                    "run の削除・権限変更は人間が行います。異常終了した run は `labkit runs mark <id> failed --reason ...`。"
                )
            if re.search(r"(?:>|\btee\b|\bsed\s+-i|\bmv\b|\bcp\b|\brm\b)[^|]*\blab\.toml\b", s) and not _lab_toml_stage(
                root
            ):
                raise Block(
                    "lab.toml は規約ファイルです。エージェントは自分を縛る規約を変えません。変更案は `labkit queue ask` で人間に伝え、今の規約で進めます。"
                )
    return None


# ---- PreToolUse: Write / Edit ----
def pretool_write(data: dict, root: Path, kind: str) -> dict | None:
    ti = data.get("tool_input") or {}
    target = ti.get("file_path") or ti.get("notebook_path")
    if not target:
        return None
    p = Path(target)
    if not p.is_absolute():
        p = Path(data.get("cwd") or ".") / p
    try:
        r = p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None
    if r == ".lab" or r.startswith(".lab/"):
        raise Block(f"{r} はハーネスの状態です。直接書かず labkit のコマンド（queue ask/done, flow）を使います。")
    in_reviews = r == REVIEW_DIR or r.startswith(REVIEW_DIR + "/")
    if _is_reviewer(data):
        if not in_reviews:
            raise Block(f"lab-reviewer が書けるのはレビュー記録（{REVIEW_DIR}/）だけです。{r} には書けません。")
        return None
    if in_reviews:
        raise Block(f"{r} はレビュー記録です。独立した lab-reviewer agent だけが書けます（Agent ツールで起動する）。")
    if kind != "project":
        return None
    if r in GENERATED:
        raise Block(f"{r} は labkit が書く台帳・生成物です（{GENERATED[r]}）。手で編集しません。")
    lab = load_lab(root)
    layout = lab["layout"]
    top = r.split("/", 1)[0]
    if r == "lab.toml" and _lab_toml_stage(root):
        return None  # 移行の段階の仕事（mode の切り替え）
    if r in PROTECTED_FILES:
        raise Block(
            f"{r} は規約ファイルです。エージェントは自分を縛る規約を変えません。変更案は `labkit queue ask` で人間に伝え、今の規約で進めます。"
        )
    for ro in layout["readonly"]:
        if r == ro or r.startswith(ro.rstrip("/") + "/"):
            raise Block(
                f"{r} は読み取り専用領域（{ro}）です。派生データは scripts から labkit.save で data/interim か data/processed に作ります。"
            )
    if top == "runs":
        raise Block(
            "runs/ はスクリプト（labkit の Run）だけが作ります。結果を変えたいならコード/設定を直して新しい run を実行してください。"
        )
    if top == "data":
        raise Block(
            "data/ のファイルは手で書きません。scripts から labkit.save / labkit.writer 経由で生成してください。"
        )
    if not any(r == w or r.startswith(w.rstrip("/") + "/") for w in layout["writable"]):
        raise Block(
            f"{r} は書き込み可能な場所ではありません。可能: {', '.join(layout['writable'])}。一時ファイルは scratch/ へ。"
        )
    if p.suffix not in {".py", ".ipynb"}:
        return None
    tool = data.get("tool_name", "")
    text = {"Write": ti.get("content"), "Edit": ti.get("new_string"), "NotebookEdit": ti.get("new_source")}.get(
        tool
    ) or ""
    if tool == "MultiEdit":
        text = "\n".join(e.get("new_string", "") for e in ti.get("edits", []))
    c = lab["check"]
    for key, allowed_key, what in (
        ("banned_plot_imports", "plot_import_allowed", "plot"),
        ("banned_formats", "format_allowed", "fmt"),
    ):
        if any(fnmatch.fnmatch(r, pat) for pat in c[allowed_key]):
            continue
        m = re.search(rf"^\s*(?:import|from)\s+({'|'.join(map(re.escape, c[key]))})\b", text, re.M)
        if m and what == "plot":
            raise Block(
                f"{m.group(1)} を直接使って図を作ることは禁止です。figspecs/<name>.toml を書いて `labkit fig` を使ってください（`labkit fig list`）。"
            )
        if m:
            raise Block(
                f"{m.group(1)} は禁止された保存形式です。配列は HDF5、表は Parquet で labkit.save を使ってください。"
            )
    return None


# ---- SessionStart / UserPromptSubmit ----
def session(data: dict, root: Path, kind: str) -> str:
    from labkit._version import __version__
    from labkit.flow import active_flows, describe

    lines = []
    if kind == "standards":
        lines.append("ここは lab-standards 本体。CLAUDE.md（メンテナンス規約）に従い、feat/* ブランチで作業する。")
    else:
        from labkit.devlog import devlog_path

        p = devlog_path(root)
        lines.append(
            f"- 今日の開発ログ {p.relative_to(root).as_posix()}: "
            + (
                "あり"
                if p.exists()
                else "まだ無い（コードを変えた日は `labkit devlog` で作り、目的・判断・未解決を書く）"
            )
        )
    lines.append(
        "- 完全自律: 承認を待つ操作は無い（push・merge・tag も自分で行う）。判断の分かれる問いは自分で決めて根拠を残し、"
        "人間に知らせたいことは `labkit queue ask` に積む（返事は待たない）。"
    )
    pv = data.get("plugin_version")
    if pv and pv != __version__:
        lines.append(
            f"- 注意: plugin lab-rules は {pv}、labkit は {__version__}。版を揃える（`/plugin marketplace update lab-standards` / pyproject のタグ）。"
        )
    if kind == "project":
        from labkit.beat import CURRENT, session_lines
        from labkit.digest import staleness

        try:  # current.toml や拍の記録が壊れていても、他の案内は届ける
            autonomous = (root / CURRENT).is_file()
            lab = load_lab(root)
            off = [k for k in ("require_prediction", "require_clean") if not lab["runs"].get(k)]
            if off and autonomous and data.get("source") != "compact":
                lines.append(
                    f"- 無効のままの関門: runs.{' / runs.'.join(off)}（lab.toml で人間が有効にする。既定 false）"
                )
            lines += session_lines(root, compact=data.get("source") == "compact")
            from labkit.focus import status_lines as focus_lines

            lines += focus_lines(root)
            if st := staleness(root, announce_missing=autonomous):
                lines.append(st)
        except Exception as e:
            lines.append(f"- 注意: {CURRENT} か .lab/beats を読めません（`labkit check`）: {type(e).__name__}: {e}")
    s = state.pending_summary(root)
    lines += [
        f"- 人間への連絡 #{it['id']}: 「{it.get('question')}」仮の判断「{it.get('assumed')}」で進行中（返事は待たない）"
        for it in s["open_questions"]
    ]
    for st in active_flows(root):
        lines.append("- " + describe(root, st).replace("\n", "\n  "))
    if data.get("source") == "compact":
        lines.insert(0, "（会話が要約されたため、主線・拍・手順の状態を再掲する）")
    return "\n".join(lines)


def prompt(data: dict, root: Path, kind: str) -> dict | None:
    """v2.0.0 から何もしない（人間の操作による更新＝承認・回答は廃止）。plugin の入口の互換のために残す."""
    return None


# ---- Stop ----
def _counter(session_id: str) -> Path:
    base = Path(os.environ.get("CLAUDE_PLUGIN_DATA") or Path.home() / ".cache" / "lab-rules")
    base.mkdir(parents=True, exist_ok=True)
    return base / f"stop-{session_id or 'unknown'}.json"


def stop(data: dict, root: Path, kind: str) -> dict | None:
    if kind != "project":
        return None
    from labkit._util import git, git_status
    from labkit.check import run_check
    from labkit.devlog import devlog_path, section_bodies, update

    lab = load_lab(root)
    sid = str(data.get("session_id") or "")
    problems: list[str] = []
    keys: list[str] = []  # 違反 1 件ごとの識別（上限で委ねた違反を覚えるため）
    issues, mode = run_check(root=root, claims=True)
    errs = [str(i) for i in issues if i.severity == "error"]
    if errs and mode == "strict":
        problems.append("`labkit check --claims` の違反:\n" + "\n".join(errs)[-3500:])
        keys += errs
    if lab["claude"]["require_devlog"]:
        changed = [p for _, p in git_status(root) if p.startswith(CODE_PREFIXES)]
        today = _dt.date.today().isoformat()
        committed = git(root, "log", "--name-only", "--format=", f"--since={today} 00:00") or ""
        changed += [f for f in committed.splitlines() if f.startswith(CODE_PREFIXES)]
        if changed:
            p = devlog_path(root)
            existed = p.exists()
            update(root)
            empty = [
                h
                for h in lab["devlog"]["must_fill"]
                if not section_bodies(p.read_text(encoding="utf-8")).get(h, "").strip()
            ]
            if empty:
                problems.append(
                    f"コードを変更した日の開発ログ {p.relative_to(root).as_posix()} の {empty} が空です"
                    + ("（今作成した。変更ファイルと run は自動で埋めた）" if not existed else "")
                    + "。目的・判断と理由・未解決を書いてください。数値は `labkit cite` の書式で。"
                )
                keys.append(f"devlog {p.name} {empty}")
    au = lab["autonomy"]
    if au["backlog"] and int(au["min_open"]) > 0:
        bp = root / au["backlog"]
        n = len(re.findall(r"^\s*[-*] \[ \]", bp.read_text(encoding="utf-8"), re.M)) if bp.is_file() else 0
        if n < int(au["min_open"]):
            problems.append(
                f"{au['backlog']} の未着手の項目（`- [ ] ...`）が {n} 件で、{au['min_open']} 件未満です。"
                "目標に最も効く順に項目を補充し、先頭の項目に着手してから終了してください（計算の完了を待つだけの終了はしない）。"
            )
            keys.append(f"backlog {n}")
    cf = _counter(sid)
    st = read_json(cf) if cf.exists() else {"blocks": 0}
    if not problems:
        cf.unlink(missing_ok=True)
        return None
    # 上限で人間に委ねた違反は覚えておき、同じ違反だけなら以後は止めない（新しい違反が出たら止める）。
    # 覚えないと、委ねた直後の終了から数え直して同じ違反で止め続ける
    released = set(st.get("released", []))
    if released and set(keys) <= released:
        return None
    if st["blocks"] >= int(lab["claude"]["max_stop_blocks"]):
        write_json_atomic(cf, {"blocks": 0, "released": sorted(released | set(keys))})
        return {
            "systemMessage": f"[lab-rules] 規約違反が {lab['claude']['max_stop_blocks']} 回の修正で解消しませんでした。人間の確認が必要です（同じ違反では以後このセッションの終了を止めません）。"
        }
    write_json_atomic(cf, {"blocks": st["blocks"] + 1, "released": sorted(released)})
    raise Block("作業完了の条件を満たしていません。以下を解消してから終了してください:\n\n" + "\n\n".join(problems))


# ---- 自分でループを止めない ----
LOOP_STOP_TOOLS = ("CronDelete", "ScheduleWakeup")


def pretool_loop(data: dict, root: Path, kind: str) -> dict | None:
    """/loop の停止（CronDelete、ScheduleWakeup の stop）は人間だけが行う（claude.allow_self_stop=false のとき）."""
    if kind != "project" or load_lab(root)["claude"]["allow_self_stop"]:
        return None
    ti = data.get("tool_input") or {}
    if data.get("tool_name") == "ScheduleWakeup" and not ti.get("stop"):
        return None
    raise Block(
        "ループを自分で止めることはできません（lab.toml の claude.allow_self_stop = false。止めるのは人間だけ）。"
        "人間の答え・承認・実機の作業を待つことは止まる理由になりません: それに依存しない仕事を進めるか、"
        "人間なしで同じ問いに答える方法（計算・公開データ・独立実装による検証）に切り替えてください。"
        "目標を達したなら、より大きい次の問いを立てて続けてください。"
    )


# ---- 入口 ----
def handle(event: str, data: dict) -> tuple[int, str, str]:
    """(exit code, stdout, stderr)。exit 2 + stderr が「止める」."""
    sc = find_scope(data.get("cwd") or ".")
    if sc is None:
        return 0, "", ""
    root, kind = sc
    try:
        if event == "pretool":
            tool = data.get("tool_name", "")
            if tool == "Bash":
                out = pretool_bash(data, root, kind)
            elif tool in LOOP_STOP_TOOLS:
                out = pretool_loop(data, root, kind)
            else:
                out = pretool_write(data, root, kind)
        elif event == "session":
            return 0, session(data, root, kind), ""
        elif event == "prompt":
            out = prompt(data, root, kind)
        elif event == "stop":
            out = stop(data, root, kind)
        else:
            return 1, "", f"labkit hook: 未知のイベント {event}"
    except Block as b:
        return 2, "", f"[lab-rules] {b}"
    return 0, json.dumps(out, ensure_ascii=False) if out else "", ""
