"""A book's first screens in a maximised browser window, as see-through mode places the side panes beside them
(`ui.seethrough.note_frame`, `rest_tick`, `panes_tick`): a single colour page in the middle first (the cover), then a
dark colour page beside a black one holding a small plate, a spread of colour pictures with a column of squares, a
greyscale page beside a black one holding a small picture, and a greyscale spread running off the window's foot -
the browser's own bar above them all, its foot 3 px under the top of a capture area set by hand at margins 85 from
the top. Before, every frame had a band across the area's top (that bar) and was taken for one with the viewer's
bars over the page; bars that never went left the side panes' ground as the cover had given it, and the panes stood
300 px from the cover's box, on the spreads, for good. Now: a page box from each screen at rest (bars that have
stayed BAR_WAIT_S are a state, not bars sliding in), the capture area set by hand standing in where a screen gives
none on a flat ground, and the panes never inside that area, nor over the page of the frame on show. Each screen's
lettering is read and translated (a page found in each), what is read with low confidence - the plate's lettering on
the black page - left as drawn, and every patch shown while the screen is; the stand-in's scenario bw walks the same
screens on the runners (tools/standin_e2e.py, `book_walk`), whose report is judged here too.
Made-up screens (tools/book_screens.py: flat colour areas, glyphs of strokes or a font's made-up lines for lettering;
no real page); no window."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image
from test_see_panes import fake_app
from test_seethrough import Facts

from taslation import panes as pn
from taslation.ui import seethrough as ui

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import book_screens  # noqa: E402
from book_screens import (BAR_ROWS, BARS_ONLY, CONTENT_TOP, CUT_COLUMN, HAND, PLATE, SCREENS, H, W,  # noqa: E402
                          blank, colour_spread, cover, grey_spread)


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


@pytest.mark.parametrize("lettering", book_screens.LETTERINGS)
def test_each_screen_is_read_translated_and_shown_whole_and_the_plate_is_left_as_drawn(tmp_path, clock, lettering):
    """The five screens one after the other in the owner's frame (an area set 3 px into the browser's bar): the strip
    left out of what is read, a page found in each (its fingerprints), its lettering read and translated, a region
    read with low confidence - the OCR here is unsure of light lettering on a dark ground, as the plate's - left as
    drawn and the plate's pixels with it, and every patch of the page shown while it is on show."""
    from helpers import EN_TEXTS, FakeOcr
    from test_seethrough import bgra

    from taslation import seethrough as st
    from taslation.config import Settings
    from taslation.pipeline import Pipeline
    from taslation.translate.simple import DictTranslator

    class PlateOcr(FakeOcr):
        def read_with_confidence(self, image):
            return self.read(image), (0.3 if float(np.asarray(image.convert("L")).mean()) < 128 else 0.95)

    settings = Settings(state_dir=tmp_path / "state")
    settings.validate()
    settings.reuse_lines = False
    app = window(tmp_path, BARS_ONLY)
    for i, (name, make, _columns) in enumerate(SCREENS):
        try:
            picture = make(lettering)
        except SystemExit:
            pytest.skip("no Japanese font")
        image = Image.fromarray(picture)
        show(app, clock, picture, 6.0 if i == 0 else 2.0)
        ui.note_strips(app, image, Facts(image))
        settings.margins = ui.strip_margins(app, BARS_ONLY, (W, H))
        assert settings.margins[1] in (CONTENT_TOP, BAR_ROWS), (name, settings.margins)  # (the strip left out)
        result = Pipeline(settings, ocr=PlateOcr(), translator=DictTranslator(EN_TEXTS), cache=None).process(image)
        assert result.fingerprints and not result.error, name  # (a page found in it)
        assert result.translated, (name, [(r.kind, r.status) for r in result.regions])
        lettered = np.asarray(result.image)
        for r in result.regions:
            if r.status == "low-confidence":
                x0, y0, x1, y1 = r.text_box
                assert (lettered[y0:y1, x0:x1] == picture[y0:y1, x0:x1]).all(), name
        if make is book_screens.dark_and_black:
            x0, y0, x1, y1 = PLATE
            assert (lettered[y0:y1, x0:x1] == picture[y0:y1, x0:x1]).all()  # (the plate as drawn)
        patches = st.make_patches(picture, lettered)
        assert patches, name
        ui.stamp_sign(app, image, Facts(image))
        store = st.SetStore()
        store.put(i + 1, (W, H), patches, sign=ui.sign_of(image, picture))
        chosen, shown, _seen = st.visible(store.sets, bgra(picture))
        assert chosen.key == i + 1 and shown == tuple(range(len(patches))), name  # (every patch, whole)


def test_the_stand_in_s_walk_is_reported_by_screen_and_judged_on_the_runners():
    """Scenario bw's report (`standin_e2e.walk_facts` of each result, `book_walk` of them all) and its judgement
    (.github/gpu-checks/summarise.py, `_walk_correctness`): each of the five screens read and translated, no frame
    read as one with no page, no pick on trial nor "no page" said, the panes never over the page, every patch on
    show, what was read with low confidence left as drawn."""
    import importlib.util

    import standin_e2e

    from taslation.regions import PageResult

    original = Image.new("RGB", (40, 30), (200, 200, 200))
    image = original.copy()
    image.paste((255, 255, 255), (0, 0, 10, 10))  # (a region lettered at 0..10)

    def region(status, box):
        return SimpleNamespace(status=status, text_box=box, bbox=box)

    result = PageResult(image=image, original=original, fingerprints=["a", "b"],
                        regions=[region("translated", (0, 0, 10, 10)), region("low-confidence", (20, 0, 30, 10)),
                                 region("low-confidence", (5, 5, 15, 15))])
    facts = standin_e2e.walk_facts(result, SimpleNamespace(screen=(1, True)))
    assert facts["screen"] == [1, True] and facts["fingerprints"] == 2 and facts["translated"] == 1
    assert facts["low"] == 2 and facts["low_drawn"] == 1  # (the second overlaps the lettered one)
    assert facts["statuses"] == {"translated": 1, "low-confidence": 2}
    walked = {**facts, "low_drawn": 2}
    jobs = [{"walk": {**walked, "screen": [page, True]}} for page in standin_e2e.WALK_SCREENS]
    see = {"pick": {"looks": {}}, "panes": {"overlap_px_max": {"left:spread": 0, "right:cover": 0}},
           "unshown": {"pages_with_unmeant": 0, "pages": []}}
    good = standin_e2e.book_walk(SimpleNamespace(jobs=[*jobs, {"walk": {**walked, "screen": None}}, {}]), see)
    assert [s["screen"] for s in good["screens"]] == list(standin_e2e.WALK_SCREENS)
    assert all(s["results"] == 1 and s["translated"] == 1 for s in good["screens"])
    assert good["other_screens"] == ["None"]  # (a frame of no screen of the stand-in's)

    spec = importlib.util.spec_from_file_location(
        "summarise", Path(__file__).resolve().parents[1] / ".github" / "gpu-checks" / "summarise.py")
    summarise = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(summarise)

    def failed(walk, names=("bw",)):
        found = []
        summarise._walk_correctness({"book_walk": walk}, list(names),
                                    lambda _s, criterion, ok, seen=None: found.append((criterion, bool(ok))))
        return [c for c, ok in found if not ok]

    assert failed(good) == [] and failed(None, ("c",)) == []
    assert failed(None) == ["the walk was reported"]
    unread = {**good, "screens": [*good["screens"][:4], {**good["screens"][4], "translated": 0}]}
    assert failed(unread) == ["each of the five screens was read and its lettering translated"]
    assert failed({**good, "no_fingerprints": 1}) == ["no frame read as one with no page in it (no page unit's "
                                                      "fingerprint)"]
    assert failed({**good, "pick_looks": {"trial": 3}}) == ["the viewer, known by its capture area set by hand, was "
                                                            "never on trial, nor was it said that no page is found "
                                                            "in the tab"]
    assert failed({**good, "overlap_px_max": {"right:spread": 12}}) == ["the side panes never lay over the page"]
    assert failed({**good, "pages_with_unmeant": 1}) == ["every lettered region's patch showed while its page was on "
                                                         "show"]
    turned = {**good, "pages_with_unmeant": 1, "pages_with_unmeant_on_show": 0}  # (a look as the stand-in turned)
    assert failed(turned) == [] and failed({**turned, "pages_with_unmeant_on_show": 1}) != []
    drawn = {**good, "screens": [{**good["screens"][0], "low_drawn": 1}, *good["screens"][1:]]}
    assert failed(drawn) == ["what was read with low confidence was left as drawn"]


def test_a_look_that_found_a_patch_not_shown_is_told_by_what_the_stand_in_drew_then():
    import standin_seethrough

    watch = object.__new__(standin_seethrough.SeeWatch)
    watch.app = SimpleNamespace(_see_unshown={7: {"looks": 2, "kinds_seen": {"no match": 1, "hover": 1}}})
    watch.screens, watch.unshown_seen, watch.unmeant_looks = {7: (3, True)}, {}, []
    watch._note_unmeant()
    watch._note_unmeant()  # (each look once)
    assert [(key, grew) for _t, key, grew in watch.unmeant_looks] == [(7, {"no match": 1})]  # (the pointer's: meant)
    t = watch.unmeant_looks[0][0]
    turned = watch.unshown_report([(t - 900, (3, True), "sharp"), (t - 200, (5, True), "soft")])
    assert turned["pages_with_unmeant"] == 1 and turned["pages_with_unmeant_on_show"] == 0  # (another screen drawn)
    assert turned["unmeant_looks"][0]["standin_drew"] == [[5, True], "soft"]
    assert watch.unshown_report([(t - 900, (3, True), "sharp")])["pages_with_unmeant_on_show"] == 1
    assert watch.unshown_report()["pages_with_unmeant_on_show"] is None  # (no draws told: not counted)


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
