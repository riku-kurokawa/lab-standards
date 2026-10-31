"""PreToolUse(Bash): 承認ゲート・手順（flow）の禁止操作・生データ/run/規約ファイルを壊す操作を止める.

判定の順:
  1. Claude が実行してはいけない操作（labkit approve/reject/answer）→ 常に拒否
  2. lab-reviewer（レビュー agent）は許可リストの読み取りコマンドだけ（_labgate.reviewer_allowed。載っていなければ拒否）
  3. 進行中の flow の段階で禁止されている操作 → 拒否（「今は <段階>。先に <条件> が必要」）
  4. 承認ゲートの対象（push, tag, merge, gh release/merge, raw freeze, copier）:
     承認済み（コマンド全文 + HEAD が一致、未使用、期限内）→ 使用済みにして許可
     presence=here かつ確認画面が出るモード → ask
     それ以外（away）→ 拒否し、承認待ちを .lab/queue に記録
  5. プロジェクトの規約（data/raw・runs・lab.toml の保護）
lab-standards 本体（copier.yml + labkit/）では 1〜4 だけを適用する。
"""

from __future__ import annotations

import re
from pathlib import Path

import _labgate as gate
from _labcommon import NO_PROMPT_MODES, block, decide, describe_condition, is_reviewer, load_lab, read_input
from _labstate import (
    active_flows,
    consume_approval,
    current_stage,
    find_scope,
    find_valid_approval,
    get_presence,
    git_branch,
    git_head,
    load_gate_conf,
    request_approval,
)

DESTRUCTIVE = r"^\s*(?:sudo\s+)?(?:rm|mv|chmod|chown|chattr|truncate|shred|unlink|ln|dd)\b|\bsed\s+-i|\bfind\b.*-(?:delete|exec\s+rm)"


def raw_write(s: str) -> bool:
    """data/raw を書き換えるか（読むだけなら False）."""
    if re.search(DESTRUCTIVE, s):
        return True
    if re.search(r">{1,2}\s*\S*data/raw", s) or re.search(r"\btee\b[^|]*data/raw", s):
        return True
    if re.match(r"^\s*(?:cp|rsync|install)\b", s):
        args = [a for a in s.split()[1:] if not a.startswith("-")]
        return bool(args) and "data/raw" in args[-1]  # コピー先が data/raw
    return False


def harness_state_write(s: str) -> bool:
    """承認記録・キュー・flow の状態を Bash で直接書き換えようとしているか."""
    return bool(
        re.search(r"\.lab/(?:approvals|queue|flows)", s)
        and re.search(
            r">{1,2}|\btee\b|\bsed\s+-i|\b(?:rm|mv|cp|touch|install|truncate|python[0-9.]*\s+-c|perl|ruby|node\s+-e)\b",
            s,
        )
    )


def gate_check(data: dict, cmd: str, root, kind: str) -> None:
    conf = load_gate_conf(root, kind)
    cwd_s = data.get("cwd") or str(root)
    cwd = Path(cwd_s)
    hits = gate.classify(cmd, conf.get("protected_branches", ["main", "master"]), git_branch(cwd))

    for h in gate.forbidden(hits):
        block(
            f"{h.description} は Claude が実行できません。人間に依頼してください（`labkit queue list` で ID を伝える）。"
        )

    if kind == "project":
        for st in active_flows(root):
            s = current_stage(st)
            bad = gate.flow_hits(hits, s.get("forbid", []))
            if bad:
                conds = (
                    "; ".join(describe_condition(c) for c in s.get("done", [])) or "（この段階の作業を終えて advance）"
                )
                block(
                    f"今は flow {st['flow']} の段階「{s['name']}」で、{bad[0].description}（カテゴリ "
                    f"{gate.FLOW_CATEGORY.get(bad[0].category)}）は禁止です。先に {conds} が必要"
                    f"（`labkit flow status` → `labkit flow advance`）。"
                )

    if not conf.get("enabled", True):
        return
    g = gate.gated(hits)
    if not g:
        return
    command = cmd.strip()
    # `git -C <dir> push` のように別リポジトリを操作するなら、承認はそのリポジトリの HEAD に結び付ける
    target = cwd
    for h in g:
        if h.repo_dir:
            target = (cwd / h.repo_dir) if not Path(h.repo_dir).is_absolute() else Path(h.repo_dir)
            break
    head = git_head(target)
    rec = find_valid_approval(root, command, head)
    if rec is not None:
        consume_approval(root, rec)
        decide("allow", f"承認 #{rec['id']} を使用（1 回限り）: {g[0].description}")
    what = "、".join(dict.fromkeys(h.description for h in g))
    presence = get_presence(root)
    mode = str(data.get("permission_mode") or "")
    if presence == "here" and mode not in NO_PROMPT_MODES:
        decide("ask", f"{what}。承認ゲートの対象です。実行してよいか確認してください。")
    item = request_approval(
        root,
        command,
        cwd=target,
        session_id=str(data.get("session_id") or ""),
        reason=what
        + ("" if presence == "away" else f"（presence=here だが permission_mode={mode} では確認画面が出ないため）"),
    )
    block(
        f"{what} は人間の承認が必要です（presence={presence}）。承認待ち #{item['id']} として記録しました。"
        f"この操作に依存しない作業を続け、終了時の報告に挙げてください。人間が `labkit approve {item['id']}` した後、"
        f"同じディレクトリ・同じ HEAD（{head[:7] if head else 'なし: git リポジトリではない'}）で同じコマンド全文を実行すると通ります。"
    )


def main() -> None:
    data = read_input()
    cmd = (data.get("tool_input") or {}).get("command", "")
    sc = find_scope(data.get("cwd") or ".")
    if sc is None or not cmd:
        return
    root, kind = sc

    if is_reviewer(data):
        for seg in gate.segments(cmd):
            if not gate.reviewer_allowed(seg):
                block(f"許可されていないコマンドです: `{seg[:80]}`。{gate.reviewer_allowed_summary()}")

    for seg in gate.segments(cmd):
        if harness_state_write(seg):
            block(
                ".lab/approvals・.lab/queue・.lab/flows は直接書き換えません。labkit のコマンド"
                "（queue / flow）を使ってください。承認・却下・回答は人間だけが行います。"
            )

    gate_check(data, cmd, root, kind)

    if kind != "project":
        return
    lab = load_lab(root)
    readonly = lab.get("layout", {}).get("readonly", ["data/raw"])
    for seg in gate.segments(cmd):
        s = seg.strip()
        if re.search(r"\bgit\s+clean\b[^|]*-[a-zA-Z]*x", s):
            block("git clean -x は管理外の data/・runs/・literature/pdfs を消します。実行しないでください。")
        if re.search(r"\bgit\s+(?:checkout|restore)\b.*\bdata/raw\b", s):
            block("data/raw を git で書き換える操作は禁止です。")
        if "data/raw" in s and raw_write(s):
            block(
                "data/raw を変更・削除する操作は禁止です（生データは不変）。生データの追加は人間が行い `labkit raw freeze` で登録します。"
            )
        for ro in readonly:
            if ro != "data/raw" and ro in s and raw_write(s):
                block(f"{ro} は読み取り専用領域です。変更・削除はしません。")
        if re.search(r"\brm\b[^|]*\bruns/", s) or re.search(r"\bchmod\b[^|]*\bruns/", s):
            block("run の削除・権限変更は人間が行います。不要な run があれば一覧を提示して判断を仰いでください。")
        if re.search(r"(?:>|\btee\b|\bsed\s+-i|\bmv\b|\bcp\b|\brm\b)[^|]*\blab\.toml\b", s):
            block("lab.toml は規約ファイルです。Claude は変更しません。")


if __name__ == "__main__":
    main()
