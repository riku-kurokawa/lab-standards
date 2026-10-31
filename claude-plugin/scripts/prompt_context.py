"""UserPromptSubmit: 承認済み・未実行の要求、未回答／回答済みの質問、進行中の手順を毎回の入力に添える.

人間が戻って「承認したので続けて」と言えば、どの ID が承認済みかを Claude が知っている状態にする。
何も無ければ何も出さない。
"""

from __future__ import annotations

import json

from _labcommon import flow_context, queue_context, read_input
from _labstate import find_scope


def main() -> None:
    data = read_input()
    sc = find_scope(data.get("cwd") or ".")
    if sc is None:
        return
    root, _kind = sc
    lines = queue_context(root) + flow_context(root)
    if not lines:
        return
    ctx = "[lab-rules] 承認キューと手順の状態:\n" + "\n".join(lines)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
