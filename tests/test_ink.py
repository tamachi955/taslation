"""A region's ink: the text colour (automatic black or white from the ground, black, white or a colour of the reader's)
and the outline (automatic on a drawing, on or off) in its own colour (automatic: the opposite of the text's), per
region in the region editor and per kind in the series sheet, the region's own winning over its kind's, which wins
over the automatic; on every lettering path (across, slanted, turned a quarter, stacked) and never changing where the
lines go. With nothing set, the lettering is byte for byte what it was before the ink could be set (`GOLDEN`, hashes
made before the change, on this computer's font; and the same calls with the old arguments)."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
from helpers import EN_TEXTS, FakeOcr
from PIL import Image

from test_formatting import Window, window  # noqa: F401 - the fixture: an edit, undo and redo on the real pipeline

from taslation.annotations import BookAnnotations, Glossary, LetteringStyle, RegionStyle, StyleGuide, ink_of
from taslation.cache import CacheStore
from taslation.i18n import CATALOGS, set_language
from taslation.pipeline import Pipeline
from taslation.regions import TextRegion
from taslation.render import find_font
from taslation.render.typeset import TextFormat, letter_text
from taslation.translate import DictTranslator
from taslation.ui.dialogs import review

TEXT = "Why on earth did you weld the hatch shut, Pyo? That really hurt."


def _font() -> str:
    spec = find_font()
    if not spec.path:
        pytest.skip("no font file on this computer")
    return spec.path


def _ellipse(w=200, h=300):
    yy, xx = np.mgrid[0:h, 0:w]
    inside = ((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2 <= 1.0
    return (inside * 255).astype(np.uint8)


def _art(w=200, h=300):
    """A busy ground: stripes a drawing or a tone would give."""
    yy, xx = np.mgrid[0:h, 0:w]
    grey = np.where(((xx + yy) // 6) % 2 == 0, 40, 215).astype(np.uint8)
    return Image.fromarray(np.stack([grey] * 3, axis=2))


def _region(angle=0.0):
    mask = _ellipse()
    region = TextRegion(0, 0, mask.shape[1], mask.shape[0], mask, (60, 100, 140, 200))
    region.angle = angle
    return region


# (name, ground colour, ground picture, region angle, letter_text keyword arguments as before the ink)
CASES = (
    ("plain", (255, 255, 255), None, 0.0, {}),
    ("dark", (30, 30, 30), None, 0.0, {}),
    ("art", (255, 255, 255), "art", 0.0, {}),
    ("outline-on", (255, 255, 255), None, 0.0, {"outline": True}),
    ("outline-off", (255, 255, 255), "art", 0.0, {"outline": False}),
    ("formatted", (255, 255, 255), None, 0.0, {"fmt": TextFormat(align="left", size=20)}),
    ("formatted-overflow", (255, 255, 255), "art", 0.0, {"fmt": TextFormat(size=60)}),
    ("slanted", (255, 255, 255), "art", 15.0, {}),
    ("turned", (30, 30, 30), None, 0.0, {"direction": "down"}),
    ("stacked", (255, 255, 255), "art", 0.0, {"direction": "stacked"}),
    ("stacked-slanted", (30, 30, 30), None, 10.0, {"direction": "stacked"}),
)


def lettered(name: str, extra: dict | None = None) -> np.ndarray:
    """The picture case *name* letters (with *extra* keyword arguments added to its own)."""
    return lettered_with(name, extra)[0]


def lettered_with(name: str, extra: dict | None = None):
    """`lettered`, and what the lettering said it did (its size, its flags, the layout that won)."""
    _name, ground, picture, angle, kwargs = next(c for c in CASES if c[0] == name)
    image = _art() if picture == "art" else Image.new("RGB", (200, 300), ground)
    done = letter_text(image, _region(angle), TEXT, _font(), 9, 60, background=ground, **kwargs, **(extra or {}))
    return np.asarray(image).copy(), done


def pages(sample_page, sample_page2, settings) -> dict[str, np.ndarray]:
    out = {}
    for name, page in (("sample_page", sample_page), ("sample_page2", sample_page2)):
        cache = CacheStore(settings.cache_dir / name).open("Book", "m")
        p = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache)
        out[name] = np.asarray(p.process(page).image).copy()
    return out


def digest(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()[:16]


def font_identity() -> tuple[str, int]:
    path = Path(_font().split("#")[0])
    return path.name, path.stat().st_size if path.is_file() else 0


# made before the ink could be set (on the code of 933328b; the cases made again there when TEXT got its invented
# name), on the font they name: a computer whose automatic font is another file letters other pixels, and checks the
# old arguments against the new ones only
GOLDEN: dict[str, object] = {
    "font": ("comicbd.ttf", 255972),
    "plain": "2cbe892dad08611a",
    "dark": "7e45ea956e48b758",
    "art": "7e01f4cabf1983dc",
    "outline-on": "2058c67e6a82143f",
    "outline-off": "80bbc2f98242063e",
    "formatted": "8210f6e268099f23",
    "formatted-overflow": "27ae3889d946c5e1",
    "slanted": "b3b7890be6c927d9",
    "turned": "f9a8858d8dc0d615",
    "stacked": "305bf8ef17914411",
    "stacked-slanted": "1bc246b71218707a",
    "sample_page": "288f7e8a1a151eb3",
    "sample_page2": "61d12727f2653615",
}
AUTOMATIC = {"color": None, "outline_color": None}  # the ink's own arguments, automatic


# ------------------------------------------------------------------ nothing set: as before, byte for byte
@pytest.mark.parametrize("name", [c[0] for c in CASES])
def test_with_no_ink_set_every_path_letters_as_before(name):
    old = lettered(name)
    assert np.array_equal(lettered(name, AUTOMATIC), old)  # the new arguments, automatic: the old arguments' pixels
    if font_identity() != GOLDEN["font"]:
        pytest.skip("another automatic font on this computer: the hashes were made with another")
    assert digest(old) == GOLDEN[name]


def test_with_no_style_or_an_empty_one_both_fixture_pages_are_as_before(sample_page, sample_page2, settings):
    shown = pages(sample_page, sample_page2, settings)
    for name, page in (("sample_page", sample_page), ("sample_page2", sample_page2)):
        cache = CacheStore(settings.cache_dir / ("again-" + name)).open("Book", "m")
        p = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache)
        result = p.process(page)
        assert np.array_equal(np.asarray(result.image), shown[name])
        for r in result.regions:  # an empty style is no style
            r.style = RegionStyle()
        p.rerender(result)
        assert np.array_equal(np.asarray(result.image), shown[name])
        if font_identity() == GOLDEN["font"]:
            assert digest(shown[name]) == GOLDEN[name]


# ------------------------------------------------------------------ the ink on every path
RED, BLUE = (200, 30, 40), (20, 40, 210)


def _near(array: np.ndarray, colour, tolerance=40) -> np.ndarray:
    return np.all(np.abs(array.astype(int) - np.array(colour)) <= tolerance, axis=2)


def _drawn(array: np.ndarray, ground: np.ndarray) -> np.ndarray:
    return np.any(array != ground, axis=2)


def _ground(name: str) -> tuple[tuple[int, int, int], np.ndarray]:
    _n, ground, picture, _a, _k = next(c for c in CASES if c[0] == name)
    return ground, np.asarray(_art() if picture == "art" else Image.new("RGB", (200, 300), ground))


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    return float((a & b).sum()) / max(1, int((a | b).sum()))


@pytest.mark.parametrize("name", ["plain", "dark", "formatted", "slanted", "turned", "stacked", "stacked-slanted"])
def test_a_text_colour_colours_the_letters_on_every_path_and_moves_none(name):
    ground, base = _ground(name)
    old, was = lettered_with(name)
    red, done = lettered_with(name, {"color": RED})
    assert done == was  # the same size, flags and layout: the colour moves no line
    assert _iou(_drawn(red, base), _drawn(old, base)) > 0.95  # the same letters at the same places (edges blend)
    assert _near(red, RED)[_drawn(red, base)].mean() > 0.2 and not _near(old, RED).any()  # (an outline on art too)
    automatic = (0, 0, 0) if ground == (255, 255, 255) else (255, 255, 255)
    assert np.array_equal(lettered(name, {"color": automatic}), old)  # the automatic colour named: the same pixels


def test_the_outline_forced_on_or_off_and_in_its_own_colour():
    plain, on = lettered("plain"), lettered("plain", {"outline": True})
    assert np.array_equal(on, lettered("outline-on")) and not np.array_equal(on, plain)
    assert np.array_equal(lettered("art", {"outline": False}), lettered("outline-off"))
    assert not np.array_equal(lettered("art"), lettered("outline-off"))  # on a drawing the outline is automatic
    blue, done = lettered_with("plain", {"outline": True, "outline_color": BLUE})
    assert _near(blue, BLUE).sum() > 50 and not _near(on, BLUE).any() and not _near(plain, BLUE).any()
    red_rim = lettered("plain", {"outline": True, "outline_color": RED})
    _ground_colour, base = _ground("plain")
    assert done == lettered_with("plain")[1] and np.array_equal(_drawn(blue, base), _drawn(red_rim, base))
    # the automatic outline round a colour of the reader's: white round a dark one, black round a light one
    dark = lettered("plain", {"color": (90, 0, 0), "outline": True})
    light = lettered("dark", {"color": (250, 230, 120), "outline": True})
    assert _near(dark, (255, 255, 255), 10)[_drawn(dark, base)].any()
    assert _near(light, (0, 0, 0), 10).sum() > 50
    for name in ("formatted-overflow", "stacked", "slanted", "turned", "stacked-slanted"):
        drawn = lettered(name, {"outline": True, "outline_color": BLUE, "color": RED})
        assert _near(drawn, BLUE).sum() > 30 and _near(drawn, RED).sum() > 30, name


def test_colour_codes_and_their_colours():
    from taslation.annotations import ink_code
    from taslation.render.typeset import ink_rgb, opposite_ink

    assert [ink_code(v) for v in ("", "black", " White ", "#A0b1C2", "#abc", "red", "#gg0000", 3, None)] == [
        "", "black", "white", "#a0b1c2", "", "", "", "", ""]
    assert ink_rgb("black") == (0, 0, 0) and ink_rgb("white") == (255, 255, 255) and ink_rgb("#ff8000") == (255, 128, 0)
    assert ink_rgb("") is None and ink_rgb("#xyz123") is None and ink_rgb("blue") is None
    assert opposite_ink((0, 0, 0)) == (255, 255, 255) and opposite_ink((255, 255, 255)) == (0, 0, 0)
    assert opposite_ink((200, 30, 40)) == (255, 255, 255) and opposite_ink((250, 230, 120)) == (0, 0, 0)


# ------------------------------------------------------------------ what keeps the ink: the annotations, the sheet
def test_a_regions_ink_is_kept_only_when_set_checked_and_formats_nothing(tmp_path):
    style = RegionStyle(colour="#C03030", outline=False, outline_colour="white")
    assert style.colour == "#C03030"  # (as made; a file's and the editor's go through `make`)
    made = RegionStyle.make(colour="#C03030", outline=False, outline_colour="white")
    assert made == RegionStyle(colour="#c03030", outline=False, outline_colour="white")
    assert made.to_json() == {"colour": "#c03030", "outline": False, "outline_colour": "white"}
    assert RegionStyle.from_json(made.to_json()) == made and not made.is_empty
    assert made.formats_nothing and RegionStyle(outline=True).formats_nothing  # a colour alone lays out nothing
    assert not RegionStyle(colour="black", size=20).formats_nothing
    odd = RegionStyle.from_json({"colour": "red", "outline": "yes", "outline_colour": "#12345"})
    assert odd == RegionStyle() and RegionStyle.from_json({"size": 20}).colour == ""  # files of before: automatic
    assert RegionStyle().to_json() == {}
    ann = BookAnnotations(tmp_path / "Book.json", "Book")
    ann.page("c" * 80, 0.7).set_style((0.1, 0.1, 0.3, 0.3), made)
    ann.save()
    again = BookAnnotations.load(tmp_path / "Book.json").pages[0].note_at((0.1, 0.1, 0.3, 0.3))
    assert again.style == made


def test_a_kinds_ink_in_the_series_sheet_and_which_one_wins():
    ls = LetteringStyle(italic=True, colour="WHITE", outline=True, outline_colour="#00ff00")
    assert ls.to_json() == {"italic": True, "colour": "WHITE", "outline": True, "outline_colour": "#00ff00"}
    back = LetteringStyle.from_json(ls.to_json())
    assert back == LetteringStyle(italic=True, colour="white", outline=True, outline_colour="#00ff00")
    assert LetteringStyle.from_json({"bold": True}) == LetteringStyle(bold=True)  # sheets of before: automatic ink
    assert LetteringStyle.from_json({"colour": "teal", "outline": 1}) == LetteringStyle()
    guide = StyleGuide.from_json({"lettering": {"shout": back.to_json()}})
    assert guide.lettering_for("shout") == back and guide.lettering_for("thought") == LetteringStyle(italic=True)
    # the region's own wins over the kind's, which wins over the automatic
    assert ink_of(None, None) == ("", None, "") and ink_of(RegionStyle(), LetteringStyle()) == ("", None, "")
    assert ink_of(None, back) == ("white", True, "#00ff00")
    assert ink_of(RegionStyle(colour="black"), back) == ("black", True, "#00ff00")
    assert ink_of(RegionStyle(outline=False, outline_colour="black"), back) == ("white", False, "black")
    assert ink_of(RegionStyle(colour="#123456"), None) == ("#123456", None, "")


def test_a_review_of_two_sheets_names_a_kinds_ink():
    from taslation.ui.dialogs import conflicts

    assert conflicts._lettering(LetteringStyle()) == "plain"
    assert conflicts._lettering(LetteringStyle(bold=True, colour="white", outline=False)) == \
        "bold, text colour White, without outline"
    assert conflicts._lettering(LetteringStyle(outline=True, outline_colour="#ff0000")) == \
        "with outline, outline colour #ff0000"


# ------------------------------------------------------------------ the pipeline: per region, per kind, the preview
def _pipeline(settings, sample_page, sheet=None):
    cache = CacheStore(settings.cache_dir).open("Book", "m")
    ann = BookAnnotations(settings.state_dir / "annotations" / "Book.json", "Book")
    p = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache,
                 annotations=ann)
    p.glossary = sheet
    return p, p.process(sample_page, complete=True)


def _inside(array: np.ndarray, region) -> np.ndarray:
    return array[region.y0:region.y1, region.x0:region.x1]


def test_the_pipeline_letters_a_regions_ink_kind_defaults_and_keeps_the_layout(sample_page, settings, tmp_path):
    p, res = _pipeline(settings, sample_page)
    target = next(r for r in res.regions if r.translated_text == "Nice weather today, huh?")
    plain, size = np.asarray(res.image).copy(), target.font_size
    assert p.set_region_style(res, target, RegionStyle(colour="#c03030"))
    p.rerender(res)
    red = np.asarray(res.image).copy()
    changed = np.any(red != plain, axis=2)
    ys, xs = np.nonzero(changed)
    assert xs.size and target.x0 <= xs.min() and xs.max() < target.x1 and target.y0 <= ys.min() and ys.max() < target.y1
    assert _near(_inside(red, target), (192, 48, 48)).sum() > 50 and target.font_size == size  # the same size
    assert target.letter_flags == ()
    again = p.process(sample_page, complete=True)  # read again: the ink comes from the annotations
    twin = next(r for r in again.regions if r.translated_text == "Nice weather today, huh?")
    assert twin.style == RegionStyle(colour="#c03030") and np.array_equal(np.asarray(again.image), red)
    bed = p.page_without(again, twin)  # the editor's preview letters the ink the bar shows
    preview, _done = p.preview_region(bed, twin, twin.translated_text, RegionStyle(colour="#2040d0"))
    assert _near(_inside(preview, twin), (32, 64, 208)).sum() > 50 and twin.style == RegionStyle(colour="#c03030")
    automatic, _done = p.preview_region(bed, twin, twin.translated_text, RegionStyle())
    assert np.array_equal(automatic, plain)

    # the kind's ink from the series sheet, under the region's own
    sheet = Glossary(tmp_path / "sheet.json", "Series")
    sheet.style = StyleGuide(lettering={"shout": LetteringStyle(colour="#2040d0", outline=True,
                                                                outline_colour="#30c030")})
    p2, res2 = _pipeline(settings, sample_page, sheet)
    shout = next(r for r in res2.regions if r.translated_text == "Thank you.")
    other = next(r for r in res2.regions if r.translated_text == "Nice weather today, huh?")
    before = np.asarray(res2.image).copy()
    assert p2.set_region_note(res2, shout, kind="shout")
    p2.rerender(res2)
    sheeted = np.asarray(res2.image).copy()
    assert _near(_inside(sheeted, shout), (32, 64, 208)).sum() > 50 and _near(_inside(sheeted, shout), (48, 192, 48)).sum() > 20
    assert np.array_equal(_inside(sheeted, other), _inside(before, other))  # another kind: as it was
    assert p2.set_region_style(res2, shout, RegionStyle(colour="black", outline=False))
    p2.rerender(res2)
    own = np.asarray(res2.image)
    assert not _near(_inside(own, shout), (32, 64, 208)).any() and not _near(_inside(own, shout), (48, 192, 48)).any()


def test_a_style_change_of_the_ink_is_saved_taken_back_and_made_again(window):
    w = window
    target = next(r for r in w.last_result.regions if r.translated_text == "Thank you.")
    picture = np.asarray(w.last_result.image).copy()
    style = RegionStyle(colour="#c03030", outline=True, outline_colour="black")
    w._edit_region(target, {"text": target.translated_text, "speaker": "", "kind": "", "continues": False, "note": "",
                            "reader_note": "", "style": style})
    inked = np.asarray(w.last_result.image).copy()
    assert target.style == style and not np.array_equal(inked, picture)
    w.undo_edit()
    assert w.said[-1] == "Edit taken back." and target.style is None
    assert np.array_equal(np.asarray(w.last_result.image), picture)
    w.redo_edit()
    assert target.style == style and np.array_equal(np.asarray(w.last_result.image), inked)


# ------------------------------------------------------------------ the editor's bar and the series sheet
def _editor(root, style=None, chooser=None):
    from taslation.pipeline import manual_region

    region = manual_region(np.full((300, 400, 3), 255, np.uint8), (20, 20, 198, 199))
    region.status, region.translated_text, region.font_size = "translated", "Nice weather today, huh?", 31
    region.style = style
    asked = []
    d = review.EditBubbleDialog(root, region, [], on_save=lambda data: None, on_drop=lambda: None,
                                on_preview=lambda text, s: asked.append(s))
    if chooser is not None:
        for choice in (d.colour_choice, d.outline_choice):
            choice.chooser = chooser
    return d, asked


def test_the_formatting_bar_shows_the_ink_gives_it_back_and_resets_it(hidden_root):
    style = RegionStyle(colour="#c03030", outline=False, outline_colour="white")
    d, _asked = _editor(hidden_root, style)
    assert d.style() == style and d.bar.winfo_manager()  # a region with a formatting: the bar is open
    assert d.colour_choice.var.get() == "Custom..." and d.colour_choice.swatch.cget("text") == "#c03030"
    assert d.outline_var.get() == "No outline" and d.outline_choice.var.get() == "White"
    d.reset_btn.invoke()
    assert d.style() == RegionStyle() and d.colour_choice.var.get() == "Auto" and d.outline_var.get() == "Auto"
    assert not d.colour_choice.swatch.winfo_manager()
    d.set_style(RegionStyle(colour="black", outline=True))
    assert d.style() == RegionStyle(colour="black", outline=True) and d.outline_var.get() == "With outline"
    d.destroy()


def test_custom_opens_the_colour_chooser_and_a_cancel_keeps_what_was_shown(hidden_root):
    answers = ["#2040D0", ""]
    asked = []

    def chooser(parent, initial):
        asked.append(initial)
        return answers.pop(0) if answers else ""

    d, previews = _editor(hidden_root, chooser=chooser)
    choice = d.colour_choice
    choice.var.set("Custom...")
    choice._picked()
    assert asked == [""] and d.style().colour == "#2040d0" and choice.var.get() == "Custom..."
    d._preview()
    assert previews[-1] == RegionStyle(colour="#2040d0")  # the page behind the editor shows it
    choice.choose()  # the swatch clicked: the chooser again, from the colour shown; cancelled, nothing changes
    assert asked == ["", "#2040d0"] and d.style().colour == "#2040d0"
    choice.var.set("White")
    choice._picked()
    assert d.style().colour == "white" and not choice.swatch.winfo_manager()
    choice.var.set("Custom...")
    choice._picked()  # cancelled: the list shows White again
    assert d.style().colour == "white" and choice.var.get() == "White"
    d.outline_var.set("With outline")
    assert d.style() == RegionStyle(colour="white", outline=True) and d._preview_job is not None
    d.destroy()


def test_the_series_sheet_keeps_each_kinds_ink(hidden_root, tmp_path, monkeypatch):
    from taslation.annotations import GlossaryStore
    from taslation.ui.dialogs import glossary

    store = GlossaryStore(tmp_path / "glossary")
    sheet = store.open("Series", "English")
    sheet.style = StyleGuide(lettering={"thought": LetteringStyle(italic=True, colour="#806040")})
    sheet.save()
    d = glossary.GlossaryDialog(hidden_root, store, "Series", "English", on_change=lambda: None)
    d.withdraw()
    colour, outline, rim = d.kind_inks["thought"]
    assert colour.get() == "#806040" and outline.get() == "Auto" and rim.get() == ""
    shout_colour, shout_outline, shout_rim = d.kind_inks["shout"]
    shout_colour.set("white")
    shout_outline.set("With outline")
    shout_rim.set("#000000")
    d._set_style()
    kept = store.open("Series", "English").style
    assert kept.lettering_for("shout") == LetteringStyle(bold=True, colour="white", outline=True,
                                                         outline_colour="#000000")
    assert kept.lettering_for("thought") == LetteringStyle(italic=True, colour="#806040")
    d.undo()  # the dialog's Undo: the kind's ink as it was, in the fields too
    assert store.open("Series", "English").style.lettering_for("shout") == LetteringStyle(bold=True)
    assert shout_colour.get() == "" and shout_outline.get() == "Auto" and shout_rim.get() == ""
    d.destroy()


def test_every_word_of_the_ink_is_in_every_language():
    from taslation.ui.dialogs import glossary

    words = [*review.INK_WORDS.values(), review.CUSTOM_INK, review.CHOOSE_INK, *review.OUTLINE_WORDS.values(),
             *review.INK_TIPS.values(), *glossary.KIND_INK_TIPS.values(), *(w for _c, w in glossary.INK_HEADINGS)]
    for code, catalog in CATALOGS.items():
        if code != "en":
            assert all(w in catalog for w in words), (code, [w for w in words if w not in catalog])
    set_language("ja")
    assert review.ink_word("black") == "黒" and review.outline_of("縁取りなし") is False
    set_language("en")
