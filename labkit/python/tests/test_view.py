"""人間への投稿（labkit post）、フィード（labkit view）、人間の返信（notes）."""

import json

import pytest

from labkit import Run, beat, post, state, view

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360000002000001e221bc330000000049454e44ae426082"
)


def write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture
def feed(git_project):
    p = git_project
    write(p / "src" / "feedpkg" / "exp.py", "def helper():\n    return 0\n\n\ndef run(cfg):\n    return {'e': 5.0}\n")
    with Run("arr-one", {"seed": 0}) as run:
        run.log_metric("e", 5.04)
    (p / "scratch").mkdir(exist_ok=True)
    (p / "scratch" / "e.png").write_bytes(PNG)
    write(
        p / "scratch" / "e.figmeta.json", '{"template": "bar", "spec_file": "figspecs/e.toml"}'
    )  # labkit fig の出力の印
    (p / "scratch" / "raw.png").write_bytes(PNG)  # 使い捨てのスクリプトで描いた図
    write(p / "prompts" / "goal_v1.md", "# 目標\n")
    write(p / "prompts" / "beat_v1.md", "# 1 拍\n")
    beat.ensure_current(p, "goal_v1.md", "beat_v1.md")
    return p, run


def test_post_keeps_frozen_evidence(feed):
    """投稿は、照合した引用・図の写し・コードの抜粋を持つ（後から図やコードが変わっても投稿は変わらない）."""
    p, run = feed
    made = post.add_post(
        p,
        "e は 5.0 で、予想の 5 倍だった",
        f"桁の見積もりが外れた。e = 5.0 [run:{run.run_id}:e]",
        figs=["scratch/e.png::縦軸の 5 を見る"],
        code=["src/feedpkg/exp.py:5-6"],
    )
    assert made["id"] == "P001" and made["cites"] == [{"run": run.run_id, "key": "e", "value": 5.04}]
    assert made["runs"] == [run.run_id] and made["figs"][0] == {
        "file": "P001/1.png",
        "caption": "縦軸の 5 を見る",
        "template": "bar",
        "spec": "figspecs/e.toml",
    }
    assert made["code"][0]["text"].startswith("def run(cfg):") and "exp.py:5-6" in made["code"][0]["label"]
    (p / "scratch" / "e.png").unlink()
    assert (p / ".lab" / "posts" / "P001" / "1.png").read_bytes() == PNG
    data = view.collect(p)
    assert [x["id"] for x in data["posts"]] == ["P001"] and data["older"] == 0
    html = view.render(p, data, embed=True)
    assert "data:image/png;base64," in html and "/*STATE*/null" not in html and "予想の 5 倍" in html


def test_post_refuses_noise(feed):
    """少なく・短く・根拠つきを、コマンドの拒否で守る."""
    p, run = feed
    ok = f"e = 5.0 [run:{run.run_id}:e]"
    for kwargs, why in [
        ({"title": "あ" * 61, "body": ok}, "見出し"),
        ({"title": "t", "body": ok + "あ" * 700}, "本文"),
        ({"title": "t", "body": ok + " C185 を撤回"}, "台帳の番号"),
        ({"title": "t", "body": "根拠の無い話"}, "根拠"),
        ({"title": "t", "body": f"e = 9.9 [run:{run.run_id}:e]"}, "一致しません"),
        ({"title": "t", "body": f"値は [run:{run.run_id}:e]"}, "直前に数値"),
        ({"title": "t", "body": ok, "figs": ["scratch/e.png"]}, "見るところ"),
        ({"title": "t", "body": ok, "figs": ["scratch/none.png::x"]}, "図がありません"),
        ({"title": "t", "body": ok, "figs": ["scratch/raw.png::x"]}, "labkit fig"),
        ({"title": "t", "body": ok, "options": ["A", "B"]}, "ask"),
        ({"title": "t", "body": ok, "code": ["src/feedpkg/exp.py"]}, "--code"),
    ]:
        with pytest.raises(ValueError, match=why):
            post.add_post(p, kwargs.pop("title"), kwargs.pop("body"), **kwargs)
    assert not post.list_posts(p)
    post.add_post(p, "A か B か", "いまは A で進めている", kind="ask", options=["A", "B"])  # 相談は根拠なしでよい
    for k in range(4):
        post.add_post(p, f"節目 {k}", "項目を閉じた", kind="milestone")
    with pytest.raises(ValueError, match="上限"):  # 1 日 5 本（[post] per_day）
        post.add_post(p, "6 本目", "多すぎる", kind="milestone")


def test_human_reply_reaches_the_next_beat_and_agent_answers(feed):
    """人間の返信は次の拍の先頭に出る。エージェントは答えて閉じる。了解は確認の印で、対応を求めない."""
    p, run = feed
    post.add_post(p, "e は 5.0 だった", "外れた", runs=[run.run_id])
    ok = state.add_note(p, "post:P001", "ok")
    assert ok["status"] == "done" and not state.note_lines(p)
    with pytest.raises(ValueError, match="一言"):
        state.add_note(p, "post:P001", "comment")
    n = state.add_note(p, "post:P001", "comment", "e の単位は何か")
    out = beat.start(p)
    assert out.index("人間の返信 N002") < out.index("今日の run") and "e の単位は何か" in out
    with pytest.raises(ValueError, match="--reply"):
        state.close_note(p, n["id"], "")
    before = view.collect(p)["stamp"]
    state.close_note(p, n["id"], "無次元。figspec のラベルに [1] を足した")
    assert not state.note_lines(p)
    data = view.collect(p)
    thread = data["notes"]["post:P001"]
    assert [x["verdict"] for x in thread] == ["ok", "comment"] and thread[1]["reply"].startswith("無次元")
    assert data["stamp"] != before  # 画面は答えが来たことに気づく


def test_agent_cannot_write_posts_or_notes_directly(feed):
    from labkit.hook import handle

    from .test_hook import bash
    from .test_hook import write as hook_write

    p, _ = feed
    assert handle("pretool", bash("echo x > .lab/notes/N009.json", p))[0] == 2
    assert handle("pretool", bash("echo x > .lab/posts/P009.json", p))[0] == 2
    assert handle("pretool", hook_write(".lab/posts/P009.json", p))[0] == 2
    assert handle("pretool", bash('uv run labkit note done N001 --reply "直した"', p))[0] == 0
    assert handle("pretool", bash('uv run labkit post "結論" --body @scratch/post.md', p))[0] == 0


def test_feed_serves_and_accepts_a_reply(feed):
    """127.0.0.1 のフィード: ページ・図・更新の印を返し、返信を .lab/notes/ に書く。投稿の図以外のファイルは渡さない."""
    import threading
    import time
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer

    p, run = feed
    post.add_post(p, "e は 5.0 だった", "外れた", figs=["scratch/e.png::5 を見る"])
    made = {}
    orig = ThreadingHTTPServer.serve_forever

    def capture(self, *a, **k):
        made["srv"] = self
        return orig(self, *a, **k)

    ThreadingHTTPServer.serve_forever = capture
    try:
        threading.Thread(target=view.serve, args=(p, 0, 1), daemon=True).start()
        for _ in range(100):
            if "srv" in made:
                break
            time.sleep(0.05)
        base = f"http://127.0.0.1:{made['srv'].server_address[1]}"
        page = urllib.request.urlopen(base + "/").read().decode("utf-8")
        assert '"writable": true' in page and "e は 5.0 だった" in page
        assert urllib.request.urlopen(base + "/fig/P001/1.png").read() == PNG
        for bad in ("/fig/P001/../../lab.toml", "/fig/P001.json"):
            with pytest.raises(urllib.error.HTTPError):
                urllib.request.urlopen(base + bad)
        stamp = urllib.request.urlopen(base + "/stamp").read()

        def send(target):
            body = json.dumps({"target": target, "verdict": "comment", "text": "図の縦軸は対数か"}).encode("utf-8")
            req = urllib.request.Request(base + "/note", data=body, headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req).read())

        with pytest.raises(urllib.error.HTTPError):
            send("queue:Q001")
        assert send("post:P001")["id"] == "N001" and state.list_notes(p, "open")[0]["text"] == "図の縦軸は対数か"
        assert urllib.request.urlopen(base + "/stamp").read() != stamp
    finally:
        ThreadingHTTPServer.serve_forever = orig
        if "srv" in made:
            made["srv"].shutdown()
