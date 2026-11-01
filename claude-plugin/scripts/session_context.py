"""SessionStart（startup/resume/clear/compact）: CLAUDE.md に書けない「状態」を文脈に入れる.

規約そのものは CLAUDE.md（compact 後も Claude Code が再読込する）と skill lab-conventions にあるので、ここでは繰り返さない。
入れるのは、今日の開発ログの有無、link 状態、presence、進行中の flow、承認待ち・質問、最近の run。
承認ゲートの 2 行だけは、v0.2.0 の CLAUDE.md や本体の CLAUDE.md に記述が無いので常に入れる。
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
    "拒否されたら、その操作に依存しない作業を続け、終了時の報告に承認待ち ID を挙げる。承認後は同じリポジトリ・同じ HEAD で同じコマンド全文を実行する。"
    "人間が `labkit delegate <カテゴリ> --hours N` で委任した操作は待たずに進める（`labkit delegate list`）。",
    '- 判断が分かれる問いは質問ツールで止まらず `labkit queue ask "<質問>" --options A B --assumed "<仮の判断と理由>" --impact "<変更時の影響>"` で積み、'
    "仮の判断で進む。`labkit approve/reject/answer` は人間専用で Claude は実行できない。",
]


def recent_runs(root, n=5) -> list[str]:
    runs = root / "runs"
    if not runs.is_dir():
        return []
    out = []
    for d in sorted((p for p in runs.iterdir() if p.is_dir()), reverse=True)[:n]:
        status = "?"
        try:
            status = json.loads((d / "meta.json").read_text(encoding="utf-8")).get("status", "?")
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
        lines.append(
            "ここは lab-standards 本体。CLAUDE.md（メンテナンス規約）に従う。feat/* ブランチで作業し、main では作業しない。"
        )
        lines += GATE_LINES
        lines.append(f"- presence={get_presence(root)}。")
        lines += queue_context(root)
    else:
        lab = load_lab(root)
        today = _dt.date.today().isoformat()
        devlog = root / lab.get("devlog", {}).get("dir", "docs/devlog") / f"{today}.md"
        lines += [
            "規約は CLAUDE.md と skill lab-conventions。承認ゲート・キュー・flow の使い方は skill lab-conventions の「人間が不在でも止まらない」節。",
            f"- 今日の開発ログ {devlog.relative_to(root)}: {'存在する' if devlog.exists() else 'まだ無い（コードを変えた日は `labkit devlog` で作る）'}。",
        ]
        lines += GATE_LINES
        lines.append(f"- presence={get_presence(root)}。")
        py = root / "pyproject.toml"
        if py.is_file():
            m = re.search(r'^labkit\s*=\s*\{[^}]*path\s*=\s*"([^"]+)"', py.read_text(encoding="utf-8"), re.M)
            if m:
                lines.append(
                    f"- 現在 lab-standards 本体を手元参照（link）中: {m.group(1)}。本体の改良は flow improve-standards の手順で進める。"
                    "この状態では commit できない。"
                )
        lines += flow_context(root)
        lines += queue_context(root)
        rr = recent_runs(root)
        if rr:
            lines.append(f"- 最近の run: {', '.join(rr)}")
    if data.get("source") == "compact":
        lines.insert(0, "（会話が要約されたため、承認待ち・手順・presence の状態を再掲する）")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
