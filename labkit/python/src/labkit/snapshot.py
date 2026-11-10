"""HEAD の写しから run を始める（labkit run --head）.

`runs.require_clean` のもとでは、作業ツリーに未コミットの変更があると run が始まらない。別の作業の途中でも commit 済みの
コードで正式な run を回せるよう、HEAD の src/・configs/ を `.lab/snapshots/<commit>/` に展開し、コードと設定をそこから読む。
実行されるコードは commit そのものなので、run は clean として記録できる（meta.json の git.snapshot = true）。

    .lab/snapshots/<commit 12 桁>/src, configs    git archive の展開（git 管理外。古い写しは PRUNE_DAYS 日で消す）

プロジェクトの外には何も作らない（worktree や clone を外に作って待つ運用の置き換え）。
限界: entry が起動する別プロセス（scripts/ の実行など）は作業ツリーのコードを使う。写しから読むのは entry の import と設定だけ。
"""

from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
import time
from pathlib import Path

from labkit._util import git, git_info

SNAPSHOT_DIR = ".lab/snapshots"
PARTS = ("src", "configs")  # 計算の結果を決めるもの: コードと設定
PRUNE_DAYS = 7
IGNORE_LINE = "snapshots/"


def _ignore(root: Path) -> None:
    """`.lab/.gitignore` に snapshots/ を足す（既にあるプロジェクトの .gitignore には無い）."""
    from labkit.state import lab_dir

    gi = lab_dir(root) / ".gitignore"
    text = gi.read_text(encoding="utf-8") if gi.is_file() else ""
    if IGNORE_LINE not in text.splitlines():
        gi.write_text(text.rstrip("\n") + f"\n{IGNORE_LINE}\n", encoding="utf-8", newline="\n")


def _prune(base: Path, keep: Path) -> None:
    limit = time.time() - PRUNE_DAYS * 86400
    for d in base.iterdir() if base.is_dir() else []:
        if d != keep and d.is_dir() and d.stat().st_mtime < limit:
            shutil.rmtree(d, ignore_errors=True)


def head_snapshot(root: Path) -> tuple[Path, dict]:
    """(写しのディレクトリ, run に記録する git の情報)。写しは commit ごとに 1 つで、あれば使い回す."""
    info = git_info(root)
    if info is None:
        raise ValueError("--head は git のリポジトリで使います（HEAD の commit の写しから実行する）")
    commit = info["commit"]
    _ignore(root)
    base = root / SNAPSHOT_DIR
    dest = base / commit[:12]
    if not (dest / ".complete").is_file():
        have = set((git(root, "ls-tree", "--name-only", commit) or "").splitlines())
        parts = [p for p in PARTS if p in have]
        if "src" not in parts:
            raise ValueError(f"HEAD（{commit[:7]}）に src/ がありません。entry のコードを commit してから実行する")
        tar = subprocess.run(["git", "archive", "--format=tar", commit, "--", *parts], cwd=root, capture_output=True)
        if tar.returncode != 0:
            raise ValueError(f"HEAD の写しを作れません: {tar.stderr.decode('utf-8', 'replace').strip()}")
        tmp = base / f".tmp-{commit[:12]}-{time.time_ns()}"
        tmp.mkdir(parents=True)
        with tarfile.open(fileobj=io.BytesIO(tar.stdout)) as tf:
            tf.extractall(tmp, filter="data")
        (tmp / ".complete").write_text(commit + "\n", encoding="utf-8")
        try:
            tmp.rename(dest)
        except OSError:  # 同時に始まった別の run が先に作った
            shutil.rmtree(tmp, ignore_errors=True)
            if not (dest / ".complete").is_file():
                raise
    dest.touch()  # 使っている写しは消さない
    _prune(base, dest)
    return dest, {
        "commit": commit,
        "branch": info["branch"],
        "dirty": False,  # 実行するコードと設定は commit そのもの
        "snapshot": True,
        "worktree_dirty_paths": info.get("dirty_paths", []),  # 写しに入っていない作業中の変更（透明性のため残す）
    }


def assert_from(fn, snap: Path, entry: str) -> None:
    """entry の関数が写しから import されたことを確かめる（editable install の finder が作業ツリーを先に返すと、
    commit と違うコードを clean な run として記録してしまう）."""
    import inspect

    src = Path(inspect.getsourcefile(fn) or "").resolve()
    if not src.is_relative_to(snap.resolve()):
        raise ValueError(
            f"entry {entry!r} が HEAD の写し（{snap}）ではなく {src} から import されました。"
            "この環境では --head を使えません（commit してから `labkit run` を実行する）"
        )
