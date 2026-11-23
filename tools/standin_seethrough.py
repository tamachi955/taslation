"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: the see-through window (`taslation.capture.seethrough`) watched in an
end-to-end run on the stand-in viewer (``tools/standin_e2e.py --see-through``), numbers only.

What `SeeWatch` notes while the run goes on, from the tool's own thread (nothing is sent to any window, no key, no
click, no message; the foreground is only read):

* every frame the stand-in's capture session delivers (`wgc.add_listener`: when), so that the frames a second of the
  browser while its bars fade or its spinner turns can be told with the see-through window on and off;
* which window is in front, every FRONT_EVERY_S, and each change (the stand-in, this process, another);
* every HIT_EVERY_S, which window `WindowFromPoint` gives at the middle of each patch shown, at the page's middle and
  on the ground beside it: the stand-in's, never the see-through window;
* the process's CPU time, every CPU_EVERY_S, with whether a page job ran;
* which screen of the stand-in's each patch set was made from (its frame's code cells, `standin_viewer.decode`);
* with *truth*: a copy of the stand-in's place on the screen every TRUTH_EVERY_S (in memory; two of them written as
  PNG into the scratch folder for the developer's eyes - they show the public sample pages and the lettering -, to be
  deleted after), and in each the patches visible of a page other than the one the copy shows (an old patch over a new
  page: its letters on the copy, and the patch not in the viewer's own frame of that moment, which the see-through
  window is never in - a patch's white over a white part of the new page, or over the new page's own lettering, is
  not it), and how the patches of the page shown lie on it (0 px off at 100 %).

`report` turns the notes and the see-through window's own (`SeeThrough.notes`) into the run's ``see_through`` block:
the time from the stand-in's change of screen (its spinner, its washed-out picture or its draw) to the window showing
none of the old page's patches (median, p90, max), the hits, the foreground's changes, the frames a second, the CPU
and the truth check's findings."""

from __future__ import annotations

import ctypes
import os
import statistics
import threading
import time
from collections import Counter
from ctypes import wintypes
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PIL import Image

FRONT_EVERY_S = 0.05
HIT_EVERY_S = 1.0
CPU_EVERY_S = 0.5
TRUTH_EVERY_S = 0.033
VISIBLE_TOL = 8  # a patch's pixel is on the screen when every channel is within this
VISIBLE_SHARE = 0.9  # a patch is on the screen when so many of its opaque pixels looked at are
INK_LEVEL = 100  # a patch's pixel darker than this (every channel) is of its letters (an old patch: its letters seen)
SHOTS_KEPT = 2
SRCCOPY, CAPTUREBLT = 0x00CC0020, 0x40000000
GA_ROOT = 2

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.WindowFromPoint.argtypes = [wintypes.POINT]
_user32.WindowFromPoint.restype = wintypes.HWND
_user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.GetAncestor.restype = wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetDC.argtypes = [wintypes.HWND]
_user32.GetDC.restype = wintypes.HDC
_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
_gdi32.CreateCompatibleDC.restype = wintypes.HDC
_gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
_gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
_gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_gdi32.SelectObject.restype = wintypes.HGDIOBJ
_gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HDC,
                          ctypes.c_int, ctypes.c_int, wintypes.DWORD]
_gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                             ctypes.c_void_p, wintypes.UINT]
_gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_gdi32.DeleteDC.argtypes = [wintypes.HDC]


class _BIH(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


def screen_copy(x: int, y: int, w: int, h: int) -> np.ndarray:
    """The screen's pixels in the rectangle (RGB, (h, w, 3)): the tool's own copy, layered windows included."""
    screen = _user32.GetDC(None)
    dc = _gdi32.CreateCompatibleDC(screen)
    bmp = _gdi32.CreateCompatibleBitmap(screen, w, h)
    try:
        old = _gdi32.SelectObject(dc, bmp)
        _gdi32.BitBlt(dc, 0, 0, w, h, screen, x, y, SRCCOPY | CAPTUREBLT)
        _gdi32.SelectObject(dc, old)
        info = _BIH(ctypes.sizeof(_BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        _gdi32.GetDIBits(dc, bmp, 0, h, buf, ctypes.byref(info), 0)
        arr = np.frombuffer(buf, np.uint8).reshape(h, w, 4)
        return np.ascontiguousarray(arr[:, :, 2::-1])
    finally:
        _gdi32.DeleteObject(bmp)
        _gdi32.DeleteDC(dc)
        _user32.ReleaseDC(None, screen)


def window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD(0)
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def visible_share(copy: np.ndarray, patch: Any, dx: int = 0, dy: int = 0, step: int = 3,
                  ink: bool = False) -> float | None:
    """The share of *patch*'s opaque pixels (every *step*-th; *ink*: its dark ones only) that *copy* (RGB, the client
    area) shows as they are, the patch moved by (*dx*, *dy*); None when it has too few or lies outside."""
    left, top, right, bottom = patch.box
    left, top, right, bottom = left + dx, top + dy, right + dx, bottom + dy
    if left < 0 or top < 0 or bottom > copy.shape[0] or right > copy.shape[1]:
        return None
    alpha = patch.bgra[::step, ::step, 3] > 0
    if int(alpha.sum()) < 20:
        return None
    want = patch.bgra[::step, ::step, 2::-1].astype(np.int16)
    have = copy[top:bottom:step, left:right:step].astype(np.int16)
    if have.shape != want.shape:
        return None
    same = np.all(np.abs(have - want) <= VISIBLE_TOL, axis=2)
    if ink:  # only the patch's dark pixels, its letters: a white patch over another white place says nothing
        alpha = alpha & (want.max(axis=2) < INK_LEVEL)
        if int(alpha.sum()) < 10:
            return None
    return float(same[alpha].mean())


def spread(values: list[float]) -> dict[str, Any]:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return {"n": 0}
    p90 = vals[min(len(vals) - 1, int(round(0.9 * (len(vals) - 1))))]
    return {"n": len(vals), "median": round(statistics.median(vals), 1), "p90": round(p90, 1),
            "max": round(vals[-1], 1)}


class SeeWatch:
    """The notes of a run with the see-through window (see the module's notes). *decode*: a frame (PIL) to the
    stand-in's screen it shows, (page, spread) or None; *top*: rows above the page's content in a client capture."""

    def __init__(self, app: Any, hwnd: int, decode: Callable[[Any], Any], truth: bool, shots: Path | None) -> None:
        self.app, self.hwnd, self.decode = app, int(hwnd), decode
        self.truth, self.shots = truth, shots
        self.delta_ms = time.time() * 1000 - time.monotonic() * 1000
        self.own_pid = os.getpid()
        self.lock = threading.Lock()
        self.frames: list[float] = []
        self.fronts: list[tuple[float, str]] = []
        self.hits: Counter[str] = Counter()
        self.cpu: list[tuple[float, float, bool]] = []
        self.screens: dict[int, Any] = {}  # set key -> screen
        self._made: list[tuple[int, Any]] = []  # (set key, its frame): held, so that no other frame takes its key
        self._over: Any = None  # the see-through window, kept for the report (the window lets go of it at its close)
        self.copies = 0
        self.truth_rows: list[dict[str, Any]] = []
        self.saved: list[str] = []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="see-watch", daemon=True)

    # the hooks
    def install(self) -> None:
        from taslation.capture import wgc
        from taslation.ui import seethrough as ui

        wgc.add_listener(self._frame)
        pairs = ui.pairs

        def noted(app: Any) -> Any:
            out = pairs(app)
            for original, _lettered, _final, _state in out:
                key = id(original)
                if not any(img is original for _k, img in self._made):
                    self.screens[key] = self.decode(original)
                    self._made = [(key, original), *self._made[:63]]
            return out

        ui.pairs = noted

    def _frame(self, hwnd: int, _seq: int) -> None:
        if hwnd == self.hwnd:
            self.frames.append(time.time() * 1000)

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.stop.set()
        self.thread.join(3.0)
        from taslation.capture import wgc

        wgc.remove_listener(self._frame)

    def over(self) -> Any:
        over = getattr(self.app, "_see_through", None) if self.app is not None else None
        if over is not None:
            self._over = over
        return over if over is not None else self._over

    def _who(self, hwnd: int) -> str:
        if not hwnd:
            return "none"
        if hwnd == self.hwnd:
            return "standin"
        over = self.over()
        if over is not None and hwnd == over.hwnd:
            return "overlay"
        return "own" if window_pid(hwnd) == self.own_pid else "other"

    def _run(self) -> None:
        next_hit = next_cpu = next_copy = 0.0
        last_front = None
        while not self.stop.wait(0.01):
            now = time.monotonic()
            front = int(_user32.GetForegroundWindow() or 0)
            who = self._who(front)
            if who != last_front:
                self.fronts.append((time.time() * 1000, who))
                last_front = who
            self.over()  # (kept)
            if now >= next_cpu:
                self.cpu.append((time.time() * 1000, time.process_time(), bool(getattr(self.app, "busy", False))))
                next_cpu = now + CPU_EVERY_S
            if now >= next_hit:
                self._hit_test()
                next_hit = now + HIT_EVERY_S
            if self.truth and now >= next_copy:
                try:
                    self._copy()
                except Exception:  # noqa: BLE001 - a copy that failed is a copy less
                    pass
                next_copy = now + TRUTH_EVERY_S

    def _hit_test(self) -> None:
        over = self.over()
        shown = over.shown() if over is not None else None
        points: list[tuple[str, int, int]] = []
        if shown is not None:
            serial, indices, origin, size = shown
            sets = {s.serial: s for s in list(over._store.sets)}
            chosen = sets.get(serial)
            if chosen is not None:
                for i in indices[:6]:
                    left, top, right, bottom = chosen.patches[i].box
                    points.append(("patch", origin[0] + (left + right) // 2, origin[1] + (top + bottom) // 2))
            points.append(("page", origin[0] + size[0] // 2, origin[1] + size[1] // 2))
            points.append(("ground", origin[0] + 12, origin[1] + size[1] // 2))
        for where, x, y in points:
            hwnd = int(_user32.GetAncestor(_user32.WindowFromPoint(wintypes.POINT(x, y)), GA_ROOT) or 0)
            self.hits[f"{where}:{self._who(hwnd)}"] += 1

    def _viewer_frame(self) -> np.ndarray | None:
        """The viewer's newest captured frame, cut to its client area as the see-through window lies on it (RGB)."""
        from taslation.capture import wgc, windows

        frame = wgc.peek(self.hwnd)
        if frame is None:
            return None
        box = wgc.crop_box(frame.size, windows._frame_bounds(self.hwnd), windows._client_box(self.hwnd))
        if box is None:
            return None
        return np.ascontiguousarray(frame.bgra[box[1]:box[3], box[0]:box[2], 2::-1])

    def _copy(self) -> None:
        over = self.over()
        if over is None:
            return
        from taslation.capture import windows

        x, y, w, h = windows._client_box(self.hwnd)
        t = time.time() * 1000
        own = self._viewer_frame()  # (before the copy: the viewer's own picture, the see-through window never in it)
        copy = screen_copy(x, y, w, h)
        self.copies += 1
        screen = self.decode(Image.fromarray(copy))
        with over._lock:
            sets = list(over._store.sets)
        shown = over.shown()
        row: dict[str, Any] = {"t": t, "screen": screen, "old_visible": 0, "own_visible": 0, "offsets": [],
                               "old_in_frame": 0, "old_sets": []}
        for s in sets:
            made_of = self.screens.get(s.key)
            for p in s.patches:
                share = visible_share(copy, p)
                if share is None or share < VISIBLE_SHARE:
                    continue
                if made_of is not None and screen is not None and made_of != screen:
                    in_frame = own is not None and own.shape == copy.shape and (
                        visible_share(own, p) or 0.0) >= VISIBLE_SHARE
                    letters = (visible_share(copy, p, ink=True) or 0.0) >= VISIBLE_SHARE
                    if in_frame or not letters:  # the viewer's own page there looks like the patch, or only its
                        row["old_in_frame"] += 1  # white is seen (the new page's own lettering over the place)
                        continue
                    row["old_visible"] += 1
                    if len(row["old_sets"]) < 2:
                        row["old_sets"].append([s.serial, shown is not None and shown[0] == s.serial, made_of])
                elif made_of == screen:
                    row["own_visible"] += 1
                    if len(row["offsets"]) < 3:
                        best = max(((visible_share(copy, p, dx, dy) or 0.0, -abs(dx) - abs(dy), dx, dy)
                                    for dx in (-1, 0, 1) for dy in (-1, 0, 1)))  # (a tie: the place itself)
                        row["offsets"].append([best[2], best[3]])
        row["shown"] = shown is not None
        self.truth_rows.append(row)
        final = shown is not None and any(s.serial == shown[0] and s.final for s in sets)  # (a page done, not filling)
        if (self.shots is not None and len(self.saved) < SHOTS_KEPT and row["own_visible"] >= 3 and final
                and (not self.saved or t - float(self.saved[-1].split("@")[1]) > 20000)):
            self.shots.mkdir(parents=True, exist_ok=True)
            path = self.shots / f"see_through_{len(self.saved) + 1}.png"
            Image.fromarray(copy).save(path)
            self.saved.append(f"{path}@{t}")

    # the report
    def report(self, events: list[dict[str, Any]], offset: float, end_ms: float) -> dict[str, Any]:
        over = self.over()
        notes = list(over.notes) if over is not None else []
        counts = dict(over.counts) if over is not None else {}
        serial_key = {n["set"]: n["key"] for n in notes if n["ev"] == "present"}
        state: list[tuple[float, int | None]] = []
        own_ms: list[float] = []  # the window's own time from a frame's arrival to its showing or hiding
        for n in notes:
            t = n["t"] * 1000 + self.delta_ms
            if n["ev"] == "show":
                state.append((t, n["set"]))
            elif n["ev"] == "hide":
                state.append((t, None))
            if n["ev"] in ("show", "hide") and n.get("arrived") and n.get("new"):  # (a look a new frame started)
                own_ms.append((n["t"] - n["arrived"]) * 1000)

        def screen_of(serial: int | None) -> Any:
            return None if serial is None else self.screens.get(serial_key.get(serial, -1))

        def shown_at(t: float) -> int | None:
            got = None
            for when, serial in state:
                if when > t:
                    break
                got = serial
            return got

        # the stand-in's changes of screen: each turn or jump, from its first change on the screen (spinner, black,
        # its washed-out picture or its draw)
        changes = []
        last_screen = None
        pending: float | None = None
        for e in events:
            t = e["t"] + offset
            ev = e["ev"]
            if ev in ("spinner", "black") and e.get("on") == "1":
                pending = t if pending is None else pending
            elif ev == "draw":
                screen = (int(e["page"]), e.get("spread") == "1")
                if e.get("why") in ("next", "previous", "jump") and screen != last_screen:
                    changes.append({"t": pending if pending is not None else t, "draw_t": t, "to": screen,
                                    "from": last_screen, "why": e.get("why"), "kind": e.get("kind")})
                last_screen = screen
                pending = None
        stale: list[float] = []
        rows = []
        nothing = 0
        for c in changes:
            before = shown_at(c["t"] - 1)
            old = screen_of(before)
            if before is None:
                nothing += 1
                continue
            if old == c["to"]:
                continue
            gone = None
            for when, serial in state:
                if when < c["t"] - 1:
                    continue
                if serial is None or screen_of(serial) != old:
                    gone = when
                    break
            ms = None if gone is None else max(0.0, gone - c["t"])
            if ms is not None:
                stale.append(ms)
            rows.append({"t": round(c["t"]), "why": c["why"], "kind": c["kind"], "stale_ms": ms})
        # the truth check: old patches over a new page, and how long after the change of that page
        late, old_rows = [], []
        for r in self.truth_rows:
            if not r["old_visible"]:
                continue
            since = [c["t"] for c in changes if c["t"] <= r["t"] and c["to"] == r["screen"]]
            late.append(round(r["t"] - since[-1]) if since else None)
            if len(old_rows) < 20:  # (each: the page on the copy, the page the old patch was made of, the time since
                last = [c for c in changes if c["t"] <= r["t"]]  # the last change of screen of any kind, and the time
                ahead = [c for c in changes if c["t"] > r["t"] and c["to"] == r["screen"]]  # to the change to the
                old_rows.append({"screen": r["screen"], "sets": r["old_sets"], "since_last_ms":  # copy's page if it
                                 round(r["t"] - last[-1]["t"]) if last else None,  # is logged after the copy)
                                 "last_to": last[-1]["to"] if last else None,
                                 "until_next_ms": round(ahead[0]["t"] - r["t"]) if ahead else None})
        offsets = Counter(tuple(o) for r in self.truth_rows for o in r["offsets"])
        # the comparison's margins: the worst share of changed pixels among the patches shown, and the least among
        # those hidden (`seethrough.CHANGED_SHARE` between them), each as a frame came
        worst = sorted(n["worst"] for n in notes if n["ev"] == "show" and n.get("new") and n.get("worst") is not None)
        least = sorted([n["least_hidden"] for n in notes if n["ev"] == "show" and n.get("new")
                        and (n.get("least_hidden") or -1) >= 0]
                       + [n["least"] for n in notes
                          if n["ev"] == "hide" and n.get("new") and n.get("least") is not None])

        def shares(v: list[float]) -> dict[str, Any]:
            if not v:
                return {"n": 0}
            return {"n": len(v), "min": round(v[0], 4), "p10": round(v[int(0.1 * (len(v) - 1))], 4),
                    "median": round(statistics.median(v), 4), "p90": round(v[int(0.9 * (len(v) - 1))], 4),
                    "max": round(v[-1], 4)}
        fps = self._fps(events, offset)
        cpu = self._cpu(changes, end_ms)
        return {"counts": {k: (round(v, 1) if isinstance(v, float) else v) for k, v in counts.items()},
                "stale_ms": spread(stale), "stale_rows": rows, "changes_with_nothing_shown": nothing,
                "own_frame_to_change_ms": spread(own_ms),
                "hides_by_why": dict(Counter(n["why"] for n in notes if n["ev"] == "hide")),
                "shares": {"shown_worst": shares(worst), "hidden_least": shares(least)},
                "hits": dict(self.hits), "front_changes": len(self.fronts) - 1 if self.fronts else 0,
                "fronts": [[round(t - (changes[0]["t"] if changes else t)), w] for t, w in self.fronts],
                "frames_per_s": fps, "cpu": cpu,
                "truth": {"copies": self.copies, "with_old_patch": len(late), "old_patch_ms_after_change": late[:20],
                          "old_rows": old_rows,
                          "max_ms": max((v for v in late if v is not None), default=None),
                          # (patches of another page that the viewer's own frame shows alike, or whose letters are not
                          # on the copy - white over white -: not the see-through window's, left out above; and the
                          # old patches of the set it showed)
                          "like_the_frame": sum(r.get("old_in_frame", 0) for r in self.truth_rows),
                          "old_of_the_set_shown": sum(1 for r in self.truth_rows
                                                      if any(o[1] for o in r.get("old_sets", []))),
                          "patch_offsets": {f"{dx},{dy}": n for (dx, dy), n in offsets.items()},
                          "shots": [s.split("@")[0] for s in self.saved]},
                "sets_made_of": len(self.screens)}

    def _fps(self, events: list[dict[str, Any]], offset: float) -> dict[str, Any]:
        """The stand-in's frames a second while its bars fade (from "bars" to "bars_done") and its spinner turns."""
        spans: dict[str, list[tuple[float, float]]] = {"bars": [], "spinner": []}
        open_: dict[str, float] = {}
        for e in events:
            t = e["t"] + offset
            if e["ev"] == "bars":
                open_["bars"] = t
            elif e["ev"] == "bars_done" and "bars" in open_:
                spans["bars"].append((open_.pop("bars"), t))
            elif e["ev"] == "spinner":
                if e.get("on") == "1":
                    open_["spinner"] = t
                elif "spinner" in open_:
                    spans["spinner"].append((open_.pop("spinner"), t))
        out = {}
        frames = sorted(self.frames)
        for kind, got in spans.items():
            rates = []
            for a, b in got:
                if b - a < 100:
                    continue
                n = sum(1 for f in frames if a <= f <= b)
                rates.append(n * 1000 / (b - a))
            out[kind] = spread(rates)
        return out

    def _cpu(self, changes: list[dict[str, Any]], end_ms: float) -> dict[str, Any]:
        """The process's CPU (per cent of one processor) at rest - no page job and no change of screen in the 3 s
        before - and while following (a change of screen in the 3 s before)."""
        rest, follow = [], []
        times = [c["t"] for c in changes]
        for (t0, c0, busy0), (t1, c1, busy1) in zip(self.cpu, self.cpu[1:]):
            if t1 <= t0:
                continue
            share = 100 * (c1 - c0) * 1000 / (t1 - t0)
            recent = any(t1 - 3000 <= t <= t1 for t in times)
            if recent:
                follow.append(share)
            elif not busy0 and not busy1:
                rest.append(share)
        return {"rest": spread(rest), "following": spread(follow)}
