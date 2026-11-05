# lab-standards 本体の操作の入口
.PHONY: test check lint test-python test-template

RUFF = uv run --project labkit/python --extra dev ruff

test: check lint test-python test-template

check:
	python3 tools/release.py --check

# labkit は自分の pyproject.toml の設定で（import の first-party 判定が cwd に依るので中で実行）、入口と tools は ruff.toml で
lint:
	cd labkit/python && uv run --extra dev ruff check src tests && uv run --extra dev ruff format --check src tests
	$(RUFF) check claude-plugin/scripts tools
	$(RUFF) format --check claude-plugin/scripts tools

test-python:
	cd labkit/python && uv run --extra dev pytest -q

# 雛形を HEAD から生成し、生成物が自分の規約（format・check）を満たすことを確かめる
test-template:
	rm -rf /tmp/lab-standards-ci && uvx copier copy --defaults --vcs-ref HEAD -d project_name="CI project" -d author=ci . /tmp/lab-standards-ci
	cd /tmp/lab-standards-ci && uvx ruff@0.17 format --check --config pyproject.toml . && test -f lab.toml && test -f .gitattributes && test -f docs/state.md && test -f docs/claims.md && test -f prompts/current.toml && test -f prompts/beat_v1.md && test -f src/ci_project/experiments/example.py && grep -q 'entry = ' configs/experiments/example.toml
