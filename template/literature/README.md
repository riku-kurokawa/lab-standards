# literature/

| パス | 中身 | git |
|---|---|---|
| `references.bib` | 唯一の書誌データベース | ✓ |
| `tags.toml` | タグの統制語彙（ここに無いタグは使えない） | ✓ |
| `notes/<citekey>.md` | 論文ごとの読書ノート | ✓ |
| `surveys/YYYY-MM-DD_<slug>.md` | サーベイ報告（本文で `[@citekey]` 引用） | ✓ |
| `INDEX.md` | 一覧（`labkit lit index` で自動生成） | ✓ |
| `pdfs/<citekey>.pdf` | PDF 本体 | × |
| `inbox/` | 未整理のダウンロード置き場 | × |

## citekey 規約

`第一著者の姓（小文字・ASCII）` + `年` + `タイトル最初の実語（冠詞・前置詞を除く）`
例: Müller, "A Fast Method for Denoising", 2023 → `muller2023fast`

## 操作

```bash
labkit lit add --file entry.bib --tags denoising eeg --pdf literature/inbox/xxx.pdf
labkit lit survey --question "EEG のアーチファクト除去手法の比較" --slug eeg-artifact-removal
labkit lit index
```
