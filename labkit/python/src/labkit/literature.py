"""文献・サーベイ管理.

literature/
    references.bib          唯一の書誌データベース（citekey = 第一著者姓 + 年 + タイトル最初の実語）
    tags.toml               タグの統制語彙（ここに無いタグは使えない）
    notes/<citekey>.md      論文ごとの読書ノート（YAML frontmatter 付き）
    surveys/YYYY-MM-DD_<slug>.md   サーベイ報告（本文で [@citekey] 引用）
    pdfs/<citekey>.pdf      PDF 本体（git 管理外）
    inbox/                  未整理のダウンロード置き場（git 管理外）
    INDEX.md                自動生成の一覧（labkit lit index）
"""

from __future__ import annotations

import datetime as _dt
import re
from importlib import resources
from pathlib import Path

from labkit._util import write_text_atomic
from labkit.config import read_toml

STOPWORDS = {"a", "an", "the", "on", "of", "for", "in", "to", "and", "with", "towards", "toward", "via"}
CITE_RE = re.compile(r"\[@([^\]\s;,]+)|;\s*@([^\]\s;,]+)|(?<![\w@])@([A-Za-z][\w:-]*\d{4}[\w-]*)")
KEY_RE = re.compile(r"^[a-z][a-z0-9-]*\d{4}[a-z0-9-]*$")
STATUS = {"unread", "skimmed", "read", "key"}


# ---------- BibTeX ----------
def parse_bib(text: str) -> dict[str, dict]:
    """最小限の BibTeX パーサ。{citekey: {"type":..., field: value}}."""
    entries: dict[str, dict] = {}
    i = 0
    while (m := re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", re.S).search(text, i)) is not None:
        etype, key = m.group(1).lower(), m.group(2)
        j, depth = m.end(), 1
        while j < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[j], 0)
            j += 1
        body = text[m.end() : j - 1]
        entries[key] = {"type": etype, **_parse_fields(body)}
        i = j
    return entries


def _parse_fields(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    i = 0
    n = len(body)
    while i < n:
        m = re.compile(r"\s*([A-Za-z_-]+)\s*=\s*", re.S).match(body, i)
        if not m:
            break
        name = m.group(1).lower()
        j = m.end()
        if j < n and body[j] == "{":
            depth, k = 1, j + 1
            while k < n and depth:
                depth += {"{": 1, "}": -1}.get(body[k], 0)
                k += 1
            val = body[j + 1 : k - 1]
        elif j < n and body[j] == '"':
            k = body.index('"', j + 1) + 1
            val = body[j + 1 : k - 1]
        else:
            k = j
            while k < n and body[k] not in ",\n":
                k += 1
            val = body[j:k].strip()
        out[name] = re.sub(r"\s+", " ", val).strip()
        i = body.find(",", k)
        i = n if i < 0 else i + 1
    return out


def make_citekey(fields: dict) -> str:
    author = fields.get("author", "anon").split(" and ")[0]
    last = author.split(",")[0] if "," in author else author.split()[-1] if author.split() else "anon"
    last = re.sub(r"[^a-z]", "", _ascii(last).lower()) or "anon"
    year = re.sub(r"\D", "", fields.get("year", ""))[:4] or "0000"
    words = [
        w.replace("-", "")
        for w in re.findall(r"[A-Za-z]+(?:-[A-Za-z]+)*", _ascii(fields.get("title", "")))
        if w.lower() not in STOPWORDS
    ]
    first = words[0].lower() if words else "untitled"
    return f"{last}{year}{first}"


def _ascii(s: str) -> str:
    import unicodedata

    s = re.sub(r"\\[`'^\"~=.uvHtcdbk]\{?(\w)\}?", r"\1", s).replace("{", "").replace("}", "")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def format_entry(key: str, fields: dict) -> str:
    etype = fields.get("type", "article")
    order = [
        "author",
        "title",
        "journal",
        "booktitle",
        "year",
        "volume",
        "number",
        "pages",
        "publisher",
        "doi",
        "url",
        "eprint",
        "archiveprefix",
    ]
    keys = [k for k in order if k in fields] + sorted(k for k in fields if k not in order and k != "type")
    body = ",\n".join(f"  {k:<13} = {{{fields[k]}}}" for k in keys)
    return f"@{etype}{{{key},\n{body}\n}}\n"


def _norm_doi(doi: str) -> str:
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip().lower())


# ---------- 操作 ----------
def lit_dir(root: Path, lab: dict) -> Path:
    return root / lab["literature"]["dir"]


def load_tags(root: Path, lab: dict) -> set[str]:
    f = lit_dir(root, lab) / "tags.toml"
    if not f.is_file():
        return set()
    data = read_toml(f)
    tags: set[str] = set()
    for group in data.values():
        if isinstance(group, dict):
            tags.update(group.keys())
        elif isinstance(group, list):
            tags.update(group)
    return tags


def add_entry(
    root: Path,
    lab: dict,
    bibtex: str,
    *,
    tags: list[str] | None = None,
    pdf: Path | None = None,
    key: str | None = None,
) -> tuple[str, Path]:
    """BibTeX を references.bib に追記し、ノートの雛形を作る。重複（key/DOI）は拒否."""
    d = lit_dir(root, lab)
    bibf = d / "references.bib"
    existing = parse_bib(bibf.read_text(encoding="utf-8")) if bibf.exists() else {}
    new = parse_bib(bibtex)
    if len(new) != 1:
        raise ValueError(f"BibTeX エントリは 1 件だけ渡してください（{len(new)} 件）")
    ((_, fields),) = new.items()
    citekey = key or make_citekey(fields)
    if citekey in existing:
        raise ValueError(f"citekey {citekey} は既に references.bib にあります")
    doi = _norm_doi(fields.get("doi", ""))
    if doi:
        for k, f in existing.items():
            if _norm_doi(f.get("doi", "")) == doi:
                raise ValueError(f"同じ DOI が既に {k} として登録されています")
    vocab = load_tags(root, lab)
    bad = [t for t in tags or [] if vocab and t not in vocab]
    if bad:
        raise ValueError(f"tags.toml に無いタグ: {bad}。先に tags.toml へ追加するか既存タグを使う")
    with open(bibf, "a", encoding="utf-8") as f:
        f.write(("\n" if bibf.exists() and bibf.stat().st_size else "") + format_entry(citekey, fields))
    has_pdf = False
    if pdf is not None:
        dst = root / lab["literature"]["pdf_dir"] / f"{citekey}.pdf"
        dst.parent.mkdir(parents=True, exist_ok=True)
        Path(pdf).replace(dst)
        has_pdf = True
    note = d / "notes" / f"{citekey}.md"
    if not note.exists():
        tpl = resources.files("labkit.templates").joinpath("paper_note.md").read_text(encoding="utf-8")
        authors = [a.strip() for a in fields.get("author", "").split(" and ") if a.strip()]
        text = (
            tpl.replace("{{citekey}}", citekey)
            .replace("{{title}}", fields.get("title", "").replace('"', "'"))
            .replace("{{authors}}", ", ".join(f'"{a}"' for a in authors))
            .replace("{{year}}", re.sub(r"\D", "", fields.get("year", "0")) or "0")
            .replace("{{venue}}", fields.get("journal", fields.get("booktitle", "")).replace('"', "'"))
            .replace("{{doi}}", fields.get("doi", ""))
            .replace("{{url}}", fields.get("url", ""))
            .replace("{{tags}}", ", ".join(tags or []))
            .replace("{{pdf}}", "true" if has_pdf else "false")
            .replace("{{added}}", _dt.date.today().isoformat())
        )
        write_text_atomic(note, text)
    return citekey, note


def read_frontmatter(path: Path) -> tuple[dict | None, str]:
    import yaml

    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end < 0:
        return None, text
    try:
        fm = yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError:
        return None, text
    return fm, text[end + 4 :]


def build_index(root: Path, lab: dict) -> Path:
    d = lit_dir(root, lab)
    bib = parse_bib((d / "references.bib").read_text(encoding="utf-8")) if (d / "references.bib").exists() else {}
    rows = []
    for key, f in sorted(bib.items(), key=lambda kv: (kv[1].get("year", ""), kv[0]), reverse=True):
        note = d / "notes" / f"{key}.md"
        fm = read_frontmatter(note)[0] if note.exists() else None
        fm = fm or {}
        pdf = (root / lab["literature"]["pdf_dir"] / f"{key}.pdf").exists()
        tags = ", ".join(fm.get("tags", []) or [])
        title = f.get("title", "").replace("|", "/")
        rows.append(
            f"| [{key}](notes/{key}.md) | {f.get('year', '')} | {title} | {tags} | "
            f"{fm.get('status', '-')} | {fm.get('relevance', '-')} | {'✓' if pdf else ''} |"
        )
    surveys = sorted((d / "surveys").glob("*.md"), reverse=True) if (d / "surveys").is_dir() else []
    s_rows = []
    for s in surveys:
        if s.name.startswith("_"):
            continue
        fm = read_frontmatter(s)[0] or {}
        s_rows.append(f"| [{s.stem}](surveys/{s.name}) | {fm.get('question', '')} |")
    text = (
        "# 文献インデックス\n\n> `labkit lit index` で自動生成。手で編集しない。\n\n"
        f"## 文献（{len(rows)} 件）\n\n| citekey | 年 | タイトル | タグ | 状態 | 重要度 | PDF |\n"
        "|---|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n\n"
        f"## サーベイ（{len(s_rows)} 件）\n\n| ファイル | 問い |\n|---|---|\n" + "\n".join(s_rows) + "\n"
    )
    out = d / "INDEX.md"
    write_text_atomic(out, text)
    return out


def check_literature(root: Path, lab: dict) -> list[tuple[str, str, str]]:
    """(code, location, message) のリスト."""
    issues: list[tuple[str, str, str]] = []
    d = lit_dir(root, lab)
    if not d.is_dir():
        return issues
    rel = lambda p: str(p.relative_to(root))  # noqa: E731
    bibf = d / "references.bib"
    bib = parse_bib(bibf.read_text(encoding="utf-8")) if bibf.exists() else {}
    for k in bib:
        if not KEY_RE.match(k):
            issues.append(("L040", rel(bibf), f"citekey {k} が規約（小文字の姓+年+語）に合いません"))
    vocab = load_tags(root, lab)
    notes = d / "notes"
    if notes.is_dir():
        for n in sorted(notes.glob("*.md")):
            if n.name.startswith("_"):
                continue
            fm, _ = read_frontmatter(n)
            if fm is None:
                issues.append(("L041", rel(n), "YAML frontmatter がありません"))
                continue
            if n.stem not in bib:
                issues.append(("L042", rel(n), f"{n.stem} が references.bib にありません"))
            if fm.get("citekey") != n.stem:
                issues.append(("L041", rel(n), "frontmatter の citekey とファイル名が一致しません"))
            if fm.get("status") not in STATUS:
                issues.append(("L041", rel(n), f"status は {sorted(STATUS)} のいずれか"))
            for t in fm.get("tags", []) or []:
                if vocab and t not in vocab:
                    issues.append(("L043", rel(n), f"タグ {t!r} が tags.toml にありません"))
    pdfdir = root / lab["literature"]["pdf_dir"]
    if pdfdir.is_dir():
        for p in sorted(pdfdir.iterdir()):
            if p.name.startswith(".") or p.name == ".gitkeep":
                continue
            if p.suffix.lower() != ".pdf" or p.stem not in bib:
                issues.append(("L044", rel(p), "PDF は <references.bib の citekey>.pdf という名前にする"))
    surveys = d / "surveys"
    if surveys.is_dir():
        for s in sorted(surveys.glob("*.md")):
            if s.name.startswith("_"):
                continue
            if not re.match(r"^\d{4}-\d{2}-\d{2}_[a-z0-9-]+\.md$", s.name):
                issues.append(("L045", rel(s), "サーベイは YYYY-MM-DD_<slug>.md（slug は小文字英数とハイフン）"))
            fm, body = read_frontmatter(s)
            if fm is None:
                issues.append(("L045", rel(s), "YAML frontmatter がありません"))
                continue
            for req in ("date", "question", "search"):
                if req not in fm:
                    issues.append(("L045", rel(s), f"frontmatter に {req} がありません"))
            for m in CITE_RE.finditer(body):
                key = next(g for g in m.groups() if g)
                if KEY_RE.match(key) and key not in bib:
                    issues.append(("L046", rel(s), f"引用 @{key} が references.bib にありません"))
    return issues
