"""The viewer the person chose kept directly under TASlation's window while TASlation is in front (`ui.order`,
`capture.keep_viewer_under`), with no activation, no key and no click - only the viewer's place in the order of the
windows -, and the status line for a viewer hidden wholly whose frames stand still. Every window here is made up: a
list of windows from the top down (`Desk`) stands in for Windows' order, and the window's side gets fakes for who is
in front; no real window is touched."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from taslation.capture import windows
from taslation.capture.windows import HWND_TOP, Placed, keep_viewer_under, windows_between
from taslation.ui import order

OWN, VIEWER, OTHER = 10, 20, 30
OWN_PID, VIEWER_PID, OTHER_PID = 1000, 2000, 3000
SCREEN = (0, 0, 1920, 1080)


class Desk:
    """Windows' order of the top-level windows, from the top down, with what each is (`Placed`); `place` moves a
    window as SetWindowPos does: directly after another, or to the top of the windows that are not topmost
    (HWND_TOP). Every move is noted, and every location change announced (`tell`)."""

    def __init__(self, *placed: Placed, minimised: tuple[int, ...] = (), refuse: bool = False):
        self.z = [p.hwnd for p in placed]
        self.of = {p.hwnd: p for p in placed}
        self.mins = set(minimised)
        self.refuse = refuse
        self.moves: list[tuple[int, int]] = []
        self.told: list[int] = []

    def root(self, hwnd: int) -> int:
        return hwnd if hwnd in self.of else 0

    def minimised(self, hwnd: int) -> bool:
        return hwnd in self.mins

    def topmost(self, hwnd: int) -> bool:
        return self.of[hwnd].topmost

    def below(self, hwnd: int) -> int:
        i = self.z.index(hwnd)
        return self.z[i + 1] if i + 1 < len(self.z) else 0

    def about(self, hwnd: int) -> Placed:
        return self.of[hwnd]

    def own_pid(self) -> int:
        return OWN_PID

    def place(self, hwnd: int, after: int) -> bool:
        self.moves.append((hwnd, after))
        if self.refuse:
            return False
        self.z.remove(hwnd)
        if after == HWND_TOP:
            at = next((i for i, h in enumerate(self.z) if not self.of[h].topmost), len(self.z))
        else:
            at = self.z.index(after) + 1
        self.z.insert(at, hwnd)
        return True

    def tell(self, hwnd: int) -> None:
        self.told.append(hwnd)


def own(**kw) -> Placed:
    return Placed(OWN, pid=OWN_PID, class_name="TkTopLevel", root_owner=OWN, rect=(0, 0, 1000, 800), **kw)


def viewer(**kw) -> Placed:
    return Placed(VIEWER, pid=VIEWER_PID, class_name="Chrome_WidgetWin_1", root_owner=VIEWER, rect=(100, 50, 1500, 1000),
                  **kw)


def other(hwnd: int = OTHER, rect=(200, 100, 1300, 900), **kw) -> Placed:
    kw.setdefault("pid", OTHER_PID)
    kw.setdefault("class_name", "Notepad")
    kw.setdefault("root_owner", hwnd)
    return Placed(hwnd, rect=rect, **kw)


# ------------------------------------------------------------------ Windows' side
def test_another_programs_window_between_has_the_viewer_put_directly_under_taslations_and_is_not_moved_itself():
    below = other(40, rect=(0, 0, 1920, 1080))
    desk = Desk(own(), other(), viewer(), below)
    between: list[int] = []
    assert keep_viewer_under(VIEWER, OWN, desk, between=between) == "placed" and between == [OTHER]
    assert desk.moves == [(VIEWER, OWN)]  # (the viewer alone, put after TASlation's window)
    assert desk.z == [OWN, VIEWER, OTHER, 40]  # (the window that lay between lies under it now, the rest as before)
    assert keep_viewer_under(VIEWER, OWN, desk) == "" and len(desk.moves) == 1  # (nothing between: nothing done)


def test_nothing_that_could_hide_the_viewer_between_the_two_leaves_the_order_as_it_is():
    hidden = other(31, shown=False)  # (hidden, minimised or cloaked)
    topmost = other(32, topmost=True)  # (stays above the viewer whatever is done)
    through = other(33, see_through=True)  # (click-through: hides nothing)
    popup = other(34, pid=VIEWER_PID, class_name="Chrome_WidgetWin_2", root_owner=VIEWER)  # (the viewer's own: moves with it)
    dialog = other(35, pid=OWN_PID, class_name="#32770", root_owner=OWN)  # (a dialog of TASlation's)
    panel = other(36, pid=OWN_PID, class_name="TkTopLevel")  # (a window Tk made in TASlation's process)
    aside = other(37, rect=(1500, 0, 1920, 40))  # (over none of the viewer)
    desk = Desk(own(), hidden, topmost, through, popup, dialog, panel, aside, viewer())
    assert windows_between(OWN, VIEWER, desk.below, desk.about, OWN_PID) == []
    assert keep_viewer_under(VIEWER, OWN, desk) == "" and desk.moves == []


def test_a_window_of_taslations_process_that_tk_did_not_make_counts_as_another_programs():
    """(the stand-in run's own cover lives in the window's process: `tools/standin_e2e.py --cover`)"""
    cover = other(38, pid=OWN_PID, class_name="StandinToolCover")
    desk = Desk(own(), cover, viewer())
    assert keep_viewer_under(VIEWER, OWN, desk) == "placed" and desk.z == [OWN, VIEWER, 38]


def test_under_a_topmost_taslation_the_viewer_goes_to_the_top_of_the_windows_not_topmost_never_above_it():
    """(Always on top, the full screen: put after a topmost window, the viewer would become topmost itself)"""
    always = other(50, topmost=True, rect=(0, 0, 300, 300))
    desk = Desk(own(topmost=True), always, other(), viewer())
    assert keep_viewer_under(VIEWER, OWN, desk) == "placed"
    assert desk.moves == [(VIEWER, HWND_TOP)]
    assert desk.z == [OWN, 50, VIEWER, OTHER]  # (under every topmost window, TASlation's first; over the other)


def test_why_nothing_is_done():
    assert keep_viewer_under(VIEWER, OWN, Desk(own(), other(), viewer(topmost=True))) == "topmost"
    assert keep_viewer_under(VIEWER, OWN, Desk(viewer(), own(), other())) == "above"  # (in front of TASlation's)
    assert keep_viewer_under(VIEWER, OWN, Desk(own(), other(), viewer(), minimised=(VIEWER,))) == "minimised"
    assert keep_viewer_under(VIEWER, OWN, Desk(own(), other(), viewer(), minimised=(OWN,))) == "minimised"
    assert keep_viewer_under(VIEWER, OWN, Desk(own(), other())) == "gone"
    refused = Desk(own(), other(), viewer(), refuse=True)  # (a viewer run as administrator, say)
    assert keep_viewer_under(VIEWER, OWN, refused) == "refused" and refused.z == [OWN, OTHER, VIEWER]
    assert refused.told == []  # (nothing moved: nothing announced)


def test_the_viewer_put_up_has_its_location_change_announced_once_so_a_browser_looks_at_its_occlusion_again():
    """(a browser's occlusion tracking looks again at a window event, not at a change of the order alone: on the
    stand-in, put over the window that hid it, it drew nothing until another program's window moved)"""
    desk = Desk(own(), other(), viewer())
    assert keep_viewer_under(VIEWER, OWN, desk) == "placed" and desk.told == [VIEWER]
    assert keep_viewer_under(VIEWER, OWN, desk) == "" and desk.told == [VIEWER]  # (nothing between: nothing more)
    above = Desk(viewer(), own(), other())
    assert keep_viewer_under(VIEWER, OWN, above) == "above" and above.told == []


def test_the_announcement_is_an_event_about_the_viewers_window_not_a_message_to_it(monkeypatch):
    calls: list[tuple] = []
    fake = SimpleNamespace(NotifyWinEvent=lambda *a: calls.append(a))
    monkeypatch.setattr(windows, "user32", fake)
    windows._Order().tell(VIEWER)
    assert calls == [(windows.EVENT_OBJECT_LOCATIONCHANGE, VIEWER, windows.OBJID_WINDOW, windows.CHILDID_SELF)]


def test_outside_windows_nothing_is_asked(monkeypatch):
    monkeypatch.setattr(windows, "IS_WINDOWS", False)
    assert keep_viewer_under(VIEWER, OWN) == "not windows"


def test_a_browser_is_hidden_wholly_for_its_rule_only_by_windows_that_hide_what_lies_under_them(monkeypatch):
    """(`capture.fully_covered` with *opaque*: TASlation's own window at WINDOW_ALPHA over all of it hides nothing so)"""
    order_ = {1: 2, 2: 3, 3: 0}
    rects = {2: (0, 0, 1920, 1080), 3: (0, 0, 1920, 1080)}
    opaque = {2: False, 3: False}
    fake = SimpleNamespace(IsWindow=lambda h: True, GetAncestor=lambda h, f: h, GetWindow=lambda h, f: order_[h],
                           IsWindowVisible=lambda h: True, IsIconic=lambda h: False, GetWindowLongW=lambda h, i: 0,
                           GetSystemMetrics=lambda i: {76: 0, 77: 0, 78: 1920, 79: 1080}[i])
    monkeypatch.setattr(windows, "IS_WINDOWS", True)
    monkeypatch.setattr(windows, "user32", fake, raising=False)
    monkeypatch.setattr(windows, "GWL_EXSTYLE", -20, raising=False)
    monkeypatch.setattr(windows, "client_rect_on_screen", lambda hwnd: (100, 100, 800, 600))
    monkeypatch.setattr(windows, "_is_cloaked", lambda hwnd: False)
    monkeypatch.setattr(windows, "_window_rect", lambda hwnd: rects[hwnd])
    monkeypatch.setattr(windows, "fully_opaque", lambda hwnd: opaque[hwnd])
    assert windows.fully_covered(1) and not windows.fully_covered(1, opaque=True)
    opaque[3] = True  # (another program's window under TASlation's, over all of the viewer)
    assert windows.fully_covered(1, opaque=True)
    rects[3] = (0, 0, 1920, 400)  # (a strip of the viewer in sight)
    assert not windows.fully_covered(1, opaque=True) and windows.fully_covered(1)


# ------------------------------------------------------------------ the window's side
@pytest.fixture
def front(monkeypatch):
    """Who is in front (``state["owner"]``) and what the order's capture call was asked (``state["asked"]``)."""
    state = {"owner": "own", "asked": [], "gives": "placed"}
    monkeypatch.setattr(order, "IS_WINDOWS", True)
    monkeypatch.setattr(order, "foreground_window", lambda: 99)
    monkeypatch.setattr(order, "foreground_owner", lambda hwnd, viewer: state["owner"])
    monkeypatch.setattr(order, "window_class", lambda hwnd: "Chrome_WidgetWin_1")  # (no real window asked)

    def keep(viewer_, own_, between=None):
        state["asked"].append((viewer_, own_))
        if between is not None and state["gives"] == "placed":
            between.append(OTHER)
        return state["gives"]

    monkeypatch.setattr(order, "keep_viewer_under", keep)
    return state


def _window(**kw) -> SimpleNamespace:
    w = SimpleNamespace(selected=SimpleNamespace(hwnd=VIEWER), _own_hwnd=lambda: OWN, _raised=None,
                        _resizing=lambda: False, said=[], lines=[], _status_key=None)
    w.say = lambda key: (w.said.append(key), setattr(w, "_status_key", key))
    w.status = lambda text: (w.lines.append(text), setattr(w, "_status_key", None))
    for k, v in kw.items():
        setattr(w, k, v)
    return w


def test_taslation_coming_to_the_front_has_the_order_looked_at_at_once_and_again_while_it_stays(front):
    w = _window()
    assert order.keep_under(w, 100.0) == "placed" and front["asked"] == [(VIEWER, OWN)]
    assert order.keep_under(w, 100.2) == ""  # (not again before ORDER_EVERY_S)
    front["gives"] = ""
    assert order.keep_under(w, 100.0 + order.ORDER_EVERY_S) == "" and len(front["asked"]) == 2  # (looked at again)
    assert order.state_of(w).placed == 1 and order.state_of(w).spells == 1


def test_nothing_is_done_while_another_program_or_the_viewer_is_in_front_and_a_new_spell_looks_at_once(front):
    w = _window()
    for owner in ("other", "viewer"):  # (the person went to another program, or to the viewer: the order is theirs)
        front["owner"] = owner
        for t in (100.0, 101.0, 102.0):
            assert order.keep_under(w, t) == ""
    assert front["asked"] == []
    front["owner"] = "own"  # (TASlation back in front)
    assert order.keep_under(w, 102.1) == "placed" and len(front["asked"]) == 1
    front["owner"] = "other"
    order.keep_under(w, 102.2)
    front["owner"] = "own"
    assert order.keep_under(w, 102.3) == "placed" and len(front["asked"]) == 2  # (a spell of its own: at once)
    assert order.state_of(w).spells == 2


def test_a_program_that_puts_its_window_back_between_at_once_is_not_fought(front):
    w = _window()
    t = 100.0
    for _ in range(order.ORDER_MOST + 3):
        order.keep_under(w, t)
        t += order.ORDER_EVERY_S
    assert len(front["asked"]) == order.ORDER_MOST  # (then left as it is for the spell: the status line says what is left)
    front["owner"] = "other"
    order.keep_under(w, t)
    front["owner"] = "own"
    assert order.keep_under(w, t + 0.1) == "placed" and len(front["asked"]) == order.ORDER_MOST + 1


def test_with_the_switch_off_a_window_over_a_part_of_the_viewer_stays_and_only_one_hiding_all_of_it_counts(
        front, monkeypatch):
    """(`order.PARTLY_COVERED_TOO` False: the way to show the owner, a window laid over a part of the viewer on
    purpose staying where the person put it)"""
    hidden = {"all": False}
    asked_opaque: list[bool] = []

    def covered(hwnd, opaque=False):
        asked_opaque.append(opaque)
        return hidden["all"]

    monkeypatch.setattr(order, "fully_covered", covered)
    monkeypatch.setattr(order, "PARTLY_COVERED_TOO", False)
    w = _window()
    assert order.keep_under(w, 100.0) == "partly" and front["asked"] == []  # (some of it in sight: left as it is)
    hidden["all"] = True
    assert order.keep_under(w, 100.5) == "placed" and front["asked"] == [(VIEWER, OWN)]
    assert set(asked_opaque) == {True}  # (by the windows that hide what lies under them: TASlation's own does not)
    monkeypatch.setattr(order, "PARTLY_COVERED_TOO", True)  # (the way built: any window between, asked at once)
    hidden["all"] = False
    assert order.keep_under(w, 101.0) == "placed" and len(asked_opaque) == 2


def test_the_log_names_the_kinds_of_window_that_went_under_the_viewer_and_no_title(front, monkeypatch, caplog):
    import logging

    monkeypatch.setattr(order, "window_class", lambda hwnd: {OTHER: "StandinToolCover"}.get(hwnd, "Chrome_WidgetWin_1"))
    with caplog.at_level(logging.INFO, logger=order.__name__):
        order.keep_under(_window(), 100.0)
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("window order: the viewer put"))
    assert line.endswith("now under it: StandinToolCover)")


def test_nothing_is_asked_while_the_viewer_is_raised_for_a_look_resized_or_not_chosen(front):
    assert order.keep_under(_window(_raised=object()), 100.0) == ""
    assert order.keep_under(_window(_resizing=lambda: True), 100.0) == ""
    assert order.keep_under(_window(selected=None), 100.0) == ""
    assert order.keep_under(_window(_own_hwnd=lambda: None), 100.0) == ""
    assert front["asked"] == []


def test_no_key_no_click_and_no_foreground_go_anywhere(front, monkeypatch):
    """Only the order's call is made: nothing that presses, posts, clicks or hands over the foreground."""
    from taslation.capture import windows as w_mod

    for name in ("press_briefly", "press_key", "post_key", "post_click", "give_foreground", "raise_window"):
        monkeypatch.setattr(w_mod, name, lambda *a, **k: pytest.fail("no key, click or foreground: " + name))
    w = _window()
    for t in (100.0, 100.5, 101.0):
        order.beat(w, t)
    assert front["asked"]


@pytest.fixture
def cover(monkeypatch):
    """The second measure's view of the viewer: hidden wholly or not (``state["hidden"]``, what *opaque* was asked
    with), its frame count (``state["count"]``) and its class."""
    state = {"hidden": True, "count": 5, "class": "Chrome_WidgetWin_1", "opaque": []}
    monkeypatch.setattr(order, "IS_WINDOWS", True)
    monkeypatch.setattr(order, "window_class", lambda hwnd: state["class"])

    def covered(hwnd, opaque=False):
        state["opaque"].append(opaque)
        return state["hidden"]

    monkeypatch.setattr(order, "fully_covered", covered)
    return state


def test_a_browser_hidden_wholly_whose_frames_stand_still_is_said_once_and_the_line_goes_with_the_spell(cover):
    w = _window(_frame_count=lambda: cover["count"])
    assert not order.covered_line(w, 100.0)  # (hidden from now on)
    assert not order.covered_line(w, 101.0) and not order.covered_line(w, 102.0)
    assert order.covered_line(w, 103.0) and w.said == [order.COVERED_KEY]  # (COVERED_STILL_S with no new frame)
    assert not order.covered_line(w, 104.0) and len(w.said) == 1  # (once in the spell)
    assert set(cover["opaque"]) == {True}  # (a browser: by the windows that hide what lies under them)
    cover["count"] = 6  # (a frame came: it draws)
    assert not order.covered_line(w, 105.0) and w.lines == [""]  # (the line taken back)
    for t in (106.0, 107.0, 108.0):
        order.covered_line(w, t)
    assert len(w.said) == 2  # (a spell of its own)
    cover["hidden"] = False
    order.covered_line(w, 109.0)
    assert w.lines == ["", ""]


def test_a_line_said_since_is_not_taken_back(cover):
    w = _window(_frame_count=lambda: cover["count"])
    for t in (100.0, 101.0, 102.0, 103.0):
        order.covered_line(w, t)
    w._status_key = "Something else the window said since"
    cover["hidden"] = False
    order.covered_line(w, 104.0)
    assert w.lines == []


def test_a_viewer_that_is_no_browser_is_said_only_once_seen_to_draw_nothing_while_covered(cover):
    cover["class"] = "TkTopLevel"
    seen = {"draws": None}
    w = _window(_frame_count=lambda: cover["count"], _draws_covered=lambda hwnd: seen["draws"])
    for t in (100.0, 101.0, 102.0, 103.0, 104.0):
        order.covered_line(w, t)
    assert w.said == []  # (not known yet: nothing said)
    seen["draws"] = True
    for t in (105.0, 106.0, 107.0, 108.0, 109.0):
        order.covered_line(w, t)
    assert w.said == []  # (it draws while covered)
    seen["draws"] = False
    for t in (110.0, 111.0, 112.0, 113.0, 114.0):
        order.covered_line(w, t)
    assert w.said == [order.COVERED_KEY] and cover["opaque"][-1] is False  # (by any window)


def test_nothing_is_said_while_taslations_own_covering_has_its_band_up(cover):
    """(`live.LiveViewMixin._set_covered`: the viewer draws nothing behind TASlation - its band and line say so)"""
    w = _window(_frame_count=lambda: cover["count"], _covered=True)
    for t in (100.0, 101.0, 102.0, 103.0, 104.0):
        order.covered_line(w, t)
    assert w.said == [] and cover["opaque"] == []


def test_without_a_frame_count_nothing_is_said(cover):
    w = _window(_frame_count=lambda: None)
    for t in (100.0, 101.0, 102.0, 103.0, 104.0):
        order.covered_line(w, t)
    assert w.said == []


def test_the_line_said_is_the_key_its_spell_takes_back():
    import inspect

    assert f'window.say("{order.COVERED_KEY}")' in inspect.getsource(order.covered_line)
