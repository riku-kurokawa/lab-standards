# scripts/

実験の入口は `configs/experiments/*.toml` の `entry` と `labkit run`（共通の入口。一度レビューした部品を使い回す）。
ここに置くのは、entry では書けないもの（外部プロセスの起動、HPC 用の前処理など）だけ。
書くときは冒頭の docstring に「entry で書けない理由」を 1 行入れる。計算の本体は `src/` の関数にし、ここでは呼ぶだけ。
`labkit check` L018 が 300 行（空行を除く）を超えるファイルを警告する。
