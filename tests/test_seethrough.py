"""See-through mode's pure parts (`taslation.seethrough`): the patches and the rule that a patch shows only over the
pixels it was made from, the window's picture, and what tells another page from bars over it and from a frame to
wait out. Synthetic frames only."""

from types import SimpleNamespace

import numpy as np
import pytest

from taslation import seethrough as st
from taslation.config import Settings
from taslation.frames import frames_differ

W, H = 400, 300


def page(seed=1, ground=0, box=(100, 0, 300, 300)):
    """A frame: a ground of one grey level, a 'page' of noise and strokes in *box*."""
    rng = np.random.default_rng(seed)
    frame = np.full((H, W, 3), ground, np.uint8)
    left, top, right, bottom = box
    art = rng.integers(60, 250, (bottom - top, right - left, 1), dtype=np.uint8).repeat(3, axis=2)
    frame[top:bottom, left:right] = art
    return frame


def lettered(frame, boxes):
    out = frame.copy()
    for left, top, right, bottom in boxes:
        out[top:bottom, left:right] = 255
        out[top + 4:top + 7, left + 4:right - 4] = 0  # a line of 'lettering'
    return out


def bgra(rgb):
    out = np.zeros((*rgb.shape[:2], 4), np.uint8)
    out[..., :3] = rgb[..., ::-1]
    out[..., 3] = 255
    return out


# ------------------------------------------------------------------ the patches
def test_a_patch_per_bubble_opaque_where_the_page_was_lettered_only():
    frame = page()
    done = lettered(frame, [(120, 20, 170, 60), (220, 200, 280, 240)])
    patches = st.make_patches(frame, done)
    assert [p.box for p in patches] == [(120, 20, 170, 60), (220, 200, 280, 240)]
    p = patches[0]
    assert p.bgra.shape == (40, 50, 4) and p.bgra[..., 3].min() == 255  # (all of the box was lettered here)
    assert tuple(p.bgra[5, 10, :3]) == (0, 0, 0) and tuple(p.bgra[0, 0, :3]) == (255, 255, 255)
    assert p.near == (114, 14, 176, 66) and p.source.shape == (26, 31, 3)


def test_letters_close_together_are_one_patch_and_a_stray_pixel_none():
    frame = page()
    done = frame.copy()
    done[50:60, 150:160] = 255 - done[50:60, 150:160]
    done[50:60, 165:175] = 255 - done[50:60, 165:175]  # 5 px apart: one bubble
    done[250, 120] = 255 - done[250, 120]  # one pixel: no patch
    assert [p.box for p in st.make_patches(frame, done)] == [(150, 50, 175, 60)]


def test_a_patch_shows_over_its_own_pixels_and_goes_when_they_change():
    frame = page()
    patch = st.make_patches(frame, lettered(frame, [(120, 20, 170, 60)]))[0]
    assert st.changed_share(patch, bgra(frame)) == 0.0 and st.patch_matches(patch, bgra(frame))
    turned = page(seed=2)
    assert not st.patch_matches(patch, bgra(turned))  # another page under it
    barred = frame.copy()
    barred[0:30] = 40  # a bar over its top
    assert not st.patch_matches(patch, bgra(barred))
    elsewhere = frame.copy()
    elsewhere[200:300] = 0  # a change far from it
    assert st.patch_matches(patch, bgra(elsewhere))
    margin = frame.copy()
    margin[62:65, 130:140] = 255 - margin[62:65, 130:140]  # within MARGIN below it
    assert not st.patch_matches(patch, bgra(margin))
    assert st.changed_share(patch, bgra(frame[:50])) == 1.0  # (a frame that does not hold its place)


def test_a_few_pixels_off_keep_it_and_a_soft_picture_does_not():
    frame = page()
    patch = st.make_patches(frame, lettered(frame, [(120, 20, 170, 60)]))[0]
    noisy = frame.astype(np.int16) + 20  # every pixel off by less than PIXEL_TOL
    assert st.patch_matches(patch, bgra(np.clip(noisy, 0, 255).astype(np.uint8)))
    import cv2

    soft = cv2.GaussianBlur(frame, (9, 9), 3)  # the page drawn soft: another picture under the patch
    assert st.changed_share(patch, bgra(soft)) > st.CHANGED_SHARE


def test_the_newest_set_that_matches_shows_the_patches_that_match():
    store = st.SetStore()
    old, new = page(1), page(2)
    a = st.make_patches(old, lettered(old, [(120, 20, 170, 60)]))
    b = st.make_patches(new, lettered(new, [(120, 20, 170, 60), (200, 200, 260, 240)]))
    store.put(1, (W, H), a)
    store.put(2, (W, H), b)
    chosen, shown, _ = st.visible(store.sets, bgra(new))
    assert chosen.key == 2 and shown == (0, 1)
    chosen, shown, _ = st.visible(store.sets, bgra(old))  # turned back: the old page's patches at once
    assert chosen.key == 1 and shown == (0,)
    half = new.copy()
    half[180:] = 0
    chosen, shown, _ = st.visible(store.sets, bgra(half))
    assert chosen.key == 2 and shown == (0,)
    assert st.visible(store.sets, bgra(page(3)))[0] is None
    assert st.visible(store.sets, bgra(new[:200]))[0] is None  # (another size: none)


def test_a_set_put_again_replaces_its_own_and_only_so_many_are_kept():
    store = st.SetStore()
    for key in range(5):
        store.put(key, (W, H), ())
    assert [s.key for s in store.sets] == [4, 3, 2]
    store.put(3, (W, H), (), final=True)
    assert [s.key for s in store.sets] == [3, 4, 2] and store.sets[0].final
    store.drop(4)
    assert [s.key for s in store.sets] == [3, 2]


def test_the_picture_is_transparent_but_for_the_patches_shown():
    frame = page()
    patches = st.make_patches(frame, lettered(frame, [(120, 20, 170, 60), (220, 200, 280, 240)]))
    out = st.compose((W, H), [patches[1]])
    assert out.shape == (H, W, 4) and out[..., 3].sum() == 255 * 60 * 40
    assert out[:100].max() == 0 and out[210, 230, 3] == 255
    again = st.compose((W, H), [patches[0]], out)  # (into the same buffer: the last picture gone)
    assert again is out and out[210, 230, 3] == 0 and out[30, 130, 3] == 255


def test_a_window_over_the_viewer_leaves_the_patches_it_meets_out():
    box = (120, 20, 170, 60)
    assert st.covered(box, (1000, 500), [(1100, 500, 1200, 600)])
    assert not st.covered(box, (1000, 500), [(1170, 500, 1200, 600)])  # (only touching)
    assert not st.covered(box, (0, 0), [])


# ------------------------------------------------------------------ another page, or bars over it
def test_bars_over_the_top_and_bottom_leave_the_steady_part_as_it_was_and_a_turn_does_not():
    frame = page()
    barred = frame.copy()
    barred[:40] = 255
    barred[270:] = 230
    box = (100, 0, 300, 300)
    assert not frames_differ(st.steady_thumb(frame, box), st.steady_thumb(barred, box))
    assert frames_differ(st.steady_thumb(frame, box), st.steady_thumb(page(seed=2), box))
    assert st.steady_box((W, H), box) == (100, 45, 300, 264)


@pytest.mark.parametrize("ground", [0, 255, 30])
def test_the_page_is_found_on_a_ground_of_any_colour(ground):
    frame = page(ground=ground, box=(100, 0, 300, 300))
    assert st.ground_box(frame) == (100, 0, 300, 300)
    barred = frame.copy()
    barred[:40] = 128  # a bar across all of it
    barred[280:] = 90
    assert st.ground_box(barred) == (100, 0, 300, 300)
    assert st.bands(barred, (100, 0, 300, 300)) == [(0, 40), (280, 300)]
    assert st.bands(frame, (100, 0, 300, 300)) == []


def test_no_page_box_without_a_ground_or_with_too_little_of_it():
    rng = np.random.default_rng(3)
    assert st.ground_box(rng.integers(0, 255, (H, W, 3), dtype=np.uint8)) is None
    assert st.ground_box(page(box=(2, 0, 398, 300))) is None  # (no ground at the sides)
    assert st.ground_box(page(box=(195, 0, 205, 300))) is None  # (no page's shape)


def test_frames_to_wait_out():
    frame = page()
    assert st.loading_kind(frame, (100, 0, 300, 300)) is None
    black = np.zeros_like(frame)
    black[140:160, 190:210] = 230  # a spinner
    assert st.loading_kind(black) == "black"
    half = frame.copy()
    half[:, 100:200] = 0
    assert st.loading_kind(half, (100, 0, 300, 300)) == "half"
    assert st.loading_kind(frame, (200, 0, 300, 300), before=(100, 0, 300, 300)) == "half"
    assert not st.half_of((150, 0, 250, 300), (100, 0, 300, 300))  # (a single page is centred)
    washed = (frame.astype(np.float32) * 0.3 + 160).astype(np.uint8)
    assert st.loading_kind(washed, (100, 0, 300, 300)) == "washed"


def test_one_look_finds_it_all_on_every_fourth_pixel_and_bars_are_painted_over():
    frame = page(ground=255, box=(100, 0, 300, 300))
    frame[:40] = 70
    found = st.look(frame)
    assert found.box == (100, 0, 300, 300) and found.bands == ((0, 40),) and found.kind is None
    assert found.ground == (255, 255, 255)
    clean = st.masked(frame, found.bands, found.ground)
    assert clean[:40].min() == 255 and np.array_equal(clean[40:], frame[40:])


def test_the_setting_is_off_by_default():
    assert Settings().see_through is False


# ------------------------------------------------------------------ the window's side (no window)
class Facts:
    """A frame's facts as the window keeps them (`ui.live.FrameFacts`: its pixels, a memo)."""

    def __init__(self, image):
        self.image, self.memo = image, {}

    def rgb(self):
        return np.asarray(self.image)

    def get(self, key, make):
        if key not in self.memo:
            self.memo[key] = make()
        return self.memo[key]


def see_app():
    return SimpleNamespace(_see_bars_since=None, _see_rest_box=None, _manual_area=False, after=lambda *a: None,
                           _see_through=object())


def test_the_steady_part_has_the_page_columns_and_the_area_rows_so_bars_never_move_it():
    from taslation.ui import seethrough as ui
    from PIL import Image

    frame = page(ground=0, box=(100, 0, 300, 300))
    frame[:36, 100:300] = 0  # a dark page's top on a dark ground: its box starts lower than the page
    assert st.ground_box(frame)[1] == 36
    barred = frame.copy()
    barred[:40] = 200  # bars over the top and the bottom: the box goes to the frame's edges
    barred[270:] = 90
    assert st.ground_box(barred) == (100, 0, 300, 300)
    app = see_app()
    plain, bars = Image.fromarray(frame), Image.fromarray(barred)
    fp, fb = Facts(plain), Facts(bars)
    assert ui.steady_area(app, plain, fp) == ui.steady_area(app, bars, fb) == (100, 0, 300, 300)
    app._see_bars_since = -1e9  # (the bars have stayed long enough to be read)
    assert not frames_differ(ui.thumb(app, plain, fp), ui.thumb(app, bars, fb))
    other = Image.fromarray(page(seed=2))
    assert frames_differ(ui.thumb(app, plain, fp), ui.thumb(app, other, Facts(other)))


def test_frames_with_bars_wait_until_they_have_stayed(monkeypatch):
    from taslation.ui import seethrough as ui
    from PIL import Image

    app = see_app()
    frame = page(ground=0, box=(100, 0, 300, 300))
    barred = frame.copy()
    barred[:40] = 200

    clock = [100.0]
    monkeypatch.setattr(ui.time, "monotonic", lambda: clock[0])
    plain, bars = Image.fromarray(frame), Image.fromarray(barred)
    fp, fb = Facts(plain), Facts(bars)
    ui.note_frame(app, plain, fp)
    assert app._see_rest_box == (100, 0, 300, 300) and not ui.waits(app, plain, fp)
    ui.note_frame(app, bars, fb)
    assert ui.waits(app, bars, fb) and ui.thumb(app, bars, fb).max() == 0  # (nothing drawn, for now)
    assert ui.reading_frame(app, bars, fb) is bars  # (nor anything read of it: it is not painted over yet)
    assert ui.detail_box(app, bars, fb, (0, 0, W, H)) == st.steady_box((W, H), (100, 0, 300, 300))
    clock[0] += ui.BAR_WAIT_S
    assert not ui.waits(app, bars, fb)
    read = ui.reading_frame(app, bars, fb)
    assert np.asarray(read)[:40].max() == 0  # the bars painted in the ground's colour
    assert not frames_differ(ui.thumb(app, bars, fb), ui.thumb(app, plain, fp))  # the same page
    fr = Facts(read)  # (facts made anew, as once the window has let go of the frame's: the look goes with the frame)
    assert ui.frame_look(app, read, fr) == ui.painted_look(app, bars, fb) == st.Look((100, 0, 300, 300), (), None,
                                                                                    (0, 0, 0))
    ui.note_frame(app, plain, fp)  # the bars gone
    assert app._see_bars_since is None and ui.waits(app, bars, fb)
    assert not ui.waits(app, read, fr) and not frames_differ(ui.thumb(app, read, fr), ui.thumb(app, plain, fp))
    # the page read under the bars is read once more now they have gone (its lines read before: from the cache)
    app._shows_page = lambda image, frame: True
    cut = SimpleNamespace(bbox=(120, 40, 170, 80))  # (a bubble read from the bar's edge down: cut by it)
    whole = SimpleNamespace(bbox=(120, 120, 170, 160))
    app.last_result = SimpleNamespace(original=read, regions=[whole, cut])
    assert ui.read_under_bars(app, plain) and not ui.read_under_bars(app, read)  # (not while they are there)
    app.last_result = SimpleNamespace(original=read, regions=[whole])  # nothing near the bars: nothing more
    assert not ui.read_under_bars(app, plain)
    app.last_result = SimpleNamespace(original=plain, regions=[whole, cut])  # read once more: never again
    assert not ui.read_under_bars(app, plain)
    app._shows_page = lambda image, frame: False  # another page
    app.last_result = SimpleNamespace(original=read, regions=[whole, cut])
    assert not ui.read_under_bars(app, plain)


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows only")
def test_the_window_is_click_through_never_activated_and_shows_nothing_until_it_has_a_viewer():
    import ctypes

    from taslation.capture import seethrough as window

    over = window.SeeThrough.start()
    assert over is not None
    try:
        user32 = ctypes.WinDLL("user32")
        user32.GetWindowLongW.restype = ctypes.c_long
        style = user32.GetWindowLongW(over.hwnd, -20) & 0xFFFFFFFF
        for flag in (window.WS_EX_LAYERED, window.WS_EX_TRANSPARENT, window.WS_EX_NOACTIVATE, window.WS_EX_TOPMOST,
                     window.WS_EX_TOOLWINDOW):
            assert style & flag
        assert not user32.IsWindowVisible(over.hwnd)
        over.present(1, (W, H), ())
        over.set_on(False)
        over.set_on(True)
        assert over.shown() is None and [n["ev"] for n in over.notes][:3] == ["present", "on", "on"]
    finally:
        over.close()
    assert over.hwnd == 0


# ------------------------------------------------------------------ nothing goes to the viewer, nothing takes the front
def test_in_see_through_mode_no_key_and_no_click_is_passed_on_to_the_viewer(monkeypatch):
    from taslation.ui import reading, translator

    sent = []
    for module, names in ((reading, ("post_key", "press_briefly")), (translator, ("post_click",))):
        for name in names:
            monkeypatch.setattr(module, name, lambda *a, _n=name, **k: sent.append(_n))
    app = SimpleNamespace(_see_through=object())  # (nothing else: a path past the first line would fail here)
    reading.ReadingMixin.forward_key(app, "Left")
    translator.TranslatorMixin._forward_click(app, SimpleNamespace(x=10, y=10))
    assert sent == []


def test_the_quiet_start_makes_a_decoy_first_window_only_in_see_through_mode_and_drops_it(monkeypatch):
    from taslation.ui import seethrough as ui

    made = []

    class Widget:
        def __init__(self, master, **options):
            self.options = options
            made.append(self)

        def winfo_id(self):
            return 4242

        def destroy(self):
            made.append(("gone", type(self).__name__))

    class Frame(Widget):
        pass

    class Toplevel(Widget):
        pass

    monkeypatch.setattr(ui.tk, "Frame", Frame)
    monkeypatch.setattr(ui.tk, "Toplevel", Toplevel)
    monkeypatch.setattr(ui.window, "IS_WINDOWS", True)
    later = []
    app = SimpleNamespace(after=lambda ms, f: later.append((ms, f)))
    ui.quiet_start(app, Settings())
    assert made == [] and not ui.quiet(app)
    ui.quiet_started(app)
    assert later == []
    ui.quiet_start(app, Settings(see_through=True))
    box, decoy = made
    # the first top-level window Tk makes is one inside a frame of the window's own: a child window, never activated
    assert box.options == {"container": True} and decoy.options == {"use": "4242"}
    assert ui.quiet(app)  # (not maximised at the start then)
    ui.quiet_started(app)
    (ms, drop), = later
    assert ms == ui.QUIET_MS
    drop()
    assert made[2:] == [("gone", "Toplevel"), ("gone", "Frame")] and not ui.quiet(app)
    ui.quiet_start(app, Settings(see_through=True))
    ui.quiet_end(app)  # (the legal notice: the reader's to answer)
    assert not ui.quiet(app)