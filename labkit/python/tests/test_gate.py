"""Bash コマンドの分類（承認ゲートの対象・禁止・レビュアーの許可リスト）."""

import pytest

from labkit.gate import classify, reviewer_allowed

P = ["main", "master"]


def cats(cmd, branch="feat/x"):
    return [h.category for h in classify(cmd, P, branch)]


@pytest.mark.parametrize(
    "cmd, branch, expect",
    [
        ("git push", "feat/x", []),
        ("git push origin feat/x", "main", []),
        ("git push -u origin feat/lab-standards", "main", []),
        ("git push", "main", ["git_push"]),
        ("git push", None, ["git_push"]),
        ("git push origin main", "feat/x", ["git_push"]),
        ("git push origin HEAD:main", "feat/x", ["git_push"]),
        ("git push origin feat/x --force", "feat/x", ["git_push"]),
        ("git push --force-with-lease", "feat/x", ["git_push"]),
        ("git push origin :feat/old", "feat/x", ["git_push"]),
        ("git push origin --delete feat/old", "feat/x", ["git_push"]),
        ("git push --tags", "feat/x", ["git_push"]),
        ("command git -c x=y push origin main", "feat/x", ["git_push"]),
        ("cd sub && git push origin main", "feat/x", ["git_push"]),
        ("git tag", "feat/x", []),
        ("git tag -l 'v*'", "feat/x", []),
        ("git tag v1.0.0", "feat/x", ["git_tag"]),
        ("git tag -d v1.0.0", "feat/x", ["git_tag"]),
        ("git merge --ff-only feat/x", "main", ["git_merge"]),
        ("git merge main", "feat/x", []),
        ("gh pr merge 12", "feat/x", ["gh_merge"]),
        ("gh release create v1.0.0", "feat/x", ["gh_release"]),
        ("gh release list", "feat/x", []),
        ("uv run labkit raw freeze", "feat/x", ["raw_freeze"]),
        ("python -m labkit.cli raw freeze", "feat/x", ["raw_freeze"]),
        ("uv run labkit raw verify", "feat/x", []),
        ("uv run labkit approve Q001", "feat/x", ["forbidden"]),
        ("labkit delegate release --hours 2", "feat/x", ["forbidden"]),
        ("labkit delegate list", "feat/x", []),
        ("uv run --extra dev labkit answer Q002 'x'", "feat/x", ["forbidden"]),
        ("copier update", "feat/x", []),
        ("uv run python scripts/run_x.py configs/x.toml", "feat/x", []),
    ],
)
def test_classify(cmd, branch, expect):
    assert cats(cmd, branch) == expect


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
