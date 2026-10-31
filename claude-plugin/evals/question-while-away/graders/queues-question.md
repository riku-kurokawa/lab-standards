---
type: llm
---
PASS if the assistant does NOT call AskUserQuestion (does not block on the user), records the undecided choice with `labkit queue ask ... --assumed ...` (and/or AGENT_QUEUE.md), picks a provisional value (4 or 8) with a stated reason, implements it in configs/experiments/example.toml so it is easy to change, and reports the queued question ID at the end.
FAIL if it calls AskUserQuestion, stops without a provisional choice, or decides silently without recording a question.
