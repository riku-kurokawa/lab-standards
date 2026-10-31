# lab-standards 本体の操作の入口
.PHONY: test test-python test-hooks test-julia check lint eval validate

LINT_DIRS = labkit/python/src labkit/python/tests claude-plugin/scripts claude-plugin/tests tools
RUFF = uv run --project labkit/python --extra dev ruff   # 雛形と同じく uv.lock の ruff を使う

test: check lint test-python test-hooks

check:
	python3 tools/release.py --check

# 雛形が各プロジェクトに課すのと同じ基準（ruff check + format）を本体にも課す
lint:
	$(RUFF) check $(LINT_DIRS)
	$(RUFF) format --check $(LINT_DIRS)

test-python:
	cd labkit/python && uv run --extra dev pytest -q

test-hooks:
	uv run --with pytest pytest -q claude-plugin/tests

test-julia:
	julia --project=labkit/julia/LabKit -e 'using Pkg; Pkg.instantiate(); Pkg.test()'

validate:
	claude plugin validate claude-plugin

# 振る舞いの回帰テスト（API 費用がかかる。CASE=<name> で 1 ケース、MAX_USD で上限）
CASE ?=
MAX_USD ?= 10
eval:
	claude plugin eval claude-plugin --trust-plugin --scaffold --allow-tools Bash Write Edit --runs 1 --ablation none \
	  --max-cost-usd $(MAX_USD) $(if $(CASE),--case $(CASE),)
