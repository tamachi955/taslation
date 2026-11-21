#!/usr/bin/env python
"""Looks on GitHub for a newer TASlation, and downloads one, when a person asks for it.

    python check_update.py check
    python check_update.py download --version X.Y.Z --to DIR

A program of its own beside setup_models.py, outside TASlation's offline guard: the window (Help > Check for
updates..., and the look once a day at its start for who turned it on) and update.ps1 run it as a process of their own
with the program files' Python; TASlation's own process never imports it and never connects anywhere but Ollama on
this computer. Standard library only; nothing of TASlation is imported.

``check`` asks for the first 16 KB of one file, the project's CHANGELOG.md on GitHub (`CHANGELOG_URL`,
`CHANGELOG_PART`): the request stays as small however long the changelog grows. The newest version is its first
``## X.Y.Z - YYYY-MM-DD`` heading; the installed one is the ``version`` line of the pyproject.toml beside this file, as
update.ps1 reads it. It prints one line of JSON: ``result`` ("newer", "up to date" or "could not ask"), ``installed``,
``installed_date`` (its entry's date in the changelog, "" when it has none or it is not in what came), ``newest``,
``date`` (the newest one's), ``newer``, ``changes`` (the changelog's entries newer than the installed version, as plain
text, at most `CHANGES_CAP` characters; for someone so many versions behind that the installed version's entry is not
in the first 16 KB, the entries that came whole and then `OLDER_CHANGES`) and ``reason`` (one plain sentence when it
could not ask). Its exit code says the same: `NEWER`, `UP_TO_DATE`, `COULD_NOT_ASK`.

``download`` gets that version's ZIP (`ZIP_URL`, about 4.6 MB) into DIR as ``taslation-X.Y.Z.zip``: first as a
``.part`` file, tried `ATTEMPTS` times `RETRY_WAIT_S` seconds apart as the installer's downloads are, going on from
where it broke off where the server allows (HTTP Range), not tried again when the server refuses it (401, 403, 404,
410). Once the file has come, every entry of it is read back (`whole_zip`): a file that does not open as a ZIP or has
an entry that does not read back whole - two builds of GitHub's archive joined by a download taken up again, a body cut
short with no length said - counts as a broken download, thrown away and asked for whole on the next try, within the
same tries. Its progress, in percent and MB, goes to stderr; the path of the ZIP, once it is whole, to stdout.

What a request is: one HTTPS GET of one of the two fixed addresses, with a fixed User-Agent (`USER_AGENT`: no version,
no system, no Python) and a Range header (the check's ``bytes=0-16383``; a download taken up again), no query string, no cookie, no credential, no proxy, nothing about the person, the computer or
the installation. GitHub sees the IP address and the time, as any site one opens does. A redirect is followed only to
`HOSTS` over HTTPS; any other address stops the run before it is asked. An answer larger than its cap
(`CHANGELOG_CAP`, `ZIP_CAP`) stops it too, and so do the timeouts (`CONNECT_S` to connect; the check `CHECK_TOTAL_S`
in all). A version is taken only as ``X.Y.Z`` and compared as numbers; anything else is "could not ask". The
changelog's text is foreign text: it is only printed, never run, never used as a path or an address.

For tests only, ``--base http://127.0.0.1:PORT`` (or ``localhost``) sends both requests to that address instead; any
other base is refused. No setting and no environment variable changes where this program asks.
"""

from __future__ import annotations

import argparse
import http.client
import json
import re
import socket
import ssl
import sys
import time
import zipfile
from pathlib import Path
from urllib.parse import SplitResult, urljoin, urlsplit

ROOT = Path(__file__).resolve().parent
CHANGELOG_URL = "https://raw.githubusercontent.com/tamachi955/taslation/main/CHANGELOG.md"
ZIP_URL = "https://github.com/tamachi955/taslation/archive/refs/tags/v{version}.zip"
HOSTS = frozenset({"github.com", "codeload.github.com", "raw.githubusercontent.com"})
TEST_HOSTS = frozenset({"127.0.0.1", "localhost"})
USER_AGENT = "TASlation-update-check"
CHANGELOG_PART = 16 * 1024  # bytes: the check asks for the changelog's beginning only (Range: bytes=0-16383)
CHANGELOG_CAP = 1 << 20  # bytes: a server that ignores Range and sends the whole file
ZIP_CAP = 60 << 20
CONNECT_S = 5.0
CHECK_TOTAL_S = 10.0  # the whole check, connecting and reading
READ_S = 30.0  # a download that gives nothing this long counts as broken off
ATTEMPTS = 3  # the download, as install.ps1's downloads: three tries in all ...
RETRY_WAIT_S = 15.0  # ... this far apart
REFUSED_HTTP = frozenset({401, 403, 404, 410})  # trying again does not help
REDIRECTS = (301, 302, 303, 307, 308)
MAX_REDIRECTS = 5
CHANGES_CAP = 6000  # characters of the changelog's entries in the answer
OLDER_CHANGES = "The older changes are in CHANGELOG.md."  # the last line of changes cut short by CHANGELOG_PART
CHUNK = 64 * 1024
PROGRESS_STEP = 10  # percent between progress lines when stderr is no console

UP_TO_DATE, NEWER, COULD_NOT_ASK = 0, 10, 20  # check
DOWNLOADED, NOT_DOWNLOADED = 0, 20  # download

_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
_HEADING = re.compile(r"^## (\S+) - ([0-9]{4}-[0-9]{2}-[0-9]{2})[ \t]*$")
_PROJECT_VERSION = re.compile(r'^\s*version\s*=\s*"([^"]*)"')
_CONTENT_RANGE = re.compile(r"bytes ([0-9]+)-([0-9]+)/([0-9]+|\*)")
_CONTROL = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2066-\u2069]")


class AskError(Exception):
    """What went wrong, as one plain sentence for a person."""


class Refused(AskError):
    """The server refused the file or does not have it (`REFUSED_HTTP`): trying again does not help."""


class Broken(AskError):
    """What came is no whole ZIP (`whole_zip`): thrown away, and the file asked for whole on the next try."""


BROKEN_ZIP = "What came from GitHub is no whole ZIP file."


class TooLarge(AskError):
    """The answer is larger than its cap: trying again does not help."""


# ---------------------------------------------------------------- versions and the changelog


def version_of(text: str) -> tuple[int, int, int] | None:
    """*text* as (X, Y, Z) when it is exactly ``X.Y.Z`` (ASCII digits only), else None."""
    if not isinstance(text, str) or _VERSION.fullmatch(text) is None:
        return None
    x, y, z = text.split(".")
    return int(x), int(y), int(z)


def installed_version(root: Path = ROOT) -> str:
    """The version of the program files beside this file: pyproject.toml's ``version`` line, as update.ps1 reads it."""
    try:
        lines = (Path(root) / "pyproject.toml").read_text("utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        raise AskError("The installed version could not be read: pyproject.toml is not in the TASlation folder.") from None
    for line in lines:
        m = _PROJECT_VERSION.match(line)
        if m:
            if version_of(m.group(1)) is None:
                break
            return m.group(1)
    raise AskError("The installed version could not be read from pyproject.toml.")


def plain(text: str) -> str:
    """Foreign text made plain: line ends as ``\\n``, no control or direction characters, no trailing spaces."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(_CONTROL.sub("", line).rstrip() for line in text.split("\n"))


def entries(changelog: str) -> list[tuple[str, str, str]]:
    """The changelog's entries in its order: (version, date, text under the heading). Every ``## `` heading must be
    ``## X.Y.Z - YYYY-MM-DD``; the first one that is not ends the list (an entry of another kind is never counted)."""
    found: list[tuple[str, str, list[str]]] = []
    for line in changelog.split("\n"):
        if line.startswith("## "):
            m = _HEADING.match(line)
            if m is None or version_of(m.group(1)) is None:
                break
            found.append((m.group(1), m.group(2), []))
        elif found:
            found[-1][2].append(line)
    return [(version, date, "\n".join(body).strip("\n")) for version, date, body in found]


def changes_between(changelog: str, installed: str, cap: int = CHANGES_CAP) -> str:
    """The text of the entries newer than *installed*, newest first, each under its heading, at most *cap*
    characters (cut at a line's end, then "...")."""
    return _changes_text(entries(changelog), installed, cap)


def _changes_text(found: list[tuple[str, str, str]], installed: str, cap: int) -> str:
    floor = version_of(installed)
    parts = []
    for version, date, body in found:
        number = version_of(version)
        if floor is not None and number is not None and number <= floor:
            break
        parts.append(f"{version} - {date}\n{body}".rstrip())
    text = "\n\n".join(parts)
    if len(text) <= cap:
        return text
    cut = text.rfind("\n", 0, cap)
    return text[: cut if cut > 0 else cap].rstrip() + "\n..."


def verdict(changelog: str, installed: str, whole: bool = True) -> dict:
    """What the changelog says against the installed version: the answer `check` prints. AskError when the newest
    version cannot be read from it. *whole*: the changelog came whole; else it is its beginning (`fetch_changelog`),
    and when no entry at or below the installed version is in it, the changes are the entries that came whole (the
    last one may be cut where the part ends: left out, unless it is the only one) and then `OLDER_CHANGES`."""
    found = entries(changelog)
    if not found:
        raise AskError("The newest version could not be read from GitHub's answer.")
    newest, date, _body = found[0]
    floor = version_of(installed)
    newer = version_of(newest) > floor  # (both are X.Y.Z here)
    installed_date = next((day for version, day, _text in found if version == installed), "")
    changes = ""
    if newer and (whole or any(version_of(version) <= floor for version, _day, _text in found)):
        changes = _changes_text(found, installed, CHANGES_CAP)
    elif newer:
        came = found[:-1] if len(found) > 1 else found
        changes = _changes_text(came, installed, CHANGES_CAP - len(OLDER_CHANGES) - 2) + "\n\n" + OLDER_CHANGES
    return {"result": "newer" if newer else "up to date", "installed": installed, "installed_date": installed_date,
            "newest": newest, "date": date, "newer": newer, "changes": changes, "reason": ""}


# ---------------------------------------------------------------- where a request may go


class Place:
    """Where requests go: GitHub over HTTPS (`HOSTS`), or for a test the loopback address *base*
    (``http://127.0.0.1:PORT`` or ``localhost``) and nothing else."""

    def __init__(self, base: str | None = None):
        self.base: SplitResult | None = None
        if base is not None:
            parts = urlsplit(base)
            try:
                port = parts.port
            except ValueError:
                port = None
            if (parts.scheme != "http" or (parts.hostname or "") not in TEST_HOSTS or port is None
                    or parts.username or parts.password or parts.path not in ("", "/") or parts.query
                    or parts.fragment):
                raise AskError("A test address must be http://127.0.0.1:PORT or http://localhost:PORT.")
            self.base = parts

    def address(self, url: str) -> str:
        """*url* (one of the fixed addresses) as this place asks for it."""
        if self.base is None:
            return url
        parts = urlsplit(url)
        return parts._replace(scheme=self.base.scheme, netloc=self.base.netloc).geturl()

    def check(self, url: str) -> SplitResult:
        """*url* taken apart when a request may go there; AskError, before anything is asked, when it may not."""
        parts = urlsplit(url)
        try:
            port = parts.port
        except ValueError:
            port = -1
        host = (parts.hostname or "").lower()
        if self.base is None:
            allowed = parts.scheme == "https" and host in HOSTS and port in (None, 443)
        else:
            allowed = parts.scheme == "http" and host == self.base.hostname and port == self.base.port
        if not allowed or parts.username or parts.password:
            raise AskError(f"GitHub sent the request on to another address ({host or '?'}), which is not asked.")
        return parts


def _connection(parts: SplitResult, timeout: float) -> http.client.HTTPConnection:
    if parts.scheme == "https":
        return http.client.HTTPSConnection(parts.hostname, parts.port or 443, timeout=timeout,
                                           context=ssl.create_default_context())
    return http.client.HTTPConnection(parts.hostname, parts.port, timeout=timeout)


def _remaining(deadline: float | None, most: float) -> float:
    if deadline is None:
        return most
    left = deadline - time.monotonic()
    if left <= 0:
        raise AskError("GitHub did not answer in time.")
    return min(most, left)


class Answer:
    """An answer being read: its connection, the connection's socket (kept: http.client lets go of it when the server
    closes after the answer) and the response, whose status is not a redirect."""

    def __init__(self, conn: http.client.HTTPConnection, sock: socket.socket, resp: http.client.HTTPResponse):
        self.conn, self.sock, self.resp = conn, sock, resp
        self.status = resp.status

    def header(self, name: str) -> str:
        return self.resp.getheader(name) or ""

    def read(self, most: int, deadline: float | None = None, read_s: float = READ_S) -> bytes:
        """What comes next, at most *most* bytes, after one wait of at most *read_s* (and no later than
        *deadline*)."""
        self.sock.settimeout(_remaining(deadline, read_s))
        return self.resp.read1(most)

    def close(self) -> None:
        self.resp.close()
        self.conn.close()


def open_url(url: str, place: Place, headers: tuple[tuple[str, str], ...] = (), deadline: float | None = None,
             read_s: float = READ_S) -> Answer:
    """One GET of *url*, redirects followed as far as *place* allows (`MAX_REDIRECTS`). The request carries the
    Host, `USER_AGENT`, ``Accept: */*``, ``Accept-Encoding: identity`` and *headers* (a download's Range), nothing
    else."""
    for _hop in range(MAX_REDIRECTS + 1):
        parts = place.check(url)
        conn = _connection(parts, _remaining(deadline, CONNECT_S))
        try:
            conn.connect()
            sock = conn.sock
            sock.settimeout(_remaining(deadline, read_s))
            conn.putrequest("GET", parts.path or "/", skip_accept_encoding=True)
            conn.putheader("User-Agent", USER_AGENT)
            conn.putheader("Accept", "*/*")
            conn.putheader("Accept-Encoding", "identity")
            for name, value in headers:
                conn.putheader(name, value)
            conn.endheaders()
            resp = conn.getresponse()
        except BaseException:
            conn.close()
            raise
        if resp.status not in REDIRECTS:
            return Answer(conn, sock, resp)
        location = resp.getheader("Location") or ""
        resp.close()
        conn.close()
        if not location:
            raise AskError("GitHub answered with a redirect that names no address.")
        url = urljoin(url, location)
    raise AskError("GitHub sent the request on too many times.")


def too_large(cap: int) -> TooLarge:
    return TooLarge(f"GitHub's answer is larger than expected (more than {cap >> 20} MB).")


def read_capped(answer: Answer, cap: int, deadline: float | None = None, read_s: float = READ_S) -> bytes:
    """The body of *answer*, at most *cap* bytes (TooLarge beyond), within *deadline*; AskError when less comes than
    the answer said."""
    length = answer.header("Content-Length")
    said = int(length) if length.strip().isdigit() else None
    if said is not None and said > cap:
        raise too_large(cap)
    data = bytearray()
    while True:
        piece = answer.read(min(CHUNK, cap + 1 - len(data)), deadline, read_s)
        if not piece:
            if said is not None and len(data) != said:
                raise AskError("The connection to GitHub broke off.")
            return bytes(data)
        data += piece
        if len(data) > cap:
            raise too_large(cap)


def failure_sentence(error: BaseException, writing: bool = False) -> str:
    """A failure as one plain sentence (*writing*: an error of the disk is possible too)."""
    if isinstance(error, AskError):
        return str(error)
    if isinstance(error, (socket.timeout, TimeoutError)):
        return "GitHub did not answer in time."
    if isinstance(error, ssl.SSLError):
        return "The secure connection to GitHub could not be made."
    if isinstance(error, socket.gaierror):
        return "GitHub could not be reached: is this computer online?"
    if isinstance(error, ConnectionRefusedError):
        return "GitHub could not be reached."
    if isinstance(error, (ConnectionError, http.client.HTTPException)):
        return "The connection to GitHub broke off."
    if writing and isinstance(error, OSError):
        return f"The ZIP could not be written ({error.strerror or type(error).__name__})."
    return "GitHub could not be reached."


# ---------------------------------------------------------------- check


def _part_is_whole(content_range: str) -> bool:
    """Whether a 206's *content_range* is the whole file; AskError when it is not the file's beginning."""
    m = _CONTENT_RANGE.fullmatch(content_range.strip())
    if m is None or int(m.group(1)) != 0:
        raise AskError("The newest version could not be read from GitHub's answer.")
    return m.group(3) != "*" and int(m.group(2)) + 1 >= int(m.group(3))


def fetch_changelog(place: Place, total_s: float | None = None) -> tuple[str, bool]:
    """The beginning of the changelog on GitHub as text, and whether that is the whole file, within *total_s*
    seconds in all (`CHECK_TOTAL_S` when not given). One GET with ``Range: bytes=0-16383`` (`CHANGELOG_PART`): a 206
    with that part is the usual answer; a 200 with the whole file, from a server that ignores Range, is taken too
    (`CHANGELOG_CAP`). A part may end inside a line, or inside a character: its last line without a line end is left
    out."""
    total_s = CHECK_TOTAL_S if total_s is None else total_s
    deadline = time.monotonic() + total_s
    answer = open_url(place.address(CHANGELOG_URL), place, (("Range", f"bytes=0-{CHANGELOG_PART - 1}"),),
                      deadline=deadline, read_s=total_s)
    try:
        if answer.status not in (200, 206):
            raise AskError(f"GitHub answered with HTTP {answer.status}.")
        whole = answer.status == 200 or _part_is_whole(answer.header("Content-Range"))
        data = read_capped(answer, CHANGELOG_CAP, deadline, total_s)
    finally:
        answer.close()
    if not whole:
        data = data[: data.rfind(b"\n") + 1]
    return plain(data.decode("utf-8", "replace")), whole


def check(place: Place, root: Path = ROOT) -> dict:
    """The answer of ``check``: never raises; a failure is "could not ask" with its reason."""
    installed = ""
    try:
        installed = installed_version(root)
        text, whole = fetch_changelog(place)
        return verdict(text, installed, whole)
    except Exception as e:  # noqa: BLE001 - every failure is one sentence, never a stack
        return {"result": "could not ask", "installed": installed, "installed_date": "", "newest": "", "date": "",
                "newer": False, "changes": "", "reason": failure_sentence(e)}


# ---------------------------------------------------------------- download


class Progress:
    """A download's progress on stderr: in a console one line written over, else a line every `PROGRESS_STEP`
    percent (every MB when the size is not said)."""

    def __init__(self, stream=None):
        self.stream = stream if stream is not None else sys.stderr
        try:
            self.over = bool(self.stream.isatty())
        except (AttributeError, ValueError, OSError):
            self.over = False
        self.last: tuple | None = None

    def show(self, done: int, total: int | None) -> None:
        if total:
            percent = min(100, done * 100 // total)
            key: tuple = ("%", percent if self.over else percent // PROGRESS_STEP)
            text = f"  {percent:3d} % ({done / 1e6:.1f} of {total / 1e6:.1f} MB)"
        else:
            key = ("MB", int(done / 1e5) if self.over else int(done / 1e6))
            text = f"  {done / 1e6:.1f} MB"
        if key == self.last:
            return
        self.last = key
        self._write(("\r" + text.ljust(36)) if self.over else text + "\n")

    def end(self) -> None:
        if self.over and self.last is not None:
            self._write("\n")
        self.last = None

    def _write(self, text: str) -> None:
        try:
            self.stream.write(text)
            self.stream.flush()
        except (OSError, ValueError):
            pass


def say(text: str) -> None:
    try:
        print(text, file=sys.stderr, flush=True)
    except (OSError, ValueError):
        pass


def _content_range_start(value: str | None) -> int | None:
    m = re.match(r"\s*bytes\s+(\d+)-", value or "")
    return int(m.group(1)) if m else None


def download_once(url: str, place: Place, part: Path, progress: Progress) -> None:
    """One try: *part* filled until the file is whole - added to from where it stopped when the server sends that
    part (206), else started anew. AskError (Refused for `REFUSED_HTTP`) when it does not come whole."""
    for _again in range(2):  # (a part kept that does not fit is thrown away, and the file asked for whole)
        have = part.stat().st_size if part.is_file() else 0
        answer = open_url(url, place, (("Range", f"bytes={have}-"),) if have else ())
        try:
            if answer.status in REFUSED_HTTP:
                raise Refused(f"GitHub has no ZIP of that version (HTTP {answer.status}).")
            fits = answer.status == 206 and have and _content_range_start(answer.header("Content-Range")) == have
            if have and answer.status in (206, 416) and not fits:
                part.unlink()
                continue
            if answer.status not in (200, 206):
                raise AskError(f"GitHub answered with HTTP {answer.status}.")
            start = have if fits else 0
            length = answer.header("Content-Length")
            total = start + int(length) if length.strip().isdigit() else None
            if (total or 0) > ZIP_CAP:
                raise too_large(ZIP_CAP)
            done = start
            with open(part, "ab" if start else "wb") as out:
                while True:
                    piece = answer.read(CHUNK)
                    if not piece:
                        break
                    done += len(piece)
                    if done > ZIP_CAP:
                        raise too_large(ZIP_CAP)
                    out.write(piece)
                    progress.show(done, total)
            if total is not None and done != total:
                raise AskError(f"The download broke off ({done / 1e6:.1f} of {total / 1e6:.1f} MB).")
            return
        finally:
            answer.close()
    raise AskError("The download could not be taken up again.")


def whole_zip(path: Path) -> bool:
    """Whether *path* opens as a ZIP and every entry in it reads back whole (`zipfile.ZipFile.testzip`: each entry's
    CRC). A download taken up again where it broke off can join two different builds of GitHub's archive into one file
    that still ends like a ZIP; this finds it."""
    try:
        with zipfile.ZipFile(path) as z:
            return z.testzip() is None
    except Exception:  # noqa: BLE001 - BadZipFile, zlib.error, EOFError, NotImplementedError, OSError: not whole
        return False


def download(version: str, folder: Path, place: Place, attempts: int = ATTEMPTS, wait_s: float = RETRY_WAIT_S,
             progress: Progress | None = None) -> Path:
    """The ZIP of *version* in *folder* (``taslation-X.Y.Z.zip``), tried *attempts* times *wait_s* apart; AskError
    when it still does not come. A file that came but is no whole ZIP (`whole_zip`) counts as a broken download: it
    is thrown away and asked for whole on the next try."""
    if version_of(version) is None:
        raise AskError("A version must be given as X.Y.Z.")
    folder = Path(folder)
    if not folder.is_dir():
        raise AskError("The folder to download into does not exist.")
    target = folder / f"taslation-{version}.zip"
    part = folder / (target.name + ".part")
    url = place.address(ZIP_URL.format(version=version))
    progress = progress or Progress()
    say(f"Downloading TASlation {version} from GitHub ...")
    for attempt in range(1, attempts + 1):
        try:
            download_once(url, place, part, progress)
            progress.end()
            if not whole_zip(part):
                raise Broken(BROKEN_ZIP)
            break
        except (Refused, TooLarge):
            progress.end()
            if part.exists():
                part.unlink()
            raise
        except Exception as e:  # noqa: BLE001 - the network or the disk: said, tried again
            progress.end()
            if isinstance(e, Broken):  # (nothing of it is taken up again: the next try asks for the file whole)
                try:
                    part.unlink(missing_ok=True)
                except OSError:
                    pass
            sentence = failure_sentence(e, writing=True)
            if attempt >= attempts:
                if isinstance(e, Broken):
                    raise AskError(f"The ZIP from GitHub did not come whole in {attempts} tries.") from None
                raise AskError(f"{sentence} Tried {attempts} times.") from None
            say(f"  Attempt {attempt} of {attempts}: {sentence} Trying again in {wait_s:g} seconds.")
            time.sleep(wait_s)
    part.replace(target)
    return target


# ---------------------------------------------------------------- the commands


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="check_update.py", description="Look on GitHub for a newer TASlation.")
    parser.add_argument("--base", help=argparse.SUPPRESS)  # tests only: http://127.0.0.1:PORT or localhost
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="ask GitHub for the newest version and print one line of JSON")
    get = commands.add_parser("download", help="download one version's ZIP")
    get.add_argument("--version", required=True)
    get.add_argument("--to", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        place = Place(args.base)
    except AskError as e:
        say(str(e))
        return COULD_NOT_ASK if args.command == "check" else NOT_DOWNLOADED
    if args.command == "check":
        answer = check(place)
        print(json.dumps(answer, ensure_ascii=True), flush=True)
        return {"newer": NEWER, "up to date": UP_TO_DATE}.get(answer["result"], COULD_NOT_ASK)
    try:
        path = download(args.version, args.to, place)
    except AskError as e:
        say(f"Not downloaded: {e}")
        return NOT_DOWNLOADED
    print(str(path), flush=True)
    return DOWNLOADED


if __name__ == "__main__":
    sys.exit(main())
