"""リリース補助: 版番号を全ファイルで揃え、整合性を検査する.

    python tools/release.py 1.0.0        # 版を書き換え、検査する
    python tools/release.py --check      # 書き換えずに整合性だけ検査（CI 用）

検査内容: 全ファイルの版が一致 / CHANGELOG に該当版の節がある / 作業ブランチが main でない（書き換え時）
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (ファイル, 正規表現（グループ 1 が版）, 置換テンプレート)
TARGETS = [
    ("labkit/python/pyproject.toml", r'^version = "([^"]+)"', 'version = "{v}"'),
    ("labkit/python/src/labkit/_version.py", r'^__version__ = "([^"]+)"', '__version__ = "{v}"'),
    ("claude-plugin/.claude-plugin/plugin.json", r'^  "version": "([^"]+)"', '  "version": "{v}"'),
    ("copier.yml", r'^  default: "v([^"]+)"\s*$', '  default: "v{v}"'),
]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def current_versions() -> dict[str, str | None]:
    out = {}
    for rel, pat, _ in TARGETS:
        m = re.search(pat, (ROOT / rel).read_text(encoding="utf-8"), re.M)
        out[rel] = m.group(1) if m else None
    return out


def set_version(v: str) -> None:
    for rel, pat, tpl in TARGETS:
        p = ROOT / rel
        text = p.read_text(encoding="utf-8")
        new, n = re.subn(pat, tpl.format(v=v), text, count=1, flags=re.M)
        if n != 1:
            raise SystemExit(f"{rel}: 版の行が見つかりません（パターン {pat}）")
        p.write_text(new, encoding="utf-8", newline="\n")  # Windows でも LF のまま


def check(expected: str | None = None) -> list[str]:
    errors = []
    vers = current_versions()
    missing = [k for k, v in vers.items() if v is None]
    if missing:
        errors.append(f"版の行が見つからない: {missing}")
    found = {v for v in vers.values() if v}
    if len(found) > 1:
        errors.append("版が揃っていない:\n" + "\n".join(f"  {k}: {v}" for k, v in vers.items()))
    v = expected or (found.pop() if len(found) == 1 else None)
    if v and not re.search(rf"^## v{re.escape(v)}\b", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), re.M):
        errors.append(f"CHANGELOG.md に '## v{v}' の節がありません")
    json.loads((ROOT / "claude-plugin/.claude-plugin/plugin.json").read_text(encoding="utf-8"))
    return errors


def main(argv: list[str]) -> int:
    if argv == ["--check"]:
        errs = check()
        print("\n".join(errs) if errs else f"OK: 版 {next(iter(set(current_versions().values())))} で揃っています")
        return 1 if errs else 0
    if len(argv) != 1 or not SEMVER.match(argv[0].lstrip("v")):
        print(__doc__)
        return 2
    v = argv[0].lstrip("v")
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()
    if branch == "main":
        print("警告: main ブランチ上です。通常は feat/* ブランチでリリース準備を行います。")
    pre = [e for e in check(v) if "CHANGELOG" in e]  # 書き換える前に確かめる（途中で止めて半端な状態を残さない）
    if pre:
        print("\n".join(pre))
        return 1
    set_version(v)
    errs = check(v)
    if errs:
        print("\n".join(errs))
        return 1
    print(f"版を {v} に揃えました。次: テスト → commit → main にマージ → git tag v{v} → git push origin main --tags")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
