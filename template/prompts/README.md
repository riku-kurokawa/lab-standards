# prompts/

LLM に渡すプロンプトを置く。

- 1 プロンプト 1 ファイル: `<用途>_v<N>.md`（例: `goal_v3.md`、`beat_v2.md`）。改訂したら上書きせず `v<N+1>` を作る（過去の run・拍が使った版を残す）。
- 現行の版は `current.toml`（goal / beat / interval）に書く。`labkit beat start` と SessionStart がここを読むので、/goal・/loop の本文に貼らなくてよい。
  古い版を指したままだと `labkit check` L005 が知らせる。
- 雛形: `goal_v1.md`（究極目標・前提・合格基準・メタ認知の問い）、`beat_v1.md`（1 拍の 5 手。`/loop 20m /lab-rules:beat`）。
