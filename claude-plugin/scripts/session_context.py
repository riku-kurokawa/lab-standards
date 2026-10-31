"""SessionStart（startup/resume/clear/compact）: プロジェクト規約・承認キュー・進行中の手順の要点を文脈に入れる.

compact（会話の要約）の後にも実行されるので、長い作業で規約が抜け落ちるのを防ぐ。
lab-standards 本体では承認ゲートとキューの状態だけを入れる。
"""

from __future__ import annotations

import datetime as _dt
import json
import re

from _labcommon import flow_context, load_lab, queue_context, read_input
from _labstate import find_scope, get_presence

GATE_LINES = [
    "- 承認ゲート: git push / git tag / 保護ブランチへの merge / gh pr merge / gh release / labkit raw freeze / copier は"
    " hooks が止める。presence=away（既定）では拒否して承認待ちキュー（.lab/queue）に記録される。"
    "拒否されたら、その操作に依存しない作業を続け、終了時の報告に承認待ち ID を挙げる。承認後は同じ cwd・同じ HEAD で同じコマンド全文を実行する。",
    "- 判断が分かれる問いは質問ツールで止まらず `labkit queue ask \"<質問>\" --options A B --assumed \"<仮の判断と理由>\" --impact \"<変更時の影響>\"` で積み、"
    "仮の判断で進む（AGENT_QUEUE.md があればそこにも書く）。`labkit approve/reject/answer` は人間専用で Claude は実行できない。",
]


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
    sc = find_scope(data.get("cwd") or ".")
    if sc is None:
        return
    root, kind = sc
    lines: list[str] = []
    if kind == "standards":
        lines.append("ここは lab-standards 本体。CLAUDE.md（メンテナンス規約）に従う。feat/* ブランチで作業し、main では作業しない。")
        lines += GATE_LINES
        lines.append(f"- presence={get_presence(root)}。")
        lines += queue_context(root)
    else:
        lab = load_lab(root)
        if not lab:
            return
        today = _dt.date.today().isoformat()
        devlog = root / lab.get("devlog", {}).get("dir", "docs/devlog") / f"{today}.md"
        lines += [
            "このプロジェクトは lab-standards の規約に従っている（規約の設定源は lab.toml、要約は CLAUDE.md）。",
            f"- Write/Edit できる場所: {', '.join(lab['layout']['writable'])}。一時ファイルは scratch/。",
            "- data/ と runs/ はスクリプト経由（labkit.save / labkit.Run）でのみ生成される。data/raw と lab.toml は変更不可。",
            "- 図は figspecs/<name>.toml と `labkit fig <spec> --run <run_id>` で作る。描画ライブラリは直接使わない（`labkit fig list` で一覧）。",
            "- 保存形式は HDF5（配列）と Parquet（表）。コードに絶対パスは書かず labkit.datapath と configs/paths を使う。",
            "- 文献は `labkit lit add`、サーベイは `labkit lit survey` で literature/ に作る。",
            "- 文書（開発ログ・ADR・レビュー）で run の数値を書くときは `labkit cite <run_id> <key> [--unit dB]` の出力"
            "（例 `12.3 dB [run:<run_id>:snr_db]`）を貼る。labkit check L032/L033 が runs/ の実データと照合する。",
            f"- 作業の完了条件は `make check` が通ること。コードを変えた日は開発ログ {devlog.relative_to(root)} を更新する"
            f"（{'存在する' if devlog.exists() else 'まだ無い。`labkit devlog` で作成'}）。",
            "- 詳細手順は lab-rules plugin の skills（new-experiment, make-figure, write-devlog, literature-survey, migrate-project, improve-standards）にある。",
            "- 雛形・labkit・hooks 自体を改良したくなったら、プロジェクト内で直さず `labkit flow start improve-standards`（skill improve-standards）。",
            "- レビュー記録 docs/reviews/ は lab-reviewer agent だけが書ける（メインのエージェントは書けない）。",
        ]
        lines += GATE_LINES
        lines.append(f"- presence={get_presence(root)}。")
        py = root / "pyproject.toml"
        if py.is_file():
            m = re.search(r'^labkit\s*=\s*\{[^}]*path\s*=\s*"([^"]+)"', py.read_text(encoding="utf-8"), re.M)
            if m:
                lines.append(f"- 現在 lab-standards 本体を手元参照（link）中: {m.group(1)}。本体の改良は flow improve-standards の手順で進める。"
                             "この状態では commit できない。")
        lines += flow_context(root)
        lines += queue_context(root)
        rr = recent_runs(root)
        if rr:
            lines.append(f"- 最近の run: {', '.join(rr)}")
    if data.get("source") == "compact":
        lines.insert(0, "（会話が要約されたため、規約・承認待ち・手順の状態を再掲する）")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
