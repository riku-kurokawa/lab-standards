"""キュー（人間への連絡）・flow（チェックリスト）・ミラー・開発ログの自動ブロック・standards link."""

import json

import pytest

from labkit import Run, flow, mirror, state
from labkit.devlog import section_bodies, update

from .conftest import git


def test_queue_is_one_way(project):
    """v2.0.0: queue は人間への連絡だけ（返事は待たない）。承認・回答・委任は無い."""
    q = state.ask_question(project, "lz4 か zstd か", options=["lz4", "zstd"], assumed="zstd（互換）")
    assert q["id"] == "Q001" and state.pending_summary(project)["open_questions"]
    state.mark_done(project, "Q001")
    assert not state.pending_summary(project)["open_questions"]
    for gone in ("approve", "reject", "answer_question", "add_delegation", "find_delegation", "request"):
        assert not hasattr(state, gone), gone
    assert (project / ".lab" / ".gitignore").read_text(encoding="utf-8").startswith("#")


def test_migrate_flow_checklist(git_project, tmp_path):
    p = git_project
    st = flow.start(p, "migrate")
    assert st["stage"] == "freeze" and "forbid" not in st["stages"][0]
    with pytest.raises(SystemExit, match="pre-migration"):
        flow.advance(p, "migrate")
    git(p, "tag", "pre-migration")
    with pytest.raises(SystemExit, match="写し"):
        flow.advance(p, "migrate")
    (p / "data" / "raw" / "r.bin").write_bytes(b"123")
    dest = tmp_path.parent / f"{tmp_path.name}-mirror"
    rec = mirror.push(p, to=str(dest), paths=["data"], progress=lambda *_: None)
    assert rec["copied"] == 1 and (dest / "t" / "data" / "raw" / "r.bin").read_bytes() == b"123"
    assert mirror.push(p, to=str(dest), paths=["data"], progress=lambda *_: None)["copied"] == 0  # 差分なし
    st, _ = flow.advance(p, "migrate")
    assert st["stage"] == "inventory"
    (p / "scratch" / "migration-inventory.csv").write_text(
        "old_path,kind,new_path,size,note\n", encoding="utf-8", newline="\n"
    )
    st, _ = flow.advance(p, "migrate")
    assert st["stage"] == "apply-template" and "via" not in st["history"][-1]
    assert "mode" in flow.unmet(p, st)[-1]  # lab_mode=warn 未達
    from labkit.hook import handle

    from .test_hook import write

    assert handle("pretool", write("lab.toml", p))[0] == 0  # 段階の仕事なので lab.toml を書ける（完全自律の移行）
    assert handle("pretool", write(".copier-answers.yml", p))[0] == 2
    (p / "lab.toml").write_text('[lab]\nproject = "t"\n[check]\nmode = "warn"\n', encoding="utf-8", newline="\n")
    (p / ".copier-answers.yml").write_text("_commit: v1.0.0\n", encoding="utf-8", newline="\n")
    st, _ = flow.advance(p, "migrate")
    assert st["stage"] == "raw-data" and "freeze" in flow.unmet(p, st)[0]
    assert handle("pretool", write("lab.toml", p))[0] == 2  # 段階を過ぎたら規約ファイルに戻る
    from labkit.rawdata import freeze

    freeze(root=p, progress=lambda *_: None)
    st, _ = flow.advance(p, "migrate")
    assert st["stage"] == "code"
    st, _ = flow.advance(p, "migrate")
    assert st["stage"] == "reproduce"
    with Run("repro", {"seed": 0}, root=p):
        pass
    missing = flow.unmet(p, st)
    assert len(missing) == 1 and "pass 記録" in missing[0]
    head = git(p, "rev-parse", "HEAD")
    (p / "docs" / "reviews").mkdir()
    (p / "docs" / "reviews" / "2026-11-02_migrate_reproduce.md").write_text(
        f"---\nreviewer: lab-reviewer\nflow: migrate\nstage: reproduce\ncommit: {head}\nverdict: pass\nfindings: []\n---\n",
        encoding="utf-8",
        newline="\n",
    )
    st, _ = flow.advance(p, "migrate")
    assert st["stage"] == "strict"
    (p / "lab.toml").write_text('[lab]\nproject = "t"\n', encoding="utf-8", newline="\n")
    st, _ = flow.advance(p, "migrate")
    assert st["stage"] == "done" and st["status"] == "finished" and flow.active_flows(p) == []
    # pull は写しから戻す
    (p / "data" / "raw" / "r.bin").chmod(0o644)
    (p / "data" / "raw" / "r.bin").unlink()
    assert mirror.pull(p, to=str(dest), progress=lambda *_: None) == 1


def test_devlog_auto_block_and_sections(git_project):
    p = git_project
    (p / "src" / "n.py").write_text("x = 1\n", encoding="utf-8", newline="\n")
    (p / ".gitignore").write_text("/runs/*\n", encoding="utf-8", newline="\n")  # 追跡済みファイルの変更（" M" の行）
    (p / "docs" / "note.md").write_text("x\n", encoding="utf-8", newline="\n")  # 文書だけの変更は dirty に数えない
    with Run("today", {"seed": 0}, root=p) as run:
        pass
    assert run.git["dirty"] and run.git["dirty_paths"] == [".gitignore", "src/n.py"]
    f = update(p)
    text = f.read_text(encoding="utf-8")
    assert "未コミット: .gitignore" in text and "未コミット: src/n.py" in text and "today" in text
    assert text.count("<!-- labkit:auto -->") == 1 and "- コード量: src 1 行（+1、1 ファイル）" in text
    text = text.replace("## 目的\n", "## 目的\n\n目的 A\n")
    f.write_text(text, encoding="utf-8", newline="\n")
    update(p)  # 自動ブロックだけ更新され、人が書いた部分は残る
    bodies = section_bodies(f.read_text(encoding="utf-8"))
    assert bodies["目的"].strip() == "目的 A" and bodies["判断と理由"] == "" and "変更ファイル（自動" not in bodies


def test_standards_status_link_unlink(project):
    from labkit import standards as std

    (project / "pyproject.toml").write_text(
        '[tool.uv.sources]\nlabkit = { git = "https://github.com/o/lab-standards.git", tag = "v1.0.0", subdirectory = "labkit/python" }\n',
        encoding="utf-8",
        newline="\n",
    )
    (project / ".copier-answers.yml").write_text(
        "_commit: v1.0.0\nstandards_repo: o/lab-standards\n", encoding="utf-8", newline="\n"
    )
    assert std.status(project).mode == "release"
    dev = project / "dev"
    (dev / "labkit" / "python").mkdir(parents=True)
    (dev / "copier.yml").write_text("", encoding="utf-8")
    (dev / "labkit" / "python" / "pyproject.toml").write_text("", encoding="utf-8")
    std.link(str(dev), root=project, do_sync=False)
    assert std.status(project).mode == "link"
    from labkit.check import run_check

    assert "L050" in {i.code for i in run_check(root=project)[0]}
    std.unlink("v1.0.0", root=project, do_sync=False)
    assert std.status(project).mode == "release" and std.status(project).ref == "v1.0.0"
    with pytest.raises(SystemExit):
        std.unlink("latest", root=project, do_sync=False)


def test_run_meta_schema_accepts_new_fields(project):
    from labkit.check import run_check

    with Run("s", {"seed": 1}, root=project) as run:
        run.log_metric("a", 1.0)
    meta = json.loads((run.dir / "meta.json").read_text(encoding="utf-8"))
    assert {"env", "pid", "paths", "seed"} <= set(meta)
    assert not [i for i in run_check(root=project)[0] if i.code == "L020"]
