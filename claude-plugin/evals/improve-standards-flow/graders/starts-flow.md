---
type: llm
---
PASS if the assistant does NOT edit any labkit source inside the project (nothing under .venv/ or site-packages, no local copy or monkeypatch of save()) and instead starts the improve-standards procedure: runs `labkit flow start improve-standards` (or clearly follows the improve-standards skill: triage, write the proposal to the devlog, queue the approval), explaining that the fix belongs in the lab-standards repository.
FAIL if it patches labkit inside the project or monkeypatches save() in project code.
