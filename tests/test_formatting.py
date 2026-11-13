"""A region's lettering formatted as in a word processor's text box: line breaks, alignment, a fixed size that does or
does not fit, bold and italic forced on and off, a font this computer lacks, line and letter spacing; the annotation
that keeps it (bounds, round trip); the pipeline's rendering paths with it and, without it, exactly the automatic
lettering on both fixture pages; the region editor's formatting bar, its live preview of the page behind it, and undo of
a formatting edit."""
from __future__ import annotations

import json
import shutil
from types import SimpleNamespace

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr
from PIL import Image

from taslation.annotations import (
    BookAnnotations,
    PageAnnotations,
    RegionNote,
    RegionStyle,
)
from taslation.cache import CacheStore
from taslation.i18n import CATALOGS, set_language
from taslation.pipeline import Pipeline, is_dark, manual_region
from taslation.regions import TextRegion
from taslation.render import covers, letter_text, erase_region, face_of, find_font, styled_font
from taslation.render.fonts import font_families
from taslation.render.lettering import Lettering
from taslation.render.typeset import NO_FIT, TextFormat, layout_formatted, layout_text, letter_text
from taslation.translate import DictTranslator
from taslation.ui import app as app_mod
from taslation.ui.dialogs import review
from taslation.ui.history import EditHistory
from taslation.ui.translator import LivePreview

FP = "c" * 80
TEXT = "Why on earth did you weld the hatch shut, Pyo?! That really hurt."


def _font() -> str:
    spec = find_font()
    if not spec.path:
        pytest.skip("no font file on this computer")
    return spec.path


def _ellipse(w=200, h=300):
    yy, xx = np.mgrid[0:h, 0:w]
    inside = ((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2 <= 1.0
    return (inside * 255).astype(np.uint8)


def _ink(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("L")) < 128


def _rows_of(ink: np.ndarray) -> list[tuple[int, int]]:
    """The bands of rows with ink, top to bottom (one per line of text)."""
    rows = ink.any(axis=1)
    bands, start = [], None
    for y, on in enumerate(rows):
        if on and start is None:
            start = y
        elif not on and start is not None:
            bands.append((start, y))
            start = None
    if start is not None:
        bands.append((start, len(rows)))
    return bands


def _letter(text, fmt=None, mask=None, font=None, box=(60, 100, 140, 200)):
    mask = _ellipse() if mask is None else mask
    region = TextRegion(0, 0, mask.shape[1], mask.shape[0], mask, box)
    img = Image.new("RGB", (mask.shape[1], mask.shape[0]), "white")
    done = letter_text(img, region, text, font or _font(), 9, 60, fmt=fmt)
    return img, done


# ------------------------------------------------------------------ the typesetter
def test_each_line_break_ends_a_line_and_the_text_still_wraps_within_it():
    fp = _font()
    mask = _ellipse()
    text = "Wait!\nWhy on earth are you doing this to me?"
    for fit in (layout_text(mask, text, fp, 9, 60), layout_formatted(mask, text, fp, TextFormat(), 9, 60)):
        lines = [ln for ln, _x, _y in fit.lines]
        assert lines[0] == "Wait!" and len(lines) >= 3  # the break ends the first line, the rest wraps
        assert " ".join(lines[1:]) == "Why on earth are you doing this to me?"
    blank = layout_formatted(mask, "Wait...\n\nWhat?!", fp, TextFormat(), 9, 60)
    lines = blank.lines
    assert [ln for ln, _x, _y in lines] == ["Wait...", "", "What?!"]  # an empty line keeps its place, formatted
    assert lines[2][2] - lines[0][2] == pytest.approx(2 * blank.line_height, abs=2)
    assert [ln for ln, _x, _y in layout_text(mask, "Wait...\n\nWhat?!", fp, 9, 60).lines] == ["Wait...", "What?!"]
    img, done = _letter("Wait...\n\nWhat?!", TextFormat())
    assert done.flags == () and len(_rows_of(_ink(img))) == 2  # two lines of ink, a line's room between them


def test_lines_align_left_centre_and_right_and_the_block_top_middle_and_bottom():
    fp = _font()
    text = "One line\nA longer second line\nThird"
    edges = {}
    wide = np.full((240, 400), 255, np.uint8)
    for align in ("left", "center", "right"):
        img, done = _letter(text, TextFormat(align=align, size=20), mask=wide, box=(100, 60, 300, 180))
        assert done.flags == ()
        ink = _ink(img)
        bands = _rows_of(ink)
        assert len(bands) == 3
        cols = [np.flatnonzero(ink[a:b].any(axis=0)) for a, b in bands]
        edges[align] = [(int(c.min()), int(c.max())) for c in cols]
    lefts = [lo for lo, _hi in edges["left"]]
    rights = [hi for _lo, hi in edges["right"]]
    assert max(lefts) - min(lefts) <= 3 and max(rights) - min(rights) <= 3  # flush left, flush right
    centres = [(lo + hi) / 2 for lo, hi in edges["center"]]
    assert max(centres) - min(centres) <= 4  # each line centred
    assert min(lefts) < min(lo for lo, _hi in edges["center"])  # the left edge is further left than centred lines
    mask = np.full((300, 200), 255, np.uint8)  # a box: the block's place shows plainly
    tops = {}
    for valign in ("top", "middle", "bottom"):
        fit = layout_formatted(mask, "Short\ntext", fp, TextFormat(valign=valign, size=20), 9, 60)
        tops[valign] = (fit.lines[0][2], fit.lines[-1][2] + fit.line_height)
    assert tops["top"][0] < tops["middle"][0] < tops["bottom"][0]
    assert tops["top"][0] <= 30 and tops["bottom"][1] >= 270  # at the top and at the bottom of the room
    for align in ("left", "right"):  # left and right are set in the inner rectangle
        fit = layout_formatted(mask, "Short\ntext", fp, TextFormat(align=align, valign="bottom"), 9, 60)
        assert fit.method == "rect" and fit.anchor == align


def test_a_fixed_size_is_kept_when_it_fits_and_never_shrunk_when_it_does_not():
    fp = _font()
    automatic = layout_text(_ellipse(), TEXT, fp, 9, 60)
    fit = layout_formatted(_ellipse(), TEXT, fp, TextFormat(size=16), 9, 60)
    assert fit.size == 16 < automatic.size and not fit.overflow  # smaller than it could be, as asked
    img, done = _letter(TEXT, TextFormat(size=16))
    assert (done.size, done.flags) == (16, ())
    big = layout_formatted(_ellipse(), TEXT, fp, TextFormat(size=48), 9, 60)
    assert big.size == 48 and big.overflow and big.method == "box"  # it does not fit: kept at 48 all the same
    mask = _ellipse()
    img, done = _letter(TEXT, TextFormat(size=48), mask=mask)
    ink = _ink(img)
    assert done.size == 48 and done.flags == (NO_FIT,)
    assert ink.any() and not (ink & (mask == 0)).any()  # cut at the bubble's edge: nothing outside it


def test_bold_and_italic_are_forced_on_and_off_over_the_series_sheet(settings):
    p = Pipeline(settings, ocr=None, translator=None)
    thought, flags = p.region_lettering("Hello", "thought", RegionStyle(italic=False))
    assert not thought.italic and flags == ()  # a thought is italic unless the region says otherwise
    shout, _ = p.region_lettering("Hello", "shout", RegionStyle(bold=False))
    assert not shout.bold
    plain, _ = p.region_lettering("Hello", "", RegionStyle(bold=True, italic=True))
    assert plain.bold and plain.italic
    assert p.region_lettering("Hello", "thought", RegionStyle())[0] == p.lettering_for("Hello", "thought")
    assert p.region_lettering("Hello", "thought", None)[0] == p.lettering_for("Hello", "thought")
    upright, _ = _letter("Hello there", TextFormat(size=30), font=p.region_lettering("x", "", RegionStyle(bold=False))[0])
    heavy, _ = _letter("Hello there", TextFormat(size=30), font=p.region_lettering("x", "", RegionStyle(bold=True))[0])
    assert _ink(heavy).sum() > _ink(upright).sum() * 1.05


def test_a_font_not_installed_or_without_the_letters_falls_back_and_is_said(settings, tmp_path):
    path = _font()
    settings.models_dir = tmp_path / "models"
    settings.fonts_dir.mkdir(parents=True)
    mine = settings.fonts_dir / "MyLetter-Bold.ttf"
    shutil.copy(path, mine)
    p = Pipeline(settings, ocr=None, translator=None)
    automatic = p.lettering_for("Hello", "")
    lettering, flags = p.region_lettering("Hello", "", RegionStyle(font="No Such Font 12345"))
    assert flags == ("font-missing",) and lettering.path == automatic.path
    lettering, flags = p.region_lettering("Hello", "", RegionStyle(font="MyLetter"))
    assert flags == () and lettering.path == str(mine)
    if covers(str(mine), "こんにちは"):
        pytest.skip("this font has Japanese letters")
    lettering, flags = p.region_lettering("こんにちは", "", RegionStyle(font="MyLetter"))
    assert flags == ("font-glyphs",) and lettering.path != str(mine)
    family = face_of(path).family
    families = font_families(settings.fonts_dir)
    assert family in families and families == sorted(set(families), key=str.casefold)
    region = manual_region(np.full((200, 300, 3), 255, np.uint8), (10, 10, 290, 190))
    done = p._set_text(Image.new("RGB", (300, 200), "white"), region, "Hello", (255, 255, 255),
                       RegionStyle(font="No Such Font 12345", size=20))
    assert done.size == 20 and done.flags == ("font-missing",)


def test_letter_spacing_and_line_spacing():
    fp = _font()
    plain, spaced = styled_font(Lettering(fp), 30), styled_font(Lettering(fp, tracking=5), 30)
    assert spaced.width("Hello") == plain.width("Hello") + 4 * 5  # between the five letters, not after the last
    assert spaced.width("H*ell*o") == styled_font(Lettering(fp), 30).width("H*ell*o") + 4 * 5  # markers take none
    a, b = (Image.new("RGB", (400, 60), "white") for _ in range(2))
    plain.draw(a, 5, 5, "Hello", (0, 0, 0))
    spaced.draw(b, 5, 5, "Hello", (0, 0, 0))
    span = lambda img: int(np.flatnonzero(_ink(img).any(axis=0)).max())  # noqa: E731
    assert span(b) - span(a) == pytest.approx(20, abs=2) and abs(int(_ink(a).sum()) - int(_ink(b).sum())) < 0.05 * _ink(a).sum()
    mask = np.full((300, 200), 255, np.uint8)
    tight = layout_formatted(mask, "One\nTwo", fp, TextFormat(size=20), 9, 60)
    loose = layout_formatted(mask, "One\nTwo", fp, TextFormat(size=20, line_spacing=2.0), 9, 60)
    assert tight.lines[1][2] - tight.lines[0][2] == pytest.approx(20 * 1.12)
    assert loose.lines[1][2] - loose.lines[0][2] == pytest.approx(40)


def test_the_automatic_format_lays_out_as_the_automatic_lettering():
    """Formatted with every field automatic, a text without empty lines that fits is set exactly as without."""
    fp = _font()
    cases = [(_ellipse(), TEXT), (_ellipse(160, 120), "Hello there!"), (np.full((120, 300), 255, np.uint8), "Nice weather today, huh?"),
             (_ellipse(220, 300), "It isn't over yet.\nNot even close!")]
    for mask, text in cases:
        a, b = layout_text(mask, text, fp, 9, 60), layout_formatted(mask, text, fp, TextFormat(), 9, 60)
        assert (a.size, a.lines, a.method) == (b.size, b.lines, b.method)


# ------------------------------------------------------------------ the annotation
def test_a_region_style_keeps_only_what_is_set_and_checks_its_bounds(tmp_path):
    assert RegionStyle().is_empty and RegionStyle().to_json() == {}
    style = RegionStyle(align="left", valign="bottom", font="Comic Neue", size=30, bold=False, italic=True,
                        line_spacing=1.5, letter_spacing=2)
    assert style.to_json() == {"align": "left", "valign": "bottom", "font": "Comic Neue", "size": 30, "bold": False,
                               "italic": True, "line_spacing": 1.5, "letter_spacing": 2}
    assert RegionStyle.from_json(style.to_json()) == style and RegionStyle(bold=False).to_json() == {"bold": False}
    odd = RegionStyle.from_json({"align": "diagonal", "valign": 3, "font": "x" * 200 + "\x00", "size": 9999,
                                 "bold": "yes", "italic": 1, "line_spacing": "wide", "letter_spacing": 999})
    assert odd == RegionStyle(font="x" * 60, size=200, letter_spacing=50)
    assert RegionStyle.from_json({"size": -3, "line_spacing": float("nan"), "letter_spacing": -99}) == RegionStyle(letter_spacing=-10)
    assert RegionStyle.from_json({"size": 2, "line_spacing": 9}) == RegionStyle(size=4, line_spacing=4.0)
    assert RegionStyle.from_json("bold") == RegionStyle() and RegionStyle.make(size=24.4) == RegionStyle(size=24)
    note = RegionNote((0.1, 0.1, 0.3, 0.3), style=RegionStyle(size=20))
    assert not note.is_empty and note.to_json() == {"box": [0.1, 0.1, 0.3, 0.3], "style": {"size": 20}}
    assert RegionNote.from_json({"box": [0.1, 0.1, 0.3, 0.3], "speaker": "Piyo"}).style == RegionStyle()  # files of before
    ann = BookAnnotations(tmp_path / "Book.json", "Book")
    page = ann.page(FP, 0.7)
    page.set_note((0.5, 0.5, 0.6, 0.7), speaker="ピヨ")
    page.set_style((0.5, 0.5, 0.6, 0.7), style)
    page.set_style((0.1, 0.1, 0.2, 0.2), RegionStyle(align="right"))
    ann.save()
    raw = json.loads((tmp_path / "Book.json").read_text(encoding="utf-8"))
    assert raw["schema"] == 1 and raw["pages"][0]["notes"][0] == {"box": [0.5, 0.5, 0.6, 0.7], "speaker": "ピヨ",
                                                                  "style": style.to_json()}
    again = BookAnnotations.load(tmp_path / "Book.json").pages[0]
    assert again.note_at((0.5, 0.5, 0.6, 0.7)).style == style and again.note_at((0.1, 0.1, 0.2, 0.2)).style.align == "right"


def test_a_notes_facts_and_its_formatting_are_set_apart():
    page = PageAnnotations(FP, 0.7)
    box = (0.5, 0.5, 0.6, 0.7)
    page.set_style(box, RegionStyle(size=30))
    page.set_note(box, speaker="Piyo", kind="shout")  # the editor's facts: the formatting stays
    assert page.note_at(box).style == RegionStyle(size=30) and page.note_at(box).speaker == "Piyo"
    page.set_note(box)  # no facts any more: the formatting alone keeps the entry
    assert page.note_at(box) is not None and page.note_at(box).style == RegionStyle(size=30)
    page.set_style(box, RegionStyle())  # automatic again: nothing is left
    assert page.notes == []
    assert page.set_style(box, RegionStyle()) is None and page.notes == []
    moved = PageAnnotations(FP, 0.7)
    moved.set_note((0.2, 0.2, 0.3, 0.3), "Piyo", "", False, "", 0.4, RegionStyle(align="left"))
    assert moved.notes[0].style.align == "left"


# ------------------------------------------------------------------ the pipeline
def _legacy_render(p: Pipeline, result) -> np.ndarray:
    """The page as the pipeline lettered it before formatting existed (the old `_render`, verbatim)."""
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
                    s.max_font_size, s.line_spacing, s.uppercase, bg, False, s.target_language)
    return np.asarray(pil)


@pytest.mark.parametrize("fixture", ["sample_page", "sample_page2"])
def test_without_a_style_both_fixture_pages_letter_exactly_as_before(fixture, request, settings):
    page = request.getfixturevalue(fixture)
    cache = CacheStore(settings.cache_dir).open("Book", "m")
    p = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache)
    res = p.process(page)
    assert len(res.translated) >= 5
    legacy = _legacy_render(p, res)
    assert int(np.any(np.asarray(res.image) != legacy, axis=2).sum()) == 0  # not one pixel differs
    patches = []
    p.process(page, use_cache=False, events=lambda kind, data: patches.append(data) if kind == "page" else None)
    assert np.array_equal(np.asarray(patches[-1]["image"]), legacy)  # the page that fills in, too
    cached = p.process(page)  # the cached page shown again
    assert cached.cache_hits == 1 and np.array_equal(np.asarray(cached.image), legacy)
    for r in cached.regions:  # an empty style is no style
        r.style = RegionStyle()
    p.rerender(cached)
    assert np.array_equal(np.asarray(cached.image), legacy)
    target = max(cached.translated, key=lambda r: r.area)
    target.style = RegionStyle(align="left", size=18)
    p.rerender(cached)
    changed = np.any(np.asarray(cached.image) != legacy, axis=2)
    ys, xs = np.nonzero(changed)
    assert xs.size and target.x0 <= xs.min() and xs.max() < target.x1 and target.y0 <= ys.min() and ys.max() < target.y1
    assert target.font_size == 18 and target.letter_flags == ()


def test_a_regions_formatting_letters_it_on_every_path_and_follows_it_when_moved(sample_page, settings):
    cache = CacheStore(settings.cache_dir).open("Book", "m")
    ann = BookAnnotations(settings.state_dir / "annotations" / "Book.json", "Book")
    p = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache, annotations=ann)
    res = p.process(sample_page, complete=True)
    target = next(r for r in res.regions if r.translated_text == "Nice weather today, huh?")
    plain = np.asarray(res.image).copy()
    style = RegionStyle(align="right", valign="top", size=20)
    assert p.set_region_style(res, target, style) and target.style == style
    p.rerender(res)
    styled = np.asarray(res.image).copy()
    assert not np.array_equal(styled, plain) and target.font_size == 20
    again = p.process(sample_page, complete=True)  # the cached page read again: the style comes from the annotations
    twin = next(r for r in again.regions if r.translated_text == "Nice weather today, huh?")
    assert twin.style == style and np.array_equal(np.asarray(again.image), styled)
    filled = []
    fresh = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), annotations=ann)
    fresh.process(sample_page, use_cache=False, events=lambda kind, data: filled.append(data) if kind == "page" else None)
    assert np.array_equal(np.asarray(filled[-1]["image"]), styled)  # a page translated afresh, filling in
    bed = p.page_without(again, twin)
    preview, done = p.preview_region(bed, twin, twin.translated_text, style)
    assert np.array_equal(preview, styled) and done.size == 20 and twin.style == style  # the preview stores nothing
    automatic, _done = p.preview_region(bed, twin, twin.translated_text, RegionStyle())
    assert np.array_equal(automatic, plain)
    x0, y0, x1, y1 = twin.bbox
    assert p.move_region(again, twin, (x0 + 6, y0 + 4, x1 + 6, y1 + 4))
    unit = again.units[twin.unit]
    assert ann.lookup(unit.fingerprint, unit.aspect, 6).note_at(unit.normalize(twin.bbox)).style == style
    assert twin.style == style
    assert p.set_region_style(again, twin, RegionStyle()) and twin.style is None
    assert ann.lookup(unit.fingerprint, unit.aspect, 6).note_at(unit.normalize(twin.bbox)) is None
    p.annotations = None
    assert not p.set_region_style(again, twin, style) and twin.style is None  # without a book's premises: nothing


# ------------------------------------------------------------------ the editor
def _region(style=None, text="Nice weather today, huh?"):
    r = manual_region(np.full((300, 400, 3), 255, np.uint8), (20, 20, 198, 199))
    r.status, r.translated_text, r.source_text, r.font_size = "translated", text, "今日はいい天気だね", 31
    r.style = style
    return r


def test_the_formatting_bar_shows_a_style_and_gives_it_back(hidden_root):
    style = RegionStyle(align="right", valign="bottom", font="Comic Neue", size=40, bold=True, italic=False,
                        line_spacing=1.5, letter_spacing=3)
    d = review.EditBubbleDialog(hidden_root, _region(style), [], on_save=lambda data: None, on_drop=lambda: None,
                                families=lambda: ["Arial", "Comic Neue"], faces=(False, True))
    assert d.style() == style and d._data()["style"] == style
    assert d.align_var.get() == "right" and d.valign_var.get() == "bottom" and d.font_var.get() == "Comic Neue"
    assert d.size_var.get() == "40" and not d.size_auto.get() and str(d.size_spin.cget("state")) == "normal"
    assert d.line_var.get() == "1.5" and d.letter_var.get() == "3"
    assert "alternate" not in d.face_boxes["bold"].state() and d.face_vars["bold"].get() and not d.face_vars["italic"].get()
    d.faces_auto_btn.invoke()  # B and I as the series sheet says: shown as "auto", the region's own look ticked
    assert d.style().bold is None and d.style().italic is None
    assert "alternate" in d.face_boxes["italic"].state() and d.face_vars["italic"].get() and not d.face_vars["bold"].get()
    d.face_boxes["italic"].invoke()  # a click forces it: off here, as the box shows it on
    assert d.style().italic is False and "alternate" not in d.face_boxes["italic"].state()
    d.size_auto.set(True)
    d._size_mode()
    d.line_var.set(review._("Auto"))
    d.font_var.set(review._("(automatic)"))
    d.letter_var.set("not a number")
    assert d.style() == RegionStyle(align="right", valign="bottom", italic=False)
    d.reset_btn.invoke()
    assert d.style() == RegionStyle() and d.size_var.get() == "31"  # the size the lettering has now
    d._fill_families()
    assert list(d.font_box.cget("values"))[:3] == ["(automatic)", "Arial", "Comic Neue"]
    d.destroy()
    d = review.EditBubbleDialog(hidden_root, _region(), [], on_save=lambda data: None, on_drop=lambda: None)
    assert d.style() == RegionStyle() and "alternate" in d.face_boxes["bold"].state() and d.fit_var.get() == ""
    d.destroy()


def test_enter_breaks_the_line_ctrl_enter_saves_and_cancel_puts_the_page_back(hidden_root):
    saved, cancelled = [], []
    d = review.EditBubbleDialog(hidden_root, _region(text="Nice weather\ntoday, huh?"), [], on_save=saved.append,
                                on_drop=lambda: None, on_cancel=lambda: cancelled.append(1))
    assert d.text.bind("<Return>") == "" and d.text.bind("<Control-Return>") and d.bind("<Control-Return>")
    d.text.insert("end", "\nOh well.")
    assert d._data()["text"] == "Nice weather\ntoday, huh?\nOh well."  # the breaks are the translation's own
    d.set_asking("again")
    d._save()  # not while the model is asked
    assert not saved and d.winfo_exists()
    d.show_answers("again", [])
    d._save()
    assert saved[-1]["text"].count("\n") == 2 and saved[-1]["style"] == RegionStyle() and not cancelled
    d = review.EditBubbleDialog(hidden_root, _region(), [], on_save=saved.append, on_drop=lambda: None,
                                on_cancel=lambda: cancelled.append(2))
    d.destroy()
    d.destroy()
    assert cancelled == [2]  # Cancel, Esc, the close button: the page as it was, once


def test_the_editor_asks_for_a_preview_after_a_pause_and_says_what_could_not_be_done(hidden_root):
    asked = []
    d = review.EditBubbleDialog(hidden_root, _region(), [], on_save=lambda data: None, on_drop=lambda: None,
                                on_preview=lambda text, style: asked.append((text, style)))
    assert d._preview_job is None
    d.align_var.set("left")
    d.text.insert("end", "!")
    d._text_changed()
    assert d._preview_job is not None and not asked  # waiting for the reader to pause
    d._preview()
    assert asked == [("Nice weather today, huh?!", RegionStyle(align="left"))]
    d.font_var.set("No Such Font 12345")
    d.show_fit(("no-fit", "font-missing"), 22)
    line = d.fit_var.get()
    assert line.startswith("The text does not fit at this size") and "\"No Such Font 12345\" is not installed" in line
    assert d.size_var.get() == "22"  # automatic: the box shows the size the lettering came to
    d.show_fit(())
    assert d.fit_var.get() == ""
    set_language("de")
    d.show_fit(("font-glyphs",))
    assert d.fit_var.get().startswith("Der Schrift „No Such Font 12345“ fehlen Zeichen")
    set_language("en")
    d.destroy()
    region = _region()
    region.letter_flags = ("no-fit",)
    rows = review.review_rows([region])
    assert rows and "text does not fit" in rows[0][1]


def test_every_word_of_the_formatting_bar_is_in_every_language():
    words = [review.AUTO, review.AUTOMATIC_FONT, *review.ALIGN_WORDS.values(), *review.VALIGN_WORDS.values(),
             *review.FIT_LINES.values(), *review.FIT_REASONS.values(), "Bold", "Italic"]
    for code, catalog in CATALOGS.items():
        if code != "en":
            assert all(w in catalog for w in words), (code, [w for w in words if w not in catalog])


# ------------------------------------------------------------------ the live preview and undo
class Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Jobs:
    def put(self, job):
        job()


class Window:
    """The parts of the App that an edit, its preview, undo and redo use, on the real pipeline; jobs and timers run
    at once."""

    _record = app_mod.App._record
    _edit_region = app_mod.App._edit_region
    _preview_region = app_mod.App._preview_region
    _show_preview = app_mod.App._show_preview
    _end_preview = app_mod.App._end_preview
    undo_edit = app_mod.App.undo_edit
    redo_edit = app_mod.App.redo_edit
    _step_through = app_mod.App._step_through

    def __init__(self, pipeline, result):
        self.pipeline, self.last_result = pipeline, result
        self.history = EditHistory()
        self.role_var, self.book_var, self.lang_var = Var("translator"), Var("Book"), Var("English")
        self.reading = self.busy = False
        self._ordering = self._chosen_region = None
        self._editor = None
        self.said, self.shown = [], 0
        self._jobs = Jobs()

    def after(self, _ms, callback):
        callback()

    def _redisplay(self):
        self.shown += 1

    def _choose(self, region):
        self._chosen_region = region

    def _post(self, kind, **data):
        if kind == "result":
            self.last_result = data["result"]
        elif kind == "translate_done":
            self.busy = False
        elif kind == "status" and "key" in data:
            self.said.append(data["key"])

    def _go_busy(self):
        self.busy = True

    def say(self, key, **values):
        self.said.append(key)

    def _result_on_show(self):
        return True

    def _start_translate(self, image, complete=None, thumb=None):
        self._post("result", result=self.pipeline.process(image, complete=True))


@pytest.fixture
def window(sample_page, settings):
    cache = CacheStore(settings.cache_dir).open("Book", "m")
    ann = BookAnnotations(settings.state_dir / "annotations" / "Book.json", "Book")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache,
                        annotations=ann)
    return Window(pipeline, pipeline.process(sample_page, complete=True))


def _picture(w):
    return np.asarray(w.last_result.image).copy()


def test_the_preview_letters_one_region_on_the_page_and_cancel_puts_the_page_back(window):
    w = window
    result = w.last_result
    target = next(r for r in result.regions if r.translated_text == "It's fine.")
    before_image, before = result.image, _picture(w)
    fits = []
    w._editor = SimpleNamespace(winfo_exists=lambda: True, show_fit=lambda flags, size=None: fits.append((flags, size)))
    preview = LivePreview(result, target)
    w._preview_region(preview, "Totally fine.\nReally.", RegionStyle(align="left", size=60))
    after = _picture(w)
    changed = np.any(after != before, axis=2)
    ys, xs = np.nonzero(changed)
    assert xs.size and target.x0 <= xs.min() and xs.max() < target.x1 and target.y0 <= ys.min() and ys.max() < target.y1
    assert fits[-1] == ((NO_FIT,), 60) and w.shown == 1  # the editor says it does not fit at 60
    assert target.translated_text == "It's fine." and target.style is None and len(w.history) == 0  # nothing stored
    w._preview_region(preview, "It's fine.", RegionStyle())
    assert np.array_equal(_picture(w), before)  # automatic again: the page as it was
    w._preview_region(preview, "Fine!", RegionStyle(valign="top"))
    w._end_preview(preview)  # Cancel
    assert result.image is before_image and not preview.open
    w._preview_region(preview, "Late", RegionStyle())  # a closed editor asks for nothing
    assert result.image is before_image


def test_a_formatting_edit_is_saved_taken_back_and_made_again(window):
    w = window
    target = next(r for r in w.last_result.regions if r.translated_text == "Thank you.")
    picture = _picture(w)
    preview = LivePreview(w.last_result, target)
    style = RegionStyle(align="left", valign="top", size=24, bold=True, letter_spacing=2)
    w._preview_region(preview, "Thanks a lot.\nReally.", style)
    shown = _picture(w)
    w._end_preview(preview, keep=True)  # Save: the preview stays until the saved page comes
    assert np.array_equal(_picture(w), shown)
    w._edit_region(target, {"text": "Thanks a lot.\nReally.", "speaker": "", "kind": "", "continues": False, "note": "",
                            "reader_note": "", "style": style})
    edited = _picture(w)
    assert np.array_equal(edited, shown) and target.style == style and target.translated_text == "Thanks a lot.\nReally."
    unit = w.last_result.units[0]
    note = w.pipeline.annotations.lookup(unit.fingerprint, unit.aspect, 6).note_at(unit.normalize(target.bbox))
    assert note.style == style
    w.undo_edit()
    assert w.said[-1] == "Edit taken back." and target.style is None and target.translated_text == "Thank you."
    assert np.array_equal(_picture(w), picture)
    assert w.pipeline.annotations.lookup(unit.fingerprint, unit.aspect, 6) is None or not any(
        not n.style.is_empty for n in w.pipeline.annotations.lookup(unit.fingerprint, unit.aspect, 6).notes)
    w.redo_edit()
    assert w.said[-1] == "Edit made again." and target.style == style and np.array_equal(_picture(w), edited)
    w._edit_region(target, {"text": target.translated_text, "speaker": "", "kind": "", "continues": False, "note": "",
                            "reader_note": "", "style": RegionStyle(align="left", valign="top", size=24, bold=True,
                                                                     letter_spacing=2)})
    assert len(w.history) == 1  # the same formatting saved again changes nothing
    w._edit_region(target, {"text": target.translated_text, "speaker": "", "kind": "", "continues": False, "note": "",
                            "reader_note": "", "style": RegionStyle()})  # Reset formatting, saved
    assert target.style is None and len(w.history) == 2
    w.undo_edit()
    assert target.style == style and np.array_equal(_picture(w), edited)
    w.pipeline.annotations = None
    w._edit_region(target, {"text": target.translated_text, "speaker": "", "kind": "", "continues": False, "note": "",
                            "reader_note": "", "style": RegionStyle(size=12)})
    assert w.said[-1] == "Could not store the formatting: give the book a name first (the Book field)."
    assert target.style == style
