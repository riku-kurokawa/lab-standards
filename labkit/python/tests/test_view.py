"""レビュー板（labkit view）と人間の返信（notes）."""

import json

import pytest

from labkit import Run, beat, claims, state, view

from .conftest import git


def write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture
def board(git_project):
    p = git_project
    write(p / "src" / "boardpkg" / "__init__.py", "")
    write(p / "src" / "boardpkg" / "exp.py", "def helper():\n    return 0\n\n\ndef run(cfg):\n    return {'e': 5.0}\n")
    git(p, "add", "-A")
    git(p, "commit", "-q", "-m", "exp を足す")
    pred = {"basis": "桁の見積もり", "claims": [{"key": "e", "range": [0, 1]}]}
    cfg = {"seed": 0, "entry": "boardpkg.exp:run", "prediction": pred, "report": {"noncomparative": ["e", "f"]}}
    with Run("arr-one", cfg) as run:
        run.log_metric("e", 5.0)
        run.log_metric("f", 1.0)
    claims.add_claim(p, "e は 5", [f"{run.run_id}:e"])
    state.ask_question(p, "A か B か", options=["A", "B"], assumed="A で進める")
    write(p / "prompts" / "goal_v1.md", "# 目標\n")
    write(p / "prompts" / "beat_v1.md", "# 1 拍\n")
    beat.ensure_current(p, "goal_v1.md", "beat_v1.md")
    beat.start(p)
    beat.end(p, predicted="e は 1 以下", observed="e = 5", decided="外れ。原因を調べる", runs=[run.run_id])
    return p, run


def test_board_bundles_evidence_per_deliverable(board):
    """主張 1 件 1 枚にしない: 同じ実験の主張・外れた予想を 1 枚に束ね、生んだコード（その commit の entry）を付ける."""
    p, run = board
    data, figs = view.collect(p, days=1)
    groups = [c for c in data["cards"] if c["kind"] == "group"]
    assert len(groups) == 1 and groups[0]["counts"] == {"retract": 0, "miss": 1, "claim": 1}
    assert {i["id"] for i in groups[0]["items"]} == {"claim:C001", f"miss:{run.run_id}"}
    code = groups[0]["codes"][0]
    assert code["label"].startswith("src/boardpkg/exp.py:5 @ ") and code["text"].startswith("def run(cfg):")
    assert [c["title"] for c in data["cards"] if c["kind"] == "question"] == ["Q001 A か B か"]
    b = data["timeline"][-1]
    assert b["decided"] == "外れ。原因を調べる" and b["runs"][0]["verdict"] == "miss"
    assert any("exp を足す" in c["subject"] for t in data["timeline"] for c in t["commits"])
    html = view.render(data, figs, embed=True)
    assert "<title>レビュー板</title>" in html and "claim:C001" in html and "/*STATE*/null" not in html
    assert view.commit_diff(p, "zzz") == "" and "def run(cfg)" in view.commit_diff(
        p, git(p, "rev-parse", "HEAD~0")[:10]
    )


def test_human_reply_reaches_the_next_beat_and_agent_answers(board):
    """人間の返信は次の拍の先頭に出る。エージェントは答えて閉じる。OK は確認の印で、対応を求めない."""
    p, run = board
    ok = state.add_note(p, "group:arr-one", "ok", covers=["claim:C001", f"miss:{run.run_id}"])
    assert ok["status"] == "done" and not state.note_lines(p)
    with pytest.raises(ValueError, match="一言"):
        state.add_note(p, "group:arr-one", "ng")
    n = state.add_note(p, "group:arr-one", "question", "e の単位は何か")
    out = beat.start(p)
    assert out.index("人間の返信 N002") < out.index("今日の run") and "e の単位は何か" in out
    with pytest.raises(ValueError, match="--reply"):
        state.close_note(p, n["id"], "")
    state.close_note(p, n["id"], "無次元。figspec のラベルに [1] を足した")
    assert not state.note_lines(p)
    data, _ = view.collect(p, days=1)
    thread = data["notes"]["group:arr-one"]
    assert [x["verdict"] for x in thread] == ["ok", "question"] and thread[1]["reply"].startswith("無次元")
    assert thread[0]["covers"] == ["claim:C001", f"miss:{run.run_id}"]  # 後から足された主張は未確認として板に戻る


def test_agent_cannot_write_notes_directly(board):
    from labkit.hook import handle

    from .test_hook import bash
    from .test_hook import write as hook_write

    p, _ = board
    assert handle("pretool", bash("echo x > .lab/notes/N009.json", p))[0] == 2
    assert handle("pretool", hook_write(".lab/notes/N009.json", p))[0] == 2
    assert handle("pretool", bash('uv run labkit note done N001 --reply "直した"', p))[0] == 0


def test_board_serves_and_accepts_a_note(board):
    """127.0.0.1 の板: ページ・図・差分を返し、返信を .lab/notes/ に書く."""
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer

    p, _ = board
    made = {}
    orig = ThreadingHTTPServer.serve_forever

    def capture(self, *a, **k):
        made["srv"] = self
        return orig(self, *a, **k)

    ThreadingHTTPServer.serve_forever = capture
    try:
        t = threading.Thread(target=view.serve, args=(p, 0, 1), daemon=True)
        t.start()
        for _ in range(100):
            if "srv" in made:
                break
            import time

            time.sleep(0.05)
        port = made["srv"].server_address[1]
        base = f"http://127.0.0.1:{port}"
        page = urllib.request.urlopen(base + "/").read().decode("utf-8")
        assert '"writable": true' in page and "claim:C001" in page
        req = urllib.request.Request(
            base + "/note",
            data=json.dumps({"target": "queue:Q001", "verdict": "choose", "text": "B"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        note = json.loads(urllib.request.urlopen(req).read())
        assert note["id"] == "N001" and state.list_notes(p, "open")[0]["text"] == "B"
    finally:
        ThreadingHTTPServer.serve_forever = orig
        if "srv" in made:
            made["srv"].shutdown()
