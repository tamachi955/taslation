"""Fonts by name: the names in the font files, glyph coverage, the series sheet's suggestion, and the pipeline's use of it."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from taslation.annotations import Glossary, StyleGuide
from taslation.pipeline import Pipeline
from taslation.render import covers, face_of, find_font, font_faces, load_font, resolve_font, split_face


def _installed_font() -> str:
    spec = find_font()
    if not spec.path:
        pytest.skip("no font file on this computer")
    return spec.path


def test_names_and_glyph_coverage_come_from_the_font_file():
    path = _installed_font()
    face = face_of(path)
    assert face is not None and face.family and face.file == path
    assert covers(path, "Hello, world! 123") and covers(path, " \n")
    assert not covers(path, "\U0010FFFD") and not covers(None, "x") and not covers(path + "#9", "x")
    assert split_face("C:/f/a.ttc#2") == ("C:/f/a.ttc", 2) and split_face("a#b.ttf") == ("a#b.ttf", 0)


def test_resolve_font_by_the_names_in_the_files_or_the_file_name(tmp_path):
    path = _installed_font()
    face = face_of(path)
    found = resolve_font(face.family)
    assert found and face_of(found.path).family == face.family
    assert not resolve_font("No Such Font 12345") and not resolve_font("")
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    mine = fonts / "MyLetter-Bold.ttf"
    shutil.copy(path, mine)
    assert resolve_font("MyLetter", fonts).path == str(mine)  # the file's name, when the family inside differs
    assert resolve_font("my letter bold", fonts).path == str(mine)
    assert resolve_font(str(mine)).path == str(mine)  # a path works, on this computer
    assert str(mine) in [f.file for f in font_faces(fonts)]


def test_find_font_takes_the_suggestion_only_where_installed_and_covering(tmp_path):
    path = _installed_font()
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    mine = fonts / "MyLetter-Bold.ttf"
    shutil.copy(path, mine)
    pref = tmp_path / "pref.ttf"
    shutil.copy(path, pref)
    assert find_font(str(pref), fonts, "Hello", "English", suggested="MyLetter").path == str(mine)  # the sheet's font first
    assert find_font(str(pref), fonts, "", "English", suggested="MyLetter").path == str(mine)
    assert find_font(str(pref), fonts, "\U0010FFFD", "English", suggested="MyLetter").path == str(pref)  # no glyph: the reader's file
    assert find_font(str(pref), fonts, "Hello", "English", suggested="No Such Font 12345").path == str(pref)
    assert find_font("", fonts, "Hello", "English").path == str(mine)  # no suggestion: as before


@pytest.mark.skipif(sys.platform != "win32" or not Path(r"C:\Windows\Fonts\YuGothB.ttc").is_file(),
                    reason="Yu Gothic UI is a face of a Windows font collection")
def test_a_face_of_a_collection_is_named_by_its_index():
    spec = resolve_font("Yu Gothic UI")
    assert spec.path.lower().endswith("yugothb.ttc#1")
    assert load_font(spec.path, 20).getname() == ("Yu Gothic UI", "Bold")
    assert covers(spec.path, "日本語 Hello")


def test_the_pipeline_uses_the_sheets_font_and_reports_a_missing_one(settings, tmp_path):
    path = _installed_font()
    settings.models_dir = tmp_path / "models"
    settings.fonts_dir.mkdir(parents=True)
    mine = settings.fonts_dir / "MyLetter-Bold.ttf"
    shutil.copy(path, mine)
    p = Pipeline(settings, ocr=None, translator=None)
    assert p.suggested_font == "" and p.font_status() == ("", None)
    g = Glossary(tmp_path / "sheet.json", "Series")
    g.style = StyleGuide(font="MyLetter")
    p.glossary = g
    assert p.font_status() == ("MyLetter", str(mine)) and p.font_for("Hello").path == str(mine) and p.font_path == str(mine)
    g.style.font = "No Such Font 12345"
    assert p.font_status() == ("No Such Font 12345", None)
    assert p.font_for("Hello").path  # the automatic choice
