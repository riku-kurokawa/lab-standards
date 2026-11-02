"""正本（runs/ と data/。git 管理外）の写しを機械の外に置く.

    labkit mirror push [--to <dest>] [--paths runs data ...]    # 差分だけコピー（削除はしない）
    labkit mirror pull [--to <dest>] [--paths ...]              # 写しから戻す（手元に無いか異なるものだけ）

dest の既定は configs/paths/<LAB_ENV>.toml の mirror_root。写し先に <プロジェクト名>/ を切り、その下に同じ相対パスで置く。
比較は size と mtime（--verify で sha256）。写し先には MIRROR.json（時刻・件数）、手元には .lab/mirror.json を残す。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from labkit._util import now_iso, read_json, sha256_file, write_json_atomic
from labkit.config import find_scope, load_lab

DEFAULT_PATHS = ("data", "runs")


def _dest(root: Path, to: str | None) -> Path:
    if to:
        return Path(to).expanduser()
    if (root / "lab.toml").is_file():
        from labkit.paths import load_paths

        mr = load_paths(root).get("mirror_root")
        if mr:
            return Path(mr)
    raise SystemExit("写し先が未設定です: --to <dest> を指定するか、configs/paths/<LAB_ENV>.toml に mirror_root を書く")


def _same(a: Path, b: Path, verify: bool) -> bool:
    if not b.exists():
        return False
    sa, sb = a.stat(), b.stat()
    if sa.st_size != sb.st_size:
        return False
    if verify:
        return sha256_file(a) == sha256_file(b)
    return abs(sa.st_mtime - sb.st_mtime) < 2


def _copy_tree(src_root: Path, dst_root: Path, paths: list[str], verify: bool, progress) -> tuple[int, int]:
    n = total = 0
    for rel in paths:
        src = src_root / rel
        if not src.exists():
            continue
        files = [src] if src.is_file() else sorted(p for p in src.rglob("*") if p.is_file())
        for p in files:
            q = dst_root / p.relative_to(src_root)
            if _same(p, q, verify):
                continue
            q.parent.mkdir(parents=True, exist_ok=True)
            progress(f"copy: {p.relative_to(src_root).as_posix()}")
            shutil.copy2(p, q)
            n += 1
            total += p.stat().st_size
    return n, total


def _project_name(root: Path) -> str:
    return (load_lab(root)["lab"]["project"] if (root / "lab.toml").is_file() else "") or root.name


def push(root: Path | None = None, to: str | None = None, paths: list[str] | None = None, verify=False, progress=print):
    sc = find_scope(root)
    root = sc[0] if sc else Path(root or ".").resolve()
    dest = _dest(root, to) / _project_name(root)
    dest.mkdir(parents=True, exist_ok=True)
    n, total = _copy_tree(root, dest, list(paths or DEFAULT_PATHS), verify, progress)
    rec = {
        "dest": str(dest),
        "pushed_at": now_iso(),
        "paths": list(paths or DEFAULT_PATHS),
        "copied": n,
        "bytes": total,
    }
    write_json_atomic(dest / "MIRROR.json", rec)
    from labkit.state import lab_dir

    write_json_atomic(lab_dir(root) / "mirror.json", rec)
    progress(f"{n} 件（{total / 1e9:.2f} GB）を {dest} に写しました")
    return rec


def pull(root: Path | None = None, to: str | None = None, paths: list[str] | None = None, verify=False, progress=print):
    sc = find_scope(root)
    root = sc[0] if sc else Path(root or ".").resolve()
    dest = _dest(root, to) / _project_name(root)
    if not (dest / "MIRROR.json").is_file():
        raise SystemExit(f"{dest} に写し（MIRROR.json）がありません")
    n, total = _copy_tree(dest, root, list(paths or read_json(dest / "MIRROR.json")["paths"]), verify, progress)
    progress(f"{n} 件（{total / 1e9:.2f} GB）を {dest} から戻しました")
    return n
