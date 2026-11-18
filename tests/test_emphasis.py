"""Lettering with a part set larger (`render.emphasis`, `TextRegion.large`): the text cut in paragraphs, each at one
size, the part's the base's times the ratio; the ratio shrinks before the base drops under the readable size, and
under `MIN_RATIO` the bubble is lettered at one size, as it is without a part (`tests/test_lettering_identity.py`
holds that pixel for pixel)."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from taslation.regions import TextRegion
from taslation.render import emphasis, find_font, letter_text
from taslation.render.typeset import TextFormat


def _ellipse(w: int, h: int) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    inside = ((xx + 0.5 - w / 2) / (w / 2)) ** 2 + ((yy + 0.5 - h / 2) / (h / 2)) ** 2 <= 1.0
    return (inside * 255).astype(np.uint8)


def _region(w: int, h: int, text: str, kind: str = "bubble") -> TextRegion:
    x0, y0 = 20, 20
    mask = _ellipse(w, h)
    return TextRegion(x0, y0, x0 + w, y0 + h, mask, (x0 + w // 4, y0 + h // 4, x0 + 3 * w // 4, y0 + 3 * h // 4),
                      kind=kind, source_text="x", translated_text=text, status="translated")


def _font(text: str = "A", language: str = "English") -> str:
    return find_font("", None, text, language).path


def _span(text: str, part: str, ratio: float) -> tuple[int, int, float]:
    a = text.index(part)
    return a, a + len(part), ratio


def _letter(region: TextRegion, text: str, large=None, draw: bool = True, **kw):
    image = Image.new("RGB", (region.x1 + 20, region.y1 + 20), (255, 255, 255)) if draw else None
    done = letter_text(image, region, text, kw.pop("font", None) or _font(text, kw.get("language", "English")), 9, 64,
                       1.12, kw.pop("uppercase", False), (255, 255, 255), False, kw.pop("language", "English"),
                       kw.pop("outline", None), kw.pop("fmt", None), large=large, floor=kw.pop("floor", 11), **kw)
    return done, image


# ------------------------------------------------------------------ the text cut in parts

def test_parts_cut_the_text_round_its_part():
    text = "I told you it was REALLY dangerous out there."
    assert emphasis.parts_of(text, _span(text, "REALLY dangerous", 1.5)) == [
        ("I told you it was", False), ("REALLY dangerous", True), ("out there.", False)]
    assert emphasis.parts_of(text, _span(text, "I told you", 1.5)) == [
        ("I told you", True), ("it was REALLY dangerous out there.", False)]


def test_no_part_or_nothing_but_the_part_is_no_cut():
    text = "GET OUT!!"
    assert emphasis.parts_of(text, None) is None
    assert emphasis.parts_of(text, (0, len(text), 1.5)) is None
    assert emphasis.parts_of(text, (3, 3, 1.5)) is None
    assert emphasis.parts_of(text, (-5, 3, 1.5)) == [("GET", True), ("OUT!!", False)]  # held inside the text


def test_the_marks_round_the_part_go_with_it():
    text = "Hey, I don't get it, so explain it to me!"
    assert emphasis.parts_of(text, _span(text, "Hey", 1.5)) == [("Hey,", True),
                                                               ("I don't get it, so explain it to me!", False)]
    text = "Man, my shop's short-staffed~, so this'll help."
    assert emphasis.parts_of(text, _span(text, "short-staffed", 1.5)) == [
        ("Man, my shop's", False), ("short-staffed~,", True), ("so this'll help.", False)]
    text = 'He said "stop" and left.'
    assert emphasis.parts_of(text, _span(text, "stop", 1.5)) == [("He said", False), ('"stop"', True),
                                                                ("and left.", False)]
    text = "Now, let's get down to business—chin..."
    assert emphasis.parts_of(text, _span(text, "business", 1.5)) == [
        ("Now, let's get down to", False), ("business—", True), ("chin...", False)]
    text = "やあ、元気？"
    assert emphasis.parts_of(text, (0, 2, 1.5)) == [("やあ、", True), ("元気？", False)]


def test_a_stressed_run_cut_by_the_part_is_marked_on_each_side():
    text = "Don't you *dare touch* that thing."
    parts = emphasis.parts_of(text, _span(text, "touch* that thing.", 1.6))
    assert parts == [("Don't you *dare*", False), ("*touch* that thing.", True)]
    text = "I *really* mean it."
    assert emphasis.parts_of(text, _span(text, "really", 1.6)) == [("I", False), ("*really*", True),
                                                                   ("mean it.", False)]


def test_the_ratio_is_capped():
    assert emphasis.ratio_of((0, 3, 3.5)) == emphasis.RATIO_CAP
    assert emphasis.ratio_of((0, 3, 1.4)) == 1.4


# ------------------------------------------------------------------ the layout

def test_a_part_is_set_larger_on_lines_of_its_own():
    text = "And then he just looked at me and said... GET OUT!!"
    region = _region(240, 220, text)
    fit = emphasis.layout_large(region.mask, emphasis.parts_of(text, _span(text, "GET OUT!!", 2.0)), 2.0, _font(),
                                9, 64, 1.12, floor=11)
    assert fit is not None and fit.big == round(fit.base * 2.0)
    big = [ln for ln in fit.lines if ln[3] == fit.big]
    assert "".join(t for t, *_ in big).replace(" ", "") == "GETOUT!!"
    assert all(ln[3] == fit.base for ln in fit.lines if ln not in big)
    tops = [top for _t, _x, top, _z, _k in fit.lines]
    assert tops == sorted(tops)  # the paragraphs in their order, top to bottom
    plain, _ = _letter(region, text, draw=False)
    done, image = _letter(region, text, _span(text, "GET OUT!!", 2.0))
    assert done.won == "large" and done.size == fit.base < plain.size
    ink = np.asarray(image.convert("L")) < 128
    assert ink.any()
    assert not ink[~np.pad(region.mask > 0, ((20, 20), (20, 20)))[:ink.shape[0], :ink.shape[1]]].any()


def test_the_ratio_shrinks_before_the_base_drops_under_the_floor():
    text = "You... you're actually here?! Seriously?!"
    region = _region(95, 250, text)
    parts = emphasis.parts_of(text, _span(text, "Seriously?!", 2.0))
    fit = emphasis.layout_large(region.mask, parts, 2.0, _font(), 9, 64, 1.12, floor=11)
    assert fit is not None
    assert fit.base == 11 and emphasis.MIN_RATIO - 0.05 <= fit.ratio < 2.0


def test_no_room_for_a_part_letters_the_text_as_without_one():
    text = "Wait, what did you just say to me? Tell me again, slowly."
    region = _region(110, 90, text)
    assert emphasis.layout_large(region.mask, emphasis.parts_of(text, _span(text, "say to me?", 2.0)), 2.0, _font(),
                                 9, 64, 1.12, floor=16) is None
    plain, before = _letter(region, text, floor=16)
    done, after = _letter(region, text, _span(text, "say to me?", 2.0), floor=16)
    assert (done.size, done.won) == (plain.size, plain.won)
    assert np.array_equal(np.asarray(before), np.asarray(after))


def test_a_ratio_under_the_least_is_no_part():
    text = "I told you it was REALLY dangerous out there."
    region = _region(230, 200, text)
    plain, before = _letter(region, text)
    done, after = _letter(region, text, _span(text, "REALLY", 1.1))
    assert done.won == plain.won and np.array_equal(np.asarray(before), np.asarray(after))


def test_the_page_cap_holds_the_base_and_a_fixed_size_is_kept():
    text = "I told you it was REALLY dangerous out there."
    region = _region(300, 260, text)
    large = _span(text, "REALLY dangerous", 1.5)
    done, _ = letter_text(None, region, text, _font(), 9, 18, 1.12, large=large, floor=11), None
    assert done.won == "large" and done.size == 18
    fmt = TextFormat("center", "middle", 15, 0.0, None)
    done = letter_text(None, region, text, _font(), 9, 64, 1.12, fmt=fmt, large=large, floor=11)
    assert done.won == "large" and done.size == 15
    fmt = TextFormat("left", "top", 0, 0.0, None)  # aligned left: one size
    assert letter_text(None, region, text, _font(), 9, 64, 1.12, fmt=fmt, large=large, floor=11).won != "large"


def test_slanted_capitals_and_text_on_the_page_take_the_part():
    text = "Hey! Over here! Quick!!"
    region = _region(220, 200, text)
    region.angle = 10.0
    done, _ = _letter(region, text, _span(text, "Quick!!", 1.8))
    assert done.won == "large"
    region = _region(230, 210, "We have to go now, before they find us!")
    done = letter_text(None, region, region.translated_text, _font(), 9, 64, 1.12, True,
                       large=_span(region.translated_text, "before they find us!", 1.5), floor=11)
    assert done.won == "large"
    page = TextRegion(20, 20, 320, 170, np.full((150, 300), 255, np.uint8), (40, 40, 300, 150), kind="text",
                      translated_text="The END of the road", status="translated")
    page.letter_box = (40, 40, 300, 150)
    done = letter_text(None, page, page.translated_text, _font(), 9, 64, 1.12,
                       large=_span(page.translated_text, "END", 1.8), floor=11)
    assert done.won == "large"


@pytest.mark.parametrize("language,text,part", [
    ("Chinese (Simplified)", "你怎么现在才来？我们等了你很久了！", "很久了！"),
    ("Hindi", "तुम आज इतनी देर से क्यों आए? हम सब इंतज़ार कर रहे थे।", "क्यों आए?"),
    ("Arabic", "لماذا تأخرت اليوم؟ لقد انتظرناك طويلا جدا!", "طويلا جدا!"),
    ("Thai", "วันนี้ทำไมกลับบ้านช้าจัง พวกเรารอเธอนานมากเลยนะ", "นานมากเลยนะ"),
])
def test_other_scripts_take_the_part(language, text, part):
    region = _region(230, 220, text)
    font = _font(text, language)
    fit = emphasis.layout_large(region.mask, emphasis.parts_of(text, _span(text, part, 1.6)), 1.6, font, 9, 64, 1.12,
                                script=__import__("taslation.render.fonts", fromlist=["script_of"]).script_of(
                                    text, language), floor=11)
    assert fit is not None and fit.big > fit.base
    big = "".join(t for t, _x, _y, z, _k in fit.lines if z == fit.big)
    assert big.replace(" ", "") == part.replace(" ", "")
    done, _ = _letter(region, text, _span(text, part, 1.6), language=language, font=font)
    assert done.won == "large"


def test_stacked_lettering_takes_the_part_in_columns_of_its_own():
    from taslation.render import vertical

    text = "你怎么现在才来？我们等了你很久了！"
    region = _region(200, 260, text)
    font = _font(text, "Chinese (Simplified)")
    stacked = vertical.layout_stacked_large(region.mask, emphasis.parts_of(text, _span(text, "很久了！", 1.6)), 1.6,
                                            font, 9, 64, 1.12, floor=11)
    assert stacked is not None
    sizes = {c.size for c in stacked.cells}
    assert sizes == {stacked.size, round(stacked.size * 1.6)}
    big = [c for c in stacked.cells if c.size > stacked.size]
    small = [c for c in stacked.cells if c.size == stacked.size]
    assert max(c.x for c in big) < min(c.x for c in small)  # the part's columns after the rest's (to the left)
    done, image = _letter(region, text, _span(text, "很久了！", 1.6), language="Chinese (Simplified)", font=font,
                          direction="stacked")
    assert done.won == "stacked" and done.size == stacked.size
    assert (np.asarray(image.convert("L")) < 128).any()


def test_each_size_is_outlined_as_wide_as_it_wants(monkeypatch):
    from taslation.render import typeset

    seen = []
    real = typeset._contour

    def contour(color, outline_color, size, outline):
        got = real(color, outline_color, size, outline)
        seen.append((size, got[1] if got else 0))
        return got

    monkeypatch.setattr(typeset, "_contour", contour)
    text = "No way... it can't be TRUE!"
    done, _ = _letter(_region(220, 180, text), text, _span(text, "TRUE!", 1.8), outline=True)
    assert done.won == "large"
    widths = dict(seen)
    assert len(widths) == 2 and all(w == max(1, round(z / 12)) for z, w in widths.items())


def test_a_part_keeps_to_the_room_its_region_has_left(tmp_path):
    """Two bubbles whose masks overlap: the one with a part is lettered in its own part of the shared white
    (`render.rooms`), its larger lines too."""
    from taslation.config import Settings
    from taslation.pipeline import Pipeline

    s = Settings(state_dir=tmp_path)
    s.art_erase = "off"
    s.validate()
    pipe = Pipeline(s, ocr=None, translator=None, cache=None)
    text = "Listen to me. We are LEAVING RIGHT NOW!!"
    a = TextRegion(20, 20, 300, 260, _ellipse(280, 240), (60, 60, 200, 200), source_text="x", translated_text=text,
                   status="translated")
    a.large = _span(text, "LEAVING RIGHT NOW!!", 1.8)
    b = TextRegion(200, 60, 420, 260, _ellipse(220, 200), (260, 110, 380, 210), source_text="x",
                   translated_text="Huh?", status="translated")
    assert pipe.share_rooms([a, b], (460, 300)) >= 1 and a.ceded is not None
    image = Image.new("RGB", (460, 300), (255, 255, 255))
    assert pipe._set_text(image, a, text, (255, 255, 255), None).won == "large"
    (cx0, cy0, cx1, cy1), gone = a.ceded
    ink = np.asarray(image.convert("L"))[cy0:cy1, cx0:cx1] < 128
    assert not (ink & gone).any()


def test_the_pipeline_letters_a_regions_own_part(tmp_path):
    from taslation.config import Settings
    from taslation.pipeline import Pipeline

    s = Settings(state_dir=tmp_path)
    s.art_erase = "off"
    s.validate()
    pipe = Pipeline(s, ocr=None, translator=None, cache=None)
    text = "And then he just looked at me and said... GET OUT!!"
    region = _region(240, 220, text)
    image = Image.new("RGB", (300, 280), (255, 255, 255))
    assert pipe._set_text(image, region, text, (255, 255, 255), None).won != "large"
    region.large = _span(text, "GET OUT!!", 2.0)
    done = pipe._set_text(image, region, text, (255, 255, 255), None)
    assert done.won == "large"
    assert pipe._set_text(image, region, text + " Now.", (255, 255, 255), None).won != "large"  # another text
    assert pipe._set_text(image, region, text, (255, 255, 255), None, part=None).won != "large"
