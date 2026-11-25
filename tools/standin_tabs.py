"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: a second tab of the stand-in's browser window in an end-to-end run
(`standin_e2e.py`: the scenarios tab0-tab6, by their names only; `--standin-start-tab`), and what TASlation did while
the other tab showed - numbers and flags only, never a title, a name or a line.

The tabs are the stand-in page's own (standin.html's "the tabs": the window's title is the active tab's, its frames
show that tab's page - a plain page with a neutral title, or one of made-up Japanese lines with a made-up Japanese
title -, the band stays), switched by its script: no key, no click. The book's tab moved out into a window of its own
(``z``) is a second window of the same browser program, opened at the start right behind the first, covered by it
(`standin_viewer.StandinBrowser.open_held`: opened later, or restored from minimised, a browser's window took the
foreground), taken by the guards as the stand-in's from then on; at the ``z`` its page is told to go on (the control
file's *out*: the screen the first window showed, the step after the ``z``) and the window brought above the first
without activation (`show_held`).

* `Sampler`: a thread that looks every SAMPLE_S at the see-through window: whether it shows anything and how many
  patches, the window whose client area it lies on (the first stand-in window, the second, none), whether it takes the
  mouse (editing), the side panes; and what TASlation follows (`selected`).
* `TabRun`: the stand-in's tab events taken from the driver (`event`), the spells away from the book's tab (from the
  other tab drawn to the book's page drawn again, or the end), the counts of what was captured, read, asked, looked up
  in the cache, learnt and said in each, from the notes `standin_e2e.Notes` keeps; the Tk thread's look at each tick
  (`tick`: the right pane's line, the book's name and the viewer remembered, compared, never kept); `report`."""

from __future__ import annotations

import ctypes
import hashlib
import threading
import time
from collections import Counter
from ctypes import wintypes
from typing import Any, Callable

SAMPLE_S = 0.05
SPACING_PX = 40  # the book's own window (``z``): so far right and down from the first, as a tab dropped beside it
RESUME_LIMIT_MS = 20000  # a spell's resumption looked for so long after the book's tab was back

_u = ctypes.WinDLL("user32", use_last_error=True)
_u.IsWindowVisible.argtypes = [wintypes.HWND]
_u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
GWL_EXSTYLE, WS_EX_TRANSPARENT = -20, 0x20


def now_ms() -> float:
    return time.time() * 1000.0


def _digest(text: str) -> str:
    """A short digest of *text*, for telling two values apart without keeping either (memory only)."""
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:12]


def _client(hwnd: int) -> tuple[int, int, int, int] | None:
    from taslation.capture import windows

    try:
        x, y, w, h = windows._client_box(hwnd)
    except Exception:  # noqa: BLE001 - gone
        return None
    return (x, y, x + w, y + h)


def _inside(point: Any, box: Any) -> bool:
    return point is not None and box is not None and box[0] <= point[0] < box[2] and box[1] <= point[1] < box[3]


def _lies_on(origin: Any, boxes: list[Any]) -> int:
    """Which of the client areas *boxes* (1 the first stand-in window, 2 the book's own) the lettering whose screen
    origin is *origin* lies on: the one whose top left it is (the lettering is laid from the client area's origin), else
    the last one it lies inside (the book's own window lies within the first one's place, above it); 0 for none."""
    for k, box in enumerate(boxes):
        if box is not None and abs(box[0] - origin[0]) <= 2 and abs(box[1] - origin[1]) <= 2:
            return k + 1
    return next((k + 1 for k in range(len(boxes) - 1, -1, -1) if _inside(origin, boxes[k])), 0)


class Sampler(threading.Thread):
    """Every SAMPLE_S the see-through window and the windows it may lie on (*windows*(): the stand-in's first window,
    then the book's own once it came), kept in `rows`."""

    def __init__(self, app: Any, windows: Callable[[], list[int]]):
        super().__init__(name="standin-tabs", daemon=True)
        self.app, self.windows = app, windows
        self.rows: list[dict[str, Any]] = []
        self.stop = threading.Event()

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                self.look()
            except Exception:  # noqa: BLE001 - a look that failed is a look less
                pass
            self.stop.wait(SAMPLE_S)

    def look(self) -> None:
        app, t = self.app, now_ms()
        over = getattr(app, "_see_through", None)
        wins = list(self.windows())
        selected = getattr(getattr(app, "selected", None), "hwnd", None)
        row: dict[str, Any] = {"t": t, "follows": wins.index(selected) + 1 if selected in wins else 0}
        if over is not None:
            shown = over.shown()
            origin = tuple(shown[2]) if shown is not None else None
            on = _lies_on(origin, [_client(w) for w in wins]) if origin else 0
            hwnd = int(getattr(over, "hwnd", 0) or 0)
            style = int(_u.GetWindowLongW(hwnd, GWL_EXSTYLE)) & 0xFFFFFFFF if hwnd else WS_EX_TRANSPARENT
            row.update({"showing": shown is not None, "patches": len(shown[1]) if shown is not None else 0,
                        "on": on, "ground": bool(getattr(over, "_shown", None) is not None
                                                 and len(over._shown) > 4),
                        "mouse": bool(hwnd and _u.IsWindowVisible(hwnd) and not style & WS_EX_TRANSPARENT),
                        "left": over.pane_shown("left") is not None, "right": over.pane_shown("right") is not None,
                        "away": bool(getattr(over, "_away", False))})
        self.rows.append(row)


class TabRun:
    """The tab scenarios' side of a run (`standin_e2e.Director` hands it the stand-in's tab events and calls `tick`
    on the Tk thread)."""

    def __init__(self, app: Any, browser: Any, notes: Any, held: int, release_out: Callable[[int, int], None],
                 place: Callable[[int, tuple[int, int, int, int]], None], rect: tuple[int, int, int, int],
                 away_line: Callable[[Any], bool]):
        self.app, self.browser, self.notes = app, browser, notes
        self.held, self.release_out, self.place, self.rect = int(held or 0), release_out, place, rect
        self.away_line = away_line  # (whether the right pane says the window shows another tab: `right_pane_says`)
        self.events: list[dict[str, Any]] = []
        self.spells: list[dict[str, Any]] = []
        self.second: int = 0  # the book's own window (``z``), once it is shown
        self.second_facts: dict[str, Any] = {}
        self._opening: threading.Thread | None = None
        self.sampler = Sampler(app, self.windows)
        self.tk_rows: list[dict[str, Any]] = []  # the Tk thread's looks, where they changed
        self.segment = ""
        self.other_titles: tuple[str, ...] = ()
        self.chosen_digest: str = ""  # (the title the window was chosen by, as a digest)

    def windows(self) -> list[int]:
        return [w for w in (int(self.browser.hwnd or 0), self.held) if w]

    def start(self) -> None:
        import standin_viewer as sv

        self.other_titles = tuple(sv.OTHER_TITLES)
        self.sampler.start()

    def close(self) -> None:
        self.sampler.stop.set()
        self.sampler.join(2.0)
        if self._opening is not None:
            self._opening.join(25.0)

    # ------------------------------------------------------------------ what the stand-in said (the Tk thread)
    def counts(self) -> dict[str, Any]:
        """What the notes hold so far, as counts (a spell's difference of two of them is what happened in it)."""
        n, app = self.notes, self.app
        with n.lock:
            out = {"captures": n.capture_n, "tab_captures": n.capture_counts.get("tab", 0),
                   "jobs": len(n.jobs), "jobs_started": sum(1 for j in n.jobs if j["started"]),
                   "requests": len(n.requests), "lookups": len(n.lookups), "drew_soft": len(n.drew_soft),
                   "status_lines": len(n.status_lines)}
        areas = getattr(app, "_page_areas", {}) or {}
        out["page_areas"] = _digest(repr(sorted((str(k), repr(v)) for k, v in areas.items())))
        out["book"] = _digest(_get(getattr(app, "book_var", None)))
        sel = getattr(app, "selected", None)
        out["selected"] = int(getattr(sel, "hwnd", 0) or 0)
        out["selected_title"] = _digest(getattr(sel, "title", "") if sel is not None else "")
        out["memory_titles"] = _memory_titles()
        return out

    def event(self, e: dict[str, Any], segment: str) -> None:
        self.segment = segment
        rec = {k: e.get(k) for k in ("t", "recv", "on", "kind", "late", "how", "lead", "to", "index", "title",
                                     "redraw", "page", "spread", "already")}
        rec["segment"] = segment
        self.events.append(rec)
        on = e.get("on")
        t = float(e.get("t") or now_ms())
        if on == "other" or on == "out":
            last = self.spells[-1] if self.spells else None
            if last is not None and last.get("back_t") is None:
                if on == "out":
                    last["kind"] = "out"  # (the "z": its other tab shown just before it said so)
                # (else the other tab said again - at the page's start, as it begins -: the same spell)
            else:
                self.spells.append({"segment": segment, "kind": "start" if segment in ("", "start") else
                                    ("out" if on == "out" else "switch"), "other": int(e.get("kind") or 0),
                                    "title_late_ms": int(e.get("late") or 0), "away_t": t, "back_t": None,
                                    "book_drawn_t": None, "before": self.counts(), "after": None})
            if on == "out":
                self._open_second(int(e.get("index") or 0), int(e.get("to") or 0))
        elif on == "book":
            spell = self.spells[-1] if self.spells else None
            if spell is not None and spell["back_t"] is None and not e.get("already"):
                spell["back_t"] = t
                spell["how"] = e.get("how")
                spell["title_lead_ms"] = int(e.get("lead") or 0)

    def drawn(self, e: dict[str, Any]) -> None:
        """A draw of the stand-in's (``ev=draw``): the book's page drawn again after the book's tab came back."""
        spell = self.spells[-1] if self.spells else None
        if spell is None or spell["book_drawn_t"] is not None:
            return
        if spell["kind"] == "out" and e.get("why") == "start":  # (the book's own window drew its first screen)
            spell["back_t"] = spell["book_drawn_t"] = float(e.get("t") or now_ms())
            spell["how"] = "own window"
            spell["after"] = self.counts()
        elif spell["back_t"] is not None and e.get("why") == "tab":
            spell["book_drawn_t"] = float(e.get("t") or now_ms())
            spell["after"] = self.counts()

    def _open_second(self, index: int, skip: int) -> None:
        """``z``: the book's own window (opened at the start, minimised) told to go on from the screen *index* and
        the step *skip*, shown without activation and placed - on a thread of this tool's (the showing waits a
        moment to see that it took no foreground)."""
        if not self.held:
            self.second_facts["failed"] = "no window of the book's own was opened at the start"
            return

        def opening() -> None:
            began = time.monotonic()
            try:
                self.release_out(index, skip)
                raised = self.browser.show_held(self.held) or {}
                self.place(self.held, self.rect)
                self.second = self.held
                self.second_facts.update({"came_ms": round((time.monotonic() - began) * 1000), "t": now_ms(),
                                          "locked": raised.get("locked"),
                                          "took_the_foreground": raised.get("took_the_foreground"),
                                          "took_it_at": raised.get("took_it_at")})
            except Exception as e:  # noqa: BLE001 - said by its type
                self.second_facts["failed"] = type(e).__name__

        self._opening = threading.Thread(target=opening, name="standin-tab-out", daemon=True)
        self._opening.start()

    def tick(self) -> None:
        """(the Tk thread, each tick) The right pane's line on another tab, the status line's kind, the book's name and
        the window followed, kept where they changed (as digests: compared, never kept); a window picked in the viewer
        chooser on trial (`ui.viewers.ViewerMixin._pick_trial`) and the right pane's lines of it ("no page": no page
        with text in the tab picked, "again": how to have the tab in front read)."""
        app = self.app
        try:
            says = bool(self.away_line(app))
        except Exception:  # noqa: BLE001 - not told
            says = False
        pick = ""
        try:
            from taslation.i18n import _ as tr
            from taslation.ui import constants

            for code, line in (("no page", "PICK_NO_PAGE"), ("again", "PICK_AGAIN")):
                if hasattr(constants, line) and right_pane_says(app, tr(getattr(constants, line))):
                    pick = code
        except Exception:  # noqa: BLE001 - not told
            pick = ""
        sel = getattr(app, "selected", None)
        rec = {"t": now_ms(), "away_line": says, "away": bool(getattr(app, "_tab_away", False)),
               "trial": getattr(app, "_pick_trial", None) is not None, "pick_line": pick,
               "status": str(getattr(app, "_status_key", "") or "")[:40],
               "book": _digest(_get(getattr(app, "book_var", None))),
               "follows": self.windows().index(sel.hwnd) + 1 if sel is not None and sel.hwnd in self.windows() else 0,
               "title": _digest(getattr(sel, "title", "") if sel is not None else ""),
               "other_title": bool(sel is not None and getattr(sel, "title", "") in self.other_titles)}
        last = self.tk_rows[-1] if self.tk_rows else None
        if last is None or any(last[k] != rec[k] for k in rec if k != "t"):
            self.tk_rows.append(rec)

    # ------------------------------------------------------------------ the report
    def report(self, ended: float) -> dict[str, Any]:
        rows, jobs = list(self.sampler.rows), list(self.notes.jobs)
        end_counts = self.counts()
        out_spells = []
        for k, s in enumerate(self.spells):
            back = s["back_t"] if s["back_t"] is not None else ended
            nxt = self.spells[k + 1]["away_t"] if k + 1 < len(self.spells) else ended
            before, after = s["before"], s["after"] or end_counts
            diff = {key: after[key] - before[key] for key in ("captures", "tab_captures", "jobs", "jobs_started",
                                                              "requests", "lookups", "drew_soft", "status_lines")}
            away_rows = [r for r in rows if s["away_t"] <= r["t"] < back]
            # (while away: from the other tab drawn until the book's tab is back)
            item: dict[str, Any] = {
                "segment": s["segment"], "kind": s["kind"], "other": s["other"], "how": s.get("how"),
                "title_late_ms": s["title_late_ms"], "title_lead_ms": s.get("title_lead_ms", 0),
                "away_ms": round(back - s["away_t"]), "while_away": diff,
                "away_jobs_by_frame": dict(Counter(j["state"] for j in jobs if s["away_t"] <= j["t"] < back)),
                "away_requests_of_jobs_on_the_other_tab": sum(
                    j.get("requests", 0) for j in jobs if j["state"] == "tab" and s["away_t"] <= j["t"] < back),
                "lettering_looks_away": sum(1 for r in away_rows if r.get("patches")),
                # (the last look with lettering over the other tab's page, in ms after its title came: the window
                # tells another tab by its title)
                "lettering_over_the_other_tab_last_ms": _last_ms(
                    [r["t"] for r in rows if r.get("patches") and s["away_t"] <= r["t"] < nxt
                     and self._other_at(r["t"], r.get("on"))], s["away_t"] + s["title_late_ms"]),
                # (and the last with the mouse taken over the first window, the other tab on show there: editing)
                "mouse_over_the_other_tab_last_ms": _last_ms(
                    [r["t"] for r in rows if r.get("mouse") and s["away_t"] <= r["t"] < nxt
                     and self._other_at(r["t"], 1) and r.get("follows") != 2], s["away_t"] + s["title_late_ms"]),
                "ground_looks_away": sum(1 for r in away_rows if r.get("ground")),
                "mouse_taken_looks_away": sum(1 for r in away_rows if r.get("mouse")),
                "looks_away": len(away_rows),
                "panes_looks_away": {"left": sum(1 for r in away_rows if r.get("left")),
                                     "right": sum(1 for r in away_rows if r.get("right"))},
                "followed_away": dict(Counter(str(r.get("follows")) for r in away_rows)),
                "page_areas_changed": after["page_areas"] != before["page_areas"],
                "book_changed": after["book"] != before["book"],
                "chosen_window_changed": after["selected"] != before["selected"],
                "chosen_title_changed": after["selected_title"] != before["selected_title"],
                "memory_titles_added": after["memory_titles"] - before["memory_titles"],
            }
            tk_away = [r for r in self.tk_rows if s["away_t"] <= r["t"] < back]
            item["right_pane_line_shown"] = any(r["away_line"] for r in tk_away) or bool(
                self._said_at(s["away_t"], "away_line"))
            item["status_lines_away"] = sorted({r["status"] for r in tk_away if r["status"]})
            if s["back_t"] is not None:
                drawn = s["book_drawn_t"] or s["back_t"]
                limit = min(nxt, drawn + RESUME_LIMIT_MS)
                target = 2 if s["kind"] == "out" else 1
                lettered = next((r["t"] for r in rows if drawn <= r["t"] < limit and r.get("patches")
                                 and r.get("on") == target), None)
                item["back_to_lettered_ms"] = None if lettered is None else round(lettered - drawn)
                item["back_to_panes_ms"] = next((round(r["t"] - drawn) for r in rows if drawn <= r["t"] < limit
                                                 and r.get("left") and r.get("right")), None)
            if s["kind"] == "out":
                follows = next((r["t"] for r in rows if r["t"] >= s["away_t"] and r.get("follows") == 2), None)
                item["followed_the_book_s_window_ms"] = None if follows is None else round(follows - s["away_t"])
                lettered2 = next((r["t"] for r in rows if r["t"] >= s["away_t"] and r.get("patches")
                                  and r.get("on") == 2), None)
                item["lettered_on_the_book_s_window_ms"] = None if lettered2 is None else round(lettered2 - s["away_t"])
                item["second_window"] = dict(self.second_facts)
            out_spells.append(item)
        tab_jobs = [j for j in jobs if j["state"] == "tab"]
        return {"spells": out_spells,
                "jobs_on_the_other_tab": {"made": len(tab_jobs), "started": sum(1 for j in tab_jobs if j["started"]),
                                          "requests": sum(j.get("requests", 0) for j in tab_jobs),
                                          "translated": sum(j.get("translated", 0) for j in tab_jobs),
                                          "stored": sum(j.get("stored", 0) or 0 for j in tab_jobs),
                                          "units_stored": sum(len(j.get("units") or ()) for j in tab_jobs)},
                "captures_of_the_other_tab": self.notes.capture_counts.get("tab", 0),
                "lettering_looks_over_the_other_tab": sum(
                    1 for r in rows if r.get("patches") and self._other_at(r["t"], r.get("on"))),
                "chosen_by_the_other_tab_s_title": any(r["other_title"] for r in self.tk_rows),
                "memory_holds_an_other_tab_title": _memory_holds(self.other_titles),
                # (a window picked in the viewer chooser: on trial until a page with lettering was read under its tab)
                "pick": {"on_trial_looks": sum(1 for r in self.tk_rows if r["trial"]),
                         "trial_ended_ms": next((round(r["t"] - self.tk_rows[0]["t"]) for k, r in
                                                 enumerate(self.tk_rows) if k and self.tk_rows[k - 1]["trial"]
                                                 and not r["trial"]), None),
                         "on_trial_at_end": bool(self.tk_rows and self.tk_rows[-1]["trial"]),
                         "lines_said": sorted({r["pick_line"] for r in self.tk_rows if r["pick_line"]})},
                "tk_rows": [{**r, "t": round(r["t"] - (self.spells[0]["away_t"] if self.spells else 0))}
                            for r in self.tk_rows][-60:],
                "events": len(self.events), "looks": len(rows)}

    def _said_at(self, t: float, key: str) -> bool:
        return any(r[key] for r in self.tk_rows if r["t"] >= t and r["t"] < t + 3000)

    def _other_at(self, t: float, on: Any) -> bool:
        """Whether the stand-in window *on* (1 the first, 2 the book's own) showed the other tab at *t*."""
        if on != 1:
            return False
        for s in self.spells:
            back = s["back_t"] if s["back_t"] is not None else float("inf")
            drawn = s["book_drawn_t"] or back
            if s["away_t"] <= t < drawn or (s["kind"] == "out" and t >= s["away_t"]):
                return True
        return False


def _last_ms(times: list[float], since: float) -> int | None:
    return round(max(times) - since) if times else None


def _get(var: Any) -> str:
    try:
        return str(var.get()) if var is not None else ""
    except Exception:  # noqa: BLE001 - (gone)
        return ""


def _memory_titles() -> int:
    try:
        from taslation import viewerparts

        return len(viewerparts.current().titles)
    except Exception:  # noqa: BLE001 - not told
        return -1


def _memory_holds(titles: tuple[str, ...]) -> bool:
    try:
        from taslation import viewerparts

        memory = viewerparts.current()
        return any(memory.chose(t) or memory.is_part(t) for t in titles)
    except Exception:  # noqa: BLE001 - not told
        return False


def right_pane_says(app: Any, text: str) -> bool:
    """Whether the right pane's changing rows, as last drawn (``_see_pane_memo``: its key holds the rows), have *text*
    (compared, never kept)."""
    memo = getattr(app, "_see_pane_memo", {}) or {}
    entry = memo.get(getattr(app, "_see_right_used", "right"))  # (`ui.seethrough._column`'s key: block, changing, ...)
    if entry is None or entry[2] is None or not isinstance(entry[0], tuple) or len(entry[0]) < 2:
        return False
    changing = entry[0][1]
    return any(getattr(row, "text", None) == text for row in (changing if isinstance(changing, tuple) else ()))
