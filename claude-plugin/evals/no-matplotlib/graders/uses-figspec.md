---
type: llm
---
PASS if the assistant does NOT create or run code that imports matplotlib/seaborn/plotly (no `import matplotlib` written to any file), and instead uses a figspec (figspecs/*.toml) with `labkit fig ... --run <run_id>`, or explains that figures are made only through labkit fig templates and proposes a figspec.
FAIL if any written file contains `import matplotlib` or `from matplotlib`, or the assistant runs a matplotlib script.
