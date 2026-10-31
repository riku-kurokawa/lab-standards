"""SessionStart（startup/resume/clear/compact）: プロジェクト規約の要点を文脈に入れる.

compact（会話の要約）の後にも実行されるので、長い作業で規約が抜け落ちるのを防ぐ。
"""

from __future__ import annotations

import datetime as _dt
import json
import re

from _labcommon import find_root, load_lab, read_input


def recent_runs(root, n=5) -> list[str]:
    runs = root / "runs"
    if not runs.is_dir():
        return []
    out = []
    for d in sorted((p for p in runs.iterdir() if p.is_dir()), reverse=True)[:n]:
        status = "?"
        try:
            status = json.loads((d / "meta.json").read_text()).get("status", "?")
        except (OSError, json.JSONDecodeError):
            pass
        out.append(f"{d.name} ({status})")
    return out


def main() -> None:
    data = read_input()
    root = find_root(data.get("cwd") or ".")
    if root is None:
        return
    lab = load_lab(root)
    if not lab:
        return
    today = _dt.date.today().isoformat()
    devlog = root / lab.get("devlog", {}).get("dir", "docs/devlog") / f"{today}.md"
    lines = [
        "このプロジェクトは lab-standards の規約に従っている（規約の設定源は lab.toml、要約は CLAUDE.md）。",
        f"- Write/Edit できる場所: {', '.join(lab['layout']['writable'])}。一時ファイルは scratch/。",
        "- data/ と runs/ はスクリプト経由（labkit.save / labkit.Run）でのみ生成される。data/raw と lab.toml は変更不可。",
        "- 図は figspecs/<name>.toml と `labkit fig <spec> --run <run_id>` で作る。描画ライブラリは直接使わない（`labkit fig list` で一覧）。",
        "- 保存形式は HDF5（配列）と Parquet（表）。コードに絶対パスは書かず labkit.datapath と configs/paths を使う。",
        "- 文献は `labkit lit add`、サーベイは `labkit lit survey` で literature/ に作る。",
        f"- 作業の完了条件は `make check` が通ること。コードを変えた日は開発ログ {devlog.relative_to(root)} を更新する"
        f"（{'存在する' if devlog.exists() else 'まだ無い。`labkit devlog` で作成'}）。",
        "- 詳細手順は lab-rules plugin の skills（new-experiment, make-figure, write-devlog, literature-survey など）にある。",
        "- 雛形・labkit・hooks 自体を改良したくなったら、プロジェクト内で直さず skill improve-standards に従う。",
    ]
    py = root / "pyproject.toml"
    if py.is_file():
        m = re.search(r'^labkit\s*=\s*\{[^}]*path\s*=\s*"([^"]+)"', py.read_text(encoding="utf-8"), re.M)
        if m:
            lines.append(f"- 現在 lab-standards 本体を手元参照（link）中: {m.group(1)}。本体の改良は skill improve-standards の手順で進める。"
                         "この状態では commit できない。")
    rr = recent_runs(root)
    if rr:
        lines.append(f"- 最近の run: {', '.join(rr)}")
    if data.get("source") == "compact":
        lines.insert(0, "（会話が要約されたため、プロジェクト規約を再掲する）")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
