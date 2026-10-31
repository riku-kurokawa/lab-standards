"""PreToolUse(Write|Edit|MultiEdit|NotebookEdit): 書き込み先と内容を規約で検査する."""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from _labcommon import PROTECTED_FILES, block, find_root, load_lab, read_input, rel


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
    root = find_root(p)
    if root is None:
        return  # lab-standards のプロジェクトではない
    r = rel(p, root)
    if r is None:
        return
    lab = load_lab(root)
    if not lab:
        return
    layout = lab["layout"]

    if r in PROTECTED_FILES:
        block(f"{r} は規約ファイルです。変更が必要なら、理由と差分案を人間に提示してください（Claude は編集しない）。")
    for ro in layout["readonly"]:
        if r == ro or r.startswith(ro.rstrip("/") + "/"):
            block(f"{r} は読み取り専用領域（{ro}）です。生データは不変。派生データは scripts から labkit.save で data/interim か data/processed に作ってください。")
    top = r.split("/", 1)[0]
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
