# prompts/

LLM に渡すプロンプトを管理する。

- 1 プロンプト 1 ファイル: `<用途>_v<N>.md`（例: `summarize-paper_v2.md`）
- 先頭に YAML frontmatter: `purpose`, `inputs`（変数名）, `output_format`, `created`, `changelog`
- 変数は `{{変数名}}` で埋め込む
- 改訂したら上書きせず版を上げる（結果の再現のため）
