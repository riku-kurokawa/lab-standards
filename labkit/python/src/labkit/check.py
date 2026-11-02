"""規約チェック（labkit check）。ルールは lab.toml で調整できる.

成果物の検証（--claims。Stop hook が見る）:
    L002 data/raw が MANIFEST と一致しない      L003 data/raw が書き込み可能
    L020 run の meta.json が無い/スキーマ違反   L021 run が running のまま（警告。`labkit runs mark`）
    L022 data/interim・processed の派生ファイルにサイドカーが無い/スキーマ違反（data/cache は対象外）
    L030 開発ログの書式違反・必須欄（目的 / 判断と理由 / 未解決）が空
    L032 文書が引用する run ID が runs/ に無い。failed/link の run の引用は警告
    L033 `12.3 dB [run:<run_id>:<key>]` の数値が metrics.json と一致しない
    L034 「結果・観察」節の小数・指数表記の数値に引用が無い（警告）
体裁（pre-commit / CI）:
    L001 トップレベルの不許可ファイル   L004 衝突マーカー   L050 本体を link したまま
    L010 描画ライブラリの直接 import    L011 src → scripts の依存   L012 絶対パスの直書き
    L013 禁止形式（pickle など）        L016 np.save / np.savez / torch.save（labkit.save を使う。警告）
    L014 図が runs/*/figures 以外にある  L015 データが data/・runs/ 以外にある
    L031 ADR の書式   L035 レビュー記録の書式   L040-L046 文献管理（literature.py）
"""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from labkit._util import read_json
from labkit.config import find_root, load_lab

SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules", ".ipynb_checkpoints"}
FIG_EXT = {".png", ".pdf", ".svg", ".eps", ".jpg", ".jpeg", ".tif", ".tiff"}
DATA_EXT = {
    ".h5",
    ".hdf5",
    ".parquet",
    ".npy",
    ".npz",
    ".mat",
    ".csv",
    ".tsv",
    ".pkl",
    ".pickle",
    ".feather",
    ".arrow",
    ".nc",
    ".zarr",
    ".pt",
    ".ckpt",
}
RUN_ID_RE = re.compile(r"\b(\d{8}-\d{6}_[a-z0-9-]+_(?:[0-9a-f]{7}|nogit)_[0-9a-f]{4})\b")
CITE_RE = re.compile(
    r"(?P<num>[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*(?P<unit>[^\s\[\]\d][^\s\[\]]{0,11})?\s*"
    r"\[run:(?P<run>[^:\]\s]+):(?P<key>[^\]\s]+)\]"
)
# 測定値らしい数値: 小数または指数表記（整数の個数・番号は対象にしない）
MEASURE_RE = re.compile(r"(?<![\w./:-])[-+]?\d+(?:\.\d+(?:[eE][-+]?\d+)?|[eE][-+]?\d+)(?![\w./:-])")
RESULTS_HEADING = "結果・観察"


@dataclass
class Issue:
    code: str
    where: str
    message: str
    severity: str = "error"  # "error" | "warn"（warn は strict でも失敗にしない）

    def __str__(self) -> str:
        return f"{self.code}{'  (warn)' if self.severity == 'warn' else ''}  {self.where}  {self.message}"


class Checker:
    def __init__(
        self, root: Path | None = None, full: bool = False, ignore: set[str] | None = None, claims: bool = False
    ):
        self.root = root or find_root()
        self.lab = load_lab(self.root)
        self.full = full
        self.claims = claims
        self.issues: list[Issue] = []
        self.skip = set(self.lab["check"]["skip"]) | set(ignore or ())

    def add(self, code: str, where: Path | str, msg: str, severity: str = "error") -> None:
        if code in self.skip:
            return
        w = where.relative_to(self.root).as_posix() if isinstance(where, Path) and where.is_absolute() else str(where)
        self.issues.append(Issue(code, w, msg, severity))

    def run(self) -> list[Issue]:
        claims = (self.rawdata, self.runs_meta, self.data_sidecars, self.devlog, self.citations)
        style = (
            self.layout,
            self.conflict_markers,
            self.standards_link,
            self.code_rules,
            self.stray_files,
            self.adr,
            self.reviews,
            self.literature,
        )
        for f in claims if self.claims else claims + style:
            try:
                f()
            except Exception as e:  # チェッカー自身の失敗も報告する
                self.add("L999", f.__name__, f"チェック中に例外: {type(e).__name__}: {e}")
        return self.issues

    # ---- 構造 ----
    def layout(self) -> None:
        allowed = set(self.lab["layout"]["allowed"]) | {".lab"}
        for p in sorted(self.root.iterdir()):
            if p.name not in allowed:
                self.add(
                    "L001", p, "トップレベルに置けません（lab.toml の layout.allowed 参照。一時ファイルは scratch/ へ）"
                )

    def conflict_markers(self) -> None:
        big = {"data", "runs", ".lab"} | SKIP_DIRS
        for t in (p for p in self.root.iterdir() if p.name not in big):
            for p in [t] if t.is_file() else t.rglob("*"):
                if set(p.parts) & SKIP_DIRS or not p.is_file() or p.suffix.lower() in FIG_EXT | DATA_EXT:
                    continue
                try:
                    with open(p, "rb") as f:
                        head = f.read(8192)
                    if b"\0" in head or (
                        b"<<<<<<< " not in head and b">>>>>>> " not in head and p.stat().st_size <= 8192
                    ):
                        continue
                    text = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if line.startswith(("<<<<<<< ", ">>>>>>> ")):
                        self.add(
                            "L004", f"{p.relative_to(self.root).as_posix()}:{i}", "マージの衝突マーカーが残っています"
                        )
                        break

    def standards_link(self) -> None:
        if not (self.root / "pyproject.toml").is_file():
            return
        from labkit.standards import status

        st = status(self.root)
        if st.mode == "link":
            self.add(
                "L050",
                "pyproject.toml",
                f"labkit が手元の本体（{st.ref}）を参照中（link）。`labkit standards unlink --to vX.Y.Z` で戻してから commit",
            )

    def rawdata(self) -> None:
        from labkit.rawdata import verify

        for code, where, msg in verify(self.root, full=self.full):
            self.add(code, where, msg)

    # ---- コード ----
    def _code_files(self):
        for d in self.lab["check"]["code_dirs"]:
            base = self.root / d
            if base.is_dir():
                yield from (
                    p for p in base.rglob("*") if p.suffix in {".py", ".ipynb", ".sh"} and not set(p.parts) & SKIP_DIRS
                )

    def _allowed(self, p: Path, patterns: list[str]) -> bool:
        rel = p.relative_to(self.root).as_posix()
        return any(fnmatch.fnmatch(rel, pat) for pat in patterns)

    def code_rules(self) -> None:
        c = self.lab["check"]
        py_plot = re.compile(rf"^\s*(?:import|from)\s+({'|'.join(map(re.escape, c['banned_plot_imports']))})\b", re.M)
        py_fmt = re.compile(rf"^\s*(?:import|from)\s+({'|'.join(map(re.escape, c['banned_formats']))})\b", re.M)
        py_dep = re.compile(r"^\s*(?:import|from)\s+(scripts|notebooks)\b", re.M)
        py_save = re.compile(r"\b(np|numpy|torch)\.(save|savez|savez_compressed)\(")
        abs_re = re.compile("|".join(c["abs_path_patterns"]))
        for p in self._code_files():
            text = p.read_text(encoding="utf-8", errors="replace")
            if p.suffix == ".ipynb":
                try:
                    cells = json.loads(text).get("cells", [])
                    text = "\n".join("".join(c.get("source", [])) for c in cells if c.get("cell_type") == "code")
                except json.JSONDecodeError:
                    continue

            def at(m, p=p, text=text) -> str:
                return f"{p.relative_to(self.root).as_posix()}:{text.count(chr(10), 0, m.start()) + 1}"

            if p.suffix == ".sh":  # ジョブスクリプトは絶対パスだけ見る
                for m in abs_re.finditer(text):
                    self.add("L012", at(m), "絶対パスの直書き。configs/paths/*.toml と環境変数（$WORK など）を使う")
                continue
            if not self._allowed(p, c["plot_import_allowed"]):
                for m in py_plot.finditer(text):
                    self.add(
                        "L010", at(m), f"{m.group(1)} の直接使用は禁止。図は figspecs/*.toml + `labkit fig` で作る"
                    )
            if not self._allowed(p, c["format_allowed"]):
                for m in py_fmt.finditer(text):
                    self.add("L013", at(m), f"{m.group(1)} は禁止形式。HDF5/Parquet（labkit.save）を使う")
                for m in py_save.finditer(text):
                    self.add(
                        "L016",
                        at(m),
                        f"{m.group(0)[:-1]} はサイドカー（来歴）が付きません。labkit.save / writer を使う",
                        "warn",
                    )
            if p.relative_to(self.root).parts[0] == "src":
                for m in py_dep.finditer(text):
                    self.add(
                        "L011",
                        at(m),
                        "src から scripts/notebooks を import できません（依存は scripts → src の一方向）",
                    )
            for m in abs_re.finditer(text):
                self.add("L012", at(m), "絶対パスの直書き。configs/paths/*.toml と labkit.datapath を使う")

    def stray_files(self) -> None:
        c = self.lab["check"]
        for d in [*c["code_dirs"], "configs", "docs", "figspecs", "prompts", "literature"]:
            base = self.root / d
            for p in base.rglob("*") if base.is_dir() else []:
                if set(p.parts) & SKIP_DIRS or not p.is_file():
                    continue
                rel = p.relative_to(self.root).as_posix()
                if p.suffix.lower() in FIG_EXT and not any(rel.startswith(x + "/") for x in c["figure_ok_dirs"]):
                    self.add("L014", p, "図は runs/<id>/figures に `labkit fig` で出力する（手作り図の混入）")
                if p.suffix.lower() in DATA_EXT and not any(rel.startswith(x + "/") for x in c["data_ok_dirs"]):
                    self.add("L015", p, "データファイルは data/ か runs/ に置く")
        for p in self.root.iterdir():
            if p.is_file() and p.suffix.lower() in FIG_EXT | DATA_EXT:
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
                meta = read_json(mf)
                jsonschema.validate(meta, schema)
            except (json.JSONDecodeError, jsonschema.ValidationError) as e:
                self.add("L020", mf, f"スキーマ違反: {getattr(e, 'message', e)}")
                continue
            if meta["status"] == "running":
                hb = d / "heartbeat"
                age = ""
                if hb.is_file():
                    import datetime as _dt

                    secs = (_dt.datetime.now() - _dt.datetime.fromtimestamp(hb.stat().st_mtime)).total_seconds()
                    age = f"最後の記録から {secs / 3600:.1f} 時間"
                self.add(
                    "L021",
                    d,
                    f"status=running のまま（{age or '実行中か異常終了'}）。終わっているなら `labkit runs mark {d.name} failed --reason ...`",
                    "warn",
                )

    def data_sidecars(self) -> None:
        import jsonschema

        from labkit.paths import datapath

        schema = self._schema("data_meta.schema.json")
        for stage in ("interim", "processed"):
            base = datapath(stage, root=self.root)
            if not base.is_dir():
                continue
            sidecars = {p for p in base.rglob("*.meta.json")}
            for p in sorted(base.rglob("*")):
                if not p.is_file() or p in sidecars or p.name.startswith(".") or p.name == "README.md":
                    continue
                sc = p.with_name(p.name + ".meta.json")
                if any(
                    q.with_name(q.name + ".meta.json") in sidecars for q in p.parents if q != base and base in q.parents
                ):
                    continue  # writer() が作ったディレクトリ形式（Zarr など）の中身
                if not sc.is_file():
                    self.add(
                        "L022",
                        p,
                        "サイドカー .meta.json がありません（labkit.save / writer で保存する。再生成できる中間物は data/cache へ）",
                    )
                    continue
                try:
                    jsonschema.validate(read_json(sc), schema)
                except (json.JSONDecodeError, jsonschema.ValidationError) as e:
                    self.add("L022", sc, f"スキーマ違反: {getattr(e, 'message', e)}")

    # ---- 文書 ----
    def _headings(self, text: str) -> set[str]:
        return {m.group(1).strip() for m in re.finditer(r"^##\s+(.+?)\s*$", text, re.M)}

    def devlog(self) -> None:
        from labkit.devlog import section_bodies

        conf = self.lab["devlog"]
        base = self.root / conf["dir"]
        for p in sorted(base.iterdir()) if base.is_dir() else []:
            if p.name in {".gitkeep", "README.md"}:
                continue
            if not re.match(r"^\d{4}-\d{2}-\d{2}\.md$", p.name):
                self.add("L030", p, "開発ログは YYYY-MM-DD.md（1 日 1 ファイル。`labkit devlog` で作成）")
                continue
            text = p.read_text(encoding="utf-8")
            if missing := [h for h in conf["required_headings"] if h not in self._headings(text)]:
                self.add("L030", p, f"必須見出しが不足: {missing}")
            bodies = section_bodies(text)
            if empty := [h for h in conf["must_fill"] if h in bodies and not bodies[h].strip()]:
                self.add("L030", p, f"見出しの本文が空: {empty}（見出しだけの開発ログは記録ではない）")

    def adr(self) -> None:
        conf = self.lab["adr"]
        base = self.root / conf["dir"]
        for p in sorted(base.iterdir()) if base.is_dir() else []:
            if p.name in {".gitkeep", "README.md"}:
                continue
            if not re.match(r"^\d{4}-[a-z0-9-]+\.md$", p.name):
                self.add("L031", p, 'ADR は NNNN-kebab-case.md（`labkit adr "タイトル"` で作成）')
                continue
            text = p.read_text(encoding="utf-8")
            if not re.search(r"^- 状態:\s*(提案|採用|却下|廃止|置換)", text, re.M):
                self.add("L031", p, "「- 状態: 提案|採用|却下|廃止|置換」の行が必要です")
            if missing := [h for h in conf["required_headings"] if h not in self._headings(text)]:
                self.add("L031", p, f"必須見出しが不足: {missing}")

    def reviews(self) -> None:
        from labkit.reviews import list_reviews

        for r in list_reviews(self.root):
            for e in r.errors:
                self.add("L035", r.path, e)

    # ---- 報告と実データの照合 ----
    def _doc_files(self):
        from labkit.reviews import REVIEW_DIR

        for d in (
            self.lab["devlog"]["dir"],
            self.lab["adr"]["dir"],
            REVIEW_DIR,
            f"{self.lab['literature']['dir']}/surveys",
        ):
            base = self.root / d
            if base.is_dir():
                yield from sorted(p for p in base.glob("*.md") if p.name != "README.md")

    def citations(self) -> None:
        from labkit.paths import runs_root

        base = runs_root(self.root)
        runs: dict[str, dict | None] = {}
        for d in base.iterdir() if base.is_dir() else []:
            if d.is_dir():
                try:
                    runs[d.name] = read_json(d / "meta.json") if (d / "meta.json").is_file() else None
                except json.JSONDecodeError:
                    runs[d.name] = None
        cache: dict[str, dict] = {}

        def metrics(rid: str) -> dict:
            if rid not in cache:
                mf = base / rid / "metrics.json"
                try:
                    cache[rid] = read_json(mf) if mf.is_file() else {}
                except json.JSONDecodeError:
                    cache[rid] = {}
            return cache[rid]

        for p in self._doc_files():
            section = None
            is_devlog = p.parent == self.root / self.lab["devlog"]["dir"]
            for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if m := re.match(r"^##\s+(.+?)\s*$", line):
                    section = m.group(1)
                where = f"{p.relative_to(self.root).as_posix()}:{n}"
                for rid in set(RUN_ID_RE.findall(line)):
                    if rid not in runs:
                        self.add(
                            "L032", where, f"run {rid} が runs/ にありません（HPC の run なら meta.json を同期する）"
                        )
                    elif runs[rid] is None:
                        self.add("L032", where, f"run {rid} に meta.json がありません")
                    else:
                        meta = runs[rid]
                        if meta.get("status") != "finished":
                            self.add(
                                "L032",
                                where,
                                f"run {rid} は status={meta.get('status')}（結果として引用しない）",
                                "warn",
                            )
                        if (meta.get("labkit_source") or {}).get("mode") == "link":
                            self.add(
                                "L032", where, f"run {rid} は link 中の labkit で実行（正式版の結果ではない）", "warn"
                            )
                rest = line
                for m in CITE_RE.finditer(line):
                    rest = rest.replace(m.group(0), " ")
                    rid, key, num = m.group("run"), m.group("key"), m.group("num")
                    if rid not in runs or runs[rid] is None:
                        continue
                    vals = metrics(rid)
                    if key not in vals:
                        self.add("L033", where, f"run {rid} の metrics.json に {key} がありません")
                    elif not num_matches(num, vals[key]):
                        self.add(
                            "L033",
                            where,
                            f"{num} は run {rid} の {key}={vals[key]} と一致しません（表示桁で丸めて比較）",
                        )
                if is_devlog and section == RESULTS_HEADING and not line.lstrip().startswith(("#", "<!--")):
                    rest = RUN_ID_RE.sub(" ", rest)
                    rest = re.sub(r"\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}(?::\d{2})?", " ", rest)
                    if MEASURE_RE.search(rest):
                        self.add(
                            "L034",
                            where,
                            "結果の数値に引用がありません。`labkit cite <run_id> <key>` の `値 [run:<id>:<key>]` を貼る（run に無い量なら metrics に記録する）",
                            "warn",
                        )

    def literature(self) -> None:
        from labkit.literature import check_literature

        for code, where, msg in check_literature(self.root, self.lab):
            self.add(code, where, msg)


def num_matches(text: str, value) -> bool:
    """表示されている桁数で丸めて一致するか（"12.3" と 12.34 → True、"12.30" と 12.34 → False）."""
    try:
        shown, v = float(text), float(value)
    except (TypeError, ValueError):
        return False
    mant = text.lower().split("e")[0]
    digits = len(mant.split(".")[1]) if "." in mant else 0
    if "e" in text.lower():
        return float(format(v, f".{digits}e")) == shown
    return round(v, digits) == shown


def format_value(value, digits: int | None) -> str:
    v = float(value)
    return f"{v:.{digits}f}" if digits is not None else f"{v:.4g}"


def cite(run_id: str, key: str, digits: int | None = None, unit: str = "", root: Path | None = None) -> str:
    """run の指標を `値 [単位] [run:<run_id>:<key>]` 書式で返す（L033 が検証できる書式）."""
    from labkit.runs import find_run

    d = find_run(run_id, root)
    mf = d / "metrics.json"
    if not mf.is_file():
        raise FileNotFoundError(f"{d.name} に metrics.json がありません（run 完了後に生成される）")
    vals = read_json(mf)
    if key not in vals:
        raise ValueError(f"{d.name} の metrics.json に {key} がありません。あるキー: {', '.join(sorted(vals))}")
    return f"{format_value(vals[key], digits)}{(' ' + unit) if unit else ''} [run:{d.name}:{key}]"


def run_check(
    full=False, root: Path | None = None, ignore: set[str] | None = None, claims=False
) -> tuple[list[Issue], str]:
    ch = Checker(root, full=full, ignore=ignore, claims=claims)
    return ch.run(), ch.lab["check"]["mode"]
