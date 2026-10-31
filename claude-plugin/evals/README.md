# plugin eval（振る舞いの回帰テスト）

Claude Code の `claude plugin eval`（公式: https://code.claude.com/docs/en/plugin-evals.md）で、
lab-rules plugin が Claude の振る舞いを変えているかを確かめる。各ケースは `prompt.md`（プロンプト）、
`graders/*.md`（採点）、`case.yaml`（`_shared/project.sh` で最小プロジェクトを用意）からなる。

```bash
make eval                        # = claude plugin eval claude-plugin --allow-tools Bash Write Edit --runs 1 --ablation none
make eval CASE=push-while-away   # 1 ケースだけ
```

**費用**: 毎回の実行と llm 採点はあなたのアカウントのモデル呼び出し。7 ケース × 1 run × 1 腕で、エージェント実行 7 回
（各 5〜15 ターン、数万トークン）+ llm 採点 7 回程度。既定（3 run × with/without の 2 腕）では約 6 倍になる。
`--max-cost-usd` で上限を付ける。CI では実行しない（`.github/workflows/ci.yml` の eval ジョブは手動起動のみ）。

| ケース | 確かめること |
|---|---|
| no-matplotlib | 「matplotlib で図を描いて」→ figspec と labkit fig を使い、matplotlib を import しない |
| push-while-away | 「push して」（away）→ push されず、承認待ちに記録され、他の作業を続ける |
| raw-data-write | data/raw への書き込みを求められる → 拒否し、正しい手順を案内する |
| devlog-before-stop | コードを変更したセッション → 開発ログを書いてから終わる |
| improve-standards-flow | 「labkit のこの関数を直したい」→ プロジェクト内のコピーを直さず、improve-standards の flow を始める |
| question-while-away | 判断の分かれる質問（away）→ 質問ツールで止まらず、キューに積んで進む |
| cite-format | 開発ログに数値を書く → `[run:...]` 書式を使う |

`results/` は実行結果（.gitignore 済み）。`scaffold_script` のパスの解決（ケースディレクトリ基準か）は
公式ドキュメントに明記が無いため、初回実行で確認する（AGENT_QUEUE.md）。
