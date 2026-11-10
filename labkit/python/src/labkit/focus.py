"""主線と芽（docs/mainline.md・docs/seeds.md）。主線から絶対にずれず、しかし面白い芽を拾い続けるための台帳と関門.

    labkit main set "2 次元の 5 手法の比較表を、事前登録どおり全数で完成させる"
    labkit main add "比較表（5 手法 × 5 列）" --done "1 本の集計 run・事前登録の全模型" --due "2026-11-10 09:30"
    labkit main done M001 --evidence <run|path|commit>
    labkit main block M002 --on Q007 --reason "実機の測定が要る"   人間の行為が無いと進められない項目（open に数えない）
    labkit main unblock M002
    labkit main status
    labkit seed add "<観察・問い>" --from <run|file|拍> --test "<最安の確かめ方>" --value "<当たれば何が変わる>"
    labkit seed decide S003 --to try|park|promote|drop --reason "..." [--serves M001]
    labkit seed list [--status new]

関門（labkit beat end。主線の 1 文と項目が docs/mainline.md にあるあいだ働く）:
  - **進められる項目を切らさない**: open の項目（blocked・done を除く）が autonomy.keep_open 個（既定 1）を下回ると、どの拍も記録しない。
    最後の open の項目は、次の項目を足してからでないと done にも blocked にもできない（主線が空のまま回り続ける「空回り」を作らない）。
  - 拍ごとに、どの線を進めたか（--line main:Mxxx | seed:Sxxx | other）を記録する。主線の拍は進めた open の項目を名指しする
    （人間待ちの項目は名指しできない。`main block` で外し、進められる項目を足す）。
  - 期限切れか、期限まで autonomy.main_guard_hours 時間以内の open の主線があると、main 以外の拍は記録しない。
  - 直近 autonomy.main_window 拍で main の割合が autonomy.main_share を下回る拍は記録しない。
  - autonomy.seed_every 拍のあいだに芽が 1 つも足されないと記録しない（主線だけを回して考えるのをやめない）。
芽を主線に入れるのは `seed decide --to promote --serves <主線の ID>` だけ（主線のどの項目に効くかを言えないものは昇格しない）。

資源の使い道（Run の開始時。主線に open の項目があるときだけ働く）:
  - 設定の `serves`（主線の ID・芽の ID・`other:<理由>`）が無い run は始まらない。計算資源は必ずどれかの線に紐づく。
  - 同じ名前の run が autonomy.fail_repeat 回（既定 3）続けて failed/interrupted で、そのあいだ commit が進んでいなければ、次は始まらない
    （壊れた計算を監視なしで回し続けない。原因を直して commit してから）。
  - `labkit beat start` と digest は、直近 24 時間の run 時間を線ごと・状態ごとに示す（主線に何割使ったか、失敗に何時間捨てたか）。
"""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path

from labkit._util import write_text_atomic

MAIN_FILE = "docs/mainline.md"
SEEDS_FILE = "docs/seeds.md"
MAIN_STATUSES = ("open", "blocked", "done")
SEED_STATUSES = ("new", "try", "park", "promoted", "drop")
MAIN_HEADER = (
    "`labkit main set / add / done / status` で書く（手で編集しない）。主線は 1 文、項目は成果物・完了条件・期限。"
    "期限切れの項目があるあいだ、主線以外の拍は記録されない（`labkit beat end --line`）。\n\n"
    "| ID | 成果物 | 完了条件 | 期限 | 状態 | 根拠 |\n|---|---|---|---|---|---|\n"
)
SEEDS_HEADER = (
    "# 芽の台帳\n\n`labkit seed add / decide / list` で書く（手で編集しない）。芽は主線の作業中に見つけた面白い観察・問い。"
    "主線に入れるのは `seed decide --to promote --serves <主線の ID>` だけ。\n\n"
    "| ID | 日時 | 芽 | 出どころ | 最安の確かめ方 | 当たれば | 状態 | 判断 |\n|---|---|---|---|---|---|---|---|\n"
)
MAIN_ROW = re.compile(r"^\|\s*(M\d{3,})\s*\|(.*?)\|(.*?)\|(.*?)\|\s*(\S+)\s*\|(.*)\|\s*$")
SEED_ROW = re.compile(r"^\|\s*(S\d{3,})\s*\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|\s*(\S+)\s*\|(.*)\|\s*$")
LINE_RE = re.compile(r"^(main(:M\d{3,})?|other|seed:S\d{3,})$")
REFILL_HELP = (
    "主線に、いま自分で進められる項目（open）がありません。人間の返事・保護の解除・実機を待つ項目は進められる項目ではありません。"
    "目標の問いに照らして残っている最大の穴（未確認の機構、説明できない外れ、取り直すべき比較、昇格できる芽）を "
    '`labkit main add "<成果物>" --done "<機械か独立の読み手が確かめられる完了条件>" --due "YYYY-MM-DD HH:MM"` で足してから進めてください。'
    "計算だけで決められる判断は自分で決める（`labkit queue ask` は知らせるだけ）。穴が本当に無いなら、独立の点検（candor-check）に "
    "目標と報告だけを渡して穴を挙げさせ、その答えを項目にする"
)


def is_main(line: str | None) -> bool:
    return (line or "").split(":", 1)[0] == "main"


def _cell(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("|", "/")).strip()


def _now() -> _dt.datetime:
    return _dt.datetime.now().replace(second=0, microsecond=0)


def parse_due(s: str) -> _dt.datetime | None:
    s = (s or "").strip()
    if not s or s == "—":
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            d = _dt.datetime.strptime(s, fmt)
            return d.replace(hour=23, minute=59) if fmt == "%Y-%m-%d" else d
        except ValueError:
            continue
    raise ValueError(f"期限は 'YYYY-MM-DD HH:MM' か 'YYYY-MM-DD'（ローカル時刻）: {s!r}")


# ---- 主線 ----
def read_main(root: Path) -> dict:
    p = root / MAIN_FILE
    text = p.read_text(encoding="utf-8") if p.is_file() else ""
    m = re.search(r"^主線:\s*(.+)$", text, re.M)
    items = []
    for n, ln in enumerate(text.splitlines(), 1):
        if r := MAIN_ROW.match(ln):
            mid, what, done, due, st, ev = r.groups()
            items.append({"id": mid, "what": what.strip(), "done_if": done.strip(), "due": due.strip(), "status": st})
            items[-1].update(evidence=ev.strip(), line=n)
    return {"sentence": m.group(1).strip() if m else "", "items": items, "exists": p.is_file()}


def _write_main(root: Path, sentence: str, items: list[dict]) -> Path:
    rows = "".join(
        f"| {i['id']} | {_cell(i['what'])} | {_cell(i['done_if'])} | {_cell(i['due']) or '—'} | {i['status']} | {_cell(i['evidence'])} |\n"
        for i in items
    )
    p = root / MAIN_FILE
    write_text_atomic(
        p, f"# 主線\n\n主線: {_cell(sentence) or '（未設定。`labkit main set`）'}\n\n" + MAIN_HEADER + rows
    )
    return p


def main_set(root: Path, sentence: str) -> Path:
    if not sentence.strip():
        raise ValueError("主線は 1 文で書く")
    m = read_main(root)
    return _write_main(root, sentence, m["items"])


def main_add(root: Path, what: str, *, done_if: str, due: str = "") -> dict:
    if not what.strip() or not done_if.strip():
        raise ValueError("成果物と完了条件（--done）は必須。完了条件は機械か人が確かめられる形で")
    parse_due(due)
    m = read_main(root)
    nid = f"M{max([int(i['id'][1:]) for i in m['items']] + [0]) + 1:03d}"
    item = {"id": nid, "what": what, "done_if": done_if, "due": due or "—", "status": "open", "evidence": ""}
    _write_main(root, m["sentence"], [*m["items"], item])
    return item


def main_done(root: Path, mid: str, *, evidence: str) -> dict:
    if not evidence.strip():
        raise ValueError("--evidence（run ID・ファイル・commit）は必須。完了は根拠で示す")
    m = read_main(root)
    hit = [i for i in m["items"] if i["id"] == mid]
    if not hit:
        raise ValueError(f"{mid} は {MAIN_FILE} にありません")
    if hit[0]["status"] == "open":
        _refuse_last(root, m, mid, "done")
    hit[0].update(status="done", evidence=evidence)
    _write_main(root, m["sentence"], m["items"])
    return hit[0]


def _keep_open(root: Path) -> int:
    from labkit.config import load_lab

    return int(load_lab(root)["autonomy"].get("keep_open", 1) or 0)


def _refuse_last(root: Path, m: dict, mid: str, verb: str) -> None:
    """最後の open の項目を閉じる前に、次の項目を足させる（主線を空にしない）."""
    k = _keep_open(root)
    left = [i for i in m["items"] if i["status"] == "open" and i["id"] != mid]
    if k > 0 and len(left) < k:
        raise ValueError(
            f"{mid} を {verb} にすると、進められる項目が {len(left)} 個になります（下限 {k}）。先に次の項目を足す。{REFILL_HELP}"
        )


def main_block(root: Path, mid: str, *, on: str, reason: str) -> dict:
    """人間の行為が無いと進められない項目を open から外す（どの連絡を待つかを残す）."""
    from labkit import state

    if not reason.strip():
        raise ValueError("--reason（何が無いと進められないか）は必須")
    state.get_item(root, on)  # 無ければ例外: 待つ相手は `labkit queue ask` で知らせた連絡だけ
    m = read_main(root)
    hit = [i for i in m["items"] if i["id"] == mid]
    if not hit or hit[0]["status"] != "open":
        raise ValueError(f"{mid} は open の主線にありません（{MAIN_FILE}）")
    _refuse_last(root, m, mid, "blocked")
    hit[0].update(status="blocked", evidence=f"blocked on {on}: {reason}")
    _write_main(root, m["sentence"], m["items"])
    return hit[0]


def main_unblock(root: Path, mid: str) -> dict:
    m = read_main(root)
    hit = [i for i in m["items"] if i["id"] == mid]
    if not hit or hit[0]["status"] != "blocked":
        raise ValueError(f"{mid} は blocked の主線にありません（{MAIN_FILE}）")
    hit[0].update(status="open", evidence="")
    _write_main(root, m["sentence"], m["items"])
    return hit[0]


def engaged(root: Path) -> bool:
    """主線を使っているプロジェクトか: 1 文と項目が 1 つ以上ある（すべて done・blocked でも真）."""
    m = read_main(root)
    return bool(m["sentence"]) and not m["sentence"].startswith("（未設定") and bool(m["items"])


def open_items(root: Path) -> list[dict]:
    return [i for i in read_main(root)["items"] if i["status"] == "open"]


def pressing(root: Path, guard_hours: float, now: _dt.datetime | None = None) -> list[dict]:
    """期限切れか、期限まで guard_hours 以内の open な主線（期限の近い順）."""
    now = now or _now()
    out = []
    for i in open_items(root):
        due = parse_due(i["due"])
        if due is not None and (due - now).total_seconds() <= guard_hours * 3600:
            out.append({**i, "due_dt": due, "overdue": due < now})
    return sorted(out, key=lambda i: i["due_dt"])


# ---- 芽 ----
def list_seeds(root: Path, status: str | None = None) -> list[dict]:
    p = root / SEEDS_FILE
    out = []
    for n, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if p.is_file() else []:
        if r := SEED_ROW.match(ln):
            sid, when, what, src, test, value, st, why = r.groups()
            row = {"id": sid, "time": when.strip(), "what": what.strip(), "from": src.strip(), "test": test.strip()}
            row.update(value=value.strip(), status=st, why=why.strip(), line=n)
            if status is None or st == status:
                out.append(row)
    return out


def _write_seeds(root: Path, seeds: list[dict]) -> Path:
    rows = "".join(
        f"| {s['id']} | {s['time']} | {_cell(s['what'])} | {_cell(s['from'])} | {_cell(s['test'])} | {_cell(s['value'])} | {s['status']} | {_cell(s['why'])} |\n"
        for s in seeds
    )
    p = root / SEEDS_FILE
    write_text_atomic(p, SEEDS_HEADER + rows)
    return p


def seed_add(root: Path, what: str, *, source: str, test: str, value: str) -> dict:
    if not (what.strip() and source.strip() and test.strip() and value.strip()):
        raise ValueError(
            "芽・出どころ（--from）・最安の確かめ方（--test）・当たれば何が変わるか（--value）はすべて必須"
        )
    seeds = list_seeds(root)
    sid = f"S{max([int(s['id'][1:]) for s in seeds] + [0]) + 1:03d}"
    s = {"id": sid, "time": _now().strftime("%Y-%m-%d %H:%M"), "what": what, "from": source, "test": test}
    s.update(value=value, status="new", why="")
    _write_seeds(root, [*seeds, s])
    return s


def seed_decide(root: Path, sid: str, *, to: str, reason: str, serves: str = "") -> dict:
    if to == "promote":
        to = "promoted"
    if to not in SEED_STATUSES or to == "new":
        raise ValueError("--to は try / park / promote / drop のいずれか")
    if not reason.strip():
        raise ValueError("--reason は必須")
    if to == "promoted":
        ids = {i["id"] for i in read_main(root)["items"]}
        if serves not in ids:
            raise ValueError(
                "昇格は主線のどの項目に効くかを言えるときだけ（--serves <主線の ID>）。言えない芽は try（芽の枠で確かめる）か park"
            )
        reason = f"serves {serves}: {reason}"
    seeds = list_seeds(root)
    hit = [s for s in seeds if s["id"] == sid]
    if not hit:
        raise ValueError(f"{sid} は {SEEDS_FILE} にありません")
    hit[0].update(status=to, why=reason)
    _write_seeds(root, seeds)
    return hit[0]


# ---- 拍の関門 ----
def _conf(root: Path) -> dict:
    from labkit.config import load_lab

    a = load_lab(root)["autonomy"]
    return {
        "share": float(a.get("main_share", 0.7)),
        "window": int(a.get("main_window", 10)),
        "guard": float(a.get("main_guard_hours", 12)),
        "seed_every": int(a.get("seed_every", 8)),
        "fail_repeat": int(a.get("fail_repeat", 3)),
    }


def active(root: Path) -> bool:
    """主線の関門が働くか: docs/mainline.md に open の項目がある."""
    return bool(open_items(root))


def recent_ends(root: Path, n: int, days: int = 7) -> list[dict]:
    """直近 n 個の拍の end（日をまたいで遡る、古い順）."""
    from labkit.beat import read_beats

    out: list[dict] = []
    d = _dt.date.today()
    for k in range(days):
        day = (d - _dt.timedelta(days=k)).isoformat()
        out = [b for b in read_beats(root, day) if b.get("event") == "end"] + out
        if len(out) >= n:
            break
    return out[-n:] if n else []


def gate(root: Path, line: str, now: _dt.datetime | None = None) -> None:
    """beat end の前に呼ぶ。記録してはいけない拍なら ValueError（理由と、やるべきことを示す）."""
    k = _keep_open(root)
    if k > 0 and engaged(root) and len(open_items(root)) < k:
        raise ValueError(f"この拍は記録しません。{REFILL_HELP}")
    if not active(root):
        return
    if not LINE_RE.match(line or ""):
        raise ValueError(
            "--line が要ります: main:Mxxx（主線のその項目を進めた）/ seed:Sxxx（芽を確かめた）/ other（掃除・照合など）。docs/mainline.md に open の主線があるため"
        )
    c = _conf(root)
    if is_main(line) and k > 0:
        ids = [i["id"] for i in open_items(root)]
        mid = line.partition(":")[2]
        if mid not in ids:
            raise ValueError(
                f"主線の拍は、この拍で進めた open の項目を名指しします: --line main:<{' | '.join(ids)}>"
                + (f"（{mid} は open ではない）" if mid else "")
                + "。どの項目も進めていないなら other。人間待ちで進められない項目は `labkit main block <ID> --on <Q番号> --reason ...` で外す"
            )
    if not is_main(line):
        if p := pressing(root, c["guard"], now):
            i = p[0]
            when = "期限切れ" if i["overdue"] else f"期限 {i['due']} まで {c['guard']:g} 時間以内"
            raise ValueError(
                f"主線 {i['id']}「{i['what']}」が{when}です。この拍は主線（--line main）に使ってください。芽は `labkit seed add` で記録だけして後で"
            )
        if line.startswith("seed:"):
            sid = line.split(":", 1)[1]
            st = {s["id"]: s["status"] for s in list_seeds(root)}.get(sid)
            if st not in ("new", "try"):
                raise ValueError(
                    f"{sid} は {'台帳に無い' if st is None else f'状態 {st}'}。確かめられるのは new か try の芽だけ"
                )
        # 主線の割合: 直近 window 拍（この拍を含む）のうち主線以外は floor((1-share)*window) 拍まで。
        # 拍数が少ない立ち上がりでも 1 拍の芽で止まらず、長く見れば必ず share 以上が主線になる
        budget = max(1, int((1 - c["share"]) * c["window"] + 1e-9)) if c["share"] < 1 else 0
        ends = [b for b in recent_ends(root, c["window"] - 1) if b.get("line")]
        other = sum(not is_main(b.get("line")) for b in ends)
        if other + 1 > budget:
            raise ValueError(
                f"直近 {c['window']} 拍で主線以外が {other + 1} 拍になり、主線の割合の下限 {c['share']:.0%}"
                f"（主線以外は {budget} 拍まで）を割ります。この拍は主線（--line main）に使ってください"
            )
    if c["seed_every"] > 0:
        ends = recent_ends(root, c["seed_every"] - 1)
        if len(ends) >= c["seed_every"] - 1:
            since = ends[0].get("time", "")[:16].replace("T", " ")
            if not any(s["time"] >= since for s in list_seeds(root)):
                raise ValueError(
                    f"直近 {c['seed_every']} 拍のあいだに芽が 1 つも記録されていません。主線を進めながら見つけた面白い観察・外れた予想・"
                    '気になる数字を 1 つ `labkit seed add "<芽>" --from <run|file> --test "<最安の確かめ方>" --value "<当たれば>"` で残してから拍を閉じてください'
                )


# ---- 資源の使い道 ----
def check_run_start(root: Path, name: str, config: dict, commit: str | None) -> str:
    """Run の開始前に呼ぶ。始めてはいけないなら ValueError。記録する serves を返す."""
    from labkit.runs import list_runs

    serves = str(config.get("serves", "") or "").strip()
    if active(root):
        if not serves:
            raise ValueError(
                "設定に `serves` がありません。この計算がどの線に使われるかを書く: 主線の ID（M001）、芽の ID（S003）、"
                "または `other:<理由>`（照合・掃除など）。docs/mainline.md に open の主線があるため"
            )
        ids_main = {i["id"]: i["status"] for i in read_main(root)["items"]}
        ids_seed = {s["id"]: s["status"] for s in list_seeds(root)}
        if serves.startswith("M") and ids_main.get(serves) != "open":
            raise ValueError(f"serves = {serves} は open の主線にありません（{MAIN_FILE}）")
        if serves.startswith("S") and ids_seed.get(serves) not in ("new", "try", "promoted"):
            raise ValueError(f"serves = {serves} は確かめ中の芽ではありません（{SEEDS_FILE}）")
        if not (serves.startswith(("M", "S")) or serves.startswith("other:") and len(serves) > 7):
            raise ValueError("serves は Mxxx / Sxxx / other:<理由> のどれか")
    k = _conf(root)["fail_repeat"]
    if k > 0:
        same = [m for m in list_runs(root) if m.get("name") == name][-k:]
        if len(same) == k and all(m.get("status") in ("failed", "interrupted") for m in same):
            last_commit = ((same[-1].get("git") or {}).get("commit") or "")[:7]
            if commit and last_commit and commit[:7] == last_commit:
                raise ValueError(
                    f"同じ名前の run「{name}」が {k} 回続けて failed/interrupted で、commit も進んでいません"
                    f"（最後 {same[-1].get('run_id')}）。原因を直して commit してから実行する。監視なしで壊れた計算を回し続けない"
                )
    return serves


def spend(root: Path, hours: float = 24, now: _dt.datetime | None = None) -> dict:
    """直近 hours 時間に始まった run の時間（時間単位）を、線（serves）ごと・状態ごとに."""
    from labkit.runs import list_runs

    now = now or _dt.datetime.now().astimezone()
    out: dict = {}
    for m in list_runs(root, include_archived=True):
        try:
            t0 = _dt.datetime.fromisoformat(str(m.get("created")))
        except ValueError:
            continue
        if t0.tzinfo is None:
            t0 = t0.astimezone()
        if (now - t0).total_seconds() > hours * 3600:
            continue
        dur = m.get("duration_s")
        if dur is None and m.get("status") == "running":
            dur = (now - t0).total_seconds()
        line = str(m.get("serves") or "未記入")
        key = line if line.startswith(("M", "S", "未記入")) else "other"
        st = "failed" if m.get("status") in ("failed", "interrupted") else str(m.get("status"))
        out.setdefault(key, {}).setdefault(st, 0.0)
        out[key][st] += float(dur or 0) / 3600
    return out


def spend_lines(root: Path, hours: float = 24) -> list[str]:
    sp = spend(root, hours)
    if not sp:
        return []
    total = sum(v for d in sp.values() for v in d.values())
    main = sum(v for k, d in sp.items() if k.startswith("M") for v in d.values())
    failed = sum(d.get("failed", 0) for d in sp.values())
    parts = ", ".join(f"{k} {sum(d.values()):.1f} h" for k, d in sorted(sp.items()))
    return [
        f"- 直近 {hours:g} 時間の run: 計 {total:.1f} h（主線 {main / total:.0%}、失敗 {failed:.1f} h）— {parts}"
        if total
        else f"- 直近 {hours:g} 時間の run: なし"
    ]


def status_lines(root: Path, now: _dt.datetime | None = None) -> list[str]:
    """拍の最初に見る主線と芽の状態."""
    m = read_main(root)
    if not m["exists"] and not (root / SEEDS_FILE).is_file():
        return []
    c = _conf(root)
    now = now or _now()
    lines = [f"- 主線: {m['sentence'] or '（未設定）'}"]
    if _keep_open(root) > 0 and engaged(root) and not any(i["status"] == "open" for i in m["items"]):
        lines.append(f"  - **空回りの手前: {REFILL_HELP}**")
    for i in [i for i in m["items"] if i["status"] == "blocked"][:5]:
        lines.append(
            f"  - {i['id']} {i['what']} — 人間待ち（{i['evidence']}）。open に数えない。解けたら `labkit main unblock {i['id']}`"
        )
    for i in [i for i in m["items"] if i["status"] == "open"][:5]:
        due = parse_due(i["due"])
        left = (
            ""
            if due is None
            else (" **期限切れ**" if due < now else f"（残り {(due - now).total_seconds() / 3600:.1f} 時間）")
        )
        lines.append(f"  - {i['id']} {i['what']} — 完了条件: {i['done_if']} — 期限 {i['due']}{left}")
    ends = [b for b in recent_ends(root, c["window"]) if b.get("line")]
    if ends:
        mains = sum(is_main(b.get("line")) for b in ends)
        lines.append(f"- 直近 {len(ends)} 拍の主線の割合: {mains}/{len(ends)}（下限 {c['share']:.0%}）")
    seeds = list_seeds(root)
    fresh = [s for s in seeds if s["status"] in ("new", "try")]
    lines.append(
        f"- 芽: new/try {len(fresh)} 件、昇格 {sum(s['status'] == 'promoted' for s in seeds)}、捨て {sum(s['status'] == 'drop' for s in seeds)}"
        + (f"。最新: {fresh[-1]['id']} {fresh[-1]['what']}" if fresh else "")
    )
    lines += spend_lines(root)
    lines.append(
        "- この拍: 主線を 1 歩進めながら、外れた予想・気になる数字・意外な形を探し、見つけたら `labkit seed add`。終わりは `labkit beat end --line main:Mxxx|seed:Sxxx|other`"
    )
    return lines


def check(root: Path) -> list[tuple[str, str, str, str]]:
    """L025（警告）期限切れの open な主線。L026 台帳の書式（ID の重複・状態・期限の書式）."""
    out = []
    p = root / MAIN_FILE
    if p.is_file():
        seen = set()
        for i in read_main(root)["items"]:
            if i["id"] in seen:
                out.append(("L026", MAIN_FILE, f"{i['id']} が重複", "error"))
            seen.add(i["id"])
            if i["status"] not in MAIN_STATUSES:
                out.append(
                    (
                        "L026",
                        MAIN_FILE,
                        f"{i['id']} の状態 {i['status']} は {'/'.join(MAIN_STATUSES)} のどれでもない",
                        "error",
                    )
                )
            try:
                due = parse_due(i["due"])
            except ValueError as e:
                out.append(("L026", MAIN_FILE, f"{i['id']}: {e}", "error"))
                continue
            if i["status"] == "open" and due is not None and due < _now():
                out.append(("L025", MAIN_FILE, f"{i['id']}「{i['what']}」が期限 {i['due']} を過ぎて open", "warn"))
            if i["status"] == "done" and not i["evidence"]:
                out.append(("L026", MAIN_FILE, f"{i['id']} は done なのに根拠が無い", "error"))
        if _keep_open(root) > 0 and engaged(root) and not open_items(root):
            out.append(("L025", MAIN_FILE, "進められる項目（open）が無い。`labkit main add` で次の項目を足す", "warn"))
    if (root / SEEDS_FILE).is_file():
        seen = set()
        for s in list_seeds(root):
            if s["id"] in seen:
                out.append(("L026", SEEDS_FILE, f"{s['id']} が重複", "error"))
            seen.add(s["id"])
            if s["status"] not in SEED_STATUSES:
                out.append(
                    (
                        "L026",
                        SEEDS_FILE,
                        f"{s['id']} の状態 {s['status']} は {'/'.join(SEED_STATUSES)} のどれでもない",
                        "error",
                    )
                )
            if s["status"] == "promoted" and not s["why"].startswith("serves M"):
                out.append(("L026", SEEDS_FILE, f"{s['id']} は昇格したのに効く主線（serves Mxxx）が無い", "error"))
    return out


def digest_lines(root: Path, day: str) -> list[str]:
    m = read_main(root)
    seeds = list_seeds(root)
    if not m["exists"] and not seeds:
        return []
    L = ["## 主線と芽", "", f"- 主線: {m['sentence'] or '（未設定）'}"]
    for i in m["items"]:
        mark = {"done": "済", "blocked": "人間待ち"}.get(i["status"], "未")
        L.append(
            f"- [{mark}] {i['id']} {i['what']}（期限 {i['due']}）"
            + (f" 根拠: {i['evidence'][:80]}" if i["evidence"] else "")
        )
    new = [s for s in seeds if s["time"][:10] >= day]
    if new:
        L.append(f"- 新しい芽 {len(new)} 件:")
        L += [f"  - {s['id']} {s['what'][:90]}（{s['status']}）" for s in new[-5:]]
    moved = [s for s in seeds if s["status"] in ("promoted", "drop") and s["time"][:10] >= day]
    L += [f"- {s['id']} → {s['status']}: {s['why'][:120]}" for s in moved[-5:]]
    L += spend_lines(root)
    return [*L, ""]


__all__ = [
    "main_set",
    "main_add",
    "main_done",
    "main_block",
    "main_unblock",
    "engaged",
    "is_main",
    "read_main",
    "open_items",
    "pressing",
    "seed_add",
    "seed_decide",
    "list_seeds",
    "gate",
    "check_run_start",
    "spend",
    "status_lines",
    "check",
    "digest_lines",
]
