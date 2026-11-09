"""Bash コマンドの分類（レビュアーの許可リスト）。v2.0.0 で承認ゲートは廃止."""

import pytest

from labkit.gate import reviewer_allowed


@pytest.mark.parametrize(
    "cmd, ok",
    [
        ("git diff --stat", True),
        ("git log --oneline -5 | head", True),
        ("git branch -D x", False),
        ("cat src/a.py | grep x", True),
        ("echo x > docs/reviews/a.md", False),
        ("sed -i 's/a/b/' x.py", False),
        ("sed -n 1,5p x.py", True),
        ("uv run labkit check", True),
        ("uv run labkit runs list", True),
        ("uv run labkit raw freeze", False),
        ("uv run --extra dev pytest -q", True),
        ("uv run ruff check src", True),
        ("uv run python scripts/x.py", False),
        ("rm -rf runs", False),
    ],
)
def test_reviewer_allowed(cmd, ok):
    assert reviewer_allowed(cmd) is ok
