"""Stop: 応答を終える前に labkit check と開発ログの有無を確かめ、違反があれば作業を続けさせる."""

from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
import sys
from pathlib import Path

from _labcommon import find_root, labkit_cmd, load_lab, read_input


def changed_code(root: Path) -> list[str]:
    try:
        out = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True,
                             check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    files = [line[3:].strip() for line in out.splitlines() if len(line) > 3]
    return [f for f in files if f.startswith(("src/", "scripts/", "jl/", "configs/", "figspecs/", "jobs/"))]


def counter_file(session: str) -> Path:
    base = Path(os.environ.get("CLAUDE_PLUGIN_DATA") or Path.home() / ".cache" / "lab-rules")
    base.mkdir(parents=True, exist_ok=True)
    return base / f"stop-{session or 'unknown'}.json"


def main() -> None:
    data = read_input()
    root = find_root(data.get("cwd") or ".")
    if root is None:
        return
    lab = load_lab(root)
    if not lab:
        return
    problems: list[str] = []

    cmd = labkit_cmd(root)
    if cmd:
        # L050（本体を link 中）は改良作業中の正常な状態なので、ここでは止めない（commit 時に pre-commit が止める）
        res = subprocess.run([*cmd, "check", "--ignore", "L050"], cwd=root, capture_output=True, text=True,
                             check=False, timeout=240)
        if res.returncode != 0:
            problems.append("`labkit check` の違反:\n" + (res.stdout + res.stderr).strip()[-3500:])
    else:
        problems.append("labkit が見つかりません。`uv sync` で環境を作ってください。")

    if lab.get("claude", {}).get("require_devlog", True):
        changed = changed_code(root)
        today = _dt.date.today().isoformat()
        devlog = root / lab.get("devlog", {}).get("dir", "docs/devlog") / f"{today}.md"
        if changed and not devlog.exists():
            problems.append(f"コードを変更しましたが今日の開発ログがありません。`labkit devlog` で {devlog.relative_to(root)} を作り、"
                            f"必須見出しに沿って今回の作業を記録してください（変更: {', '.join(changed[:8])}）。")

    cf = counter_file(data.get("session_id", ""))
    state = json.loads(cf.read_text()) if cf.exists() else {"blocks": 0}
    if not problems:
        cf.unlink(missing_ok=True)
        return
    limit = int(lab.get("claude", {}).get("max_stop_blocks", 3))
    if state["blocks"] >= limit:
        cf.unlink(missing_ok=True)
        print(json.dumps({"systemMessage": f"[lab-rules] 規約違反が {limit} 回の修正で解消しませんでした。人間の確認が必要です。"},
                         ensure_ascii=False))
        return
    state["blocks"] += 1
    cf.write_text(json.dumps(state))
    print("[lab-rules] 作業完了の条件を満たしていません。以下を解消してから終了してください:\n\n" + "\n\n".join(problems),
          file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
