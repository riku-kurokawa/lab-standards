"""テキストの読み書きは encoding を明示する（Windows の既定は cp932 で、日本語の meta.json や devlog、hooks の出力が壊れる）.

ruff の PLW1514 は preview 専用で、しかも `(root / "x").write_text(...)` のように受け手が Path と分からない呼び出しを見ない。
ここで AST を歩いて検査する。対象: labkit の src/tests、hooks、tools。
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TARGETS = ["labkit/python/src", "labkit/python/tests", "claude-plugin/scripts", "claude-plugin/tests", "tools"]
TEXT_METHODS = {"read_text", "write_text", "open"}
# これらのモジュール関数の open は対象外（バイナリ or 別物）
NOT_FILE_OPEN = {"os", "tarfile", "zipfile", "webbrowser", "gzip", "h5py", "urlopen"}


def _kw(call: ast.Call, name: str) -> ast.expr | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def _is_binary(call: ast.Call) -> bool:
    mode = _kw(call, "mode")
    if mode is None and len(call.args) >= 2 and isinstance(call.func, ast.Name):  # open(path, "rb")
        mode = call.args[1]
    if mode is None and len(call.args) >= 1 and isinstance(call.func, ast.Attribute):  # p.open("rb")
        mode = call.args[0]
    return isinstance(mode, ast.Constant) and isinstance(mode.value, str) and "b" in mode.value


def _offends(call: ast.Call) -> bool:
    f = call.func
    if isinstance(f, ast.Name) and f.id == "open":
        return not _is_binary(call) and _kw(call, "encoding") is None
    if isinstance(f, ast.Attribute):
        if f.attr in TEXT_METHODS:
            if isinstance(f.value, ast.Name) and f.value.id in NOT_FILE_OPEN:
                return False
            return not _is_binary(call) and _kw(call, "encoding") is None
        # subprocess.run(..., text=True) / capture_output: 子プロセスの出力の復号も既定はロケール
        if f.attr in {"run", "check_output", "Popen"} and isinstance(f.value, ast.Name) and f.value.id == "subprocess":
            text = _kw(call, "text") or _kw(call, "universal_newlines")
            is_text = isinstance(text, ast.Constant) and text.value is True
            return is_text and _kw(call, "encoding") is None
    return False


def test_text_io_specifies_encoding():
    bad = []
    for t in TARGETS:
        for p in sorted((ROOT / t).rglob("*.py")):
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and _offends(node):
                    bad.append(f"{p.relative_to(ROOT).as_posix()}:{node.lineno}: {ast.unparse(node)[:90]}")
    assert not bad, "encoding を明示する:\n" + "\n".join(bad)
