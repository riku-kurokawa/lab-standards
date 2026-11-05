"""文献管理: 書誌の取得・読んだ記録・正直さの検査・読書キュー・INDEX."""

import datetime as dt
import urllib.error

import pytest

from labkit import literature as lit
from labkit.config import load_lab
from labkit.literature import (
    add_entry,
    build_index,
    check_literature,
    fetch_bibtex,
    format_queue,
    format_surveys,
    list_surveys,
    mark_read,
    parse_bib,
    read_frontmatter,
    reading_queue,
)

BIB = """@article{whatever,
  author = {M{\\"u}ller, Anna and Tanaka, Taro},
  title = {A {Fast} Method for Denoising},
  journal = {J. Signal Proc.},
  year = {2023},
  doi = {10.1000/xyz123}
}"""
ARXIV_BIB = """@misc{sato2026sparse,
      title={Sparse Solvers},
      author={Sato, Ken},
      year={2026},
      eprint={2606.09554},
      archivePrefix={arXiv},
      primaryClass={math.NA},
      url={https://arxiv.org/abs/2606.09554},
}"""


def fake_http(table: dict):
    calls = []

    def _get(url, accept=None):
        calls.append((url, accept))
        if url not in table:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return table[url]

    _get.calls = calls
    return _get


def set_fm(note, **kv):
    """frontmatter のキーを書き換える（テスト用。コメントは気にしない）."""
    text = note.read_text(encoding="utf-8")
    end = text.find("\n---", 3)
    lines = text[3:end].split("\n")
    for k, v in kv.items():
        lines = [ln for ln in lines if not ln.startswith(f"{k}:")] + [f"{k}: {v}"]
    note.write_text(text[:3] + "\n".join(lines) + text[end:], encoding="utf-8", newline="\n")


def survey(project, name, **fm):
    head = "\n".join(f"{k}: {v}" for k, v in {"date": name[:10], "question": '"q"', "search": "{}", **fm}.items())
    s = project / "literature" / "surveys" / f"{name}.md"
    s.write_text(f"---\n{head}\n---\n本文\n", encoding="utf-8", newline="\n")
    return s


def l04(project, lab, code):
    return [i for i in check_literature(project, lab) if i[0] == code]


# ---------- fetch_bibtex ----------
def test_fetch_bibtex_doi(project, monkeypatch):
    get = fake_http({"https://doi.org/10.1000/xyz123": BIB})
    monkeypatch.setattr(lit, "_http_get", get)
    text = fetch_bibtex(doi="https://doi.org/10.1000/XYZ123")
    assert get.calls == [("https://doi.org/10.1000/xyz123", "application/x-bibtex")]
    ((key, fields),) = parse_bib(text).items()
    assert key == "whatever" and fields["source"] == f"doi:10.1000/xyz123 {dt.date.today().isoformat()}"
    assert text.rstrip().endswith("}") and "source" in text.splitlines()[-2]  # source は最後のフィールド
    citekey, note = add_entry(project, load_lab(project), text)
    assert citekey == "muller2023fast" and note.exists()


def test_fetch_bibtex_arxiv(monkeypatch):
    get = fake_http({"https://arxiv.org/bibtex/2606.09554": ARXIV_BIB})
    monkeypatch.setattr(lit, "_http_get", get)
    for aid in (
        "2606.09554",
        "arXiv:2606.09554v2",
        "https://arxiv.org/abs/2606.09554v1",
        "https://arxiv.org/pdf/2606.09554.pdf",
    ):
        fields = next(iter(parse_bib(fetch_bibtex(arxiv=aid)).values()))
        assert fields["source"].startswith("arxiv:2606.09554 ") and fields["eprint"] == "2606.09554"
    assert all(a is None for _, a in get.calls)


def test_fetch_bibtex_failures(monkeypatch):
    monkeypatch.setattr(lit, "_http_get", fake_http({"https://doi.org/10.1/html": "<html>not bibtex</html>"}))
    with pytest.raises(ValueError, match=r"DOI 10\.1/none を解決できません（HTTP Error 404"):
        fetch_bibtex(doi="10.1/none")
    with pytest.raises(ValueError, match="BibTeX でない応答"):
        fetch_bibtex(doi="10.1/html")
    with pytest.raises(ValueError, match="arXiv 9999.00000 を解決できません"):
        fetch_bibtex(arxiv="9999.00000")
    with pytest.raises(ValueError):
        fetch_bibtex()
    with pytest.raises(ValueError):
        fetch_bibtex(doi="10.1/x", arxiv="1")


# ---------- mark_read ----------
def test_mark_read(project):
    lab = load_lab(project)
    key, note = add_entry(project, lab, BIB, tags=["denoising"])
    before = note.read_text(encoding="utf-8")
    assert "read_by: agent        # agent | human | both" in before
    mark_read(project, lab, key, by="agent", scope="sections")
    fm = read_frontmatter(note)[0]
    assert (fm["read_by"], fm["read_scope"], fm["status"]) == ("agent", "sections", "unread")
    mark_read(project, lab, key, by="human", status="read")
    after = note.read_text(encoding="utf-8")
    fm = read_frontmatter(note)[0]
    assert (fm["read_by"], fm["read_scope"], fm["status"]) == ("both", "sections", "read")
    assert "read_by: both        # agent | human | both（誰が読んだか）" in after  # コメントと桁は保持
    assert "status: read        # unread | skimmed | read | key" in after
    assert after.count("\n---") == 1 and after.split("\n---")[1] == before.split("\n---")[1]  # 本文は不変
    assert [ln.split(":")[0] for ln in after.split("\n---")[0].splitlines()[1:]] == [
        ln.split(":")[0] for ln in before.split("\n---")[0].splitlines()[1:]
    ]  # キーの順序・数も不変
    # 古いノート（キー無し）: human が読めば both（agent が書いたものとみなす）、キーは末尾に追加
    old = project / "literature" / "notes" / "old2020x.md"
    old.write_text("---\ncitekey: old2020x\nstatus: read\n---\n本文\n", encoding="utf-8", newline="\n")
    mark_read(project, lab, "old2020x", by="human", scope="full")
    assert (
        old.read_text(encoding="utf-8")
        == "---\ncitekey: old2020x\nstatus: read\nread_by: both\nread_scope: full\n---\n本文\n"
    )
    for kw in ({"by": "robot"}, {"by": "human", "scope": "all"}, {"by": "human", "status": "done"}):
        with pytest.raises(ValueError):
            mark_read(project, lab, key, **kw)
    with pytest.raises(ValueError, match="がありません"):
        mark_read(project, lab, "nobody2000x", by="human")


# ---------- L041 / L047 ----------
def test_check_note_honesty(project):
    lab = load_lab(project)
    key, note = add_entry(project, lab, BIB, tags=["denoising"])
    assert l04(project, lab, "L047") == []  # unread は対象外
    set_fm(note, status="read")  # read_scope: abstract, claims: [] のまま
    issues = l04(project, lab, "L047")
    assert len(issues) == 2 and all(len(i) == 4 and i[3] == "warn" for i in issues)
    assert issues[0][2].startswith("status=read だが claims が空") and "read_scope=abstract" in issues[1][2]
    strict = {**lab, "literature": {**lab["literature"], "note_body": "error"}}
    assert all(len(i) == 3 for i in l04(project, strict, "L047"))
    set_fm(note, claims='["収束は O(1/k)（Thm 2）"]', read_scope="sections")
    assert l04(project, lab, "L047") == []
    set_fm(note, status="key", read_scope="none")
    assert [i[2] for i in l04(project, lab, "L047")] == [
        "status=key だが read_scope=none（本文を読んで sections/full にするか、status を skimmed に戻す）"
    ]
    # 古いノート（claims・read_scope のキーが無い）は違反にしない
    note.write_text(f"---\ncitekey: {key}\nstatus: read\n---\n", encoding="utf-8", newline="\n")
    assert l04(project, lab, "L047") == []
    # L041: read_by / read_scope の値
    set_fm(note, read_by="alien", read_scope="everything")
    msgs = [i[2] for i in l04(project, lab, "L041")]
    assert any("read_by は" in m for m in msgs) and any("read_scope は" in m for m in msgs)
    assert all(len(i) == 3 for i in l04(project, lab, "L041"))


# ---------- L048 ----------
def test_check_survey_verdict(project):
    lab = load_lab(project)
    s = survey(project, "2026-11-01_draft", status="draft")
    assert l04(project, lab, "L048") == []
    survey(project, "2026-11-02_old", status="done")  # 古い雛形（verdict / n_opened のキーが無い）は対象外
    assert l04(project, lab, "L048") == []
    s = survey(project, "2026-11-02_done", status="done", verdict='""', n_opened=0)
    issues = l04(project, lab, "L048")
    assert [(i[0], i[1], i[3]) for i in issues] == [("L048", s, "warn")] * 2
    assert "verdict が" in issues[0][2] and "n_opened が 0" in issues[1][2]
    survey(project, "2026-11-02_done", status="done", verdict="partly", n_opened=3)
    assert l04(project, lab, "L048") == []
    survey(project, "2026-11-02_done", status="done", verdict="maybe", n_opened=3)
    strict = {**lab, "literature": {**lab["literature"], "survey_verdict": "error"}}
    assert [len(i) for i in l04(project, strict, "L048")] == [3]
    items = list_surveys(project, lab)
    assert [(i["date"], i["slug"], i["status"], i["verdict"], i["n_opened"]) for i in items] == [
        ("2026-11-02", "old", "done", "", 0),
        ("2026-11-02", "done", "done", "maybe", 3),
        ("2026-11-01", "draft", "draft", "", 0),
    ]
    assert format_surveys(items).splitlines()[1] == "2026-11-02  done  (done/maybe/opened=3)  q"


# ---------- queue / index ----------
def add(project, lab, key, year, **fm):
    bib = f"@article{{x,\n  author = {{{key[:-5].title()}, A}},\n  title = {{T {key}}},\n  year = {{{year}}}\n}}"
    _, note = add_entry(project, lab, bib, key=key)
    set_fm(note, **fm)
    return note


def test_reading_queue_and_index(project):
    lab = load_lab(project)
    add(project, lab, "aaa2021x", 2021, relevance=5, status="key", claims='["A が成り立つ"]')
    add(project, lab, "bbb2022x", 2022, relevance=3, status="read", read_by="human")
    add(project, lab, "ccc2020x", 2020, relevance=4, status="skimmed")
    add(project, lab, "ddd2023x", 2023, relevance=4, status="read", read_by="both", claims='["D"]')
    add(project, lab, "eee2019x", 2019, relevance=1, status="unread")
    old = project / "literature" / "notes" / "fff2018x.md"
    old.write_text(
        "---\ncitekey: fff2018x\nstatus: read\nrelevance: 2\ntitle: F\n---\n", encoding="utf-8", newline="\n"
    )
    q = reading_queue(project, lab)
    assert [(r["citekey"], r["read_by"]) for r in q] == [
        ("aaa2021x", "agent"),
        ("ccc2020x", "agent"),
        ("fff2018x", "agent"),
        ("eee2019x", "agent"),
    ]
    assert [r["citekey"] for r in reading_queue(project, lab, min_relevance=4)] == ["aaa2021x", "ccc2020x"]
    assert format_queue(q).splitlines()[:2] == [
        "5  aaa2021x  (key/agent)  T aaa2021x — A が成り立つ",
        "4  ccc2020x  (skimmed/agent)  T ccc2020x",
    ]
    (project / "docs" / "x.md").write_text(
        "根拠 [@aaa2021x] と [@aaa2021x; @ccc2020x]\n", encoding="utf-8", newline="\n"
    )
    (project / "docs" / "decisions" / "0001-y.md").write_text("@ccc2020x\n", encoding="utf-8", newline="\n")
    (project / "literature" / "surveys" / "2026-11-03_s.md").write_text(
        '---\ndate: 2026-11-03\nquestion: "q"\nsearch: {}\nstatus: done\nverdict: known\nn_opened: 2\n---\n[@ccc2020x]\n',
        encoding="utf-8",
        newline="\n",
    )
    text = build_index(project, lab).read_text(encoding="utf-8")
    head = text.split("## 人間の読書キュー")[0]
    assert head.splitlines()[4:] == [
        "## 要点（relevance ≥ 4 か key、3 件）",
        "",
        "- aaa2021x — A が成り立つ（agent）",
        "- ddd2023x — D（both）",
        "- ccc2020x — （要点未記入）（agent）",
        "",
    ]
    assert "\n4 件（人間がまだ読んでいないノート）。`labkit lit queue` で一覧。\n" in text
    assert "| citekey | 年 | タイトル | タグ | 状態 | 読んだ | 重要度 | PDF | 使用 |" in text
    assert "| [aaa2021x](notes/aaa2021x.md) | 2021 | T aaa2021x |  | key | agent | 5 |  | x |" in text
    assert (
        "| [ccc2020x](notes/ccc2020x.md) | 2020 | T ccc2020x |  | skimmed | agent | 4 |  | 0001-y, x, 2026-11-03_s |"
        in text
    )
    assert "| [bbb2022x](notes/bbb2022x.md) | 2022 | T bbb2022x |  | read | human | 3 |  |  |" in text
    assert "| [2026-11-03_s](surveys/2026-11-03_s.md) | q | done | known | 2 |" in text
