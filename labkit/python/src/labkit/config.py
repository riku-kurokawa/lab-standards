"""プロジェクトルートと lab.toml（規約の唯一の設定源）の読み込み."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from labkit._labstate import DEFAULTS, deep_merge  # noqa: F401  （DEFAULTS は他モジュールが config 経由で参照）


def find_root(start: str | os.PathLike | None = None) -> Path:
    """lab.toml を含むディレクトリを上方向に探す（環境変数 LAB_PROJECT_ROOT が優先）."""
    env = os.environ.get("LAB_PROJECT_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    p = Path(start or Path.cwd()).resolve()
    if p.is_file():
        p = p.parent
    for d in (p, *p.parents):
        if (d / "lab.toml").is_file():
            return d
    raise FileNotFoundError(
        f"lab.toml が {p} から上位に見つかりません。lab-standards で生成したプロジェクト内で実行してください。"
    )


def read_toml(path: str | os.PathLike) -> dict:
    """TOML を読む。文法エラーにはファイル名を付ける（tomllib の例外には位置しか無い）."""
    with open(path, "rb") as f:
        try:
            return tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"{path}: TOML の文法エラー: {e}") from e


def load_lab(root: str | os.PathLike | None = None) -> dict:
    r = Path(root) if root else find_root()
    return deep_merge(DEFAULTS, read_toml(r / "lab.toml"))
