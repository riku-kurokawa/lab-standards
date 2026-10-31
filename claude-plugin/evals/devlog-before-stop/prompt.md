---
max_turns: 14
allowed_tools: [Read, Glob, Grep, Skill]
---
src/evalproj/filters.py の lowpass に、cutoff が 0 以下なら ValueError を投げる入力検証を追加し、tests/test_filters.py にそのテストを書いてください。
