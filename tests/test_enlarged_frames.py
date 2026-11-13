"""What follows the viewer's window enlarged at the first read (`capture.enlarge_window`: moved and resized, no key), on
the window's real code with the capture as a script: the frame from before, a black frame of the new size, then the
page. The new frame goes on the page with the new size's capture area, Auto's first page goes on whoever is in front,
nothing is concluded about a viewer that does not draw, and no key at all goes to the viewer."""

from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from taslation.batch import thumbnail
from taslation.capture import CaptureError, Enlarged, Raised, WindowInfo, is_blank
from taslation.config import Settings
from taslation.pagekeys import PageKeys
from taslation.ui import live, reading, viewers
from taslation.ui.app import Profiles
from taslation.ui.live import Following, LiveViewMixin
from taslation.ui.viewers import ViewerMixin

HWND = 5
SMALL, WORK = (100, 60, 1300, 900), (0, 0, 1920, 1079)  # the window as the reader left it; its monitor's work area
OLD_SIZE, NEW_SIZE = (1920, 1032), (1920, 1079)
OLD_PANEL, NEW_PANEL = (637, 114, 1283, 1028), (579, 0, 1341, 1079)
HELPED = "This viewer draws nothing while it is covered: from now on it comes to the front for a moment at each page."


def page(size, seed=1):
    rng = np.random.default_rng(seed)
    return Image.fromarray(rng.integers(0, 255, (size[1] // 8, size[0] // 8, 3), dtype=np.uint8)).resize(size)


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class Window(LiveViewMixin, ViewerMixin):
    """The window's capture, live view, Auto and the wait for the viewer's window, as they are; around them a stand-in
    that only keeps what they ask for (`after` queues: `run` plays the queue and the heartbeats)."""

    def __init__(self, tmp_path, mode="events", owner="other"):
        self.settings = Settings(state_dir=tmp_path, settle_ms=0, auto_interval_ms=0, page_turn_wait_ms=0)
        self.settings.margins = (0, 0, 0, 0)
        self.profiles = Profiles(tmp_path / "profiles.json")
        self.selected = WindowInfo(HWND, "Yomizuq - Google Chrome", "Chrome_WidgetWin_1", 123, SMALL)
        self.jobs, self.said, self.shown, self.books = [], [], [], []
        self.auto_var, self.book_var = Var(True), Var("Yomizuq")
        self.ready, self.busy, self.reading, self.batch, self._batching = True, False, False, None, False
        self._page_areas, self._manual_area, self._hand_area, self._area_hinted = {}, False, None, False
        self._enlarged = self._enlarging = self._enlarge_asked = None
        self._area_large, self._covered = False, False
        self._live = self._live_thumb = self._fill = self._auto_last = self._auto_candidate = None
        self._start_pending = None
        self.canvas = SimpleNamespace(set_note=lambda *_a: None)
        self._book_scanned, self._scanned_book = False, ""
        self._following = Following(mode=mode, owner=owner, look_at=0.0,
                                    events=SimpleNamespace(take=lambda: [], viewer=HWND))

    _viewer_shows_book = lambda self, win: True
    _covers_viewer = lambda self, hwnd: True  # TASlation lies over the viewer
    _page_keys = lambda self, win=None: PageKeys()
    _name_needed = lambda self: True
    _page_uncached = lambda self, image: True
    scan_mode = lambda self: "page"

    def _set_covered(self, covered):
        self._covered = covered

    def say(self, text, **params):
        self.said.append(text)

    def status(self, line):
        pass

    def after(self, ms, job):
        self.jobs.append(job)
        return job

    def after_cancel(self, job):
        if job in self.jobs:
            self.jobs.remove(job)

    def _redisplay(self):
        self.shown.append(self._live)

    def _begin_book(self, image, thumb, whole):
        self.books.append((image, tuple(self.settings.margins)))

    def run(self, until, steps=60):
        """Heartbeats and what waits, in turn, until *until()* or the steps are up."""
        for _ in range(steps):
            if until():
                return
            for job in self.jobs[:]:
                if job in self.jobs:
                    self.jobs.remove(job)
                    job()
            self._beat()


@pytest.fixture
def desk(monkeypatch):
    """The viewer's window (`frames`: what each capture gives, the last one for good, once the window has taken the
    size), the windows enlarged, every key or click that went to it (none may), what was raised."""
    d = SimpleNamespace(rect=SMALL, enlarged=[], keys=[], raised=[], lowered=[], old=page(OLD_SIZE), frames=[],
                        asked=0, come=True)

    def capture(hwnd, **_):
        d.asked += 1
        if d.rect == SMALL or not d.frames:
            return d.old
        return d.frames.pop(0) if len(d.frames) > 1 else d.frames[0]

    def enlarge(hwnd):
        d.enlarged.append(hwnd)
        before, d.rect = d.rect, WORK
        return Enlarged(hwnd, before, WORK)

    for module in (live, reading, viewers):
        for name in ("press_key", "press_briefly", "post_key", "post_click", "with_foreground"):
            if hasattr(module, name):
                monkeypatch.setattr(module, name, lambda *a, _n=name, **k: d.keys.append((_n, a)))

    monkeypatch.setattr(live, "capture_window", capture)
    monkeypatch.setattr(live, "behind_others", lambda hwnd: True)
    monkeypatch.setattr(live, "raise_window", lambda hwnd: d.raised.append(hwnd) or Raised(hwnd, 0))
    monkeypatch.setattr(live, "lower_window", d.lowered.append)
    monkeypatch.setattr(live, "frames_come", lambda hwnd: d.come)
    monkeypatch.setattr(live, "window_rect", lambda hwnd: d.rect)
    monkeypatch.setattr(live, "window_exists", lambda hwnd: True)
    monkeypatch.setattr(live, "find_page_area", lambda image: None if is_blank(image) else
                        NEW_PANEL if image.size == NEW_SIZE else OLD_PANEL)
    monkeypatch.setattr(viewers, "enlarge_window", enlarge)
    monkeypatch.setattr(viewers, "window_rect", lambda hwnd: d.rect)
    monkeypatch.setattr(viewers, "window_shown", lambda hwnd: True)
    return d


def test_once_enlarged_the_new_frame_is_on_the_page_and_auto_goes_on_with_neither_window_in_front(tmp_path, desk):
    black, new = Image.new("RGB", NEW_SIZE, "black"), page(NEW_SIZE, 2)
    desk.frames = [black, black, new]
    w = Window(tmp_path)
    w.run(lambda: desk.enlarged)
    assert w._live is desk.old and tuple(w.settings.margins) == (637, 114, 637, 4)
    w.run(lambda: w.books)
    assert desk.enlarged == [HWND] and desk.keys == []
    assert w._live is new and w.shown[-1] is new  # never the black frame, and the old one no more
    assert black not in w.shown
    assert [(image, margins) for image, margins in w.books] == [(new, (579, 0, 579, 0))]  # the start dialog's turn
    assert w._area_large and w._following.owner == "other"


def test_a_resize_transition_never_says_the_viewer_does_not_draw(tmp_path, desk):
    desk.come = False  # (no frame has come of the new size yet, as at the moment of the change)
    black = Image.new("RGB", NEW_SIZE, "black")
    desk.frames = [black, black, black, page(NEW_SIZE, 2)]
    w = Window(tmp_path)
    w.run(lambda: w.books)
    assert desk.raised == [] and HELPED not in w.said and w._draws_covered(HWND) is None
    assert not w._covered
    w._raise_for_key(HWND)  # and no key raises it later
    assert desk.raised == []


def test_two_black_frames_are_no_window_that_has_settled(tmp_path, desk):
    black = Image.new("RGB", NEW_SIZE, "black")
    desk.frames = [black, black, black, black]
    w = Window(tmp_path)
    w.run(lambda: desk.enlarged)
    for _ in range(3):
        w._enlarge_wait()
    assert w._enlarging is not None  # it goes on waiting


def test_a_stale_frame_of_the_size_before_does_not_count(tmp_path, desk):
    new = page(NEW_SIZE, 2)
    desk.frames = [desk.old, desk.old, desk.old, new]
    w = Window(tmp_path)
    w.run(lambda: w.books)
    assert w._live is new and [image for image, _ in w.books] == [new]


def test_the_new_size_has_the_readers_own_area_for_it(tmp_path, desk, monkeypatch):
    monkeypatch.setattr(live, "page_panel", lambda image, hand=None: None)  # (no panel inside the reader's area)
    new = page(NEW_SIZE, 2)
    desk.frames = [new]
    w = Window(tmp_path)
    w.profiles.set_margins(w.selected, (0, 85, 0, 0), large=False)
    w.profiles.set_margins(w.selected, (500, 0, 500, 0), large=True)
    w._manual_area, w._hand_area = True, (0, 85, 0, 0)
    w.run(lambda: w.books)
    assert w._area_large and w._hand_area == (500, 0, 500, 0) and w._manual_area
    assert w.books[0][0] is new and tuple(w.settings.margins) == (500, 0, 500, 0)


def test_without_a_frame_of_the_new_size_the_old_area_goes_and_the_viewer_is_looked_at_until_one_comes(tmp_path, desk):
    black, new = Image.new("RGB", NEW_SIZE, "black"), page(NEW_SIZE, 2)
    desk.frames = [black] * 14 + [new]
    w = Window(tmp_path)
    w.run(lambda: desk.enlarged)
    w.run(lambda: w._enlarging is None)
    assert w._live is desk.old and tuple(w.settings.margins) == (0, 0, 0, 0) and w._following.unseen
    w.run(lambda: w.books)
    assert w._live is new and tuple(w.settings.margins) == (579, 0, 579, 0)


def test_with_follow_poll_the_new_frame_goes_on_the_page_as_well(tmp_path, desk):
    new = page(NEW_SIZE, 2)
    desk.frames = [new]
    w = Window(tmp_path, mode="poll")
    w._on_new_page(desk.old, thumbnail(desk.old))
    assert desk.enlarged == [HWND] and desk.keys == []
    w.run(lambda: w._enlarging is None)
    assert w._live is new


def test_another_size_goes_on_the_page_though_its_thumbnail_is_the_same(tmp_path, desk):
    w = Window(tmp_path)
    small, large = Image.new("RGB", (64, 64), (9, 9, 9)), Image.new("RGB", (128, 128), (9, 9, 9))
    w._show_live(small)
    w._show_live(large)
    assert w._live is large


# ------------------------------------------------------------------ when the raised look is concluded
def blank_window(tmp_path, desk, wait_ms):
    w = Window(tmp_path)
    w.settings.page_turn_wait_ms = wait_ms
    desk.old = Image.new("RGB", OLD_SIZE, "black")
    return w


def read(w):
    """A look at the viewer, as the window takes one: a look that fails is looked at again."""
    try:
        return w._capture(HWND)
    except CaptureError:
        return None


def test_a_frame_blank_only_for_a_moment_raises_nothing(tmp_path, desk):
    w = blank_window(tmp_path, desk, 60000)
    for _ in range(3):
        read(w)
    desk.old = page(OLD_SIZE)
    read(w)
    assert desk.raised == []


def test_a_frame_that_stays_blank_with_the_size_stable_is_looked_at_raised_and_that_is_concluded(tmp_path, desk):
    w = blank_window(tmp_path, desk, 0)
    read(w)  # it has just gone blank
    assert desk.raised == []
    read(w)
    assert desk.raised == [HWND]
    desk.old = page(OLD_SIZE)
    read(w)
    assert w.said == [HELPED] and w._draws_covered(HWND) is False
    assert w.profiles.covered_for(w.selected) is False  # kept: a later session raises it before each key at once


def test_a_change_of_the_windows_size_starts_the_wait_over(tmp_path, desk):
    w = blank_window(tmp_path, desk, 0)
    read(w)
    desk.rect = WORK
    desk.frames = [Image.new("RGB", NEW_SIZE, "black")]
    read(w)  # the reader's own full screen, say
    assert desk.raised == []


def test_a_new_size_while_it_is_raised_explains_the_new_frame(tmp_path, desk):
    w = blank_window(tmp_path, desk, 0)
    read(w)
    read(w)
    assert desk.raised == [HWND]
    desk.rect = WORK
    desk.frames = [page(NEW_SIZE, 2)]
    read(w)
    assert w.said == [] and w._draws_covered(HWND) is None
