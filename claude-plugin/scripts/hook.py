"""lab-rules の hook 入口（標準ライブラリのみ）。判定はすべて labkit（`labkit hook <event>`）が行う.

プロジェクトの venv の labkit → 本体（labkit/python/.venv）→ PATH の順に探し、stdin の JSON をそのまま渡す。
labkit が見つからなければ何もしない（SessionStart だけ 1 行知らせる）。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdin, sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def find_root(start: Path) -> Path | None:
    for d in (start, *start.parents):
        if (d / "lab.toml").is_file() or ((d / "copier.yml").is_file() and (d / "labkit" / "python").is_dir()):
            return d
    return None


def labkit_cmd(root: Path) -> list[str] | None:
    for venv in (root / ".venv", root / "labkit" / "python" / ".venv"):
        for exe in (venv / "bin" / "labkit", venv / "Scripts" / "labkit.exe"):
            if exe.is_file():
                return [str(exe)]
    if shutil.which("labkit"):
        return ["labkit"]
    if shutil.which("uv") and (root / "pyproject.toml").is_file():
        return ["uv", "run", "--quiet", "labkit"]
    return None


def main() -> int:
    event = sys.argv[1]
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        data = {}
    root = find_root(Path(data.get("cwd") or ".").resolve())
    if root is None:
        return 0
    cmd = labkit_cmd(root)
    if cmd is None:
        if event == "session":
            print("[lab-rules] labkit が見つからないため規約の検査は無効です。`uv sync` で環境を作ってください。")
        return 0
    version = json.loads((Path(__file__).resolve().parents[1] / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    r = subprocess.run([*cmd, "hook", event, "--plugin-version", version], input=raw, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=root)
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
