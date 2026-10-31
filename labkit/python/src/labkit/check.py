"""規約チェック（labkit check）。すべてのルールは lab.toml で調整できる.

コード一覧:
    L001 トップレベルに許可されていないファイル/ディレクトリ
    L002 data/raw が MANIFEST と一致しない      L003 data/raw が書き込み可能
    L010 描画ライブラリの直接 import（図は labkit fig のテンプレートで作る）
    L011 src が scripts/notebooks を import している（依存の向き違反）
    L012 コードに絶対パスが直書きされている（configs/paths/*.toml を使う）
    L013 禁止形式（pickle/JLD2 など）の使用
    L014 図ファイルが runs/*/figures 以外にある  L015 データファイルが data/ と runs/ 以外にある
    L020 run の meta.json が無い/スキーマ違反   L021 run が未完了（running のまま）
    L022 data/ の派生ファイルにサイドカーが無い/スキーマ違反
    L030 開発ログの書式違反                     L031 ADR の書式違反
    L032 文書が引用する run ID が runs/ に無い（meta.json が無い）。failed/link の run の引用は警告
    L033 run の数値の引用が `12.3 dB [run:<run_id>:<key>]` 書式でない／metrics.json と一致しない
    L035 レビュー記録（docs/reviews/）の書式違反
    L050 lab-standards 本体を手元参照（link）したまま（commit 禁止）
    L040-L046 文献管理（literature.py 参照）
"""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from labkit.config import find_root, load_lab

SKIP_DIRS = {".git", ".venv", "__pycache__", ".mlflow", ".pytest_cache", ".ruff_cache", "node_modules",
             ".ipynb_checkpoints"}
FIG_EXT = {".png", ".pdf", ".svg", ".eps", ".jpg", ".jpeg", ".tif", ".tiff"}
DATA_EXT = {".h5", ".hdf5", ".parquet", ".npy", ".npz", ".mat", ".csv", ".tsv", ".pkl", ".pickle",
            ".jld2", ".bson", ".feather", ".arrow", ".nc", ".zarr", ".pt", ".ckpt"}


@dataclass
class Issue:
    code: str
    where: str
    message: str
    severity: str = "error"  # "error" | "warn"（warn は strict でも失敗にしない）

    def __str__(self) -> str:
        tag = "  (warn)" if self.severity == "warn" else ""
        return f"{self.code}{tag}  {self.where}  {self.message}"


# run ID: YYYYMMDD-HHMMSS_<slug>_<commit7|nogit>_<hex4>（runs.make_run_id と同じ）
RUN_ID_RE = re.compile(r"\b(\d{8}-\d{6}_[a-z0-9-]+_(?:[0-9a-f]{7}|nogit)_[0-9a-f]{4})\b")
# 数値の引用: <数値> [<単位>] [run:<run_id>:<key>]（`labkit cite` が出力する書式）
CITE_RE = re.compile(
    r"(?P<num>[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*(?P<unit>[^\s\[\]\d][^\s\[\]]{0,11})?\s*"
    r"\[run:(?P<run>[^:\]\s]+):(?P<key>[^\]\s]+)\]")
NUMBER_RE = re.compile(r"(?<![\w./:-])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?(?![\w./:-])")


class Checker:
    def __init__(self, root: Path | None = None, full: bool = False, ignore: set[str] | None = None):
        self.root = root or find_root()
        self.lab = load_lab(self.root)
        self.full = full
        self.issues: list[Issue] = []
        self.skip = set(self.lab["check"]["skip"]) | set(ignore or ())

    def add(self, code: str, where: Path | str, msg: str, severity: str = "error") -> None:
        if code in self.skip:
            return
        w = str(where.relative_to(self.root)) if isinstance(where, Path) and where.is_absolute() else str(where)
        self.issues.append(Issue(code, w, msg, severity))

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    def run(self) -> list[Issue]:
        for f in (self.layout, self.standards_link, self.rawdata, self.code_rules, self.stray_files,
                  self.runs_meta, self.data_sidecars, self.devlog, self.adr, self.reviews, self.citations,
                  self.literature):
            try:
                f()
            except Exception as e:  # チェッカー自身の失敗も報告する
                self.add("L999", f.__name__, f"チェック中に例外: {type(e).__name__}: {e}")
        return self.issues

    # ---- 構造 ----
    def layout(self) -> None:
        allowed = set(self.lab["layout"]["allowed"]) | {".lab"}  # v0.3.0 ハーネスの状態（古い lab.toml でも許す）
        for p in sorted(self.root.iterdir()):
            if p.name not in allowed:
                self.add("L001", p, "トップレベルに置けません（lab.toml の layout.allowed 参照。一時ファイルは scratch/ へ）")

    def standards_link(self) -> None:
        if not (self.root / "pyproject.toml").is_file():
            return
        from labkit.standards import status

        st = status(self.root)
        if st.python_mode == "link":
            self.add("L050", "pyproject.toml", f"labkit が手元の本体（{st.python_ref}）を参照中（link）。"
                     "リリース後に `labkit standards unlink --to vX.Y.Z` で戻してから commit する")
        if st.julia_mode == "link":
            self.add("L050", "jl/Project.toml", f"LabKit が手元の本体（{st.julia_ref}）を参照中（link）。"
                     "`labkit standards unlink --to vX.Y.Z` で戻してから commit する")

    def rawdata(self) -> None:
        from labkit.rawdata import verify

        for code, where, msg in verify(self.root, full=self.full):
            self.add(code, where, msg)

    # ---- コード ----
    def _code_files(self):
        for d in self.lab["check"]["code_dirs"]:
            base = self.root / d
            if not base.is_dir():
                continue
            for p in base.rglob("*"):
                if p.suffix in {".py", ".jl", ".ipynb"} and not (set(p.parts) & SKIP_DIRS):
                    yield p

    def _allowed(self, p: Path, patterns: list[str]) -> bool:
        rel = str(p.relative_to(self.root))
        return any(fnmatch.fnmatch(rel, pat) for pat in patterns)

    def code_rules(self) -> None:
        c = self.lab["check"]
        plot = [re.escape(m) for m in c["banned_plot_imports"]]
        fmts = [re.escape(m) for m in c["banned_formats"]]
        py_plot = re.compile(rf"^\s*(?:import|from)\s+({'|'.join(plot)})\b", re.M)
        jl_plot = re.compile(rf"^\s*(?:using|import)\s+[^#\n]*\b({'|'.join(plot)})\b", re.M)
        py_fmt = re.compile(rf"^\s*(?:import|from)\s+({'|'.join(fmts)})\b", re.M)
        jl_fmt = re.compile(rf"^\s*(?:using|import)\s+[^#\n]*\b({'|'.join(fmts)})\b", re.M)
        py_dep = re.compile(r"^\s*(?:import|from)\s+(scripts|notebooks)\b", re.M)
        abs_re = re.compile("|".join(c["abs_path_patterns"]))
        for p in self._code_files():
            text = p.read_text(encoding="utf-8", errors="replace")
            if p.suffix == ".ipynb":
                try:
                    cells = json.loads(text).get("cells", [])
                    text = "\n".join("".join(cell.get("source", [])) for cell in cells
                                     if cell.get("cell_type") == "code")
                except json.JSONDecodeError:
                    continue
            is_jl = p.suffix == ".jl"

            def line_of(m, p=p, text=text) -> str:
                return f"{p.relative_to(self.root)}:{text.count(chr(10), 0, m.start()) + 1}"

            if not self._allowed(p, c["plot_import_allowed"]):
                for m in (jl_plot if is_jl else py_plot).finditer(text):
                    self.add("L010", line_of(m), f"{m.group(1)} の直接使用は禁止。図は figspecs/*.toml + `labkit fig` で作る")
            if not self._allowed(p, c["format_allowed"]):
                for m in (jl_fmt if is_jl else py_fmt).finditer(text):
                    self.add("L013", line_of(m), f"{m.group(1)} は禁止形式。HDF5/Parquet（labkit.save）を使う")
            rel_parts = p.relative_to(self.root).parts
            if rel_parts[0] == "src" and not is_jl:
                for m in py_dep.finditer(text):
                    self.add("L011", line_of(m), "src から scripts/notebooks を import できません（依存は scripts → src の一方向）")
            for m in abs_re.finditer(text):
                self.add("L012", line_of(m), "絶対パスの直書き。configs/paths/*.toml と labkit.datapath を使う")

    def stray_files(self) -> None:
        c = self.lab["check"]
        roots = [self.root / d for d in c["code_dirs"]] + [self.root / d for d in
                 ("configs", "docs", "figspecs", "jobs", "prompts", "literature")]
        for base in roots:
            if not base.is_dir():
                continue
            for p in base.rglob("*"):
                if set(p.parts) & SKIP_DIRS or not p.is_file():
                    continue
                rel = str(p.relative_to(self.root))
                if p.suffix.lower() in FIG_EXT and not any(rel.startswith(d + "/") for d in c["figure_ok_dirs"]):
                    self.add("L014", p, "図は runs/<id>/figures に `labkit fig` で出力する（手作り図の混入）")
                if p.suffix.lower() in DATA_EXT and not any(rel.startswith(d + "/") for d in c["data_ok_dirs"]):
                    self.add("L015", p, "データファイルは data/ か runs/ に置く")
        for p in self.root.iterdir():
            if p.is_file() and (p.suffix.lower() in FIG_EXT | DATA_EXT):
                self.add("L015", p, "ルート直下にデータ/図を置けません")

    # ---- run とデータ ----
    def _schema(self, name: str) -> dict:
        return json.loads(resources.files("labkit.schemas").joinpath(name).read_text(encoding="utf-8"))

    def runs_meta(self) -> None:
        import jsonschema

        from labkit.paths import runs_root

        base = runs_root(self.root)
        if not base.is_dir():
            return
        schema = self._schema("run_meta.schema.json")
        for d in sorted(base.iterdir()):
            if not d.is_dir():
                if d.name != ".gitkeep":
                    self.add("L020", d, "runs/ 直下には run ディレクトリだけを置く")
                continue
            mf = d / "meta.json"
            if not mf.is_file():
                self.add("L020", d, "meta.json がありません（labkit の Run 以外で作られた？）")
                continue
            try:
                meta = json.loads(mf.read_text(encoding="utf-8"))
                jsonschema.validate(meta, schema)
            except (json.JSONDecodeError, jsonschema.ValidationError) as e:
                self.add("L020", mf, f"スキーマ違反: {getattr(e, 'message', e)}")
                continue
            if meta["status"] == "running":
                self.add("L021", d, "status=running のまま（実行中か、異常終了）")

    def data_sidecars(self) -> None:
        import jsonschema

        from labkit.paths import datapath

        schema = self._schema("data_meta.schema.json")
        for stage in ("interim", "processed"):
            base = datapath(stage, root=self.root)
            if not base.is_dir():
                continue
            for p in sorted(base.iterdir()):
                if p.name.startswith(".") or p.name.endswith(".meta.json") or p.name in {"README.md"}:
                    continue
                sc = p.with_name(p.name + ".meta.json")
                if not sc.is_file():
                    self.add("L022", p, "サイドカー .meta.json がありません（labkit.save / writer で保存する）")
                    continue
                try:
                    jsonschema.validate(json.loads(sc.read_text(encoding="utf-8")), schema)
                except (json.JSONDecodeError, jsonschema.ValidationError) as e:
                    self.add("L022", sc, f"スキーマ違反: {getattr(e, 'message', e)}")

    # ---- 文書 ----
    def _headings(self, text: str) -> set[str]:
        return {m.group(1).strip() for m in re.finditer(r"^##\s+(.+?)\s*$", text, re.M)}

    def devlog(self) -> None:
        conf = self.lab["devlog"]
        base = self.root / conf["dir"]
        if not base.is_dir():
            return
        for p in sorted(base.iterdir()):
            if p.name in {".gitkeep", "README.md"}:
                continue
            if not re.match(r"^\d{4}-\d{2}-\d{2}\.md$", p.name):
                self.add("L030", p, "開発ログは YYYY-MM-DD.md（1日1ファイル。`labkit devlog` で作成）")
                continue
            heads = self._headings(p.read_text(encoding="utf-8"))
            missing = [h for h in conf["required_headings"] if h not in heads]
            if missing:
                self.add("L030", p, f"必須見出しが不足: {missing}")

    def adr(self) -> None:
        conf = self.lab["adr"]
        base = self.root / conf["dir"]
        if not base.is_dir():
            return
        for p in sorted(base.iterdir()):
            if p.name in {".gitkeep", "README.md"}:
                continue
            if not re.match(r"^\d{4}-[a-z0-9-]+\.md$", p.name):
                self.add("L031", p, "ADR は NNNN-kebab-case.md（`labkit adr \"タイトル\"` で作成）")
                continue
            text = p.read_text(encoding="utf-8")
            if not re.search(r"^- 状態:\s*(提案|採用|却下|廃止|置換)", text, re.M):
                self.add("L031", p, "「- 状態: 提案|採用|却下|廃止|置換」の行が必要です")
            missing = [h for h in conf["required_headings"] if h not in self._headings(text)]
            if missing:
                self.add("L031", p, f"必須見出しが不足: {missing}")

    def reviews(self) -> None:
        from labkit.reviews import REVIEW_DIR, list_reviews

        if not (self.root / REVIEW_DIR).is_dir():
            return
        for r in list_reviews(self.root):
            for e in r.errors:
                self.add("L035", r.path, e)

    # ---- 報告と実データの照合（L032 / L033） ----
    def _doc_files(self):
        from labkit.reviews import REVIEW_DIR

        dirs = [self.lab["devlog"]["dir"], self.lab["adr"]["dir"], REVIEW_DIR,
                str(Path(self.lab["literature"]["dir"]) / "surveys")]
        for d in dirs:
            base = self.root / d
            if base.is_dir():
                yield from sorted(p for p in base.glob("*.md") if p.name != "README.md")

    def _run_index(self) -> dict[str, dict | None]:
        """run_id -> meta（meta.json が無ければ None）."""
        from labkit.paths import runs_root

        base = runs_root(self.root)
        out: dict[str, dict | None] = {}
        if base.is_dir():
            for d in base.iterdir():
                if d.is_dir():
                    mf = d / "meta.json"
                    try:
                        out[d.name] = json.loads(mf.read_text(encoding="utf-8")) if mf.is_file() else None
                    except json.JSONDecodeError:
                        out[d.name] = None
        return out

    def citations(self) -> None:
        from labkit.paths import runs_root

        runs = self._run_index()
        bare = self.lab["check"].get("cite_bare_numbers", "warn")
        cache: dict[str, dict] = {}

        def metrics(run_id: str) -> dict:
            if run_id not in cache:
                mf = runs_root(self.root) / run_id / "metrics.json"
                try:
                    cache[run_id] = json.loads(mf.read_text(encoding="utf-8")) if mf.is_file() else {}
                except json.JSONDecodeError:
                    cache[run_id] = {}
            return cache[run_id]

        for p in self._doc_files():
            text = p.read_text(encoding="utf-8", errors="replace")
            for n, line in enumerate(text.splitlines(), 1):
                where = f"{p.relative_to(self.root)}:{n}"
                ids = set(RUN_ID_RE.findall(line))
                for rid in ids:  # L032: 引用された run の存在と状態
                    if rid not in runs:
                        self.add("L032", where, f"run {rid} が runs/ にありません（HPC の run なら meta.json を同期する）")
                    elif runs[rid] is None:
                        self.add("L032", where, f"run {rid} に meta.json がありません")
                    else:
                        m = runs[rid]
                        if m.get("status") in ("failed", "interrupted", "running"):
                            self.add("L032", where, f"run {rid} は status={m.get('status')}（結果として引用しない）", "warn")
                        if (m.get("labkit_source") or {}).get("mode") == "link":
                            self.add("L032", where, f"run {rid} は link 中の labkit で実行（正式版の結果ではない）", "warn")
                rest = line
                for m in CITE_RE.finditer(line):  # L033: 数値の引用を metrics.json と照合
                    rest = rest.replace(m.group(0), " ")
                    rid, key, num = m.group("run"), m.group("key"), m.group("num")
                    if rid not in runs or runs[rid] is None:
                        continue  # L032 で報告済み
                    vals = metrics(rid)
                    if key not in vals:
                        self.add("L033", where, f"run {rid} の metrics.json に {key} がありません")
                    elif not num_matches(num, vals[key]):
                        self.add("L033", where, f"{num} は run {rid} の {key}={vals[key]} と一致しません（表示桁で丸めて比較）")
                if ids and bare != "off" and not line.lstrip().startswith("#"):
                    for rid in ids:
                        rest = rest.replace(rid, " ")
                    rest = re.sub(r"\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}(?::\d{2})?", " ", rest)  # 日付・時刻は除く
                    if NUMBER_RE.search(rest):
                        self.add("L033", where, "run ID と同じ行に書式のない数値があります。`labkit cite <run_id> <key>` の "
                                 "`値 [run:<run_id>:<key>]` 書式で書く（lab.toml の check.cite_bare_numbers = \"off\" で無効化）",
                                 "warn")

    def literature(self) -> None:
        from labkit.literature import check_literature

        for code, where, msg in check_literature(self.root, self.lab):
            self.add(code, where, msg)


def num_matches(text: str, value) -> bool:
    """表示されている桁数で丸めて一致するか（"12.3" と 12.34 → True、"12.30" と 12.34 → False）."""
    try:
        shown = float(text)
        v = float(value)
    except (TypeError, ValueError):
        return False
    mant = text.lower().split("e")[0]
    digits = len(mant.split(".")[1]) if "." in mant else 0
    if "e" in text.lower():
        return float(format(v, f".{digits}e")) == shown
    return round(v, digits) == shown


def format_value(value, digits: int | None) -> str:
    """`labkit cite` 用。digits 指定なら小数点以下をその桁に丸める。未指定は有効数字 4 桁."""
    v = float(value)
    if digits is not None:
        return f"{v:.{digits}f}"
    if v == 0:
        return "0"
    if 1e-3 <= abs(v) < 1e6:
        s = f"{v:.4g}"
        return s if "e" not in s else f"{v:.6f}".rstrip("0").rstrip(".")
    return f"{v:.3e}"


def cite(run_id: str, key: str, digits: int | None = None, unit: str = "", root: Path | None = None) -> str:
    """run の指標を `値 [単位] [run:<run_id>:<key>]` 書式で返す（L033 が検証できる書式）."""
    from labkit.runs import find_run

    d = find_run(run_id, root)
    mf = d / "metrics.json"
    if not mf.is_file():
        raise FileNotFoundError(f"{d.name} に metrics.json がありません（run 完了後に生成される）")
    vals = json.loads(mf.read_text(encoding="utf-8"))
    if key not in vals:
        raise KeyError(f"{d.name} の metrics.json に {key} がありません。あるキー: {', '.join(sorted(vals))}")
    shown = format_value(vals[key], digits)
    return f"{shown}{(' ' + unit) if unit else ''} [run:{d.name}:{key}]"


def run_check(full: bool = False, root: Path | None = None, ignore: set[str] | None = None) -> tuple[list[Issue], str]:
    ch = Checker(root, full=full, ignore=ignore)
    return ch.run(), ch.lab["check"]["mode"]
