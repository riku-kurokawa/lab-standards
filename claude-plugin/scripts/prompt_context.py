"""UserPromptSubmit: 人間の操作で生じた差分（承認済み・未実行 / 回答あり / 却下）だけを添える.

承認待ち・未回答の質問・手順の段階は SessionStart（compact 含む）と拒否時の hook が既に伝えているので繰り返さない。
何も無ければ何も出さない（通常のプロンプトでは 0 行）。
"""

from __future__ import annotations

import json

from _labcommon import queue_delta_context, read_input
from _labstate import find_scope


def main() -> None:
    data = read_input()
    sc = find_scope(data.get("cwd") or ".")
    if sc is None:
        return
    root, _kind = sc
    lines = queue_delta_context(root)
    if not lines:
        return
    ctx = "[lab-rules] 人間の操作による更新:\n" + "\n".join(lines)
    print(
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
