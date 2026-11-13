"""At the limit of the automatic fit, for small lettering only (a plain fit under RESCUE_BELOW points): a long Latin
word hyphenated at a syllable-like point, never a short word, one with a digit or one in capitals; the text condensed
by up to 8 % only where that beats the next smaller size, and at a fixed size only when the region's style says so;
lettering at 14 points or more never touched; the layout that won said in the fit; the lettering byte for byte as before
wherever neither is needed; and the shape layout's margin keeping every glyph off the bubble's edge."""
from __future__ import annotations

import cv2
import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr
from PIL import Image

from taslation.annotations import RegionStyle
from taslation.pipeline import Pipeline, is_dark
from taslation.regions import TextRegion
from taslation.render import letter_text, erase_region, find_font, make_lettering, shape_layout, styled_font
from taslation.render import typeset
from taslation.render.lettering import Lettering
from taslation.render.typeset import (CONDENSE_STEPS, NO_FIT, SHAPE_PAD, TextFormat, _candidate_rects, _fit_at,
                                      _hyphenate, hyphen_points, layout_formatted, layout_text)
from taslation.translate import DictTranslator
from taslation.ui.dialogs import review


def _font() -> str:
    spec = find_font()
    if not spec.path:
        pytest.skip("no font file on this computer")
    return spec.path


def _ellipse(w=200, h=300):
    yy, xx = np.mgrid[0:h, 0:w]
    inside = ((xx - w / 2 + 0.5) / (w / 2)) ** 2 + ((yy - h / 2 + 0.5) / (h / 2)) ** 2 <= 1.0
    return (inside * 255).astype(np.uint8)


def _words(fit) -> str:
    """The text the lines of *fit* hold, its hyphens taken out again."""
    joined = ""
    for ln, _x, _y in fit.lines:
        joined += ln[:-1] if ln.endswith("-") else ln + " "
    return " ".join(joined.split())


# ------------------------------------------------------------------ hyphenation
def test_hyphen_points_are_syllable_like_and_never_in_short_digit_or_capital_words():
    assert hyphen_points("wonderful") == [3, 6] and hyphen_points("children") == [4]  # won-der-ful, chil-dren
    assert hyphen_points("extraordinarily") == [7, 9, 11] and hyphen_points("probably") == [3, 5]
    assert hyphen_points("backpacker") == [4] and hyphen_points("laughter") == [5]  # never inside ck or gh
    assert 3 in hyphen_points("Entschuldigung") and hyphen_points("complètement")  # accented Latin letters too
    for word in ("amazing", "shield", "HIYOOOOOOO", "UNBELIEVABLE", "R2D2R2D2R2", "привет-привет", "seven77seven",
                 "dont'worryaboutit"):
        assert hyphen_points(word) == [], word  # under 8 letters, capitals, a digit, another script, an apostrophe
    for word in ("transformation", "understanding", "impossible", "naturellement", "Schwierigkeiten"):
        assert all(3 <= p <= len(word) - 3 for p in hyphen_points(word)), word
    assert _hyphenate("*extraordinarily*,", "lgc", lambda head: len(head) <= 10) == ("*extraor-", "dinarily*,")
    assert _hyphenate("extraordinarily", "lgc", lambda head: False) is None  # no point whose part fits
    assert _hyphenate("extraordinarily", "jp", lambda head: True) is None  # Latin scripts only


SIZES = [(w, h) for w in (60, 70, 80, 90, 100, 110, 120, 140, 160, 200) for h in (120, 140, 160, 200, 300)]


def _bubble(text: str, fp: str, small: bool, **kinds) -> tuple[np.ndarray, object, object]:
    """An ellipse where *text*'s plain fit is under RESCUE_BELOW (*small*) or at it or over, and where the rescue at
    the limit (*kinds*: hyphenate / condense) would set it larger at any size: (mask, plain fit, rescued fit)."""
    saved = typeset.RESCUE_BELOW
    try:
        for w, h in SIZES:
            mask = _ellipse(w, h)
            plain = layout_text(mask, text, fp, 9, 64, hyphenate=False, condense=False)
            if (plain.size < saved) != small:
                continue
            typeset.RESCUE_BELOW = None  # what the rescue would do without the gate
            rescued = layout_text(mask, text, fp, 9, 64, **kinds)
            typeset.RESCUE_BELOW = saved
            if rescued.size > plain.size:
                return mask, plain, rescued
    finally:
        typeset.RESCUE_BELOW = saved
    pytest.skip("no bubble of the set shows it with this computer's font")


def test_a_long_word_takes_a_hyphen_only_at_the_limit():
    fp = _font()
    text = "Unbelievably extraordinary!"
    narrow, plain, _rescued = _bubble(text, fp, True, condense=False)
    fit = layout_text(narrow, text, fp, 9, 64, condense=False)
    assert plain.size < typeset.RESCUE_BELOW and fit.size > plain.size and fit.hyphens >= 1
    assert fit.won.endswith("+hyphens") and any(ln.endswith("-") for ln, _x, _y in fit.lines) and _words(fit) == text
    assert plain.hyphens == 0
    roomy = layout_text(_ellipse(600, 400), text, fp, 9, 64, condense=False)
    assert roomy.hyphens == 0 and roomy.won in ("shape", "rect")  # it fits whole: no hyphen
    for whole in ("I can not do this, okay? Not any more!", "UNBELIEVABLY EXTRAORDINARY!", "R2D2R2D2R2D2 is here"):
        kept = layout_text(narrow, whole, fp, 9, 64, condense=False)
        assert kept.hyphens == 0, whole
    tiny = _ellipse(60, 120)  # at the smallest size the word was broken anywhere; now at a syllable
    broken = layout_text(tiny, "Extraordinarily", fp, 9, 64, hyphenate=False, condense=False)
    assert broken.size == 9 and not broken.clean
    mended = layout_text(tiny, "Extraordinarily", fp, 9, 64, condense=False)
    assert mended.clean and mended.hyphens >= 1 and _words(mended) == "Extraordinarily" and mended.size >= 9


def test_lettering_that_reads_well_is_never_hyphenated_nor_condensed():
    """Only small lettering is rescued: a plain fit of RESCUE_BELOW points or more stays exactly as it was, even
    where hyphens or condensing would make it larger."""
    fp = _font()
    assert typeset.RESCUE_BELOW == 14
    for text, kinds in (("Unbelievably extraordinary!", {"condense": False}),
                        ("Why on earth did you weld the hatch shut, Pyo?! That really hurt, you know!",
                         {"hyphenate": False})):
        mask, plain, rescued = _bubble(text, fp, False, **kinds)
        assert plain.size >= 14 and rescued.size > plain.size  # without the gate it would have changed
        now = layout_text(mask, text, fp, 9, 64, **kinds)
        assert (now.size, now.lines, now.won, now.condense, now.hyphens) == (plain.size, plain.lines, plain.won, 1.0, 0)


# ------------------------------------------------------------------ condensing
def test_condensing_is_used_only_where_it_beats_the_next_smaller_size():
    fp = _font()
    text = "Why on earth did you weld the hatch shut, Pyo?! That really hurt, you know!"
    mask, plain, _rescued = _bubble(text, fp, True, hyphenate=False)
    fit = layout_text(mask, text, fp, 9, 64, hyphenate=False)
    assert plain.size < 14 and fit.size > plain.size and fit.condense in CONDENSE_STEPS and fit.won.endswith("+condensed")
    assert shape_layout(mask, text, fp, fit.size, fit.size) is None  # uncondensed it does not fit at that size
    rects = _candidate_rects(mask, None, False, None)
    for factor in (f for f in CONDENSE_STEPS if f > fit.condense):  # the mildest step that fits was taken
        assert _fit_at(mask, text, fp, fit.size, factor, 0, 1.12, False, "lgc", None, rects, TextFormat(), False) is None
    big = _ellipse(400, 400)
    roomy = layout_text(big, "Hi!", fp, 9, 64)
    assert roomy.size == 64 and roomy.condense == 1.0 and roomy.won in ("shape", "rect")  # the largest size: as it was
    assert roomy.lines == layout_text(big, "Hi!", fp, 9, 64, hyphenate=False, condense=False).lines
    # a fixed size is never condensed unless the style says so, and then at any size
    fixed = fit.size
    kept = layout_formatted(mask, text, fp, TextFormat(size=fixed), 9, 64)
    assert kept.overflow and kept.condense == 1.0
    allowed = layout_formatted(mask, text, fp, TextFormat(size=fixed, condense=True), 9, 64)
    assert not allowed.overflow and allowed.condense < 1.0 and allowed.size == fixed
    auto = layout_formatted(mask, text, fp, TextFormat(), 9, 64)
    assert auto.condense < 1.0 and auto.size == fit.size  # an automatic size may be condensed by default
    never = layout_formatted(mask, text, fp, TextFormat(condense=False), 9, 64)
    assert never.condense == 1.0 and never.size <= fit.size


def test_a_condensed_line_is_drawn_as_narrow_as_it_is_measured():
    fp = _font()
    plain, narrow = styled_font(Lettering(fp), 40), styled_font(Lettering(fp, condense=0.92), 40)
    assert narrow.width("Hello there") == round(plain.width("Hello there") * 0.92)
    a, b = (Image.new("RGB", (500, 80), "white") for _ in range(2))
    plain.draw(a, 10, 10, "Hello there", (0, 0, 0))
    narrow.draw(b, 10, 10, "Hello there", (0, 0, 0))

    def span(img):
        cols = np.flatnonzero((np.asarray(img.convert("L")) < 128).any(axis=0))
        return int(cols.max() - cols.min())

    assert abs(span(b) - 0.92 * span(a)) <= 3 and span(b) < span(a)
    rows_a = np.flatnonzero((np.asarray(a.convert("L")) < 128).any(axis=1))
    rows_b = np.flatnonzero((np.asarray(b.convert("L")) < 128).any(axis=1))
    assert abs(len(rows_a) - len(rows_b)) <= 2  # as high as it was


# ------------------------------------------------------------------ byte for byte where neither is needed
def _letter_page(p: Pipeline, result, **rescue) -> np.ndarray:
    s = p.settings
    out = np.asarray(result.original).copy()
    backgrounds = {}
    for i, r in enumerate(result.regions):
        if r.status == "translated" and r.translated_text:
            backgrounds[i] = erase_region(out, r, s.erase_mode, s.white_threshold, s.dark_threshold, is_dark(r))
    pil = Image.fromarray(out)
    for i, bg in backgrounds.items():
        r = result.regions[i]
        letter_text(pil, r, r.translated_text, p.lettering_for(r.translated_text, r.tag), s.min_font_size,
                    s.max_font_size, s.line_spacing, s.uppercase, bg, False, s.target_language, **rescue)
    return np.asarray(pil)


@pytest.mark.parametrize("fixture", ["sample_page", "sample_page2"])
def test_where_neither_is_needed_the_lettering_is_byte_identical(fixture, request, settings):
    page = request.getfixturevalue(fixture)
    p = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"))
    res = p.process(page, use_cache=False)
    before = _letter_page(p, res, hyphenate=False, condense=False)
    now = _letter_page(p, res)
    assert np.array_equal(now, np.asarray(res.image))  # what the pipeline letters
    s = p.settings
    untouched = np.ones(now.shape[:2], bool)
    plain_regions = 0
    for r in res.translated:
        tx0, ty0, tx1, ty1 = r.letter_box or r.text_box
        anchor = (tx0 - r.x0, ty0 - r.y0, tx1 - r.x0, ty1 - r.y0)
        fit = layout_text(r.mask, r.translated_text, p.lettering_for(r.translated_text, r.tag), s.min_font_size,
                          s.max_font_size, s.line_spacing, False, None, r.kind in ("text", "text-dark"), anchor)
        if fit.won in ("shape", "rect"):  # neither triggered here: the region as before, pixel for pixel
            plain_regions += 1
            assert np.array_equal(now[r.y0:r.y1, r.x0:r.x1], before[r.y0:r.y1, r.x0:r.x1])
        else:
            untouched[r.y0:r.y1, r.x0:r.x1] = False
    assert plain_regions >= 1
    assert np.array_equal(now[untouched], before[untouched])  # and nothing else on the page changed
    # a page where neither is needed anywhere: every text at the largest size
    mask = _ellipse(300, 300)
    canvas = np.full((320, 640, 3), 255, np.uint8)
    regions = [TextRegion(10, 10, 310, 310, mask, (100, 100, 200, 200)),
               TextRegion(330, 10, 630, 310, mask, (420, 100, 520, 200))]
    for r, text in zip(regions, ("Hi!", "Oh?")):
        r.translated_text, r.status = text, "translated"
    images = []
    for rescue in ({"hyphenate": False, "condense": False}, {}):
        img = Image.fromarray(canvas.copy())
        for r in regions:
            letter_text(img, r, r.translated_text, _font(), 9, 64, **rescue)
        images.append(np.asarray(img))
    assert np.array_equal(images[0], images[1])


# ------------------------------------------------------------------ the margin
def test_no_glyph_touches_the_bubble_edge_within_a_pixel():
    """What the shape layout's margin (SHAPE_PAD) keeps: plain, italic and bold lettering on ellipses of several
    sizes, with and without the rescue, never within a pixel of the mask's edge."""
    spec = find_font()
    if not spec.path:
        pytest.skip("no font file on this computer")
    looks = [make_lettering(spec, "", False, False), make_lettering(spec, "", True, False), make_lettering(spec, "", False, True)]
    texts = ["Hello there!", "Where are you going?", "Why on earth did you weld the hatch shut?!", "WHAT?!",
             "Extraordinarily unbelievable!"]
    assert SHAPE_PAD == 0.05
    for w, h in ((80, 110), (160, 220), (260, 200), (100, 260)):
        mask = _ellipse(w, h)
        inside = (mask > 0).astype(np.uint8)
        near = (cv2.distanceTransform(np.pad(inside, 1), cv2.DIST_L2, 3)[1:-1, 1:-1] <= 1.0) | (inside == 0)
        for look in looks:
            for text in texts:
                region = TextRegion(0, 0, w, h, mask, (w // 4, h // 4, 3 * w // 4, 3 * h // 4))
                img = Image.new("RGB", (w, h), "white")
                letter_text(img, region, text, look, 9, 64)
                ink = np.asarray(img.convert("L")) < 250
                assert not (ink & near).any(), (w, h, look.italic, look.bold, text)


# ------------------------------------------------------------------ the style and the editor
def test_a_regions_style_may_allow_or_forbid_condensing(hidden_root):
    from taslation.i18n import CATALOGS
    from taslation.pipeline import manual_region

    assert RegionStyle(condense=True).to_json() == {"condense": True}
    assert RegionStyle(condense=False).to_json() == {"condense": False}
    assert RegionStyle.from_json({"condense": "yes"}).condense is None and RegionStyle().condense is None
    assert RegionStyle.from_json({"size": 30, "condense": True}) == RegionStyle(size=30, condense=True)
    region = manual_region(np.full((300, 400, 3), 255, np.uint8), (20, 20, 198, 199))
    region.status, region.translated_text, region.font_size = "translated", "Nice weather today, huh?", 31
    d = review.EditBubbleDialog(hidden_root, region, [], on_save=lambda data: None, on_drop=lambda: None)
    assert d.style().condense is None and "alternate" in d.condense_box.state() and d.condense_var.get()
    d.size_auto.set(False)
    d._size_mode()  # a fixed size: not condensed unless asked, and the box says so
    assert not d.condense_var.get() and d.style().condense is None and "alternate" in d.condense_box.state()
    d.condense_box.invoke()
    assert d.style().condense is True and "alternate" not in d.condense_box.state()
    d.reset_btn.invoke()
    assert d.style() == RegionStyle() and "alternate" in d.condense_box.state()
    d.destroy()
    assert all("Condense to fit" in catalog for code, catalog in CATALOGS.items() if code != "en")
    assert NO_FIT == "no-fit"
