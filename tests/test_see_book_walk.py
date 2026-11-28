"""A book's first screens in a maximised browser window, as see-through mode places the side panes beside them
(`ui.seethrough.note_frame`, `rest_tick`, `panes_tick`): a single colour page in the middle first (the cover), then a
dark colour page beside a black one holding a small plate, a spread of colour pictures with a column of squares, a
greyscale page beside a black one holding a small picture, and a greyscale spread running off the window's foot -
the browser's own bar above them all, its foot 3 px under the top of a capture area set by hand at margins 85 from
the top. Before, every frame had a band across the area's top (that bar) and was taken for one with the viewer's
bars over the page; bars that never went left the side panes' ground as the cover had given it, and the panes stood
300 px from the cover's box, on the spreads, for good. Now: a page box from each screen at rest (bars that have
stayed BAR_WAIT_S are a state, not bars sliding in), the capture area set by hand standing in where a screen gives
none on a flat ground, and the panes never inside that area, nor over the page of the frame on show.
Made-up screens drawn here (flat colour areas, blocks for lettering; no real page); no window."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image
from test_see_panes import fake_app
from test_seethrough import Facts

from taslation import panes as pn
from taslation.ui import seethrough as ui

W, H = 1920, 1032  # a maximised window's client area at 100 %
BAR_ROWS = 88  # rows 0-87: the browser's tab strip and address bar, in the client area
CONTENT_TOP = 87  # the pages' first row on the screens (the bar's last row, where a page is drawn over it)
SPREAD = (294, 1626)  # the pages' columns on the screen (a spread of two pages 666 px wide)
HAND = (296, 85, 292, 0)  # margins of a capture area set by hand about the spread (its top 3 px over the bar's foot)
BARS_ONLY = (0, 85, 0, 0)  # margins of one that trims only the browser's bar


def blank() -> np.ndarray:
    out = np.zeros((H, W, 3), np.uint8)  # the viewer's black ground
    out[:BAR_ROWS] = (222, 225, 230)
    out[44:76, 200:1400] = 255  # (an address bar)
    return out


def blocks(out, x0, y0, n, w, h, gap, colour, outline=None):
    """*n* blocks for lettering in a row (with an *outline* round each: large decorative lettering)."""
    for i in range(n):
        x = x0 + i * (w + gap)
        if outline is not None:
            out[y0 - 4:y0 + h + 4, x - 4:x + w + 4] = outline
        out[y0:y0 + h, x:x + w] = colour


def disc(out, cx, cy, r, colour):
    ys, xs = np.ogrid[:H, :W]
    out[(ys - cy) ** 2 + (xs - cx) ** 2 <= r * r] = colour


def oval(out, cx, cy, rx, ry, line):
    """A bubble: white inside an outline *line* px wide."""
    ys, xs = np.ogrid[:H, :W]
    out[((xs - cx) / rx) ** 2 + ((ys - cy) / ry) ** 2 <= 1] = 0
    out[((xs - cx) / (rx - line)) ** 2 + ((ys - cy) / (ry - line)) ** 2 <= 1] = 255


def glyphs(out, x, y, n, seed, size=26):
    """*n* made-up glyphs in a column from (*x*, *y*): strokes whose lengths change from glyph to glyph (lettering,
    not a tone of equal dots)."""
    for k in range(n):
        top, v = y + k * (size + 6), (seed + k * 7) % 5
        out[top + 2:top + 5, x + 2 + v:x + size - 2] = 20
        out[top + 2 + v:top + size - 2, x + size // 2 - 2:x + size // 2 + 1] = 20
        out[top + size - 8:top + size - 5, x + 4:x + size - 4 - 2 * v] = 20
        if (seed + k) % 2:
            out[top + 9:top + 13, x + 5:x + 11] = 20
        else:
            out[top + 8:top + 18, x + size - 7:x + size - 4] = 20


def cover() -> np.ndarray:
    """A single colour page in the middle (629..1291 x 88..1030): flat colour areas, large outlined lettering."""
    out = blank()
    x0, x1, y0, y1 = 629, 1291, 88, 1030
    out[y0:y1, x0:x1] = (90, 160, 230)
    out[y0 + 380:y0 + 700, x0:x1] = (200, 40, 50)
    out[y0 + 700:y1, x0:x1] = (240, 200, 40)
    blocks(out, x0 + 60, y0 + 90, 6, 70, 110, 22, (20, 20, 60), outline=(255, 255, 255))
    return out


def dark_and_black() -> np.ndarray:
    """A dark colour page (294..960, the full height) beside a page as black as the ground holding a small plate."""
    out = blank()
    out[87:1032, 294:960] = (50, 30, 80)
    out[300:700, 400:800] = (90, 60, 140)
    disc(out, 620, 820, 120, (140, 90, 60))
    out[805:996, 1313:1591] = (200, 160, 60)
    out[815:986, 1323:1581] = (40, 30, 20)
    blocks(out, 1340, 860, 4, 44, 80, 16, (220, 180, 70))
    return out


def colour_spread() -> np.ndarray:
    """A spread of colour pictures to the pages' edges, no gutter; on the right one a column of six squares of one
    size, each with a round badge and lines of small lettering beside it, a plate at its top left."""
    out = blank()
    for i, colour in enumerate([(255, 120, 40), (40, 200, 120), (250, 230, 60), (60, 120, 240)]):
        out[87 + i * 236:87 + (i + 1) * 236, 294:960] = colour
    blocks(out, 340, 160, 5, 80, 120, 30, (250, 250, 250), outline=(10, 10, 10))
    out[87:1032, 960:1626] = (30, 20, 50)
    out[110:180, 975:1200] = (200, 170, 90)
    for k in range(6):
        y = 303 + 119 * k
        out[y:y + 108, 983:1091] = [(180, 90, 90), (90, 180, 90), (90, 90, 180), (180, 180, 90), (90, 180, 180),
                                    (180, 90, 180)][k]
        disc(out, 1091, y + 100, 14, (240, 240, 240))
        for line in range(3):
            out[y + 20 + line * 22:y + 32 + line * 22, 1110:1300 - line * 40] = (230, 200, 120)
    return out


def grey_and_picture() -> np.ndarray:
    """A greyscale page with panels and a bubble (294..960) beside a black page holding a small colour picture."""
    out = blank()
    out[87:1032, 294:960] = 245
    out[100:400, 310:944] = 128
    out[104:396, 314:940] = 200
    out[420:1020, 310:620] = 90
    out[420:1020, 640:944] = 180
    disc(out, 800, 250, 70, (255, 255, 255))
    out[200:300, 790:796] = 20
    out[200:280, 810:816] = 20
    out[570:1007, 1291:1599] = (160, 110, 70)
    out[620:900, 1340:1550] = (60, 140, 200)
    return out


CUT_COLUMN = (1500, 1526)  # (`grey_spread`) the columns of the bubble's lettering the content's top cuts


def grey_spread() -> np.ndarray:
    """A greyscale spread (294..915 | 960..1626, a white gutter) running off the window's foot, a bubble cut by the
    content's top - the browser's bar over all above it -, one of its two columns of lettering cut with it."""
    out = blank()
    out[CONTENT_TOP:BAR_ROWS] = 0  # (the content from that row on, the viewer's ground beside the page too)
    out[CONTENT_TOP:1032, 294:1626] = 250
    for x0, x1 in ((294, 915), (960, 1626)):
        out[110:500, x0 + 16:x1 - 16] = 30
        out[114:496, x0 + 20:x1 - 20] = 210
        out[520:1032, x0 + 16:x1 - 16] = 30
        out[524:1032, x0 + 20:x1 - 20] = 150
    oval(out, 1490, 130, 85, 120, 5)
    glyphs(out, CUT_COLUMN[0], 70, 5, seed=1)
    glyphs(out, 1462, 95, 4, seed=2)
    disc(out, 400, 700, 60, (255, 255, 255))
    out[660:740, 396:402] = 20
    out[:CONTENT_TOP] = blank()[:CONTENT_TOP]  # (the bar over the page and the bubble above the content's top)
    return out


# the screens, and the page box the look finds in each with no area set by hand or one that trims only the bar
# (to LOOK_STEP: on every fourth pixel); the plate and the small picture on the black pages are the page's edge there
SCREENS = [("cover", cover, (632, 1292)), ("dark page and black page", dark_and_black, (296, 1592)),
           ("colour spread", colour_spread, (296, 1628)), ("grey page and black page", grey_and_picture, (296, 1600)),
           ("grey spread", grey_spread, (296, 1628))]


@pytest.fixture
def clock(monkeypatch):
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(ui.time, "monotonic", lambda: clock.now)
    return clock


def window(tmp_path, margins):
    """The window's side: its see-through state as `ui.seethrough.start` leaves it, the area as set (None: none)."""
    app = fake_app(tmp_path, _see_ground=None, _see_unrested=None, _see_bars_since=None, _see_rest_box=None,
                   _manual_area=margins is not None, after=lambda *a: None, _pick_nothing=False)
    app._hand_set = lambda: margins
    return app


def show(app, clock, picture, seconds):
    """The screen *picture* captured every 0.1 s for *seconds* (the very picture: one facts), the window's tick after
    each: the panes as they stand at the end."""
    image = Image.fromarray(picture)
    facts = Facts(image)
    steps = int(round(seconds / 0.1))
    for _ in range(steps):
        ui.note_frame(app, image, facts)
        clock.now += 0.1
        ui.panes_tick(app)
    left, right = app._see_through.handed[-1]
    return (left[1] if left else None), (right[1] if right else None)


def walk(app, clock):
    """The five screens one by one, the cover for 6 s (the bars' wait goes by on it), each after it for 2 s: (its
    name, the page's columns the look finds in it, the panes' boxes) once it has been shown."""
    for i, (name, make, columns) in enumerate(SCREENS):
        yield name, columns, show(app, clock, make(), 6.0 if i == 0 else 2.0)


@pytest.mark.parametrize("margins", [None, BARS_ONLY], ids=["no area set", "an area that trims only the bar"])
def test_the_page_box_is_taken_from_each_screen_and_the_panes_never_lie_on_its_page(tmp_path, clock, margins):
    app = window(tmp_path, margins)
    seen_right = []
    for name, columns, (left, right) in walk(app, clock):
        assert app._see_rest_box is not None and app._see_rest_box[::2] == columns, name  # (this screen's, at rest)
        # the browser's bar: a bar with no area set; with an area set 3 px into it a strip, never the viewer's bars
        assert (app._see_bars_since is not None) == (margins is None), name
        assert left is not None and right is not None, name
        assert left[2] <= columns[0] - pn.GAP and right[0] >= columns[1] + pn.GAP, name  # (beside it, a gap off)
        seen_right.append(right[0])
    # the right pane: 300 px from the cover, out past the black page's plate, out past the spread - then still
    assert seen_right[0] == SCREENS[0][2][1] + pn.MAX_FROM_PAGE
    assert seen_right[1] == SCREENS[1][2][1] + pn.GAP and seen_right[2:] == [SCREENS[2][2][1] + pn.GAP] * 3
    assert not any(app._see_pane_over.values())  # (placed right: the check never had to hide one)


def test_with_an_area_set_by_hand_about_the_spread_the_panes_stand_outside_it_on_every_screen(tmp_path, clock):
    app = window(tmp_path, HAND)
    first, last = HAND[0], W - HAND[2]
    places = set()
    for name, columns, (left, right) in walk(app, clock):
        assert left is not None and right is not None, name
        assert left[2] <= first - pn.GAP and right[0] >= last + pn.GAP, name  # (never inside the area)
        assert left[0] >= pn.GAP and right[2] <= W - pn.GAP  # (inside the window, GAP in from its edges)
        if name == "cover":  # (the look finds the cover on the ground inside the area ...)
            assert app._see_rest_box[::2] == columns
        else:  # (... and on the others no page on a flat ground: the area stands in, the ground beyond it black)
            assert app._see_rest_box == (first, HAND[1], last, H) and app._see_ground[3] == (0, 0, 0), name
        places.add((left, right))
    assert len(places) == 1  # (they never moved)
    assert not any(app._see_pane_over.values())


def test_the_area_set_by_hand_stands_in_for_the_page_box_only_on_a_flat_ground_beyond_it_and_with_room(tmp_path):
    def box_of(margins, picture):
        app = window(tmp_path, margins)
        image = Image.fromarray(picture)
        facts = Facts(image)
        return ui._box_of(app, image, facts, ui.frame_look(app, image, facts))

    spread = colour_spread()
    assert box_of(HAND, spread) == ((296, 85, 1628, H), (0, 0, 0))  # (no page on a ground in it: the area)
    assert box_of(HAND, cover())[0][::2] == (632, 1292)  # (a page on the ground in it: the look's box)
    assert box_of(None, spread)[0][::2] == (296, 1628)  # (no area set: the look's)
    wide = blank()
    wide[87:, 40:W - 40] = (60, 120, 240)  # (a picture filling an area set 40 px in from the window's sides)
    for x in range(40, W - 40, 12):
        wide[87:, x:x + 6] = (240, 200, 60)
    assert box_of((40, 85, 40, 0), wide)[0] is None  # (no room beyond it for a pane: nothing stands in)
    assert box_of((300, 85, 300, 0), wide)[0] is None  # (the area inside the picture: no flat ground beyond it)
    patterned = spread.copy()
    patterned[BAR_ROWS:, :296:8] = 200  # (no flat ground beyond it: a list or a sidebar, say)
    assert box_of(HAND, patterned)[0] is None


def test_on_the_fifth_screen_the_bubble_cut_by_the_content_s_top_is_read_lettered_up_to_it_and_shown(tmp_path, clock):
    """The owner's case: an area set by hand 3 px into the browser's bar, a strip of it along the area's top the same
    on every frame, and a bubble the content's top cuts, a column of its lettering cut with it. The strip is no bar
    and is not read; the bubble is closed by the area's edge, its cut column read with the rest and erased up to that
    edge, and its patch - reaching the edge - shown with all the others while the page is on show."""
    from helpers import EN_TEXTS, FakeOcr
    from test_seethrough import bgra

    from taslation import seethrough as st
    from taslation.config import Settings
    from taslation.pipeline import Pipeline
    from taslation.translate.simple import DictTranslator

    app = window(tmp_path, BARS_ONLY)
    picture = grey_spread()
    image = Image.fromarray(picture)
    show(app, clock, picture, 2.0)
    ui.note_strips(app, image, Facts(image))  # (as each frame is captured)
    assert app._see_bars_since is None  # (the strip: no bar, no wait)
    margins = ui.strip_margins(app, BARS_ONLY, (W, H))
    assert margins == (0, CONTENT_TOP, 0, 0)  # (read from the content's top: the strip left out)
    settings = Settings(state_dir=tmp_path / "state")
    settings.validate()
    settings.margins, settings.reuse_lines = margins, False
    result = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), cache=None).process(image)
    cut = [r for r in result.regions if r.y0 == CONTENT_TOP]
    assert len(cut) == 1 and cut[0].kind == "bubble" and cut[0].status == "translated", result.regions
    bubble = cut[0]
    assert bubble.text_box[1] == CONTENT_TOP and bubble.text_box[2] >= CUT_COLUMN[1] - 3  # (the cut column in it)
    cut_ink = np.zeros((H, W), bool)
    cut_ink[CONTENT_TOP:CONTENT_TOP + 8, CUT_COLUMN[0]:CUT_COLUMN[1]] = picture[CONTENT_TOP:CONTENT_TOP + 8,
                                                                              CUT_COLUMN[0]:CUT_COLUMN[1], 0] < 140
    ys, xs = np.nonzero(cut_ink)
    assert len(ys) and (bubble.mask[ys - bubble.y0, xs - bubble.x0] > 0).all()  # (erased: in its mask, to the edge)
    lettered = np.asarray(result.image)
    patches = st.make_patches(picture, lettered)
    assert any(p.box[1] <= CONTENT_TOP + 2 for p in patches)  # (its patch from the area's edge)
    ui.stamp_sign(app, image, Facts(image))
    sign = ui.sign_of(image, picture)
    assert sign.area[1] == CONTENT_TOP  # (the sign made of the area less the strip)
    store = st.SetStore()
    store.put(1, (W, H), patches, sign=sign)
    chosen, shown, seen = st.visible(store.sets, bgra(picture))
    assert chosen.key == 1 and shown == tuple(range(len(patches))) and seen.bars == ()  # every patch, whole


def test_the_report_of_the_capture_area_tells_the_area_set_by_hand_from_the_page_found_inside_it(tmp_path):
    from taslation.ui import report

    # (the report of the owner's window said "margins 296,85,292,0 (set by hand)" of the page found inside an area
    # whose columns were the window's: the person's own area is told apart now)
    app = SimpleNamespace(_manual_area=True, _hand_set=lambda: BARS_ONLY, _margins_of=lambda image: HAND)
    result = SimpleNamespace(original=Image.new("RGB", (W, H)))
    text = "\n".join(report.screen_lines(app, result))
    assert "capture_area = margins 296,85,292,0 (the page found inside the area set by hand, margins 0,85,0,0)" in text
    app._hand_set = lambda: HAND
    assert "capture_area = margins 296,85,292,0 (set by hand)" in "\n".join(report.screen_lines(app, result))
    app._manual_area = False
    assert "capture_area = margins 296,85,292,0 (found)" in "\n".join(report.screen_lines(app, result))
