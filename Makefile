# lab-standards 本体の操作の入口
.PHONY: test check lint test-python test-template

LINT_DIRS = labkit/python/src labkit/python/tests claude-plugin/scripts tools
RUFF = uv run --project labkit/python --extra dev ruff

test: check lint test-python test-template

check:
	python3 tools/release.py --check

lint:
	$(RUFF) check $(LINT_DIRS)
	$(RUFF) format --check $(LINT_DIRS)

test-python:
	cd labkit/python && uv run --extra dev pytest -q

# 雛形を HEAD から生成し、生成物が自分の規約（format・check）を満たすことを確かめる
test-template:
	rm -rf /tmp/lab-standards-ci && uvx copier copy --defaults --vcs-ref HEAD -d project_name="CI project" -d author=ci . /tmp/lab-standards-ci
	cd /tmp/lab-standards-ci && uvx ruff@0.17 format --check --config pyproject.toml . && test -f lab.toml && test -f .gitattributes
