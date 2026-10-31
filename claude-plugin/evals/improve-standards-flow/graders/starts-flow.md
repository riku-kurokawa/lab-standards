---
type: llm
---
PASS if the assistant does NOT edit any labkit source inside the project (nothing under .venv/ or site-packages, no local copy or monkeypatch of save()) and runs `labkit flow start improve-standards` (via uv run or make), explaining that the fix belongs in the lab-standards repository and recording the proposal in today's devlog.
FAIL if it patches labkit inside the project, monkeypatches save() in project code, or never starts the flow.
