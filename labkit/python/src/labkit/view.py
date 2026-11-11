"""フィード（labkit view）: エージェントの投稿（labkit post）を新しい順に読み、その場で返信する.

    labkit view [--days 14] [--port 8765]    手元の 127.0.0.1 で開く（返信できる。新しい投稿は自動で知らせる）
    labkit view --out feed.html              1 枚の HTML に書き出す（図は埋め込み。返信はできない）

載るのは投稿だけ（拍・run・台帳は載せない。それらは機械が検証する記録で、投稿の根拠として引かれる）。
人間の返信は `.lab/notes/`（git 管理）に残り、次の `labkit beat start` の先頭に出る。エージェントは
`labkit note done <ID> --reply ...` で答え、その答えは同じ投稿のスレッドに出る。「了解」は確認の印で、対応を求めない。
"""

from __future__ import annotations

import base64
import datetime as _dt
import json
import mimetypes
import re
from importlib import resources
from pathlib import Path

from labkit.post import KINDS, POSTS_DIR, list_posts


def collect(root: Path, days: float = 14) -> dict:
    """フィードの状態（JSON にできる dict）."""
    from labkit import focus, state
    from labkit.config import load_lab

    now = _dt.datetime.now().astimezone()
    since = (now - _dt.timedelta(days=days)).isoformat(timespec="seconds")
    posts = list_posts(root)
    shown = [p for p in posts if str(p.get("created", "")) >= since]
    notes: dict[str, list[dict]] = {}
    for n in state.list_notes(root):
        notes.setdefault(n["target"], []).append(n)
    return {
        "project": load_lab(root)["lab"].get("project") or root.name,
        "generated": now.strftime("%Y-%m-%d %H:%M"),
        "goal": focus.read_main(root)["sentence"],
        "kinds": KINDS,
        "posts": list(reversed(shown)),
        "older": len(posts) - len(shown),
        "notes": notes,
        "stamp": f"{len(posts)}:{sum(len(v) for v in notes.values())}:{sum(bool(n.get('reply')) for v in notes.values() for n in v)}",
        "writable": False,
    }


def _fig_path(root: Path, name: str) -> Path | None:
    """投稿の図（P003/1.png）だけを返す（ほかのファイルは渡さない）."""
    if not re.fullmatch(r"P\d{3,}/\d+\.[a-z]{3,4}", name):
        return None
    p = root / POSTS_DIR / name
    return p if p.is_file() else None


def render(root: Path, data: dict, *, embed: bool) -> str:
    """1 枚の HTML。embed なら図を data URI で埋め込む（--out）。そうでなければ図は /fig/<P003/1.png> から読む."""
    if embed:
        uris = {}
        for f in (f for p in data["posts"] for f in p.get("figs") or []):
            path = _fig_path(root, f["file"])
            if path:
                mime = mimetypes.guess_type(path.name)[0] or "image/png"
                uris[f["file"]] = f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()
        data = {**data, "fig_uris": uris}
    page = resources.files("labkit.templates").joinpath("view.html").read_text(encoding="utf-8")
    return page.replace("/*STATE*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))


def serve(root: Path, port: int = 8765, days: float = 14) -> None:
    """127.0.0.1 だけで待ち受ける。状態は読むたびに作り直す（常に最新）。返信は .lab/notes/ に書く."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from labkit import state

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/", "/index.html"):
                data = {**collect(root, days), "writable": True}
                self._send(200, render(root, data, embed=False).encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/stamp":  # 新しい投稿・返信があるかを画面が聞く
                self._send(200, collect(root, days)["stamp"].encode("utf-8"), "text/plain")
            elif self.path.startswith("/fig/") and (p := _fig_path(root, self.path[5:])):
                self._send(200, p.read_bytes(), mimetypes.guess_type(p.name)[0] or "image/png")
            else:
                self._send(404, b"", "text/plain")

        def do_POST(self) -> None:  # noqa: N802
            host = (self.headers.get("Host") or "").split(":")[0]
            if self.path != "/note" or host not in ("127.0.0.1", "localhost"):
                return self._send(403, b"", "text/plain")
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                target = str(body["target"])
                if not re.fullmatch(r"post:P\d{3,}", target):
                    raise ValueError("返信先は投稿（post:P###）")
                note = state.add_note(root, target, str(body.get("verdict", "")), str(body.get("text", "")))
            except (ValueError, KeyError) as e:
                return self._send(400, str(e).encode("utf-8"), "text/plain; charset=utf-8")
            self._send(200, json.dumps(note, ensure_ascii=False).encode("utf-8"), "application/json")

        def log_message(self, *a) -> None:  # 端末を埋めない
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"フィード: http://localhost:{httpd.server_address[1]}/  （Ctrl+C で止める。返信は次の拍の先頭に届く）")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
