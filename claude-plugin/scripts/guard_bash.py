"""PreToolUse(Bash): 生データ・run・規約ファイルを壊すシェル操作を止める."""

from __future__ import annotations

import re

from _labcommon import block, find_root, read_input

DESTRUCTIVE = r"^\s*(?:sudo\s+)?(?:rm|mv|chmod|chown|chattr|truncate|shred|unlink|ln|dd)\b|\bsed\s+-i|\bfind\b.*-(?:delete|exec\s+rm)"


def raw_write(s: str) -> bool:
    """data/raw を書き換えるか（読むだけなら False）."""
    if re.search(DESTRUCTIVE, s):
        return True
    if re.search(r">{1,2}\s*\S*data/raw", s) or re.search(r"\btee\b[^|]*data/raw", s):
        return True
    if re.match(r"^\s*(?:cp|rsync|install)\b", s):
        args = [a for a in s.split()[1:] if not a.startswith("-")]
        return bool(args) and "data/raw" in args[-1]  # コピー先が data/raw
    return False


def main() -> None:
    data = read_input()
    cmd = (data.get("tool_input") or {}).get("command", "")
    root = find_root(data.get("cwd") or ".")
    if root is None or not cmd:
        return
    for seg in re.split(r"&&|\|\||;|\n", cmd):
        s = seg.strip()
        if not s:
            continue
        if re.search(r"\bgit\s+clean\b[^|]*-[a-zA-Z]*x", s):
            block("git clean -x は管理外の data/・runs/・literature/pdfs を消します。実行しないでください。")
        if re.search(r"\bgit\s+(?:checkout|restore)\b.*\bdata/raw\b", s):
            block("data/raw を git で書き換える操作は禁止です。")
        if "data/raw" in s and raw_write(s):
            block("data/raw を変更・削除する操作は禁止です（生データは不変）。生データの追加は人間が行い `labkit raw freeze` で登録します。")
        if re.search(r"\brm\b[^|]*\bruns/", s) or re.search(r"\bchmod\b[^|]*\bruns/", s):
            block("run の削除・権限変更は人間が行います。不要な run があれば一覧を提示して判断を仰いでください。")
        if re.search(r"(?:>|\btee\b|\bsed\s+-i|\bmv\b|\bcp\b|\brm\b)[^|]*\blab\.toml\b", s):
            block("lab.toml は規約ファイルです。Claude は変更しません。")


if __name__ == "__main__":
    main()
