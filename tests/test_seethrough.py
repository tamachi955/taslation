"""See-through mode's pure parts (`taslation.seethrough`): the patches and the rule that a page's patches show whole
while the viewer's frame is that page (its sign), but under a bar of the viewer's; the window's picture, and what
tells another page from bars over it, a strip along the area's edge and a frame to wait out. Synthetic frames only."""

from dataclasses import replace
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


def art(seed=1, ground=0, box=(100, 0, 300, 300)):
    """A frame: a ground of one grey level, a 'page' of flat grey blocks 40 px a side in *box* (as a page's picture,
    drawn soft it stays near itself)."""
    import cv2

    rng = np.random.default_rng(seed)
    frame = np.full((H, W, 3), ground, np.uint8)
    left, top, right, bottom = box
    coarse = rng.integers(60, 250, ((bottom - top) // 40 + 1, (right - left) // 40 + 1), dtype=np.uint8)
    big = cv2.resize(coarse, (right - left, bottom - top), interpolation=cv2.INTER_NEAREST)
    frame[top:bottom, left:right] = big[..., None].repeat(3, axis=2)
    return frame


def soft(frame):
    """The frame drawn from a picture half its size (a viewer's first, soft picture of a page)."""
    import cv2

    small = cv2.resize(frame, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR)


def sign_of(frame, page=(100, 300), area=None, cut=()):
    return st.page_sign(frame, area or (0, 0, W, H), page, cut)


def put(store, key, frame, boxes, **kw):
    """The set of the page *frame* lettered in *boxes*, with its sign, put into *store*."""
    patches = st.make_patches(frame, lettered(frame, boxes))
    store.put(key, (W, H), patches, sign=sign_of(frame, **kw))
    return patches


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
    assert not hasattr(p, "near")  # (no pixels of the frame kept with it: the page's sign decides)


def test_letters_close_together_are_one_patch_and_a_stray_pixel_none():
    frame = page()
    done = frame.copy()
    done[50:60, 150:160] = 255 - done[50:60, 150:160]
    done[50:60, 165:175] = 255 - done[50:60, 165:175]  # 5 px apart: one bubble
    done[250, 120] = 255 - done[250, 120]  # one pixel: no patch
    assert [p.box for p in st.make_patches(frame, done)] == [(150, 50, 175, 60)]


def test_the_pixel_sizes_go_with_the_viewers_dpi():
    # 100 %, 125 %, 150 %, 200 %: the group's 9 px, the margin by a bar's 6, the look's step of 4 and the cut's 3
    assert [st.scaled(st.GROUP_PX, d) for d in (96, 120, 144, 192)] == [9, 11, 14, 18]
    assert [st.scaled(st.MARGIN, d) for d in (96, 120, 144, 192)] == [6, 8, 9, 12]
    assert [st.scaled(st.LOOK_STEP, d) for d in (96, 120, 144, 192)] == [4, 5, 6, 8]
    assert [st.scaled(3, d) for d in (96, 120, 144, 192)] == [3, 4, 5, 6]  # (half up: 4.5 is 5)
    assert st.scaled(9, None) == st.scaled(9, 0) == 9 and st.scaled(1, 48) == 1
    frame = page()
    done = frame.copy()
    done[50:60, 150:160] = 255 - done[50:60, 150:160]
    done[50:60, 172:182] = 255 - done[50:60, 172:182]  # 12 px apart: two patches at 100 %, one bubble at 150 %
    assert len(st.make_patches(frame, done)) == 2
    one, = st.make_patches(frame, done, gap=st.scaled(st.GROUP_PX, 144))
    assert one.box == (150, 50, 182, 60)


def test_the_window_side_takes_the_sizes_at_the_viewers_dpi(monkeypatch):
    from PIL import Image

    from taslation.ui import seethrough as ui

    app = see_app()
    app._see_dpi = 144
    steps = []
    real = st.look
    monkeypatch.setattr(ui.st, "look", lambda rgb, before=None, step=st.LOOK_STEP, strip=st.STRIP_PX:
                        steps.append((step, strip)) or real(rgb, before, step, strip))
    image = Image.fromarray(page(ground=0))
    ui.frame_look(app, image, Facts(image))
    assert steps == [(6, 12)] and ui.px(app, ui.CUT_PX) == 5
    app._see_dpi = 96
    assert ui.px(app, ui.CUT_PX) == ui.CUT_PX
    assert ui.window.viewer_dpi(0) == st.BASE_DPI  # (no viewer: as at 100 %)
    if __import__("sys").platform == "win32":
        import ctypes

        desktop = ctypes.windll.user32.GetDesktopWindow()
        assert 96 <= ui.window.viewer_dpi(desktop) <= 480  # (the monitor's own; this test changes no setting)


def test_a_set_shows_whole_while_its_page_is_on_show_soft_or_sharp_and_goes_with_it():
    frame = art()
    store = st.SetStore()
    put(store, 1, frame, [(120, 20, 170, 60), (220, 200, 280, 240)])
    chosen, shown, seen = st.visible(store.sets, bgra(frame))
    assert chosen.key == 1 and shown == (0, 1) and seen.distance == 0.0 and seen.bars == ()
    assert st.page_distance(store.sets[0].sign, bgra(soft(frame))) <= st.PAGE_TOL
    assert st.visible(store.sets, bgra(soft(frame)))[1] == (0, 1)  # the same page drawn soft: shown whole
    noisy = np.clip(frame.astype(np.int16) + np.random.default_rng(5).integers(-12, 13, frame.shape), 0, 255)
    assert st.visible(store.sets, bgra(noisy.astype(np.uint8)))[1] == (0, 1)  # (pixels a little off everywhere)
    # another page, the page 2 px aside (moving), a jump's black: the set goes, every patch at once
    for other in (art(seed=2), np.roll(frame, 2, axis=1), np.zeros_like(frame)):
        chosen, shown, seen = st.visible(store.sets, bgra(other))
        assert chosen is None and shown == () and seen.looked[0][0] == 1 and seen.looked[0][1] > st.PAGE_TOL
    assert st.visible(store.sets, bgra(frame[:200]))[0] is None  # (another size: none)
    assert st.page_distance(store.sets[0].sign, bgra(frame[:200])) == 255.0
    store.put(2, (W, H), ())  # (a set with no sign: never shown)
    assert st.visible(store.sets, bgra(frame))[0].key == 1


def test_the_newest_set_whose_page_is_on_show_is_chosen_a_set_with_no_patches_too():
    store = st.SetStore()
    old, new = art(1), art(2)
    put(store, 1, old, [(120, 20, 170, 60)])
    put(store, 2, new, [(120, 20, 170, 60), (200, 200, 260, 240)])
    chosen, shown, _ = st.visible(store.sets, bgra(new))
    assert chosen.key == 2 and shown == (0, 1)
    chosen, shown, _ = st.visible(store.sets, bgra(old))  # turned back: the old page's patches at once
    assert chosen.key == 1 and shown == (0,)
    half = new.copy()
    half[180:] = 0  # (one half of the page another: the page is another page until read again)
    assert st.visible(store.sets, bgra(half))[0] is None
    store.put(3, (W, H), (), sign=sign_of(new))  # the page read again, nothing lettered: its marks go by it
    chosen, shown, _ = st.visible(store.sets, bgra(new))
    assert chosen.key == 3 and shown == ()


def test_a_patch_at_the_area_s_edge_shows_whole_whatever_lies_beyond_it():
    # the owner's case: a bubble at the very top of the page (its box from row 41, the page from row 40), the rows
    # above it the browser's own band, whose last rows - inside the capture area - are drawn a shade apart later: no
    # margin of the patch's is compared, and a line along the area's edge is no bar
    frame = art(box=(100, 40, 300, 300))
    frame[:40] = 60
    store = st.SetStore()
    put(store, 1, frame, [(120, 41, 170, 80), (101, 280, 140, 300)], area=(0, 37, W, H))
    later = frame.copy()
    later[36:40] = 160
    chosen, shown, seen = st.visible(store.sets, bgra(later))
    assert shown == (0, 1) and seen.bars == ()
    assert st.bar_rows(store.sets[0].sign, bgra(later), least=0) == ((37, 41),)  # (a run of one row: no bar)


def test_a_bar_over_the_page_hides_the_patches_it_lies_over_or_near_and_no_others():
    frame = art()
    store = st.SetStore()
    put(store, 1, frame, [(120, 10, 170, 25), (180, 34, 200, 38), (230, 50, 280, 70), (220, 200, 280, 240)])
    barred = frame.copy()
    barred[:30] = 40  # a bar over the top
    chosen, shown, seen = st.visible(store.sets, bgra(barred))
    assert chosen.key == 1 and seen.distance == 0.0 and seen.bars == ((0, 32),)
    assert shown == (2, 3)  # (under it, and MARGIN px below it: hidden; the others shown)
    barred[272:] = 230  # and one over the bottom
    assert st.visible(store.sets, bgra(barred))[2].bars == ((0, 32), (272, 300))
    ground = frame.copy()
    ground[:30, :100] = ground[:30, 300:] = 200  # (a bar over the ground beside the page, the page's columns as
    assert st.bar_rows(store.sets[0].sign, bgra(ground)) == ((0, 32),)  # they were: a bar all the same)
    middle = frame.copy()
    middle[120:160, 100:300] = 30  # (rows across the page far from its edges: no bar; the page another)
    assert st.bar_rows(store.sets[0].sign, bgra(middle)) == () and st.visible(store.sets, bgra(middle))[0] is None


def test_rows_painted_over_in_the_frame_read_keep_out_of_its_steady_part():
    frame = art()
    painted = frame.copy()
    painted[:80] = 0
    sign = st.page_sign(painted, (0, 0, W, H), (100, 300), cut=((0, 83),))
    assert sign.steady == (100, 83, 300, 264)  # (the steady part's top was inside the painted rows: below them)
    assert st.page_distance(sign, bgra(frame)) == 0.0  # the bars gone, the page as it was


def test_a_page_read_under_bars_shows_while_they_stay_and_its_patch_by_them_goes_once_they_go():
    frame = art()
    barred = frame.copy()
    barred[:40] = 200  # bars that stayed: the page read with their rows painted in the ground's colour
    painted = barred.copy()
    painted[:40] = 0
    done = lettered(painted, [(120, 43, 170, 80), (220, 200, 280, 240)])  # (3 px below them, and one far)
    sign = st.page_sign(painted, (0, 0, W, H), (100, 300), cut=((0, 43),))
    sign = replace(sign, rows=sign_of(barred).rows)  # (the area as captured: `ui.seethrough.stamp_sign`)
    store = st.SetStore()
    store.put(1, (W, H), st.make_patches(painted, done), sign=sign)
    assert st.visible(store.sets, bgra(barred))[1] == (0, 1)  # the bars still there: all shown
    chosen, shown, seen = st.visible(store.sets, bgra(frame))  # gone: the one by them waits for the page read again
    assert chosen.key == 1 and shown == (1,) and seen.bars == ((0, 40),)


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
    assert found.ground == (255, 255, 255) and found.strips == ()
    clean = st.masked(frame, found.bands, found.ground)
    assert clean[:40].min() == 255 and np.array_equal(clean[40:], frame[40:])


@pytest.mark.parametrize("ground", [0, 255])
def test_a_strip_along_the_area_s_edge_is_no_band_and_the_page_is_looked_for_between_the_strips(ground):
    # a browser's own bar 3 px inside an area set by hand (its foot), and 7 rows of something at the area's foot
    frame = page(ground=ground, box=(100, 0, 300, 300))
    frame[:3] = (222, 225, 230)
    frame[293:] = (90, 90, 90)
    found = st.look(frame)
    assert found.bands == () and found.strips == ((0, 3), (293, 300)) and found.kind is None  # (to the row)
    assert found.box == (100, 4, 300, 296)  # (the page between them, to within the look's step)
    frame[:40] = 70  # a bar of the viewer's there: a band, no strip
    found = st.look(frame)
    assert found.bands == ((0, 40),) and found.strips == ((293, 300),)
    assert st.look(frame, strip=0).bands == ((0, 40), (296, 300))  # (with no strips allowed: bands, as before)


def test_see_through_mode_is_no_setting_but_the_programs_one_mode():
    import dataclasses

    from taslation import config

    assert "see_through" not in {f.name for f in dataclasses.fields(Settings)}
    assert "see_through" in config.WINDOW_SETTINGS  # (a file that still has it loads: the log names it once)
    assert Settings().see_through_indicators is True  # (its indicators' pane: on until the reader switches it off)


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


def test_half_a_spread_is_told_only_in_a_frame_of_the_rest_s_size():
    """The page box at the last rest tells half a spread drawn (a frame to wait out) only in a frame of its size: in
    the viewer's window given another size a single page about half as wide as the spread before, near its side, was
    waited out - and every frame after it, since no frame waited out is at rest (the narrow window's pages never read,
    on the runners and here, with the OCR on the processor)."""
    from PIL import Image

    from taslation.ui import seethrough as ui

    def frame(size, box):
        out = np.zeros((size[1], size[0], 3), np.uint8)
        left, top, right, bottom = box
        art = np.random.default_rng(3).integers(60, 250, (bottom - top, right - left, 1), dtype=np.uint8)
        out[top:bottom, left:right] = art.repeat(3, axis=2)
        return Image.fromarray(out)

    app = see_app()
    spread = frame((400, 200), (40, 0, 340, 200))
    ui.note_frame(app, spread, Facts(spread))
    assert app._see_rest_box == (40, 0, 340, 200) and app._see_rest_size == (400, 200)
    half = frame((400, 200), (40, 0, 188, 200))  # one page of the spread drawn, the other not yet
    assert ui.frame_look(app, half, Facts(half)).kind == "half" and ui.waits(app, half, Facts(half))
    single = frame((380, 200), (40, 0, 188, 200))  # the window narrower: a page of its own there
    facts = Facts(single)
    assert ui.frame_look(app, single, facts).kind is None and not ui.waits(app, single, facts)
    ui.note_frame(app, single, facts)  # at rest: the box at the new size
    assert app._see_rest_box == (40, 0, 188, 200) and app._see_rest_size == (380, 200)


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
def test_no_key_and_no_click_is_passed_on_to_the_viewer():
    """(see-through mode, the program's one mode: every key and click is the viewer's. The functions that could send
    one are left in `capture.windows` for the tools' guards and stand-ins alone; no module of the program calls them)"""
    import re
    from pathlib import Path

    import taslation

    root = Path(taslation.__file__).resolve().parent
    senders = re.compile(r"\b(post_key|post_click|press_briefly|press_key|SendInput|keybd_event|mouse_event)\b")
    callers = sorted(path.relative_to(root).as_posix() for path in root.rglob("*.py")
                     if senders.search(path.read_text(encoding="utf-8"))
                     and path.relative_to(root).as_posix() not in ("capture/windows.py", "capture/__init__.py"))
    assert callers == []
    from taslation.ui import translator

    assert not hasattr(translator.TranslatorMixin, "_forward_click")


def test_the_quiet_start_makes_a_decoy_first_window_on_windows_and_drops_it(monkeypatch):
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
    later, attributes = [], []
    titles = []
    app = SimpleNamespace(after=lambda ms, f: later.append((ms, f)),
                          wm_attributes=lambda *a: attributes.append((len(made), a)), wm_title=titles.append)
    monkeypatch.setattr(ui.window, "IS_WINDOWS", False)  # (elsewhere than on Windows: no decoy, nothing hidden)
    ui.quiet_start(app)
    assert made == [] and not ui.quiet(app) and not ui.hidden(app) and attributes == [] and titles == []
    ui.quiet_started(app)
    assert later == []
    monkeypatch.setattr(ui.window, "IS_WINDOWS", True)
    ui.quiet_start(app)
    box, decoy = made
    # the first top-level window Tk makes is one inside a frame of the window's own: a child window, never activated
    assert box.options == {"container": True} and decoy.options == {"use": "4242"}
    assert ui._name_of(decoy) == "the start's decoy"  # (as the log of the foreground's "just before" names it)
    assert ui.quiet(app)  # (not maximised at the start then)
    # ... and the window itself is never on the screen in this mode, an application's window with its taskbar
    # button (no tool window) titled for it
    assert ui.hidden(app) and attributes == [] and titles == [ui.BUTTON_TITLE]
    ui.quiet_started(app)
    (ms, drop), = later
    assert ms == ui.QUIET_MS
    drop()
    assert made[2:] == [("gone", "Toplevel"), ("gone", "Frame")] and not ui.quiet(app)
    assert ui.hidden(app) and len(later) == 1  # (nothing put aside, nothing minimised: it never was on the screen)
    ui.quiet_start(app)
    ui.quiet_end(app)  # (the legal notice: the reader's to answer)
    assert not ui.quiet(app) and ui.hidden(app)  # (off the screen all the same)


# ------------------------------------------------------------------ the bars gone: only the bubbles they cut read again
def _units():
    from taslation import fingerprint as fp

    n = fp.FINGERPRINT_HEX_LEN
    # read with the bars' rows (0-40) painted over on a dark ground: the page's box starts below them, and the
    # fingerprint is another; without them the same page has its whole box
    painted = fp.PageUnit(box=(100, 40, 300, 300), fingerprint="0" * n)
    plain = fp.PageUnit(box=(100, 0, 300, 300), fingerprint="f" * n)
    return painted, plain


def _carry(tmp_path, painted, plain, rows=((0, 40),)):
    from PIL import Image

    from taslation.cache import BookCache, CachedBubble, CachedPage
    from taslation.pipeline import Pipeline

    cache = BookCache(tmp_path / "cache.json", "Book", "model")
    cut = CachedBubble(box=painted.normalize((120, 40, 170, 80)), text="cut",
                       poly=[painted.normalize((120, 40, 120, 40))[:2]])
    whole = CachedBubble(box=painted.normalize((120, 120, 170, 160)), text="whole",
                         poly=[painted.normalize((130, 125, 130, 125))[:2]])
    cache.add(CachedPage(fingerprint=painted.fingerprint, aspect=painted.aspect, bubbles=[cut, whole], seq=3))
    saved = []
    pipe = SimpleNamespace(cache=cache, units_of=lambda rgb: [plain], _save_store=lambda kind, store: saved.append(kind),
                           settings=SimpleNamespace(fingerprint_max_distance=36))
    got = Pipeline.carry_over(pipe, SimpleNamespace(units=[painted]), Image.new("RGB", (W, H)), rows, 3)
    return got, cache, saved


def test_a_page_read_under_bars_is_carried_over_to_the_frame_without_them_less_the_bubbles_they_cut(tmp_path):
    painted, plain = _units()
    (carried, dropped), cache, saved = _carry(tmp_path, painted, plain)
    assert (carried, dropped) == (1, 1) and saved == ["cache"]
    page, = cache.pages  # (the painted frame's own entry gone)
    assert page.fingerprint == plain.fingerprint and page.seq == 3
    assert page.incomplete  # (its next reading reads and asks for the cut bubble alone)
    bubble, = page.bubbles
    # the same place on the screen, in the plain unit's terms
    assert bubble.text == "whole" and plain.denormalize(bubble.box) == (120, 120, 170, 160)
    x, y = bubble.poly[0]
    assert (round(plain.box[0] + x * plain.width), round(plain.box[1] + y * plain.height)) == (130, 125)


def test_nothing_cut_carries_the_page_over_whole_and_another_page_is_not_carried(tmp_path):
    from taslation import fingerprint as fp

    painted, plain = _units()
    (carried, dropped), cache, _saved = _carry(tmp_path, painted, plain, rows=((0, 20),))  # (above every bubble)
    assert (carried, dropped) == (1, 0)
    page, = cache.pages
    assert page.fingerprint == plain.fingerprint and not page.incomplete and len(page.bubbles) == 2
    elsewhere = fp.PageUnit(box=(300, 0, 400, 300), fingerprint=plain.fingerprint)  # (boxes that hardly meet)
    (carried, dropped), cache, saved = _carry(tmp_path / "x", painted, elsewhere)
    assert (carried, dropped) == (0, 0) and saved == [] and [p.fingerprint for p in cache.pages] == [painted.fingerprint]


def test_after_the_bars_the_page_is_read_again_only_when_bubbles_were_left_out_and_once():
    from PIL import Image

    from taslation.ui import seethrough as ui

    plain = Image.new("RGB", (W, H))
    calls = []

    def app_with(answer, busy=False):
        read = Image.new("RGB", (W, H))
        read.info[ui.PAINTED_INFO] = ((0, 40),)
        cut = SimpleNamespace(bbox=(120, 40, 170, 80))
        pipeline = SimpleNamespace(carry_over=lambda result, image, rows, near: calls.append(rows) or answer)
        return SimpleNamespace(last_result=SimpleNamespace(original=read, regions=[cut], units=[]), pipeline=pipeline,
                               busy=busy, _shows_page=lambda image, frame: True, _see_carries=[])

    app = app_with((1, 1))
    assert ui.after_bars(app, plain) and calls == [((0, 40),)] and app._see_carries[0][1:] == (1, 1)
    assert not ui.after_bars(app, plain) and len(calls) == 1  # (once: the read frame's mark is gone)
    assert not ui.after_bars(app_with((1, 0)), plain)  # carried over whole: nothing to ask
    assert ui.after_bars(app_with((0, 0)), plain)  # nothing carried and a bubble cut: read anew
    assert not ui.after_bars(app_with((1, 1), busy=True), plain) and len(calls) == 3  # (a job runs: later)


# ------------------------------------------------------------------ the frame read: what its page's sign is made of
def test_the_frame_read_is_stamped_with_what_its_page_s_sign_is_made_of(monkeypatch):
    from PIL import Image

    from taslation.ui import seethrough as ui

    app = SimpleNamespace(_see_dpi=144)  # (a viewer at 150 %: CUT_PX 3 -> 5)
    monkeypatch.setattr(ui, "area_rgb", lambda app, image, facts: (None, (0, 40, W, H)))
    monkeypatch.setattr(ui, "frame_look", lambda app, image, facts: st.Look((100, 30, 300, 300), (), None,
                                                                            (0, 0, 0), ((40, 44),)))
    captured = art(box=(100, 44, 300, 300))
    image = Image.fromarray(captured)
    image.info[ui.PAINTED_INFO] = ((60, 80),)
    ui.stamp_sign(app, image, Facts(image))
    area, page_cols, cut_rows, rows = ui.sign_facts(image)
    assert area == (0, 44, W, H) and page_cols == (100, 300) and cut_rows == ((55, 85),)  # (the strip left out)
    assert rows.shape == (len(range(44, H, 4)), W // 4, 3)
    assert ui.sign_facts(image.copy())[:3] == (area, page_cols, cut_rows)  # (the frame read's copies carry it)
    image.info.pop(ui.PAINTED_INFO)  # (`after_bars` takes the bars' mark: the stamp stays)
    assert ui.sign_facts(image)[2] == ((55, 85),)
    assert ui.sign_facts(Image.new("RGB", (W, H))) is None  # (a frame with none: the sign of its pixels alone)
    # the patch thread makes the patches of a page and its sign
    made = []
    over = SimpleNamespace(present=lambda key, size, patches, final, sign: made.append((patches, sign)))
    ui.Patcher(over, run=False)._make(1, image, Image.fromarray(lettered(captured, [(120, 45, 170, 80)])), True, 9)
    patches, sign = made[0]
    assert patches[0].box == (120, 45, 170, 80) and sign.area == (0, 44, W, H) and sign.page == (100, 300)
    assert st.page_distance(sign, bgra(captured)) == 0.0 and st.bar_rows(sign, bgra(captured)) == ()
    plain = Image.fromarray(captured)
    assert ui.sign_of(plain, captured).area == (0, 0, W, H)  # (no stamp: the whole frame)


def _unshown_app(why, regions, on_show=True):
    from PIL import Image

    original = Image.new("RGB", (W, H))
    result = SimpleNamespace(original=original, regions=regions)
    over = SimpleNamespace(why_not_shown=lambda: {"key": id(original), **why} if "key" not in why else why)
    return SimpleNamespace(_see_through=over, last_result=result, _result_on_show=lambda: on_show), original


def _region(box, status="translated"):
    return SimpleNamespace(bbox=box, status=status, translated_text="Line." if status == "translated" else "")


def test_the_lettered_regions_not_shown_are_told_with_why_numbers_and_kinds_only(monkeypatch):
    from taslation.ui import seethrough as ui

    regions = [_region((120, 41, 170, 80)), _region((200, 100, 250, 140)), _region((10, 10, 20, 20)),
               _region((260, 200, 290, 240)), _region((300, 250, 330, 280), status="untranslated")]
    why = {"boxes": ((120, 41, 170, 80), (200, 100, 250, 140), (260, 200, 290, 240)),
           "valid": (1, 2), "barred": (0,), "bars": ((0, 44),), "covered": (2,), "drawn": (1,), "hover": None,
           "distance": 0.4, "limit": st.PAGE_TOL, "frame_at": 0.0, "final": True}
    app, original = _unshown_app(why, regions)
    found = ui.unshown(app)
    assert found["regions"] == 4  # (the one not translated is no lettered region)
    kinds = {i: kind for i, kind, _facts in found["not_shown"]}
    assert kinds == {0: "bars", 2: "no patch", 3: "covered"}
    facts = next(f for i, _k, f in found["not_shown"] if i == 0)
    assert facts["rows"] == ((0, 44),) and facts["patches"] == 1
    assert found["kinds"] == {"bars": 1, "no patch": 1, "covered": 1} and found["distance"] == 0.4
    words = repr(found)
    assert "Line." not in words  # (no text of the page)
    # the pointer resting on one, the original shown in the editor, none drawn for none of those, the lettering
    # hidden, no set's page on show
    shown_all = {**why, "valid": (0, 1, 2), "barred": (), "covered": ()}
    assert ui.unshown(_unshown_app({**shown_all, "hover": 0}, regions[:1])[0])["kinds"] == {"hover": 1}
    assert ui.unshown(_unshown_app({**shown_all, "bare": (0,), "editing": True}, regions[:1])[0]
                      )["kinds"] == {"original": 1}
    assert ui.unshown(_unshown_app({**shown_all, "drawn": ()}, regions[:1])[0])["kinds"] == {"not drawn": 1}
    assert ui.unshown(_unshown_app({"key": None, "hidden": "off"}, regions[:2])[0])["kinds"] == {"hidden:off": 2}
    app, original = _unshown_app({"key": None, "sets": (), "frame_at": 0.0}, regions[:2])
    app._see_through.why_not_shown = lambda: {"key": None, "sets": (id(original),), "frame_at": 0.0,
                                              "looked": ((id(original), 9.5),), "limit": st.PAGE_TOL}
    found = ui.unshown(app)
    assert found["kinds"] == {"no match": 2}
    assert found["not_shown"][0][2] == {"set_known": 1, "distance": 9.5, "limit": st.PAGE_TOL}
    # not the page on show, another page's set chosen, a frame the viewer has just drawn: nothing told
    assert ui.unshown(_unshown_app(why, regions, on_show=False)[0]) is None
    assert ui.unshown(_unshown_app({**why, "key": 1}, regions)[0]) is None
    import time as _time

    assert ui.unshown(_unshown_app({**why, "frame_at": _time.monotonic()}, regions)[0]) is None


def stepping(monkeypatch, frame):
    """A see-through window over a viewer (window 5) whose frame is *frame* (RGB, W x H, at the screen's top left),
    its looks (`SeeThrough._step`) made in the test: what it drew or hid noted."""
    from taslation.capture import seethrough as window
    from taslation.capture import wgc
    from taslation.capture import windows as cw

    monkeypatch.setattr(window, "_user32", SimpleNamespace(IsWindow=lambda h: 1, IsIconic=lambda h: 0,
                                                           IsWindowVisible=lambda h: 1, ShowWindow=lambda h, c: 1))
    monkeypatch.setattr(cw, "_is_cloaked", lambda h: False)
    monkeypatch.setattr(cw, "_client_box", lambda h: (0, 0, W, H))
    monkeypatch.setattr(cw, "_frame_bounds", lambda h: (0, 0, W, H))
    monkeypatch.setattr(window.wgc, "peek", lambda h: wgc.Frame(bgra(frame), 1))
    for name, value in (("cursor_pos", lambda: None), ("button_down", lambda: False),
                        ("cover_rects", lambda *a: []), ("viewer_dpi", lambda h: st.BASE_DPI)):
        monkeypatch.setattr(window, name, value)
    over = window.SeeThrough()
    drawn = []
    for name in ("_key_tick", "_edit_take", "_hook_moves", "_pane_presses", "_place_panes", "_right_plates",
                 "_edit_held"):
        setattr(over, name, lambda *a, **k: None)
    over._rect_tick = lambda *a: True
    over._sizing_tick = lambda *a: False
    over._draw = lambda chosen, shown, origin, size, *a: (
        drawn.append(("show", chosen.key, shown)), setattr(over, "_shown", (chosen.serial, shown, origin, size)))
    over._hide = lambda why, *a, **k: (drawn.append(("hide", why)), setattr(over, "_shown", None))
    over.follow(5)
    return over, drawn


def test_a_page_finished_before_the_window_looked_at_its_patches_is_no_lettering_gone(monkeypatch):
    """The page's result came (the Tk thread) before its patches reached the see-through window (the patch thread
    makes them) or before the window looked again: its last look, which had no set of that page, says nothing of
    it - it was told "no match", the lettering gone from a page at rest, as the look after found it shown. A set let
    go of while its page is on show is told."""
    from PIL import Image

    from taslation.ui import seethrough as ui

    frame = art()
    original = Image.fromarray(frame)
    key = id(original)
    result = SimpleNamespace(original=original, regions=[_region((120, 41, 170, 80))])
    over, drawn = stepping(monkeypatch, frame)
    app = SimpleNamespace(_see_through=over, last_result=result, _result_on_show=lambda: True)
    over.present(1, (W, H), (), sign=sign_of(art(seed=2)))  # (the page before's set: another page)
    over._step()
    assert over.why_not_shown()["key"] is None and ui.unshown(app, settled=False) is None  # (none of its own yet)
    over.present(key, (W, H), st.make_patches(frame, lettered(frame, [(120, 41, 170, 80)])), True, sign_of(frame))
    assert ui.unshown(app, settled=False) is None  # (handed over after the window's last look: it never saw them)
    over._step()
    assert drawn[-1] == ("show", key, (0,)) and ui.unshown(app, settled=False)["kinds"] == {}
    for other in range(2, 2 + st.SETS_KEPT):  # (three pages after it: its set let go of while it is on show)
        over.present(other, (W, H), (), sign=sign_of(art(seed=other + 1)))
    over._step()
    found = ui.unshown(app, settled=False)
    assert found["kinds"] == {"no match": 1} and found["not_shown"][0][2]["set_known"] == 0


def test_a_page_gives_the_log_one_line_of_its_regions_not_shown_and_the_tools_their_kinds(monkeypatch, caplog):
    import logging

    from taslation.ui import seethrough as ui

    regions = [_region((120, 41, 170, 80))]
    why = {"boxes": ((120, 41, 170, 80),), "valid": (), "barred": (0,), "bars": ((0, 44),), "covered": (),
           "drawn": (), "frame_at": 0.0}
    app, original = _unshown_app(why, regions)
    caplog.set_level(logging.INFO, logger=ui.log.name)
    for k in range(5):
        ui.unshown_tick(app, now=100.0 + k * ui.UNSHOWN_EVERY_S)
    ui.unshown_tick(app, now=104.5)  # (sooner than UNSHOWN_EVERY_S: no look)
    entry = app._see_unshown[id(original)]
    assert entry["looks"] == 5 and entry["kinds_seen"] == {"bars": 5}
    lines = [r.getMessage() for r in caplog.records if "lettered regions not shown" in r.getMessage()]
    assert lines == [f"see-through: page {id(original) & 0xFFFF:04x}: 1 of 1 lettered regions not shown "
                     "(bars 1)"]
    app._see_through.why_not_shown = lambda: {"key": id(original), **why, "drawn": (0,)}
    ui.unshown_tick(app, now=110.0)
    said = [r for r in caplog.records if "lettered regions not shown" in r.getMessage()]
    assert len(said) == 2  # (its count changed)
    assert "0 of 1 lettered regions not shown (none)" in caplog.records[-1].getMessage()


def test_the_window_keeps_the_page_s_distance_and_the_bars_over_the_set_it_chose():
    from taslation.capture import seethrough as window

    frame = art()
    patches = st.make_patches(frame, lettered(frame, [(120, 10, 170, 25), (220, 200, 280, 240)]))
    chosen = st.PatchSet(key=7, size=(W, H), patches=patches, serial=3, final=True, sign=sign_of(frame))
    later = frame.copy()
    later[:30] = 40  # (a bar over the first)
    _set, valid, seen = st.visible([chosen], bgra(later))
    facts = window.SeeThrough._facts_of(chosen, valid, valid, seen, [chosen], (W, H), 5.0)
    assert facts["key"] == 7 and facts["valid"] == (1,) and facts["barred"] == (0,) and facts["bars"] == ((0, 32),)
    assert facts["boxes"][0] == (120, 10, 170, 25) and facts["distance"] == 0.0 and facts["limit"] == st.PAGE_TOL
    seen = st.visible([chosen], bgra(art(seed=2)))[2]
    none = window.SeeThrough._facts_of(None, (), (), seen, [chosen], (W, H), 5.0)
    assert none["key"] is None and none["sets"] == (7,) and none["looked"][0][0] == 7
    assert none["looked"][0][1] > st.PAGE_TOL and none["at"] == 5.0


def test_a_frame_with_the_very_bytes_of_the_one_compared_last_is_decided_as_it_was_and_any_change_is_compared():
    """A viewer sends frames while its page stands still (some 40 a second): each full look compared every set's page
    with the frame. Rows of the client area holding the very bytes of the frame compared last, with the same sets, box
    and DPI - all `visible` decides from - are decided as that frame was, by a memcmp; a byte changed anywhere in
    those rows (a column outside the box too), another set put, another box or DPI is compared at that frame."""
    from taslation.capture import seethrough as window

    over = window.SeeThrough()
    over._dpi = 96
    calls = []
    real = st.visible

    def counted(sets, frame, *args, **kw):
        calls.append(frame.shape)
        return real(sets, frame, *args, **kw)

    frame = art()
    store = st.SetStore()
    put(store, 1, frame, [(120, 10, 170, 25)])
    full = np.zeros((H + 40, W + 20, 4), np.uint8)  # (the window's frame: its border round the client area)
    full[30:30 + H, 10:10 + W] = bgra(frame)
    box = (10, 30, 10 + W, 30 + H)
    import unittest.mock as mock

    with mock.patch.object(st, "visible", counted):
        first = over._decide(store.sets, full, box)
        assert first[0] is store.sets[0] and first[1] == (0,) and len(calls) == 1 and calls[0] == (H, W, 4)
        again = full.copy()  # (a new frame of the same bytes: the capture's own copy)
        assert over._decide(store.sets, again, box) == first and len(calls) == 1
        assert over._decide(list(store.sets), again, box) == first and len(calls) == 1  # (the same sets, a new list)
        assert over.counts["same"] == 2 and over.counts["compares"] == 1
        changed = again.copy()
        changed[30 + H - 1, 10 + W - 1, 0] ^= 1  # (one byte, the client area's last)
        assert over._decide(store.sets, changed, box)[0] is store.sets[0] and len(calls) == 2
        beside = changed.copy()
        beside[30 + 5, 2, 1] ^= 1  # (a byte in those rows beside the box: compared all the same)
        over._decide(store.sets, beside, box)
        assert len(calls) == 3
        beside = beside.copy()
        beside[30:30 + H, 10:10 + W] = bgra(art(seed=2))  # (another page)
        assert over._decide(store.sets, beside, box)[0] is None and len(calls) == 4
        put(store, 2, art(seed=2), [(220, 200, 280, 240)])  # (a set put: its page is the one on show)
        assert over._decide(store.sets, beside.copy(), box)[0] is store.sets[0] and len(calls) == 5
        store.put(2, (W, H), store.sets[0].patches, sign=store.sets[0].sign)  # (put again: a new set, the same page)
        assert over._decide(store.sets, beside.copy(), box)[0].serial == 3 and len(calls) == 6
        over._dpi = 144  # (another DPI: the bars' reach and the margin scale with it)
        over._decide(store.sets, beside.copy(), box)
        assert len(calls) == 7
        smaller = (10, 31, 10 + W, 30 + H)  # (another box)
        over._decide(store.sets, beside.copy(), smaller)
        assert len(calls) == 8 and over.counts["compares"] == 8 and over.counts["same"] == 2


def test_same_rows_compares_every_byte_of_the_rows_and_only_those():
    from taslation.capture import seethrough as window

    a = np.random.default_rng(3).integers(0, 256, (50, 60, 4), dtype=np.uint8)
    b = a.copy()
    assert window.same_rows(a, b, 0, 50) and window.same_rows(a, a, 0, 50)
    b[49, 59, 3] ^= 0x80
    assert not window.same_rows(a, b, 0, 50) and window.same_rows(a, b, 0, 49)  # (the last row left out)
    assert window.same_rows(a, b, 10, 10)  # (no rows)
    assert not window.same_rows(a, a[:, :59].copy(), 0, 50)  # (another shape)
    assert not window.same_rows(a, a.astype(np.uint16), 0, 50)  # (another type)
    strided = np.ascontiguousarray(np.concatenate([a, a], axis=1))[:, :60]  # (not C-contiguous: numpy compares)
    assert not strided.flags.c_contiguous and window.same_rows(a, strided, 0, 50)
    assert not window.same_rows(b, strided, 0, 50)
