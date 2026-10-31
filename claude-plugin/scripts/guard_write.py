"""PreToolUse(Write|Edit|MultiEdit|NotebookEdit): 書き込み先と内容を規約で検査する.

v0.3.0 で追加:
  - .lab/approvals, .lab/queue, .lab/flows への直接書き込みは拒否（labkit のコマンド経由のみ）
  - docs/reviews/（レビュー記録）は agent_type=lab-reviewer のときだけ書ける。lab-reviewer はそれ以外に書けない
  - 進行中の flow の段階が "code" を禁止していれば src/scripts/... への書き込みを拒否
  - lab-standards 本体（copier.yml + labkit/）では上の 2 点（状態とレビュー記録）だけを適用
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from _labcommon import (
    CODE_DIRS,
    HARNESS_STATE_DIRS,
    PROTECTED_FILES,
    REVIEW_DIR,
    block,
    describe_condition,
    is_reviewer,
    load_lab,
    read_input,
    rel,
)
from _labstate import active_flows, current_stage, find_scope


def new_text(tool: str, ti: dict) -> str:
    if tool == "Write":
        return ti.get("content", "")
    if tool == "Edit":
        return ti.get("new_string", "")
    if tool == "MultiEdit":
        return "\n".join(e.get("new_string", "") for e in ti.get("edits", []))
    if tool == "NotebookEdit":
        return ti.get("new_source", "")
    return ""


def harness_rules(data: dict, r: str) -> None:
    if r == ".lab-standards-root" or any(r == d or r.startswith(d + "/") for d in HARNESS_STATE_DIRS):
        block(f"{r} はハーネスの状態です。直接書かず labkit のコマンド（queue ask/done, flow start/advance）を使います。"
              "承認・却下・回答は人間だけが行います。")
    in_reviews = r == REVIEW_DIR or r.startswith(REVIEW_DIR + "/")
    if is_reviewer(data):
        if not in_reviews:
            block(f"lab-reviewer が書けるのはレビュー記録（{REVIEW_DIR}/YYYY-MM-DD_<flow>_<段階>.md）だけです。{r} には書けません。")
        return
    if in_reviews:
        block(f"{r} はレビュー記録です。独立した lab-reviewer agent だけが書けます（自己採点の防止）。"
              "Agent ツールで lab-reviewer を起動し、レビュー記録を書かせてください。")


def main() -> None:
    data = read_input()
    tool = data.get("tool_name", "")
    ti = data.get("tool_input", {}) or {}
    target = ti.get("file_path") or ti.get("notebook_path")
    if not target:
        return
    p = Path(target)
    if not p.is_absolute():
        p = Path(data.get("cwd") or ".") / p
    sc = find_scope(p)
    if sc is None:
        return  # lab-standards のプロジェクトでも本体でもない
    root, kind = sc
    r = rel(p, root)
    if r is None:
        return
    harness_rules(data, r)
    if kind != "project":
        return

    lab = load_lab(root)
    if not lab:
        return
    layout = lab["layout"]
    top = r.split("/", 1)[0]

    for st in active_flows(root):
        s = current_stage(st)
        if "code" in s.get("forbid", []) and top in CODE_DIRS:
            conds = "; ".join(describe_condition(c) for c in s.get("done", []))
            block(f"今は flow {st['flow']} の段階「{s['name']}」で、コードの変更（{top}/）は禁止です。"
                  f"先に {conds or 'この段階の作業'} が必要（`labkit flow status`）。下書きは scratch/ へ。")

    if r in PROTECTED_FILES:
        block(f"{r} は規約ファイルです。変更が必要なら、理由と差分案を人間に提示してください（Claude は編集しない）。")
    for ro in layout["readonly"]:
        if r == ro or r.startswith(ro.rstrip("/") + "/"):
            block(f"{r} は読み取り専用領域（{ro}）です。生データは不変。派生データは scripts から labkit.save で data/interim か data/processed に作ってください。")
    if top == "runs":
        block("runs/ はスクリプト（labkit の Run）だけが作ります。結果を変えたいならコード/設定を直して新しい run を実行してください。")
    if top == "data":
        block("data/ のファイルは手で書きません。scripts から labkit.save / labkit.writer 経由で生成してください（来歴サイドカーが付きます）。")
    if top not in layout["writable"] and r not in layout["writable"]:
        block(f"{r} は書き込み可能な場所ではありません。可能: {', '.join(layout['writable'])}。一時ファイルは scratch/ へ。新しい置き場所が必要なら人間に相談してください。")

    if p.suffix not in {".py", ".jl", ".ipynb"}:
        return
    text = new_text(tool, ti)
    c = lab["check"]
    is_jl = p.suffix == ".jl"

    def allowed(key: str) -> bool:
        return any(fnmatch.fnmatch(r, pat) for pat in c.get(key, []))

    if not allowed("plot_import_allowed"):
        mods = "|".join(map(re.escape, c["banned_plot_imports"]))
        pat = rf"^\s*(?:using|import)\s+[^#\n]*\b({mods})\b" if is_jl else rf"^\s*(?:import|from)\s+({mods})\b"
        m = re.search(pat, text, re.M)
        if m:
            block(f"{m.group(1)} を直接使って図を作ることは禁止です。figspecs/<name>.toml を書いて `labkit fig figspecs/<name>.toml --run <run_id>` を使ってください（`labkit fig list` でテンプレート一覧）。合うテンプレートが無ければ、skill add-figure-template に従って人間に提案してください。")
    if not allowed("format_allowed"):
        mods = "|".join(map(re.escape, c["banned_formats"]))
        pat = rf"^\s*(?:using|import)\s+[^#\n]*\b({mods})\b" if is_jl else rf"^\s*(?:import|from)\s+({mods})\b"
        m = re.search(pat, text, re.M)
        if m:
            block(f"{m.group(1)} は禁止された保存形式です。配列は HDF5、表は Parquet で labkit.save を使ってください。")


if __name__ == "__main__":
    main()
