# 比較は 1 軸だけを変える（ceteris paribus）

手法・設計・設定を比べる run を書くときに読む。条件のそろっていない比較が「同条件」と文章で書かれたまま主張の根拠になった実例があり
（accelerated-diff-pat で 10 件の主張を撤回）、比較の公平性は文章ではなく凍結した設定から機械が確かめる。合わなければ run は始まらないか failed になり、理由が出る。

- 腕（手法・設計・設定）の比較が成り立つのは、**宣言した 1 軸（`vary`）以外の条件がすべての腕で同一**で、それを**機械が凍結した設定から確かめた**ときだけ。文章や手書きの dict で「同条件」と書いても根拠にならない。
- 比較は run の前に設定へ書く: `[compare.<名>]` に `vary = "<軸 1 つ>"`・`keys = ["<この比較の指標>"]`、`[compare.<名>.common]` に全腕で同一の条件、
  `[compare.<名>.arms.<腕>]` に軸の値だけ（1 語で、腕の名前か `levels = [...]` の値。`"ours+lr0.1"` のように束ねない）。腕の条件は common ∪ 腕の表から導出され
  （entry は `labkit.compare.arm_conditions(cfg, "<名>")` で読む）、腕の表に軸以外の鍵があれば run は始まらない。`[compare]` の外（common の中も）に腕を名指す語（腕の名前・軸の値・levels）を含む鍵
  （`[solver.ours]`・`flat_steps`）があっても始まらない。`lab.toml` の `[compare] required`（人間が分野の条件を列挙する）が common に無い・空・`n/a`・`未定` などでも始まらない。
- 比較対象の自由パラメータ（平板の高さなど）は `[[compare.<名>.sweep]]`（arm・param・values・metric・direction）で掃引を宣言し、値ごとのスコアを `log_metric` する。
  metric は比較の指標を含む名前（`"gain_db_flat_h{value}"`）、direction は比較の `better = "max" | "min"` と同じ。1 腕でも調整するなら、対象外でない全腕を同じ総試行数で調整する。
  最良は run の記録から決まり（`labkit.compare.chosen(run, "<名>")`）、腕の値が最良でなければ run は failed。
- 目的を受け取れない腕が「対象外」（負けではない）になるのは `objective` と capability の宣言だけ。人間が `lab.toml` の `[compare.capability]`（手法 = 受け取れる目的）に
  登録したものが独立した宣言。設定の `[compare.<名>.capability]` は著者の宣言として comparisons.json と check（L027 の警告）に出て、`lab.toml` と食い違えば拒否する。
- 設定は開始時に凍結される（`meta.config_sha256`）。entry が `run.config` や config.json を途中で書き換えると run は failed。比較の run は `labkit runs mark ... finished` にできない。
- 比較の記録 `comparisons.json` は Run の終了時に 1 回だけ書かれ、meta の outputs に hash が載る。L027 は凍結した config.json・metrics.json から計算し直す（記録の matched は信用しない）。
- **主張の根拠は既定で拒否**: 指標は matched な比較の `keys` か、設定の `[report] noncomparative`（比較ではない指標。ワイルドカードの前に 2 文字以上の固定の接頭辞。
  腕の名前・軸の値・levels・比較の指標の語幹・vs/minus/over などの比べる語を含まない）に run の前に書いたものだけ。台帳の本文・備考の引用も同じ基準で照合する。
  根拠が複数の run にまたがるなら `labkit claim add ... --axis <設定の鍵>`（`_git_commit` などの内部の鍵は不可）。軸以外の凍結した設定（`[compare.<名>]` の common・arms を含む）と
  commit が同一でなければ拒否する。主張は既定で比較（2 つ以上の値を引くなら 1 つの run の値は 1 つの matched な比較の keys だけ。非比較は 1 つまで）。他の文書でも、同じ指標（腕を名指す語を除いて同じ指標も）を 2 つ以上の run から引くなら、段落・表を分けても文書のどこかに `axis=<鍵>`（値は 1 語）を書き、軸以外が同一でなければ L027（開発ログだけ警告、他は error）。
- 条件のそろっていなかった run は `labkit runs archive <id> ... --reason "条件不一致: ..."` で退避し（削除しない。取り消しも理由つきで履歴に残る）、その数値の引用は L032 の error。

