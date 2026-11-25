"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: the stand-in's window moved over this computer's monitors as they are
and resized as a drag of its edge or corner resizes it, in an end-to-end run (`standin_e2e.py`: the scenarios m0-m4
and r1-r8, by their names only), and what TASlation's windows did meanwhile - numbers only. No display setting is
changed, nothing of another program's is moved, no key or click goes to the system.

* `Screens`: the monitors (each one's rectangle, work area and DPI, the primary first, numbered from 1).
* `WindowSteps`: what is done to the stand-in's window - the tool's own browser's -: placed (``SetWindowPos`` without
  activation), maximised on its monitor (never on the primary: refused there) with the foreground locked meanwhile
  (`standin_viewer.lock_foreground`) and looked at after, restored without activation; and `Drag`, a thread that gives
  it many sizes over DRAG_S as a drag of an edge or a corner does - with the see-through watch's own button held
  (`standin_seethrough.SeeWatch.fake_button`: what TASlation reads as the mouse's button; the real one is never
  pressed) from PRESS_LEAD_S before the first size to RELEASE_AFTER_S after the last, its pointer at the edge dragged,
  or with no button (a resize by a tool or the keyboard). A real drag runs the window's own sizing loop
  (WM_ENTERSIZEMOVE); these sizes come as a program's moves do.
* `Sampler`: a thread that looks every SAMPLE_S (FAST_SAMPLE_S while the window changes) at the stand-in's window and
  client area, the lettering's window and the set it shows, the side panes and why each is not shown, the editing
  marks, the region editor's place, the hidden window's monitor, the scales in force and the page's regions as each
  result has them; numbers only.
* `Tour`: on the Tk thread, once the window is at rest at a place, the window's dialogs and menus opened through
  their own objects one after the other (the viewer chooser, Series and Volume, Settings, the legal notice, the GPU's
  box, How to use, the region editor and the place entry on the first region, the Menu and the list of target
  languages), each measured twice (its monitor, its work area, Tk's scale) and closed again; meanwhile the foreground
  is locked and nothing of TASlation's may hand it over (`windows.give_foreground`, `see_menu._front`: replaced by
  ones that only count), and who is in front is read before and after each.
* `report`: per segment of these scenarios, the tables (`standin_e2e.print_table` prints them)."""

from __future__ import annotations

import ctypes
import os
import statistics
import threading
import time
from collections import Counter
from ctypes import wintypes
from typing import Any, Callable

SAMPLE_S = 0.05
FAST_SAMPLE_S = 0.015
DRAG_S = 1.5  # a drag's sizes come over so long ...
DRAG_STEPS = 45  # ... so many of them
PRESS_LEAD_S = 0.12  # the button held so long before the first size ...
RELEASE_AFTER_S = 0.10  # ... and let go so long after the last
STEP_REST_S = 1.0  # a window step done this long before its scenario may be released
TOUR_SHOWN_S = 0.35  # a dialog measured so long after it is on the screen, and again so long after that
TOUR_WAIT_S = 2.5  # ... waited for so long at the most
MENU_LOOK_MS = 300  # a menu measured so long after it was posted, then ended (`EndMenu`)
ESC_AFTER_S = 2.5  # ... Escape posted to the menu's own window should it still be up then
TOUR = ("chooser", "book", "settings", "notice", "gpu", "help", "editor", "place_entry", "menu", "languages")
FOOT_PX = 2  # (`fits`) a box this near the edge of another still lies in it

_u = ctypes.WinDLL("user32", use_last_error=True)
_u.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
_u.MonitorFromPoint.restype = wintypes.HMONITOR
_u.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
_u.MonitorFromWindow.restype = wintypes.HMONITOR
_u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_u.IsWindowVisible.argtypes = [wintypes.HWND]
_u.IsZoomed.argtypes = [wintypes.HWND]
_u.IsIconic.argtypes = [wintypes.HWND]
_u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                            wintypes.UINT]
_u.GetForegroundWindow.restype = wintypes.HWND
_u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_u.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
_u.FindWindowExW.restype = wintypes.HWND
_u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
SW_MAXIMIZE, SW_SHOWNOACTIVATE, SW_SHOWMINNOACTIVE = 3, 4, 7
SWP_NOZORDER, SWP_NOACTIVATE = 0x0004, 0x0010
MONITOR_DEFAULTTONULL, MONITOR_DEFAULTTONEAREST = 0, 2


def now_ms() -> float:
    return time.time() * 1000.0


def window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    r = wintypes.RECT()
    if not hwnd or not _u.GetWindowRect(hwnd, ctypes.byref(r)):
        return None
    return (r.left, r.top, r.right, r.bottom)


def pid_of(hwnd: int) -> int:
    pid = wintypes.DWORD(0)
    if hwnd:
        _u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def inside(box: Any, area: Any, slack: int = FOOT_PX) -> bool:
    """Whether the rectangle *box* (left, top, right, bottom) lies in *area*."""
    return (box is not None and area is not None and box[0] >= area[0] - slack and box[1] >= area[1] - slack
            and box[2] <= area[2] + slack and box[3] <= area[3] + slack)


def where(e: BaseException) -> list[str]:
    """The last frames of *e*'s traceback as file:line function (no value of any variable)."""
    import traceback

    return [f"{os.path.basename(f.filename)}:{f.lineno} {f.name}" for f in traceback.extract_tb(e.__traceback__)[-3:]]


def on_a_runner() -> bool:
    """Whether this runs on one of GitHub's runners (its own GITHUB_ACTIONS): a computer of its own, one monitor."""
    return os.environ.get("GITHUB_ACTIONS") == "true"


def spread(values: list[float]) -> dict[str, Any]:
    v = sorted(x for x in values if x is not None)
    if not v:
        return {"n": 0}
    return {"n": len(v), "median": round(statistics.median(v), 1), "p90": round(v[int(0.9 * (len(v) - 1))], 1),
            "max": round(v[-1], 1)}


# ---------------------------------------------------------------------------------------------------- the monitors
class Screens:
    """The monitors as they are: each one's rectangle, work area, DPI and handle, the primary first (numbered from
    1 in that order)."""

    def __init__(self) -> None:
        self.monitors: list[dict[str, Any]] = []

        class Info(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD)]

        try:
            shcore = ctypes.WinDLL("shcore")
        except OSError:
            shcore = None

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                            wintypes.LPARAM)
        def each(handle, _dc, _rect, _lparam):  # type: ignore[no-untyped-def]
            info = Info()
            info.cbSize = ctypes.sizeof(Info)
            if _u.GetMonitorInfoW(handle, ctypes.byref(info)):
                m, w = info.rcMonitor, info.rcWork
                dpi = None
                if shcore is not None:
                    x, y = ctypes.c_uint(0), ctypes.c_uint(0)
                    if shcore.GetDpiForMonitor(handle, 0, ctypes.byref(x), ctypes.byref(y)) == 0:
                        dpi = int(x.value)
                self.monitors.append({"handle": int(handle or 0), "rect": (m.left, m.top, m.right, m.bottom),
                                      "work": (w.left, w.top, w.right, w.bottom), "primary": bool(info.dwFlags & 1),
                                      "dpi": dpi})
            return True

        _u.EnumDisplayMonitors(0, 0, each, 0)
        self.monitors.sort(key=lambda m: (not m["primary"], m["rect"][0], m["rect"][1]))

    def number(self, handle: int) -> int | None:
        return next((i + 1 for i, m in enumerate(self.monitors) if m["handle"] == int(handle or 0)), None)

    def at(self, x: int, y: int) -> int | None:
        """The monitor the screen point is on (None: on none)."""
        return self.number(_u.MonitorFromPoint(wintypes.POINT(int(x), int(y)), MONITOR_DEFAULTTONULL) or 0)

    def of_window(self, hwnd: int) -> int | None:
        """The monitor that holds most of the window (Windows' own choice; the nearest when it is on none)."""
        return self.number(_u.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST) or 0) if hwnd else None

    def on_any(self, hwnd: int) -> bool:
        return bool(hwnd) and bool(_u.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONULL))

    def met(self, box: Any) -> list[int]:
        """The monitors the rectangle meets, the one it shares most with first."""
        if box is None:
            return []
        shares = []
        for i, m in enumerate(self.monitors):
            r = m["rect"]
            w, h = min(box[2], r[2]) - max(box[0], r[0]), min(box[3], r[3]) - max(box[1], r[1])
            if w > 0 and h > 0:
                shares.append((-(w * h), i + 1))
        return [n for _s, n in sorted(shares)]

    def monitor(self, number: int | None) -> dict[str, Any] | None:
        return self.monitors[number - 1] if number and 1 <= number <= len(self.monitors) else None

    def facts(self) -> list[dict[str, Any]]:
        return [{"n": i + 1, "rect": list(m["rect"]), "work": list(m["work"]), "primary": m["primary"],
                 "dpi": m["dpi"]} for i, m in enumerate(self.monitors)]


def taskbar_setting() -> dict[str, Any]:
    """How the taskbars show the buttons, read from the person's settings (read only): a taskbar on every monitor or
    the primary's alone, and on which of them a window's button shows (Explorer's MMTaskbarEnabled, MMTaskbarMode)."""
    out: dict[str, Any] = {"all_monitors": None, "mode": None}
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced") as key:
            for name, label in (("MMTaskbarEnabled", "all_monitors"), ("MMTaskbarMode", "mode")):
                try:
                    out[label] = int(winreg.QueryValueEx(key, name)[0])
                except OSError:
                    pass
    except OSError:
        pass
    mode = out["mode"]
    out["buttons_on"] = ("the primary's taskbar alone (one taskbar)" if out["all_monitors"] in (0, None) else
                         "every taskbar" if mode in (0, None) else
                         "the primary's taskbar and the one where the window is" if mode == 1 else
                         "the taskbar where the window is")
    return out


# ---------------------------------------------------------------------------------------------------- the window steps
class WindowSteps:
    """What is done to the stand-in's window (*hwnd*, the tool's own browser's, its processes *tree*): nothing is
    activated, the primary monitor is never covered by a maximised window."""

    def __init__(self, hwnd: int, screens: Screens, tree: Callable[[], set[int]], lock: Callable[[bool], bool]):
        self.hwnd, self.screens, self.tree, self.lock = int(hwnd), screens, tree, lock

    def front(self) -> str:
        hwnd = int(_u.GetForegroundWindow() or 0)
        if not hwnd:
            return "none"
        pid = pid_of(hwnd)
        return "standin" if pid in self.tree() else "own" if pid == os.getpid() else "other"

    def place(self, rect: tuple[int, int, int, int]) -> None:
        """To *rect* (x, y, width, height: its outer rectangle), not activated, its place in the order kept."""
        x, y, w, h = (int(v) for v in rect)
        _u.SetWindowPos(self.hwnd, None, x, y, w, h, SWP_NOACTIVATE | SWP_NOZORDER)

    def maximise(self) -> dict[str, Any]:
        """Maximised on the monitor that holds most of it - refused on the primary (but on one of GitHub's runners,
        `on_a_runner`: its one monitor, with nothing of a person's on it) -, the foreground locked meanwhile; whether it
        took the foreground all the same (then minimised without activation and shown again without it: Windows gives
        the foreground back to the window behind)."""
        n = self.screens.of_window(self.hwnd)
        monitor = self.screens.monitor(n)
        if monitor is None or (monitor["primary"] and not on_a_runner()):
            return {"refused": "the primary monitor is never covered by a maximised window", "monitor": n}
        before = self.front()
        locked = self.lock(True)
        try:
            _u.ShowWindow(self.hwnd, SW_MAXIMIZE)
            end = time.monotonic() + 1.0
            while not _u.IsZoomed(self.hwnd) and time.monotonic() < end:
                time.sleep(0.02)
            time.sleep(0.15)
            after = self.front()
            took = after == "standin" and before != "standin"
            if took:
                _u.ShowWindow(self.hwnd, SW_SHOWMINNOACTIVE)
                time.sleep(0.1)
                _u.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        finally:
            if locked:
                self.lock(False)
        return {"monitor": n, "zoomed": bool(_u.IsZoomed(self.hwnd)), "front_before": before, "front_after": after,
                "took_the_foreground": took, "foreground_locked": bool(locked)}

    def restore(self) -> dict[str, Any]:
        """Back from maximised without activation."""
        before = self.front()
        _u.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        end = time.monotonic() + 1.0
        while _u.IsZoomed(self.hwnd) and time.monotonic() < end:
            time.sleep(0.02)
        return {"zoomed": bool(_u.IsZoomed(self.hwnd)), "front_before": before, "front_after": self.front()}


def edge_point(rect: tuple[int, int, int, int], edge: str) -> tuple[int, int]:
    """Where the pointer is while *edge* of the window *rect* (x, y, width, height) is dragged: on its frame."""
    x, y, w, h = rect
    right, bottom = x + w - 3, y + h - 3
    return {"right": (right, y + h // 2), "bottom": (x + w // 2, bottom), "corner": (right, bottom),
            "left": (x + 3, y + h // 2)}.get(edge, (right, bottom))


class Drag(threading.Thread):
    """The window *hwnd* given DRAG_STEPS sizes from *start* to *end* (x, y, width, height) over DRAG_S, as the drag
    of *edge* gives them; with *button* the watch's button held from PRESS_LEAD_S before to RELEASE_AFTER_S after
    (and its pointer at the edge), without it none. `facts`: when, numbers only."""

    def __init__(self, steps: WindowSteps, start: tuple[int, int, int, int], end: tuple[int, int, int, int], edge: str,
                 watch: Any, button: bool, seconds: float = DRAG_S, count: int = DRAG_STEPS):
        super().__init__(name="standin-drag", daemon=True)
        self.steps, self.start_rect, self.end_rect, self.edge = steps, start, end, edge
        self.watch, self.button, self.seconds, self.count = watch, bool(button), seconds, max(1, int(count))
        self.facts: dict[str, Any] = {"edge": edge, "button": self.button, "from": list(start), "to": list(end),
                                      "press_t": None, "first_t": None, "last_t": None, "release_t": None,
                                      "sizes": 0, "front_before": steps.front(), "front_after": None}

    def run(self) -> None:
        watch, f = self.watch, self.facts
        try:
            if self.button:
                watch.fake_point = edge_point(self.start_rect, self.edge)
                watch.fake_button = True
                f["press_t"] = now_ms()
                time.sleep(PRESS_LEAD_S)
            for k in range(1, self.count + 1):
                share = k / self.count
                rect = tuple(round(a + (b - a) * share) for a, b in zip(self.start_rect, self.end_rect))
                if self.button:  # (the pointer moves first, the window's edge follows it)
                    watch.fake_point = edge_point(rect, self.edge)  # type: ignore[arg-type]
                self.steps.place(rect)  # type: ignore[arg-type]
                f["first_t"] = f["first_t"] or now_ms()
                f["last_t"] = now_ms()
                f["sizes"] += 1
                time.sleep(self.seconds / self.count)
            if self.button:
                time.sleep(RELEASE_AFTER_S)
        finally:
            if self.button:
                watch.fake_button = False
                watch.fake_point = None
                f["release_t"] = now_ms()
            f["front_after"] = self.steps.front()


def watch_pane_whys(holder: Any) -> None:
    """`ui.seethrough.panes_tick`'s two calls of `pane_on_screen` (the left pane's box, then the right one's) and
    `panes.place` watched, so that a pane not handed over is told by why in *holder*'s ``pane_why`` (side -> why, ""
    for none): no ground yet, no room, off the screen (`Sampler`, `standin_seethrough.SeeWatch`: each install wraps
    what is there, another's hooks too)."""
    from taslation import panes as pn
    from taslation.ui import seethrough as ui

    tick, on_screen, place = ui.panes_tick, ui.pane_on_screen, pn.place
    calls = {"n": 0}

    def ticked(app: Any) -> Any:
        calls["n"] = 0
        if getattr(app, "_see_ground", None) is None:
            holder.pane_why = {"left": "no ground", "right": "no ground"}
        return tick(app)

    def placed(*a: Any, **k: Any) -> Any:
        out = place(*a, **k)
        holder.pane_why = {"left": "" if out[0] is not None else "no room",
                           "right": "" if out[1] is not None else "no room"}
        return out

    def screened(box: Any, origin: Any) -> Any:
        side = "left" if calls["n"] % 2 == 0 else "right"
        calls["n"] += 1
        out = on_screen(box, origin)
        if box is not None and out is None:
            holder.pane_why[side] = "off the screen"
        return out

    ui.panes_tick = ticked
    ui.pane_on_screen = screened
    pn.place = placed


def other_why(over: Any, side: str) -> str:
    """Why the side pane *side*, handed over by the Tk thread, is not on the screen though `watch_pane_whys` found no
    reason: the viewer sized with the pointer, or a window above the viewer meeting it ("" for neither)."""
    if getattr(over, "_sizing", False):
        return "sizing"  # (the viewer sized with the pointer: `SeeThrough._sizing_tick`)
    if _covered_pane(over, side):
        return "covered"  # (a window above the viewer meets it: the region editor, a dialog, another program's)
    return ""


def _covered_pane(over: Any, side: str) -> bool:
    """Whether the side pane *side* the Tk thread handed over is left out for a window above the viewer that meets it
    (the see-through window's `_covers`: the region editor, a dialog), as `SeeThrough._place_panes` finds it."""
    from taslation import seethrough as st

    want = (getattr(over, "_pane_want", None) or {}).get(side)
    origin = over.client_origin() if callable(getattr(over, "client_origin", None)) else None
    if want is None or origin is None:
        return False
    _serial, bgra, box = want[:3]
    height, width = bgra.shape[:2]
    return bool(st.covered((box[0], box[1], box[0] + width, box[1] + height), origin,
                           list(getattr(over, "_covers", None) or [])))


# ---------------------------------------------------------------------------------------------------- the looks
class Sampler(threading.Thread):
    """Every SAMPLE_S (FAST_SAMPLE_S while *fast*() says the window changes) a look at the stand-in (*hwnd*) and at
    TASlation's windows over it, kept in `rows` (numbers only); the page's regions as each new result has them in
    `results`; why each side pane is not shown, as the Tk thread found it (`install`), in `pane_why`."""

    def __init__(self, app: Any, hwnd: int, screens: Screens, fast: Callable[[], bool],
                 screen_of: Callable[[Any], Any] | None = None):
        super().__init__(name="standin-monitors", daemon=True)
        self.app, self.hwnd, self.screens, self.fast = app, int(hwnd), screens, fast
        self.screen_of = screen_of  # (a frame to the stand-in's screen it shows, (page, spread) or None)
        self.rows: list[dict[str, Any]] = []
        self.results: list[dict[str, Any]] = []
        self.pane_why: dict[str, str] = {"left": "", "right": ""}
        self.stop = threading.Event()
        self._result_id = 0
        self.editor: tuple[int, tuple[int, int, int, int] | None] = (0, None)  # (its frame, its region's box)
        self.editor_page: tuple[Any, Any] | None = None  # (the editor's page: its frame's size, the screen)
        self._editor_region = 0  # (the id of the region it was seen on last)
        self.editor_carry: dict[str, Any] | None = None  # (`carry_facts` of the editor's page and the one on show)
        self.tk_errors: Counter[str] = Counter()  # (`tk_look`'s failures, by type and where)
        # (frame width, height, the screen's first page, spread) -> the page as the stand-in drew it there (its
        # canvas's pixels: `standin_e2e.Director.pull` puts each draw's in)
        self.page_rects: dict[tuple[int, int, int, bool], tuple[int, int, int, int]] = {}

    def install(self) -> None:
        """Why a side pane is not handed over, kept in `pane_why` (`watch_pane_whys`)."""
        watch_pane_whys(self)

    def tk_look(self) -> None:
        """(the Tk thread, each tick) The region editor's frame and its region's box in the page, for `look`; the
        page it opened on (its frame's size and the stand-in's screen there, `editor_page`) as the editor is first seen."""
        editor = getattr(self.app, "_editor", None)
        try:
            if editor is not None and editor.winfo_exists():
                region = getattr(editor, "region", None)
                box = tuple(int(v) for v in region.bbox) if region is not None else None
                frame = int(editor.wm_frame(), 16)
                if frame != self.editor[0] or id(region) != self._editor_region:  # (a new editor, or its page taken
                    self._editor_region = id(region)  # again: `TranslatorMixin._carry_editor`)
                    original = getattr(getattr(self.app, "last_result", None), "original", None)
                    screen = None
                    if original is not None and self.screen_of is not None:
                        try:
                            screen = self.screen_of(original)
                        except Exception:  # noqa: BLE001 - not told
                            screen = None
                    self.editor_page = (tuple(original.size), tuple(screen) if screen else None) \
                        if original is not None else None
                self.editor = (frame, box)  # type: ignore[assignment]
                held, new = getattr(self.app, "_editor_held", None), getattr(self.app, "last_result", None)
                if held is None:
                    self.editor_carry = {"held": None}
                elif new is not None and held.result is new:
                    self.editor_carry = {"on_its_page": list(new.original.size), "region_held": held.region is region}
                elif new is not None:
                    try:
                        self.editor_carry = carry_facts(held.result, new, held.region)
                    except Exception as e:  # noqa: BLE001 - said by its type and where it rose
                        self.editor_carry = {"error": type(e).__name__, "at": where(e)}
                return
        except Exception as e:  # noqa: BLE001 - (going; counted by where it rose)
            self.tk_errors[f"{type(e).__name__} {' < '.join(where(e))}"] += 1
        self.editor = (0, None)

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                self.look()
            except Exception:  # noqa: BLE001 - a look that failed is a look less
                pass
            self.stop.wait(FAST_SAMPLE_S if self.fast() else SAMPLE_S)

    def look(self) -> None:
        from taslation.capture import windows
        from taslation.ui import seethrough as ui

        app, s = self.app, self.screens
        t = now_ms()
        outer = window_rect(self.hwnd)
        x, y, w, h = windows._client_box(self.hwnd)
        client = (x, y, x + w, y + h)
        row: dict[str, Any] = {"t": t, "outer": outer, "client": client, "zoomed": bool(_u.IsZoomed(self.hwnd)),
                               "monitor": s.of_window(self.hwnd), "met": s.met(outer)}
        over = getattr(app, "_see_through", None)
        if over is not None:
            shown = over.shown()
            sets = {k.serial: k for k in list(over._store.sets)}
            if shown is not None:
                serial, indices, origin, size = shown
                chosen = sets.get(serial)
                row["shown"] = {"origin": tuple(origin), "size": tuple(size), "n": len(indices),
                                "set_size": tuple(chosen.size) if chosen is not None else None,
                                "final": bool(chosen.final) if chosen is not None else None}
            hwnd = int(getattr(over, "hwnd", 0) or 0)
            row["overlay"] = window_rect(hwnd) if hwnd and _u.IsWindowVisible(hwnd) else None
            panes = {}
            for side in ("left", "right"):
                box = over.pane_shown(side)
                pane = int((getattr(over, "panes", {}) or {}).get(side, 0) or 0)
                why = self.pane_why.get(side, "")
                if box is None and not why:
                    why = other_why(over, side)
                panes[side] = {"box": tuple(box) if box is not None else None,
                               "visible": bool(pane and _u.IsWindowVisible(pane)),
                               "monitors": s.met(box) if box is not None else [],
                               "why": why}
            row["panes"] = panes
            marks = getattr(over, "_marks", None)
            if marks is not None:
                own = next((k for k in sets.values() if k.key == marks.key), None)
                row["marks"] = {"boxes": len(marks.boxes), "set_size": tuple(own.size) if own is not None else None}
            row["over_dpi"] = getattr(over, "_dpi", None)
        root = int(getattr(app, "_see_root_hwnd", 0) or 0)
        row["root"] = {"monitor_nearest": s.of_window(root), "on_a_monitor": s.on_any(root)} if root else None
        row["see_dpi"] = getattr(app, "_see_dpi", None)
        try:
            row["left_room"] = ui.left_room(app)  # (none: the taskbar button's click gives the Menu)
        except Exception:  # noqa: BLE001 - not told
            row["left_room"] = None
        try:
            row["dialog_dpi"] = ui.dialog_dpi(app)
        except Exception:  # noqa: BLE001 - not told
            row["dialog_dpi"] = None
        editor, region = self.editor  # (the Tk thread's, `tk_look`: no Tk call from this thread)
        if editor and _u.IsWindowVisible(editor):
            row["editor"] = window_rect(editor)
            row["editor_monitors"] = s.met(row["editor"]) if row["editor"] is not None else []
            row["editor_box"], row["editor_page"] = region, self.editor_page
            row["editor_carry"] = self.editor_carry
            origin = over.client_origin() if over is not None else None
            if region is not None and origin is not None:
                b = region
                row["editor_region"] = (origin[0] + b[0], origin[1] + b[1], origin[0] + b[2], origin[1] + b[3])
        result = getattr(app, "last_result", None)
        if result is not None and id(result) != self._result_id and getattr(result, "original", None) is not None:
            self._result_id = id(result)
            boxes = [tuple(int(v) for v in r.bbox) for r in list(getattr(result, "regions", None) or ())]
            screen = None
            if self.screen_of is not None:
                try:
                    screen = self.screen_of(result.original)
                except Exception:  # noqa: BLE001 - not told
                    screen = None
            self.results.append({"t": t, "id": id(result), "size": tuple(result.original.size), "boxes": boxes,
                                 "screen": tuple(screen) if screen else None, "client": client})
        self.rows.append(row)


# ---------------------------------------------------------------------------------------------------- the dialogs
class Tour:
    """The window's dialogs and menus, opened one after the other through their own objects and measured (`TOUR`),
    stepped from the Tk loop (`step`, each tick). Nothing of TASlation's may hand the foreground over meanwhile and it
    is locked; who is in front is read before and after each."""

    def __init__(self, app: Any, hwnd: int, screens: Screens, steps: WindowSteps, lock: Callable[[bool], bool]):
        self.app, self.hwnd, self.screens, self.steps, self.lock = app, int(hwnd), screens, steps, lock
        self.rows: list[dict[str, Any]] = []
        self.queue: list[str] = []
        self.label = ""
        self.item: dict[str, Any] | None = None
        self.handed: Counter[str] = Counter()  # the hand-overs of the foreground refused meanwhile
        self._undo: list[Callable[[], None]] = []
        self.locked = False
        self.watch: Any = None  # (the see-through watch: its pointer, `_button_menu`)

    def busy(self) -> bool:
        return bool(self.queue) or self.item is not None

    def start(self, label: str, items: tuple[str, ...] = TOUR) -> None:
        self.label, self.queue = label, list(items)
        self._quiet()

    def _quiet(self) -> None:
        """`windows.give_foreground` (wherever TASlation holds it) and `see_menu._front` replaced by ones that only
        count, until the tour ends."""
        import demo_video
        from taslation.capture import windows
        from taslation.ui import see_menu

        original = getattr(windows.give_foreground, "__wrapped__", None) or windows.give_foreground
        current = windows.give_foreground

        def refused(hwnd: int, *_a: Any, **_k: Any) -> bool:
            self.handed["give_foreground"] += 1
            return False

        refused.__wrapped__ = original  # type: ignore[attr-defined]
        n = demo_video.replace_everywhere(current, refused)
        front = see_menu._front

        def no_front(hwnd: int) -> bool:
            self.handed["menu_front"] += 1
            return False

        see_menu._front = no_front
        self._undo = [lambda: demo_video.replace_everywhere(refused, current),
                      lambda: setattr(see_menu, "_front", front)]
        self.handed["replaced_in_modules"] = n

    def _end(self) -> None:
        for undo in self._undo:
            undo()
        self._undo = []

    def step(self) -> None:
        if self.item is None:
            if not self.queue:
                return
            name = self.queue.pop(0)
            self.item = {"name": name, "phase": "open", "t0": time.monotonic()}
        item = self.item
        try:
            getattr(self, f"_{item['phase']}")(item)
        except Exception as e:  # noqa: BLE001 - noted by its type and where (no value), the next one goes on
            row = item.setdefault("row", {})
            row["error"] = type(e).__name__
            row["error_at"] = where(e)
            self._close(item)
        if self.item is None and not self.queue:
            self._end()

    # the phases
    def _open(self, item: dict[str, Any]) -> None:
        from taslation.ui import see_edit, see_menu

        app, name = self.app, item["name"]
        row = item["row"] = {"segment": self.label, "item": name, "front_before": self.steps.front()}
        self.locked = bool(self.lock(True))
        row["foreground_locked"] = self.locked
        regions = list(app._page_regions()) if callable(getattr(app, "_page_regions", None)) else []
        widget: Any = None
        if name == "chooser":
            widget = see_menu.open_viewer(app)
        elif name == "book":
            widget = see_menu.open_book(app)
        elif name == "settings":
            app.open_settings()
            widget = getattr(app, "_settings_dialog", None)
        elif name == "notice":
            from pathlib import Path

            from taslation.ui.dialogs.notice import NoticeDialog

            widget = NoticeDialog(app, Path(app.settings.state_dir), "en", startup=False)
        elif name == "gpu":
            from taslation.ui.dialogs.gpu_short import GpuShortDialog

            widget = GpuShortDialog(app, 1500, ("ocr",), lambda _c, _r: None)
        elif name == "help":
            app.open_help()
            widget = getattr(app, "_help", None)
        elif name == "editor":
            if not regions:
                row["skipped"] = "no region on the page"
            else:
                see_edit.open_editor(app, regions[0])
                widget = getattr(app, "_editor", None)
                row["region_screen"] = self._region_box(regions[0])
        elif name == "place_entry":
            if not regions or not see_edit.open_place_entry(app, regions[0]):
                row["skipped"] = "no region on the page, or not placed"
            else:  # (measured at once: an entry that does not get the keys - the foreground locked - goes by itself)
                entry = getattr(app, "_see_place_entry", None)
                widget = getattr(entry, "top", None)
                if widget is not None:
                    widget.update_idletasks()
                    row["first"] = self._measure(widget)
                    item["widget"] = widget
                    self._close(item)
                    return
        elif name in ("menu", "languages"):
            self._menu(item)
            return
        elif name == "button_menu":
            self._button_menu(item)
            return
        item["widget"] = widget
        if widget is None:
            row.setdefault("skipped", "not opened")
            self._close(item)
            return
        item["phase"], item["since"] = "wait", time.monotonic()

    def _region_box(self, region: Any) -> list[int] | None:
        over = getattr(self.app, "_see_through", None)
        origin = over.client_origin() if over is not None else None
        if origin is None:
            return None
        b = [int(v) for v in region.bbox]
        return [origin[0] + b[0], origin[1] + b[1], origin[0] + b[2], origin[1] + b[3]]

    def _wait(self, item: dict[str, Any]) -> None:
        widget = item["widget"]
        try:
            viewable = bool(widget.winfo_exists() and widget.winfo_viewable())
        except Exception:  # noqa: BLE001 - (gone)
            viewable = False
        now = time.monotonic()
        if viewable and "shown_at" not in item:
            item["shown_at"] = now
            item["row"]["shown_ms"] = round((now - item["t0"]) * 1000)
        if "shown_at" in item and now - item["shown_at"] >= TOUR_SHOWN_S:
            item["row"]["first"] = self._measure(widget)
            item["phase"], item["since"] = "again", now
        elif now - item["t0"] > TOUR_WAIT_S:
            item["row"]["never_shown"] = True
            item["row"]["first"] = self._measure(widget)
            self._close(item)

    def _again(self, item: dict[str, Any]) -> None:
        if time.monotonic() - item["since"] >= TOUR_SHOWN_S:
            item["row"]["second"] = self._measure(item["widget"])
            self._close(item)

    def _measure(self, widget: Any) -> dict[str, Any]:
        try:
            hwnd = int(widget.wm_frame(), 16)
        except Exception:  # noqa: BLE001 - (no frame)
            hwnd = int(widget.winfo_id())
        return self._facts(window_rect(hwnd))

    def _facts(self, rect: tuple[int, int, int, int] | None) -> dict[str, Any]:
        s = self.screens
        viewer_n = s.of_window(self.hwnd)
        viewer = s.monitor(viewer_n)
        out: dict[str, Any] = {"rect": list(rect) if rect else None, "viewer_monitor": viewer_n,
                               "viewer_met": s.met(window_rect(self.hwnd))}
        if rect is None:
            return out
        centre = ((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2)
        on = s.at(*centre)
        out.update({"monitor": on, "met": s.met(rect), "on_viewer_monitor": on == viewer_n,
                    "in_viewer_work_area": inside(rect, viewer["work"]) if viewer else None})
        root = int(getattr(self.app, "_see_root_hwnd", 0) or 0)
        out["root_monitor_nearest"] = s.of_window(root) if root else None
        try:
            scaling = float(self.app.tk.call("tk", "scaling"))
            ui_scale = float(getattr(self.app.settings, "ui_scale", 1.0) or 1.0)
            out["tk_dpi"] = round(scaling * 72 / ui_scale)
        except Exception:  # noqa: BLE001 - not told
            out["tk_dpi"] = None
        out["monitor_dpi"] = (s.monitor(on) or {}).get("dpi")
        return out

    def _button_menu(self, item: dict[str, Any]) -> None:
        """A click on TASlation's taskbar button while the left pane has no room, as the window takes it
        (`ui.seethrough.front_tick` with *clicked*: the Menu at the pointer), the watch's pointer on the primary
        monitor's taskbar - where this computer's one taskbar is (`taskbar_setting`) - and no click made; whether it
        came and where (`_menu`)."""
        from taslation.ui import seethrough as ui

        primary = self.screens.monitor(1)
        watch = self.watch
        if primary is None or watch is None:
            item["row"]["skipped"] = "no primary monitor or no watch"
            self._close(item)
            return
        r, w = primary["rect"], primary["work"]
        point = ((r[0] + r[2]) // 2, (w[3] + r[3]) // 2 if w[3] < r[3] else r[3] - 20)
        item["row"].update({"left_room": ui.left_room(self.app), "pointer": list(point)})
        watch.fake_point = point
        try:
            self._menu(item, opener=lambda: ui.front_tick(self.app, clicked=True) == "menu")
        finally:
            watch.fake_point = None

    def _menu(self, item: dict[str, Any], opener: Callable[[], bool] | None = None) -> None:
        """The Menu or the list of target languages at the left pane, as its click posts it (`see_menu`; *opener*:
        another way it comes): measured MENU_LOOK_MS after it is up (Windows' menu window of this process) and ended
        (`EndMenu`, from Tk's timer that runs while the menu is; Escape posted to the menu's own window after
        ESC_AFTER_S should it still be up)."""
        from taslation.ui import see_menu

        app, row = self.app, item["row"]
        found: dict[str, Any] = {}

        def look() -> None:
            hwnd = self._menu_window()
            found["rect"] = window_rect(hwnd) if hwnd else None
            _u.EndMenu()

        def fallback() -> None:
            time.sleep(ESC_AFTER_S)
            hwnd = self._menu_window()
            if hwnd:
                found["escape"] = True
                _u.PostMessageW(hwnd, 0x0100, 0x1B, 0)
                _u.PostMessageW(hwnd, 0x0101, 0x1B, 0)

        threading.Thread(target=fallback, name="tour-menu-escape", daemon=True).start()
        job = app.after(MENU_LOOK_MS, look)
        t = time.monotonic()
        if opener is None:
            opener = (lambda: see_menu.popup_at_pane(app)) if item["name"] == "menu" else (
                lambda: see_menu.languages_at_pane(app))
        opened = opener()
        if not opened:
            try:
                app.after_cancel(job)
            except Exception:  # noqa: BLE001
                pass
            row["skipped"] = "no left pane" if item["name"] != "button_menu" else "not opened"
        row["up_ms"] = round((time.monotonic() - t) * 1000)
        row["first"] = self._facts(found.get("rect"))
        row["escape_needed"] = bool(found.get("escape"))
        self._close(item)

    @staticmethod
    def _menu_window() -> int:
        hwnd = None
        for _ in range(64):
            hwnd = _u.FindWindowExW(None, hwnd, "#32768", None)
            if not hwnd:
                return 0
            if pid_of(hwnd) == os.getpid() and _u.IsWindowVisible(hwnd):
                return int(hwnd)
        return 0

    def _close(self, item: dict[str, Any]) -> None:
        from taslation.ui import see_edit

        app, name, widget = self.app, item["name"], item.get("widget")
        try:
            if name == "editor":
                editor = getattr(app, "_editor", None)
                if editor is not None and editor.winfo_exists():
                    editor.close_asked()
            elif name == "place_entry":
                see_edit.drop_place_entry(app)
            elif widget is not None and widget.winfo_exists():
                widget.destroy()
        except Exception as e:  # noqa: BLE001 - noted
            item.setdefault("row", {})["close_error"] = type(e).__name__
        row = item.setdefault("row", {})
        row["front_after"] = self.steps.front()
        if self.locked:
            self.lock(False)
            self.locked = False
        self.rows.append(row)
        self.item = None


# ---------------------------------------------------------------------------------------------------- the run
M_NAMES = ("m0", "m1", "m2", "m3", "m4")
R_NAMES = ("r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8")
EDITOR_LEAD_S = 0.8  # (r1 while editing) the region editor opened so long before the drag begins
# what is opened and measured at rest after a step: every dialog and menu at each m place; after the first r step
# that leaves the left pane no room (r4's corner, say), a click on the taskbar button as the window takes it
TOURS: dict[str, tuple[str, ...]] = {n: TOUR for n in M_NAMES}


class WindowRun:
    """The window steps of the m and r scenarios and the tours at the m places, driven from `standin_e2e.Director`
    on the Tk loop: `may_begin` (the window at rest, the watch's own pointer scene over), `begin` (the step: a place,
    a maximise or restore, a `Drag`), `ready` (the step done and the window at rest again, the tour at an m place
    over), `fast` (the looks quicker while the window changes), `tick` (when the watch's pointer scene ran);
    `report` the tables. *start*: the stand-in's place at the start (x, y, width, height); *editing*: the role kept
    as editing - r1 then opens the region editor on the page's first region before its drag (and r2 closes it)."""

    def __init__(self, app: Any, hwnd: int, screens: Screens, steps: WindowSteps, sampler: Sampler, tour: Tour,
                 start: tuple[int, int, int, int], see: Any, editing: bool = False):
        self.app, self.hwnd, self.screens, self.steps, self.sampler, self.tour = app, int(hwnd), screens, steps, \
            sampler, tour
        self.start_rect, self.see, self.editing = tuple(start), see, bool(editing)
        self.start_monitor = screens.of_window(hwnd)
        if tour is not None:
            tour.watch = see
        self.records: list[dict[str, Any]] = []
        self.drag: Drag | None = None
        self.done_at: float | None = None
        self.toured: set[str] = set()
        self.hover_span: list[float | None] = [None, None]
        self.editor_open = False
        self.opened_on: dict[str, Any] | None = None  # (r1: the page and region the editor opened on, numbers only)
        self._touring: str | None = None  # (the m place whose tour runs)
        self._items: dict[str, tuple[str, ...]] = {}  # (what each step's tour opens, `ready`)
        self._button_toured = False

    # where
    def _rect(self) -> tuple[int, int, int, int]:
        r = window_rect(self.hwnd) or (0, 0, 0, 0)
        return (r[0], r[1], r[2] - r[0], r[3] - r[1])

    def _other(self) -> int | None:
        here = self.screens.of_window(self.hwnd)
        others = [i + 1 for i in range(len(self.screens.monitors)) if i + 1 != here]
        return others[0] if others else None

    def _second(self) -> int | None:
        return next((i + 1 for i, m in enumerate(self.screens.monitors) if not m["primary"]), None)

    def _on(self, n: int | None, rect: tuple[int, int, int, int], dx: int = 0, dy: int = 0
            ) -> tuple[int, int, int, int] | None:
        """*rect*'s size at the top left of monitor *n*'s work area (+ *dx*, *dy*), no larger than it."""
        m = self.screens.monitor(n)
        if m is None:
            return None
        work = m["work"]
        w, h = min(rect[2], work[2] - work[0] - dx), min(rect[3], work[3] - work[1] - dy)
        return (work[0] + dx, work[1] + dy, w, h)

    def _straddle(self, rect: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
        """*rect*'s size with its middle on the edge its monitor shares with the other one."""
        a, b = self.screens.monitor(self.screens.of_window(self.hwnd)), self.screens.monitor(self._other())
        if a is None or b is None:
            return None
        ra, rb = a["rect"], b["rect"]
        _x, _y, w, h = rect
        top = max(a["work"][1], b["work"][1]) + 30
        if rb[0] == ra[2] or ra[0] == rb[2]:  # (side by side)
            edge = ra[2] if rb[0] == ra[2] else ra[0]
            return (edge - w // 2, top, w, h)
        if rb[1] == ra[3] or ra[1] == rb[3]:  # (one above the other)
            edge = ra[3] if rb[1] == ra[3] else ra[1]
            return (max(a["work"][0], b["work"][0]) + 30, edge - h // 2, w, h)
        return None

    # the steps
    def may_begin(self, rested: bool) -> bool:
        see = self.see
        hover = getattr(see, "hover_thread", None)
        scene_over = getattr(see, "standin", None) is not None or (hover is not None and not hover.is_alive())
        return rested and scene_over and not see.acting()

    def begin(self, name: str) -> None:
        rect = self._rect()
        rec: dict[str, Any] = {"name": name, "t": now_ms(), "before": list(rect),
                               "monitor_before": self.screens.of_window(self.hwnd)}
        facts: dict[str, Any] = {"t": rec["t"]}
        self.done_at, self.drag = None, None
        try:
            if name not in ("m0", "m3", "r6") and _u.IsZoomed(self.hwnd):  # (restored first: m4, r7, or a start
                facts["restore"] = self.steps.restore()  # maximised, `--standin-maximised`)
                rect = self._rect()
            if name == "m1":
                target = self._on(self._other(), rect, 40, 30)
                self._instant(facts, target)
            elif name == "m2":
                self._instant(facts, self._straddle(rect))
            elif name == "m3":
                self._instant(facts, self._on(self._second(), rect))
                facts["maximise"] = self.steps.maximise()
            elif name == "m4":
                self._instant(facts, self.start_rect)
            elif name == "r1":
                if self.editing:
                    facts["editor_opened"] = self._open_editor()
                x, y, w, h = rect
                self._drag(facts, rect, (x, y, round(w * 0.72), h), "right", True,
                           EDITOR_LEAD_S if facts.get("editor_opened") else 0.0)
            elif name == "r2":
                facts["editor_closed"] = self._close_editor()
                x, y, w, h = rect
                m = self.screens.monitor(self.screens.of_window(self.hwnd))
                room = (m["work"][2] - x) if m else w
                self._drag(facts, rect, (x, y, min(round(self.start_rect[2] * 1.25), room), h), "right", True)
            elif name == "r3":
                x, y, w, h = rect
                m = self.screens.monitor(self.screens.of_window(self.hwnd))
                room = (m["work"][3] - y) if m else h
                self._drag(facts, rect, (x, y, w, min(h + 140, room)), "bottom", True)
            elif name == "r4":  # (to about 1300 x 900 from r3's: no room for the panes beside a spread)
                x, y, w, h = rect
                self._drag(facts, rect, (x, y, max(800, w - 620), max(500, h - 100)), "corner", True)
            elif name == "r5":
                m = self.screens.monitor(self.screens.of_window(self.hwnd))
                if m is not None:
                    work = m["work"]
                    self._instant(facts, (work[0], work[1], (work[2] - work[0]) // 2, work[3] - work[1]))
            elif name == "r6":
                facts["maximise"] = self.steps.maximise()
                facts.update({"first_t": facts["t"], "last_t": now_ms(), "sizes": 1, "button": False})
            elif name == "r7":
                facts.setdefault("restore", None)
                facts.update({"first_t": facts["t"], "last_t": now_ms(), "sizes": 1, "button": False})
            elif name == "r8":
                x, y, w, h = rect
                self._drag(facts, rect, (x, y, w + 420, h - 120), "corner", False)
        except Exception as e:  # noqa: BLE001 - noted, the run goes on
            facts["error"] = type(e).__name__
        if self.drag is None:
            self.done_at = time.monotonic()
        rec["facts"] = facts
        self.records.append(rec)

    def _instant(self, facts: dict[str, Any], target: tuple[int, int, int, int] | None) -> None:
        if target is None:
            facts["refused"] = "no such place on these monitors"
            return
        self.steps.place(target)
        t = now_ms()
        facts.update({"to": list(target), "first_t": facts.get("first_t") or t, "last_t": t, "sizes": 1,
                      "button": False})

    def _drag(self, facts: dict[str, Any], start: tuple[int, int, int, int], end: tuple[int, int, int, int],
              edge: str, button: bool, delay: float = 0.0) -> None:
        drag = Drag(self.steps, start, end, edge, self.see, button)
        if delay:
            inner = drag.run

            def later() -> None:
                time.sleep(delay)
                inner()

            drag.run = later  # type: ignore[method-assign]
        self.drag = drag
        facts["drag"] = drag.facts
        drag.start()

    def _open_editor(self) -> bool:
        from taslation.ui import see_edit

        regions = list(self.app._page_regions()) if callable(getattr(self.app, "_page_regions", None)) else []
        if not regions:
            return False
        self.tour._quiet()
        self.tour.locked = bool(self.tour.lock(True))
        result = getattr(self.app, "last_result", None)
        original = getattr(result, "original", None)
        self.opened_on = {"size": list(original.size) if original is not None else None,
                          "box": [int(v) for v in regions[0].bbox],
                          "in_last_result": any(r is regions[0] for r in getattr(result, "regions", ()) or ())}
        see_edit.open_editor(self.app, regions[0])
        self.editor_open = getattr(self.app, "_editor", None) is not None
        held = getattr(self.app, "_editor_held", None)
        self.opened_on["held"] = held is not None and held.region is regions[0]
        return self.editor_open

    def _close_editor(self) -> bool | None:
        if not self.editor_open:
            return None
        self.editor_open = False
        editor = getattr(self.app, "_editor", None)
        try:
            if editor is not None and editor.winfo_exists():
                editor.close_asked()
        finally:
            self.tour._end()
            if self.tour.locked:
                self.tour.lock(False)
                self.tour.locked = False
        return True

    def ready(self, name: str, rested: bool) -> bool:
        if self.drag is not None:
            if self.drag.is_alive():
                return False
            if self.done_at is None:
                self.done_at = time.monotonic()
        if self.done_at is None or time.monotonic() - self.done_at < STEP_REST_S or not rested:
            return False
        if name not in self._items:  # (decided once, at rest: the taskbar button's Menu where the left pane has no room)
            items = TOURS.get(name, ())
            if not items and name in R_NAMES and not self._button_toured:
                from taslation.ui import seethrough as ui

                if not ui.left_room(self.app):
                    items, self._button_toured = ("button_menu",), True
            self._items[name] = items
        items = self._items[name]
        if items and name not in self.toured:
            if not self.tour.busy():
                if self._touring == name:
                    self.toured.add(name)
                    self._touring = None
                    return True
                self._touring = name
                self.tour.start(name, items)
            self.tour.step()
            return False
        return True

    def fast(self) -> bool:
        return (self.drag is not None and self.drag.is_alive()) or (
            self.done_at is not None and time.monotonic() - self.done_at < 3.0)

    def tick(self) -> None:
        self.sampler.tk_look()
        hover = getattr(self.see, "hover_thread", None)
        if hover is not None and hover.is_alive() and self.hover_span[0] is None:
            self.hover_span[0] = now_ms()
        if self.hover_span[0] is not None and self.hover_span[1] is None and hover is not None \
                and not hover.is_alive():
            self.hover_span[1] = now_ms()

    def close(self) -> None:
        self._close_editor()
        if self.tour.busy() or self.tour._undo:
            self.tour.queue = []
            self.tour._end()
        if self.tour.locked:
            self.tour.lock(False)
            self.tour.locked = False

    # the report
    def report(self, notes: Any, top: int, end_ms: float) -> dict[str, Any]:
        rows = self.sampler.rows
        over = self.see.over() if self.see is not None else None
        hides = [(n["t"] * 1000 + self.see.delta_ms, f"{n['side']}:{n.get('why')}")
                 for n in (list(over.notes) if over is not None else []) if n["ev"] == "pane_hide"]
        out: dict[str, Any] = {"screens": self.screens.facts(), "taskbar": taskbar_setting(),
                               "start": {"rect": list(self.start_rect), "monitor": self.start_monitor},
                               "looks": len(rows)}
        places: list[dict[str, Any]] = []
        spans = [(r["name"], r["t"], self.records[i + 1]["t"] if i + 1 < len(self.records) else end_ms, r)
                 for i, r in enumerate(self.records)] or [("run", rows[0]["t"] if rows else 0.0, end_ms, None)]
        for name, t0, t1, rec in spans:
            block = place_block(segment_rows(rows, t0, t1), self.screens)
            block["segment"] = name
            if rec is not None:
                block["step"] = {k: v for k, v in rec["facts"].items() if k not in ("drag",)}
                block["monitor_before"] = rec["monitor_before"]
                stale = [r["t"] for r in segment_rows(rows, t0, t1) if r.get("overlay") is not None and any(_stale(r))]
                block["stale_ms_after_the_step"] = _ms(max(stale), rec["facts"].get("last_t") or t0) if stale else None
            ages = _stale_looks(rows, t0, t1)
            block["stale_longest_ms"] = round(max(a for _t, _p, _z, a, _on in ages)) if ages else None
            block["stale_with_patches_looks"] = sum(1 for *_x, on in ages if on)
            block["tour"] = [r for r in self.tour.rows if r.get("segment") == name]
            block["overlay_pane_hides"] = dict(Counter(w for t, w in hides if t0 <= t < t1))
            if rec is not None and name in R_NAMES:
                facts = dict(rec["facts"].get("drag") or rec["facts"])
                block["resize"] = drag_block(rows, facts, notes, t1, self.sampler.page_rects, top)
                if name == "r1" and self.opened_on is not None and block["resize"].get("editor") is not None:
                    block["resize"]["editor"]["opened_on"] = self.opened_on
                    block["resize"]["editor"]["look_errors"] = dict(self.sampler.tk_errors)
            places.append(block)
        out["places"] = places
        h0, h1 = self.hover_span
        at = [r for r in rows if h0 is not None and h0 <= r["t"] <= (h1 or end_ms)]
        hover = getattr(self.see, "hover", None) or {}
        out["hover"] = {"from_t": h0, "ms": _ms(h1, h0), "monitors": dict(Counter(str(r["monitor"]) for r in at)),
                        "rounds": len(hover.get("rounds") or []), "gone_ms": hover.get("gone_ms"),
                        "back_ms": hover.get("back_ms"), "others_stayed": hover.get("others_stayed"),
                        "bubble_kept": hover.get("bubble_kept"),
                        "edge_ok": None if not hover.get("edge") else [
                            s["patch_shown"] for s in hover["edge"]["steps"]] == hover["edge"]["expected_shown"],
                        "front_same": hover.get("front_same"), "error": hover.get("error")}
        out["region_fit"] = region_fit(self.sampler.results, self.sampler.page_rects, top)
        out["handed_over_refused"] = dict(self.tour.handed)
        return out


# ---------------------------------------------------------------------------------------------------- the report
def _ms(t: float | None, since: float | None) -> int | None:
    return None if t is None or since is None else round(t - since)


def _stale(row: dict[str, Any]) -> tuple[bool, bool]:
    """(drawn at another place, drawn at another scale) of a look: the lettering's window on show where the stand-in's
    client area is not, or a set of another frame size."""
    over, client, shown = row.get("overlay"), row.get("client"), row.get("shown")
    if over is None or client is None:
        return False, False
    place = abs(over[0] - client[0]) > 0 or abs(over[1] - client[1]) > 0
    size = (over[2] - over[0], over[3] - over[1]) != (client[2] - client[0], client[3] - client[1])
    if shown is not None and shown.get("set_size") is not None:
        size = size or tuple(shown["set_size"]) != (client[2] - client[0], client[3] - client[1])
    return place, size


def carry_facts(old: Any, new: Any, region: Any) -> dict[str, Any]:
    """(the Tk thread) Why the open editor's region would or would not be found again on the page on show
    (`translator.carried_region`'s tests, numbers only): the two pages' frame sizes, their page units and the most
    fingerprint bits apart, the region's unit, the regions there of its kind and translation and how far the best
    one's box overlaps the region's place carried there."""
    from taslation.fingerprint import hamming
    from taslation.ui import translator as tr

    out: dict[str, Any] = {"sizes": [list(getattr(old.original, "size", ())), list(getattr(new.original, "size", ()))]}
    pa, pb = list(old.fingerprints or ()), list(new.fingerprints or ())
    out["prints"] = [len(pa), len(pb)]
    try:
        out["bits_apart_most"] = max((hamming(p, q) for p, q in zip(pa, pb)), default=None)
    except (TypeError, ValueError):
        out["bits_apart_most"] = "?"
    ua, ub = list(getattr(old, "units", ()) or ()), list(getattr(new, "units", ()) or ())
    out["units"] = [len(ua), len(ub)]
    unit = int(getattr(region, "unit", 0) or 0)
    out["unit"] = unit
    out["regions"] = [len(tr.editor_regions(old)), len(tr.editor_regions(new))]
    if ua and ub and len(ua) == len(ub) and 0 <= unit < len(ua):
        there = ub[unit].denormalize(ua[unit].normalize(tuple(region.bbox)))
        alike = [r for r in tr.editor_regions(new) if int(getattr(r, "unit", 0) or 0) == unit and r.kind == region.kind
                 and (r.translated_text or "") == (region.translated_text or "")]
        out["alike"] = len(alike)
        out["best_overlap"] = round(max((tr._overlap(there, tuple(r.bbox)) for r in alike), default=0.0), 3)
        out["unit_boxes"] = [list(ua[unit].box), list(ub[unit].box)]
    out["carried"] = tr.carried_region(old, new, region, 36) is not None
    return out


def _stale_looks(rows: list[dict[str, Any]], t0: float, t1: float) -> list[tuple[float, bool, bool, float, bool]]:
    """Each look from *t0* to *t1* whose lettering's window was stale (`_stale`): (its time, at another place, at
    another scale, ms since the first look that saw the client at its place and size - the change came up to a look's
    time before that -, patches on show: False for the editing ground alone, which draws nothing one sees)."""
    out: list[tuple[float, bool, bool, float, bool]] = []
    since, last = 0.0, None
    for r in rows:
        client = tuple(r.get("client") or ())
        if client != last:
            since, last = r["t"], client
        if not t0 <= r["t"] < t1 or r.get("overlay") is None:
            continue
        place, scale = _stale(r)
        if place or scale:
            out.append((r["t"], place, scale, r["t"] - since, bool((r.get("shown") or {}).get("n"))))
    return out


def carry(box: tuple[int, ...], old: tuple[int, ...], new: tuple[int, ...], top: int) -> tuple[int, int, int, int]:
    """*box* (frame pixels) of a page the stand-in drew at *old* (its canvas's pixels) where the same page drawn at
    *new* has it; *top*: the rows above the canvas in the frame."""
    w0, h0 = max(1, old[2] - old[0]), max(1, old[3] - old[1])
    w1, h1 = new[2] - new[0], new[3] - new[1]

    def x(v: int) -> int:
        return round(new[0] + (v - old[0]) / w0 * w1)

    def y(v: int) -> int:
        return round(new[1] + top + (v - old[1] - top) / h0 * h1)

    return x(box[0]), y(box[1]), x(box[2]), y(box[3])


def _meets(a: Any, b: Any) -> bool:
    return a is not None and b is not None and a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def editor_block(rows: list[dict[str, Any]], first: float, release: float, t_end: float,
                 page_rects: dict[Any, Any] | None = None, top: int = 0) -> dict[str, Any] | None:
    """The region editor open over a window step (r1 while editing), None when none was: how far it moved from the
    last look before the step's first size to the look at the step's new size (the first after the release whose
    editor's page is of the client's size - its page taken over by the page on show, ``taken_over`` -; else the
    step's last look), the monitors it lay on and the viewer's; its region there - the box of the editor's page
    carried to the page as the stand-in drew it at the client's size (`carry`, *page_rects*: `Sampler.page_rects`;
    *top*: the rows above its canvas) -, whether that lies in the viewer and whether the editor lies over it; the
    region's box as the editor has it at the client's place, which is what the window goes by for the editor's
    region (``box_as_kept_in_viewer``: an old page's box at the new size may run past the viewer); and how its page
    and box went (``changes``, ms from the step's first size)."""
    edited = [r for r in rows if first <= r["t"] < t_end and r.get("editor")]
    if not edited:
        return None
    before = next((r for r in reversed(rows) if r["t"] < first and r.get("editor")), None)

    def taken(r: dict[str, Any]) -> bool:  # (the editor's page one of the client's size: its page taken over)
        page, c = r.get("editor_page"), r["client"]
        return bool(page) and tuple(page[0]) == (c[2] - c[0], c[3] - c[1])

    end = next((r for r in edited if r["t"] > release and taken(r)), edited[-1])
    page = end.get("editor_page")
    screen = tuple(page[1]) if page and page[1] else None
    out: dict[str, Any] = {
        "looks": len(edited),
        "moved_px": None if before is None or before["editor"] is None or end["editor"] is None else
        max(abs(a - b) for a, b in zip(before["editor"], end["editor"])),
        "editor_monitors": end.get("editor_monitors"), "viewer_monitor": end.get("monitor"),
        "measured_ms_after_release": _ms(end["t"], release),
        "taken_over": before is not None and before.get("editor_page") != end.get("editor_page"),
        "carry_facts": end.get("editor_carry"), "box": end.get("editor_box"),
        "page": None if not page else [list(page[0]), list(page[1]) if page[1] else None],
        "box_as_kept_in_viewer": inside(end.get("editor_region"), end["client"])}
    box, c = end.get("editor_box"), end["client"]
    now = None
    if box is not None and page and screen is not None and page_rects:
        size, size_now = tuple(page[0]), (c[2] - c[0], c[3] - c[1])
        old = page_rects.get((int(size[0]), int(size[1]), int(screen[0]), bool(screen[1])))
        new = page_rects.get((int(size_now[0]), int(size_now[1]), int(screen[0]), bool(screen[1])))
        if old is not None and new is not None:
            b = carry(box, old, new, top)
            now = (c[0] + b[0], c[1] + b[1], c[0] + b[2], c[1] + b[3])
    changes, last = [], None  # (how the editor's page and box went: ms from the step's first size)
    for r in rows:
        if r["t"] >= t_end or not r.get("editor"):
            continue
        state = (r.get("editor_page"), r.get("editor_box"))
        if state != last and len(changes) < 20:
            changes.append([round(r["t"] - first), list(state[0][0]) if state[0] else None,
                            list(state[1]) if state[1] else None])
            last = state
    out["changes"] = changes
    out["region_now"] = list(now) if now is not None else None
    out["region_now_in_viewer"] = inside(now, c) if now is not None else None
    out["over_its_region_now"] = _meets(end["editor"], now) if now is not None else None
    return out


def segment_rows(rows: list[dict[str, Any]], t0: float, t1: float) -> list[dict[str, Any]]:
    return [r for r in rows if t0 <= r["t"] < t1]


def place_block(rows: list[dict[str, Any]], screens: Screens) -> dict[str, Any]:
    """What the looks of one place say: where the stand-in was, how the lettering lay on it, the panes."""
    if not rows:
        return {"looks": 0}
    last = rows[-1]
    shown = [r for r in rows if r.get("overlay") is not None]
    off = [(r["overlay"][0] - r["client"][0], r["overlay"][1] - r["client"][1]) for r in shown]
    stale = [_stale(r) for r in shown]
    panes: dict[str, Any] = {}
    for side in ("left", "right"):
        pairs = [(r["panes"][side], r) for r in rows if r.get("panes")]
        looks = [p for p, _r in pairs]
        on = [p for p in looks if p["box"] is not None]
        panes[side] = {"shown_looks": len(on), "hidden_looks": len(looks) - len(on),
                       "inside_viewer": sum(1 for p, r in pairs
                                            if p["box"] is not None and inside(p["box"], r["client"])),
                       "monitors": dict(Counter(",".join(str(n) for n in p["monitors"]) for p in on)),
                       "why_hidden": dict(Counter(p["why"] or "?" for p in looks if p["box"] is None))}
    return {"looks": len(rows), "monitor": last["monitor"], "met": last["met"], "zoomed": last["zoomed"],
            "client": list(last["client"]),
            "lettering_shown_looks": len(shown),
            "lettering_offset_px": dict(Counter(f"{dx},{dy}" for dx, dy in off)),
            "stale_place_looks": sum(1 for p, _s in stale if p), "stale_scale_looks": sum(1 for _p, z in stale if z),
            "panes": panes,
            "scales": {"see_dpi": dict(Counter(str(r.get("see_dpi")) for r in rows)),
                       "dialog_dpi": dict(Counter(str(r.get("dialog_dpi")) for r in rows)),
                       "overlay_dpi": dict(Counter(str(r.get("over_dpi")) for r in rows))},
            "root": last.get("root"),
            "monitor_dpi": (screens.monitor(last["monitor"]) or {}).get("dpi")}


def drag_block(rows: list[dict[str, Any]], facts: dict[str, Any], notes: Any, t_end: float,
               page_rects: dict[Any, Any] | None = None, top: int = 0) -> dict[str, Any]:
    """One window step that changed the size (a drag, or a size given without the button): from its first size to
    the end of its segment *t_end* - the lettering drawn at a stale place or scale (how long after the look that saw
    the client so, with patches on show or the editing ground alone), the patches hidden, back at the new size (patches
    of a set of that size on show, its page done: of a final set) and the ms; the panes; the jobs started while the button was down and on the sizes between; an open region editor
    (`editor_block`: *results*, *page_rects*, *top* as `region_fit` has them)."""
    first = facts.get("first_t") or facts.get("t")
    release = facts.get("release_t") or facts.get("last_t") or first
    if first is None:
        return {}
    during = [r for r in rows if first <= r["t"] <= (release or first)]
    after = [r for r in rows if (release or first) < r["t"] < t_end]
    stale = [(t, p, z) for t, p, z, _age, _on in _stale_looks(rows, first, t_end)]
    ages = [(age, on) for _t, _p, _z, age, on in _stale_looks(rows, first, t_end)]
    end_size = None
    if after:
        c = after[-1]["client"]
        end_size = (c[2] - c[0], c[3] - c[1])
    # (within the step: a window maximised at once may show the new size's ground at the first look, never hidden)
    first_hidden = next((r["t"] for r in rows if first <= r["t"] < t_end and r.get("overlay") is None), None)
    def lettered(r: dict[str, Any]) -> bool:  # (patches of a set of the new size: not the editing ground alone)
        shown = r.get("shown") or {}
        return bool(r.get("overlay") is not None and shown and shown.get("n") and shown.get("set_size") is not None
                    and tuple(shown["set_size"]) == end_size)

    back = next((r["t"] for r in after if lettered(r)), None)
    final_back = next((r["t"] for r in after if lettered(r) and r["shown"].get("final")), None)
    panes: dict[str, Any] = {}
    for side in ("left", "right"):
        on_during = [r for r in during if r.get("panes") and r["panes"][side]["box"] is not None]
        outside = [r for r in rows if first <= r["t"] < t_end and r.get("panes")
                   and r["panes"][side]["box"] is not None and not inside(r["panes"][side]["box"], r["client"])]
        hidden_at = next((r["t"] for r in rows if first <= r["t"] < t_end and r.get("panes")
                          and r["panes"][side]["box"] is None), None)
        back_at = next((r["t"] for r in after if r.get("panes") and r["panes"][side]["box"] is not None
                        and inside(r["panes"][side]["box"], r["client"])), None)
        last = after[-1]["panes"][side] if after and after[-1].get("panes") else None
        panes[side] = {"looks_shown_during": len(on_during), "looks_during": len(during),
                       "outside_the_viewer_looks": len(outside),
                       "hidden_ms_after_first_size": _ms(hidden_at, first),
                       "back_ms_after_release": _ms(back_at, release),
                       "at_end": None if last is None else ("shown" if last["box"] is not None else
                                                           f"hidden: {last['why'] or '?'}")}
    with notes.lock:
        jobs = [dict(j) for j in notes.jobs if j["started"] and first - 50 <= j["t"] < t_end]
        margins = [dict(m) for m in notes.margins if first <= m["t"] < t_end]
        lookups = [dict(k) for k in notes.lookups if first <= k["t"] < t_end]
    pressed = [j for j in jobs if facts.get("press_t") and facts["press_t"] <= j["t"] <= (release or 0)]
    between = [j for j in jobs if end_size is not None and j.get("size") and tuple(j["size"]) != end_size]
    first_job = next((j for j in jobs if (release or 0) <= j["t"] and j.get("size")
                      and tuple(j["size"]) == end_size), None)
    looked = [k for k in lookups if first_job is not None and k.get("job") == first_job["id"]]
    marks = [r for r in rows if first <= r["t"] < t_end and r.get("marks") and r.get("overlay") is not None]
    stale_marks = [r for r in marks if r["marks"].get("set_size") is not None
                   and tuple(r["marks"]["set_size"]) != (r["client"][2] - r["client"][0],
                                                         r["client"][3] - r["client"][1])]
    editor = editor_block(rows, first, release or first, t_end, page_rects or {}, top)
    timeline = _timeline(rows, jobs, notes, first, t_end)
    seen_sizes = {tuple(m["size"]) for m in margins if m.get("size") and m["t"] <= (release or first)}
    at_new = next((m["t"] for m in margins if end_size is not None and m.get("size")
                   and tuple(m["size"]) == end_size), None)
    own_new = next((m["t"] for m in margins if end_size is not None and m.get("size")
                    and tuple(m["size"]) == end_size and m["read"] == m["own"]), None)
    return {"edge": facts.get("edge"), "button": facts.get("button"), "sizes_given": facts.get("sizes"),
            "drag_ms": _ms(facts.get("last_t"), first), "end_size": list(end_size) if end_size else None,
            "stale_place_looks": sum(1 for _t, p, _z in stale if p),
            "stale_scale_looks": sum(1 for _t, _p, z in stale if z),
            "stale_ms": _ms(max((t for t, p, z in stale if p or z), default=None), first),
            "stale_longest_ms": round(max((a for a, _on in ages), default=0)) if ages else None,
            "stale_with_patches_looks": sum(1 for _a, on in ages if on),
            "lettering_hidden_ms_after_first_size": _ms(first_hidden, first),
            "lettering_back_at_new_size_ms_after_release": _ms(back, release),
            "page_done_at_new_size_ms_after_release": _ms(final_back, release),
            "panes": panes,
            "jobs_started_while_pressed": len(pressed), "requests_while_pressed": sum(j["requests"] for j in pressed),
            "jobs_on_sizes_between": len(between), "requests_on_sizes_between": sum(j["requests"] for j in between),
            "first_job_after": None if first_job is None else {
                "ms_after_release": _ms(first_job["t"], release), "requests": first_job["requests"],
                "result_from": first_job.get("result_from"),
                "cache_hits": sum(1 for k in looked if k.get("hit") is not None),
                "cache_misses": sum(1 for k in looked if k.get("hit") is None)},
            # the capture area: the frame sizes the window looked at while the size changed, and from the release to
            # the frame of the new size looked at, and read by its own area (found again for that size)
            "frame_sizes_looked_at_during": len(seen_sizes),
            "new_size_looked_at_ms_after_release": _ms(at_new, release),
            "own_area_at_new_size_ms_after_release": _ms(own_new, release),
            "marks_looks": len(marks), "marks_of_another_size_looks": len(stale_marks), "editor": editor,
            "left_room_at_end": after[-1].get("left_room") if after else None,
            "front_before": facts.get("front_before"), "front_after": facts.get("front_after"),
            "timeline": timeline}


TIMELINE_MOST = 80  # (`_timeline`) entries kept at the most


def _timeline(rows: list[dict[str, Any]], jobs: list[dict[str, Any]], notes: Any, first: float, t_end: float
              ) -> list[str]:
    """What changed from the step's first size to *t_end*, in ms from that size: the client's size (as it settles),
    the lettering's window shown or hidden and the set it shows (its frame size, final or not), the page jobs started
    (their frame size and requests) and what the window showed (`Notes.displays`: the kind, the screen, the bubbles
    lettered). Numbers only."""
    out: list[tuple[float, str]] = []
    last: tuple[Any, ...] | None = None
    for r in rows:
        if not first <= r["t"] < t_end:
            continue
        c = r["client"]
        shown = r.get("shown") or {}
        state = ((c[2] - c[0], c[3] - c[1]), r.get("overlay") is not None,
                 tuple(shown.get("set_size") or ()) if r.get("overlay") is not None else (),
                 shown.get("final") if r.get("overlay") is not None else None)
        if state != last:
            size, on, set_size, final = state
            out.append((r["t"], f"client {size[0]}x{size[1]}: " + (
                f"lettering of a set {set_size[0]}x{set_size[1]}{' final' if final else ''}" if on and set_size
                else "lettering shown" if on else "lettering hidden")))
            last = state
    for j in jobs:
        size = j.get("size") or (0, 0)
        out.append((j["t"], f"job {j['id']} on {size[0]}x{size[1]}, {j.get('requests', 0)} requests"))
    with notes.lock:
        displays = [dict(d) for d in getattr(notes, "displays", []) if first <= d["t"] < t_end]
    for d in displays:
        out.append((d["t"], f"window shows {d.get('kind')} page {d.get('page')}"
                            f"{' spread' if d.get('spread') else ''} lettered {d.get('lettered')}"))
    out.sort(key=lambda e: e[0])
    return [f"{round(t - first)} ms {text}" for t, text in out[:TIMELINE_MOST]]


def region_fit(results: list[dict[str, Any]], page_rects: dict[tuple[int, int, int, bool], Any], top: int
               ) -> dict[str, Any]:
    """A screen's regions at one frame size against the same screen's at another (the page's results as the window
    had them, `Sampler.results`): each box put on the page's rectangle as the stand-in drew it at that size (0 to 1
    across and down; *top*: the rows above the stand-in's canvas in the frame), the nearest box of the other size
    found, and how far apart they lie in px of the later size. A region stored at one size and shown at another lies
    within a px or two of where it was; a page read afresh at the new size may find its boxes a little otherwise."""
    worst: list[float] = []
    pairs, unequal, no_rect = 0, 0, 0

    def rect_of(r: dict[str, Any]) -> Any:
        w, h = r["size"]
        return page_rects.get((int(w), int(h), int(r["screen"][0]), bool(r["screen"][1])))

    def norm(box: tuple[int, ...], p: tuple[int, ...]) -> tuple[float, ...]:
        w, h = max(1, p[2] - p[0]), max(1, p[3] - p[1])
        y0 = p[1] + top
        return ((box[0] - p[0]) / w, (box[1] - y0) / h, (box[2] - p[0]) / w, (box[3] - y0) / h)

    rows = [r for r in results if r.get("screen") and r["boxes"]]
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if a["size"] == b["size"] or a["screen"] != b["screen"]:
                continue
            if len(a["boxes"]) != len(b["boxes"]):
                unequal += 1
                continue
            pa, pb = rect_of(a), rect_of(b)
            if pa is None or pb is None:
                no_rect += 1
                continue
            na, nb = [norm(x, pa) for x in a["boxes"]], [norm(x, pb) for x in b["boxes"]]
            scale = (pb[2] - pb[0], pb[3] - pb[1])
            gaps = []
            for box in na:
                best = min(nb, key=lambda o, box=box: sum(abs(u - v) for u, v in zip(box, o)))
                gaps.append(max(abs(box[0] - best[0]) * scale[0], abs(box[2] - best[2]) * scale[0],
                                abs(box[1] - best[1]) * scale[1], abs(box[3] - best[3]) * scale[1]))
            pairs += 1
            worst.append(max(gaps))
    return {"results": len(results), "results_with_their_screen": len(rows),
            "sizes": sorted({f"{r['size'][0]}x{r['size'][1]}" for r in rows}), "page_rects": len(page_rects),
            "pairs_of_sizes": pairs, "worst_px": spread(worst), "pairs_with_other_region_counts": unequal,
            "pairs_without_the_page_rect": no_rect}
