"""Lettering styles: stressed runs, italic and bold faces (the family's cuts or synthetic), the style guide's
lettering per kind, and what the pipeline sets a region in."""

from __future__ import annotations

import shutil

import numpy as np
import pytest
from PIL import Image

from taslation.annotations import DEFAULT_LETTERING, LETTERING_KINDS, Glossary, GlossaryStore, LetteringStyle, StyleGuide
from taslation.pipeline import Pipeline
from taslation.regions import TextRegion
from taslation.render import (FontSpec, Lettering, balance_marks, letter_text, face_of, find_font, font_faces,
                              load_font, make_lettering, split_runs, strip_marks, styled_font)
from taslation.render.typeset import text_width


def _installed_font() -> str:
    spec = find_font()
    if not spec.path:
        pytest.skip("no font file on this computer")
    return spec.path


def _ink(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("L")) < 128


def _stem_edges(ink: np.ndarray) -> tuple[int, int]:
    """The leftmost ink column in the top three rows and in the bottom three rows of a glyph."""
    rows = np.flatnonzero(ink.any(axis=1))
    top = min(int(np.flatnonzero(ink[r]).min()) for r in rows[:3])
    bottom = min(int(np.flatnonzero(ink[r]).min()) for r in rows[-3:])
    return top, bottom


def test_stressed_runs_are_marked_with_asterisks():
    assert split_runs("I *really* do") == [("I ", False), ("really", True), (" do", False)]
    assert split_runs("*not now*") == [("not now", True)]
    assert split_runs("now* and *then") == [("now", True), (" and ", False), ("then", True)]  # a span split over two lines
    assert split_runs("*not") == [("not", True)] and split_runs("5 * 3") == [("5 * 3", False)] and split_runs("") == []
    assert strip_marks("*Hey* you") == "Hey you" and strip_marks("plain") == "plain"
    assert balance_marks("I *really* do") == "I *really* do" and balance_marks("*oops, a stray") == "oops, a stray"
    assert balance_marks("one *two* three*") == "one two three" and balance_marks("5 * 3") == "5 * 3"


def test_markers_take_no_room_and_stressed_words_carry_more_ink():
    path = _installed_font()
    sf = styled_font(Lettering(path), 30)
    plain = load_font(path, 30)
    assert sf.width("really") == text_width(plain, "really")
    assert sf.width("*really*") < text_width(plain, "*really*")
    assert sf.width("I *really* do") >= sf.width("I really do")
    a, b, c = (Image.new("RGB", (400, 60), (255, 255, 255)) for _ in range(3))
    sf.draw(a, 5, 5, "Hi *there*", (0, 0, 0))
    styled_font(Lettering(path, emphasis=False), 30).draw(b, 5, 5, "Hi *there*", (0, 0, 0))
    styled_font(Lettering(path, emphasis=False), 30).draw(c, 5, 5, "Hi there", (0, 0, 0))
    assert abs(int(_ink(b).sum()) - int(_ink(c).sum())) <= 0.03 * _ink(c).sum()  # without emphasis the markers just vanish
    assert _ink(a).sum() > _ink(c).sum() * 1.05  # with it, the stressed word is heavier


def test_synthetic_italic_leans_and_synthetic_bold_thickens():
    upright, leant, bold = (Image.new("RGB", (120, 80), (255, 255, 255)) for _ in range(3))
    styled_font(Lettering(None), 40).draw(upright, 10, 5, "l", (0, 0, 0))  # Pillow's own font: no cuts, so synthetic
    styled_font(Lettering(None, italic=True), 40).draw(leant, 10, 5, "l", (0, 0, 0))
    styled_font(Lettering(None, bold=True), 40).draw(bold, 10, 5, "l", (0, 0, 0))
    top, bottom = _stem_edges(_ink(upright))
    assert abs(top - bottom) <= 2
    top, bottom = _stem_edges(_ink(leant))
    assert top - bottom >= 4  # the top of the stem is to the right of its foot
    assert _ink(bold).sum() > _ink(upright).sum() * 1.15


def test_the_familys_cuts_are_found_by_their_names():
    path = _installed_font()
    lt = make_lettering(FontSpec(path), "", True, True)
    assert lt.path == path and lt.italic and lt.bold
    family = face_of(path).family
    cuts = [f for f in font_faces() if f.family == family and f.path != path]
    has_italic = any("italic" in f.subfamily.lower() or "oblique" in f.subfamily.lower() for f in cuts)
    assert (lt.italic_path is not None) == has_italic
    if lt.italic_path:
        assert face_of(lt.italic_path).family == family
        img = Image.new("RGB", (300, 60), (255, 255, 255))
        styled_font(lt, 30).draw(img, 5, 5, "Hi *there*", (0, 0, 0))
        assert _ink(img).any()
    assert make_lettering(FontSpec(None), "", True, True) == Lettering(None, False, True, True)


def test_the_style_guide_letters_each_kind(tmp_path):
    sg = StyleGuide()
    assert sg.lettering_for("thought").italic and sg.lettering_for("shout").bold and not sg.lettering_for("narration").italic
    sg.lettering_for("thought").italic = False  # a copy: the default is untouched
    assert DEFAULT_LETTERING["thought"].italic and sg.to_json() == {}
    sg = StyleGuide.from_json({"lettering": {"thought": {}, "narration": {"font": "Noto Serif", "bold": True},
                                             "bogus": {"italic": True}, "shout": "x"}})
    assert set(sg.lettering) == {"thought", "narration"} and not sg.lettering_for("thought").italic  # explicitly plain
    assert sg.lettering_for("narration") == LetteringStyle(font="Noto Serif", bold=True) and sg.lettering_for("shout").bold
    assert sg.to_json() == {"lettering": {"thought": {}, "narration": {"font": "Noto Serif", "bold": True}}}
    store = GlossaryStore(tmp_path / "gl")
    g = store.open("Series")
    g.style = sg
    g.save()
    assert store.open("Series").style.lettering == sg.lettering and g.format() == ""  # the model is not told
    other = StyleGuide(lettering={"thought": LetteringStyle(italic=True), "sfx": LetteringStyle(font="Bangers")})
    assert sg.fill_from(other) == 1 and sg.lettering["sfx"].font == "Bangers" and not sg.lettering["thought"].italic
    assert set(LETTERING_KINDS) == {"thought", "shout", "narration", "handwritten", "sfx"}


def test_the_pipeline_sets_each_kind_in_its_lettering(settings, tmp_path):
    path = _installed_font()
    settings.models_dir = tmp_path / "models"
    settings.fonts_dir.mkdir(parents=True)
    mine, narr = settings.fonts_dir / "MyLetter-Bold.ttf", tmp_path / "MyNarr-Regular.ttf"
    shutil.copy(path, mine)
    shutil.copy(path, narr)
    p = Pipeline(settings, ocr=None, translator=None)
    assert p.lettering_for("Hello", "thought").italic and p.lettering_for("Hello", "shout").bold
    assert not p.lettering_for("Hello").italic and not p.lettering_for("Hello").bold
    g = Glossary(tmp_path / "sheet.json", "Series")
    g.style = StyleGuide(font="MyLetter", lettering={"thought": LetteringStyle(), "narration": LetteringStyle(font=str(narr)),
                                                     "sfx": LetteringStyle(font="No Such Font 12345", bold=True)})
    p.glossary = g
    thought = p.lettering_for("Hello", "thought")
    assert not thought.italic and thought.path == str(mine)
    assert p.lettering_for("Hello", "narration").path == str(narr)  # the kind's own font
    sfx = p.lettering_for("Hello", "sfx")
    assert sfx.path == str(mine) and sfx.bold  # a font this computer lacks: the sheet's lettering font
    mask = np.full((200, 300), 255, np.uint8)
    r = TextRegion(0, 0, 300, 200, mask, (50, 50, 250, 150), tag="thought")
    img = Image.new("RGB", (300, 200), (255, 255, 255))
    assert letter_text(img, r, "Did she *really* say that?", p.lettering_for("x", r.tag), 9, 60).size >= 9
    assert _ink(img).any()
    assert p.set_size(mask, "Did she *really* say that?", "bubble", (50, 50, 250, 150), 0, 0, "thought") >= 9


def test_a_stray_marker_from_the_model_is_dropped_before_the_translation_is_kept(settings):
    from taslation.translate import DictTranslator

    p = Pipeline(settings, ocr=None, translator=DictTranslator({"魔法少女だ": "*A magical girl."}))
    entries = [{"ja": "魔法少女だ", "text": "*A magical girl.", "mask": np.full((300, 400), 255, np.uint8), "kind": "bubble",
                "anchor": (100, 100, 300, 200), "x0": 0, "y0": 0, "meta": {}}]
    assert p.tighten(entries) == ["A magical girl."]
    assert p.tighten([{**entries[0], "text": "A *magical* girl."}]) == ["A *magical* girl."]
