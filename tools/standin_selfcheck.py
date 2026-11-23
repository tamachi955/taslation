"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: the stand-in viewer's profiles driven alone, no TASlation.

    python tools/standin_selfcheck.py --out SCRATCH [--profile dark|light|both] [--synthetic] [--no-shots]
                                      [--no-extra] [--browser auto|chrome|edge]

The stand-in page (`tools/standin_viewer/standin.html`) is opened in a HEADLESS browser (Chrome or Edge, as
`standin_viewer.find_browser` finds it; ``--headless=new`` on a throwaway profile in SCRATCH): no window on the
screen, nothing taken from anyone's windows, no input of the system's. It is driven through the browser's own
debugging protocol (a websocket on 127.0.0.1, a port the browser picks): the pointer and the keys as the page gets
them from a person (``Input.dispatchMouseEvent``, ``Input.dispatchKeyEvent``: trusted events), the window's size and
the screen's (``Emulation.setDeviceMetricsOverride``: the browser's own window 1918 x (946 + the band), then its full
screen 1920 x 1080), the page's console read as the e2e tool reads it, pictures of it taken by the browser
(``Page.captureScreenshot``) into SCRATCH/shots.

For each profile: the cover alone, a turn by key, by the side arrow, by a click on the ground (dark) or on the page
(light), the bars shown and hidden as the profile shows them, the slider dragged and its bar clicked (the black with
its spinner, or the washed-out picture), the full screen and back; then the same profile with a few of its parts
switched (`EXTRA`). The page's log is printed (times from the start, no page text: the page says numbers only) and
kept in SCRATCH/log.txt; each check is said PASS or FAIL, and what the e2e tool's decoder reads in each picture.
Exit status 1 when a check failed.

The pages are the public sample pages the e2e tool uses (the dataset's, read where they are) or, with --synthetic
or without them, the repository's test pages; nothing is copied. The pictures in SCRATCH/shots hold those pages:
written into the scratch folder only (--no-shots: none written, each still decoded).

Standard library and Pillow only."""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import standin_viewer as sv  # noqa: E402

WINDOW = (1918, 946)  # the viewer's area in the browser's window, as measured (its band over it: the tabs, the bar)
FULL = (1920, 1080)  # the browser's full screen
BAND = 54
PAGES = 24
# a few parts switched, to show each goes alone: the bars toggled by a click in the page's middle, a click on the
# page turning it, one page of a spread first at every jump (dark); the washed-out picture long enough for a look,
# the arrows only after a move (light)
EXTRA = {"dark": {"bars": "click", "page_clicks": "1", "jump_half": "1", "half_ms": "1500"},
         "light": {"preview_ms": "1500", "arrow_show": "move"}}


# ---------------------------------------------------------------------------------------------------- the socket
class Socket:
    """A websocket client, enough for the browser's debugging protocol: text frames out (masked), frames in."""

    def __init__(self, url: str, timeout: float = 10.0):
        u = urlparse(url)
        self.sock = socket.create_connection((u.hostname, u.port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
                           ).encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("the browser closed the socket at its start")
            head += chunk
        status, _sep, self.buffer = head.partition(b"\r\n\r\n")
        if b" 101 " not in status.split(b"\r\n")[0] + b" ":
            raise ConnectionError("the browser refused the socket")
        self.sock.settimeout(None)
        self.send_lock = threading.Lock()

    def _exact(self, n: int) -> bytes:
        while len(self.buffer) < n:
            chunk = self.sock.recv(1 << 16)
            if not chunk:
                raise ConnectionError("closed")
            self.buffer += chunk
        out, self.buffer = self.buffer[:n], self.buffer[n:]
        return out

    def _frame(self, op: int, data: bytes) -> None:
        n = len(data)
        head = bytearray([0x80 | op])
        if n < 126:
            head.append(0x80 | n)
        elif n < 1 << 16:
            head += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        body = bytes(b ^ mask[k & 3] for k, b in enumerate(data))
        with self.send_lock:
            self.sock.sendall(bytes(head) + mask + body)

    def send(self, text: str) -> None:
        self._frame(0x1, text.encode("utf-8"))

    def receive(self) -> str:
        parts: list[bytes] = []
        while True:
            b0, b1 = self._exact(2)
            op, n = b0 & 0x0F, b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._exact(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._exact(8))[0]
            mask = self._exact(4) if b1 & 0x80 else b""
            data = self._exact(n)
            if mask:
                data = bytes(b ^ mask[k & 3] for k, b in enumerate(data))
            if op == 0x8:
                raise ConnectionError("closed")
            if op == 0x9:
                self._frame(0xA, data)
                continue
            if op in (0x0, 0x1, 0x2):
                parts.append(data)
                if b0 & 0x80:
                    return b"".join(parts).decode("utf-8", "replace")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class Cdp:
    """The debugging protocol on one target: `call` waits for its answer; the page's console lines (`said`) and
    the other events are kept as they come, by a reader thread."""

    def __init__(self, url: str):
        self.ws = Socket(url)
        self.ids = 0
        self.answers: dict[int, dict[str, Any]] = {}
        self.cond = threading.Condition()
        self.said: list[tuple[float, dict[str, str]]] = []
        self.alive = True
        threading.Thread(target=self._read, name="cdp", daemon=True).start()

    def _read(self) -> None:
        try:
            while True:
                msg = json.loads(self.ws.receive())
                with self.cond:
                    if "id" in msg:
                        self.answers[msg["id"]] = msg
                    elif msg.get("method") == "Runtime.consoleAPICalled":
                        for arg in msg["params"].get("args", []):
                            said = sv.parse_line('"' + str(arg.get("value", "")) + '"')
                            if said is not None:
                                self.said.append((time.monotonic(), said))
                    self.cond.notify_all()
        except (ConnectionError, OSError, ValueError):
            with self.cond:
                self.alive = False
                self.cond.notify_all()

    def call(self, method: str, timeout: float = 15.0, **params: Any) -> dict[str, Any]:
        with self.cond:
            self.ids += 1
            n = self.ids
        self.ws.send(json.dumps({"id": n, "method": method, "params": params}))
        end = time.monotonic() + timeout
        with self.cond:
            while n not in self.answers:
                left = end - time.monotonic()
                if left <= 0 or not self.alive:
                    raise RuntimeError(f"no answer to {method}")
                self.cond.wait(left)
            msg = self.answers.pop(n)
        if "error" in msg:
            raise RuntimeError(f"{method}: {msg['error'].get('message', '')}")
        return msg.get("result", {})

    def value(self, expression: str) -> Any:
        """What an expression in the page's global scope gives (JSON)."""
        out = self.call("Runtime.evaluate", expression=f"JSON.stringify({expression})", returnByValue=True)
        return json.loads(out.get("result", {}).get("value") or "null")

    def count(self) -> int:
        with self.cond:
            return len(self.said)

    def wait(self, test: Callable[[dict[str, str]], bool], since: int, seconds: float) -> dict[str, str] | None:
        end = time.monotonic() + seconds
        with self.cond:
            while True:
                for _t, said in self.said[since:]:
                    if test(said):
                        return said
                left = end - time.monotonic()
                if left <= 0 or not self.alive:
                    return None
                self.cond.wait(min(left, 0.1))

    def close(self) -> None:
        self.ws.close()


# ---------------------------------------------------------------------------------------------------- the browser
class Headless:
    """The headless browser on a throwaway *profile* (made here, deleted at `close`), its debugging port its own."""

    def __init__(self, program: Path, profile: Path):
        self.profile = Path(profile)
        self.profile.mkdir(parents=True, exist_ok=False)
        flags = [f for f in sv.FLAGS if not f.startswith(("--enable-logging", "--v="))]
        self.proc = subprocess.Popen([str(program), f"--user-data-dir={self.profile}", "--headless=new",
                                      "--remote-debugging-port=0", "--hide-scrollbars", *flags,
                                      f"--window-size={FULL[0]},{FULL[1]}", "about:blank"],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        port_file = self.profile / "DevToolsActivePort"
        end = time.monotonic() + 20
        while not port_file.is_file() or len(port_file.read_text().split()) < 2:
            if self.proc.poll() is not None or time.monotonic() > end:
                raise RuntimeError("the headless browser did not open its debugging port")
            time.sleep(0.1)
        port, path = port_file.read_text().split()[:2]
        self.base, self.browser_ws = f"127.0.0.1:{port}", f"ws://127.0.0.1:{port}{path}"

    def page(self) -> Cdp:
        with urllib.request.urlopen(f"http://{self.base}/json/list", timeout=10) as r:  # (no proxy: a local socket)
            targets = json.loads(r.read().decode())
        target = next(t for t in targets if t.get("type") == "page")
        return Cdp(target["webSocketDebuggerUrl"])

    def close(self) -> dict[str, Any]:
        out: dict[str, Any] = {"closed": False, "processes_ended": 0, "profile_deleted": False}
        tree = sv.process_tree(self.proc.pid) if sys.platform == "win32" else {self.proc.pid}
        try:
            ws = Socket(self.browser_ws, timeout=5)
            ws.send(json.dumps({"id": 1, "method": "Browser.close", "params": {}}))
            self.proc.wait(10)
            out["closed"] = True
            ws.close()
        except (OSError, ConnectionError, subprocess.TimeoutExpired):
            pass
        if sys.platform == "win32":
            alive = {pid for pid, _parent in sv.processes()}
            for pid in sorted(tree & alive):
                if sv._end_process(pid):  # noqa: SLF001 - the stand-in's own way of ending its browser's tree
                    out["processes_ended"] += 1
        if self.proc.poll() is None:
            self.proc.kill()
        for _attempt in range(20):
            shutil.rmtree(self.profile, ignore_errors=True)
            if not self.profile.exists():
                out["profile_deleted"] = True
                break
            time.sleep(0.5)
        return out


# ---------------------------------------------------------------------------------------------------- the check
class Check:
    """One profile's run: the page opened with its options, driven, checked, pictured."""

    def __init__(self, cdp: Cdp, out: Path, name: str, label: str, folder: Path, options: dict[str, str],
                 keep_shots: bool, results: list[tuple[str, bool, str]]):
        self.cdp, self.out, self.name, self.label = cdp, out, name, label
        self.folder, self.options, self.keep_shots, self.results = folder, options, keep_shots, results
        self.start = 0
        self.size = WINDOW
        self.mouse = (0.0, 0.0)

    # the page's size, the pointer, the keys
    def resize(self, full: bool) -> None:
        w, h = FULL if full else (WINDOW[0], WINDOW[1] + BAND)
        self.size = (w, h)
        self.cdp.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=False,
                      screenWidth=FULL[0], screenHeight=FULL[1])

    def move(self, x: float, y: float, steps: int = 1, buttons: int = 0) -> None:
        x0, y0 = self.mouse
        for k in range(1, steps + 1):
            px, py = x0 + (x - x0) * k / steps, y0 + (y - y0) * k / steps
            self.cdp.call("Input.dispatchMouseEvent", type="mouseMoved", x=px, y=py, buttons=buttons,
                          button="left" if buttons else "none")
            if steps > 1:
                time.sleep(0.016)
        self.mouse = (x, y)

    def press(self, x: float, y: float) -> None:
        self.move(x, y)
        self.cdp.call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", buttons=1,
                      clickCount=1)

    def release(self, x: float, y: float) -> None:
        self.cdp.call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", buttons=0,
                      clickCount=1)
        self.mouse = (x, y)

    def click(self, x: float, y: float) -> None:
        self.press(x, y)
        time.sleep(0.05)
        self.release(x, y)

    def key(self, name: str) -> None:
        code = {"ArrowLeft": 37, "ArrowRight": 39}[name]
        for kind in ("rawKeyDown", "keyUp"):
            self.cdp.call("Input.dispatchKeyEvent", type=kind, key=name, code=name, windowsVirtualKeyCode=code,
                          nativeVirtualKeyCode=code)

    # what the page said
    def expect(self, what: str, since: int, seconds: float, **words: str) -> dict[str, str] | None:
        said = self.cdp.wait(lambda s: all(s.get(k) == v for k, v in words.items()), since, seconds)
        self.results.append((f"{self.label}: {what}", said is not None,
                             " ".join(f"{k}={v}" for k, v in words.items())))
        return said

    def note(self, what: str, ok: bool, detail: str = "") -> None:
        self.results.append((f"{self.label}: {what}", ok, detail))

    def shot(self, name: str) -> str:
        data = base64.b64decode(self.cdp.call("Page.captureScreenshot", format="png")["data"])
        state = "?"
        try:
            from PIL import Image

            with Image.open(io.BytesIO(data)) as image:
                state = sv.decode(image.convert("RGB"), 0).state()
        except ImportError:
            pass
        path = self.out / "shots" / f"{self.label}_{name}.png"
        if self.keep_shots:
            path.write_bytes(data)
        print(f"  picture {path.name}: the e2e decoder reads {state}")
        return state

    def geometry(self, said: dict[str, str] | None, what: str) -> None:
        if not said or "box" not in said:
            self.note(f"geometry {what}", False, "no draw")
            return
        x0, y0, x1, y1 = (int(v) for v in said["box"].split(","))
        band = int(said.get("band", "0"))
        area_h = self.size[1] - band
        fit = abs((y1 - y0) - area_h) <= 1
        self.note(f"geometry {what}: page {x1 - x0} x {y1 - y0}, ground {x0} | {self.size[0] - x1}, band {band}",
                  fit and abs(x0 - (self.size[0] - x1)) <= 1, "fitted to the height of the viewer's area, centred")

    # the run
    def open(self) -> None:
        self.cdp.call("Page.enable")
        self.cdp.call("Runtime.enable")
        self.resize(False)
        token = "t" + secrets.token_hex(4)
        url = sv.page_url(token, [], self.folder, seed=1, band=BAND, profile=self.name, options=self.options)
        self.start = self.cdp.count()
        self.cdp.call("Page.navigate", url=url)
        ready = self.cdp.wait(lambda s: s.get("ev") == "ready", self.start, 20)
        self.note("the page is ready", ready is not None and ready.get("profile") == self.name)
        time.sleep(0.3)

    def area(self) -> dict[str, int]:
        return self.cdp.value("viewerArea()")

    def run(self) -> None:
        dark = self.name == "dark"
        first = self.cdp.wait(lambda s: s.get("ev") == "draw" and s.get("why") == "start", self.start, 5)
        self.geometry(first, "the cover alone, window")
        self.note("the cover alone", bool(first) and first.get("pages") == "1")
        self.shot("window_cover")

        n = self.cdp.count()  # a turn by key: the spread of pages 1 and 2
        self.key("ArrowLeft")
        self.expect("a turn by key", n, 2, ev="turn", by="key", dir="next")
        drawn = self.expect("its draw, sharp at once", n, 2, ev="draw", why="next", state="sharp")
        self.geometry(drawn, "a spread, window")
        self.shot("window_spread_bars_hidden")

        a = self.area()
        cx, cy = a["x"] + a["w"] / 2, a["y"] + a["h"] / 2
        n = self.cdp.count()  # a move: dark's arrows come, light's bars come
        self.move(cx, cy, steps=4)
        if self.options.get("arrow_show", "move" if dark else "always") == "move":
            self.expect("the side arrows on a move", n, 2, ev="arrows", on="1")
        bars = self.options.get("bars", "edge" if dark else "move")
        if bars == "move":
            self.expect("the bars on a move", n, 2, ev="bars", on="1", why="move")
        time.sleep(0.4)
        self.shot("window_after_a_move")

        sides = self.cdp.value("arrowRects(viewerArea(), P.arrows, P.arrow_inset, dpr())")
        n = self.cdp.count()  # the left arrow: the next screen
        left = sides["left"]
        self.click(left["x"] + left["w"] / 2, left["y"] + left["h"] / 2)
        self.expect("a turn by the side arrow", n, 2, ev="turn", by="arrow", dir="next")
        time.sleep(0.3)

        box = self.cdp.value("pageBox()")
        n = self.cdp.count()  # a click on the ground left of the page, then right of it
        self.click(box["x0"] / 2, cy + 120)
        if int(self.options.get("ground_clicks", "1" if dark else "0")):
            self.expect("a turn by a click on the left ground", n, 2, ev="turn", by="ground", dir="next")
            time.sleep(0.3)
            n = self.cdp.count()
            self.click((box["x1"] + self.size[0]) / 2, cy + 120)
            self.expect("back by a click on the right ground", n, 2, ev="turn", by="ground", dir="previous")
        else:
            self.expect("a click on the ground turns nothing", n, 2, ev="pointer", kind="released", on="ground")
        time.sleep(0.3)
        n = self.cdp.count()  # a click on the page's left third
        self.click(box["x0"] + (box["x1"] - box["x0"]) / 6, cy)
        if int(self.options.get("page_clicks", "0" if dark else "1")):
            self.expect("a turn by a click on the page's left third", n, 2, ev="turn", by="page", third="left")
        else:
            self.expect("a click on the page turns nothing", n, 2, ev="pointer", kind="released", on="page_left")
        time.sleep(0.3)

        self.bars_in_and_out(bars, cx, cy)
        self.slider(dark)
        self.full_screen(dark, bars, cx)

    def bars_in_and_out(self, bars: str, cx: float, cy: float) -> None:
        a = self.area()
        n = self.cdp.count()
        if bars == "edge":
            self.move(cx, a["y"] + a["h"] - 20, steps=4)  # the bottom band
            self.expect("the bars at the bottom edge", n, 2, ev="bars", on="1", why="edge")
            time.sleep(0.5)
            self.shot("window_bars_shown")
            n = self.cdp.count()
            self.move(cx, cy, steps=4)
            self.expect("the bars go a moment after the pointer left", n, 3, ev="bars", on="0", why="edge_left")
            self.expect("their fade ends", n, 3, ev="bars_done", on="0")
            n = self.cdp.count()
            self.move(cx, a["y"] + 30, steps=4)  # the top band
            self.expect("the bars at the top edge", n, 2, ev="bars", on="1", why="edge")
            time.sleep(0.4)
            n = self.cdp.count()
            self.move(cx, cy, steps=4)
            self.expect("and away again", n, 3, ev="bars", on="0")
        elif bars == "move":
            self.move(cx + 40, cy, steps=2)
            time.sleep(0.4)
            self.shot("window_bars_shown")
            n = self.cdp.count()
            self.expect("the bars go 3 s after the last move", n, 4.5, ev="bars", on="0", why="time")
        elif bars == "click":
            box = self.cdp.value("pageBox()")
            mid = (box["x0"] + box["x1"]) / 2
            self.click(mid, cy)
            self.expect("the bars on by a click in the page's middle", n, 2, ev="bars", on="1", why="click")
            time.sleep(0.4)
            self.shot("window_bars_shown")
            n = self.cdp.count()
            self.click(mid, cy)
            self.expect("and off by another", n, 2, ev="bars", on="0", why="click")
        time.sleep(0.5)
        if self.cdp.value("arrows.on"):  # (a picture with neither: the arrows' own time)
            time.sleep(3.2)
        self.shot("window_bars_hidden")

    def show_bars(self) -> None:
        bars = self.options.get("bars", "edge" if self.name == "dark" else "move")
        a = self.area()
        if bars == "click":
            if not self.cdp.value("bars.on"):
                box = self.cdp.value("pageBox()")
                self.click((box["x0"] + box["x1"]) / 2, a["y"] + a["h"] / 2)
        else:
            self.move(a["x"] + a["w"] / 2, a["y"] + a["h"] - 20, steps=3)
        time.sleep(0.4)

    def slider(self, dark: bool) -> None:
        self.show_bars()
        t = self.cdp.value("track()")
        knob = self.cdp.value("knobX(index)")
        count = self.cdp.value("entries.length")
        n = self.cdp.count()  # the knob dragged to about page 12
        self.press(knob, t["y"])
        target = t["x1"] - (12 / max(1, count - 1)) * (t["x1"] - t["x0"])
        self.move(target, t["y"], steps=10, buttons=1)
        self.release(target, t["y"])
        self.expect("a jump by a drag of the knob", n, 2, ev="jump", by="drag")
        self.after_jump(dark, n, "drag")
        n = self.cdp.count()  # a click on the bar near its right end (page 4 or so)
        self.show_bars()
        spot = t["x1"] - (4 / max(1, count - 1)) * (t["x1"] - t["x0"])
        self.click(spot, t["y"])
        self.expect("a jump by a click on the bar", n, 2, ev="jump", by="click")
        self.after_jump(dark, n, "click")

    def after_jump(self, dark: bool, n: int, how: str) -> None:
        if dark:
            on = self.expect(f"the black with its spinner ({how})", n, 2, ev="spinner", on="1", why="jump")
            if how == "drag":
                self.shot("window_spinner")
            off = self.expect(f"... and its end ({how})", n, 3, ev="spinner", on="0", why="jump")
            if on and off:
                ms = float(off["t"]) - float(on["t"])
                lo, hi = (int(v) for v in self.options.get("jump_ms", "500-1100").split("-"))
                self.note(f"the spinner's time {ms:.0f} ms", lo - 30 <= ms <= hi + 60, f"{lo}-{hi} ms")
            half = self.cdp.wait(lambda s: s.get("ev") == "draw" and s.get("why") == "jump", n, 3)
            if half and half.get("kind") == "half":
                self.shot(f"window_half_{how}")
                self.expect("the other page later", n, 4, ev="draw", why="sharp")
            else:
                self.note("the jump's draw, sharp", bool(half) and half.get("state") == "sharp")
        else:
            self.expect(f"the washed-out picture ({how})", n, 2, ev="preview", on="1")
            drawn = self.cdp.wait(lambda s: s.get("ev") == "draw" and s.get("kind") == "preview", n, 2)
            if how == "drag" and drawn:
                self.shot("window_preview")
            off = self.expect(f"... then sharp ({how})", n, 3, ev="preview", on="0")
            self.expect(f"the sharp draw ({how})", n, 3, ev="draw", why="sharp", state="sharp")
            if drawn and off:
                ms, want = float(off["t"]) - float(drawn["t"]), int(self.options.get("preview_ms", "200"))
                self.note(f"the washed-out picture's time {ms:.0f} ms", want - 30 <= ms <= want + 150, f"{want} ms")
        time.sleep(0.4)

    def full_screen(self, dark: bool, bars: str, cx: float) -> None:
        n = self.cdp.count()
        self.resize(True)
        self.expect("the full screen: no band", n, 3, ev="size", full="1", band="0")
        if dark:
            self.expect("the black with its spinner as it resizes", n, 2, ev="spinner", on="1", why="resize")
            self.shot("full_spinner")
            on = self.cdp.wait(lambda s: s.get("ev") == "spinner" and s.get("on") == "1", n, 1)
            off = self.expect("... and its end", n, 2, ev="spinner", on="0", why="resize")
            if on and off:
                ms = float(off["t"]) - float(on["t"])
                self.note(f"its time {ms:.0f} ms", 370 <= ms <= 560, "400-500 ms")
        else:
            got = self.cdp.wait(lambda s: s.get("ev") == "spinner", n, 1.0)
            self.note("no black as it resizes", got is None)
        drawn = self.expect("the page at the new size", n, 3, ev="draw", why="resize", state="sharp")
        self.geometry(drawn, "a spread, full screen")
        time.sleep(0.5)
        if self.cdp.value("arrows.on") or self.cdp.value("bars.on"):
            time.sleep(3.6)
        self.shot("full_bars_hidden")
        self.show_bars()
        time.sleep(0.3)
        self.shot("full_bars_shown")
        n = self.cdp.count()
        self.resize(False)
        self.expect("back to the window: the band again", n, 3, ev="size", full="0", band=str(BAND))
        self.expect("the page at that size", n, 3, ev="draw", why="resize")
        time.sleep(0.4)


def summary_of(said: list[tuple[float, dict[str, str]]]) -> list[str]:
    """The log as lines: ms from the first, what was said (no page text: the page says numbers and words only)."""
    if not said:
        return []
    t0 = float(said[0][1]["t"])
    lines = []
    for _t, s in said:
        words = " ".join(f"{k}={v}" for k, v in s.items() if k not in ("ev", "t", "step"))
        lines.append(f"{float(s['t']) - t0:9.1f}  {s['ev']:<10} {words}")
    return lines


def parse(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, help="a scratch folder (made; never the repository)")
    ap.add_argument("--profile", default="both", choices=("dark", "light", "both"))
    ap.add_argument("--synthetic", action="store_true", help="the repository's test pages, not the dataset's")
    ap.add_argument("--browser", default="auto", choices=("auto", "chrome", "edge"))
    ap.add_argument("--no-shots", action="store_true", help="no pictures written (they are still decoded)")
    ap.add_argument("--no-extra", action="store_true", help="the profiles as they are only, not `EXTRA`")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    out = Path(args.out).resolve()
    if out.is_relative_to(ROOT):
        raise SystemExit("--out is a scratch folder outside the repository")
    out.mkdir(parents=True, exist_ok=True)
    (out / "shots").mkdir(exist_ok=True)
    folder = out / "standin"
    folder.mkdir(exist_ok=True)
    import standin_e2e as e2e

    pictures: list[Any] | None = None if args.synthetic else e2e.dataset_pages(1, 1, PAGES)
    print(f"pages: {'the dataset' if pictures else 'the repository test pages'} ({PAGES})")
    sv.write_page_list(folder, pictures or e2e.synthetic_pages(PAGES))
    sv.write_control(folder, 0)
    found = sv.find_browser(args.browser)
    if found is None:
        raise SystemExit("neither Chrome nor Edge is installed here")
    results: list[tuple[str, bool, str]] = []
    runs = [(p, p, {}) for p in (("dark", "light") if args.profile == "both" else (args.profile,))]
    if not args.no_extra:
        runs += [(p, f"{p}_switched", EXTRA[p]) for p, _l, _o in list(runs)]
    log: list[str] = []
    browser = Headless(found[1], out / f"profile_{secrets.token_hex(3)}")
    try:
        cdp = browser.page()
        try:
            for name, label, options in runs:
                print(f"\n== {label} {' '.join(f'{k}={v}' for k, v in options.items())}")
                check = Check(cdp, out, name, label, folder, options, not args.no_shots, results)
                check.open()
                try:
                    check.run()
                except Exception as e:  # noqa: BLE001 - said, the next profile goes on
                    results.append((f"{label}: the run", False, f"{type(e).__name__}: {e}"))
                with cdp.cond:
                    said = cdp.said[check.start:]
                lines = summary_of(said)
                log += [f"== {label}", *lines]
                for line in lines:
                    print("  " + line)
        finally:
            cdp.close()
    finally:
        closed = browser.close()
    (out / "log.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
    print("\n== checks")
    for what, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {what}" + (f"  ({detail})" if detail else ""))
    failed = sum(1 for _w, ok, _d in results if not ok)
    print(f"\n{len(results) - failed} of {len(results)} checks passed; browser closed {closed}; log {out / 'log.txt'}; "
          f"pictures {out / 'shots' if not args.no_shots else 'none'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
