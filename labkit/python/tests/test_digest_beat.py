"""人間の入口（digest）、1 拍の入口（beat）、レビュー記録の 1 行要約、開発ログのコード量."""

import json

import pytest

from labkit import Run, beat, claims
from labkit.check import run_check
from labkit.devlog import section_bodies, update
from labkit.digest import build, staleness
from labkit.hook import handle
from labkit.reviews import load_review, open_reviews

from .conftest import git


def write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


def review(p, name, verdict, extra=""):
    stage = name.split("_")[2].split(".")[0]  # ファイル名の stage と揃える
    write(
        p / "docs" / "reviews" / name,
        f"---\nreviewer: lab-reviewer\nflow: adhoc\nstage: {stage}\ncommit: {'a' * 40}\nverdict: {verdict}\n{extra}"
        + ('findings:\n  - "must: a.py:1 x"\n  - "should: b.py:2 y"\n' if verdict != "pass" else "findings: []\n")
        + "---\n",
    )


def test_reviews_summary_resolves_and_open_list(project):
    p = project
    review(p, "2026-11-01_adhoc_review.md", "changes-requested")
    review(
        p,
        "2026-11-02_adhoc_review.md",
        "changes-requested",
        "summary: 草稿の下限に格子の不確かさが無い\nresolves: docs/reviews/2026-11-01_adhoc_review.md\n",
    )
    review(p, "2026-11-03_adhoc_plan.md", "pass", "summary: " + "長" * 121 + "\nresolves: docs/reviews/nope.md\n")
    review(
        p, "2026-11-04_adhoc_plan_2.md", "pass", 'summary: ""\n'
    )  # summary が空 → 警告（stage が違うので 11-02 は閉じない）
    got = [i for i in run_check(root=p)[0] if i.code == "L035"]
    assert sorted((i.severity, i.where) for i in got) == [  # 11-01 は summary のキーが無い古い記録なので警告しない
        ("error", "docs/reviews/2026-11-03_adhoc_plan.md"),
        ("warn", "docs/reviews/2026-11-03_adhoc_plan.md"),
        ("warn", "docs/reviews/2026-11-04_adhoc_plan_2.md"),
    ]
    assert [r.path.name for r in open_reviews(p)] == ["2026-11-02_adhoc_review.md"]  # 11-01 は 11-02 が resolves
    r = load_review(p / "docs" / "reviews" / "2026-11-02_adhoc_review.md")
    assert r.counts == (1, 1) and r.date == "2026-11-02"
    from labkit.reviews import template

    t = template("adhoc", "review", "a" * 40, resolves=r)
    assert "resolves: " in t and "| 1 | must: a.py:1 x | |" in t and "summary:" in t


def test_beat_start_end_and_devlog_block(git_project):
    p = git_project
    with pytest.raises(FileNotFoundError, match="current.toml"):
        beat.start(p)
    write(p / "prompts" / "goal_v1.md", "# 目標 v1\n\n## 究極目標\n\n法則を見つける\n\n## 基準\n\n7 項目\n")
    write(p / "prompts" / "beat_v1.md", "# 1 拍\n\n1. 状態\n")
    write(p / "prompts" / "goal_v2.md", "# 目標 v2\n")
    beat.ensure_current(p, "goal_v1.md", "beat_v1.md")
    l005 = [i for i in run_check(root=p)[0] if i.code == "L005"]
    assert len(l005) == 1 and "goal_v2.md" in l005[0].message and l005[0].severity == "warn"
    out = beat.start(p)
    assert (
        out.startswith("# 拍 1")
        and "## goal: prompts/goal_v1.md" in out
        and "法則を見つける" in out
        and "open な主張: 0" in out
    )
    rec = beat.end(p, predicted="e1 0.02", observed="0.05", decided="模型 B を捨てる", runs=["r1"])
    assert rec["beat"] == 1 and rec["time"]
    text = update(p).read_text(encoding="utf-8")
    assert "## 拍（自動" in text and "判断: 模型 B を捨てる" in text and "run: r1" in text
    assert "拍（自動" not in "".join(section_bodies(text))  # L030 の判定に干渉しない
    assert "模型 B を捨てる" in beat.log(p) and "拍 2" in beat.start(p)
    s = handle("session", {"cwd": str(p), "source": "compact"})[1]
    assert "goal goal_v1.md" in s and "最後の拍 1" in s and "法則を見つける" in s  # compact 後は目標の冒頭を原文で戻す
    s2 = handle("session", {"cwd": str(p)})[1]
    assert "法則を見つける" not in s2 and "無効のままの関門: runs.require_prediction / runs.require_clean" in s2


def test_beat_end_refuses_a_stall(git_project):
    p = git_project
    write(p / "prompts" / "goal_v1.md", "# 目標\n")
    write(p / "prompts" / "beat_v1.md", "# 1 拍\n")
    beat.ensure_current(p, "goal_v1.md", "beat_v1.md")
    idle = dict(predicted="変化なし", decided="止められた計算は人間の再開の指示まで起動しない")
    for k in (730, 730):
        beat.start(p)
        beat.end(p, observed=f"open {k}、計算は停止のまま", **idle)
    assert "停滞: 同じ判断・結果の拍が 2 回" in beat.start(p)
    with pytest.raises(ValueError, match="人間の停止ではありません"):
        beat.end(p, observed="open 729、計算は停止のまま", **idle)  # 数字の揺れは同じ判断
    rec = beat.end(p, observed="open 729、計算は停止のまま", stall_reason="実機の測定待ちで代替なし", **idle)
    assert rec["stall_reason"] and "**停滞**: 実機の測定待ち" in beat.log(p)
    beat.start(p)
    beat.end(p, observed="open 729、計算は停止のまま", runs=["r1"], **idle)  # run を出した拍は停滞でない
    beat.start(p)
    assert beat.end(p, observed="census を再開した", decided="メモリが戻ったので再開した")["beat"] == 5


def test_digest_builds_one_page(git_project):
    p = git_project
    pytest.importorskip("h5py")
    import numpy as np

    from labkit import runpath, save
    from labkit.viz import render

    assert "まだ無い" in staleness(p)
    pred = {"basis": "桁", "claims": [{"key": "snr_db", "range": [0, 5]}]}
    with Run("good", {"seed": 0, "prediction": pred, "report": {"noncomparative": ["snr_db"]}}) as run:
        run.log_metric("snr_db", 12.3)
        save(runpath(run, "s.h5"), {"t": np.arange(10.0), "x": np.sin(np.arange(10.0))})
    write(
        p / "figspecs" / "ts.toml",
        'template = "timeseries"\n[data]\nfile = "s.h5"\nx = "t"\ny = ["x"]\n[labels]\ntitle = "時系列"\n',
    )
    render(p / "figspecs" / "ts.toml", run_id=run.run_id)
    with pytest.raises(RuntimeError):
        with Run("bad", {"seed": 0}):
            raise RuntimeError("x")
    claims.add_claim(p, "SNR は 12 dB", [f"{run.run_id}:snr_db:dB:1"])
    review(p, "2026-11-05_adhoc_review.md", "changes-requested", "summary: 要修正 1\n")
    from labkit import state

    state.ask_question(p, "A か B か", options=["A", "B"], assumed="A")
    out = build(p, since="2000-01-01")
    text = out.read_text(encoding="utf-8")
    for head in (
        "## 主張",
        "## 予想と結果",
        "## run の収支",
        "## 新しい図",
        "## 未解消のレビュー",
        "## 人間への連絡（返事は待たずに進めている。新しい順）",
        "## labkit check",
        "コード量:",
    ):
        assert head in text, head
    # 人間の判断が要るものが先頭に来る: 外れた予想・新しい連絡。主張には根拠の run を生んだコード（entry か run 名）と commit
    top = text.split("## 先に見るもの")[1].split("## ")[0]
    assert "外れた予想 1 件" in top and "新しい連絡 1 件" in top
    assert "  - コード: `good` @ " in text
    assert (
        "C001" in text
        and "miss" in text
        and "failed 1" in text
        and "![時系列](docs/assets/digest/" in text
        and "要修正 1" in text
    )
    assert (p / "docs" / "assets" / "digest").is_dir() and len(text.splitlines()) < 120
    assert not [i for i in run_check(root=p)[0] if i.where.startswith("docs/DIGEST.md")]  # DIGEST は照合の対象外
    git(p, "add", "-A")
    git(p, "commit", "-q", "-m", "digest")
    assert staleness(p) is None


def test_code_volume_line(git_project):
    p = git_project
    write(p / "src" / "a.py", "x = 1\n\ny = 2\n")
    git(p, "add", "-A")
    git(p, "commit", "-q", "-m", "a")
    write(p / "src" / "a.py", "x = 1\n\ny = 2\nz = 3\n")
    text = update(p).read_text(encoding="utf-8")
    assert "- コード量: src 3 行（+3、1 ファイル）" in text and "300 行超 0 本" in text  # その日の増分（空行を除く）


def test_empty_project_digest_does_not_fail(project):
    out = build(project, since="2000-01-01")
    assert out.is_file() and "# DIGEST" in out.read_text(encoding="utf-8")
    assert json.loads(json.dumps({"ok": True}))


def test_digest_groups_misses_and_lists_code_to_review(git_project):
    """同じ根拠の外れは 1 行。src の変更は試験の有無つきで載る。撤回は理由つきで先頭に."""
    p = git_project
    base = git(p, "rev-parse", "HEAD")
    pred = {"basis": "同じ根拠", "claims": [{"key": "e", "range": [0, 1]}]}
    for k in range(3):
        with Run(f"arr-{k}", {"seed": k, "prediction": pred, "report": {"noncomparative": ["e"]}}) as run:
            run.log_metric("e", 5.0)
    write(p / "src" / "solver.py", "def f():\n    return 1\n")
    write(p / "src" / "plain.py", "def g():\n    return 2\n")
    write(p / "tests" / "test_solver.py", "def test_f():\n    assert True\n")
    git(p, "add", "-A")
    git(p, "commit", "-q", "-m", "code")
    c = claims.add_claim(p, "e は 5", [f"{run.run_id}:e"])
    claims.retract_claim(p, c["id"], "条件が違っていた")
    text = build(p, since=base).read_text(encoding="utf-8")
    assert "ほか 2 本" in text and text.count("✗ arr-") == 1
    assert "- `src/solver.py` +2 −0\n" in text and "- `src/plain.py` +2 −0 — **試験の変更なし**" in text
    assert "**撤回** C001" in text.split("## 主張")[0] and "理由: 条件が違っていた" in text


def test_beat_end_refreshes_stale_digest(git_project):
    """人間の入口は `beat end` が作り直す（「1 日 1 回作る」という規則に頼らない）."""
    p = git_project
    write(p / "prompts" / "goal_v1.md", "# 目標\n")
    write(p / "prompts" / "beat_v1.md", "# 1 拍\n")
    beat.ensure_current(p, "goal_v1.md", "beat_v1.md")
    beat.start(p)
    beat.end(p, decided="始めた")
    d = p / "docs" / "DIGEST.md"
    assert d.is_file()
    d.write_text("# DIGEST（2026-01-01 00:00、古い）\n", encoding="utf-8")
    beat.start(p)
    beat.end(p, decided="次に進めた", observed="x")
    assert "古い" not in d.read_text(encoding="utf-8")
    stamp = d.read_text(encoding="utf-8")
    beat.start(p)
    beat.end(p, decided="さらに進めた", observed="y")
    assert d.read_text(encoding="utf-8") == stamp  # refresh_hours 以内は作り直さない
