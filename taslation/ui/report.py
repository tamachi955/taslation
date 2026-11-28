"""A report of what TASlation knows of the page on show, for a person to paste where they ask for help: Menu > Copy a
report (the whole page), Copy a report of the chosen regions and Copy a report with this region's text (editing, with
regions chosen: `menu_entries`), and the region editor's Copy a report of this region (`EditBubbleDialog`'s
*on_report*). After copying, the right pane says how many lines went to the clipboard (`COPIED`).

The text is plain, in a fence so that it pastes cleanly, in sections of ``key = value`` lines whose keys are English in
every language of the window and stay as they are (the ``*_KEYS`` below; a key may come more than once, a line for each
monitor, region, line of the foreground or kind of problem), the most important first: the reported regions in full
(a region's report: that region first), the page and a line for each of its regions, the screen and the viewer's
window, the side panes and the lettering's window, the program, the log's warnings and errors. MAX_LINES at the most.

Numbers and states only: no text of the page, no title (of the book, of the viewer's window), no name of a file of
the reader's, no pixels; every value passes `errorlog.scrub` (characters beyond ASCII as ``…``, paths as ``<path>``),
and the first line says so (`HEAD`). Only the person's own act adds the reading and the translation of the one region
reported (*with_text*: the editor's With this region's text, the Menu's Copy a report with this region's text), never
another region's, and the first line says that instead (`HEAD_WITH_TEXT`). Nothing is written to disk or sent anywhere:
the text goes to the clipboard alone (`copy_report`). Gathered when asked, from what the window keeps anyway - the
see-through window's last look (`SeeThrough.report_facts`, `why_not_shown`; `seethrough.unshown` and the per-region
history of `unshown_tick`), the page jobs' times (`jobs.job_times`), the frames' states (`seethrough.note_state`), the
translator's streams (`Pipeline.stream_log`), the log's kinds of warnings and errors (`errorlog.problems`) -, and a
few pixel counts made from the page's two pictures in memory (what the erase left of the original's dark pixels)."""

from __future__ import annotations

import platform
import time
from collections import Counter
from typing import Any, Iterable, Sequence

import numpy as np

from .. import errorlog
from ..i18n import _
from ..i18n import current as ui_language

HEAD = "TASlation report (no page text, no titles)"
HEAD_WITH_TEXT = "TASlation report (no titles; with the reading and the translation of region {n} alone)"
FENCE = "```"
MAX_LINES = 300  # lines of a report at the most: the regions' one-line summaries go first where it is longer
PROBLEMS_SHOWN = 12  # kinds of warnings and errors a report names (`errorlog.problems`), the most recent first
FOREGROUND_LINES = 20  # lines of the log of the foreground a report gives (`seethrough.foreground_tick`), the newest
JOBS_BEFORE = 3  # page jobs before the newest a report gives a line each
STREAMS_SHOWN = 2  # the translator's streams a report gives (`Pipeline.stream_log`, the newest: a page's units)
DARK_TOL = 24  # (`dark_kept`) an original's dark pixel is left as it was where the page's differs by no more
# the room a bubble's automatic lettering took beyond its own across (`TextRegion.fitted`), as the direction line
# says it
FITTED_WORDS = {"turned": "turned", "overrun": "over the outline"}

# the menu's entries, the editor's button and box, and what the right pane says after a copy (the window's words)
COPY_REPORT = "Copy a report"
COPY_CHOSEN = "Copy a report of the chosen regions"
COPY_WITH_TEXT = "Copy a report with this region's text"
COPY_REGION = "Copy a report of this region"
WITH_TEXT = "With this region's text"
COPIED = "Report copied ({n} lines)."
REPORT_TIP = ("Numbers and states of the page on show and of TASlation, for a report: no text of the page and no "
              "titles. Paste it where you ask for help.")
WITH_TEXT_TIP = "Adds this region's Japanese and its translation, and no other text."

# the keys of each section, in their order (a report's lines keep them, whatever the window's language)
PAGE_KEYS = ("key", "size", "on_show", "units", "from_cache", "regions", "kinds", "lettered", "not_shown", "job",
             "job_before", "stream", "timings", "error", "region")
REGION_KEYS = ("number", "status", "source", "kind", "direction", "box", "page_box", "text_box", "letter_box",
               "bubble", "edges", "reading", "translation", "lettering", "erase", "dark_kept", "patches", "shown",
               "history")
TEXT_KEYS = ("reading_text", "translation_text")
SCREEN_KEYS = ("monitor", "viewer", "viewer_known", "viewer_window", "viewer_client", "viewer_dpi", "viewer_state",
               "viewer_in_front", "viewer_covered", "tab", "capture_route", "frame_size", "frames_per_s", "frame_states",
               "capture_area", "page_at_rest", "steady_band", "bars")
PANES_KEYS = ("left", "right", "lettering_window", "lettering", "takes_mouse", "insert_key", "foreground",
              "foreground_line", "keys_guard", "hidden_root")
PROGRAM_KEYS = ("version", "commit", "python", "tk", "os", "torch", "gpu", "ui_language", "target_language", "mode",
                "translator", "ocr", "layout_model", "inpainting", "server", "offline_guard", "settings_changed",
                "last_error")
LOG_KEYS = ("problem",)
SECTIONS = ("region", "page", "screen", "panes", "program", "log")


# ------------------------------------------------------------------ small pieces
def _safe(value: Any) -> str:
    """*value* as a report has it: one line, through `errorlog.scrub`."""
    return " ".join(errorlog.scrub(value).split())


def _box(box: Any) -> str:
    if box is None:
        return "none"
    try:
        return ",".join(str(int(v)) for v in box)
    except (TypeError, ValueError):
        return "?"


def _yes(flag: Any) -> str:
    return "yes" if flag else "no"


def _get(do: Any, default: Any = None) -> Any:
    """What *do*() gives; *default* where it fails (a report never fails for one fact)."""
    try:
        return do()
    except Exception:  # noqa: BLE001 - that fact left out
        return default


def _ms(at: Any, since: float) -> str:
    return "-" if at is None else f"{round((float(at) - since) * 1000)} ms"


def _ago(at: Any, now: float) -> str:
    return "never" if at is None else f"{max(0.0, now - float(at)):.1f} s ago"


def _meets(a: Sequence[int], b: Sequence[int]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


class _Lines:
    """The lines of one section, each ``key = value`` with a key of its section's (`SECTIONS`' ``*_KEYS``)."""

    def __init__(self, title: str, keys: tuple[str, ...]):
        self.title, self.keys = title, keys
        self.lines: list[str] = [f"[{title}]"]

    def add(self, key: str, value: Any, safe: bool = True) -> None:
        if key not in self.keys:
            raise KeyError(key)
        self.lines.append(f"{key} = {_safe(value) if safe else value}")


# ------------------------------------------------------------------ the page and its regions
def _page_box(app: Any, result: Any) -> Any:
    """The page's box in the frame: the one at rest of the frame's size, else the capture area's."""
    rest = getattr(app, "_see_rest_box", None)
    size = getattr(app, "_see_rest_size", None)
    if rest is not None and (size is None or tuple(size) == tuple(result.original.size)):
        return tuple(int(v) for v in rest)
    return (0, 0, *result.original.size)


def _numbers(app: Any, result: Any) -> tuple[dict[int, int], dict[int, int], int]:
    """(region id -> its plate's number on the page, region id -> its number in the editor, the editor's count)."""
    from .translator import editor_regions

    plates: dict[int, int] = {}
    if result is getattr(app, "last_result", None):
        page = _get(app._page_regions, []) if hasattr(app, "_page_regions") else []
        plates = {id(r): n for n, r in enumerate(page or [], 1)}
    shown = editor_regions(result)
    return plates, {id(r): n for n, r in enumerate(shown, 1)}, len(shown)


class _Page:
    """What the regions' lines are made from, gathered once for the page *result*."""

    def __init__(self, app: Any, result: Any):
        self.app, self.result = app, result
        self.now = time.monotonic()
        self.key = id(result.original)
        self.box = _page_box(app, result)
        self.plates, self.editor, self.editor_count = _numbers(app, result)
        settings = getattr(app, "settings", None)
        self.dark = int(getattr(settings, "dark_threshold", 140) or 140)
        self.erase_mode = str(getattr(settings, "erase_mode", "fill") or "fill")
        pipeline = getattr(app, "pipeline", None)
        eraser = getattr(pipeline, "art_eraser", None)
        self.inpaints = eraser is not None and not getattr(eraser, "failed", False)
        over = getattr(app, "_see_through", None)
        facts = _get(lambda: over.report_facts(self.key), None) if over is not None else None
        self.over = facts or {}
        self.patches: list[tuple[tuple[int, ...], float]] = list(self.over.get("patches") or [])
        from . import seethrough

        found = _get(lambda: seethrough.unshown(app, settled=False), None)
        self.unshown = found if found is not None and found.get("key") == self.key else None
        self.hidden = {i: (kind, f) for i, kind, f in (self.unshown or {}).get("not_shown", ())}
        entry = (getattr(app, "_see_unshown", None) or {}).get(self.key) or {}
        self.history: dict[int, dict[str, Any]] = entry.get("regions") or {}
        self._pixels: tuple[np.ndarray, np.ndarray] | None = None

    def pixels(self) -> tuple[np.ndarray, np.ndarray] | None:
        """The frame read and the lettered page, RGB, once (None: no lettered page of the frame's size)."""
        if self._pixels is None:
            image = getattr(self.result, "image", None)
            original = self.result.original
            if image is None or tuple(image.size) != tuple(original.size):
                return None
            self._pixels = (np.asarray(original.convert("RGB")), np.asarray(image.convert("RGB")))
        return self._pixels


def dark_kept(original: np.ndarray, lettered: np.ndarray, region: Any, dark: int = 140,
              tol: int = DARK_TOL) -> int | None:
    """How many of the original's dark pixels (mean of the channels under *dark*) inside *region*'s interior (its mask
    within its box) the lettered page shows as they were (within *tol* on every channel): the original's lettering
    the erase left (where the new lettering lies over the old in the same ink, those pixels count too). None without
    a mask of the box's size."""
    x0, y0, x1, y1 = (int(v) for v in region.bbox)
    mask = getattr(region, "mask", None)
    if not isinstance(mask, np.ndarray) or mask.shape[:2] != (y1 - y0, x1 - x0) or x1 <= x0 or y1 <= y0:
        return None
    o = original[y0:y1, x0:x1].astype(np.int16)
    q = lettered[y0:y1, x0:x1].astype(np.int16)
    if o.shape[:2] != mask.shape[:2] or q.shape != o.shape:
        return None
    inside = mask > 0
    darkness = o.mean(axis=2) < dark
    same = np.abs(o - q).max(axis=2) <= tol
    return int(np.count_nonzero(inside & darkness & same))


def _changed_box(original: np.ndarray, lettered: np.ndarray, box: Sequence[int]) -> Any:
    """Where the lettered page differs from the frame within *box* grown by half its size (the lettering may run past
    the region): that box in the frame's pixels, None for nowhere."""
    x0, y0, x1, y1 = (int(v) for v in box)
    h, w = original.shape[:2]
    gx, gy = (x1 - x0) // 2, (y1 - y0) // 2
    a0, b0, a1, b1 = max(0, x0 - gx), max(0, y0 - gy), min(w, x1 + gx), min(h, y1 + gy)
    if a1 <= a0 or b1 <= b0:
        return None
    differs = np.any(original[b0:b1, a0:a1] != lettered[b0:b1, a0:a1], axis=2)
    ys, xs = np.nonzero(differs)
    if not xs.size:
        return None
    return a0 + int(xs.min()), b0 + int(ys.min()), a0 + int(xs.max()) + 1, b0 + int(ys.max()) + 1


def _source(region: Any) -> str:
    from ..render.erase import MANUAL_KINDS

    if region.kind in MANUAL_KINDS:
        return "own (drawn by the person)"
    return "layout model" if getattr(region, "from_model", False) else "detectors"


def _erase_way(page: _Page, region: Any) -> str:
    from ..pipeline import erases

    if not erases(region):
        return "none"
    mask = getattr(region, "mask", None)
    area = int(np.count_nonzero(mask)) if isinstance(mask, np.ndarray) else 0
    if getattr(region, "inpainted", None) is not None:
        way = "inpainting"
    elif getattr(region, "toned", False):
        way = "tone fill"
    elif page.inpaints:
        way = f"paper fill ({page.erase_mode}) or inpainting not kept"
    else:
        way = f"paper fill ({page.erase_mode})"
    return f"{way}; mask {area} px"


def _shown(page: _Page, i: int, region: Any) -> tuple[str, str]:
    """(whether its lettering shows now, and why not: the kind and its numbers) at the last look."""
    from ..pipeline import erases

    if not erases(region):
        return "nothing lettered", ""
    if page.unshown is None:
        return "not known (another page on show, or no look yet)", ""
    if i not in page.hidden:
        return "yes", ""
    kind, facts = page.hidden[i]
    parts = [kind]
    if facts.get("distance") is not None:
        parts.append(f"the page's distance {facts['distance']} over the limit {facts.get('limit')}")
    if facts.get("rows"):
        parts.append("a bar over rows " + ", ".join(f"{a}-{b}" for a, b in facts["rows"]))
    if "patches" in facts:
        parts.append(f"{facts['patches']} patch(es)")
    if "set_known" in facts:
        parts.append(f"set known {_yes(facts['set_known'])}")
    return "no", "; ".join(parts)


def _region_facts(page: _Page, i: int, region: Any) -> dict[str, str]:
    """The values of a region's lines (`REGION_KEYS`), numbers and states only."""
    r, box = region, tuple(int(v) for v in region.bbox)
    p = page.box
    plate = page.plates.get(id(r))
    editor = page.editor.get(id(r))
    out: dict[str, str] = {}
    out["number"] = (f"{plate if plate is not None else 'none'} on its plate; "
                     f"{f'{editor} of {page.editor_count}' if editor is not None else 'none'} in the editor; index {i}")
    out["status"] = f"{r.status}{'; from the cache' if getattr(r, 'from_cache', False) else ''}"
    out["source"] = _source(r)
    out["kind"] = f"{r.kind}; tag {getattr(r, 'tag', '') or 'none'}"
    text_box = getattr(r, "text_box", None) or box
    tall = (text_box[3] - text_box[1]) > (text_box[2] - text_box[0])
    style = getattr(r, "style", None)
    fitted = FITTED_WORDS.get(str(getattr(r, "fitted", "") or ""), "")
    out["direction"] = (f"original {'tall' if tall else 'wide'}; lettering "
                        f"{getattr(style, 'direction', '') or 'auto'}{f' ({fitted})' if fitted else ''}; "
                        f"slant {round(float(getattr(r, 'angle', 0.0) or 0.0), 1)}")
    out["box"] = f"{_box(box)} ({box[2] - box[0]}x{box[3] - box[1]})"
    out["page_box"] = _box((box[0] - p[0], box[1] - p[1], box[2] - p[0], box[3] - p[1]))
    out["text_box"] = _box(text_box)
    out["letter_box"] = _box(getattr(r, "letter_box", None))
    mask = getattr(r, "mask", None)
    interior = int(np.count_nonzero(mask)) if isinstance(mask, np.ndarray) else 0
    if r.kind in ("bubble", "dark-bubble"):
        out["bubble"] = f"yes; its box {_box(box)}; interior {interior} px"
    else:
        out["bubble"] = f"no; area {interior} px"
    out["edges"] = (f"left {box[0] - p[0]}, top {box[1] - p[1]}, right {p[2] - box[2]}, bottom {p[3] - box[3]} "
                    f"(px to the page box {_box(p)})")
    chars = len(str(getattr(r, "source_text", "") or ""))
    if chars:
        out["reading"] = (f"{chars} chars; confidence {round(float(getattr(r, 'ocr_confidence', 1.0)), 3)}; readers "
                          f"split {_yes(getattr(r, 'ocr_split', False))}; corrected by the person "
                          f"{_yes(getattr(r, 'ocr_reading', None) is not None)}")
    else:
        out["reading"] = "none kept" + (" (from the cache)" if getattr(r, "from_cache", False) else "")
    text = str(getattr(r, "translated_text", "") or "")
    flags = ",".join(str(f) for f in (getattr(r, "flags", None) or ())) or "none"
    out["translation"] = (f"{len(text)} chars; {text.count(chr(10)) + 1 if text else 0} line(s) given; reused "
                          f"{_yes(getattr(r, 'reused', False))}; flags {flags}")
    letter_flags = ",".join(str(f) for f in (getattr(r, "letter_flags", None) or ())) or "none"
    pixels = page.pixels()
    changed = _changed_box(pixels[0], pixels[1], box) if pixels is not None else None
    formatted = style is not None and not getattr(style, "formats_nothing", True)
    out["lettering"] = (f"size {int(getattr(r, 'font_size', 0) or 0)} (cap {int(getattr(r, 'size_cap', 0) or 0)}, "
                        f"room {int(getattr(r, 'room', 0) or 0)}); could not {letter_flags}; changed {_box(changed)}; "
                        f"formatted {'by the person' if formatted else 'automatic'}")
    out["erase"] = _erase_way(page, r)
    kept = dark_kept(pixels[0], pixels[1], r, page.dark) if pixels is not None else None
    out["dark_kept"] = "-" if kept is None else str(kept)
    own = [(b, s) for b, s in page.patches if _meets(b, box)]
    if page.over.get("patches") is None:
        out["patches"] = "not known (no patches of this page in the lettering's window)"
    else:
        out["patches"] = f"{len(own)}" + "".join(f"; {_box(b)} opaque {s}" for b, s in own[:4])
    shown, why = _shown(page, i, r)
    out["shown"] = shown + (f": {why}" if why else "")
    seen = page.history.get(i)
    out["history"] = ("none" if not seen else
                      f"shown {_ago(seen.get('shown_at'), page.now)}; not shown {_ago(seen.get('unshown_at'), page.now)}"
                      + (f" ({seen.get('kind')})" if seen.get("kind") else ""))
    return out


def region_lines(page: _Page, i: int, region: Any, with_text: bool = False) -> list[str]:
    """A region's section, in full; *with_text*: its reading and translation too (the person asked for them)."""
    plate = page.plates.get(id(region))
    lines = _Lines(f"region {plate if plate is not None else '-'}", (*REGION_KEYS, *TEXT_KEYS))
    for key, value in _region_facts(page, i, region).items():
        lines.add(key, value)
    if with_text:
        reading = str(getattr(region, "source_text", "") or "")
        translation = str(getattr(region, "translated_text", "") or "")
        lines.add("reading_text", reading.replace("\n", " / ") or "(none kept)", safe=False)
        lines.add("translation_text", translation.replace("\n", " / ") or "(none)", safe=False)
    return lines.lines


def _summary(page: _Page, i: int, region: Any) -> str:
    """A region's one line on the page's section."""
    facts = _region_facts(page, i, region)
    plate = page.plates.get(id(region))
    flags = ",".join(str(f) for f in (getattr(region, "flags", None) or ())) or "none"
    return _safe(f"{plate if plate is not None else '-'} (index {i}): {region.status}; {region.kind}; box "
                 f"{facts['box']}; shown {facts['shown']}; patches {facts['patches'].split(';')[0]}; dark_kept "
                 f"{facts['dark_kept']}; size {int(getattr(region, 'font_size', 0) or 0)}; flags {flags}")


def _job_line(job: dict[str, Any]) -> str:
    t0 = float(job.get("start", 0.0))
    end = ("finished " + _ms(job["finished"], t0) if "finished" in job else
           f"cancelled {_ms(job['cancelled'], t0)} ({job.get('why') or '?'})" if "cancelled" in job else "running")
    return (f"started {_ago(t0, time.monotonic())}{' (early)' if job.get('early') else ''}; first request "
            f"{_ms(job.get('first_request'), t0)}; first lettered {_ms(job.get('first_lettered'), t0)}; {end}")


def page_lines(app: Any, result: Any, page: _Page | None, regions: Sequence[Any]) -> list[str]:
    """The page's section, a line for each of its regions at its end."""
    from . import jobs

    lines = _Lines("page", PAGE_KEYS)
    if result is None or getattr(result, "original", None) is None or page is None:
        lines.add("key", "none (no page read yet)")
    else:
        lines.add("key", f"{page.key & 0xFFFF:04x} (as the log names it)")
        lines.add("size", "x".join(str(v) for v in result.original.size))
        on_show = _get(app._result_on_show, False) if result is getattr(app, "last_result", None) else False
        fill = getattr(app, "_fill", None)
        lines.add("on_show", f"{_yes(on_show)}; a page filling in {_yes(fill is not None and fill.final is None)}")
        prints = [str(p)[:8] for p in (getattr(result, "fingerprints", None) or ())]
        count = len(prints) or len(getattr(result, "units", None) or ()) or 1
        lines.add("units", f"{count} ({'spread' if count > 1 else 'single page'})"
                  + (f"; fingerprints {', '.join(prints)}" if prints else ""))
        lines.add("from_cache", f"{int(getattr(result, 'cache_hits', 0))} unit(s); read now "
                                f"{int(getattr(result, 'cache_misses', 0))}")
        lines.add("regions", f"{len(result.regions)}: " + (", ".join(
            f"{k} {n}" for k, n in sorted(Counter(r.status for r in result.regions).items())) or "none"))
        lines.add("kinds", ", ".join(f"{k} {n}" for k, n in sorted(Counter(r.kind for r in result.regions).items()))
                  or "none")
        found = page.unshown
        if found is None:
            lines.add("lettered", "not known (another page on show, or no look yet)")
        else:
            distance = (f"; the page on show by its sign: distance {found['distance']} (limit {found['limit']})"
                        if found.get("distance") is not None else "")
            lines.add("lettered", f"{found['regions']} lettered; {found['regions'] - len(found['not_shown'])} shown"
                      + distance)
            lines.add("not_shown", ", ".join(f"{k} {n}" for k, n in sorted(found["kinds"].items())) or "none")
        times = jobs.job_times(app)
        if times:
            lines.add("job", _job_line(times[-1]))
            for job in times[-1 - JOBS_BEFORE:-1][::-1]:
                lines.add("job_before", _job_line(job))
        pipeline = getattr(app, "pipeline", None)
        for entry in list(getattr(pipeline, "stream_log", ()) or ())[-STREAMS_SHOWN:]:
            lines.add("stream", "unit {unit}: {outcome}; requests {requests} (taken back {requests_taken_back}); "
                                "lines taken back {lines_taken_back} of {runs_taken_back} run(s) ({why}); first "
                                "answer {first} ms; final lines {final_lines}".format(
                                    why=entry.get("why_taken_back") or "none", first=entry.get("first_answer_ms"),
                                    **{k: entry.get(k, "?") for k in ("unit", "outcome", "requests",
                                                                       "requests_taken_back", "lines_taken_back",
                                                                       "runs_taken_back", "final_lines")}))
        timings = getattr(result, "timings", None) or {}
        lines.add("timings", ", ".join(f"{k} {round(float(v) * 1000)} ms" for k, v in timings.items()) or "none")
        lines.add("error", getattr(result, "error", "") or "none")
        reported = {id(r) for r in regions}
        for i, r in enumerate(result.regions):
            if id(r) not in reported:
                lines.add("region", _get(lambda i=i, r=r: _summary(page, i, r), f"(index {i}: not told)"), safe=False)
    return lines.lines


# ------------------------------------------------------------------ the screen, the panes, the program, the log
def _states(app: Any) -> str:
    kept = list(getattr(app, "_see_frame_states", ()) or ())
    if not kept:
        return "none noted"
    counts = Counter(state for _t, state in kept)
    return f"last {len(kept)}: " + ", ".join(f"{k} {n}" for k, n in counts.most_common()) + f"; newest {kept[-1][1]}"


def _known(app: Any, browser: bool) -> str:
    """Whether the viewer is one known here, or a pick of it is on trial (`viewers.ViewerMixin._known_viewer`,
    `_pick_trial`), and the last verdict on its frames then (`bookpage.judge`)."""
    trial = getattr(app, "_pick_trial", None)
    if trial is not None:
        return f"no: picked, on trial (its last frame judged {trial.get('verdict') or 'nothing yet'})"
    if not browser:
        return "an app's window: never on trial"
    known = getattr(app, "_viewer_known", "")
    return {"area": "yes: an area set by hand for it", "read": "yes: a book read in it before"}.get(
        known, "no, but not on trial (chosen without a pick, or lettering read since)")


def screen_lines(app: Any, result: Any) -> list[str]:
    from ..capture import seethrough as window
    from ..capture import wgc, windows
    from . import layout

    lines = _Lines("screen", SCREEN_KEYS)
    for n, m in enumerate(_get(layout.monitors, []) or [], 1):
        lines.add("monitor", f"{n}: {_box(m['rect'])}; work {_box(m['work'])}; dpi {m.get('dpi') or '?'}"
                             f"{'; primary' if m.get('primary') else ''}")
    win = getattr(app, "selected", None)
    hwnd = int(getattr(win, "hwnd", 0) or 0)
    if not hwnd:
        lines.add("viewer", "none chosen")
    else:
        browser = windows.is_browser_class(str(getattr(win, "class_name", "") or ""))
        lines.add("viewer", f"{'a browser' if browser else 'an app'} (not named)")
        lines.add("viewer_known", _known(app, browser))
        lines.add("viewer_window", _box(_get(lambda: windows.window_rect(hwnd))))
        client = _get(lambda: windows.client_rect_on_screen(hwnd))
        lines.add("viewer_client", "none" if client is None else
                  f"{client[0]},{client[1]} {client[2]}x{client[3]}")
        lines.add("viewer_dpi", _get(lambda: window.viewer_dpi(hwnd), "?"))
        state = ("minimised" if _get(lambda: windows.window_minimised(hwnd), False) else
                 "full screen" if _get(lambda: windows.is_fullscreen(hwnd), False) else
                 "maximised" if _get(lambda: windows.window_maximised(hwnd), False) else "normal")
        lines.add("viewer_state", state)
        lines.add("viewer_in_front", _yes(_get(lambda: window.viewer_in_front(hwnd), False)))
        over = getattr(app, "_see_through", None)
        facts = (_get(lambda: over.report_facts(), {}) or {}) if over is not None else {}
        covers = facts.get("covers", [])
        lines.add("viewer_covered", f"{len(covers)} window(s) over it" + "".join(f"; {_box(c)}" for c in covers[:6]))
        tab = getattr(app, "_tab_kind", None)  # (as last seen: `ViewerMixin._tab_seen`)
        lines.add("tab", f"{tab} (as last seen)" if browser and tab else "not a browser's" if not browser else "not seen yet")
        lines.add("capture_route", _get(wgc.route, "?"))
        frame = _get(lambda: wgc.peek(hwnd))
        lines.add("frame_size", "none" if frame is None else "x".join(str(v) for v in frame.size))
        lines.add("frames_per_s", f"{facts.get('frames_per_s', '?')} (last {window.REPORT_FPS_S:g} s)")
    lines.add("frame_states", _states(app))
    image = getattr(result, "original", None) if result is not None else None
    if image is not None and callable(getattr(app, "_margins_of", None)):
        margins = _get(lambda: app._margins_of(image))
        hand = _get(app._hand_set) if getattr(app, "_manual_area", False) and callable(
            getattr(app, "_hand_set", None)) else None
        from . import seethrough

        trimmed = _get(lambda: seethrough.strip_margins(app, hand, image.size), hand) if hand is not None else None
        how = "found" if hand is None else "set by hand" if tuple(hand) == tuple(margins or ()) else \
            f"set by hand, margins {_box(hand)}, less the strip along its edge" if tuple(trimmed or ()) == tuple(
                margins or ()) else f"the page found inside the area set by hand, margins {_box(hand)}"
        lines.add("capture_area", f"margins {_box(margins)} ({how})")
    rest = getattr(app, "_see_rest_box", None)
    size = getattr(app, "_see_rest_size", None)
    lines.add("page_at_rest", "none" if rest is None else
              f"{_box(rest)} in frames of {'x'.join(str(v) for v in size) if size else '?'}")
    ground = getattr(app, "_see_ground", None)
    lines.add("steady_band", "none (no page at rest on a flat ground)" if ground is None else
              f"rows {ground[2][0]}-{ground[2][1]}; ground colour {'flat' if ground[3] is not None else 'not one colour'}; "
              f"area columns {ground[4][0]}-{ground[4][1]}")
    since = getattr(app, "_see_bars_since", None)
    strips = sorted({rows for found in (getattr(app, "_see_strips", None) or {}).values() for rows in found})
    lines.add("bars", ("none" if since is None else f"over the page for {time.monotonic() - float(since):.1f} s")
              + ("; strips along the area's edge (beyond the area, not read): rows "
                 + ", ".join(f"{a}-{b}" for a, b in strips) if strips else ""))
    return lines.lines


def _pane(app: Any, facts: dict[str, Any], side: str) -> str:
    from . import seethrough

    box = (facts.get("panes") or {}).get(side)
    if box is not None:
        return f"shown at {_box(box)} ({box[2] - box[0]}x{box[3] - box[1]})"
    if not facts:
        return "hidden: no lettering window"
    if getattr(app, "_see_ground", None) is None:
        return "hidden: no page at rest on a flat ground"
    if side == "right" and not _get(lambda: seethrough.indicators_on(app), True):
        return "hidden: Indicators off"
    if facts.get("sizing"):
        return "hidden: the viewer's window being sized"
    if facts.get("moving"):
        return "hidden: the viewer's window moved or sized a moment ago (back at rest)"
    over = (getattr(app, "_see_pane_over", None) or {}).get(side)
    if over:  # (`seethrough._clear_of_page`)
        return f"hidden: {over}"
    if not (facts.get("pane_wanted") or {}).get(side):
        return "hidden: no room beside the page, or off the monitors"
    if facts.get("covers"):
        return "hidden: a window over the viewer meets it"
    return "hidden: not drawn yet"


def panes_lines(app: Any) -> list[str]:
    lines = _Lines("panes", PANES_KEYS)
    over = getattr(app, "_see_through", None)
    facts = (_get(lambda: over.report_facts(), {}) or {}) if over is not None else {}
    lines.add("left", _pane(app, facts, "left"))
    lines.add("right", _pane(app, facts, "right") + f"; showing {getattr(app, '_see_right_used', 'right')}")
    why = (_get(lambda: over.why_not_shown(), {}) or {}) if over is not None else {}
    origin, size = facts.get("origin"), facts.get("size")
    place = "none" if origin is None or size is None else f"{origin[0]},{origin[1]} {size[0]}x{size[1]}"
    shown = facts.get("shown")
    lines.add("lettering_window", f"{place}; " + (f"on show: set {shown[0]}, {shown[1]} patch(es)" if shown else
                                                    f"hidden ({why.get('hidden') or 'nothing matched'})"))
    lines.add("lettering", "none" if not facts else
              f"{'on' if facts.get('on') else 'off'}; another tab {_yes(facts.get('away'))}; sets {facts.get('sets', 0)}")
    lines.add("takes_mouse", "none" if not facts else
              f"{_yes(facts.get('takes_mouse'))}; editing {_yes(facts.get('editing'))}; dpi {facts.get('dpi', '?')}")
    lines.add("insert_key", "held" if facts.get("key_held") else "not held")
    counts = getattr(app, "_see_foreground", None) or {}
    lines.add("foreground", ", ".join(f"{k} {n}" for k, n in sorted(counts.items())) or "no change noted")
    for line in list(getattr(app, "_see_foreground_lines", ()) or ())[-FOREGROUND_LINES:]:
        lines.add("foreground_line", line)
    guarded = getattr(app, "_see_guarded", None) or {}
    woke = (_get(lambda: dict(over.counts), {}) or {}) if over is not None else {}
    lines.add("keys_guard", f"given back {sum(guarded.values())}"
              + (f" ({', '.join(f'{k} {n}' for k, n in sorted(guarded.items()))})" if guarded else "")
              + f"; the viewer made the foreground window at a press {woke.get('woke', 0)}"
              + (f", refused {woke['woke_failed']}" if woke.get("woke_failed") else ""))
    geometry = _get(app.winfo_geometry, "?") if callable(getattr(app, "winfo_geometry", None)) else "?"
    lines.add("hidden_root", geometry)
    return lines.lines


def _models(app: Any) -> dict[str, str]:
    from . import seethrough

    settings = getattr(app, "settings", None)
    pipeline = getattr(app, "pipeline", None)
    out: dict[str, str] = {}
    translator = getattr(pipeline, "translator", None)
    model = getattr(translator, "model", "") or getattr(settings, "ollama_model", "?")
    where = getattr(app, "_compute_where", "") or "not loaded yet"
    out["translator"] = f"{model}; on {where}"
    ocr = getattr(pipeline, "ocr", None)
    if ocr is None:
        out["ocr"] = "not loaded"
    else:
        missing = list(getattr(ocr, "missing", ()) or ())
        placement = getattr(ocr, "placement", None)
        readers = "charspot alone" if missing else "charspot, nar, cpt"
        out["ocr"] = (f"{readers}; on {seethrough._readers_at(app) or 'not placed yet'} "
                      f"(placed by {getattr(placement, 'why', '?')}; {getattr(placement, 'room', None)} MiB of room)")
    layout = getattr(pipeline, "layout", None)
    out["layout_model"] = ("off" if layout is None else
                           f"on; {'failed' if getattr(layout, 'failed', False) else 'GPU' if _get(layout.uses_gpu, False) else 'processor'}")
    eraser = getattr(pipeline, "art_eraser", None)
    out["inpainting"] = ("off" if eraser is None else
                         f"{getattr(eraser, 'setting', '?')}; "
                         f"{'failed' if getattr(eraser, 'failed', False) else 'GPU' if _get(eraser.uses_gpu, False) else 'processor'}; "
                         f"regions {getattr(eraser, 'counts', {})}")
    return out


def program_lines(app: Any) -> list[str]:
    from . import see_edit

    lines = _Lines("program", PROGRAM_KEYS)
    date = _get(errorlog.release_date, "")
    lines.add("version", errorlog.program_version() + (f" (dated {date})" if date else ""))
    lines.add("commit", _get(errorlog.program_commit, "") or "not known")
    lines.add("python", f"{platform.python_version()} ({platform.architecture()[0]}, {platform.python_implementation()})")
    lines.add("tk", errorlog.tk_version())
    lines.add("os", f"{platform.system()} {platform.release()} ({platform.version()}, {platform.machine()})")
    lines.add("torch", errorlog.torch_line())
    lines.add("gpu", _get(errorlog.gpu_line, "") or "not in use by torch")
    settings = getattr(app, "settings", None)
    lines.add("ui_language", ui_language())
    lines.add("target_language", getattr(settings, "target_language", "?"))
    editing = _get(lambda: see_edit.on(app), False)
    lines.add("mode", "editing" if editing else "Reader mode" if _get(lambda: see_edit.reader_mode(app), False)
              else "not editing")
    for key, value in _models(app).items():
        lines.add(key, value)
    from ..ollama_start import own_server, setup_of

    url = getattr(settings, "ollama_url", "")
    ours = _get(lambda: own_server(url), None)
    port = _get(lambda: settings.ollama_port, None)
    setup = _get(lambda: setup_of(url, getattr(settings, "state_dir", None)), None)
    cloud = ("its own settings" if setup is None else "cloud features off" if setup.no_cloud
             else "cloud features not turned off")  # (TASlation tells only the server it starts: `ollama_start`)
    lines.add("server", f"{'started by TASlation' if ours else 'not started by TASlation'}; {cloud}; "
                        f"{_get(lambda: errorlog.ollama_line(port), 'not asked')}")
    lines.add("offline_guard", errorlog.guard_line())
    changed = errorlog.settings_lines(settings)
    lines.add("settings_changed", ", ".join(changed) if changed else "none")
    last = errorlog.last_error()
    if last is None:
        lines.add("last_error", "none in this session")
    else:
        first = (last[1].splitlines() or [""])[0]
        lines.add("last_error", f"{time.strftime('%H:%M:%S', time.localtime(last[0]))}: {first}")
    return lines.lines


def log_lines() -> list[str]:
    lines = _Lines("log", LOG_KEYS)
    found = errorlog.problems()
    now = time.time()
    for level, name, wording, n, at in found[:PROBLEMS_SHOWN]:
        lines.add("problem", f"{level} {name}: {wording} (x{n}, last {max(0.0, now - at):.0f} s ago)")
    if not found:
        lines.add("problem", "none in this session")
    elif len(found) > PROBLEMS_SHOWN:
        lines.add("problem", f"{len(found) - PROBLEMS_SHOWN} more kind(s) left out")
    return lines.lines


# ------------------------------------------------------------------ the report
def report_text(app: Any, regions: Iterable[Any] | None = None, with_text: bool = False, result: Any = None) -> str:
    """The report (see the module's notes) of the page *result* (the last translated one when None), *regions* of it
    in full and first (none: a line for each region alone), with the reading and translation of the region reported
    when *with_text* and exactly one is."""
    result = result if result is not None else getattr(app, "last_result", None)
    page = None
    if result is not None and getattr(result, "original", None) is not None:
        page = _get(lambda: _Page(app, result), None)
    chosen = [r for r in (regions or ()) if result is not None and any(r is q for q in result.regions)]
    text = with_text and len(chosen) == 1
    head = HEAD
    body: list[str] = []
    for region in chosen:
        i = next(k for k, q in enumerate(result.regions) if q is region)
        if page is not None:
            body += _get(lambda i=i, region=region: region_lines(page, i, region, text),
                         [f"[region -]", f"number = index {i} (not told)"])
        if text:
            plate = page.plates.get(id(region)) if page is not None else None
            head = HEAD_WITH_TEXT.format(n=plate if plate is not None else f"index {i}")
    body += _get(lambda: page_lines(app, result, page, chosen), ["[page]", "key = not told"])
    rest = []
    for part in (lambda: screen_lines(app, result), lambda: panes_lines(app), lambda: program_lines(app), log_lines):
        rest += _get(part, []) or []
    lines = [head, *body, *rest]
    if len(lines) > MAX_LINES:  # (the regions' one-line summaries go first, the newest problems stay)
        over = len(lines) - MAX_LINES + 1
        cut = [n for n, line in enumerate(lines) if line.startswith("region = ")][-over:]
        lines = [line for n, line in enumerate(lines) if n not in set(cut)]
        lines = lines[:MAX_LINES - 1] + [f"cut = {over} line(s) left out"]
    return "\n".join([FENCE, *lines, FENCE])


def line_count(text: str) -> int:
    """The lines of the report *text* within its fence."""
    return max(0, text.count("\n") - 1)


def copy_report(app: Any, regions: Iterable[Any] | None = None, with_text: bool = False, widget: Any = None,
                result: Any = None) -> int:
    """`report_text` on the clipboard (through *widget*, else the window: `copy_details.put_on_clipboard`) in place of
    what was there - the person asked for it -, and the right pane says how many lines (`COPIED`); that number."""
    from .copy_details import put_on_clipboard

    text = report_text(app, regions, with_text, result)
    put_on_clipboard(widget if widget is not None else app, text)
    n = line_count(text)
    say = getattr(app, "say", None)
    if callable(say):
        say(COPIED, n=n)
    return n


def menu_entries(app: Any, menu: Any) -> None:
    """The Menu's report entries: Copy a report (the page on show); while editing with regions chosen, Copy a report of
    the chosen regions, and with one chosen, Copy a report with this region's text. No dialog: the foreground goes
    back to the viewer as the menu ends."""
    from . import see_edit
    from .translator import chosen_regions

    menu.add_command(label=_(COPY_REPORT), command=lambda: copy_report(app))
    chosen = chosen_regions(app) if _get(lambda: see_edit.on(app), False) else []
    if chosen:
        menu.add_command(label=_(COPY_CHOSEN), command=lambda: copy_report(app, chosen_regions(app)))
    if len(chosen) == 1:
        menu.add_command(label=_(COPY_WITH_TEXT),
                         command=lambda: copy_report(app, chosen_regions(app)[:1], with_text=True))
