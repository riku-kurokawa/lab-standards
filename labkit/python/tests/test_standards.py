"""labkit standards link / unlink と L050."""

from pathlib import Path

import pytest

from labkit import standards as std
from labkit.check import run_check

PYPROJECT = """[project]
name = "p"
dependencies = ["labkit"]

[tool.uv.sources]
labkit = { git = "https://github.com/me/lab-standards.git", tag = "v0.1.0", subdirectory = "labkit/python" }
"""
JL = """name = "P"

[deps]
LabKit = "a7622db1-e488-467e-8923-aeb5b3c692de"

[sources]
LabKit = { url = "https://github.com/me/lab-standards.git", subdir = "labkit/julia/LabKit", rev = "v0.1.0" }
"""


@pytest.fixture
def dev(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("lab-standards")
    (d / "copier.yml").write_text("_subdirectory: template\n")
    (d / "labkit" / "python").mkdir(parents=True)
    (d / "labkit" / "python" / "pyproject.toml").write_text("[project]\nname='labkit'\n")
    (d / "labkit" / "julia" / "LabKit").mkdir(parents=True)
    return d


@pytest.fixture
def proj(project: Path) -> Path:
    (project / "pyproject.toml").write_text(PYPROJECT)
    (project / "jl").mkdir()
    (project / "jl" / "Project.toml").write_text(JL)
    (project / ".copier-answers.yml").write_text(
        "_commit: v0.1.0\nstandards_repo: me/lab-standards\nstandards_ref: v0.1.0\n"
    )
    return project


def test_status_release(proj):
    st = std.status(proj)
    assert (st.python_mode, st.python_ref) == ("release", "v0.1.0")
    assert (st.julia_mode, st.julia_ref) == ("release", "v0.1.0")
    assert not st.linked
    assert not [i for i in run_check()[0] if i.code == "L050"]


def test_link_unlink_roundtrip(proj, dev):
    st = std.link(str(dev), root=proj, do_sync=False)
    assert st.linked and st.python_ref.endswith("labkit/python") and st.julia_mode == "link"
    assert "editable = true" in (proj / "pyproject.toml").read_text()
    codes = [i for i in run_check()[0] if i.code == "L050"]
    assert len(codes) == 2
    assert not [i for i in run_check(ignore={"L050"})[0] if i.code == "L050"]
    st = std.unlink("v0.3.0", root=proj, do_sync=False)
    assert (st.python_mode, st.python_ref, st.julia_ref) == ("release", "v0.3.0", "v0.3.0")
    text = (proj / "pyproject.toml").read_text()
    assert 'dependencies = ["labkit"]' in text and 'subdirectory = "labkit/python"' in text


def test_unlink_requires_tag(proj):
    with pytest.raises(SystemExit):
        std.unlink("main", root=proj, do_sync=False)


def test_link_rejects_non_checkout(proj, tmp_path):
    with pytest.raises(SystemExit):
        std.link(str(tmp_path), root=proj, do_sync=False)


def test_run_records_labkit_source(project):
    import json

    from labkit import Run

    with Run("src") as run:
        pass
    src = json.loads((run.dir / "meta.json").read_text())["labkit_source"]
    # テストは本体チェックアウトから実行しているので link 扱いになる
    assert src["mode"] == "link" and (Path(src["path"]) / "copier.yml").exists()
