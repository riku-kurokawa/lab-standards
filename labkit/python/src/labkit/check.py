"""規約チェック（labkit check）。ルールは lab.toml で調整できる.

成果物の検証（--claims。Stop hook が見る）:
    L002 data/raw が MANIFEST と一致しない      L003 data/raw が書き込み可能
    L020 run の meta.json が無い（殻は `labkit runs mark`）/スキーマ違反
    L021 run が running のまま 10 分以上記録が無い（警告。`labkit runs mark`）
    L022 data/interim・processed の派生ファイルにサイドカーが無い/スキーマ違反（data/cache は対象外）
    L024 予想（prediction）のある run が finished なのに判定（prediction_result）が無い、または予想の key が metrics に無く
         判定できなかった（警告。`labkit runs verdict`）
    L023 run を実行した labkit の版がプロジェクトの固定版と違う（警告。(版, 実行環境) ごとに 1 件。環境の同期漏れ）
    L030 開発ログの書式違反・必須欄（目的 / 判断と理由 / 未解決）が空
    L032 文書（check.claim_docs）が引用する run ID が runs/ に無い。failed/link の run と、退避済みの run の ID だけの言及は警告、
         退避済みの run の数値の引用 `値 [run:<id>:<key>]` は check.archived_citation（既定 error。履歴の文書では警告）、
         dirty な run の引用は check.dirty_citation（既定 warn）。状態の指摘は (文書, 種類) ごとに 1 件。自動ブロック・DIGEST・
         台帳の撤回済みの行は見ない
    L027 比較は 1 軸だけ（compare.py）。凍結した config.json・metrics.json・comparisons.json（meta の outputs と config_sha256 の
         hash を照合）から比較を計算し直す（記録の matched は信用しない）: [compare] を宣言した finished の run の比較がそろっていない・
         記録が無い・改変されている（退避済みは対象外）。対象外が著者の宣言だけ（lab.toml の [compare.capability] に無い）なら警告。
         台帳の open な主張（本文・根拠・備考のすべての引用）の指標が matched な比較の指標でも非比較の宣言（[report] noncomparative。
         腕の名前・比較の指標の語幹・比べる語を含まない）でもない（既定で拒否）、複数 run の根拠に axis が無い・軸以外の設定
         （[compare.<名>] の common・arms を含む）か commit が違う。他の文書の数値の引用: そろわない比較の指標、未宣言の指標、
         同じ指標（腕を名指す語を除いて同じ指標も）を 2 つ以上の run から引く文書（段落・表を区別しない文書ごと。文書に axis=<鍵> が無い・軸以外が違う）は error。
         履歴の文書（check.history_docs: 開発ログ・事前登録・ADR・レビュー。書いた時点の記録で、後の規則に合わせて書き換えない）では
         警告（未宣言と run をまたぐ同じ指標は check.undeclared_citation、既定 warn）。現在の文書（台帳・state・papers・reports など）は error
         1 行（表の行も）に 2 つ以上の run の値、または 1 つの matched な比較の keys ではない同じ run の 2 つ以上の値を並べる行は警告
         （開発ログは出さない）。同じ行に open な主張の ID（根拠がその行の引用を含む）があるか、run をまたぐだけで同じ行の axis=<鍵> が
         通れば出さない。文の意味は機械に読めないので、比較は台帳（claim add）で強制し、文書の並置は警告だけ（残る危険）
         legacy の run（labkit < 2.2.0。meta.config_sha256 が無い。compare.is_legacy）は比較の run ではない（run 単位の照合をせず、
         設定の compare という表は無視）。その 1 つの値の引用は警告、主張に並べた 2 つ以上の値・文書で run をまたぐ同じ指標は error
    L033 `12.3 dB [run:<run_id>:<key>]` の数値が metrics.json と一致しない
    L034 「結果・観察」節の小数・指数表記の数値に引用が無い（警告。引用を含む行は対象外）
    L036 主張の台帳 docs/claims.md の書式、撤回の理由、open な主張の根拠が dirty/failed/退避済み/無い run（claims.py）
    L038 結果・主張の節が scratch/ のファイルを根拠にしている（警告。検証できない）
体裁（pre-commit / CI）:
    L001 トップレベルの不許可ファイル   L004 衝突マーカー   L050 本体を link したまま
    L005 prompts/current.toml が指す goal/beat が無い、またはより新しい版がある（警告。beat.py）
    L025 主線（docs/mainline.md）の open な項目が期限切れ（警告）  L026 主線・芽の台帳の書式（ID の重複・状態・期限・根拠。focus.py）
    L010 描画ライブラリの直接 import    L011 src → scripts の依存（scripts → scripts は警告）   L012 絶対パスの直書き
    L013 禁止形式（pickle など）        L016 np.save / np.savez / torch.save（labkit.save を使う。警告。tests/ は対象外）
    L017 src のモジュールがどこからも import されていない（警告。configs の entry も使用に数える）
    L018 src・scripts のファイルが check.max_file_lines 行（空行を除く）を超える（警告。人間が読める大きさに保つ）
    L014 図が runs/*/figures 以外にある  L015 データが data/・runs/ 以外にある
    L031 ADR の書式   L035 レビュー記録の書式（summary の欠落は警告）   L037 state.md の構造（H1 は 1 つ、同じ H2 は 1 回、行数）
    L040-L048 文献管理（literature.py。L047 ノートの正直さ、L048 サーベイの判定は警告）
"""

from __future__ import annotations

import fnmatch
import functools
import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from labkit._util import read_json, rel_or_abs
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
CLAIM_ID_RE = re.compile(r"\b(C\d{3,})\b")
RUN_ID_RE = re.compile(r"\b(\d{8}-\d{6}_[a-z0-9-]+_(?:[0-9a-f]{7}|nogit)_[0-9a-f]{4})\b")
# 引用: 数値 [単位] [run:<id>:<key>]。単位は数字で始まらず括弧・読点を含まない 1 語（m/s^2 可。無次元は "1"）。数値は cite の直前にあること。
# 符号は Unicode のマイナス（−）も受ける（文書に残りやすい）
CITE_RE = re.compile(
    r"(?P<num>[-+−]?\d+(?:\.\d+)?(?:[eE][-+−]?\d+)?)\s*(?P<unit>1|[^\s\[\]\d()（）、・,;:][^\s\[\]()（）、・,;:]{0,11})?\s*"
    r"\[run:(?P<run>[^:\]\s]+):(?P<key>[^\]\s]+)\]"
)
# 測定値らしい数値: 小数または指数表記（整数の個数・番号は対象にしない）
MEASURE_RE = re.compile(r"(?<![\w./:−-])[-+−]?\d+(?:\.\d+(?:[eE][-+−]?\d+)?|[eE][-+−]?\d+)(?![\w./:-])")
RESULTS_HEADING = "結果・観察"


def walk_files(base: Path, skip: set[str] | frozenset[str] = frozenset()):
    """base 以下のファイル。SKIP_DIRS と skip の名前のディレクトリには降りない
    （rglob は .venv や .claude/worktrees の中まで歩いてから捨てるので、worktree が 100 個あると check が終わらない）."""
    import os

    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and d not in skip)
        for f in sorted(filenames):
            yield Path(dirpath) / f


_VALIDATORS: dict[int, object] = {}


@functools.cache
def _load_schema(name: str) -> dict:
    """同じ dict を返し続ける（_validate が id で検証器を使い回す）."""
    return json.loads(resources.files("labkit.schemas").joinpath(name).read_text(encoding="utf-8"))


def _validate(instance: dict, schema: dict) -> None:
    """jsonschema.validate と同じ判定。schema の検査と解決を run ごとにやり直さない（550 run で 40 秒かかっていた）."""
    import jsonschema

    v = _VALIDATORS.get(id(schema))
    if v is None:
        cls = jsonschema.validators.validator_for(schema)
        cls.check_schema(schema)
        v = _VALIDATORS[id(schema)] = cls(schema)
    if (err := jsonschema.exceptions.best_match(v.iter_errors(instance))) is not None:
        raise err


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
        w = rel_or_abs(where, self.root) if isinstance(where, Path) and where.is_absolute() else str(where)
        self.issues.append(Issue(code, w, msg, severity))

    def run(self) -> list[Issue]:
        claims = (self.rawdata, self.runs_meta, self.data_sidecars, self.devlog, self.citations, self.claims_ledger)
        style = (
            self.layout,
            self.conflict_markers,
            self.standards_link,
            self.code_rules,
            self.dead_modules,
            self.file_length,
            self.stray_files,
            self.adr,
            self.reviews,
            self.state_file,
            self.prompts_current,
            self.focus_ledgers,
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
        # 衝突マーカーは git が管理する文書とコードに残る。成果物（data・runs）、管理外（scratch）、読み取り専用（legacy）、
        # Claude Code の作業領域（.claude: worktree の写し）は見ない
        big = {"data", "runs", ".lab", ".claude", "scratch", *self.lab["layout"]["readonly"]} | SKIP_DIRS
        for t in (p for p in self.root.iterdir() if p.name not in big):
            for p in [t] if t.is_file() else walk_files(t):
                if p.suffix.lower() in FIG_EXT | DATA_EXT:
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
                yield from (p for p in walk_files(base) if p.suffix in {".py", ".ipynb", ".sh"})

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
                # tests/ は対象外: 試験が作る一時ファイルは成果物ではない（来歴は要らない）
                for m in py_save.finditer(text) if p.relative_to(self.root).parts[0] != "tests" else ():
                    self.add(
                        "L016",
                        at(m),
                        f"{m.group(0)[:-1]} はサイドカー（来歴）が付きません。labkit.save / writer を使う",
                        "warn",
                    )
            top = p.relative_to(self.root).parts[0]
            if top == "src":
                for m in py_dep.finditer(text):
                    self.add(
                        "L011",
                        at(m),
                        "src から scripts/notebooks を import できません（依存は scripts → src の一方向）",
                    )
            elif top == "scripts":
                for m in py_dep.finditer(text):
                    self.add(
                        "L011", at(m), "scripts が scripts を import している。共通部分は src の関数にする", "warn"
                    )
            for m in abs_re.finditer(text):
                self.add("L012", at(m), "絶対パスの直書き。configs/paths/*.toml と labkit.datapath を使う")

    def file_length(self) -> None:
        """L018: src・scripts のファイルが長すぎる（空行を除く行数）。人間が一度に読める大きさに保つ."""
        c = self.lab["check"]
        limit = int(c["max_file_lines"])
        if limit <= 0:
            return
        for p in self._code_files():
            if p.suffix != ".py" or p.relative_to(self.root).parts[0] not in ("src", "scripts"):
                continue
            if self._allowed(p, c["max_lines_allowed"]):
                continue
            n = count_code_lines(p)
            if n > limit:
                self.add(
                    "L018",
                    p,
                    f"{n} 行（上限 {limit}）。使っていない分岐・実験ごとの特例を削り、一般の部分を src の小さな関数に分ける",
                    c["long_file"],
                )

    def dead_modules(self) -> None:
        """L017: src のモジュールがどこからも import されていない（警告。使われていないコードは消すか legacy へ）.
        configs の `entry = "pkg.mod:func"`（labkit run）も使用に数える."""
        src = self.root / "src"
        if not src.is_dir():
            return
        texts: dict[Path, str] = {}
        configs = (self.root / "configs").rglob("*.toml") if (self.root / "configs").is_dir() else []
        for p in [*self._code_files(), *configs, *(self.root / f for f in ("Makefile", "pyproject.toml"))]:
            if p.is_file() and not set(p.parts) & SKIP_DIRS:
                texts[p] = p.read_text(encoding="utf-8", errors="replace")
        imp = re.compile(r"^\s*(?:from\s+\S+\s+import\s+(?:\([^)]*\)|.*)|import\s+.*)$", re.M)
        for mod in sorted(src.rglob("*.py")):
            if set(mod.parts) & SKIP_DIRS or mod.stem in ("__init__", "__main__", "conftest"):
                continue
            dotted = ".".join(mod.relative_to(src).with_suffix("").parts)
            word = re.compile(rf"\b{re.escape(mod.stem)}\b")
            used = False
            for p, text in texts.items():
                if p == mod:
                    continue
                if dotted in text or any(word.search(m.group(0)) for m in imp.finditer(text)):
                    used = True
                    break
            if not used:
                self.add(
                    "L017",
                    mod,
                    "どこからも import されていません（src・scripts・tests・jobs）。使わないなら消すか legacy/ へ",
                    "warn",
                )

    def stray_files(self) -> None:
        c = self.lab["check"]
        for d in [*c["code_dirs"], "configs", "docs", "figspecs", "prompts", "literature"]:
            base = self.root / d
            for p in walk_files(base) if base.is_dir() else []:
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
        return _load_schema(name)

    def runs_meta(self) -> None:
        import jsonschema

        from labkit.paths import runs_root

        base = runs_root(self.root)
        if not base.is_dir():
            return
        schema = self._schema("run_meta.schema.json")
        pinned = pinned_version(self.root)
        stale: dict[tuple[str, str], list] = {}  # (版, 実行環境) → [件数, 最初の run]
        for d in sorted(base.iterdir()):
            if not d.is_dir():
                if d.name != ".gitkeep":
                    self.add("L020", d, "runs/ 直下には run ディレクトリだけを置く")
                continue
            mf = d / "meta.json"
            if not mf.is_file():
                self.add(
                    "L020",
                    d,
                    "meta.json がありません（開始直後に止められた殻なら "
                    f"`labkit runs mark {d.name} --to interrupted --reason ...` で記録する。Claude が実行してよい）",
                )
                continue
            try:
                meta = read_json(mf)
                _validate(meta, schema)
            except (json.JSONDecodeError, jsonschema.ValidationError) as e:
                self.add("L020", mf, f"スキーマ違反: {getattr(e, 'message', e)}")
                continue
            if pinned and meta.get("labkit_version") != pinned[0] and after(meta.get("created"), pinned[1]):
                key = (str(meta.get("labkit_version")), (meta.get("command") or ["?"])[0] or "?")
                stale.setdefault(key, [0, d.name])[0] += 1
            self._l024(d, meta)
            self._l021(d, meta)
            self._l027_run(d, meta)
        for (ver, py), (count, first) in stale.items():
            self.add(
                "L023",
                base,
                f"{count} 件の run が labkit {ver} で実行されている（プロジェクトの固定版は {pinned[0]}。例: {first}）。"
                f"実行環境 {py} を `uv sync --reinstall-package labkit` で揃える",
                "warn",
            )

    def _l024(self, d: Path, meta: dict) -> None:
        if meta["status"] == "finished" and meta.get("prediction") and not meta.get("prediction_result"):
            self.add(
                "L024",
                d,
                f"予想を書いた run の判定がありません。`labkit runs verdict {d.name} --say hit|miss|partial --note ...`"
                "（表形式の予想は run の終了時に自動で判定される）",
                "warn",
            )
        res = meta.get("prediction_result") or {}
        if meta["status"] == "finished" and res.get("verdict") == "undeterminable" and not meta.get("archived"):
            pred = meta.get("prediction") if isinstance(meta.get("prediction"), dict) else {}
            keys = ", ".join(str(c.get("key")) for c in (pred.get("claims") or [])[:5])
            self.add(
                "L024",
                d,
                f"予想を判定できなかった（予想の key が metrics に無い: {keys or res.get('error', '?')}）。当たりも外れも残らない予想は予想にならない。"
                f"次からは entry が返す指標名と `[[prediction.claims]]` の key を合わせる。この run は `labkit runs verdict {d.name} --say hit|miss|partial --note ...`",
                "warn",
            )

    def _l027_run(self, d: Path, meta: dict) -> None:
        """[compare] を宣言した finished の run の比較を、凍結した成果物から計算し直す."""
        from labkit.compare import COMPARISON_FILE, is_legacy, run_status

        if meta["status"] != "finished" or meta.get("archived") or is_legacy(meta):
            return  # legacy（labkit < 2.2.0）の run は比較の run ではない（設定の compare という表は別の意味）

        if not (d / "config.json").is_file() or not (
            (d / COMPARISON_FILE).exists() or '"compare"' in (d / "config.json").read_text(encoding="utf-8")
        ):
            return
        st = run_status(d, meta, self.lab)
        for a in st["author_excluded"]:
            self.add(
                "L027",
                d,
                f"対象外 {a} は著者の宣言だけ（lab.toml の [compare.capability] に無い）。人間が lab.toml に登録すると独立した宣言になる",
                "warn",
            )
        if probs := st["problems"]:
            self.add(
                "L027",
                d,
                "比較の条件がそろっていない（ceteris paribus）: "
                + "; ".join(probs[:5])
                + f"。結果にしないなら `labkit runs archive {d.name} --reason ...`",
            )

    def _l021(self, d: Path, meta: dict) -> None:
        if meta["status"] == "running":
            hb = d / "heartbeat"
            age = ""
            if hb.is_file():
                import datetime as _dt

                secs = (_dt.datetime.now() - _dt.datetime.fromtimestamp(hb.stat().st_mtime)).total_seconds()
                if secs < 600:  # 記録が続いている run は実行中。異常終了の疑いがあるものだけ知らせる
                    return
                age = f"最後の記録から {secs / 3600:.1f} 時間"
            self.add(
                "L021",
                d,
                f"status=running のまま（{age or '実行中か異常終了'}）。終わっているなら `labkit runs mark {d.name} --to failed --reason ...`",
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
                    _validate(read_json(sc), schema)
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
            for i, e in enumerate(r.errors):
                hint = (
                    "（lab-reviewer の記録でなければ docs/reviews/ ではなく docs/reports/ などに置く）"
                    if i == 0
                    else ""
                )
                self.add("L035", r.path, e + hint)
            for w in r.warnings:
                self.add("L035", r.path, w, "warn")

    # ---- 報告と実データの照合 ----
    def citations(self) -> None:
        from labkit.claims import AXIS_RE, CLAIMS_FILE, ROW_RE
        from labkit.compare import arm_labels, cross_run_problem, evidence_problems, key_problem, run_status, strip_arms

        runs = run_index(self.root)
        undeclared_sev = self.lab["check"]["undeclared_citation"]
        status_cache: dict[str, dict] = {}
        cache: dict[str, dict] = {}
        dirty_sev = self.lab["check"]["dirty_citation"]
        archived_sev = self.lab["check"]["archived_citation"]
        devlog_dir = self.root / self.lab["devlog"]["dir"]
        history = [h.rstrip("/") + "/" for h in self.lab["check"]["history_docs"]]
        reviews_dir = self.root / "docs/reviews"

        def metrics(rid: str) -> dict:
            if rid not in cache:
                mf = runs[rid]["_dir"] / "metrics.json"
                try:
                    cache[rid] = read_json(mf) if mf.is_file() else {}
                except json.JSONDecodeError:
                    cache[rid] = {}
            return cache[rid]

        # 同じ文書が多数の run を何十回も引用するので、状態の指摘は (文書, 種類) ごとに 1 件にまとめる（最初の行、run 数、箇所数）
        agg: dict[tuple[str, str], list] = {}
        # 文書ごと（段落・表・本文を区別しない）の引用 (run, 指標, 行) と axis=<鍵>。同じ指標（腕を名指す語を除いて同じ指標も）を
        # 2 つ以上の run から引く文書は、実験間の比較として照合する
        docs: dict[str, dict] = {}

        # 台帳の open な主張 → 根拠の欄の引用 (run, 指標)。文書の行がこの主張の ID を書けば、行の並置は台帳の関門を通ったとみなす
        ledger: dict[str, set] = {}
        cf = self.root / CLAIMS_FILE
        for ln in cf.read_text(encoding="utf-8", errors="replace").splitlines() if cf.is_file() else []:
            if (r := ROW_RE.match(ln)) and r.group(5) == "open":
                ledger[r.group(1)] = {(c.group("run"), c.group("key")) for c in CITE_RE.finditer(r.group(4))}

        def juxtaposed(line: str, cites: list[tuple[str, str]]) -> str:
            """行の並置（警告）: 2 つ以上の run の値、または 1 つの matched な比較の keys ではない同じ run の 2 つ以上の値."""
            keys: dict[str, set] = {}
            for rid, key in cites:
                keys.setdefault(rid, set()).add(key)
            within = []
            for rid, ks in keys.items():
                st = status_cache[rid]
                if len(ks) > 1 and not (ks <= st["matched_keys"] and len({st["owner"][k] for k in ks}) == 1):
                    within.append(f"run {rid} の {sorted(ks)}")
            cross = len(keys) > 1
            if not (cross or within):
                return ""
            if any(set(cites) <= ledger.get(cid, set()) for cid in CLAIM_ID_RE.findall(line)):
                return ""
            if not within and any(not cross_run_problem(runs, list(keys), a) for a in AXIS_RE.findall(line)):
                return ""
            what = "・".join(([f"{len(keys)} 個の run の値"] if cross else []) + within)
            return (
                f"1 行に {what} を並べている（比較に見える）。比較は台帳を通す: `labkit claim add` が 1 軸だけの違いを確かめる。"
                "通した主張の ID（C001）を同じ行に書くか、run をまたぐだけなら同じ行に axis=<鍵> を書く。"
                "文書の並置は文の意味を機械が読めないので警告だけ（残る危険。docs/harness.md）"
            )

        def note(doc: str, rid: str, kind: str, n: int, msg: str, sev: str, code: str = "L032") -> None:
            if sev == "off":
                return
            a = agg.setdefault((doc, kind), [n, set(), 0, msg, sev, code])
            a[1].add(rid)
            a[2] += 1

        for p, n, line, section in doc_lines(self.root, self.lab):
            is_devlog = p.parent == devlog_dir
            doc = p.relative_to(self.root).as_posix()
            # 履歴の文書（書いた時点の記録。後の規則に合わせて書き換えない）では L027・L032 の引用の指摘を警告にする
            is_history = is_devlog or any(doc.startswith(h) for h in history)
            is_claims = p == self.root / CLAIMS_FILE
            where = f"{doc}:{n}"
            dd = docs.setdefault(doc, {"cites": [], "axes": [], "history": is_history})
            if not is_claims and p.parent != reviews_dir:
                dd["axes"] += [a for a in AXIS_RE.findall(line) if a not in dd["axes"]]
            row = ROW_RE.match(line) if is_claims else None
            if row and row.group(5) == "retracted":
                continue  # 撤回済みの主張は履歴（根拠が崩れたことは撤回の理由に書いてある）。状態の列で判定する
            if row and row.group(5) == "open":
                cells = " ".join((row.group(3), row.group(4), row.group(6)))  # 本文・根拠・備考のすべての引用
                cites = [(m.group("run"), m.group("key")) for m in CITE_RE.finditer(cells)]
                axis = (AXIS_RE.search(row.group(4)) or [None, None])[1]
                warns: list[str] = []
                for why in evidence_problems(runs, self.lab, cites, axis, warns):
                    self.add("L027", where, f"{row.group(1)} の根拠: {why}（比較は 1 軸だけを変える。既定で拒否）")
                for why in warns:
                    self.add("L027", where, f"{row.group(1)} の根拠: {why}", "warn")
            for rid in set(RUN_ID_RE.findall(line)):
                if rid not in runs:
                    self.add("L032", where, f"run {rid} が runs/ にありません（HPC の run なら meta.json を同期する）")
                    continue
                meta = runs[rid]
                if meta.get("status") is None:
                    self.add("L032", where, f"run {rid} に meta.json がありません")
                    continue
                if meta.get("status") != "finished":
                    note(
                        doc,
                        rid,
                        "status",
                        n,
                        f"run {rid} は status={meta.get('status')}（結果として引用しない）",
                        "warn",
                    )
                if (meta.get("labkit_source") or {}).get("mode") == "link":
                    note(doc, rid, "link", n, f"run {rid} は link 中の labkit で実行（正式版の結果ではない）", "warn")
                if meta.get("archived"):
                    note(
                        doc,
                        rid,
                        "archived",
                        n,
                        f"run {rid} は退避済み（labkit runs archive）。根拠にするなら退避を取り消す",
                        "warn",
                    )
                if (meta.get("git") or {}).get("dirty") and p.parent != reviews_dir:
                    msg = f"run {rid} は dirty（未コミットの差分あり）。結果として引用するなら commit して clean に再実行する"
                    note(doc, rid, "dirty", n, msg, dirty_sev)
            rest = line
            line_cites: list[tuple[str, str]] = []
            for m in CITE_RE.finditer(line):
                rest = rest.replace(m.group(0), " ")
                rid, key, num = m.group("run"), m.group("key"), m.group("num")
                if rid not in runs or runs[rid].get("status") is None:
                    continue
                if runs[rid].get("archived"):
                    msg = f"run {rid} は退避済み（labkit runs archive）の数値を引用している。退避した結果は根拠にしない"
                    # 開発ログは履歴（書き換えない）なので警告。他の文書・台帳は check.archived_citation
                    sev = "warn" if is_history and archived_sev == "error" else archived_sev
                    note(doc, rid, "archived-cite", n, msg, sev)
                if not is_claims and p.parent != reviews_dir:
                    dd["cites"].append((rid, key, n))
                    line_cites.append((rid, key))
                    st = status_cache.setdefault(rid, run_status(runs[rid]["_dir"], runs[rid], self.lab))
                    kind, why = key_problem(st, key)
                    if (
                        kind == "legacy"
                    ):  # 1 つの値の引用は警告（並べた値・run をまたぐ同じ指標は下の照合が error にする）
                        note(doc, rid, "legacy", n, f"run {rid}: {why}", "warn", "L027")
                    elif kind in ("unmatched", "undeclared") and not is_history:
                        self.add("L027", where, f"run {rid}: {why}（比較は 1 軸だけを変える。既定で拒否）")
                    elif kind == "unmatched":
                        note(doc, rid, "unmatched", n, f"run {rid}: {why}", "warn", "L027")
                    elif kind == "undeclared":
                        note(doc, rid, "undeclared", n, f"run {rid}: {why}", undeclared_sev, "L027")
                vals = metrics(rid)
                if key not in vals:
                    self.add("L033", where, f"run {rid} の metrics.json に {key} がありません")
                elif not num_matches(num, vals[key]) and not (
                    m.group("unit") == "%" and num_matches(num, vals[key] * 100)
                ):  # % は 100 倍の表示を許す
                    self.add(
                        "L033", where, f"{num} は run {rid} の {key}={vals[key]} と一致しません（表示桁で丸めて比較）"
                    )
            if not is_devlog and (why := juxtaposed(line, line_cites)):
                self.add("L027", where, why, "warn")
            results = (is_devlog and section == RESULTS_HEADING) or is_claims
            if results and not line.lstrip().startswith(("#", "<!--")) and not CITE_RE.search(line):
                rest = RUN_ID_RE.sub(" ", rest)
                rest = re.sub(r"\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}(?::\d{2})?", " ", rest)
                if is_devlog and MEASURE_RE.search(rest):
                    self.add(
                        "L034",
                        where,
                        "結果の数値に引用がありません。`labkit cite <run_id> <key>` の `値 [run:<id>:<key>]` を貼る（run に無い量なら metrics に記録する）",
                        "warn",
                    )
            if results and re.search(r"(?<![\w/])scratch/", line):
                self.add(
                    "L038",
                    where,
                    "scratch/ のファイルは検証できません。根拠にするなら src に entry を書いて commit し `labkit run` の run を引用する",
                    "warn",
                )
        for doc, dd in docs.items():
            labels = [
                t for rid in {r for r, _, _ in dd["cites"]} for t in arm_labels(status_cache[rid]["cfg"]).values()
            ]
            groups: dict[str, list] = {}
            for rid, key, n in dd["cites"]:
                groups.setdefault(strip_arms(key, labels) or key, []).append((rid, n))
            for key, cs in groups.items():
                rids = sorted({r for r, _ in cs})
                if len(rids) < 2:
                    continue
                whys = [cross_run_problem(runs, rids, a) for a in dd["axes"] or [None]]
                if all(whys):
                    msg = (
                        f"文書の指標 {key!r} の引用が run をまたぐ: {whys[0]}（文書に axis=<設定の鍵> を書き、"
                        "軸以外が同一の run だけを並べる。段落・表を分けても同じ文書なら比較）"
                    )
                    if dd["history"]:
                        note(doc, "", "cross-run", cs[0][1], msg, undeclared_sev, "L027")
                    else:
                        self.add("L027", f"{doc}:{cs[0][1]}", msg)
        for (doc, _), (first, rids, count, msg, sev, code) in agg.items():
            more = f"（この文書で {len(rids)} run・{count} 箇所）" if count > 1 else ""
            self.add(code, f"{doc}:{first}", msg + more, sev)

    def claims_ledger(self) -> None:
        from labkit.claims import check_claims

        for code, where, msg, sev in check_claims(self.root, self.lab):
            self.add(code, where, msg, sev)

    def state_file(self) -> None:
        """L037: state.md は「今」だけを持つ。H1 が 2 つ以上・同じ H2 が 2 回以上は積層（旧版は git log -p にある）."""
        conf = self.lab["state"]
        p = self.root / conf["file"]
        if not p.is_file():
            return
        text = p.read_text(encoding="utf-8", errors="replace")
        body = strip_fences(text)  # コードブロック内の # はコメント
        h1 = re.findall(r"^#\s+\S", body, re.M)
        h2 = [m.group(1).strip() for m in re.finditer(r"^##\s+(.+?)\s*$", body, re.M)]
        dup = sorted({h for h in h2 if h2.count(h) > 1})
        hint = "（古い節は消す。履歴は `git log -p` と prompts/goal_v<N>.md にある）"
        if len(h1) > 1:
            self.add("L037", p, f"H1（# ）が {len(h1)} 個あります。state は 1 つの現在だけを書く{hint}")
        if dup:
            self.add("L037", p, f"同じ H2 が複数回あります: {dup}{hint}")
        n = sum(1 for ln in text.splitlines() if ln.strip())
        if n > int(conf["max_lines"]):
            self.add(
                "L037", p, f"{n} 行（上限 {conf['max_lines']}）。拍ごとに該当欄を上書きし、積み上げない{hint}", "warn"
            )

    def prompts_current(self) -> None:
        from labkit.beat import check_current

        for code, where, msg in check_current(self.root):
            self.add(code, where, msg, "warn")

    def focus_ledgers(self) -> None:
        from labkit.focus import check as focus_check

        for code, where, msg, sev in focus_check(self.root):
            self.add(code, where, msg, sev)

    def literature(self) -> None:
        from labkit.literature import check_literature

        for code, where, msg, *sev in check_literature(self.root, self.lab):
            self.add(code, where, msg, sev[0] if sev else "error")


def count_code_lines(path: Path) -> int:
    """空行を除いた行数（L018 と開発ログのコード量の行で使う）."""
    return sum(1 for ln in path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip())


def after(t: str | None, ref: str) -> bool:
    """ISO 8601 の時刻 t が ref 以降か（時差が違っても比べられるよう datetime で比較。読めなければ False）."""
    import datetime as _dt

    try:
        return _dt.datetime.fromisoformat(str(t)) >= _dt.datetime.fromisoformat(ref)
    except (TypeError, ValueError):
        return False


def pinned_version(root: Path) -> tuple[str, str] | None:
    """(pyproject が固定する labkit の版, その固定を書いた commit の日時)。固定が無ければ None。L023 の基準."""
    from labkit._util import git
    from labkit.standards import status

    if not (root / "pyproject.toml").is_file():
        return None
    st = status(root)
    if st.mode != "release" or not st.ref:
        return None
    when = git(root, "log", "-1", "--format=%cI", "--", "pyproject.toml") or ""
    return st.ref.lstrip("v"), when


def run_index(root: Path) -> dict[str, dict]:
    """runs/ の {run_id: meta}（meta.json が無い・壊れている run は {} に "_dir" だけ）。"_dir" に run のパス."""
    from labkit.paths import runs_root

    base = runs_root(root)
    out: dict[str, dict] = {}
    for d in base.iterdir() if base.is_dir() else []:
        if not d.is_dir():
            continue
        try:
            meta = read_json(d / "meta.json") if (d / "meta.json").is_file() else {}
        except json.JSONDecodeError:
            meta = {}
        out[d.name] = {**meta, "_dir": d}
    return out


def doc_lines(root: Path, lab: dict):
    """照合する文書（check.claim_docs）の (path, 行番号, 行, 節) を順に返す。自動ブロック・DIGEST・README は飛ばす."""
    from labkit.devlog import AUTO_END, AUTO_START

    skip = {root / lab["digest"]["file"]}
    seen: set[Path] = set()
    for pat in lab["check"]["claim_docs"]:
        for p in sorted(root.glob(pat)):
            if p in seen or not p.is_file() or p.name == "README.md" or p in skip or set(p.parts) & SKIP_DIRS:
                continue
            seen.add(p)
            section, auto = None, False
            for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if AUTO_START in line:
                    auto = True
                if auto:
                    auto = AUTO_END not in line
                    continue
                if m := re.match(r"^##\s+(.+?)\s*$", line):
                    section = m.group(1)
                yield p, n, line, section


def cited_run_ids(root: Path, lab: dict | None = None) -> dict[str, list[str]]:
    """文書と拍の記録が引用している run ID → 引用箇所（path:line）。退避の候補（--uncited）と DIGEST が使う."""
    from labkit.beat import BEATS_DIR

    lab = lab or load_lab(root)
    out: dict[str, list[str]] = {}
    for p, n, line, _ in doc_lines(root, lab):
        for rid in set(RUN_ID_RE.findall(line)):
            out.setdefault(rid, []).append(f"{p.relative_to(root).as_posix()}:{n}")
    for p in sorted((root / BEATS_DIR).glob("*.jsonl")) if (root / BEATS_DIR).is_dir() else []:
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for rid in set(RUN_ID_RE.findall(line)):
                out.setdefault(rid, []).append(f"{p.relative_to(root).as_posix()}:{n}")
    return out


def strip_fences(text: str) -> str:
    """Markdown のコードブロック（``` / ~~~）の中身を除く（見出しの数え上げ用）."""
    out, fence = [], None
    for ln in text.splitlines():
        s = ln.lstrip()
        if fence is None and s.startswith(("```", "~~~")):
            fence = s[:3]
        elif fence is not None and s.startswith(fence):
            fence = None
        elif fence is None:
            out.append(ln)
    return "\n".join(out)


def num_matches(text: str, value) -> bool:
    """表示されている桁数で丸めて一致するか（"12.3" と 12.34 → True、"12.30" と 12.34 → False）。Unicode のマイナスも受ける."""
    text = text.replace("−", "-")
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
