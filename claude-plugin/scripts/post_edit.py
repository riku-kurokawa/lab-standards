"""PostToolUse(Write|Edit|MultiEdit): Python ファイルを ruff で整形し、残った lint 違反を Claude に返す."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from _labcommon import find_root, read_input, tool_cmd


def main() -> None:
    data = read_input()
    target = (data.get("tool_input") or {}).get("file_path")
    if not target or not target.endswith(".py"):
        return
    p = Path(target)
    root = find_root(p)
    if root is None or not p.is_file():
        return
    rel = p.resolve().relative_to(root.resolve()).as_posix()
    if rel.startswith(("scratch/", "legacy/")):
        return
    ruff = tool_cmd(root, "ruff")
    if ruff is None:
        return
    subprocess.run([*ruff, "format", "--quiet", str(p)], cwd=root, check=False)
    subprocess.run([*ruff, "check", "--fix", "--quiet", str(p)], cwd=root, check=False, capture_output=True)
    res = subprocess.run(
        [*ruff, "check", "--output-format", "concise", str(p)], cwd=root, capture_output=True, text=True, check=False
    )
    if res.returncode != 0 and res.stdout.strip():
        print(
            f"[lab-rules] {rel} に lint 違反が残っています。修正してください:\n{res.stdout.strip()[:3000]}",
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
