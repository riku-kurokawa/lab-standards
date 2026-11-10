"""主線と芽（focus.py）: 主線から絶対にずれず、芽を拾い続け、資源をどれかの線に紐づける."""

import datetime as _dt

import pytest

from labkit import Run, beat, focus
from labkit.check import run_check


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def setup_beats(p):
    put(p / "prompts" / "goal_v1.md", "# 目標\n\n## 目標\n\n表を完成\n")
    put(p / "prompts" / "beat_v1.md", "# 1 拍\n")
    beat.ensure_current(p, "goal_v1.md", "beat_v1.md")


_count = iter(range(10**6))


def _word(n):
    """停滞検出は数字を無視するので、通し番号を文字にする."""
    return "".join(chr(ord("a") + int(d)) for d in str(n))


def one_beat(p, line, **kw):
    """1 拍を始めて閉じる（毎回ちがう判断にして、停滞検出に掛からないようにする）."""
    kw.pop("tag", None)
    beat.start(p)
    return beat.end(p, decided=f"判断 {line} {_word(next(_count))}", observed="x", line=line, **kw)


def far(hours=72):
    return (_dt.datetime.now() + _dt.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")


def test_ledgers_are_not_hand_edited(git_project):
    from labkit.hook import handle

    from .test_hook import bash, write

    p = git_project
    assert handle("pretool", write("docs/mainline.md", p))[0] == 2  # 期限を手で延ばして関門を逃げない
    assert handle("pretool", write("docs/seeds.md", p))[0] == 2
    assert handle("pretool", bash("sed -i s/open/done/ docs/mainline.md", p))[0] == 2
    assert handle("pretool", bash("cat docs/mainline.md", p)) == (0, "", "")


def test_ledgers_and_check(project):
    p = project
    focus.main_set(p, "2 次元の 5 手法の比較表を完成させる")
    a = focus.main_add(p, "比較表", done_if="1 本の集計 run で全マス", due=far())
    with pytest.raises(ValueError, match="完了条件"):
        focus.main_add(p, "x", done_if="")
    with pytest.raises(ValueError, match="期限"):
        focus.main_add(p, "x", done_if="y", due="明日")
    s = focus.seed_add(p, "交差で符号が反転する", source="run X", test="1 例を 2 角度で", value="交差の法則")
    with pytest.raises(ValueError, match="必須"):
        focus.seed_add(p, "x", source="", test="t", value="v")
    with pytest.raises(ValueError, match="--serves"):
        focus.seed_decide(p, s["id"], to="promote", reason="面白い")  # 主線に効くと言えない芽は昇格しない
    focus.seed_decide(p, s["id"], to="promote", reason="表の外れ値を説明", serves=a["id"])
    assert focus.list_seeds(p)[0]["status"] == "promoted"
    with pytest.raises(ValueError, match="根拠"):
        focus.main_done(p, a["id"], evidence="")
    with pytest.raises(ValueError, match="先に次の項目"):
        focus.main_done(p, a["id"], evidence="run R")  # 最後の open の項目は、次を足すまで閉じられない
    b = focus.main_add(p, "外れ値の機構", done_if="対照 run で特定か、特定できないと記録", due=far())
    focus.main_done(p, a["id"], evidence="run R")
    assert [i["id"] for i in focus.open_items(p)] == [b["id"]]
    codes = {i.code for i in run_check(root=p)[0]}
    assert "L026" not in codes and "L025" not in codes
    # 期限切れは L025、壊れた台帳は L026
    focus.main_add(p, "遅れた項目", done_if="z", due="2000-01-01 09:00")
    issues = run_check(root=p)[0]
    assert any(i.code == "L025" and i.severity == "warn" for i in issues)
    text = (p / focus.SEEDS_FILE).read_text(encoding="utf-8").replace("| promoted |", "| maybe |")
    put(p / focus.SEEDS_FILE, text)
    assert any(i.code == "L026" for i in run_check(root=p)[0])


def test_gate_keeps_the_main_line(git_project):
    p = git_project
    setup_beats(p)
    # 芽の頻度は別の試験で見る（分の粒度で比べるので、遅い機械ではこの試験の途中で芽の関門が先に働く）
    with open(p / "lab.toml", "a", encoding="utf-8", newline="\n") as f:
        f.write("[autonomy]\nseed_every = 0\n")
    # 主線が無いあいだは何も強制しない（既存プロジェクトの互換）
    assert one_beat(p, "")["beat"] == 1
    focus.main_set(p, "比較表")
    m = focus.main_add(p, "比較表", done_if="全マス", due=far())
    with pytest.raises(ValueError, match="--line"):
        one_beat(p, "")
    beat.end(p, decided="主線を進めた", line=f"main:{m['id']}")  # 開いた拍を閉じる
    s = focus.seed_add(p, "芽", source="拍 2", test="1 例", value="法則")
    with pytest.raises(ValueError, match="new か try"):
        one_beat(p, "seed:S999")
    beat.end(p, decided="主線 2", line=f"main:{m['id']}")
    # 主線の割合: 直近 10 拍で主線以外は 3 拍まで（70 %）。4 拍目は記録しない
    assert one_beat(p, f"seed:{s['id']}")["line"] == f"seed:{s['id']}"
    assert one_beat(p, "other")["line"] == "other"
    assert one_beat(p, "other", tag="2")["line"] == "other"
    with pytest.raises(ValueError, match="割合"):
        one_beat(p, "other", tag="again")
    beat.end(p, decided="主線に戻る", line=f"main:{m['id']}")
    for k in range(7):
        one_beat(p, f"main:{m['id']}", tag=str(k))
    # 期限が近い主線があると、主線以外の拍は記録しない
    focus.main_add(p, "発表の表", done_if="全マス", due=far(hours=2))
    for k in range(3):
        one_beat(p, f"main:{m['id']}", tag=f"m{k}")
    with pytest.raises(ValueError, match="期限"):
        one_beat(p, "other", tag="late")
    beat.end(p, decided="主線", line=f"main:{m['id']}")
    focus.main_done(p, m["id"], evidence="run R")
    assert f"[main:{m['id']}]" in beat.log(p)


def test_seeds_must_keep_coming(git_project, monkeypatch):
    p = git_project
    setup_beats(p)
    focus.main_set(p, "比較表")
    focus.main_add(p, "比較表", done_if="全マス", due=far())
    with open(p / "lab.toml", "a", encoding="utf-8", newline="\n") as f:
        f.write("[autonomy]\nseed_every = 3\nstall_beats = 0\n")
    one_beat(p, "main:M001", tag="1")
    one_beat(p, "main:M001", tag="2")
    with pytest.raises(ValueError, match="芽が 1 つも"):
        one_beat(p, "main:M001", tag="3")
    focus.seed_add(p, "外れた予想: 2 倍波が 3 % 低い", source="拍 3", test="格子 2 倍", value="NS の床")
    beat.end(p, decided="主線 3", line="main:M001")
    lines = "\n".join(focus.status_lines(p))
    assert "主線: 比較表" in lines and "芽: new/try 1 件" in lines and "seed add" in lines


def test_runs_are_tied_to_a_line_and_broken_runs_do_not_repeat(git_project):
    p = git_project
    focus.main_set(p, "比較表")
    m = focus.main_add(p, "比較表", done_if="全マス", due=far())
    with pytest.raises(ValueError, match="serves"):
        with Run("score", {"seed": 0}):
            pass
    with pytest.raises(ValueError, match="open の主線"):
        with Run("score", {"seed": 0, "serves": "M999"}):
            pass
    with Run("score", {"seed": 0, "serves": m["id"]}) as run:
        pass
    import json

    assert json.loads((run.dir / "meta.json").read_text(encoding="utf-8"))["serves"] == m["id"]
    for _ in range(3):
        with pytest.raises(RuntimeError):
            with Run("broken", {"seed": 0, "serves": "other:照合"}):
                raise RuntimeError("bug")
    with pytest.raises(ValueError, match="続けて failed"):
        with Run("broken", {"seed": 0, "serves": "other:照合"}):
            pass
    sp = focus.spend(p)
    assert m["id"] in sp and sp["other"]["failed"] >= 0
    assert "失敗" in focus.spend_lines(p)[0]
    assert "## 主線と芽" in "\n".join(focus.digest_lines(p, "2000-01-01"))


def test_mainline_never_runs_dry(git_project):
    """空回りを作らない: 進められる項目が無い主線では拍を閉じられず、人間待ちの項目は名指しできない."""
    from labkit import state

    p = git_project
    setup_beats(p)
    with open(p / "lab.toml", "a", encoding="utf-8", newline="\n") as f:
        f.write("[autonomy]\nseed_every = 0\n")
    focus.main_set(p, "比較表")
    a = focus.main_add(p, "legacy への移動", done_if="人間が保護を外した後に移す", due=far())
    # 主線の拍は進めた項目を名指しする（何も進めていない「main」は記録されない）
    with pytest.raises(ValueError, match="名指し"):
        one_beat(p, "main")
    beat.end(p, decided="準備の枝を作った", line=f"main:{a['id']}")
    # 人間待ちは block で外す。待つ相手は queue の連絡だけ。最後の open の項目は、次を足すまで外せない
    q = state.ask_question(p, "保護を外してよいか", options=["外す", "外さない"], assumed="外さない")
    with pytest.raises(Exception):  # noqa: B017, PT011  無い連絡は待てない
        focus.main_block(p, a["id"], on="Q999", reason="保護")
    with pytest.raises(ValueError, match="先に次の項目"):
        focus.main_block(p, a["id"], on=q["id"], reason="保護の解除が要る")
    b = focus.main_add(p, "説明できない外れの機構", done_if="対照 run で特定か、特定できないと記録", due=far())
    focus.main_block(p, a["id"], on=q["id"], reason="保護の解除が要る")
    assert [i["id"] for i in focus.open_items(p)] == [b["id"]]
    with pytest.raises(ValueError, match="open ではない"):
        one_beat(p, f"main:{a['id']}")  # 人間待ちの項目を進めたことにはできない
    beat.end(p, decided="機構の対照を投げた", line=f"main:{b['id']}")
    assert "人間待ち" in "\n".join(focus.status_lines(p))
    # 既に空になっている主線（旧版で全部 done にした台帳）: どの線の拍も記録しない。項目を足すと動く
    text = (p / focus.MAIN_FILE).read_text(encoding="utf-8").replace("| open |", "| done | run R")
    put(p / focus.MAIN_FILE, text)
    assert any(i.code == "L025" for i in run_check(root=p)[0])
    assert "空回りの手前" in "\n".join(focus.status_lines(p))
    for line in ("other", "main", ""):
        with pytest.raises(ValueError, match="進められる項目"):
            one_beat(p, line)
    c = focus.main_add(p, "取り直す比較", done_if="1 軸・同一 commit の run", due=far())
    assert beat.end(p, decided="比較を投げた", line=f"main:{c['id']}")["line"] == f"main:{c['id']}"
    focus.main_unblock(p, a["id"])
    assert len(focus.open_items(p)) == 2
    # keep_open = 0 で旧来の挙動（空の主線は何も強制しない）
    text = (p / focus.MAIN_FILE).read_text(encoding="utf-8").replace("| open |", "| done | run R")
    put(p / focus.MAIN_FILE, text)
    with open(p / "lab.toml", "a", encoding="utf-8", newline="\n") as f:
        f.write("keep_open = 0\n")
    assert one_beat(p, "")["beat"]
