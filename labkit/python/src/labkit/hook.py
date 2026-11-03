"""Claude Code hooks の判定。plugin の claude-plugin/scripts/hook.py が stdin の JSON をそのまま渡して呼ぶ.

    labkit hook pretool | session | prompt | stop      （stdin: Claude Code の hook 入力 JSON）

PreToolUse(Bash):
  1. Claude が実行してはいけない操作（labkit approve/reject/answer/delegate）→ 拒否
  2. lab-reviewer（レビュー agent）は許可リストの読み取りコマンドだけ
  3. 承認ゲートの対象（保護ブランチへの push/merge、tag、gh release/merge、raw freeze）:
       委任あり → 許可 / 確認画面が出る permission mode → ask / それ以外 → 拒否して .lab/queue に積む
  4. 成果物の保護: data/raw・runs/・lab.toml・.lab/ を壊す操作
PreToolUse(Write/Edit): .lab/ と規約ファイルの保護、docs/reviews/ は lab-reviewer だけ、置き場所、禁止 import
SessionStart / UserPromptSubmit: 状態（承認待ち・回答・委任・flow・今日の開発ログ）を文脈に入れる
Stop: 主張の検証（labkit check --claims）と、コードを変えた日の開発ログの判断欄が空でないこと
lab-standards 本体では 1〜3 と .lab/ の保護だけ。
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

INTERACTIVE_MODES = {"default", "acceptEdits", "plan"}  # hook の ask が確認画面として人間に届くモード
REVIEWER = "lab-reviewer"
REVIEW_DIR = "docs/reviews"
PROTECTED_FILES = {"lab.toml", ".copier-answers.yml", ".claude/settings.json"}
CODE_PREFIXES = ("src/", "scripts/", "configs/", "figspecs/", "jobs/")
DESTRUCTIVE = r"^\s*(?:sudo\s+)?(?:rm|mv|chmod|chown|chattr|truncate|shred|unlink|ln|dd)\b|\bsed\s+-i|\bfind\b.*-(?:delete|exec\s+rm)"
DELETING = r"^\s*(?:sudo\s+)?(?:rm|shred|unlink|truncate)\b|\bfind\b.*-(?:delete|exec\s+rm)"


class Block(Exception):
    """操作を止め、理由を Claude に返す（exit 2）."""


def _decision(decision: str, reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": f"[lab-rules] {reason}",
        }
    }


def _is_reviewer(data: dict) -> bool:
    t = str(data.get("agent_type") or "")
    return t == REVIEWER or t.endswith(":" + REVIEWER)


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
    if _is_reviewer(data):
        for seg in segs:
            if not gate.reviewer_allowed(seg):
                raise Block(f"許可されていないコマンドです: `{seg[:80]}`。{gate.reviewer_allowed_summary()}")
    for seg in segs:
        if re.search(r"\.lab/(?:queue|flows|delegations)", seg) and re.search(
            r">{1,2}|\btee\b|\bsed\s+-i|\b(?:rm|mv|cp|touch|truncate|python[0-9.]*\s+-c|perl|node\s+-e)\b", seg
        ):
            raise Block(
                ".lab/ は直接書き換えません（labkit queue / flow を使う）。承認・却下・回答・委任は人間だけが行います。"
            )

    lab = load_lab(root)
    conf = lab["gate"]
    cwd = Path(data.get("cwd") or root)
    branch = state.git_branch(cwd)
    hits = gate.classify(cmd, conf["protected_branches"], branch)
    reasons: list[str] = []
    for h in hits:
        if h.category == "forbidden":
            raise Block(f"{gate.FORBIDDEN}。人間に依頼してください（`labkit queue list` で ID を伝える）。")
    gated = [h for h in hits if h.category in gate.GATED]
    if gated and conf.get("enabled", True):
        for h in gated:
            d = state.find_delegation(root, h.category, branch)
            if d is None:
                mode = str(data.get("permission_mode") or "default")
                if mode in INTERACTIVE_MODES:
                    return _decision("ask", f"{h.description}。承認ゲートの対象です。実行してよいか確認してください。")
                item = state.request(
                    root,
                    h.category,
                    cmd.strip(),
                    cwd=cwd,
                    reason=h.description,
                    session=str(data.get("session_id") or ""),
                )
                raise Block(
                    f"{h.description} は人間の承認が必要です。承認待ち #{item['id']} として記録しました。"
                    "この操作に依存しない作業を続け、終了時の報告に挙げてください。"
                    f"人間が {root} で `labkit approve {item['id']}`（この種類・このブランチを 24 時間許可）か "
                    f"`labkit delegate {h.category} --hours N` をすると通ります"
                    "（ゲートはこのセッションのプロジェクトで判定するので、別のリポジトリを操作するときもここで承認・委任する）。"
                )
            reasons.append(f"委任 #{d['id']}（{h.category}）")

    if kind == "project":
        readonly = lab["layout"]["readonly"]
        raw_in = state.find_delegation(root, "raw_write")
        toml_ok = state.find_delegation(root, "lab_toml")
        for seg in segs:
            s = seg.strip()
            if re.search(r"\bgit\s+clean\b[^|]*-[a-zA-Z]*x", s):
                raise Block("git clean -x は管理外の data/・runs/・literature/pdfs を消します。実行しないでください。")
            if re.search(r"\bgit\s+(?:checkout|restore)\b.*\bdata/raw\b", s):
                raise Block("data/raw を git で書き換える操作は禁止です。")
            if "data/raw" in s and _raw_write(s):
                if raw_in is None or re.search(DELETING, s):
                    raise Block(
                        "data/raw を変更・削除する操作は禁止です（生データは不変）。搬入は人間が行うか、"
                        "人間が `labkit delegate raw_write --hours N` で委任したときだけ移動でき、その後 `labkit raw freeze` で登録します。"
                    )
                reasons.append(f"委任 #{raw_in['id']}（raw_write）")
            for ro in readonly:
                if ro != "data/raw" and ro in s and _raw_write(s):
                    raise Block(f"{ro} は読み取り専用領域です。変更・削除はしません。")
            if re.search(r"\b(?:rm|chmod)\b[^|]*\bruns/", s):
                raise Block(
                    "run の削除・権限変更は人間が行います。異常終了した run は `labkit runs mark <id> failed --reason ...`。"
                )
            if re.search(r"(?:>|\btee\b|\bsed\s+-i|\bmv\b|\bcp\b|\brm\b)[^|]*\blab\.toml\b", s):
                if toml_ok is None:
                    raise Block(
                        "lab.toml は規約ファイルです。変更案を人間に提示してください（人間は `labkit delegate lab_toml` で委任できる）。"
                    )
                reasons.append(f"委任 #{toml_ok['id']}（lab_toml）")
    return _decision("allow", "、".join(dict.fromkeys(reasons)) + " により許可") if reasons else None


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
    lab = load_lab(root)
    layout = lab["layout"]
    top = r.split("/", 1)[0]
    if r in PROTECTED_FILES:
        if r == "lab.toml" and state.find_delegation(root, "lab_toml") is not None:
            return None
        raise Block(
            f"{r} は規約ファイルです。理由と差分案を人間に提示してください（人間は `labkit delegate lab_toml` で委任できる）。"
        )
    for ro in layout["readonly"]:
        if r == ro or r.startswith(ro.rstrip("/") + "/"):
            if ro == "data/raw" and state.find_delegation(root, "raw_write") is not None:
                return None
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
def _queue_delta(root: Path) -> list[str]:
    s = state.pending_summary(root)
    lines = [
        f"- 承認済み #{it['id']}: {it['category']}（ブランチ {it.get('branch')}）は委任 {it.get('delegation')} の期限まで実行してよい。"
        f"実行したら `labkit queue done {it['id']}`"
        for it in s["approved"]
    ]
    lines += [
        f"- 回答あり #{it['id']}: 質問「{it.get('question')}」→ 回答「{it.get('answer')}」（仮の判断は「{it.get('assumed')}」）。"
        f"取り込んだら `labkit queue done {it['id']}`"
        for it in s["answered"]
    ]
    lines += [
        f"- 却下 #{it['id']}: `{it['command']}`"
        + (f"（理由: {it['note']}）" if it.get("note") else "")
        + f" → 実行しない。確認したら `labkit queue done {it['id']}`"
        for it in s["rejected"]
    ]
    return lines


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
        "- 承認ゲート: 保護ブランチへの push/merge・tag・gh release/merge・raw freeze は hooks が止め、承認待ち（.lab/queue）に積む。"
        "拒否されたら依存しない作業を続け、終了時に ID を報告する。feat ブランチへの push は自由。"
        "判断の分かれる問いは `labkit queue ask` に積んで仮の判断で進む。approve/reject/answer/delegate は人間専用。"
    )
    pv = data.get("plugin_version")
    if pv and pv != __version__:
        lines.append(
            f"- 注意: plugin lab-rules は {pv}、labkit は {__version__}。版を揃える（`/plugin marketplace update lab-standards` / pyproject のタグ）。"
        )
    lines += [
        f"- 委任中 {state.describe_delegation(d)}: 承認を待たずに実行してよい" for d in state.active_delegations(root)
    ]
    lines += _queue_delta(root)
    s = state.pending_summary(root)
    lines += [
        f"- 承認待ち #{it['id']}: `{it['command']}` — 人間の `labkit approve {it['id']}` を待つ" for it in s["pending"]
    ]
    lines += [
        f"- 未回答の質問 #{it['id']}: 「{it.get('question')}」仮の判断「{it.get('assumed')}」で進行中"
        for it in s["open_questions"]
    ]
    for st in active_flows(root):
        lines.append("- " + describe(root, st).replace("\n", "\n  "))
    if data.get("source") == "compact":
        lines.insert(0, "（会話が要約されたため、承認待ち・委任・手順の状態を再掲する）")
    return "\n".join(lines)


def prompt(data: dict, root: Path, kind: str) -> dict | None:
    lines = _queue_delta(root)
    if not lines:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "[lab-rules] 人間の操作による更新:\n" + "\n".join(lines),
        }
    }


# ---- Stop ----
def _counter(session_id: str) -> Path:
    base = Path(os.environ.get("CLAUDE_PLUGIN_DATA") or Path.home() / ".cache" / "lab-rules")
    base.mkdir(parents=True, exist_ok=True)
    return base / f"stop-{session_id or 'unknown'}.json"


def stop(data: dict, root: Path, kind: str) -> dict | None:
    if kind != "project":
        return None
    from labkit._util import git
    from labkit.check import run_check
    from labkit.devlog import devlog_path, section_bodies, update

    lab = load_lab(root)
    sid = str(data.get("session_id") or "")
    mine = [i for i in state.pending_summary(root)["pending"] if sid and i.get("session_id") == sid]
    if mine:
        ids = ", ".join(f"#{i['id']}" for i in mine)
        return {
            "systemMessage": f"[lab-rules] 承認待ち {ids} があるため終了を許可します。人間: `labkit queue list` → `labkit approve <ID>`"
        }
    problems: list[str] = []
    keys: list[str] = []  # 違反 1 件ごとの識別（上限で委ねた違反を覚えるため）
    issues, mode = run_check(root=root, claims=True)
    errs = [str(i) for i in issues if i.severity == "error"]
    if errs and mode == "strict":
        problems.append("`labkit check --claims` の違反:\n" + "\n".join(errs)[-3500:])
        keys += errs
    if lab["claude"]["require_devlog"]:
        status = git(root, "status", "--porcelain", "--untracked-files=all") or ""
        changed = [ln[3:] for ln in status.splitlines() if ln[3:].startswith(CODE_PREFIXES)]
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
            out = pretool_bash(data, root, kind) if tool == "Bash" else pretool_write(data, root, kind)
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
