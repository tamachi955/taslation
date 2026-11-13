"""Lines balanced once the size is chosen, the size and the lines' places unmoved, within the line breaks the reader
kept, with stressed spans, hyphens, condensing and scripts wrapped by character respected, the greedy lines kept where
no balanced ones exist, no line of a lone short word ("I" on an oval's top line, "you." at its foot; not in CJK)
where the bubble's shape allows another way at the same size; and the lettering of a page kept alike: a cap of a multiple of the page's median per kind, that
leaves shouts and a size the reader set alone and gives one region lettered on its own what it gets on its page."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from taslation.annotations import RegionStyle
from taslation.pipeline import PageFill, Pipeline
from taslation.regions import TextRegion
from taslation.render import covers, find_font, styled_font, typeset
from taslation.render.typeset import (TextFormat, _balanced_lines, _display_width, _line_rooms, _NO_LINE_START,
                                      _shape_room, layout_formatted, layout_text, page_caps, wrap_lines)

TEXT = "You have got the academic ability to get into a top university so why aim for a third-rate one?"


def _font() -> str:
    spec = find_font()
    if not spec.path:
        pytest.skip("no font file on this computer")
    return spec.path


def _ellipse(w=240, h=320):
    yy, xx = np.mgrid[0:h, 0:w]
    inside = ((xx - w / 2 + 0.5) / (w / 2)) ** 2 + ((yy - h / 2 + 0.5) / (h / 2)) ** 2 <= 1.0
    return (inside * 255).astype(np.uint8)


def _both(monkeypatch, layout):
    """What *layout*() gives greedy, and balanced."""
    monkeypatch.setattr(typeset, "BALANCE_LINES", False)
    greedy = layout()
    monkeypatch.setattr(typeset, "BALANCE_LINES", True)
    return greedy, layout()


def _texts(fit) -> list[str]:
    return [t for t, _x, _y in fit.lines]


def test_the_words_are_shared_out_and_the_last_line_is_not_left_a_word():
    font = styled_font(_font(), 20)
    tokens = "the quick brown fox jumps over the lazy dog".split()
    width = _display_width(font, "the quick brown fox jumps over the lazy", "lgc")
    assert wrap_lines(" ".join(tokens), font, width, "lgc") == ["the quick brown fox jumps over the lazy", "dog"]
    assert _balanced_lines(tokens, [width, width], font, "lgc") == ["the quick brown fox jumps", "over the lazy dog"]


def test_a_last_line_of_one_short_word_is_avoided_where_the_line_above_can_give_a_word():
    font = styled_font(_font(), 20)
    tokens = "well then we shall all go".split()
    width = _display_width(font, "well then we shall all", "lgc")
    assert wrap_lines(" ".join(tokens), font, width, "lgc")[-1] == "go"
    assert len(_balanced_lines(tokens, [width, width], font, "lgc")[-1].split()) > 1


def test_each_line_follows_its_room():
    """A narrow first line and a wide second one: the slack is measured against each line's own room."""
    font = styled_font(_font(), 20)
    tokens = "aa bb cc dd ee ff gg".split()
    narrow = _display_width(font, "aa bb", "lgc")
    wide = _display_width(font, "cc dd ee ff gg", "lgc")
    assert _balanced_lines(tokens, [narrow, wide], font, "lgc") == ["aa bb", "cc dd ee ff gg"]


def test_the_size_and_the_places_stay_and_every_line_fits_its_room(monkeypatch):
    font, mask = _font(), _ellipse(320, 240)
    greedy, fit = _both(monkeypatch, lambda: layout_text(mask, TEXT, font, max_size=24))
    assert fit.size == greedy.size and fit.method == greedy.method
    assert [(x, y) for _t, x, y in fit.lines] == [(x, y) for _t, x, y in greedy.lines]
    assert " ".join(_texts(fit)) == TEXT
    assert _texts(fit) != _texts(greedy)
    rooms = _line_rooms(fit, _shape_room(mask, typeset.SHAPE_PAD, None))
    assert all(fit.font.width(t) <= room for t, room in zip(_texts(fit), rooms))


def test_a_rectangle_is_balanced_to_its_width(monkeypatch):
    font = _font()
    mask = np.full((90, 400), 255, np.uint8)
    greedy, fit = _both(monkeypatch, lambda: layout_text(mask, TEXT, font))
    assert len(fit.lines) > 1 and fit.size == greedy.size
    assert " ".join(_texts(fit)) == TEXT
    assert all(fit.font.width(t) <= max(fit.measure, 1) for t in _texts(fit) if fit.method == "rect")


def test_a_line_break_of_the_reader_stays(monkeypatch):
    font, mask = _font(), _ellipse(320, 320)
    text = "A short one.\n\nThe quick brown fox jumps over the lazy dog and runs off to the river bank for good."
    fmt = TextFormat()
    greedy, fit = _both(monkeypatch, lambda: layout_formatted(mask, text, font, fmt))
    lines = _texts(fit)
    assert lines[:2] == ["A short one.", ""] and fit.size == greedy.size
    assert " ".join(lines[2:]) == text.split("\n")[2]
    assert [y for _t, _x, y in fit.lines] == [y for _t, _x, y in greedy.lines]


def test_text_aligned_to_a_side_wraps_as_in_a_word_processor(monkeypatch):
    font, mask = _font(), _ellipse(320, 320)
    fmt = TextFormat(align="left")
    greedy, fit = _both(monkeypatch, lambda: layout_formatted(mask, TEXT, font, fmt))
    assert _texts(fit) == _texts(greedy)


def test_no_line_lies_wholly_inside_a_stressed_span():
    font = styled_font(_font(), 20)
    tokens = "*one two three four* five".split()
    room = _display_width(font, "two three", "lgc")
    lines = _balanced_lines(tokens, [room, room, room], font, "lgc")
    assert lines is None or all("*" in ln or ln == "five" for ln in lines)
    wide = _display_width(font, "three four* five", "lgc")
    lines = _balanced_lines(tokens, [wide, wide], font, "lgc")
    assert " ".join(lines) == " ".join(tokens)


def test_a_hyphenated_paragraph_stays_as_the_rescue_set_it(monkeypatch):
    font = _font()
    mask = _ellipse(90, 200)
    text = "Extraordinary circumstances notwithstanding everything"
    greedy, fit = _both(monkeypatch, lambda: layout_text(mask, text, font))
    if not fit.hyphens:
        pytest.skip("this font sets the text without a hyphen")
    assert _texts(fit) == _texts(greedy)


def test_condensed_lines_are_measured_as_condensed(monkeypatch):
    font = _font()
    mask = _ellipse(110, 150)
    text = "Ten years later on a summer evening"
    greedy, fit = _both(monkeypatch, lambda: layout_text(mask, text, font))
    assert fit.size == greedy.size and fit.condense == greedy.condense
    rooms = _line_rooms(fit, _shape_room(mask, typeset.SHAPE_PAD, None))
    assert rooms is not None and all(fit.font.width(t) <= r for t, r in zip(_texts(fit), rooms))


def test_japanese_keeps_its_line_start_rule(monkeypatch):
    spec = find_font(text="日本語", language="Japanese")
    if not spec.path or not covers(spec.path, "日本語"):
        pytest.skip("no Japanese font on this computer")
    text = "吾輩は猫である。名前はまだ無い。どこで生れたかとんと見当がつかぬ。何でも薄暗いじめじめした所で泣いていた。"
    mask = _ellipse(260, 320)
    greedy, fit = _both(monkeypatch, lambda: layout_text(mask, text, spec.path, script="jp"))
    assert "".join(_texts(fit)) == text and fit.size == greedy.size
    assert not any(t[0] in _NO_LINE_START for t in _texts(fit))


def test_a_thai_line_never_starts_with_a_combining_mark():
    font = styled_font(_font(), 20)
    tokens = list("กินข้าวหรือยัง")
    room = _display_width(font, "".join(tokens), "thai")
    lines = _balanced_lines(tokens, [room // 2 + 20, room // 2 + 20], font, "thai")
    assert lines is not None and "".join(lines) == "".join(tokens)
    assert lines[1][0] not in "ิ้ั"


def test_without_a_valid_way_the_greedy_lines_stay(monkeypatch):
    font = styled_font(_font(), 20)
    assert _balanced_lines(["Supercalifragilistic", "word"], [10, 10], font, "lgc") is None
    assert _balanced_lines(["one"], [100, 100], font, "lgc") is None
    mask = np.full((30, 40), 255, np.uint8)
    greedy, fit = _both(monkeypatch, lambda: layout_text(mask, "Supercalifragilistic word", _font()))
    assert _texts(fit) == _texts(greedy)


# --- no lone short word at the start or the end of a block -----------------------------------------------------


def _unmoved(monkeypatch, layout):
    """What *layout*() gives with the block kept nearest the centre (ORPHAN_SHIFT 0, as before), and as it is."""
    monkeypatch.setattr(typeset, "ORPHAN_SHIFT", 0.0)
    before = layout()
    monkeypatch.undo()
    return before, layout()


def _lone(line: str, first: bool) -> bool:
    """A lone short word: one Latin word of ORPHAN_FIRST_LETTERS (first line) or ORPHAN_LETTERS (last) or fewer, or
    one character of a script wrapped by character with only the signs that may not start a line after it."""
    if any(ord(c) > 0x2E80 for c in line):
        return len([c for c in line if c not in _NO_LINE_START]) == 1
    words = line.split()
    return len(words) == 1 and len(words[0]) <= (typeset.ORPHAN_FIRST_LETTERS if first else typeset.ORPHAN_LETTERS)


def _fits_its_rooms(fit, mask) -> bool:
    """Every line no wider than the mask's run at its rows (what hangs past a CJK line's end aside)."""
    rooms = _line_rooms(fit, _shape_room(mask, typeset.SHAPE_PAD, None))
    script = typeset.script_of("".join(_texts(fit)))
    hang = "".join(_NO_LINE_START)
    return rooms is not None and all(_display_width(fit.font, t.rstrip(hang), script) <= room
                                     for t, room in zip(_texts(fit), rooms))


@pytest.mark.parametrize("text, w, h", [
    ("I was able to paint the whole wall by myself", 160, 200),  # the end-to-end case: "I" alone on the top line
    ("Je ne sais pas ce que tu veux dire par là", 160, 200),
])
def test_a_lone_short_first_word_is_avoided_where_the_block_may_move(monkeypatch, text, w, h):
    font, mask = _font(), _ellipse(w, h)
    before, fit = _unmoved(monkeypatch, lambda: layout_text(mask, text, font, max_size=24))
    assert fit.method == "shape" and fit.size == before.size and not fit.overflow
    assert " ".join(_texts(fit)) == text
    assert not _lone(_texts(fit)[0], True) and not _lone(_texts(fit)[-1], False)
    assert _fits_its_rooms(fit, mask)


def test_a_last_line_of_one_short_word_is_avoided_in_a_round_bubble(monkeypatch):
    font, mask, text = _font(), _ellipse(120, 150), "I think that this one is for you."
    before, fit = _unmoved(monkeypatch, lambda: layout_text(mask, text, font, max_size=28))
    assert fit.size == before.size and " ".join(_texts(fit)) == text
    assert not _lone(_texts(fit)[-1], False) and not _lone(_texts(fit)[0], True)
    assert _fits_its_rooms(fit, mask)


def test_a_bubble_too_narrow_for_two_words_a_line_still_sets_the_text(monkeypatch):
    """Where no top within reach avoids a short line, the text is set all the same: the same size, nothing over."""
    font, mask, text = _font(), _ellipse(90, 300), "I think that this one is for you."
    before, fit = _unmoved(monkeypatch, lambda: layout_text(mask, text, font, max_size=24))
    assert fit.size == before.size and not fit.overflow and fit.clean
    assert " ".join(_texts(fit)) == text and len(fit.lines) > 4
    assert _fits_its_rooms(fit, mask)


@pytest.mark.parametrize("text, w, h", [
    ("私は壁を全部ひとりで塗ることができたよ。", 120, 210),
    ("我一个人把整面墙都刷完了。", 120, 180),
    ("今日はとても良い天気だね。", 240, 90),
])
def test_cjk_lines_are_as_before(monkeypatch, text, w, h):
    """No lone-word rule in a script wrapped by character: one character on a line is no lone word there, and the way
    round it breaks inside one (我 / 一个人 would become 我一 / 个人把). The block stays nearest the centre and the lines
    are shared out as without any orphan penalty; the line-start rule holds."""
    spec = find_font(text=text)
    if not spec.path or not covers(spec.path, text):
        pytest.skip("no font for this script on this computer")
    mask = _ellipse(w, h)
    before, fit = _unmoved(monkeypatch, lambda: layout_text(mask, text, spec.path, max_size=28))
    monkeypatch.setattr(typeset, "ORPHAN_SLACK", 0.0)  # no orphan penalty at all
    plain = layout_text(mask, text, spec.path, max_size=28)
    monkeypatch.undo()
    lines = _texts(fit)
    assert "".join(lines) == text and len(lines) > 1
    assert lines == _texts(before) == _texts(plain) and fit.size == before.size == plain.size
    assert [y for _t, _x, y in fit.lines] == [y for _t, _x, y in before.lines]
    assert not any(t[0] in _NO_LINE_START for t in lines)


def test_a_balanced_cjk_line_of_one_character_costs_nothing_more_and_keeps_its_line_start_rule(monkeypatch):
    spec = find_font(text="今日", language="Japanese")
    if not spec.path or not covers(spec.path, "今日"):
        pytest.skip("no Japanese font on this computer")
    font = styled_font(spec.path, 20)
    tokens = list("今日はとても良い天気だね。")
    rooms = [_display_width(font, "今日はとても良い天気だ", "jp"), _display_width(font, "だね", "jp")]
    lines = _balanced_lines(tokens, rooms, font, "jp")
    monkeypatch.setattr(typeset, "ORPHAN_SLACK", 0.0)
    assert lines is not None and lines == _balanced_lines(tokens, rooms, font, "jp")
    assert "".join(lines) == "".join(tokens) and not any(t[0] in _NO_LINE_START for t in lines)
    assert lines[-1] == "ね。"  # (the closing mark hangs with the last character, as before)


def test_a_first_line_of_one_short_word_is_penalised_like_a_last_one():
    font = styled_font(_font(), 20)
    tokens = "I can do it now".split()
    rooms = [_display_width(font, "I can", "lgc"), _display_width(font, "can do it now", "lgc")]
    assert _balanced_lines(tokens, rooms, font, "lgc")[0] == "I can"


def test_the_caps_are_a_multiple_of_the_median_of_the_kind(monkeypatch):
    monkeypatch.setattr(typeset, "SIZE_CAP", 1.25)
    caps = page_caps([("", 16, 0), ("speech", 20, 0), ("", 64, 0), ("thought", 12, 0), ("shout", 40, 0)])
    assert caps[:3] == [25 - 1, 24, 24]  # 1.25 x 20 = 25: above 24 the sizes tried go by twos
    assert caps[3] == 15 and caps[4] == 0
    assert page_caps([("", 8, 0), ("", 8, 0), ("", 8, 0)], 11) == [11, 11, 11]
    monkeypatch.setattr(typeset, "SIZE_CAP", None)
    assert page_caps([("", 16, 0)]) == [0]


def test_lettering_that_stood_out_in_the_original_may_stand_out(monkeypatch):
    monkeypatch.setattr(typeset, "SIZE_CAP", 1.25)
    caps = page_caps([("", 16, 18.0), ("", 16, 20.0), ("", 16, 22.0), ("", 64, 200.0), ("", 16, 0.0)])
    assert caps[:3] == [20, 20, 20]  # 1.25 x 16: the 22 against the median of 21 is the same lettering
    assert caps[3] > 64 and caps[4] == 20


def _page(*specs):
    """Regions in a row on a white page, as (width, height, text, tag, style)."""
    regions, x = [], 10
    for w, h, text, tag, style in specs:
        mask = np.full((h, w), 255, np.uint8)
        regions.append(TextRegion(x, 10, x + w, 10 + h, mask, (x, 10, x + w, 10 + h), status="translated",
                                  translated_text=text, tag=tag, style=style))
        x += w + 20
    return np.full((320, x + 10, 3), 255, np.uint8), regions


LONG = "This one is long enough to fill its whole bubble with quite a few words in it."


def _specs(tag="", style=None):
    return [(150, 150, LONG, "", None), (150, 150, LONG + " Yes.", "", None), (140, 150, LONG, "", None),
            (280, 280, "Ah!", tag, style)]


def test_a_cry_lettered_huge_in_the_original_is_not_capped(settings):
    _font()
    p = Pipeline(settings, ocr=None, translator=None)
    out, regions = _page(*_specs())
    for r in regions[:3]:
        r.glyph = 20.0
    regions[3].glyph = 130.0
    p._render(out, regions)
    assert regions[3].font_size > 2 * max(r.font_size for r in regions[:3])


def test_a_short_line_in_a_big_bubble_stays_near_its_neighbours(settings):
    _font()
    p = Pipeline(settings, ocr=None, translator=None)
    out, regions = _page(*_specs())
    p._render(out, regions)
    near = [r.font_size for r in regions[:3]]
    assert regions[3].font_size <= round(typeset.SIZE_CAP * sorted(near)[1]) + 1
    assert regions[3].size_cap > 0


def test_a_shout_and_a_size_the_reader_set_are_left_alone(settings):
    _font()
    p = Pipeline(settings, ocr=None, translator=None)
    out, regions = _page(*_specs("shout"))
    p._render(out, regions)
    free = max(r.font_size for r in regions[:3])
    assert regions[3].font_size > 2 * free and regions[3].size_cap == 0
    out, regions = _page(*_specs("", RegionStyle(size=60)))
    p._render(out, regions)
    assert regions[3].font_size == 60


def test_a_region_lettered_on_its_own_comes_out_as_on_its_page(settings):
    _font()
    p = Pipeline(settings, ocr=None, translator=None)
    page, regions = _page(*_specs())
    whole = page.copy()
    p._render(whole, regions)
    alone = page.copy()
    box, done = p._letter_region(alone, regions[3], regions[3].translated_text)
    assert done.size == regions[3].font_size
    x0, y0, x1, y1 = regions[3].bbox
    assert np.array_equal(whole[y0:y1, x0:x1], alone[y0:y1, x0:x1])


def test_a_page_that_fills_in_ends_up_with_the_caps_of_the_finished_page(settings):
    _font()
    p = Pipeline(settings, ocr=None, translator=None)
    page, regions = _page(*_specs())
    fill = PageFill(p, page.copy(), lambda kind, data: None)
    fill.announce(regions)
    texts = [r.translated_text for r in regions]
    for r, text in zip(regions, texts):
        fill.draft(r, text)
    filled = [r.size_cap for r in regions]
    p._render(page.copy(), regions)
    assert [r.size_cap for r in regions] == filled and filled[3] > 0


def test_an_edit_of_one_region_leaves_the_sizes_of_the_others(settings):
    _font()
    p = Pipeline(settings, ocr=None, translator=None)
    page, regions = _page(*_specs())
    p._render(page.copy(), regions)
    caps = [r.size_cap for r in regions]
    result = SimpleNamespace(original=Image.fromarray(page), regions=regions, image=None)
    regions[0].translated_text = "Short."
    p.rerender(result)
    assert [r.size_cap for r in regions] == caps
    regions[3].tag = "shout"
    p.rerender(result)
    assert regions[3].font_size > 2 * caps[3]


def test_the_editors_page_without_a_region_keeps_the_caps(settings):
    _font()
    p = Pipeline(settings, ocr=None, translator=None)
    page, regions = _page(*_specs())
    p._render(page.copy(), regions)
    caps = [r.size_cap for r in regions]
    p._render(page.copy(), regions[1:], record=False)
    assert [r.size_cap for r in regions] == caps
