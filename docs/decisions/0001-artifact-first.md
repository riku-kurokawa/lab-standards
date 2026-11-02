# 0001: 統制を入力側から成果物側へ移す（v1.0.0）

- 状態: 採用
- 日付: 2026-11-02

## 背景

v0.3/v0.4 のハーネスは「Claude に何を打たせないか」（承認ゲート・段階による操作禁止・presence・テキスト照合）に投資した。
2 プロジェクトでの実運用 2 日分の監査（`docs/audit-2026-11-02.md`）で、統制層は摩擦点のほぼすべてで迂回され、
2 箇所では再現性を逆方向に押していた: HEAD 束縛の承認が「commit しない」運用と未コミットのコードによる dirty な run を生み、
running のまま残った run を違反扱いする L021 が `SKIP=labkit-check` の常態化を生んだ。統制コードの行数は研究の核を上回っていた。

## 決定

- 検証の対象を成果物（run の meta.json、サイドカー、開発ログの引用）に置き、Stop hook は `labkit check --claims` だけで止める。
- 承認は「種類＋ブランチ＋期限」の委任に統一し、HEAD にもコマンド全文にも結び付けない。feat ブランチへの push は自由。
- flow は完了条件のチェックリストだけにし、段階による操作禁止・presence・improve-standards flow・MLflow・plugin eval・Julia 版を削除する。
- run の来歴に環境（lockfile の hash、パッケージ版、GPU）・seed・dirty.patch・出力の hash・入力の生成元 run を加え、`labkit runs mark` と `labkit mirror` を足す。
- 開発ログは機械で埋まる欄を機械が埋め（`labkit devlog`）、人が書く欄が空なら違反にする。
- 図の import 禁止は維持し、テンプレートを拡充する（band・bar・数値 x の errorbar・panels）。
- hooks の判定を labkit に一本化し、plugin は標準ライブラリだけの入口にする。

## 理由と検討した代替案

- 入力側の統制を強化する（sandbox 必須、検出の網を広げる）: Windows では sandbox が無く、hooks は公式にも security boundary ではない。迂回のたびに記録が歪む構造は変わらない。不採用。
- ゲートを全廃して GitHub のブランチ保護と確認画面だけに頼る: 無人の auto モードで保護ブランチへの push と raw freeze が止まらない。最小ゲートを残した。
- 描画ライブラリの直接使用を許可しプロジェクト内テンプレートを登録する: 利用者の選択で見送り（来歴よりも図の一貫性を優先）。テンプレート拡充で対応。

## 影響

- v0.x のプロジェクトの `lab.toml`・figspec・meta.json はそのまま動く。`.lab/approvals` と `.lab/presence` は使われなくなる。
- 開発ログの必須見出しが 4 つになり、目的・判断と理由・未解決 が空だと L030。既存の 7 見出しのログは上位互換。
- `np.save` 系の保存が L016（警告）になる。`jobs/` も絶対パス検査の対象になる。
