"""Many monitor layouts, by calculation only - no display setting is changed: each layout is one line of `LAYOUTS`
(its monitors, the primary marked, each at its own scale), and every viewer place a layout gives (`placements`: a
window on each monitor, one maximised there, one over the edge of every two monitors that meet) goes through the
same checks against a stand-in for Windows' monitor calls (`Screen`: MonitorFromPoint, MonitorFromRect/Window -
the monitor that holds most of the window, else the nearest -, the work areas, the virtual screen, each monitor's
DPI, the frame Windows draws round a window at that DPI):

* the hidden window off every monitor;
* every dialog on the viewer's monitor, inside its work area (those placed over the viewer, those that come by
  themselves over its monitor's middle), its frame as that monitor draws it;
* the viewer chooser over the window preselected;
* the region editor beside the region's box and the place entry over its number plate, inside the monitor;
* the side panes inside the viewer's window, never on the page on show nor within GAP px of it, and through pages
  turned in one window (`WALKS`: spreads and single pages) within MAX_FROM_PAGE px of the widest the page has been,
  moved only when a wider page than any before came and then only as far as they must (`walk`, `_span`; on
  ultrawide monitors how far each is from the page, and was the old way, and how often each moved: `pane_gaps`);
* the DPI the lettering and the dialogs take: the viewer's monitor's (never that of the monitor nearest the hidden
  window's place);
* a box moved and resized on the lettering's window with the pointer's messages as Windows sends them (client
  pixels, negative past the window's left or top edge), at the viewer's DPI, and a drag past the client's edge.

Adding a layout is adding one line to `LAYOUTS`."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Iterator

import pytest

import taslation.capture as capture
from taslation import panes as pn
from taslation import seethrough as st
from taslation.ui import layout, see_edit, see_menu
from taslation.ui import seethrough as ui

Box = tuple[int, int, int, int]
VIEWER = 500  # the viewer's window handle
TASKBAR_PX = 48  # the taskbar at the foot of every monitor, at 100 %
BORDER_PX, CAPTION_PX = 8, 31  # the frame Windows draws round a window at 100 % (`layout.frame_extents`)
WINDOW = (1300, 900)  # a viewer's window that is not maximised, at 100 %
ROOT_SIZE = (1180, 920)  # the hidden window's size (`layout.DEFAULT_SIZE`)
DIALOGS = {"small box": (420, 180), "Settings": (640, 560), "large": (980, 820)}  # inside sizes at 100 %
EDITOR = (480, 400)  # the region editor's inside at 100 %
ENTRY = (40, 24)  # the place entry at 100 %


@dataclass(frozen=True)
class Mon:
    rect: Box
    scale: int = 100
    primary: bool = False

    @property
    def dpi(self) -> int:
        return round(96 * self.scale / 100)

    @property
    def work(self) -> Box:
        left, top, right, bottom = self.rect
        return left, top, right, bottom - round(TASKBAR_PX * self.scale / 100)


def mon(x: int, y: int, w: int, h: int, scale: int = 100, primary: bool = False) -> Mon:
    return Mon((x, y, x + w, y + h), scale, primary)


P = True  # (the primary monitor)
LAYOUTS: dict[str, tuple[Mon, ...]] = {
    "two 1920x1080 in a row (this computer)": (mon(0, 0, 1920, 1080, primary=P), mon(1920, 0, 1920, 1080)),
    "3 in a row": (mon(0, 0, 1920, 1080, primary=P), mon(1920, 0, 1920, 1080), mon(3840, 0, 1920, 1080)),
    "3, the primary in the middle": (mon(-1920, 0, 1920, 1080), mon(0, 0, 1920, 1080, primary=P),
                                     mon(1920, 0, 1920, 1080)),
    "4 in a row": (mon(0, 0, 1920, 1080, primary=P), mon(1920, 0, 1920, 1080), mon(3840, 0, 1920, 1080),
                   mon(5760, 0, 1920, 1080)),
    "3, ultrawide 3440x1440 between two 16:9, other tops": (mon(-1920, 180, 1920, 1080),
                                                            mon(0, 0, 3440, 1440, primary=P),
                                                            mon(3440, 180, 1920, 1080)),
    "3, 2560x1440 at 125 % above two 16:9": (mon(0, 0, 1920, 1080, primary=P), mon(1920, 0, 1920, 1080),
                                             mon(640, -1440, 2560, 1440, 125)),
    "4, ultrawide 5120x1440 above three, 125 % in the middle": (mon(0, 0, 1920, 1080, primary=P),
                                                               mon(1920, 0, 2560, 1440, 125),
                                                               mon(4480, 0, 1920, 1080), mon(0, -1440, 5120, 1440)),
    "4 at 150 % in a row": (mon(0, 0, 3840, 2160, 150, primary=P), mon(3840, 0, 3840, 2160, 150),
                            mon(7680, 0, 3840, 2160, 150), mon(11520, 0, 3840, 2160, 150)),
    "2x2 grid": (mon(0, 0, 1920, 1080, primary=P), mon(1920, 0, 1920, 1080), mon(0, -1080, 1920, 1080),
                 mon(1920, -1080, 1920, 1080)),
    "L shape with a gap": (mon(0, 0, 1920, 1080, primary=P), mon(1920, 0, 1920, 1080), mon(1920, 1080, 1920, 1080)),
    "1920x1080 beside 2560x1440 beside 3840x2160, other tops": (mon(0, 360, 1920, 1080, primary=P),
                                                               mon(1920, 0, 2560, 1440), mon(4480, -720, 3840, 2160)),
    "portrait 1080x1920": (mon(0, 0, 1080, 1920, primary=P),),
    "portrait beside 16:9": (mon(0, 0, 1920, 1080, primary=P), mon(1920, -420, 1080, 1920)),
    "ultrawide 2560x1080": (mon(0, 0, 2560, 1080, primary=P),),
    "ultrawide 3440x1440": (mon(0, 0, 3440, 1440, primary=P),),
    "ultrawide 3840x1080": (mon(0, 0, 3840, 1080, primary=P),),
    "ultrawide 5120x1440": (mon(0, 0, 5120, 1440, primary=P),),
    "ultrawide 2560x1080 beside 16:9": (mon(0, 0, 1920, 1080, primary=P), mon(1920, 0, 2560, 1080)),
    "ultrawide 3440x1440 beside 16:9": (mon(0, 0, 1920, 1080, primary=P), mon(1920, 0, 3440, 1440)),
    "ultrawide 3840x1080 beside 16:9": (mon(0, 0, 1920, 1080, primary=P), mon(1920, 0, 3840, 1080)),
    "ultrawide 5120x1440 left of 16:9": (mon(-5120, 0, 5120, 1440), mon(0, 0, 1920, 1080, primary=P)),
    "100 % with 125 %": (mon(0, 0, 1920, 1080, primary=P), mon(1920, 0, 2560, 1440, 125)),
    "100 % with 150 %": (mon(0, 0, 1920, 1080, primary=P), mon(1920, 0, 3840, 2160, 150)),
    "100 % with 200 %": (mon(0, 0, 1920, 1080, primary=P), mon(1920, 0, 3840, 2160, 200)),
    "150 % primary, 100 % to its left": (mon(-1920, 0, 1920, 1080), mon(0, 0, 3840, 2160, 150, primary=P)),
}


def _gap(rect: Box, x: int, y: int) -> int:
    """How far the point (x, y) is from *rect* (0 inside it), as Windows measures a nearest monitor."""
    dx = max(rect[0] - x, 0, x - (rect[2] - 1))
    dy = max(rect[1] - y, 0, y - (rect[3] - 1))
    return dx * dx + dy * dy


def _meet(a: Box, b: Box) -> int:
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def _inside(inner: Box, outer: Box) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def extents(dpi: int) -> tuple[int, int]:
    return round(BORDER_PX * dpi / 96), round(CAPTION_PX * dpi / 96)


class Screen:
    """Windows' monitor calls for the monitors of a layout, and the windows on them by handle."""

    def __init__(self, monitors: tuple[Mon, ...], windows: dict[int, Box]):
        self.monitors, self.windows = monitors, windows

    @property
    def primary(self) -> Mon:
        return next(m for m in self.monitors if m.primary)

    def at(self, x: int, y: int, nearest: bool = True) -> Mon | None:
        """MonitorFromPoint: the monitor that holds the point, else the nearest (or None)."""
        holding = [m for m in self.monitors if m.rect[0] <= x < m.rect[2] and m.rect[1] <= y < m.rect[3]]
        if holding:
            return holding[0]
        return min(self.monitors, key=lambda m: _gap(m.rect, x, y)) if nearest else None

    def of_rect(self, rect: Box) -> Mon:
        """MonitorFromRect / MonitorFromWindow: the one that holds most of *rect*, else the nearest to its middle."""
        best = max(self.monitors, key=lambda m: _meet(m.rect, rect))
        if _meet(best.rect, rect) > 0:
            return best
        return self.at((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2)  # type: ignore[return-value]

    def virtual(self) -> tuple[int, int, int, int]:
        left, top = min(m.rect[0] for m in self.monitors), min(m.rect[1] for m in self.monitors)
        right, bottom = max(m.rect[2] for m in self.monitors), max(m.rect[3] for m in self.monitors)
        return left, top, right - left, bottom - top

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def work_area(_widget: Any, x: int | None = None, y: int | None = None) -> Box:
            return (self.at(x, y) if x is not None and y is not None else self.primary).work

        def dpi_at(x: int | None = None, y: int | None = None) -> int:
            return (self.at(x, y) if x is not None and y is not None else self.primary).dpi

        def frame_extents(at: tuple[int, int] | None = None) -> tuple[int, int]:
            return extents(dpi_at(*at) if at is not None else self.primary.dpi)  # (the system's DPI: the primary's)

        def monitor_rect(hwnd: int) -> Box | None:
            return self.of_rect(self.windows[hwnd]).rect if hwnd in self.windows else None

        def monitor_at(x: int, y: int) -> Box | None:
            m = self.at(x, y, nearest=False)
            return m.rect if m is not None else None

        monkeypatch.setattr(layout, "work_area", work_area)
        monkeypatch.setattr(layout, "dpi_at", dpi_at)
        monkeypatch.setattr(layout, "frame_extents", frame_extents)
        monkeypatch.setattr(layout, "monitor_rect", monitor_rect)
        monkeypatch.setattr(layout, "monitor_at", monitor_at)
        monkeypatch.setattr(layout, "window_exists", lambda hwnd: hwnd in self.windows)
        monkeypatch.setattr(layout, "IS_WINDOWS", True)
        monkeypatch.setattr(capture, "window_exists", lambda hwnd: hwnd in self.windows)
        monkeypatch.setattr(capture, "window_rect", lambda hwnd: self.windows[hwnd])
        monkeypatch.setattr(ui.window, "virtual_screen", self.virtual)
        monkeypatch.setattr(ui.window, "viewer_dpi", lambda hwnd: self.of_rect(self.windows[hwnd]).dpi)


@dataclass(frozen=True)
class Place:
    """A viewer's window on a layout: its rectangle and its client area (screen pixels)."""

    label: str
    rect: Box
    client: Box


def _client(rect: Box, scale: int) -> Box:
    b = round(BORDER_PX * scale / 100)  # (a browser draws its own title bar: the client is the window less its border)
    return rect[0] + b, rect[1] + b, rect[2] - b, rect[3] - b


def placements(monitors: tuple[Mon, ...]) -> Iterator[Place]:
    for i, m in enumerate(monitors):
        s = m.scale
        l_, t_, r_, b_ = m.work
        w = min(round(WINDOW[0] * s / 100), r_ - l_ - 40)
        h = min(round(WINDOW[1] * s / 100), b_ - t_ - 40)
        x, y = l_ + min(100, r_ - l_ - w) * s // 100, t_ + min(60, b_ - t_ - h) * s // 100
        rect = (x, y, x + w, y + h)
        yield Place(f"on monitor {i + 1}", rect, _client(rect, s))
        b = round(BORDER_PX * s / 100)  # (a maximised window reaches its border beyond the work area)
        rect = (l_ - b, t_ - b, r_ + b, b_ + b)
        yield Place(f"maximised on monitor {i + 1}", rect, _client(rect, s))
    far_left, far_right = min(m.rect[0] for m in monitors), max(m.rect[2] for m in monitors)
    for i, m in enumerate(monitors):  # (dragged mostly off the screen past an outer edge: three tenths still on it)
        w, h = round(WINDOW[0] * m.scale / 100), min(round(WINDOW[1] * m.scale / 100), m.work[3] - m.work[1] - 120)
        top = m.work[1] + 60
        if m.rect[2] == far_right:
            rect = (m.rect[2] - w * 3 // 10, top, m.rect[2] + w * 7 // 10, top + h)
            yield Place(f"mostly past the right edge of monitor {i + 1}", rect, _client(rect, m.scale))
        if m.rect[0] == far_left:
            rect = (m.rect[0] - w * 7 // 10, top, m.rect[0] + w * 3 // 10, top + h)
            yield Place(f"mostly past the left edge of monitor {i + 1}", rect, _client(rect, m.scale))
    for i, a in enumerate(monitors):
        for j, c in enumerate(monitors):
            if i == j or a.rect[2] != c.rect[0]:
                continue
            top = max(a.rect[1], c.rect[1])
            bottom = min(a.rect[3], c.rect[3])
            if bottom - top < 400:
                continue
            w, h = round(WINDOW[0] * a.scale / 100), min(round(WINDOW[1] * a.scale / 100), bottom - top - 100)
            x = a.rect[2] - w * 6 // 10  # (six tenths on the left one)
            rect = (x, top + 50, x + w, top + 50 + h)
            yield Place(f"over monitors {i + 1} and {j + 1}", rect, _client(rect, a.scale))


CASES = [pytest.param(name, place, id=f"{name}: {place.label}")
         for name, monitors in LAYOUTS.items() for place in placements(monitors)]


@pytest.fixture
def screen(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Screen:
    name, place = request.node.callspec.params["name"], request.node.callspec.params["place"]
    s = Screen(LAYOUTS[name], {VIEWER: place.rect})
    s.install(monkeypatch)
    return s


def _app(dpi: int | None = None, origin: tuple[int, int] | None = None) -> SimpleNamespace:
    """The window as the dialogs and the editing see it: hidden (see-through mode), following the viewer."""
    over = SimpleNamespace(client_origin=lambda: origin)
    return SimpleNamespace(_see_hidden=True, selected=SimpleNamespace(hwnd=VIEWER), _see_through=over,
                           _see_dpi=dpi if dpi is not None else st.BASE_DPI, _own_hwnd=lambda: 0)


class _Parent:
    """A dialog's parent: the hidden window, which says where its dialogs go (`seethrough.dialog_centre`)."""

    def __init__(self, app: SimpleNamespace):
        self.app = app

    def winfo_toplevel(self) -> SimpleNamespace:
        return SimpleNamespace(dialog_centre=lambda: ui.dialog_centre(self.app))

    def _root(self) -> SimpleNamespace:
        return self.app


def _frame(spot: tuple[int, int], size: tuple[int, int], dpi: int) -> Box:
    border, caption = extents(dpi)
    return spot[0], spot[1], spot[0] + size[0] + 2 * border, spot[1] + size[1] + caption + border


def _scaled(size: tuple[int, int], dpi: int) -> tuple[int, int]:
    return round(size[0] * dpi / 96), round(size[1] * dpi / 96)


# ------------------------------------------------------------------ the checks, one layout and viewer place each
@pytest.mark.parametrize("name, place", CASES)
def test_the_hidden_window_meets_no_monitor(name: str, place: Place, screen: Screen) -> None:
    geometry = layout.GEOMETRY.match(ui.root_geometry(f"{ROOT_SIZE[0]}x{ROOT_SIZE[1]}+0+0"))
    assert geometry is not None
    x, y = int(geometry.group(3)), int(geometry.group(4))
    worst = max(m.dpi for m in screen.monitors)  # (its frame at the largest scale there is)
    rect = _frame((x, y), _scaled(ROOT_SIZE, worst), worst)
    assert not any(_meet(m.rect, rect) for m in screen.monitors)


@pytest.mark.parametrize("name, place", CASES)
def test_every_dialog_goes_on_the_viewer_s_monitor_inside_its_work_area(name: str, place: Place,
                                                                      screen: Screen) -> None:
    viewer = screen.of_rect(place.rect)
    parent = _Parent(_app(viewer.dpi))
    area, centre = layout.dialog_area(None, parent)  # type: ignore[arg-type]
    assert area == viewer.work  # (over the viewer: the part of it on its monitor, `dialog_centre`)
    assert screen.at(*centre) == viewer
    by_itself = layout.book_monitor(parent)  # type: ignore[arg-type]
    assert by_itself == viewer.rect  # (one that comes by itself: over its monitor's middle, `place_by_book`)
    middle = ((by_itself[0] + by_itself[2]) // 2, (by_itself[1] + by_itself[3]) // 2)
    for kind, size in DIALOGS.items():
        size = _scaled(size, viewer.dpi)  # (Tk's scaling follows the viewer's monitor: `seethrough.dialog_dpi`)
        for where in (centre, middle):
            spot = layout.dialog_spot(size, where, layout.work_area(None, *where))
            frame = _frame(spot, size, viewer.dpi)
            if frame[2] - frame[0] <= area[2] - area[0] and frame[3] - frame[1] <= area[3] - area[1]:
                assert _inside(frame, area), kind
            else:  # (larger than the work area: its title bar on it, the rest cut where the dialog fits itself)
                assert (spot[0], spot[1]) == (area[0], area[1]), kind


@pytest.mark.parametrize("name, place", CASES)
def test_the_viewer_chooser_goes_over_the_window_preselected(name: str, place: Place, screen: Screen) -> None:
    chooser = SimpleNamespace(box=SimpleNamespace(current=lambda: 0),
                              windows=[SimpleNamespace(hwnd=VIEWER, rect=place.rect)])
    at = see_menu.ViewerDialog._over_preselected(chooser)  # type: ignore[arg-type]
    assert at is not None
    area, centre = layout.dialog_area(None, None, at=at)  # type: ignore[arg-type]
    holder = screen.at(*centre, nearest=False)
    assert holder is not None and _meet(holder.rect, place.rect) > 0  # (on a monitor the window shows on)
    size = _scaled(DIALOGS["small box"], holder.dpi)
    assert _inside(_frame(layout.dialog_spot(size, centre, area), size, holder.dpi), area)


def _boxes(size: tuple[int, int], dpi: int) -> list[Box]:
    """Regions' boxes (frame pixels) at the frame's four corners and in its middle."""
    w, h = _scaled((200, 120), dpi)
    m = st.scaled(10, dpi)
    width, height = size
    return [(m, m, m + w, m + h), (width - m - w, m, width - m, m + h), (m, height - m - h, m + w, height - m),
            (width - m - w, height - m - h, width - m, height - m),
            ((width - w) // 2, (height - h) // 2, (width + w) // 2, (height + h) // 2)]


@pytest.mark.parametrize("name, place", CASES)
def test_the_region_editor_and_the_place_entry_stay_beside_the_box_inside_its_monitor(name: str, place: Place,
                                                                                    screen: Screen) -> None:
    client = place.client
    size = (client[2] - client[0], client[3] - client[1])
    dpi = screen.of_rect(place.rect).dpi
    app = _app(dpi, (client[0], client[1]))
    for box in _boxes(size, dpi):
        on_screen = (client[0] + box[0], client[1] + box[1], client[0] + box[2], client[1] + box[3])
        middle = ((on_screen[0] + on_screen[2]) // 2, (on_screen[1] + on_screen[3]) // 2)
        holder = screen.at(*middle)
        area = holder.work
        spot = see_edit.editor_place(app, SimpleNamespace(bbox=box))  # type: ignore[misc]
        assert spot is not None
        inside = _scaled(EDITOR, holder.dpi)
        frame = _frame(spot(*inside), inside, holder.dpi)
        assert _inside(frame, area)
        visible = (max(on_screen[0], area[0]), max(on_screen[1], area[1]), min(on_screen[2], area[2]),
                   min(on_screen[3], area[3]))
        room = max(visible[0] - area[0], area[2] - visible[2]) >= frame[2] - frame[0] + st.scaled(see_edit.EDITOR_GAP,
                                                                                                    dpi)
        if room:
            assert not _meet(frame, visible), "the editor covers the box with room beside it"
        plate = pn.badge("12", (60, 160, 80), dpi)
        px, py = see_edit._place_plate(box, plate, size, dpi)
        h, w = plate.shape[:2]
        plate_on_screen = (client[0] + px, client[1] + py, client[0] + px + w, client[1] + py + h)
        entry = _scaled(ENTRY, holder.dpi)
        ex, ey = see_edit.entry_spot(plate_on_screen, entry, layout.work_area(None, *middle))
        assert _inside((ex, ey, ex + entry[0], ey + entry[1]), area)


def _page(size: tuple[int, int], aspect: float) -> Box:
    """The page box of a viewer that fits the page (width / height *aspect*) to its frame, in the middle."""
    width, height = size
    ph, pw = height, round(height * aspect)
    if pw > width:
        pw, ph = width, round(width / aspect)
    return (width - pw) // 2, (height - ph) // 2, (width + pw) // 2, (height + ph) // 2


def pane_sizes(dpi: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """The left pane's and the right one's (width, height) at *dpi*."""
    return (st.scaled(200, dpi), st.scaled(520, dpi)), (st.scaled(pn.INDICATORS_W, dpi), st.scaled(600, dpi))


def pane_boxes(size: tuple[int, int], page: Box, dpi: int,
               before: tuple[int | None, int | None] | None = None) -> tuple[Box | None, Box | None]:
    left, right = pane_sizes(dpi)
    return pn.place(size, page, (0, size[1]), left, right, dpi, before=before)


def from_page(boxes: tuple[Box | None, Box | None], page: Box) -> tuple[int | None, int | None]:
    """The px from *page* to the left pane and from the page to the right one (None: hidden)."""
    left, right = boxes
    return page[0] - left[2] if left else None, right[0] - page[2] if right else None


# the pages a viewer shows in one window, one after the other: spreads (1.42; 1.5 a wider one) and single pages
WALKS = {"a spread first": (1.42, 0.71, 1.42, 0.71, 0.65, 0.71, 1.42),
         "a single page first": (0.71, 0.65, 0.71, 1.42, 0.71, 1.42, 0.71),
         "a wider spread later": (0.71, 1.42, 0.71, 1.5, 0.71, 1.42, 0.71)}


@dataclass(frozen=True)
class Step:
    """A page of a walk: its aspect, its box, the box the panes went by (`pn.reaches`), the panes' boxes, how far
    each moved from where it was (0 for the first page and for a pane hidden then or before)."""

    aspect: float
    page: Box
    wide: Box
    boxes: tuple[Box | None, Box | None]
    moved: tuple[int, int]


def walk(size: tuple[int, int], dpi: int, aspects: tuple[float, ...]) -> list[Step]:
    """*aspects*' pages shown one after the other in one window as `ui.seethrough.panes_tick` places the panes: by
    the widest the page has been beside which each pane fitted, each where it was while that still does."""
    (lw, _lh), (rw, _rh) = pane_sizes(dpi)
    fits = (lambda room: room >= lw, lambda room: room >= rw)
    steps = []
    seen: tuple[int | None, int | None] = (None, None)
    before: tuple[int | None, int | None] | None = None
    for aspect in aspects:
        page = _page(size, aspect)
        reach = pn.reaches(size, page, seen, fits, dpi)
        wide = (page[0] if reach[0] is None else reach[0], page[1], page[2] if reach[1] is None else reach[1], page[3])
        boxes = pane_boxes(size, wide, dpi, before)
        edges, was = pn.edges(boxes), before or (None, None)
        moved = (abs(edges[0] - was[0]) if edges[0] is not None and was[0] is not None else 0,
                 abs(edges[1] - was[1]) if edges[1] is not None and was[1] is not None else 0)
        steps.append(Step(aspect, page, wide, boxes, moved))
        seen, before = pn.seen_after(reach, seen), pn.edges(boxes, before)
    return steps


def moves(steps: list[Step]) -> tuple[int, int]:
    """How many times each pane moved through *steps*."""
    return sum(1 for s in steps if s.moved[0]), sum(1 for s in steps if s.moved[1])


@pytest.mark.parametrize("name, place", CASES)
def test_the_side_panes_stay_inside_the_viewer_s_window(name: str, place: Place, screen: Screen) -> None:
    client = place.client
    size = (client[2] - client[0], client[3] - client[1])
    dpi = screen.of_rect(place.rect).dpi
    gap, far = st.scaled(pn.GAP, dpi), st.scaled(pn.MAX_FROM_PAGE, dpi)
    for aspects in ((1.42,), (0.71,), *WALKS.values()):  # (a spread, one page, each alone; then the walks)
        for step in walk(size, dpi, aspects):
            for placed in step.boxes:
                box = ui.pane_on_screen(placed, (client[0], client[1]))
                if placed is not None and "mostly past" not in place.label:
                    assert box == placed  # (on the screen whole: shown where `panes.place` put it)
                if box is None:  # (no room beside the page, or partly off the screen: hidden, the Menu from there)
                    continue
                assert _inside(box, (0, 0, *size)) and not _meet(box, step.page)
                on_screen = (client[0] + box[0], client[1] + box[1], client[0] + box[2], client[1] + box[3])
                corners = ((on_screen[0], on_screen[1]), (on_screen[2] - 1, on_screen[3] - 1))
                assert all(screen.at(x, y, nearest=False) is not None for x, y in corners)
                if "over monitors" not in place.label:  # (a window on one monitor: its panes on that one alone)
                    assert _inside(on_screen, screen.of_rect(place.rect).rect)
            # never on the page on show nor within a gap of it; within the cap of the widest the page has been
            for near, wide in zip(from_page(step.boxes, step.page), from_page(step.boxes, step.wide)):
                assert near is None or (near >= gap and wide is not None and gap <= wide <= far), (aspects, step)


def _span(size: tuple[int, int], page: Box, dpi: int) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
    """Where each pane's edge toward the page may be beside *page* (low, high; None: nowhere), worked out here on
    its own: GAP px from the page at the least, MAX_FROM_PAGE px at the most, the pane GAP px inside the frame."""
    gap, far = st.scaled(pn.GAP, dpi), st.scaled(pn.MAX_FROM_PAGE, dpi)
    (lw, _lh), (rw, _rh) = pane_sizes(dpi)
    left = (max(gap + lw, page[0] - far), page[0] - gap)
    right = (page[2] + gap, min(size[0] - gap - rw, page[2] + far))
    return (left if left[0] <= left[1] else None), (right if right[0] <= right[1] else None)


@pytest.mark.parametrize("name, place", CASES)
def test_through_spreads_and_single_pages_a_pane_moves_only_when_a_wider_page_comes_and_then_only_as_far_as_it_must(
        name: str, place: Place, screen: Screen) -> None:
    client = place.client
    size = (client[2] - client[0], client[3] - client[1])
    dpi = screen.of_rect(place.rect).dpi
    for label, aspects in WALKS.items():
        widest: list[int | None] = [None, None]  # (worked out here: per side the farthest out a page's edge came
        before: list[int | None] = [None, None]  # beside which the pane fitted; the panes' edges toward the page)
        for step in walk(size, dpi, aspects):
            spans_now, spans_wide = _span(size, step.page, dpi), _span(size, step.wide, dpi)
            for k in (0, 1):
                edge_now = step.page[0] if k == 0 else step.page[2]
                fits_now = spans_now[k] is not None
                assert (step.boxes[k] is None) == (not fits_now), (label, step)  # (hidden exactly where no room)
                grew = fits_now and (widest[k] is None or (edge_now < widest[k] if k == 0 else edge_now > widest[k]))
                if grew:
                    widest[k] = edge_now
                assert (step.wide[0] if k == 0 else step.wide[2]) == (widest[k] if fits_now else edge_now), (label, k)
                box, span = step.boxes[k], spans_wide[k]
                if box is None or span is None:
                    continue
                edge = box[2] if k == 0 else box[0]
                if before[k] is None:  # (no place before: as far from the widest page as the span lets it)
                    assert edge == (span[0] if k == 0 else span[1])
                elif not grew:
                    assert edge == before[k]  # (no wider page: not moved, however far the page on show is)
                else:  # (a wider page: moved once, to the span's end nearest to where it was, if it must)
                    assert edge == min(max(before[k], span[0]), span[1])
                before[k] = edge


@pytest.mark.parametrize("name, place", CASES)
def test_the_lettering_and_the_dialogs_take_the_viewer_s_monitor_s_dpi(name: str, place: Place,
                                                                       screen: Screen) -> None:
    viewer = screen.of_rect(place.rect)
    dpi = ui.window.viewer_dpi(VIEWER)
    assert dpi == viewer.dpi  # (the patches' and the panes' sizes, the grips: `seethrough.px`)
    assert ui.dialog_dpi(_app(dpi)) == viewer.dpi  # (Tk's scaling while hidden: `scaling.DpiWatch`'s source)
    no_viewer = _app(dpi)
    no_viewer.selected = None
    assert ui.dialog_dpi(no_viewer) == screen.primary.dpi  # (before a viewer: where the start's dialogs go)


def _lparam(x: int, y: int) -> int:
    """A pointer message's position as Windows packs it: client pixels, each a signed 16-bit word."""
    return (ctypes.c_ushort(y).value << 16) | ctypes.c_ushort(x).value


def _client_point(screen_point: tuple[int, int], client: Box) -> tuple[int, int]:
    """(as `SeeThrough._edit_message` reads it) the client point of a pointer message at *screen_point*."""
    lparam = _lparam(screen_point[0] - client[0], screen_point[1] - client[1])
    return ctypes.c_short(lparam & 0xFFFF).value, ctypes.c_short((lparam >> 16) & 0xFFFF).value


@pytest.mark.parametrize("name, place", CASES)
def test_a_box_is_moved_and_resized_on_the_lettering_at_the_viewer_s_dpi_past_the_client_s_edge(
        name: str, place: Place, screen: Screen) -> None:
    client = place.client
    size = (client[2] - client[0], client[3] - client[1])
    dpi = screen.of_rect(place.rect).dpi
    reach = st.scaled(st.GRIP_PX, dpi)
    boxes = tuple(_boxes(size, dpi))
    plate = pn.badge("1", (60, 160, 80), dpi)
    plates = tuple((plate, see_edit._place_plate(b, plate, size, dpi)) for b in boxes)
    marks = st.Marks(key=1, boxes=boxes, plates=plates)
    far = 300 * dpi // 96  # (the pointer this far past the client's edges, the capture the window's)
    for i, box in enumerate(boxes):
        corner = (client[0] + box[2] + reach - 1, client[1] + box[3] + reach - 1)  # (the se corner, just within reach)
        start = _client_point(corner, client)
        assert st.edit_grip(marks, start, reach) == (i, "se")
        past = _client_point((client[2] + far, client[3] + far), client)
        moved = st.edit_drag(marks, i, "se", start, past, size)[i]
        assert moved[2] == size[0] and moved[3] == size[1] and moved[:2] == box[:2]
        nw = _client_point((client[0] + box[0] - reach + 1, client[1] + box[1] - reach + 1), client)
        assert st.edit_grip(marks, nw, reach) == (i, "nw")
        past = _client_point((client[0] - far, client[1] - far), client)
        assert past[0] < 0 and past[1] < 0  # (negative client pixels, read as such)
        moved = st.edit_drag(marks, i, "nw", nw, past, size)[i]
        assert moved[0] == 0 and moved[1] == 0 and moved[2:] == box[2:]
        inside = _client_point((client[0] + (box[0] + box[2]) // 2, client[1] + box[3] - 2 * reach), client)
        assert st.edit_grip(marks, inside, reach) == (i, "move")
        moved = st.edit_drag(marks, i, "move", inside, past, size)[i]
        assert moved[0] == 0 and moved[1] == 0 and (moved[2] - moved[0], moved[3] - moved[1]) == (
            box[2] - box[0], box[3] - box[1])
        px, py = plates[i][1]
        on_plate = _client_point((client[0] + px + plate.shape[1] // 2, client[1] + py + plate.shape[0] // 2), client)
        assert st.edit_grip(marks, on_plate, reach) == (i, st.PLATE)
    drawn = st.drawn_box(_client_point((client[0] - far, client[1] - far), client),
                         _client_point((client[2] + far, client[3] + far), client), size)
    assert drawn == (0, 0, *size)


# ------------------------------------------------------------------ what is reported, and the old ways it replaced
ULTRAWIDE = [(name, place) for name, monitors in LAYOUTS.items() if "ultrawide" in name
             for place in placements(monitors) if place.label.startswith("maximised")
             and (lambda m: (m.rect[2] - m.rect[0]) / (m.rect[3] - m.rect[1]) > 2)(
                 Screen(monitors, {VIEWER: place.rect}).of_rect(place.rect))]


def _old_place(size: tuple[int, int], page: Box, dpi: int) -> tuple[Box | None, Box | None]:
    """(the old way, before 2.0.0's cap) each pane GAP px in from the frame's edge whatever the page's width."""
    gap = st.scaled(pn.GAP, dpi)
    (lw, lh), (rw, rh) = pane_sizes(dpi)
    left = (gap, gap, gap + lw, gap + lh)
    right = (size[0] - gap - rw, gap, size[0] - gap, gap + rh)
    return (left if left[2] + gap <= page[0] else None), (right if right[0] - gap >= page[2] else None)


def pane_gaps() -> list[tuple[str, str, str, int, int | None, int | None, int | None, int | None]]:
    """(layout, viewer place, page, client width, px from the page to the left pane and to the right one, None:
    hidden; the same the old way) on every ultrawide monitor maximised, for a spread and for one page, each the
    first page shown."""
    rows = []
    for name, place in ULTRAWIDE:
        client = place.client
        size = (client[2] - client[0], client[3] - client[1])
        dpi = Screen(LAYOUTS[name], {VIEWER: place.rect}).of_rect(place.rect).dpi
        for label, aspect in (("spread", 1.42), ("one page", 0.71)):
            page = _page(size, aspect)
            rows.append((name, place.label, label, size[0], *from_page(walk(size, dpi, (aspect,))[0].boxes, page),
                         *from_page(_old_place(size, page, dpi), page)))
    return rows


def test_on_ultrawide_monitors_the_panes_come_within_the_cap_of_the_widest_page_where_the_edges_were_far() -> None:
    rows = pane_gaps()
    assert len(rows) == 2 * len(ULTRAWIDE) and ULTRAWIDE
    for name, label, page, width, left, right, _old_left, _old_right in rows:
        assert left is not None and right is not None, (name, label, page)
        assert pn.GAP <= left <= pn.MAX_FROM_PAGE and pn.GAP <= right <= pn.MAX_FROM_PAGE  # (all at 100 % here)
    old = {(r[0], r[2]): r[6] for r in rows}
    assert old[("ultrawide 5120x1440", "one page")] == 1858  # (the old way: the left pane 1858 px from a page)
    assert max(max(r[6], r[7]) for r in rows) > pn.MAX_FROM_PAGE
    print("\nlayout | viewer | first page | client width | page to left pane px | page to right pane px | the old"
          " way: left | right")
    for row in rows:
        print(" | ".join(str(v) for v in row))
    print("\nlayout | viewer | walk | moves (left, right) | at the end, px from the widest page | from the page"
          " on show")
    for name, place in ULTRAWIDE:
        size = (place.client[2] - place.client[0], place.client[3] - place.client[1])
        for label, aspects in WALKS.items():
            steps = walk(size, 96, aspects)
            for step in steps:  # (within the cap of the widest the page has been, whatever is on show)
                assert all(px is not None and pn.GAP <= px <= pn.MAX_FROM_PAGE
                           for px in from_page(step.boxes, step.wide)), (name, label, step)
            grown = sum(1 for i in range(1, len(aspects)) if aspects[i] > max(aspects[:i]))
            assert max(moves(steps)) <= grown  # (a move only where a wider page than any before came)
            if label == "a spread first":
                assert moves(steps) == (0, 0)
            last = steps[-1]
            print(name, "|", place.label, "|", label, "|", moves(steps), "|", from_page(last.boxes, last.wide), "|",
                  from_page(last.boxes, last.page))


def test_in_a_1920_window_the_panes_stand_still_once_a_spread_was_seen_and_move_once_at_most_before() -> None:
    """The commonest window, a maximised 1920 x 1080 one: a spread first, the panes at the frame's edges (as near
    the spread as the old way) and never moved through single pages and spreads, though one page is 385 px from
    them; a single page first, the panes 300 px from it, then once out at the first spread, and still from there
    on; a spread wider than the ground leaves the panes room for hides them, and they come back where they were."""
    size = (1920, 1032)
    assert from_page(_old_place(size, _page(size, 0.71), 96), _page(size, 0.71)) == (385, 386)
    first = walk(size, 96, WALKS["a spread first"])
    assert moves(first) == (0, 0) and from_page(first[0].boxes, first[0].page) == (19, 20)
    assert {s.boxes for s in first} == {first[0].boxes}
    assert from_page(first[1].boxes, first[1].page) == (385, 386)  # (beside one page: where the spread put them)
    after = walk(size, 96, WALKS["a single page first"])
    assert from_page(after[0].boxes, after[0].page) == (pn.MAX_FROM_PAGE, pn.MAX_FROM_PAGE)
    assert moves(after) == (1, 1) and [s.aspect for s in after if any(s.moved)] == [1.42]
    assert {s.boxes for s in after[3:]} == {after[3].boxes}  # (from the first spread on: still)
    wider = walk(size, 96, WALKS["a wider spread later"])
    assert moves(wider) == (1, 1) and wider[3].boxes == (None, None)  # (1.5 wide: no room, hidden)
    assert wider[4].boxes == wider[2].boxes  # (and back where they were)


def _nearest_to_the_hidden_window(monitors: tuple[Mon, ...]) -> Mon:
    s = Screen(monitors, {})
    x, y = ui.off_screen(s.virtual())
    return s.at(x, y)  # type: ignore[return-value]


def test_where_the_dialogs_were_scaled_for_the_monitor_nearest_the_hidden_window_they_now_take_the_viewer_s(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """(the old way: Tk's scaling from the hidden window's own monitor, Windows' nearest to its place off every
    monitor - the dialogs of a viewer on another monitor drawn at the wrong scale)"""
    wrong = []
    for name, monitors in LAYOUTS.items():
        root_monitor = _nearest_to_the_hidden_window(monitors)
        for place in placements(monitors):
            s = Screen(monitors, {VIEWER: place.rect})
            with monkeypatch.context() as m:
                s.install(m)
                viewer = s.of_rect(place.rect)
                assert ui.dialog_dpi(_app(ui.window.viewer_dpi(VIEWER))) == viewer.dpi
            if root_monitor.dpi != viewer.dpi:
                wrong.append((name, place.label))
    assert ("100 % with 200 %", "maximised on monitor 2") in wrong  # (drawn at 100 % on a monitor at 200 % before)


def test_the_tick_scales_the_dialogs_again_when_the_viewer_goes_to_a_monitor_of_another_dpi(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from taslation.ui import see_edit as edit

    for name in ("present", "panes_tick", "keep_hidden", "front_tick", "foreground_tick"):
        monkeypatch.setattr(ui, name, lambda app: None)
    monkeypatch.setattr(edit, "tick", lambda app, over: None)
    monkeypatch.setattr(see_menu, "chooser_tick", lambda app: None)
    dpi = {"now": 96}
    monkeypatch.setattr(ui.window, "viewer_dpi", lambda hwnd: dpi["now"])
    checks = []
    over = SimpleNamespace(follow=lambda hwnd: None, set_hover_delay=lambda ms: None, set_add_key=lambda on: None)
    app = SimpleNamespace(_see_through=over, selected=SimpleNamespace(hwnd=VIEWER), _see_hidden=True,
                          _see_dpi=96, settings=SimpleNamespace(add_area_key=True, hover_delay_ms=450),
                          _dpi_watch=SimpleNamespace(check=lambda: checks.append(app._see_dpi)))
    ui.tick(app)
    assert checks == []  # (the same monitor: nothing)
    dpi["now"] = 192
    ui.tick(app)
    ui.tick(app)
    assert checks == [192] and app._see_dpi == 192


def test_a_dialog_s_frame_is_measured_on_the_monitor_it_goes_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """(the old way: the frame at the system's DPI, 100 % here - a dialog on a monitor at 200 % placed as if its
    title bar were half as tall, its foot under the taskbar)"""
    s = Screen(LAYOUTS["100 % with 200 %"], {VIEWER: (1920, 0, 5760, 2112)})
    s.install(monkeypatch)
    area = s.monitors[1].work
    border, caption = extents(192)
    size = (1000, area[3] - area[1] - caption - border)  # (as tall as the work area leaves a dialog there)
    centre = ((area[0] + area[2]) // 2, (area[1] + area[3]) // 2)
    spot = layout.dialog_spot(size, centre, area)
    assert _inside(_frame(spot, size, 192), area)
    with monkeypatch.context() as m:  # (the old way: the frame at the system's DPI wherever the dialog goes)
        m.setattr(layout, "frame_extents", lambda at=None: extents(96))
        old = layout.dialog_spot(size, centre, area)
    assert not _inside(_frame(old, size, 192), area)
