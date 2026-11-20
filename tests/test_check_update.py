"""check_update.py, the program that asks GitHub for the newest version and downloads its ZIP: every request goes to a
small HTTP server on 127.0.0.1 that the test starts (``--base``), never to the network. What the server saw of each
request is checked too: the fixed User-Agent, no query string, nothing about the installation."""

from __future__ import annotations

import ast
import io
import json
import shutil
import socket
import subprocess
import sys
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import check_update as cu  # noqa: E402

CHANGELOG = """# Changelog

What changed for someone who uses TASlation, newest first.

## 0.9.0 - 2026-11-25

Updates

* Help > Check for updates... looks for a newer version.

## 0.8.2 - 2026-11-22

* A smaller fix.

## 0.8.1 - 2026-11-20

* What 0.8.1 brought.

## 0.8.0 - 2026-11-19

* Older still.
"""


class Server:
    """A loopback HTTP server: *routes* maps a path to a function of the handler that answers it; every request's
    line and headers are kept in ``seen``."""

    def __init__(self, routes):
        self.routes = routes
        self.seen: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):  # noqa: N802 - the server's name
                outer.seen.append({"line": self.requestline, "path": self.path,
                                   "headers": [(k, v) for k, v in self.headers.items()]})
                route = outer.routes.get(self.path)
                if route is None:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                route(self)

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.httpd.block_on_close = False  # (a slow answer's thread is not waited for)
        self.port = self.httpd.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


CHANGELOG_PATH = "/tamachi955/taslation/main/CHANGELOG.md"


def zip_path(version: str) -> str:
    return f"/tamachi955/taslation/archive/refs/tags/v{version}.zip"


def body(data: bytes, status: int = 200, headers: dict | None = None, length: bool = True):
    def answer(h):
        h.send_response(status)
        for k, v in (headers or {}).items():
            h.send_header(k, v)
        if length:
            h.send_header("Content-Length", str(len(data)))
        else:
            h.send_header("Connection", "close")
        h.end_headers()
        h.wfile.write(data)
        if not length:
            h.close_connection = True
    return answer


def redirect(location: str):
    def answer(h):
        h.send_response(302)
        h.send_header("Location", location)
        h.send_header("Content-Length", "0")
        h.end_headers()
    return answer


@pytest.fixture
def server():
    made: list[Server] = []

    def make(routes):
        s = Server(routes)
        made.append(s)
        return s

    yield make
    for s in made:
        s.close()


def scratch(tmp_path: Path, version: str = "0.8.1") -> Path:
    """A folder with check_update.py beside a pyproject.toml of *version*, as an installation has them."""
    folder = tmp_path / "TASlation here"
    folder.mkdir()
    shutil.copy2(ROOT / "check_update.py", folder / "check_update.py")
    (folder / "pyproject.toml").write_text(f'[project]\nname = "taslation"\nversion = "{version}"\n', "utf-8")
    return folder


def run(folder: Path, *args: str, timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(folder / "check_update.py"), *args], capture_output=True,
                          text=True, encoding="utf-8", timeout=timeout, stdin=subprocess.DEVNULL)


def answer_of(result: subprocess.CompletedProcess) -> dict:
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 1, result.stdout + result.stderr
    return json.loads(lines[0])


# ---------------------------------------------------------------- the fixed addresses and what a request says


def test_the_two_addresses_and_the_hosts_are_fixed():
    assert cu.CHANGELOG_URL == "https://raw.githubusercontent.com/tamachi955/taslation/main/CHANGELOG.md"
    assert cu.ZIP_URL == "https://github.com/tamachi955/taslation/archive/refs/tags/v{version}.zip"
    assert cu.HOSTS == {"github.com", "codeload.github.com", "raw.githubusercontent.com"}
    assert cu.USER_AGENT == "TASlation-update-check"
    assert "?" not in cu.CHANGELOG_URL and "?" not in cu.ZIP_URL


@pytest.mark.parametrize("url", ["http://github.com/x", "https://evil.example/x", "https://github.com:8443/x",
                                 "https://user:pw@github.com/x", "ftp://github.com/x", "file:///c:/x",
                                 "https://github.com.evil.example/x", "https://127.0.0.1/x"])
def test_github_only_over_https(url):
    with pytest.raises(cu.AskError):
        cu.Place().check(url)


@pytest.mark.parametrize("url", ["https://github.com/a", "https://codeload.github.com/a",
                                 "https://raw.githubusercontent.com/a", "https://GitHub.com:443/a"])
def test_the_three_hosts_are_allowed(url):
    assert cu.Place().check(url).hostname in cu.HOSTS


@pytest.mark.parametrize("base", ["http://example.com:80", "https://127.0.0.1:8080", "http://127.0.0.1",
                                  "http://10.0.0.1:8080", "http://127.0.0.1:8080/other", "http://u@127.0.0.1:8080",
                                  "http://127.0.0.1:8080?q=1", "http://127.0.0.2:8080"])
def test_a_test_address_is_loopback_only(tmp_path, base):
    with pytest.raises(cu.AskError):
        cu.Place(base)
    result = run(scratch(tmp_path), "--base", base, "check")
    assert result.returncode == cu.COULD_NOT_ASK and result.stdout == ""


def test_the_request_says_nothing_about_the_person_or_the_installation(tmp_path, server):
    s = server({CHANGELOG_PATH: body(CHANGELOG.encode())})
    result = run(scratch(tmp_path, "0.8.1"), "--base", s.base, "check")
    assert result.returncode == cu.NEWER, result.stderr
    assert len(s.seen) == 1
    request = s.seen[0]
    assert request["line"] == f"GET {CHANGELOG_PATH} HTTP/1.1"  # no query string
    headers = dict(request["headers"])
    assert sorted(headers) == ["Accept", "Accept-Encoding", "Host", "User-Agent"]
    assert headers["User-Agent"] == "TASlation-update-check" and headers["Accept-Encoding"] == "identity"
    text = json.dumps(request)
    for word in ("0.8.1", "Python", "python", "Windows", "urllib", "Cookie", "Authorization", sys.version.split()[0]):
        assert word not in text, word


def test_the_program_uses_the_standard_library_only_and_the_package_never_imports_it():
    tree = ast.parse((ROOT / "check_update.py").read_text("utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[0])
    assert names - {"__future__"} <= set(sys.stdlib_module_names), names
    for path in (ROOT / "taslation").rglob("*.py"):
        text = path.read_text("utf-8")
        assert "import check_update" not in text and "from check_update" not in text, path


def test_no_setting_or_variable_moves_it(monkeypatch):
    text = (ROOT / "check_update.py").read_text("utf-8")
    assert "os.environ" not in text and "getenv" not in text and "import os" not in text


# ---------------------------------------------------------------- check


def test_a_newer_version_with_the_changes_between(tmp_path, server):
    s = server({CHANGELOG_PATH: body(CHANGELOG.encode())})
    answer = answer_of(run(scratch(tmp_path, "0.8.1"), "--base", s.base, "check"))
    assert answer["result"] == "newer" and answer["newer"] is True
    assert (answer["installed"], answer["newest"], answer["date"]) == ("0.8.1", "0.9.0", "2026-11-25")
    assert answer["changes"].startswith("0.9.0 - 2026-11-25\nUpdates")
    assert "0.8.2 - 2026-11-22" in answer["changes"] and "What 0.8.1 brought" not in answer["changes"]
    assert answer["reason"] == ""


@pytest.mark.parametrize("installed", ["0.9.0", "0.10.0", "1.0.0"])
def test_up_to_date_and_ahead(tmp_path, server, installed):
    s = server({CHANGELOG_PATH: body(CHANGELOG.encode())})
    result = run(scratch(tmp_path, installed), "--base", s.base, "check")
    answer = answer_of(result)
    assert result.returncode == cu.UP_TO_DATE
    assert answer["result"] == "up to date" and answer["newer"] is False and answer["changes"] == ""
    assert answer["newest"] == "0.9.0"


def test_versions_compare_as_numbers():
    assert cu.version_of("0.10.0") > cu.version_of("0.9.9")
    for bad in ("0.9", "v0.9.0", "0.9.0-rc1", "0.9.0 ", "١.٢.٣", "0.9.0\n", "", "0..1"):
        assert cu.version_of(bad) is None, bad


def test_a_redirect_is_followed_on_the_same_place(tmp_path, server):
    s = server({CHANGELOG_PATH: redirect("/moved/CHANGELOG.md"), "/moved/CHANGELOG.md": body(CHANGELOG.encode())})
    answer = answer_of(run(scratch(tmp_path), "--base", s.base, "check"))
    assert answer["result"] == "newer" and [r["path"] for r in s.seen] == [CHANGELOG_PATH, "/moved/CHANGELOG.md"]


@pytest.mark.parametrize("where", ["https://evil.example/CHANGELOG.md", "http://localhost:1/CHANGELOG.md",
                                   "file:///C:/Windows/win.ini"])
def test_a_redirect_elsewhere_stops_before_it_is_asked(tmp_path, server, where):
    s = server({CHANGELOG_PATH: redirect(where)})
    result = run(scratch(tmp_path), "--base", s.base, "check")
    answer = answer_of(result)
    assert result.returncode == cu.COULD_NOT_ASK and answer["result"] == "could not ask"
    assert "another address" in answer["reason"] and len(s.seen) == 1
    assert "Traceback" not in result.stdout + result.stderr


def test_too_many_redirects(tmp_path, server):
    s = server({CHANGELOG_PATH: redirect(CHANGELOG_PATH)})
    answer = answer_of(run(scratch(tmp_path), "--base", s.base, "check"))
    assert answer["result"] == "could not ask" and len(s.seen) == cu.MAX_REDIRECTS + 1


@pytest.mark.parametrize("length", [True, False])
def test_an_oversized_answer(tmp_path, server, length):
    s = server({CHANGELOG_PATH: body(CHANGELOG.encode() + b"x" * (cu.CHANGELOG_CAP + 10), length=length)})
    answer = answer_of(run(scratch(tmp_path), "--base", s.base, "check"))
    assert answer["result"] == "could not ask" and "larger than expected" in answer["reason"]


def test_a_broken_connection(tmp_path, server):
    def broken(h):
        h.send_response(200)
        h.send_header("Content-Length", "100000")
        h.end_headers()
        h.wfile.write(CHANGELOG.encode()[:50])
        h.wfile.flush()
        h.close_connection = True
        h.connection.shutdown(socket.SHUT_RDWR)
    s = server({CHANGELOG_PATH: broken})
    result = run(scratch(tmp_path), "--base", s.base, "check")
    assert answer_of(result)["result"] == "could not ask" and "Traceback" not in result.stderr


@pytest.mark.parametrize("stalls", ["before", "within"])
def test_a_slow_answer_is_given_up_in_time(server, monkeypatch, tmp_path, stalls):
    def slow(h):
        if stalls == "before":
            time.sleep(3)
            body(CHANGELOG.encode())(h)
            return
        data = CHANGELOG.encode()
        h.send_response(200)
        h.send_header("Content-Length", str(len(data)))
        h.end_headers()
        for i in range(0, len(data), 20):  # a trickle: each piece in time, the whole too late
            h.wfile.write(data[i:i + 20])
            time.sleep(0.1)
    s = server({CHANGELOG_PATH: slow})
    monkeypatch.setattr(cu, "CHECK_TOTAL_S", 0.8)
    began = time.monotonic()
    answer = cu.check(cu.Place(s.base), scratch(tmp_path))
    assert answer["result"] == "could not ask" and answer["reason"] == "GitHub did not answer in time."
    assert time.monotonic() - began < 2.0


def test_nothing_listening(tmp_path):
    with socket.socket() as sock:  # a port that was free a moment ago
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    answer = answer_of(run(scratch(tmp_path), "--base", f"http://127.0.0.1:{port}", "check"))
    assert answer["result"] == "could not ask" and answer["reason"]


@pytest.mark.parametrize("first", ["## 0.9 - 2026-11-25", "## v0.9.0 - 2026-11-25", "## 0.9.0-rc1 - 2026-11-25",
                                   "## Unreleased", "## 0.9.0 - tomorrow"])
def test_a_wrong_version_string_is_could_not_ask(tmp_path, server, first):
    text = CHANGELOG.replace("## 0.9.0 - 2026-11-25", first)
    s = server({CHANGELOG_PATH: body(text.encode())})
    answer = answer_of(run(scratch(tmp_path), "--base", s.base, "check"))
    assert answer["result"] == "could not ask" and answer["newest"] == ""


def test_a_missing_heading_and_an_error_status(tmp_path, server):
    s = server({CHANGELOG_PATH: body(b"# Changelog\n\nnothing here\n")})
    folder = scratch(tmp_path)
    answer = answer_of(run(folder, "--base", s.base, "check"))
    assert answer["result"] == "could not ask" and answer["reason"] == "The newest version could not be read from GitHub's answer."
    s.routes[CHANGELOG_PATH] = body(b"oops", status=500)
    answer = answer_of(run(folder, "--base", s.base, "check"))
    assert answer["result"] == "could not ask" and answer["reason"] == "GitHub answered with HTTP 500."
    assert answer["installed"] == "0.8.1" and answer["newest"] == ""


def test_an_unreadable_installed_version(tmp_path, server):
    s = server({CHANGELOG_PATH: body(CHANGELOG.encode())})
    folder = scratch(tmp_path)
    (folder / "pyproject.toml").write_text('[project]\nversion = "0.8"\n', "utf-8")
    answer = answer_of(run(folder, "--base", s.base, "check"))
    assert answer["result"] == "could not ask" and "installed version" in answer["reason"]
    assert s.seen == []  # nothing is asked before the installed version is known


def test_the_changes_are_plain_text_and_capped():
    huge = "## 0.9.0 - 2026-11-25\n\n" + "\n".join(f"* line {i} \x1b[31mred\x1b[0m \u202eabc" for i in range(5000))
    huge += "\n\n## 0.8.1 - 2026-11-20\n\n* old\n"
    text = cu.changes_between(cu.plain(huge), "0.8.1")
    assert len(text) <= cu.CHANGES_CAP + 4 and text.endswith("\n...")
    assert "\x1b" not in text and "\u202e" not in text and "old" not in text
    assert cu.changes_between(CHANGELOG, "0.8.2") == "0.9.0 - 2026-11-25\nUpdates\n\n* Help > Check for updates... looks for a newer version."
    assert cu.changes_between(CHANGELOG, "0.0.1").count(" - 2026-") == 4


def test_entries_end_at_a_heading_of_another_kind():
    text = "## 0.9.0 - 2026-11-25\n\n* a\n\n## Notes\n\n## 0.8.0 - 2026-11-01\n"
    assert [v for v, _d, _b in cu.entries(text)] == ["0.9.0"]


# ---------------------------------------------------------------- download


def a_zip(size: int = 300_000) -> bytes:
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_STORED) as z:
        z.writestr("taslation-0.9.0/pyproject.toml", 'version = "0.9.0"\n')
        z.writestr("taslation-0.9.0/filler.bin", bytes(range(256)) * (size // 256))
    return data.getvalue()


def test_a_download_comes_whole_with_its_progress(tmp_path, server):
    data = a_zip()
    s = server({zip_path("0.9.0"): redirect("/codeload/v0.9.0.zip"), "/codeload/v0.9.0.zip": body(data)})
    to = tmp_path / "into"
    to.mkdir()
    result = run(scratch(tmp_path), "--base", s.base, "download", "--version", "0.9.0", "--to", str(to))
    assert result.returncode == cu.DOWNLOADED, result.stderr
    target = to / "taslation-0.9.0.zip"
    assert result.stdout.strip() == str(target) and target.read_bytes() == data
    assert sorted(p.name for p in to.iterdir()) == ["taslation-0.9.0.zip"]
    assert "100 % (0.3 of 0.3 MB)" in result.stderr and "Downloading TASlation 0.9.0 from GitHub" in result.stderr
    for request in s.seen:
        headers = dict(request["headers"])
        assert headers["User-Agent"] == "TASlation-update-check" and "?" not in request["path"]
        assert "0.8.1" not in json.dumps(request)


def test_a_download_goes_on_where_it_broke_off(tmp_path, server):
    data = a_zip(400_000)
    calls = []

    def flaky(h):
        calls.append(h.headers.get("Range"))
        if len(calls) == 1:
            h.send_response(200)
            h.send_header("Content-Length", str(len(data)))
            h.end_headers()
            h.wfile.write(data[:150_000])
            h.wfile.flush()
            h.close_connection = True
            h.connection.shutdown(socket.SHUT_RDWR)
            return
        start = int(h.headers["Range"].split("=")[1].rstrip("-"))
        h.send_response(206)
        h.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
        h.send_header("Content-Length", str(len(data) - start))
        h.end_headers()
        h.wfile.write(data[start:])
    s = server({zip_path("0.9.0"): flaky})
    said = io.StringIO()
    target = cu.download("0.9.0", tmp_path, cu.Place(s.base), wait_s=0, progress=cu.Progress(said))
    assert target.read_bytes() == data
    assert calls[0] is None and calls[1].startswith("bytes=") and int(calls[1][6:-1]) > 0


def test_a_server_without_ranges_starts_it_anew(tmp_path, server):
    data = a_zip()
    (tmp_path / "taslation-0.9.0.zip.part").write_bytes(b"not the start of it")
    s = server({zip_path("0.9.0"): body(data)})  # (a 200 for a Range: the whole file)
    assert cu.download("0.9.0", tmp_path, cu.Place(s.base), wait_s=0,
                       progress=cu.Progress(io.StringIO())).read_bytes() == data


def test_three_tries_then_it_stops(tmp_path, server, monkeypatch):
    s = server({zip_path("0.9.0"): body(b"busy", status=503)})
    waits = []
    monkeypatch.setattr(cu.time, "sleep", waits.append)
    with pytest.raises(cu.AskError, match="Tried 3 times"):
        cu.download("0.9.0", tmp_path, cu.Place(s.base), progress=cu.Progress(io.StringIO()))
    assert waits == [15.0, 15.0] and len(s.seen) == 3


def test_a_refused_download_is_not_tried_again(tmp_path, server):
    s = server({})  # 404 for everything
    to = tmp_path / "into"
    to.mkdir()
    began = time.monotonic()
    result = run(scratch(tmp_path), "--base", s.base, "download", "--version", "0.9.0", "--to", str(to))
    assert result.returncode == cu.NOT_DOWNLOADED and "HTTP 404" in result.stderr and result.stdout == ""
    assert len(s.seen) == 1 and time.monotonic() - began < 10 and list(to.iterdir()) == []


def test_what_is_no_zip_is_thrown_away(tmp_path, server):
    s = server({zip_path("0.9.0"): body(b"<html>not a zip</html>")})
    with pytest.raises(cu.AskError, match="no ZIP"):
        cu.download("0.9.0", tmp_path, cu.Place(s.base), wait_s=0, progress=cu.Progress(io.StringIO()))
    assert list(tmp_path.iterdir()) == []


def test_an_oversized_zip_stops_at_once(tmp_path, server, monkeypatch):
    monkeypatch.setattr(cu, "ZIP_CAP", 100_000)
    s = server({zip_path("0.9.0"): body(a_zip(), length=False)})
    with pytest.raises(cu.TooLarge):
        cu.download("0.9.0", tmp_path, cu.Place(s.base), wait_s=0, progress=cu.Progress(io.StringIO()))
    assert len(s.seen) == 1 and list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("version", ["0.9", "v0.9.0", "../0.9.0", "0.9.0/../../x", "0.9.0?x=1"])
def test_a_version_must_be_x_y_z(tmp_path, server, version):
    s = server({})
    result = run(scratch(tmp_path), "--base", s.base, "download", "--version", version, "--to", str(tmp_path))
    assert result.returncode == cu.NOT_DOWNLOADED and s.seen == []
