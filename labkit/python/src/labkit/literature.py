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
READ_BY = {"agent", "human", "both"}
READ_SCOPE = {"none", "abstract", "sections", "full"}
VERDICT = {"novel", "known", "partly", "inconclusive"}
USED_IN_GLOBS = ("docs/**/*.md", "literature/surveys/*.md")  # INDEX の「使用」列: [@citekey] を探す文書


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
        "source",
    ]
    keys = [k for k in order if k in fields] + sorted(k for k in fields if k not in order and k != "type")
    body = ",\n".join(f"  {k:<13} = {{{fields[k]}}}" for k in keys)
    return f"@{etype}{{{key},\n{body}\n}}\n"


def _norm_doi(doi: str) -> str:
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip().lower())


def _norm_arxiv(aid: str) -> str:
    """'arXiv:2606.09554v2' や abs/pdf の URL を '2606.09554' に."""
    s = re.sub(r"^(https?://arxiv\.org/(abs|pdf)/|arxiv:)", "", aid.strip(), flags=re.I)
    return re.sub(r"v\d+$", "", s.removesuffix(".pdf"))


def _http_get(url: str, accept: str | None = None) -> str:
    """HTTP GET（テストでは monkeypatch で差し替える）。失敗は OSError 系をそのまま投げる."""
    import urllib.request

    headers = {"User-Agent": "labkit"} | ({"Accept": accept} if accept else {})
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def fetch_bibtex(doi: str | None = None, arxiv: str | None = None) -> str:
    """DOI か arXiv id から BibTeX を取得し、出所と取得日を source フィールドに付けて返す（記憶から書誌を作らない）."""
    if bool(doi) == bool(arxiv):
        raise ValueError("doi か arxiv のどちらか一方を指定する")
    if doi:
        ident = _norm_doi(doi)
        url, accept, label, src = f"https://doi.org/{ident}", "application/x-bibtex", f"DOI {ident}", f"doi:{ident}"
    else:
        ident = _norm_arxiv(arxiv or "")
        url, accept, label, src = f"https://arxiv.org/bibtex/{ident}", None, f"arXiv {ident}", f"arxiv:{ident}"
    try:
        text = _http_get(url, accept)
    except OSError as e:  # HTTPError・URLError・timeout
        raise ValueError(f"{label} を解決できません（{e}）") from None
    entries = parse_bib(text)
    if len(entries) != 1:
        raise ValueError(f"{label} を解決できません（BibTeX でない応答: {text.strip()[:60]!r}）")
    ((key, fields),) = entries.items()
    fields["source"] = f"{src} {_dt.date.today().isoformat()}"
    return format_entry(key, fields)


# ---------- 操作 ----------
def _pdf_dir(root: Path, lab: dict) -> Path:
    p = Path(lab["literature"]["pdf_dir"]).expanduser()
    return p if p.is_absolute() else root / p


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
    with open(bibf, "a", encoding="utf-8", newline="\n") as f:
        f.write(("\n" if bibf.exists() and bibf.stat().st_size else "") + format_entry(citekey, fields))
    has_pdf = False
    if pdf is not None:
        dst = _pdf_dir(root, lab) / f"{citekey}.pdf"
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


def mark_read(
    root: Path, lab: dict, citekey: str, *, by: str, scope: str | None = None, status: str | None = None
) -> Path:
    """notes/<citekey>.md の frontmatter の read_by（必要なら read_scope・status）だけを書き換える。

    他の行とコメントは保持し、キーが無ければ frontmatter の末尾に足す。agent が読んだ後に human（またはその逆）なら both.
    """
    if by not in ("agent", "human"):
        raise ValueError("by は agent か human")
    if scope is not None and scope not in READ_SCOPE:
        raise ValueError(f"scope は {sorted(READ_SCOPE)} のいずれか")
    if status is not None and status not in STATUS:
        raise ValueError(f"status は {sorted(STATUS)} のいずれか")
    note = lit_dir(root, lab) / "notes" / f"{citekey}.md"
    if not note.is_file():
        raise ValueError(f"ノート {citekey} がありません（labkit lit add で作る）")
    fm, _ = read_frontmatter(note)
    if fm is None:
        raise ValueError(f"{note.name} に YAML frontmatter がありません")
    prev = fm.get("read_by") or "agent"  # キーが無い古いノートは agent が書いたものとみなす
    updates = {"read_by": "both" if prev in READ_BY and prev != by else by}
    if scope:
        updates["read_scope"] = scope
    if status:
        updates["status"] = status
    text = note.read_text(encoding="utf-8")
    end = text.find("\n---", 3)
    lines = text[3:end].split("\n")  # lines[0] は開始 "---" の直後（空）
    for key, val in updates.items():
        pat = re.compile(rf"^({re.escape(key)}\s*:\s*)([^#]*?)(\s*#.*)?$")
        for i, line in enumerate(lines):
            if m := pat.match(line):
                lines[i] = f"{m.group(1)}{val}{m.group(3) or ''}"
                break
        else:
            lines.append(f"{key}: {val}")
    write_text_atomic(note, text[:3] + "\n".join(lines) + text[end:])
    return note


# ---------- 一覧 ----------
def _notes(root: Path, lab: dict) -> list[tuple[Path, dict]]:
    """notes/*.md の (path, frontmatter)。frontmatter が無いもの・_ で始まるものは飛ばす."""
    notes = lit_dir(root, lab) / "notes"
    out = []
    for n in sorted(notes.glob("*.md")) if notes.is_dir() else []:
        if n.name.startswith("_"):
            continue
        fm, _ = read_frontmatter(n)
        if fm is not None:
            out.append((n, fm))
    return out


def _int(v, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _first_claim(fm: dict) -> str:
    c = fm.get("claims")
    c = c[0] if isinstance(c, list) and c else c
    return str(c).strip() if isinstance(c, str) and c.strip() else ""


def _cell(v) -> str:
    return str(v if v is not None else "").replace("|", "/").replace("\n", " ")


def _note_row(n: Path, fm: dict) -> dict:
    return {
        "citekey": n.stem,
        "title": str(fm.get("title", "") or ""),
        "year": _int(fm.get("year")),
        "relevance": _int(fm.get("relevance")),
        "status": str(fm.get("status", "") or ""),
        "read_by": str(fm.get("read_by") or "agent"),
        "claim": _first_claim(fm),
    }


def reading_queue(root: Path, lab: dict, *, min_relevance: int = 1) -> list[dict]:
    """人間がまだ読んでいないノート（read_by が human/both でない）を relevance・year の降順で."""
    items = [_note_row(n, fm) for n, fm in _notes(root, lab)]
    items = [r for r in items if r["read_by"] not in ("human", "both") and r["relevance"] >= min_relevance]
    return sorted(items, key=lambda r: (-r["relevance"], -r["year"], r["citekey"]))


def format_queue(items: list[dict]) -> str:
    return "\n".join(
        f"{r['relevance']}  {r['citekey']}  ({r['status']}/{r['read_by']})  {r['title']}"
        + (f" — {r['claim']}" if r["claim"] else "")
        for r in items
    )


def list_surveys(root: Path, lab: dict) -> list[dict]:
    d = lit_dir(root, lab) / "surveys"
    out = []
    for s in sorted(d.glob("*.md"), reverse=True) if d.is_dir() else []:
        if s.name.startswith("_"):
            continue
        fm = read_frontmatter(s)[0] or {}
        date, _, slug = s.stem.partition("_")
        out.append(
            {
                "date": str(fm.get("date") or date),
                "slug": slug or s.stem,
                "question": str(fm.get("question", "") or ""),
                "status": str(fm.get("status", "") or ""),
                "verdict": str(fm.get("verdict") or ""),
                "n_opened": _int(fm.get("n_opened")),
            }
        )
    return out


def format_surveys(items: list[dict]) -> str:
    return "\n".join(
        f"{r['date']}  {r['slug']}  ({r['status'] or '-'}/{r['verdict'] or '-'}/opened={r['n_opened']})  {r['question']}"
        for r in items
    )


def _used_in(root: Path, lab: dict) -> dict[str, list[str]]:
    """[@citekey] が出現する文書（stem）を citekey ごとに。文書は 1 回ずつ読む."""
    used: dict[str, list[str]] = {}
    for g in USED_IN_GLOBS:
        for f in sorted(root.glob(g)):
            if not f.is_file() or f.name.startswith("_"):
                continue
            keys = {next(x for x in m.groups() if x) for m in CITE_RE.finditer(f.read_text(encoding="utf-8"))}
            for k in keys:
                if f.stem not in used.setdefault(k, []):
                    used[k].append(f.stem)
    return used


def build_index(root: Path, lab: dict) -> Path:
    d = lit_dir(root, lab)
    bib = parse_bib((d / "references.bib").read_text(encoding="utf-8")) if (d / "references.bib").exists() else {}
    fms = {n.stem: fm for n, fm in _notes(root, lab)}
    used = _used_in(root, lab)
    rows, points = [], []
    for key, f in sorted(bib.items(), key=lambda kv: (kv[1].get("year", ""), kv[0]), reverse=True):
        fm = fms.get(key, {})
        r = _note_row(d / "notes" / f"{key}.md", fm)
        pdf = (_pdf_dir(root, lab) / f"{key}.pdf").exists()
        tags = ", ".join(fm.get("tags", []) or [])
        u = used.get(key, [])
        rows.append(
            f"| [{key}](notes/{key}.md) | {f.get('year', '')} | {_cell(f.get('title', ''))} | {tags} | "
            f"{fm.get('status', '-')} | {fm.get('read_by', '-')} | {fm.get('relevance', '-')} | {'✓' if pdf else ''} | "
            f"{', '.join(u[:3])}{'…' if len(u) > 3 else ''} |"
        )
        if fm and (r["relevance"] >= 4 or r["status"] == "key"):
            points.append(r)
    points.sort(key=lambda r: (-r["relevance"], -r["year"], r["citekey"]))
    p_rows = [f"- {r['citekey']} — {_cell(r['claim']) or '（要点未記入）'}（{r['read_by']}）" for r in points[:30]]
    s_rows = [
        f"| [{s['date']}_{s['slug']}](surveys/{s['date']}_{s['slug']}.md) | {_cell(s['question'])} | "
        f"{s['status']} | {s['verdict']} | {s['n_opened']} |"
        for s in list_surveys(root, lab)
    ]
    n_queue = len(reading_queue(root, lab))
    text = (
        "# 文献インデックス\n\n> `labkit lit index` で自動生成。手で編集しない。\n\n"
        f"## 要点（relevance ≥ 4 か key、{len(p_rows)} 件）\n\n" + "\n".join(p_rows) + "\n\n"
        f"## 人間の読書キュー\n\n{n_queue} 件（人間がまだ読んでいないノート）。`labkit lit queue` で一覧。\n\n"
        f"## 文献（{len(rows)} 件）\n\n| citekey | 年 | タイトル | タグ | 状態 | 読んだ | 重要度 | PDF | 使用 |\n"
        "|---|---|---|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n\n"
        f"## サーベイ（{len(s_rows)} 件）\n\n| ファイル | 問い | 状態 | 判定 | 開いた件数 |\n|---|---|---|---|---|\n"
        + "\n".join(s_rows)
        + "\n"
    )
    out = d / "INDEX.md"
    write_text_atomic(out, text)
    return out


def _issue(code: str, where: Path, msg: str, severity: str) -> tuple:
    """severity が error なら従来の 3 要素、warn なら 4 要素目に severity を付ける."""
    return (code, where, msg) if severity == "error" else (code, where, msg, severity)


def check_literature(root: Path, lab: dict) -> list[tuple[str, Path, str] | tuple[str, Path, str, str]]:
    """(code, location, message[, severity]) のリスト。4 要素目が無ければ error."""
    issues: list = []  # 位置は絶対 Path のまま返す（Checker.add が / 区切りの相対に直す）
    d = lit_dir(root, lab)
    if not d.is_dir():
        return issues
    sev_body = lab["literature"].get("note_body", "warn")
    sev_verdict = lab["literature"].get("survey_verdict", "warn")
    bibf = d / "references.bib"
    bib = parse_bib(bibf.read_text(encoding="utf-8")) if bibf.exists() else {}
    for k in bib:
        if not KEY_RE.match(k):
            issues.append(("L040", bibf, f"citekey {k} が規約（小文字の姓+年+語）に合いません"))
    vocab = load_tags(root, lab)
    notes = d / "notes"
    if notes.is_dir():
        for n in sorted(notes.glob("*.md")):
            if n.name.startswith("_"):
                continue
            fm, _ = read_frontmatter(n)
            if fm is None:
                issues.append(("L041", n, "YAML frontmatter がありません"))
                continue
            if n.stem not in bib:
                issues.append(("L042", n, f"{n.stem} が references.bib にありません"))
            if fm.get("citekey") != n.stem:
                issues.append(("L041", n, "frontmatter の citekey とファイル名が一致しません"))
            if fm.get("status") not in STATUS:
                issues.append(("L041", n, f"status は {sorted(STATUS)} のいずれか"))
            if "read_by" in fm and fm["read_by"] not in READ_BY:
                issues.append(("L041", n, f"read_by は {sorted(READ_BY)} のいずれか"))
            if "read_scope" in fm and fm["read_scope"] not in READ_SCOPE:
                issues.append(("L041", n, f"read_scope は {sorted(READ_SCOPE)} のいずれか"))
            for t in fm.get("tags", []) or []:
                if vocab and t not in vocab:
                    issues.append(("L043", n, f"タグ {t!r} が tags.toml にありません"))
            st = fm.get("status")
            # 正直さ: 読んだと言うなら確立したことと読んだ範囲がある（claims・read_scope のキーが無い古いノートは対象外）
            if st in ("read", "key"):
                if "claims" in fm and not fm.get("claims"):
                    msg = f"status={st} だが claims が空（確立したことを 1〜3 行書く。読んでいなければ status を skimmed に戻す）"
                    issues.append(_issue("L047", n, msg, sev_body))
                if fm.get("read_scope") in ("none", "abstract"):
                    msg = f"status={st} だが read_scope={fm['read_scope']}（本文を読んで sections/full にするか、status を skimmed に戻す）"
                    issues.append(_issue("L047", n, msg, sev_body))
    pdfdir = _pdf_dir(root, lab)
    if pdfdir.is_dir() and pdfdir.is_relative_to(root):  # 複数プロジェクトで共有する書庫（プロジェクト外）は検査しない
        for p in sorted(pdfdir.iterdir()):
            if p.name.startswith(".") or p.name == ".gitkeep":
                continue
            if p.suffix.lower() != ".pdf" or p.stem not in bib:
                issues.append(("L044", p, "PDF は <references.bib の citekey>.pdf という名前にする"))
    surveys = d / "surveys"
    if surveys.is_dir():
        for s in sorted(surveys.glob("*.md")):
            if s.name.startswith("_"):
                continue
            if not re.match(r"^\d{4}-\d{2}-\d{2}_[a-z0-9-]+\.md$", s.name):
                issues.append(("L045", s, "サーベイは YYYY-MM-DD_<slug>.md（slug は小文字英数とハイフン）"))
            fm, body = read_frontmatter(s)
            if fm is None:
                issues.append(("L045", s, "YAML frontmatter がありません"))
                continue
            for req in ("date", "question", "search"):
                if req not in fm:
                    issues.append(("L045", s, f"frontmatter に {req} がありません"))
            if fm.get("status") == "done":  # 判定: 問いに答え、一次情報を実際に開いたか
                if fm.get("verdict") not in VERDICT:
                    msg = f"status=done だが verdict が {sorted(VERDICT)} のどれでもない（問いへの答えを 1 語で書く）"
                    issues.append(_issue("L048", s, msg, sev_verdict))
                if _int(fm.get("n_opened")) <= 0:
                    msg = "status=done だが n_opened が 0（一次情報を実際に開いた件数を書く。開いていなければ status を draft に戻す）"
                    issues.append(_issue("L048", s, msg, sev_verdict))
            for m in CITE_RE.finditer(body):
                key = next(g for g in m.groups() if g)
                if KEY_RE.match(key) and key not in bib:
                    issues.append(("L046", s, f"引用 @{key} が references.bib にありません"))
    return issues
