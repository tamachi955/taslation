"""setup_models.py's downloads against a small HTTP server on this machine: percent and MB as a file comes, and a
file taken up from where it stopped (HTTP Range) - after a dropped connection in the same run, or from the part an
earlier run left - with its checksum over the whole of it; a server that ignores Range starts the file anew."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from taslation import translator_install as ti

ROOT = Path(__file__).resolve().parent.parent
DATA = bytes(range(256)) * 400  # 102,400 bytes


def load():
    spec = importlib.util.spec_from_file_location("setup_models_downloads", ROOT / "setup_models.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.RETRY_WAIT_S = 0.0
    module.CHUNK = 4096
    return module


class Files(ThreadingHTTPServer):
    """Files by path; ``ranges`` whether Range is honoured, ``drops`` how many bytes the next answers longer than
    that send before the connection is cut (one entry per answer), ``fail`` status codes for the next answers; ``asked`` each
    request's path and Range."""

    daemon_threads = True

    def __init__(self, files: dict[str, bytes]):
        super().__init__(("127.0.0.1", 0), Handler)
        self.files = files
        self.ranges = True
        self.drops: list[int] = []
        self.fail: list[int] = []
        self.asked: list[tuple[str, str | None]] = []
        self.sent = 0

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/{path}"


class Handler(BaseHTTPRequestHandler):
    server: Files
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_GET(self):
        name = self.path.lstrip("/")
        wanted = self.headers.get("Range")
        self.server.asked.append((name, wanted))
        if self.server.fail:
            self.send_error(self.server.fail.pop(0))
            return
        if name not in self.server.files:
            self.send_error(404)
            return
        data = self.server.files[name]
        start = 0
        if wanted and self.server.ranges:
            start = int(wanted.split("=", 1)[1].split("-", 1)[0])
            if start >= len(data):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(data)}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
        else:
            self.send_response(200)
        body = data[start:]
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Accept-Ranges", "bytes" if self.server.ranges else "none")
        self.end_headers()
        if self.server.drops and self.server.drops[0] < len(body):  # (a file shorter than that comes whole)
            body = body[:self.server.drops.pop(0)]
            self.close_connection = True
        self.wfile.write(body)
        self.wfile.flush()
        self.server.sent += len(body)


@pytest.fixture
def server():
    files = Files({"model.bin": DATA, "small.txt": b"licence text\n"})
    thread = threading.Thread(target=files.serve_forever, daemon=True)
    thread.start()
    yield files
    files.shutdown()
    files.server_close()


@pytest.fixture
def sm(monkeypatch):
    module = load()
    monkeypatch.setattr(module, "_progress", False)
    return module


def test_a_whole_file_comes_in_one_go_and_only_then_is_in_place(sm, server, tmp_path):
    dest = tmp_path / "model.bin"
    sm._fetch(server.url("model.bin"), dest)
    assert dest.read_bytes() == DATA and [p.name for p in tmp_path.iterdir()] == ["model.bin"]
    assert server.asked == [("model.bin", None)]


def test_a_part_an_earlier_run_left_is_taken_up_where_it_stopped(sm, server, tmp_path):
    dest = tmp_path / "model.bin"
    (tmp_path / "model.bin.part").write_bytes(DATA[:60_000])
    sm._fetch(server.url("model.bin"), dest)
    assert dest.read_bytes() == DATA
    assert server.asked == [("model.bin", "bytes=60000-")] and server.sent == len(DATA) - 60_000


def test_a_connection_that_drops_is_taken_up_again_in_the_same_run(sm, server, tmp_path, capsys):
    server.drops = [30_000, 20_000]
    dest = tmp_path / "model.bin"
    sm._fetch(server.url("model.bin"), dest)
    assert dest.read_bytes() == DATA
    assert [r for _p, r in server.asked] == [None, "bytes=30000-", "bytes=50000-"]
    out = capsys.readouterr().out
    assert out.count("the connection broke off") == 2 and "going on from 0.0 MB (try 2 of 4)" in out


def test_a_server_that_ignores_range_starts_the_file_anew(sm, server, tmp_path):
    server.ranges = False
    (tmp_path / "model.bin.part").write_bytes(b"\xff" * 1000)  # what is there is not added to
    dest = tmp_path / "model.bin"
    sm._fetch(server.url("model.bin"), dest)
    assert dest.read_bytes() == DATA


def test_a_part_already_whole_is_not_downloaded_again(sm, server, tmp_path):
    (tmp_path / "model.bin.part").write_bytes(DATA)
    sm._fetch(server.url("model.bin"), tmp_path / "model.bin")
    assert (tmp_path / "model.bin").read_bytes() == DATA and server.sent == 0


def test_a_part_longer_than_the_file_is_thrown_away(sm, server, tmp_path):
    (tmp_path / "model.bin.part").write_bytes(DATA + b"more")
    sm._fetch(server.url("model.bin"), tmp_path / "model.bin")
    assert (tmp_path / "model.bin").read_bytes() == DATA
    assert [r for _p, r in server.asked] == [f"bytes={len(DATA) + 4}-", None]


def test_too_many_drops_fail_and_the_part_waits_for_the_next_run(sm, server, tmp_path):
    server.drops = [10_000] * (sm.RETRIES + 1)
    dest = tmp_path / "model.bin"
    with pytest.raises(sm.IncompleteDownload, match="model.bin arrived incomplete"):
        sm._fetch(server.url("model.bin"), dest)
    assert not dest.exists() and (tmp_path / "model.bin.part").stat().st_size == 10_000 * (sm.RETRIES + 1)
    sm._fetch(server.url("model.bin"), dest)  # the next run
    assert dest.read_bytes() == DATA


def test_a_missing_file_is_not_asked_for_again_but_a_busy_server_is(sm, server, tmp_path):
    with pytest.raises(urllib.error.HTTPError):
        sm._fetch(server.url("gone.bin"), tmp_path / "gone.bin")
    assert len(server.asked) == 1
    server.asked.clear()
    server.fail = [503]
    sm._fetch(server.url("small.txt"), tmp_path / "small.txt")
    assert len(server.asked) == 2 and (tmp_path / "small.txt").read_bytes() == b"licence text\n"


def test_a_full_disk_is_not_tried_again(sm, tmp_path, monkeypatch):
    calls = []

    def full(request, timeout):
        calls.append(request)
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(sm.urllib.request, "urlopen", full)
    with pytest.raises(OSError):
        sm._fetch("https://example.invalid/f", tmp_path / "f")
    assert len(calls) == 1


def test_the_percent_and_the_mb_are_said_as_it_comes(sm, server, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(sm, "QUIET_BYTES", 0)
    sm._fetch(server.url("model.bin"), tmp_path / "model.bin")
    lines = capsys.readouterr().out.splitlines()
    shown = [line for line in lines if "%" in line]
    assert shown[-1] == "  100 %  (0.1 of 0.1 MB)"
    assert 8 <= len(shown) <= 11 and all(" of 0.1 MB)" in line for line in shown)  # (a line every 10 %)


def test_a_small_file_comes_without_progress_lines(sm, server, tmp_path, capsys):
    sm._fetch(server.url("small.txt"), tmp_path / "small.txt")
    assert capsys.readouterr().out == "Downloading small.txt ...\n"


class Console(io.StringIO):
    def isatty(self):
        return True


def test_in_a_console_one_line_is_written_over():
    sm = load()
    stream = Console()
    shown = sm._Shown(stream=stream)
    for done in range(0, 3_000_001, 300_000):
        shown.update(done, 3_000_000)
    shown.end()
    text = stream.getvalue()
    assert text.count("\r") == 11 and text.endswith("\n") and text.count("\n") == 1
    assert "\r  100 %  (3.0 of 3.0 MB)" in text


def test_the_window_s_run_gets_no_progress_text_of_ours(sm, server, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(sm, "_progress", True)
    monkeypatch.setattr(sm, "QUIET_BYTES", 0)
    sm._fetch(server.url("model.bin"), tmp_path / "model.bin")
    assert "%" not in capsys.readouterr().out


# ---- PLaMo: taken up again, its checksum over the whole file

@pytest.fixture
def plamo(server, monkeypatch, tmp_path):
    licence = b"licence\n"
    server.files.update({"LICENSE/en": licence, ti.PLAMO_FILE: DATA})
    monkeypatch.setattr(ti, "plamo_url", lambda name: server.url(name))
    monkeypatch.setattr(ti, "PLAMO_LICENCE_FILES", (("LICENSE/en", hashlib.sha256(licence).hexdigest(), "LICENSE"),))
    monkeypatch.setattr(ti, "PLAMO_BYTES", len(DATA))
    monkeypatch.setattr(ti, "PLAMO_SHA256", hashlib.sha256(DATA).hexdigest())
    return server


def test_plamo_taken_up_after_a_drop_passes_its_checksum(sm, plamo, tmp_path, capsys):
    plamo.drops = [40_000]
    gguf = sm.download_plamo(tmp_path / "models", threading.Event())
    assert gguf.read_bytes() == DATA and not list(gguf.parent.glob("*.part"))
    assert [r for p, r in plamo.asked if p == ti.PLAMO_FILE] == [None, "bytes=40000-"]
    assert "the connection broke off" in capsys.readouterr().out


def test_plamo_from_a_part_of_another_file_fails_its_checksum_and_is_removed(sm, plamo, tmp_path):
    folder = ti.plamo_dir(tmp_path / "models")
    folder.mkdir(parents=True)
    (folder / (ti.PLAMO_FILE + ".part")).write_bytes(b"\x00" * 50_000)  # not the start of this file
    with pytest.raises(OSError, match="failed its checksum"):
        sm.download_plamo(tmp_path / "models", threading.Event())
    assert not list(folder.glob("*.part")) and not list(folder.glob("*.gguf"))


def test_plamo_s_progress_says_percent_and_mb(sm, plamo, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(sm, "QUIET_BYTES", 0)
    sm.download_plamo(tmp_path / "models", threading.Event())
    shown = [line for line in capsys.readouterr().out.splitlines() if "%" in line]
    assert shown[-1] == "  100 %  (0.1 of 0.1 MB)" and len(shown) >= 15  # (every 5 %)


# ---- ollama's own progress in install.ps1's run

def test_the_installer_s_run_shows_ollama_s_percent_and_mb(sm, capsys, monkeypatch):
    monkeypatch.setattr(sm, "_brief", True)
    seen = sm._ollama_progress("pull")
    for line in ("pulling manifest", "pulling 4f2b: 10% |##  | 330 MB/3.3 GB", "pulling 4f2b: 10% |##  | 340 MB/3.3 GB",
                 "pulling 4f2b: 55% |#####| 1.8 GB/3.3 GB", "verifying sha256 digest"):
        seen(line)
    seen.end()
    lines = capsys.readouterr().out.splitlines()
    assert lines == ["   10 %  (330.0 of 3,300.0 MB)", "   55 %  (1,800.0 of 3,300.0 MB)"]


def test_by_hand_ollama_s_lines_are_passed_on_as_they_are(sm, capsys, monkeypatch):
    monkeypatch.setattr(sm, "_brief", False)
    seen = sm._ollama_progress("pull")
    seen("pulling 4f2b: 10% 330 MB/3.3 GB")
    assert capsys.readouterr().out == "  pulling 4f2b: 10% 330 MB/3.3 GB\n"


@pytest.mark.parametrize(("text", "sizes"), [
    ("pulling 4f2b: 45% 1.5 GB/3.3 GB", (1500.0, 3300.0)),
    ("12 MB / 27 MB", (12.0, 27.0)),
    ("512 KiB/1 MiB", (0.524288, 1.048576)),
    ("pulling manifest", None),
])
def test_sizes_of_ollama_s_lines(text, sizes):
    found = ti.sizes_of(text)
    if sizes is None:
        assert found is None
    else:
        assert found == pytest.approx(sizes)


def test_progress_text():
    assert ti.progress_text(45, 12.34, 27.0) == "   45 %  (12.3 of 27.0 MB)"
    assert ti.progress_text(7) == "    7 %"
    assert ti.progress_text(None, 12.3) == "  12.3 MB"
    assert ti.progress_text(130, 1, 1) == "  100 %  (1.0 of 1.0 MB)"
