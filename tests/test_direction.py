"""A region's text direction (`RegionStyle.direction`): kept with the formatting and undone with it, lettered
horizontally (Auto, Horizontal: byte for byte as before), turned a quarter either way ("down", "up") or stacked
column by column (`render.vertical`), composed with the slant; the editor's choice and translator mode's key."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from taslation.annotations import DIRECTIONS, RegionStyle
from taslation.pipeline import Pipeline, manual_region
from taslation.render import find_font, letter_text
from taslation.render import vertical
from taslation.render.fonts import covers

LATIN = "Ab cd"


def _latin_font():
    spec = find_font()
    if not spec:
        pytest.skip("no font")
    return spec.path


def _cjk_font():
    spec = find_font(text="あ日「」ー…", language="Japanese")
    if not spec or not covers(spec.path, "あ日"):
        pytest.skip("no Japanese font")
    return spec.path


def _region(box, size=(400, 400)):
    return manual_region(np.full((size[1], size[0], 3), 255, np.uint8), box)


def _drawn(region, text, font, size=(400, 400), **kw):
    image = Image.new("RGB", size, "white")
    done = letter_text(image, region, text, font, 9, 64, **kw)
    return np.asarray(image.convert("L")) < 128, done


# ---------------------------------------------------------------- the setting
def test_the_direction_is_kept_with_the_formatting_and_old_data_has_none():
    assert DIRECTIONS == ("", "horizontal", "down", "up", "stacked")
    assert RegionStyle().direction == "" and RegionStyle().is_empty and "direction" not in RegionStyle().to_json()
    for d in DIRECTIONS[1:]:
        style = RegionStyle.make(direction=d)
        assert style.to_json() == {"direction": d} and RegionStyle.from_json(style.to_json()) == style
        assert not style.is_empty and style.formats_nothing  # it turns or stacks the lines, it formats nothing
    assert RegionStyle.from_json({"align": "left"}).direction == ""  # a file from before
    assert RegionStyle.from_json({"direction": "diagonal"}).direction == ""
    assert RegionStyle.from_json({"direction": 3}).direction == ""
    assert not RegionStyle.make(direction="down", size=20).formats_nothing


def test_the_direction_is_stored_and_taken_back_with_the_premises(sample_page, settings):
    from helpers import EN_TEXTS, FakeOcr

    from taslation.annotations import BookAnnotations
    from taslation.translate import DictTranslator

    ann = BookAnnotations(settings.state_dir / "annotations" / "Book.json", "Book")
    p = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS), annotations=ann)
    result = p.process(sample_page, complete=True)
    region = result.translated[0]
    assert p.set_region_style(result, region, RegionStyle(direction="stacked"))
    again = BookAnnotations.load(ann.path) if hasattr(BookAnnotations, "load") else None
    if again is not None:
        unit = result.units[0]
        note = again.page(unit.fingerprint, unit.aspect).note_at(unit.normalize(region.bbox), 0.5)
        assert note is not None and note.style.direction == "stacked"
    redone = p.process(sample_page, complete=True)
    assert any(getattr(r.style, "direction", "") == "stacked" for r in redone.regions if r.style is not None)


# ---------------------------------------------------------------- lettering
def test_auto_and_horizontal_letter_byte_for_byte_as_before():
    font = _latin_font()
    region = _region((60, 80, 300, 220))
    before, done = _drawn(region, "A line of text as it always was.", font)
    for d in ("", "horizontal"):
        now, same = _drawn(region, "A line of text as it always was.", font, direction=d)
        assert np.array_equal(now, before) and same == done


def test_the_pipeline_letters_an_auto_direction_as_no_style(settings):
    p = Pipeline(settings, ocr=None, translator=None)
    region = _region((60, 80, 300, 220))
    pictures = []
    for style in (None, RegionStyle(), RegionStyle(direction="horizontal")):
        image = Image.new("RGB", (400, 400), "white")
        p._set_text(image, region, "Exactly the same lettering.", (255, 255, 255), style)
        pictures.append(np.asarray(image))
    assert np.array_equal(pictures[0], pictures[1]) and np.array_equal(pictures[0], pictures[2])


@pytest.mark.parametrize("direction", ["down", "up"])
def test_a_quarter_turn_letters_inside_the_region_and_reads_the_right_way(direction):
    font = _latin_font()
    region = _region((170, 40, 230, 360))  # tall and narrow: one line, turned
    ink, done = _drawn(region, "WWW iiiiii", font, direction=direction)
    ys, xs = np.nonzero(ink)
    assert done.size > 0 and xs.size
    assert xs.min() >= 170 and xs.max() < 230 and ys.min() >= 40 and ys.max() < 360  # inside the region
    assert np.ptp(ys) > 3 * np.ptp(xs)  # the line runs down the region
    heavy_first = float(np.nonzero(ink)[0].mean())
    other, _ = _drawn(region, "iiiiii WWW", font, direction=direction)
    heavy_last = float(np.nonzero(other)[0].mean())
    if direction == "down":  # read from the top: the heavy word, written first, lies higher
        assert heavy_first < heavy_last - 10
    else:  # read from the bottom up: the word written first lies lower
        assert heavy_first > heavy_last + 10
    upright, _ = _drawn(_region((40, 170, 360, 230)), "WWW iiiiii", font)
    assert abs(int(ink.sum()) - int(upright.sum())) < 0.25 * int(upright.sum())  # the same text, turned


def test_a_quarter_turn_follows_the_regions_shape_and_size(settings):
    font = _latin_font()
    wide = _region((40, 150, 360, 250))
    tall = _region((150, 40, 250, 360))
    flat, a = _drawn(wide, "The same words in both regions", font)
    turned, b = _drawn(tall, "The same words in both regions", font, direction="down")
    assert a.size == b.size  # the tall region turned is the wide one: the same size fits


def test_stacked_columns_run_right_to_left_with_upright_glyphs():
    font = _cjk_font()
    mask = np.full((300, 200), 255, np.uint8)
    stacked = vertical.layout_stacked(mask, "あいう\nかきく", font, 9, 40)
    first = [c for c in stacked.cells if c.shown in "あいう"]
    second = [c for c in stacked.cells if c.shown in "かきく"]
    assert len(first) == len(second) == 3 and not stacked.overflow
    assert len({c.x for c in first}) == 1 and min(c.x for c in first) > max(c.x for c in second)  # right to left
    assert [c.shown for c in sorted(first, key=lambda c: c.y)] == list("あいう")  # top to bottom
    assert all(not c.turned for c in stacked.cells)


def test_stacked_marks_take_their_vertical_forms():
    font = _cjk_font()
    mask = np.full((600, 120), 255, np.uint8)
    stacked = vertical.layout_stacked(mask, "「あー…」、ゃ", font, 9, 40)
    shown = {c.shown: c for c in stacked.cells}
    assert "ー" in shown and shown["ー"].turned  # no presentation form: turned a quarter clockwise
    for ch, form in (("…", "︙"), ("「", "﹁"), ("」", "﹂"), ("、", "︑")):
        if covers(font, form):
            assert form in shown and not shown[form].turned
        else:
            assert shown[ch].turned or ch == "、"
    assert shown["ゃ"].shift == (vertical.SMALL_SHIFT, vertical.SMALL_SHIFT)
    assert vertical.vertical_glyph("(", None) == ("(", True)  # no font known: turned


def test_stacked_latin_letters_stand_one_per_cell_and_a_column_never_starts_with_a_closing_mark():
    font = _latin_font()
    mask = np.full((400, 80), 255, np.uint8)
    stacked = vertical.layout_stacked(mask, "SPINE", font, 9, 40)
    cells = sorted(stacked.cells, key=lambda c: c.y)
    assert [c.shown for c in cells] == list("SPINE") and len({c.x for c in cells}) == 1
    assert all(b.y - a.y == stacked.size for a, b in zip(cells, cells[1:]))
    assert vertical.fill_columns([list("あいう。")], [3, 3]) == [list("あいう。")]  # hung at the foot


def test_stacked_lettering_is_drawn_inside_the_region():
    font = _cjk_font()
    region = _region((150, 40, 250, 360))
    ink, done = _drawn(region, "縦書きの文字です。", font, direction="stacked")
    ys, xs = np.nonzero(ink)
    assert done.won == "stacked" and done.size > 0
    assert xs.min() >= 150 and xs.max() < 250 and ys.min() >= 40 and ys.max() < 360
    assert np.ptp(ys) > 2 * np.ptp(xs)


def test_the_direction_composes_with_the_slant(monkeypatch):
    from taslation.render import slant

    seen = []
    real = slant.letter_slanted

    def spy(image, region, letter):
        seen.append(region.angle)
        return real(image, region, letter)

    monkeypatch.setattr(slant, "letter_slanted", spy)
    font = _latin_font()
    region = _region((150, 40, 250, 360))
    region.angle = 20.0
    ink, _ = _drawn(region, "Turned and slanted", font, direction="down")
    assert seen == [-70.0] and ink.any() and region.angle == 20.0  # (the region itself is left as it is)
    seen.clear()
    _drawn(region, "Turned and slanted", font, direction="up")
    assert seen == [110.0]
    seen.clear()
    calls = []
    real_stacked = vertical.letter_stacked
    monkeypatch.setattr(vertical, "letter_stacked", lambda *a, **k: calls.append(a[1].angle) or real_stacked(*a, **k))
    _drawn(region, "SLANT", font, direction="stacked")
    assert seen == [20.0] and calls == [0.0]  # stacked in the frame, then turned by the slant


def test_the_translators_room_follows_the_direction(settings):
    from taslation.pipeline import translation_room

    settings.readable_font_size = 12
    mask = np.full((60, 300), 255, np.uint8)
    flat = translation_room(mask, (0, 0, 300, 60), "あ" * 40, settings)
    turned = translation_room(mask.T.copy(), (0, 0, 60, 300), "あ" * 40, settings, direction="down")
    assert flat == turned
    p = Pipeline(settings, ocr=None, translator=None)
    tall = np.full((300, 60), 255, np.uint8)
    assert p.set_size(tall, "A few words", "bubble", (0, 0, 60, 300), 0, 0, direction="down") == \
        p.set_size(mask, "A few words", "bubble", (0, 0, 300, 60), 0, 0)


# ---------------------------------------------------------------- the editor
def test_the_editor_offers_the_text_directions_in_a_word_processors_words(hidden_root):
    from taslation.ui.dialogs import review

    r = _region((20, 20, 198, 199))
    r.status, r.translated_text, r.source_text = "translated", "Hi there", "やあ"
    d = review.EditBubbleDialog(hidden_root, r, [], on_save=lambda data: None, on_drop=lambda: None)
    assert d.direction_var.get() == "Auto" and d.style() == RegionStyle()
    assert list(d.direction_box.cget("values")) == ["Auto", "Horizontal", "Rotate all text 90°", "Rotate all text 270°",
                                                    "Stacked"]
    d.direction_var.set("Stacked")
    assert d.style() == RegionStyle(direction="stacked")
    d.reset_btn.invoke()
    assert d.style() == RegionStyle() and d.direction_var.get() == "Auto"
    d.destroy()
    r.style = RegionStyle(direction="down", slant=10.0)
    d = review.EditBubbleDialog(hidden_root, r, [], on_save=lambda data: None, on_drop=lambda: None)
    assert d.direction_var.get() == "Rotate all text 90°" and d.style() == RegionStyle(direction="down", slant=10.0)
    d.destroy()
