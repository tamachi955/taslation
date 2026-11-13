"""A viewer that stays black (`taslation.recovery`): it is only waited for, with nothing pressed and no capture made but
of a frame the session delivered; then the person is told, once and in plain words, to reload the book in its own
window, and TASlation goes on waiting - no key goes to the viewer, ever, in the window or in a batch. A black frame is
never read or cached. Stand-ins for the viewer: no window, no key."""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr, read_book
from PIL import Image, ImageDraw
from test_batch import FakeViewer

from taslation import batch as batch_mod
from taslation import capture, recovery
from taslation.batch import BatchReader
from taslation.cache import CacheStore
from taslation.capture import is_black, wgc
from taslation.config import ConfigError, Settings
from taslation.i18n import UI_LANGUAGES, _, set_language
from taslation.message_texts import catalog
from taslation.messages import Message, render
from taslation.pipeline import Pipeline
from taslation.recovery import GAVE_UP, LOADING, RECOVERED, BlackWatch
from taslation.translate import DictTranslator
from taslation.ui import jobs, live, reading, viewers
from taslation.ui.constants import VIEWER_BLACK, VIEWER_LOADING

HWND = 1
BLACK = Image.new("RGB", (640, 480), (0, 0, 0))
SENDERS = ("press_briefly", "press_key", "post_key", "post_click", "with_foreground", "click_screen")


def spinner(size=(640, 480)) -> Image.Image:
    img = Image.new("RGB", size, (0, 0, 0))
    ImageDraw.Draw(img).ellipse((size[0] // 2 - 16, size[1] // 2 - 16, size[0] // 2 + 16, size[1] // 2 + 16),
                                outline=(255, 255, 255), width=3)
    return img


class Screen:
    """What recovery could touch of a window: every key or click that would go to it, in order (none may), and the
    frames the capture session counted."""

    def __init__(self, monkeypatch):
        self.keys: list = []
        self.seq: int | None = 1
        for module in (capture, live, reading, viewers):
            for name in SENDERS:
                if hasattr(module, name):
                    monkeypatch.setattr(module, name, lambda *a, _n=name, **k: self.keys.append((_n, a)))
        monkeypatch.setattr(recovery, "frame_count", lambda hwnd: self.seq)


def run(watch: BlackWatch, seconds: float, *, black=True, size=(800, 600), start=0.0, step=1.0):
    """The spell looked at every *step* seconds from *start*: [(when, what happened)] of what did."""
    out = []
    t = start
    while t <= start + seconds:
        said = watch.step(black, size, t)
        if said:
            out.append((t, said))
        t += step
    return out


@pytest.fixture
def conf():
    return Settings()


# ------------------------------------------------------------------ what counts as black
@pytest.mark.parametrize("image, margins, expected", [
    (BLACK, (0, 0, 0, 0), True),
    (spinner(), (0, 0, 0, 0), True),  # the real case: a black page with a spinner, which is not one flat colour
    (Image.new("RGB", (640, 480), (24, 24, 28)), (0, 0, 0, 0), True),  # one dark colour
    (Image.new("RGB", (640, 480), (255, 255, 255)), (0, 0, 0, 0), False),  # a blank page of the book
    (Image.new("RGB", (640, 480), (120, 120, 120)), (0, 0, 0, 0), False),
])
def test_what_is_black(image, margins, expected):
    assert is_black(image, margins) is expected


def test_black_is_judged_over_the_capture_area():
    img = Image.new("RGB", (640, 480), (0, 0, 0))
    ImageDraw.Draw(img).rectangle((0, 0, 640, 84), fill=(240, 240, 240))  # the browser's bars
    assert not is_black(img)
    assert is_black(img, (0, 85, 0, 0))
    assert is_black(BLACK, (700, 700, 0, 0))  # margins that leave nothing: the whole frame


def test_a_dark_page_with_ink_on_it_is_no_black_frame():
    img = Image.new("RGB", (640, 480), (0, 0, 0))
    d = ImageDraw.Draw(img)
    for y in range(40, 440, 40):
        d.rectangle((60, y, 580, y + 14), fill=(255, 255, 255))
    assert not is_black(img)


# ------------------------------------------------------------------ the wait, then the notice
def test_nothing_is_pressed_during_the_wait_and_the_line_comes_once(conf, monkeypatch):
    screen = Screen(monkeypatch)
    watch = BlackWatch(HWND, conf, size=(800, 600), now=0.0)
    assert run(watch, 29) == [(8.0, LOADING)]
    assert screen.keys == []


def test_defaults_are_the_owners(conf):
    assert conf.black_wait_s == 30 and recovery.SAY_AFTER_S == 8


def test_after_the_wait_the_notice_comes_once_and_nothing_is_pressed(conf, monkeypatch):
    screen = Screen(monkeypatch)
    watch = BlackWatch(HWND, conf, size=(800, 600), now=0.0)
    assert run(watch, 600) == [(8.0, LOADING), (30.0, GAVE_UP)]  # said once, however long it stays black
    assert watch.told and screen.keys == []
    assert watch.step(False, (800, 600), 601.0) == RECOVERED  # the person reloaded it: the next frame ends it


def test_a_frame_that_recovers_during_the_wait_ends_it_silently(conf, monkeypatch):
    screen = Screen(monkeypatch)
    watch = BlackWatch(HWND, conf, size=(800, 600), now=0.0)
    assert run(watch, 4) == []
    assert watch.step(False, (800, 600), 5.0) == RECOVERED
    assert screen.keys == [] and not watch.said and not watch.told


def test_a_resize_starts_the_wait_over(conf, monkeypatch):
    screen = Screen(monkeypatch)
    watch = BlackWatch(HWND, conf, size=(800, 600), now=0.0)
    run(watch, 25)
    assert watch.step(True, (1000, 700), 26.0) == ""  # the size changed: frames of that say nothing
    assert run(watch, 28, start=27.0, size=(1000, 700)) == []  # (the line was said: a spell says it once)
    assert watch.step(True, (1000, 700), 56.0) == GAVE_UP
    assert screen.keys == []


def test_the_watch_has_no_key_to_press():
    assert not hasattr(recovery, "press_briefly") and not hasattr(recovery, "RELOADS")


# ------------------------------------------------------------------ no polling
def test_only_a_frame_the_session_delivered_is_there_to_judge(conf, monkeypatch):
    screen = Screen(monkeypatch)
    watch = BlackWatch(HWND, conf, size=(800, 600), now=0.0)
    assert not watch.new_frame(1.0) and not watch.new_frame(2.0) and not watch.new_frame(600.0)
    screen.seq = 2
    assert watch.new_frame(601.0) and not watch.new_frame(602.0)


def test_without_a_session_one_capture_every_two_seconds(conf, monkeypatch):
    screen = Screen(monkeypatch)
    screen.seq = None
    watch = BlackWatch(HWND, conf, size=(800, 600), now=0.0)
    looks = [t for t in range(1, 11) if watch.new_frame(float(t))]
    assert looks == [2, 4, 6, 8, 10]


def test_the_session_counts_its_frames_in_memory(monkeypatch):
    session = SimpleNamespace(hwnd=5, ended=False, has_frame=True, seq=7)
    monkeypatch.setattr(wgc, "_session", session)
    assert wgc.count(5) == 7 and capture.frame_count(5) == 7
    assert wgc.count(6) is None  # no session of that window, and none is started for the asking
    assert wgc._session is session
    session.ended = True
    assert wgc.count(5) is None
    session.ended, session.has_frame = False, False
    assert wgc.count(5) is None


# ------------------------------------------------------------------ settings
@pytest.mark.parametrize("value", [0, -1])
def test_settings_are_checked(value):
    with pytest.raises(ConfigError):
        Settings(black_wait_s=value).validate()


def test_the_reload_settings_of_old_still_load_and_do_nothing(tmp_path):
    path = tmp_path / "taslation.toml"
    path.write_text('reload_key = "F5"\nblack_reload_wait_s = 20\nblack_reload_gap_s = 300\nblack_reload_max = 2\n'
                    'fullscreen_key = "F11"\nblack_wait_s = 12\n', encoding="utf-8")
    settings = Settings.load(path)
    assert settings.black_wait_s == 12 and not hasattr(settings, "reload_key")
    assert not hasattr(settings, "fullscreen_key")


# ------------------------------------------------------------------ the texts
def test_the_window_lines_in_every_language():
    try:
        for lang in UI_LANGUAGES:
            set_language(lang)
            for key in (VIEWER_LOADING, VIEWER_BLACK):
                if lang != "en":
                    assert _(key) != key, (lang, key)
            assert "F5" in _(VIEWER_BLACK) and "TASlation" in _(VIEWER_BLACK)
    finally:
        set_language("en")


def test_the_batch_lines_in_every_language():
    for lang in UI_LANGUAGES:
        text = render(Message("batch.viewer_black"), catalog(lang))
        assert "TASlation" in text and "F5" in text and "{" not in text, lang


# ------------------------------------------------------------------ the batch
class Spell:
    """How the viewer goes black: at the frame after page *page* was left (the key that turned it arrives on black), it
    stays black until *cure* says so: None (never: the reader brings it back) or "wait" (by itself after *frames*)."""

    def __init__(self, page: int, cure: str | None, frames: int = 2):
        self.page, self.cure, self.frames = page, cure, frames


class BlackingViewer(FakeViewer):
    """A `FakeViewer` that goes black as a `Spell` says, as the reader turns to the page. Every capture counts."""

    def __init__(self, pages, spell: Spell, frame=None, screen: Screen | None = None):
        self.spell, self.frame = spell, frame if frame is not None else spinner(pages[0].size)
        self.black = False
        self.spent = False
        self.captures = 0
        self.screen = screen
        super().__init__(pages)

    @property
    def index(self):
        return self._index

    @index.setter
    def index(self, value):
        self._index = value
        if self.spell.page is not None and value == self.spell.page and not self.spent:
            self.black, self.spent = True, True

    def capture(self, hwnd):
        self.captures += 1
        if self.black:
            if self.spell.cure == "wait":
                self.spell.frames -= 1
                if self.spell.frames <= 0:
                    self.black = False
            if self.black:
                return self.frame
        return super().capture(hwnd)


def wire(viewer, settings, monkeypatch, screen):
    monkeypatch.setattr(batch_mod, "capture_window", viewer.capture)
    monkeypatch.setattr(batch_mod, "window_exists", lambda hwnd: True)
    monkeypatch.setattr(batch_mod, "window_rect", lambda hwnd: (0, 0, 800, 600))
    monkeypatch.setattr(batch_mod, "window_title", lambda hwnd: "Book - Browser")
    screen.seq = None  # no session: every look is a capture ...
    monkeypatch.setattr(recovery, "FALLBACK_LOOK_S", 0)
    monkeypatch.setattr(BlackWatch, "fallback_look_s", 0.0)  # ... and looks are as quick as the test
    monkeypatch.setattr(BlackWatch, "say_after_s", 0.02)
    monkeypatch.setattr(BlackWatch, "step_s", 0.005)
    settings.settle_ms = 5
    settings.page_turn_wait_ms = 60
    settings.black_wait_s = 0.05
    cache = CacheStore(settings.cache_dir).open("Book", "fake")
    return Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=cache), cache


def reader_for(pipeline, settings, **kwargs):
    said: list[str] = []
    kwargs.setdefault("context_mode", False)
    reader = BatchReader(pipeline, hwnd=HWND, settings=settings, on_progress=lambda p, r: said.append(p.message), title="Book - Browser", **kwargs)
    reader.viewer_class = "Chrome_WidgetWin_1"
    return reader, said


def codes(said) -> list[str]:
    return [getattr(m, "code", "") for m in said]


def in_hand(reader):
    thread = threading.Thread(target=reader.run, daemon=True)
    thread.start()
    return thread


def until(condition, seconds=10.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not condition():
        time.sleep(0.002)
    return condition()


def black_after_first_page(reader, viewer):
    """The first page is read, the reader turns, the viewer stays black, and the run says so."""
    assert until(lambda: reader.progress.pages == 1)
    viewer.index = 1
    assert until(lambda: getattr(reader.progress.waiting, "code", "") == "batch.viewer_black")


def test_a_batch_waits_out_a_slow_page_and_presses_nothing(sample_page, sample_page2, settings, monkeypatch):
    screen = Screen(monkeypatch)
    viewer = BlackingViewer([sample_page, sample_page2], Spell(1, "wait", frames=2), screen=screen)
    pipeline, cache = wire(viewer, settings, monkeypatch, screen)
    reader, said = reader_for(pipeline, settings)
    p = read_book(reader, viewer)
    assert p.pages == 2 and len(cache) == 2
    assert p.reason == Message("batch.finished_reading")
    assert screen.keys == [] and "batch.viewer_black" not in codes(said)


def test_a_black_viewer_is_said_and_the_run_waits_for_the_reader_with_no_key(sample_page, sample_page2, settings, monkeypatch):
    screen = Screen(monkeypatch)
    viewer = BlackingViewer([sample_page, sample_page2], Spell(1, None), screen=screen)
    pipeline, cache = wire(viewer, settings, monkeypatch, screen)
    reader, said = reader_for(pipeline, settings)
    thread = in_hand(reader)
    black_after_first_page(reader, viewer)
    time.sleep(0.1)
    assert thread.is_alive() and screen.keys == []
    assert "batch.viewer_loading" in codes(said)
    assert len(cache) == 1  # the page done is kept; the black frame is not in it
    viewer.black = False  # the reader brought it back
    assert until(lambda: reader.progress.pages == 2)
    assert reader.progress.waiting is None
    reader.finish()
    thread.join(10)
    assert reader.progress.reason == Message("batch.finished_reading") and screen.keys == []


def test_a_flat_black_viewer_is_waited_for_too(sample_page, sample_page2, settings, monkeypatch):
    screen = Screen(monkeypatch)
    black = Image.new("RGB", sample_page.size, (0, 0, 0))
    viewer = BlackingViewer([sample_page, sample_page2], Spell(1, None), frame=black, screen=screen)
    pipeline, cache = wire(viewer, settings, monkeypatch, screen)
    monkeypatch.setattr(batch_mod, "behind_others", lambda hwnd: False)
    reader, _said = reader_for(pipeline, settings)
    thread = in_hand(reader)
    black_after_first_page(reader, viewer)
    reader.stop()
    thread.join(10)
    assert len(cache) == 1 and screen.keys == []


def test_black_from_the_start_and_finished_reading_says_no_page_was_seen(sample_page, sample_page2, settings, monkeypatch):
    screen = Screen(monkeypatch)
    viewer = BlackingViewer([sample_page, sample_page2], Spell(None, None), screen=screen)
    viewer.black = True
    pipeline, cache = wire(viewer, settings, monkeypatch, screen)
    reader, _said = reader_for(pipeline, settings)
    thread = in_hand(reader)
    assert until(lambda: getattr(reader.progress.waiting, "code", "") == "batch.viewer_black")
    reader.finish()
    thread.join(10)
    p = reader.progress
    assert p.pages == 0 and len(cache) == 0 and p.reason == Message("batch.no_page_seen") and screen.keys == []


def test_finished_reading_while_black_goes_on_to_the_translation(sample_page, sample_page2, settings, monkeypatch):
    screen = Screen(monkeypatch)
    viewer = BlackingViewer([sample_page, sample_page2], Spell(1, None), screen=screen)
    pipeline, cache = wire(viewer, settings, monkeypatch, screen)
    pipeline.translator = translator = DictTranslator(EN_TEXTS)
    reader, _said = reader_for(pipeline, settings, context_mode=True, book="Book")
    thread = in_hand(reader)
    black_after_first_page(reader, viewer)
    reader.finish()
    thread.join(20)
    p = reader.progress
    assert p.pages == 1 and p.reason == Message("batch.finished_reading") and p.phase == "done"
    assert translator.calls and p.checked > 0 and screen.keys == []
    assert p.summary.code == "batch.finished"


def test_a_stop_while_black_ends_the_run_with_nothing_translated(sample_page, sample_page2, settings, monkeypatch):
    screen = Screen(monkeypatch)
    viewer = BlackingViewer([sample_page, sample_page2], Spell(1, None), screen=screen)
    pipeline, cache = wire(viewer, settings, monkeypatch, screen)
    pipeline.translator = translator = DictTranslator(EN_TEXTS)
    reader, _said = reader_for(pipeline, settings, context_mode=True)
    thread = in_hand(reader)
    black_after_first_page(reader, viewer)
    reader.stop()
    thread.join(10)
    assert reader.progress.summary.code == "batch.stopped_reading" and translator.calls == [] and len(cache) == 0


def test_no_capture_while_no_frame_comes(sample_page, sample_page2, settings, monkeypatch):
    screen = Screen(monkeypatch)
    viewer = BlackingViewer([sample_page, sample_page2], Spell(1, None), screen=screen)
    pipeline, _cache = wire(viewer, settings, monkeypatch, screen)
    screen.seq = 1  # a session, whose counter stands still: the viewer shows the same black frame
    monkeypatch.setattr(recovery, "frame_count", lambda hwnd: 1)
    settings.black_wait_s = 0.15
    reader, _said = reader_for(pipeline, settings)
    seen: list[int] = []
    original = reader._through_black

    def through(image):
        seen.append(viewer.captures)
        return original(image)

    reader._through_black = through
    read_book(reader, viewer, patience_s=0.5)
    assert len(seen) == 1 and viewer.captures == seen[0]


# ------------------------------------------------------------------ the window
class Window(live.LiveViewMixin):
    """The parts of the window a spell goes through; time and the viewer are the test's."""

    def __init__(self, settings):
        self.settings = settings
        self.selected = SimpleNamespace(hwnd=HWND, title="Book - Browser")
        self.reading = False
        self.batch = None
        self._batching = False
        self.busy = False
        self._enlarged = None
        self._enlarging = None
        self.lines: list[str] = []
        self.pages: list[Image.Image] = []
        self.found = 0
        self.afresh = 0
        self.ticks = 0
        self._status_key = None
        self._following = SimpleNamespace(mode="poll", owner="own")

    def say(self, key, **values):
        self.lines.append(key)
        self._status_key = key

    def _normal_status(self):
        self.lines.append("normal")

    def _covers_viewer(self, hwnd):
        return False

    def _set_covered(self, covered):
        pass

    def _find_page(self, image):
        self.found += 1

    def _sync_area(self):
        pass

    def _apply_found_margins(self):
        pass

    def _look_afresh(self, frame=None, thumb=None):
        self.afresh += 1

    def _book_in_front(self):
        return True

    def _tick(self):
        self.ticks += 1


class Clock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now


@pytest.fixture
def stage(monkeypatch):
    screen = Screen(monkeypatch)
    clock = Clock()
    state = SimpleNamespace(screen=screen, clock=clock, frame=spinner(), captures=0)

    def grab(hwnd, allow_screen_fallback=True):
        state.captures += 1
        return state.frame

    monkeypatch.setattr(live, "capture_window", grab)
    monkeypatch.setattr(live, "window_exists", lambda hwnd: True)
    monkeypatch.setattr(live, "window_rect", lambda hwnd: (0, 0, 800, 600))
    monkeypatch.setattr(live, "time", SimpleNamespace(monotonic=clock.monotonic))
    monkeypatch.setattr(recovery, "time", SimpleNamespace(monotonic=clock.monotonic))
    return state


def beats(window, state, seconds, step=0.5):
    for _i in range(int(seconds / step)):
        state.clock.now += step
        window._beat()


def test_the_window_waits_with_no_capture_and_says_so_once(settings, stage):
    window = Window(settings)
    window._capture(HWND)
    assert window._black_open() and window.found == 0  # a black frame: no page looked for in it
    stage.captures = 0
    beats(window, stage, 29)
    assert stage.captures == 0 and stage.screen.keys == []  # no frame came: nothing was taken
    assert window.lines == [VIEWER_LOADING] and window.ticks == 0  # and no other look either


def test_the_window_judges_only_a_frame_the_session_delivered(settings, stage):
    window = Window(settings)
    window._capture(HWND)
    stage.captures = 0
    stage.screen.seq = 2
    beats(window, stage, 3)
    assert stage.captures == 1


def test_the_window_uses_one_capture_every_two_seconds_on_the_fallback(settings, stage):
    stage.screen.seq = None
    window = Window(settings)
    window._capture(HWND)
    stage.captures = 0
    beats(window, stage, 10)
    assert stage.captures in (4, 5)  # (every 2 s of the heartbeat's steps)


def test_recovery_during_the_wait_is_silent(settings, stage, sample_page):
    window = Window(settings)
    window._capture(HWND)
    beats(window, stage, 3)
    stage.frame, stage.screen.seq = sample_page, 2
    beats(window, stage, 2)
    assert not window._black_open() and window.lines == [] and stage.screen.keys == []
    assert window.found == 1  # the page is a page again
    assert window.ticks > 0  # the usual looks are back


def test_the_loading_line_goes_when_the_frame_comes(settings, stage, sample_page):
    window = Window(settings)
    window._capture(HWND)
    beats(window, stage, 10)
    stage.frame, stage.screen.seq = sample_page, 2
    beats(window, stage, 2)
    assert window.lines == [VIEWER_LOADING, "normal"]


def test_the_window_tells_the_person_to_reload_once_and_presses_nothing(settings, stage, sample_page):
    window = Window(settings)
    window._capture(HWND)
    beats(window, stage, 120)
    assert stage.screen.keys == []
    assert window.lines == [VIEWER_LOADING, VIEWER_BLACK]
    stage.frame, stage.screen.seq = sample_page, 2  # the person reloaded the book in its window
    beats(window, stage, 2)
    assert not window._black_open() and window.lines[-1] == "normal"
    assert window.afresh == 1  # the page is taken as the viewer shows it now
    assert stage.screen.keys == []


def test_no_spell_while_taslation_gives_the_window_a_new_size(settings, stage):
    window = Window(settings)
    window._enlarging = {"enlarged": object()}
    window._capture(HWND)
    assert not window._black_open()


def test_a_size_given_meanwhile_ends_the_spell(settings, stage):
    window = Window(settings)
    window._capture(HWND)
    window._enlarging = {"enlarged": object()}
    window._capture(HWND)
    assert not window._black_open()


def test_nothing_is_pressed_while_the_reader_is_in_another_program(settings, stage):
    window = Window(settings)
    window._following = SimpleNamespace(mode="events", owner="other", events=MagicMock(take=lambda: []), look_at=None,
                                        op=None, last_poll=0.0, unseen=False, last_input=0)
    window._capture(HWND)
    beats(window, stage, 40)
    window._following.owner = "own"
    beats(window, stage, 40)
    assert stage.screen.keys == [] and window.lines == [VIEWER_LOADING, VIEWER_BLACK]


def test_another_tab_ends_the_spell_with_no_key(settings, stage):
    window = Window(settings)
    window._capture(HWND)
    beats(window, stage, 10)
    window._book_in_front = lambda: False
    beats(window, stage, 40)
    assert not window._black_open() and stage.screen.keys == []


def test_a_batch_takes_over_from_the_window(settings, stage):
    window = Window(settings)
    window._capture(HWND)
    window.batch = object()
    beats(window, stage, 40)
    assert not window._black_open() and stage.screen.keys == []


def test_a_black_frame_is_never_started(settings):
    window = MagicMock(settings=settings)
    window._black_watch = None
    jobs.JobsMixin._start_translate(window, spinner())
    window._go_busy.assert_not_called()
    window.say.assert_called_once_with(VIEWER_LOADING)
    assert np.asarray(spinner()).mean() < 5
