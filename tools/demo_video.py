"""The recording at the top of the README (dev tool, never part of a release): the real TASlation window, in English,
in a whole-book run over public sample pages - the pages read as a stand-in viewer turns them, then translated by the
real models, each line lettered as the model answers it - taken from TASlation's own window only and made into an
animated GIF.

    python tools/demo_video.py [--title balloon_dream] [--first 4] [--pages 8] [--out docs/media/whole-book-demo.gif]

The pages are those of one title of the OpenMantra dataset ("Towards Fully Automated Manga Translation", Ryota Hinami,
Shonosuke Ishiwatari, Kazuhiko Yasuda, Yusuke Matsui, AAAI 2021; published by Mantra Inc.), read from
``~/.taslation/datasets/openmantra`` where `tools/fetch_openmantra.py` put it. The dataset is under Creative Commons
Attribution-NonCommercial 4.0 (CC BY-NC 4.0), not under TASlation's licence, and the GIF shows its pages: the GIF is
CC BY-NC material too. Every frame says so under the picture ("Sample pages: OpenMantra dataset (Mantra Inc., CC BY-NC
4.0)"); wherever the GIF is shown the dataset is to be credited and the licence named, and the GIF is never part of a
release (it is in docs/media for the README alone, like the dataset itself, which is never shipped).

What runs, all on this computer:

* the stand-in viewer: a Tk window of a child process of this tool (``--serve-viewer``, the same file), titled
  ``Sample Viewer - OpenMantra sample``, maximised on the primary monitor, *--pages* pages from *--first* two to a
  screen, the first on the right (a book read right to left); ``--single`` shows one page a screen. Its pages are
  turned by this tool telling the child so on its standard input - no key, no click, nothing sent to any window - at
  a reader's pace: the next screen once the run has read the one on show and it has been on show for *--dwell* seconds;
* TASlation's window in this process, as ``taslation gui --book NAME`` opens it (`ui.app.App`, *--book* the book's
  name), in English, *--size* large, with the offline guard on (only Ollama's port on this computer can be reached),
  the real OCR from TASLATION_MODELS_DIR and the default translator through Ollama (the window starts Ollama when it
  does not answer, as ever). Everything is done through the window's own controls, as a person's clicks would: the
  stand-in is picked in the Viewer list (the list opened, the entry chosen), Read whole book... and the dialog's Start
  are pressed, and so is the band's Finished reading once the last screen is read; the run then translates the book
  with the page area following it, and the GIF ends on the translated last screen. No line is made up: every English
  line in the GIF is the model's;
* pictures of TASlation's own window, about *--fps* a second from the Tk loop (`capture_window` of its own handle,
  client area, never a copy of the screen), into memory: scaled to *--width*, a picture barely unlike the one before
  left out (the one before shown longer), and made into the GIF with Pillow - a caption strip under each frame says the
  stage and the credit, long waits are cut to *--longest* seconds, a stage longer than its share of *--length* is shown
  faster (the caption says how much), one adaptive palette for all frames, no dither, optimised.

What it touches, and what not: the user's own windows - another TASlation, a book in a browser - are never listed,
chosen, captured, moved, raised, focused or sent anything. The window list the app sees holds the stand-in alone
(`list_windows` replaced in every module that has it); every function that captures, moves, raises, enlarges, focuses
or sends a key or a click to a window is replaced by one that raises unless its window is the stand-in or one of this
process's own (a key or a click: the stand-in alone; a copy of the screen, a click on the screen and the global hot keys
never), and a refused call ends the demo; the viewer chosen is checked at every choice and at every picture, and any
other ends the demo at once. Windows.Graphics.Capture keeps one session at a time, the viewer's: TASlation's own window
is pictured with PrintWindow instead, so that the run's capture of the viewer is never interrupted. The app itself
sends no key in a whole-book run, and none is sent here. The state folder is a temporary one (TASLATION_STATE_DIR too,
the legal notice dismissed, the window in English, the first start's popup seen): nothing of ``~/.taslation`` is read
but the dataset's pages, nothing written there; the folder goes at the end, and the pictures never reach the disk but
as the GIF. Nothing of the pages' text is printed or logged: the tool prints numbers (timings, pages, frames) as JSON.

The run shows its windows on the screen for a few minutes (the stand-in maximised, TASlation's window over it); the
foreground is taken no more than the app takes it. A stage of the run that does not come within *--timeout* seconds
ends the demo, as does a refused call: the windows close, the folder goes, no GIF is written.

``--keep-recording FILE`` keeps the pictures (TASlation's window only, the sample pages in it) in FILE, and
``--from-recording FILE`` makes the GIF again from them with other GIF settings, without a run; delete FILE after."""

from __future__ import annotations

import argparse
import ctypes
import io
import json
import os
import pickle
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DATASET = Path.home() / ".taslation" / "datasets" / "openmantra"  # read only: its pages
VIEWER_TITLE = "Sample Viewer - OpenMantra sample"
GROUND = "#2b2b2b"  # the stand-in's ground round the pages (as tools/fake_viewer.py)
CREDIT = "Sample pages: OpenMantra dataset (Mantra Inc., CC BY-NC 4.0)"
CAPTIONS = {"intro": "The viewer chosen: Read whole book... starts the run",
            "reading": "Reading the pages as they are turned",
            "translating": "Translating: lines appear as the model answers",
            "done": "Done: the book is translated"}
SHARES = {"intro": 0.06, "reading": 0.36, "translating": 0.50, "done": 0.08}  # of --length, at most
STEP_MS = 100  # the director looks at the run this often
INTRO_S = 1.8  # the window with the viewer's page, before Read whole book... is pressed
FINISH_DWELL_S = 1.5  # the last screen read: this long before Finished reading
END_HOLD_S = 3.0  # the run over: the translated page on show this long before the recording ends
MIN_FRAME_MS = 80  # a frame comes once the one before it has been shown this long (others are left out)
MIN_GIF_MS = 40  # no frame shorter (browsers show a GIF's frames of 10 ms or less for 100 ms)
SAME_LEVELS, SAME_PIXELS = 14, 24  # a picture differs from the one before when more pixels than this differ so much


# ---------------------------------------------------------------------------------------------------- the stand-in
def page_files(title: str, first: int, pages: int) -> list[Path]:
    """The dataset's *pages* page files of *title* from page *first* (the dataset's page_index, 1-based)."""
    folder = DATASET / "images" / title / "ja"
    files = [folder / f"{n - 1:03d}.jpg" for n in range(first, first + pages)]
    missing = [f.name for f in files if not f.is_file()]
    if missing:
        raise SystemExit(f"not in the dataset ({folder}): {', '.join(missing)}; tools/fetch_openmantra.py fetches it")
    return files


def screens_of(files: list[Path], single: bool) -> list[Image.Image]:
    """What the stand-in shows screen by screen: each page alone, or two pages side by side, the first on the right."""
    pages = [Image.open(f).convert("RGB") for f in files]
    if single:
        return pages
    out = []
    for i in range(0, len(pages), 2):
        pair = pages[i:i + 2]
        if len(pair) == 1:
            out.append(pair[0])
            continue
        right, left = pair
        both = Image.new("RGB", (right.width + left.width, max(right.height, left.height)), (255, 255, 255))
        both.paste(left, (0, 0))
        both.paste(right, (left.width, 0))
        out.append(both)
    return out


def serve_viewer(args: argparse.Namespace) -> int:
    """The stand-in viewer (the child process): the screens on a dark ground, fitted with 20 px round them; told on its
    standard input "next", "prev" or "quit", it says "shown N" once screen N is drawn. "ready HWND PID" first, once
    the first screen is on show. Standard input closed (the tool gone): it closes."""
    import tkinter as tk

    from PIL import ImageTk

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor, as TASlation's window
    except (AttributeError, OSError):
        pass
    screens = screens_of(page_files(args.title, args.first, args.pages), args.single)
    root = tk.Tk()
    root.title(VIEWER_TITLE)
    root.configure(bg=GROUND)
    root.geometry("1200x860+40+40")
    canvas = tk.Canvas(root, bg=GROUND, highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    state: dict[str, Any] = {"index": 0, "photo": None, "size": None, "ready": False, "steady": 0}
    told: queue.Queue[str] = queue.Queue()

    def say(line: str) -> None:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    def draw(force: bool = False) -> None:
        w, h = canvas.winfo_width(), canvas.winfo_height()
        if w < 50 or h < 50 or (not force and state["size"] == (w, h)):
            return
        state["size"] = (w, h)
        page = screens[state["index"]]
        scale = min((w - 40) / page.width, (h - 40) / page.height)
        shown = page.resize((max(1, int(page.width * scale)), max(1, int(page.height * scale))), Image.LANCZOS)
        state["photo"] = ImageTk.PhotoImage(shown)
        canvas.delete("all")
        canvas.create_image(w // 2, h // 2, image=state["photo"])

    def show(index: int) -> None:
        state["index"] = max(0, min(len(screens) - 1, index))
        draw(force=True)
        root.update_idletasks()
        say(f"shown {state['index']}")

    def listen() -> None:  # (a thread: Tk is left to its own loop, which takes the lines from the queue)
        for line in sys.stdin:
            told.put(line.strip())
        told.put("quit")

    def take() -> None:
        while True:
            try:
                line = told.get_nowait()
            except queue.Empty:
                break
            if line == "next":
                show(state["index"] + 1)
            elif line == "prev":
                show(state["index"] - 1)
            elif line == "quit":
                root.destroy()
                return
        if not state["ready"] and root.state() == "zoomed":  # maximised and drawn at that size for 0.3 s
            drawn = state["size"] == (canvas.winfo_width(), canvas.winfo_height())
            state["steady"] = state["steady"] + 1 if drawn else 0
            if state["steady"] >= 10:
                state["ready"] = True
                say(f"ready {int(root.wm_frame(), 16)} {os.getpid()}")
        root.after(30, take)

    root.bind("<Configure>", lambda _e: draw())
    root.after(100, lambda: root.state("zoomed"))
    root.after(50, take)
    threading.Thread(target=listen, daemon=True).start()
    root.mainloop()
    return 0


class StandIn:
    """The stand-in viewer seen from this tool: the child process, its window's handle and process, and the turns."""

    def __init__(self, args: argparse.Namespace):
        command = [sys.executable, str(Path(__file__).resolve()), "--serve-viewer", "--title", args.title,
                   "--first", str(args.first), "--pages", str(args.pages)] + (["--single"] if args.single else [])
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                                     encoding="utf-8", bufsize=1)
        self.lines: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        self.hwnd, self.pid = self._ready()
        self.index = 0
        self.screens = (args.pages + (0 if args.single else 1)) // (1 if args.single else 2)

    def _read(self) -> None:
        for line in self.proc.stdout:  # type: ignore[union-attr]
            self.lines.put(line.strip())

    def _ready(self, seconds: float = 30.0) -> tuple[int, int]:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                line = self.lines.get(timeout=0.2)
            except queue.Empty:
                if self.proc.poll() is not None:
                    raise SystemExit("the stand-in viewer did not start")
                continue
            if line.startswith("ready "):
                _word, hwnd, pid = line.split()
                return int(hwnd), int(pid)
        raise SystemExit("the stand-in viewer did not come up")

    def turn(self) -> None:
        """The next screen (a line to the child: no key goes anywhere)."""
        self.proc.stdin.write("next\n")  # type: ignore[union-attr]
        self.proc.stdin.flush()  # type: ignore[union-attr]
        self.index += 1

    def close(self) -> None:
        try:
            self.proc.stdin.write("quit\n")  # type: ignore[union-attr]
            self.proc.stdin.flush()  # type: ignore[union-attr]
            self.proc.stdin.close()  # type: ignore[union-attr]
        except (OSError, ValueError):
            pass
        try:
            self.proc.wait(5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        if _process_alive(self.pid):  # (a venv's python.exe starts the interpreter as a process of its own)
            _end_process(self.pid)


def _process_alive(pid: int) -> bool:
    kernel32 = ctypes.WinDLL("kernel32")
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    code = wintypes.DWORD()
    kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
    kernel32.CloseHandle(handle)
    return code.value == 259  # STILL_ACTIVE


def _end_process(pid: int) -> None:
    kernel32 = ctypes.WinDLL("kernel32")
    handle = kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
    if handle:
        kernel32.TerminateProcess(handle, 1)
        kernel32.CloseHandle(handle)


# ---------------------------------------------------------------------------------------------------- the guard
class Refused(RuntimeError):
    """A call the demo does not allow: the window it was for is not the stand-in nor one of this process's own."""


class Guard:
    """The only windows the app may act on: the stand-in (*viewer*) and this process's own. Every refused call is noted
    (`refused`) and raises; `used` counts what reached the stand-in."""

    def __init__(self, viewer: int):
        self.viewer = viewer
        self.own_pid = os.getpid()
        self.refused: list[str] = []
        self.used: dict[str, int] = {}
        self.chosen: set[int] = set()
        self.user32 = ctypes.WinDLL("user32")
        self.user32.GetAncestor.restype = wintypes.HWND
        self.user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]

    def _root(self, hwnd: int) -> int:
        return int(self.user32.GetAncestor(hwnd, 2) or 0) or int(hwnd)  # GA_ROOT

    def is_viewer(self, hwnd: Any) -> bool:
        try:
            return bool(hwnd) and self._root(int(hwnd)) == self.viewer
        except (TypeError, ValueError, OSError):
            return False

    def is_own(self, hwnd: Any) -> bool:
        try:
            pid = wintypes.DWORD(0)
            self.user32.GetWindowThreadProcessId(int(hwnd), ctypes.byref(pid))
            return bool(hwnd) and pid.value == self.own_pid
        except (TypeError, ValueError, OSError):
            return False

    def refuse(self, name: str) -> None:
        self.refused.append(name)
        raise Refused(f"the demo does not allow {name} here")

    def wrap(self, name: str, original: Callable[..., Any], allow: str,
             target: Callable[..., Any]) -> Callable[..., Any]:
        """*original* behind a check of its window, *target*(args, kwargs): "viewer" (the stand-in alone), "ours" (the
        stand-in or this process's own) or "never"."""

        def guarded(*args: Any, **kwargs: Any) -> Any:
            hwnd = None if allow == "never" else target(args, kwargs)
            ok = allow != "never" and (self.is_viewer(hwnd) or (allow == "ours" and self.is_own(hwnd)))
            if not ok:
                self.refuse(name)
            if self.is_viewer(hwnd):
                self.used[name] = self.used.get(name, 0) + 1
            return original(*args, **kwargs)

        guarded.__wrapped__ = original  # type: ignore[attr-defined]
        return guarded


def first_arg(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    return args[0] if args else kwargs.get("hwnd")


def hwnd_of_first(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    held = args[0] if args else next(iter(kwargs.values()), None)
    return getattr(held, "hwnd", None)


# name -> (who it may act on, where its window is): every function of `capture.windows` that captures, moves, raises,
# enlarges, focuses or sends a key or a click to a window
GUARDED = {
    "capture_window": ("ours", first_arg), "enlarge_window": ("ours", first_arg), "move_window": ("ours", first_arg),
    "unminimise_window": ("ours", first_arg), "raise_window": ("ours", first_arg), "ask_repaint": ("ours", first_arg),
    "bring_to_front": ("ours", first_arg), "give_foreground": ("ours", first_arg),
    "restore_window": ("ours", hwnd_of_first), "lower_window": ("ours", hwnd_of_first),
    "press_key": ("viewer", first_arg), "press_briefly": ("viewer", first_arg), "post_key": ("viewer", first_arg),
    "post_click": ("viewer", first_arg),
    "click_screen": ("never", first_arg), "capture_screen_rect": ("never", first_arg),
}


def taslation_modules() -> list[Any]:
    return [m for name, m in list(sys.modules.items()) if m is not None and (name == "taslation" or
                                                                             name.startswith("taslation."))]


def replace_everywhere(original: Any, replacement: Any) -> int:
    """*original* replaced by *replacement* in every module of TASlation that holds it (imported by name or its own)."""
    n = 0
    for module in taslation_modules():
        for attr, value in list(vars(module).items()):
            if value is original:
                setattr(module, attr, replacement)
                n += 1
    return n


def install_guard(guard: Guard, viewer_info: Callable[[], Any]) -> dict[str, int]:
    """The window list the app sees holds the stand-in alone; every function of `GUARDED` checks its window; the
    stand-in's capture goes through Windows.Graphics.Capture, TASlation's own windows through PrintWindow (one session
    at a time: the viewer's is never closed for a picture of the window); the global hot keys are never registered."""
    import taslation.capture.overlay as overlay
    import taslation.capture.wgc as wgc
    import taslation.capture.windows as windows

    done = {"list_windows": replace_everywhere(windows.list_windows, lambda include_own=False: [viewer_info()])}
    for name, (allow, target) in GUARDED.items():
        original = getattr(windows, name)
        done[name] = replace_everywhere(original, guard.wrap(name, original, allow, target))
    latest = wgc.latest

    def compositor(hwnd: int, *args: Any, **kwargs: Any) -> Any:
        if guard.is_viewer(hwnd):
            return latest(hwnd, *args, **kwargs)
        if guard.is_own(hwnd):
            return None  # PrintWindow
        guard.refuse("a capture session")

    wgc.latest = compositor  # (looked up as `wgc.latest` at every call)

    def no_hot_keys(*_a: Any, **_k: Any) -> Any:
        guard.refuse("global hot keys")

    overlay.HotKeys.start = classmethod(lambda cls, *a, **k: no_hot_keys())  # type: ignore[assignment]
    return done


# ---------------------------------------------------------------------------------------------------- the pictures
@dataclass
class Shot:
    t: float  # monotonic seconds
    stage: str
    png: bytes


@dataclass
class Recording:
    width: int
    shots: list[Shot] = field(default_factory=list)
    end: float = 0.0
    taken: int = 0  # pictures taken (also those left out)
    seconds_taking: float = 0.0  # spent on the Tk thread taking them


class Recorder:
    """Pictures of TASlation's own window from the Tk loop (`capture_window` of its handle: the client area, never the
    screen), handed to a thread of their own that scales them to *width* and leaves out one barely unlike the last kept
    (*mask*: a box of the window, in its pixels, not looked at for that - the busy bar that never stops moving)."""

    def __init__(self, app: Any, width: int, fps: float, stage: Callable[[], str], check: Callable[[], None]):
        self.app, self.width, self.period = app, width, 1.0 / fps
        self.stage, self.check = stage, check
        self.recording = Recording(width)
        self.queue: queue.Queue[Any] = queue.Queue()
        self.on = False
        self.thread = threading.Thread(target=self._keep, name="demo-frames", daemon=True)
        self.thread.start()
        self.last: np.ndarray | None = None
        self.last_stage = ""
        self.mask: tuple[int, int, int, int] | None = None

    def start(self) -> None:
        if not self.on:
            self.on = True
            self._tick()

    def stop(self) -> Recording:
        self.on = False
        self.queue.put(None)
        self.thread.join(60)
        self.recording.end = time.monotonic()
        return self.recording

    def _tick(self) -> None:
        if not self.on:
            return
        from taslation.capture import windows

        began = time.monotonic()
        self.check()
        app = self.app
        try:
            hwnd = app._own_hwnd()
            image = windows.capture_window(hwnd, client_only=True, allow_screen_fallback=False)
            holder = app.progress_holder
            x, y = holder.winfo_rootx() - app.winfo_rootx(), holder.winfo_rooty() - app.winfo_rooty()
            mask = (x - 2, y - 2, x + holder.winfo_width() + 2, y + holder.winfo_height() + 2)
            self.queue.put((began, self.stage(), image, mask))
            self.recording.taken += 1
        except Exception:  # noqa: BLE001 - a picture missed (the window being rebuilt): the next one comes
            pass
        spent = time.monotonic() - began
        self.recording.seconds_taking += spent
        app.after(max(10, int((self.period - spent) * 1000)), self._tick)

    def _keep(self) -> None:
        while True:
            item = self.queue.get()
            if item is None:
                return
            t, stage, image, mask = item
            scale = self.width / image.width
            small = image.resize((self.width, max(1, round(image.height * scale))), Image.LANCZOS)
            grey = np.asarray(small.convert("L"), dtype=np.int16)
            if self.last is not None and stage == self.last_stage and grey.shape == self.last.shape:
                differ = np.abs(grey - self.last) > SAME_LEVELS
                x0, y0, x1, y1 = (int(v * scale) for v in mask)
                differ[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = False
                if int(differ.sum()) <= SAME_PIXELS:
                    continue
            self.last, self.last_stage = grey, stage
            buf = io.BytesIO()
            small.save(buf, format="PNG", compress_level=1)
            self.recording.shots.append(Shot(t, stage, buf.getvalue()))


# ---------------------------------------------------------------------------------------------------- the GIF
def font(size: int, bold: bool = False) -> Any:
    for name in (("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def caption_strip(width: int, text: str, height: int) -> Image.Image:
    """The strip under a frame: the stage on the left, the dataset's credit on the right."""
    strip = Image.new("RGB", (width, height), (24, 24, 24))
    draw = ImageDraw.Draw(strip)
    big, small = font(max(11, height * 15 // 34)), font(max(10, height * 12 // 34))
    draw.text((12, height // 2), text, fill=(238, 238, 238), font=big, anchor="lm")
    draw.text((width - 12, height // 2), CREDIT, fill=(160, 160, 160), font=small, anchor="rm")
    return strip


def timeline(recording: Recording, length: float, longest: float) -> tuple[list[int], dict[str, float]]:
    """How long each picture is shown in the GIF (ms; 0: left out) and each stage's speed-up: the real time it was on
    show, cut to *longest*, then shortened alike in a stage longer than its share of *length* (`SHARES`). The last
    picture, the translated book at the end, is the exception: it is shown as long as it was, up to `END_HOLD_S`, at
    its own pace, so the end can be read before the GIF starts again."""
    shots = recording.shots
    real = [b.t - a.t for a, b in zip(shots, shots[1:])] + [max(0.1, recording.end - shots[-1].t)]
    capped = [min(d, longest) for d in real[:-1]] + [min(real[-1], END_HOLD_S)]
    speed: dict[str, float] = {}
    for stage, share in SHARES.items():
        total = sum(d for d, s in zip(capped[:-1], shots) if s.stage == stage)
        speed[stage] = max(1.0, total / (share * length)) if total else 1.0
    shown = [d / speed[s.stage] * 1000 for d, s in zip(capped[:-1], shots)] + [capped[-1] * 1000]
    out = [0.0] * len(shots)
    last = -1  # the picture kept last
    for i, d in enumerate(shown):
        # a picture comes once the one kept before it has been shown MIN_FRAME_MS; one that comes sooner is left out
        # and the one before it shown longer, but for the last of a stage
        ends = i + 1 == len(shots) or shots[i + 1].stage != shots[i].stage
        if last < 0 or out[last] >= MIN_FRAME_MS or ends or shots[last].stage != shots[i].stage:
            out[i], last = d, i
        else:
            out[last] += d
    # (in tens of ms: a GIF keeps hundredths of a second, and Pillow would cut the rest off)
    return [max(MIN_GIF_MS, 10 * round(d / 10)) if d else 0 for d in out], speed


def make_gif(recording: Recording, out: Path, length: float, longest: float, caption_h: int,
             colours: int = 256) -> dict[str, Any]:
    """The GIF of *recording*: each picture with its caption strip under it, shown for its `timeline` time, all with
    one adaptive palette made from a sample of them (no dither: an unchanged part of a picture stays the same bytes,
    so Pillow writes only what changed), optimised."""
    durations, speed = timeline(recording, length, longest)
    kept = [(s, d) for s, d in zip(recording.shots, durations) if d]
    strips: dict[str, Image.Image] = {}

    def caption(stage: str) -> str:
        text = CAPTIONS[stage]
        return text + (f"  ({speed[stage]:.1f}x speed)" if speed[stage] >= 1.15 else "")

    frames: list[Image.Image] = []
    for shot, _d in kept:
        picture = Image.open(io.BytesIO(shot.png)).convert("RGB")
        if shot.stage not in strips:
            strips[shot.stage] = caption_strip(picture.width, caption(shot.stage), caption_h)
        frame = Image.new("RGB", (picture.width, picture.height + caption_h))
        frame.paste(picture, (0, 0))
        frame.paste(strips[shot.stage], (0, picture.height))
        frames.append(frame)
    sample = frames[:: max(1, len(frames) // 24)] + [frames[-1]]
    w, h = frames[0].size
    montage = Image.new("RGB", (w // 2 * min(4, len(sample)), h // 2 * ((len(sample) + 3) // 4)))
    for i, frame in enumerate(sample):
        montage.paste(frame.resize((w // 2, h // 2), Image.BOX), ((i % 4) * (w // 2), (i // 4) * (h // 2)))
    for strip in strips.values():  # the captions' anti-aliased letters have their colours too
        montage.paste(strip.resize((w // 2, caption_h)), (0, 0))
    palette = montage.quantize(colors=colours, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    paletted = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    out.parent.mkdir(parents=True, exist_ok=True)
    paletted[0].save(out, save_all=True, append_images=paletted[1:], duration=[d for _s, d in kept], loop=0,
                     optimize=True, disposal=1)
    total = sum(d for _s, d in kept)
    stages: dict[str, float] = {}
    clock = 0
    for shot, d in kept:
        stages.setdefault(shot.stage, clock / 1000)
        clock += d
    return {"bytes": out.stat().st_size, "width": w, "height": h, "frames": len(kept),
            "seconds": round(total / 1000, 1),
            "speed": {k: round(v, 2) for k, v in speed.items()}, "stage_starts_s": stages,
            "pictures_taken": recording.taken, "pictures_kept": len(recording.shots)}


# ---------------------------------------------------------------------------------------------------- the run
class Director:
    """The demo's steps on the Tk loop, each when the window is ready for it, as a person would take them; the times of
    the run, numbers only."""

    def __init__(self, app: Any, viewer: StandIn, guard: Guard, args: argparse.Namespace):
        self.app, self.viewer, self.guard, self.args = app, viewer, guard, args
        self.stage = "loading"
        self.step = self.wait_ready
        self.since = time.monotonic()
        self.began = time.monotonic()
        self.failed = ""
        self.recorder: Recorder | None = None
        self.recording: Recording | None = None
        self.times: dict[str, Any] = {"turned": [], "read_done": {}, "translate_done": {}}

    # the checks
    def check(self) -> None:
        """Ends the demo at once when the app was refused a call or has any viewer but the stand-in chosen."""
        selected = getattr(self.app, "selected", None)
        if selected is not None and selected.hwnd != self.viewer.hwnd:
            self.fail("a window other than the stand-in was chosen")
        elif self.guard.refused:
            self.fail(f"a call was refused: {', '.join(sorted(set(self.guard.refused)))}")
        elif self.viewer.proc.poll() is not None and not _process_alive(self.viewer.pid):
            self.fail("the stand-in viewer closed")

    def fail(self, why: str) -> None:
        if not self.failed:
            self.failed = why
            print(f"demo ended: {why}", file=sys.stderr)
        self.app.after_idle(self.app.quit)

    def run(self) -> None:
        self.app.after(STEP_MS, self._loop)

    def _loop(self) -> None:
        if self.failed:
            return
        self.check()
        if self.failed:
            return
        if time.monotonic() - self.since > self.args.timeout:
            self.fail(f"no progress for {self.args.timeout:.0f} s at the step {self.step.__name__}")
            return
        try:
            self.step()
        except Exception as e:  # noqa: BLE001 - said, and the demo ends
            self.fail(f"{type(e).__name__} at the step {self.step.__name__}: {e}")
            return
        self.app.after(STEP_MS, self._loop)

    def go(self, step: Callable[[], None]) -> None:
        self.step, self.since = step, time.monotonic()
        print(f"{time.monotonic() - self.began:7.1f} s  {step.__name__}", file=sys.stderr, flush=True)

    def waited(self) -> float:
        return time.monotonic() - self.since

    # the steps
    def wait_ready(self) -> None:
        if self.app.ready:
            self.times["models_ready_s"] = round(time.monotonic() - self.began, 1)
            self.go(self.choose_viewer)

    def choose_viewer(self) -> None:
        """The Viewer list opened (its rescan) and the stand-in picked in it, as a person does."""
        app = self.app
        app._rescan_windows()
        index = next((i for i, w in enumerate(app.windows) if w.hwnd == self.viewer.hwnd), None)
        if index is None:
            raise RuntimeError("the stand-in is not in the Viewer list")
        app.window_box.current(index)
        app.window_box.event_generate("<<ComboboxSelected>>")
        self.go(self.wait_live)

    def wait_live(self) -> None:
        """The viewer's page on the page area: the Reader role chosen with its button, as a person who reads the book
        chooses it (a book with no translations yet opens in translator mode, whose tools and hint would take the
        page's room; the run is the same in either), and the recording starts."""
        from tkinter import ttk

        app = self.app
        if app.selected is None or getattr(app, "_live", None) is None or getattr(app, "_enlarging", None) is not None:
            return
        if self.waited() < 1.5:
            return
        if not getattr(self, "reader_chosen", False):  # (chosen, it is the book's role: the window's own choice waits)
            reader = next((b for b in walk(app) if isinstance(b, ttk.Radiobutton) and str(b.cget("value")) == "reader"),
                          None)
            if reader is None:
                raise RuntimeError("the window has no Reader button")
            reader.invoke()
            self.reader_chosen = True
            self.since = time.monotonic()  # (the page area takes the room: looked at again in a moment)
            return
        if app.role_var.get() != "reader":
            raise RuntimeError("the window left the Reader role")
        self.stage = "intro"
        self.recorder = Recorder(app, self.args.width, self.args.fps, lambda: self.stage, self.check)
        self.recorder.start()
        self.go(self.press_read_whole_book)

    def press_read_whole_book(self) -> None:
        if self.waited() < INTRO_S:
            return
        if str(self.app.batch_btn["state"]) == "disabled":
            return
        self.app.batch_btn.invoke()
        self.go(self.press_start)

    def press_start(self) -> None:
        """The dialog's Start, once the dialog is up."""
        from tkinter import ttk

        from taslation.ui.dialogs.batch import BatchDialog

        dialogs = [w for w in self.app.winfo_children() if isinstance(w, BatchDialog) and w.winfo_exists()]
        if not dialogs or self.waited() < 0.6:
            return
        start = next((b for b in walk(dialogs[0]) if isinstance(b, ttk.Button) and b.cget("text") == "Start"), None)
        if start is None:
            raise RuntimeError("the dialog has no Start")
        self.times["run_started_s"] = round(time.monotonic() - self.began, 1)
        self.run_began = time.monotonic()
        start.invoke()
        self.go(self.wait_reading)

    def pages(self) -> dict[int, Any]:
        return getattr(self.app, "_strip_model").pages

    def read_over(self, seq: int) -> bool:
        cell = self.pages().get(seq)
        return cell is not None and cell.stages.get("read") in ("done", "skipped", "failed")

    def wait_reading(self) -> None:
        """The run reads the screen on show: the first page of the strip."""
        if self.app.batch is not None and self.pages():
            self.stage = "reading"
            self.turned_at = time.monotonic()
            self.times["turned"].append(round(self.turned_at - self.run_began, 2))
            self.go(self.reading)

    def reading(self) -> None:
        """The screen on show read and on show *--dwell* s: the next one, as a reader turns it; the last one read:
        Finished reading."""
        seq = self.viewer.index + 1
        if not self.read_over(seq):
            return
        self.times["read_done"].setdefault(seq, round(time.monotonic() - self.run_began, 2))
        on_show = time.monotonic() - self.turned_at
        if self.viewer.index + 1 >= self.viewer.screens:
            if on_show >= max(self.args.dwell, FINISH_DWELL_S):
                self.go(self.press_finished)
            return
        if on_show >= self.args.dwell:
            self.viewer.turn()
            print(f"{time.monotonic() - self.began:7.1f} s  screen {self.viewer.index + 1} on show", file=sys.stderr,
                  flush=True)
            self.turned_at = time.monotonic()
            self.times["turned"].append(round(self.turned_at - self.run_began, 2))
            self.since = time.monotonic()

    def press_finished(self) -> None:
        """The band's Finished reading, pressed as a person presses it."""
        from tkinter import ttk

        band = getattr(self.app, "scan_band", None)
        button = next((b for b in walk(band) if isinstance(b, ttk.Button) and b.cget("text") == "Finished reading"),
                      None) if band is not None else None
        if button is None:
            return
        self.stage = "translating"
        self.finished_at = time.monotonic()
        self.times["finished_reading_s"] = round(self.finished_at - self.run_began, 2)
        button.invoke()
        self.go(self.translating)

    def translating(self) -> None:
        for seq, cell in self.pages().items():
            if cell.stages.get("translate") in ("done", "failed", "skipped"):
                self.times["translate_done"].setdefault(seq, round(time.monotonic() - self.finished_at, 2))
        if self.app.batch is None and not self.app._batching:
            self.times["run_over_after_finished_s"] = round(time.monotonic() - self.finished_at, 2)
            self.times["run_seconds"] = round(time.monotonic() - self.run_began, 2)
            band = getattr(self.app, "_band", None) or {}
            self.times["summary"] = getattr(band.get("summary"), "code", "")
            self.stage = "done"
            self.result_before = self.app.last_result
            self.shown_at: float | None = None
            self.go(self.ending)

    def ending(self) -> None:
        """The page on show translated from the cache (the run's end does it: `translate_now`) and on show
        `END_HOLD_S`; without that result, the window as it is after 15 s."""
        app = self.app
        if self.shown_at is None:
            if (app.last_result is not self.result_before and not app.busy) or self.waited() > 15:
                self.shown_at = time.monotonic()
                self.times["end_page_shown_after_run_s"] = round(self.waited(), 2)
            return
        if time.monotonic() - self.shown_at < END_HOLD_S:
            return
        self.recording = self.recorder.stop() if self.recorder is not None else None
        self.go(self.close)

    def close(self) -> None:
        self.step = lambda: None
        self.app.after_idle(self.app.quit)


def walk(widget: Any) -> list[Any]:
    out = []
    for child in widget.winfo_children():
        out.append(child)
        out.extend(walk(child))
    return out


def scratch_state() -> Path:
    """A state folder of its own for the run: the legal notice dismissed, the window in English, the first start's
    popup seen (as tools/strip_demo.py)."""
    from taslation import notice
    from taslation.i18n import save_ui_flag, save_ui_language
    from taslation.ui.dialogs.help import FIRST_STEPS_FLAG

    state = Path(os.environ["TASLATION_STATE_DIR"])
    notice.save_country(state, "JP")
    notice.dismiss(state, "en")
    save_ui_language(state, "en")
    save_ui_flag(state, FIRST_STEPS_FLAG)
    return state


def record(args: argparse.Namespace) -> tuple[Recording, dict[str, Any]]:
    """The run, recorded (see the module's docstring)."""
    import taslation
    from taslation import batch, pipeline, translation_view  # noqa: F401 - every module in place before the guard
    from taslation.capture import enable_dpi_awareness
    from taslation.ui import app, jobs, live, overbook, reading, strip, trouble, viewers  # noqa: F401
    from taslation.ui.dialogs import batch as batch_dialog, caches, start, stop  # noqa: F401

    if not Path(taslation.__file__).resolve().is_relative_to(ROOT):
        raise SystemExit(f"taslation comes from {taslation.__file__}, not from {ROOT}: set PYTHONPATH")
    enable_dpi_awareness()
    viewer = StandIn(args)
    try:
        return run_with(args, viewer)
    finally:
        viewer.close()


def run_with(args: argparse.Namespace, viewer: StandIn) -> tuple[Recording, dict[str, Any]]:
    from taslation import netguard
    from taslation.capture import WindowInfo, program_name, window_class, window_rect, window_title
    from taslation.config import Settings
    from taslation.ui import app as app_mod

    guard = Guard(viewer.hwnd)
    if guard.is_own(viewer.hwnd) or window_title(viewer.hwnd) != VIEWER_TITLE:
        raise SystemExit("the stand-in's window is not what it should be")

    def viewer_info() -> WindowInfo:
        return WindowInfo(viewer.hwnd, window_title(viewer.hwnd), window_class(viewer.hwnd), viewer.pid,
                          window_rect(viewer.hwnd), program_name(viewer.pid))

    patched = install_guard(guard, viewer_info)
    chosen = app_mod.App._on_window_selected

    def selected(self: Any, *a: Any, **k: Any) -> Any:
        result = chosen(self, *a, **k)
        if self.selected is not None:
            guard.chosen.add(self.selected.hwnd)
            if self.selected.hwnd != viewer.hwnd:
                guard.refused.append("a viewer other than the stand-in")
        return result

    app_mod.App._on_window_selected = selected
    state = scratch_state()
    settings = Settings(state_dir=state, ui_language="en", target_language="English", over_book=False,
                        flash_when_done=False, sound_when_done=False, always_on_top=False)
    settings.validate()
    netguard.install(settings.ollama_port)  # nothing but Ollama's port on this computer, as the window has it
    app = app_mod.App(settings, book=args.book, auto=False)
    width, height = args.size
    app.geometry(f"{width}x{height}+{args.at[0]}+{args.at[1]}")
    app.after(600, lambda: app.geometry(f"{width}x{height}+{args.at[0]}+{args.at[1]}"))
    director = Director(app, viewer, guard, args)
    stages: list[tuple[float, int, str, str]] = []
    own_stage = app_mod.App._on_page_stage

    def staged(self: Any, data: dict[str, Any]) -> None:
        stages.append((time.monotonic(), int(data.get("seq") or 0), str(data.get("stage")), str(data.get("state"))))
        own_stage(self, data)

    app_mod.App._on_page_stage = staged
    director.run()
    try:
        app.mainloop()
    finally:
        recording = director.recording
        if recording is None and director.recorder is not None:
            recording = director.recorder.stop()
        report = dict(director.times)
        report["last_step"] = director.step.__name__
        report.update(lines(app))
        report.update(stage_times(stages))
        report["guard"] = {"patched": patched, "refused": guard.refused, "chosen": sorted(guard.chosen),
                           "stand_in": viewer.hwnd, "reached_the_stand_in": guard.used,
                           "only_the_stand_in_chosen": guard.chosen <= {viewer.hwnd}}
        finish_app(app)
    if director.failed:
        raise SystemExit(f"demo ended without a GIF: {director.failed}")
    return recording, report  # type: ignore[return-value]


def lines(app: Any) -> dict[str, Any]:
    """How many lines the run found and translated (numbers only)."""
    model = getattr(app, "_strip_model", None)
    return {"screens_on_strip": len(model.pages) if model is not None else 0}


def stage_times(stages: list[tuple[float, int, str, str]]) -> dict[str, Any]:
    """Seconds each screen spent reading (from its read waiting to read done) and translating (from translate working
    to translate done), from the run's ``page_stage`` events."""
    first: dict[tuple[int, str, str], float] = {}
    for t, seq, stage, state in stages:
        first.setdefault((seq, stage, state), t)
    seqs = sorted({seq for _t, seq, _s, _st in stages if seq})
    read, translate = {}, {}
    for seq in seqs:
        a = first.get((seq, "read", "working")) or first.get((seq, "read", "waiting"))
        b = first.get((seq, "read", "done"))
        if a and b:
            read[seq] = round(b - a, 2)
        a, b = first.get((seq, "translate", "working")), first.get((seq, "translate", "done"))
        if a and b:
            translate[seq] = round(b - a, 2)
    starts = [first[(s, "translate", "working")] for s in seqs if (s, "translate", "working") in first]
    ends = [first[(s, "translate", "done")] for s in seqs if (s, "translate", "done") in first]
    return {"read_seconds_per_screen": read, "translate_seconds_per_screen": translate,
            "translation_total_s": round(max(ends) - min(starts), 2) if starts and ends else None}


def finish_app(app: Any) -> None:
    """The window closed as its own Close does when nothing of a run is left to lose (the viewer's window put back, the
    translator's model let go); else torn down."""
    from taslation.ui.strip import close_warning

    try:
        if close_warning(app) is None:
            app._on_close()
        else:
            app.batch and app.batch.stop()
            app.destroy()
    except Exception:  # noqa: BLE001 - the window goes all the same
        try:
            app.destroy()
        except Exception:  # noqa: BLE001
            pass


def parse(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--title", default="balloon_dream", help="the OpenMantra title folder")
    ap.add_argument("--first", type=int, default=4, help="the first page (the dataset's page number, from 1)")
    ap.add_argument("--pages", type=int, default=8)
    ap.add_argument("--single", action="store_true", help="one page a screen (default: two, right to left)")
    ap.add_argument("--book", default="", help="the Book box (default: the title, with OpenMantra)")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "media" / "whole-book-demo.gif")
    ap.add_argument("--size", type=lambda s: tuple(int(v) for v in s.lower().split("x")), default=(1180, 920),
                    help="TASlation's window, WIDTHxHEIGHT below its menu bar (Tk's geometry; default: its first size)")
    ap.add_argument("--at", type=lambda s: tuple(int(v) for v in s.split(",")), default=(370, 10),
                    help="where TASlation's window goes on the screen, X,Y")
    ap.add_argument("--dwell", type=float, default=2.5, help="seconds a read screen stays on show before the next")
    ap.add_argument("--fps", type=float, default=4.5, help="pictures of the window a second")
    ap.add_argument("--width", type=int, default=960, help="the GIF's width")
    ap.add_argument("--length", type=float, default=40.0, help="seconds the GIF lasts at most, roughly")
    ap.add_argument("--longest", type=float, default=1.5, help="seconds a frame is shown at most")
    ap.add_argument("--caption", type=int, default=34, help="the caption strip's height (0: none)")
    ap.add_argument("--colours", type=int, default=256)
    ap.add_argument("--timeout", type=float, default=300.0, help="seconds a step of the run may wait")
    ap.add_argument("--keep-recording", type=Path, default=None, help=argparse.SUPPRESS)
    ap.add_argument("--from-recording", type=Path, default=None, help=argparse.SUPPRESS)
    ap.add_argument("--serve-viewer", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    args.book = args.book or f"{args.title} (OpenMantra)"
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    if args.serve_viewer:
        return serve_viewer(args)
    if sys.platform != "win32":
        raise SystemExit("the demo needs Windows (window capture)")
    if args.from_recording is not None:
        with open(args.from_recording, "rb") as f:
            recording, report = pickle.load(f)
    else:
        page_files(args.title, args.first, args.pages)
        state = Path(tempfile.mkdtemp(prefix="taslation-demo-"))
        os.environ["TASLATION_STATE_DIR"] = str(state)  # (before TASlation is imported: nothing finds ~/.taslation)
        os.environ.pop("SELFTRANS_STATE_DIR", None)
        if not (os.environ.get("TASLATION_MODELS_DIR") or (ROOT / "models").is_dir()):
            raise SystemExit("set TASLATION_MODELS_DIR to the folder of the installed models")
        try:
            recording, report = record(args)
        finally:
            shutil.rmtree(state, ignore_errors=True)
        report["state_folder_removed"] = not state.exists()
        if args.keep_recording is not None:
            with open(args.keep_recording, "wb") as f:
                pickle.dump((recording, report), f)
    if not recording.shots:
        raise SystemExit("no picture was taken")
    report["gif"] = make_gif(recording, args.out, args.length, args.longest, args.caption, args.colours)
    report["gif"]["path"] = str(args.out)
    print(json.dumps(report, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
