"""The lettering font is chosen by what its cmap covers, and a letter it lacks is drawn from the glyphs it has."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from taslation.config import Settings
from taslation.regions import TextRegion
from taslation.render import fonts
from taslation.render.fonts import can_draw, drawable, find_font
from taslation.render.typeset import letter_text

LATIN = (0x20, 0x7E)
MACRON, DOTLESS_I, EM_DASH = 0x304, 0x131, 0x2014


def _cov(*spans: tuple[int, int]):
    spans = sorted(spans)
    return tuple(a for a, _b in spans), tuple(b for _a, b in spans)


@pytest.fixture
def comic_like(monkeypatch):
    """"comic.ttf" has ASCII, Latin-1, a few Latin Extended-A letters (ā, Á), the dotless i, the combining macron
    and acute, and the em dash, but not ō, ū, Ō or ś; "wide.ttf" has everything."""
    table = {
        "comic.ttf": _cov(LATIN, (0xA0, 0xFF), (0x101, 0x101), (DOTLESS_I, DOTLESS_I), (0x301, 0x301),
                          (MACRON, MACRON), (EM_DASH, EM_DASH)),
        "wide.ttf": _cov((0x20, 0x2FFF)),
    }
    monkeypatch.setattr(fonts, "_coverage", lambda path: table.get(Path(str(path)).name))


def test_a_lowercase_letter_the_font_lacks_is_composed_from_its_base_and_mark(comic_like):
    assert drawable("comic.ttf", "Tōkyō") == "Tōkyō"
    assert drawable("comic.ttf", "Ryūji") == "Ryūji"
    assert can_draw("comic.ttf", "Tōkyō") and not fonts.covers("comic.ttf", "Tōkyō")


def test_an_i_with_a_macron_is_set_on_the_dotless_i(comic_like):
    assert drawable("comic.ttf", "ī") == "ı̄"


def test_a_letter_the_font_has_is_drawn_as_it_is(comic_like):
    assert drawable("comic.ttf", "Wait—!") == "Wait—!"
    assert drawable("comic.ttf", "ā café") == "ā café"  # precomposed glyphs the font has


def test_a_capital_is_drawn_precomposed_or_without_its_macron(comic_like):
    assert drawable("comic.ttf", "Ōsaka") == "Osaka"  # no Ō: the macron would run into the O
    assert drawable("comic.ttf", "Ōsaka") == "Osaka"  # the same, written decomposed
    assert drawable("comic.ttf", "Á") == "Á"  # the precomposed capital the font has
    assert not can_draw("comic.ttf", "Ś")  # Ś: no precomposed capital, an acute is not dropped
    assert can_draw("comic.ttf", "Ōta")


def test_a_letter_with_no_way_to_draw_it_is_left_out_as_before(comic_like):
    assert not can_draw("comic.ttf", "Love ♥")
    assert drawable("comic.ttf", "Love ♥ you") == "Love  you"
    assert drawable("comic.ttf", "ś") == "ś"  # ś: s and the combining acute
    assert drawable("comic.ttf", "aṡb") == "ab"  # ṡ: no dot above to compose it from, left out as before
    assert not can_draw("nothing.ttf", "abc") and drawable("nothing.ttf", "ō") == "ō"


def test_the_comic_font_is_kept_wherever_its_cmap_can_draw_the_text(monkeypatch, tmp_path):
    comic, noto = tmp_path / fonts.COMIC_FONT, tmp_path / fonts.NOTO_FONTS["lgc"]
    for path in (comic, noto):
        path.write_bytes(b"x")
    table = {comic.name: _cov(LATIN, (0xA0, 0xFF), (DOTLESS_I, DOTLESS_I), (MACRON, MACRON), (EM_DASH, EM_DASH)),
             noto.name: _cov((0x20, 0x2FFF))}
    monkeypatch.setattr(fonts, "_coverage", lambda path: table.get(Path(str(path)).name))
    assert find_font("", tmp_path, "Wait—!", "English").path == str(comic)  # an em dash it has: before, Noto
    assert find_font("", tmp_path, "Rotō", "English").path == str(comic)  # composed
    assert find_font("", tmp_path, "Ś", "English").path == str(noto)  # a capital it cannot draw
    assert find_font("", tmp_path, "ạ", "Vietnamese").path == str(noto)  # a dot below it lacks
    assert find_font("", tmp_path, "", "English").path == str(comic)


def test_an_unreadable_comic_font_falls_back_to_the_range_test(monkeypatch, tmp_path):
    (tmp_path / fonts.COMIC_FONT).write_bytes(b"x")
    (tmp_path / fonts.NOTO_FONTS["lgc"]).write_bytes(b"x")
    monkeypatch.setattr(fonts, "_coverage", lambda path: None)
    assert find_font("", tmp_path, "Hello", "English").path == str(tmp_path / fonts.COMIC_FONT)
    assert find_font("", tmp_path, "Wait—", "English").path == str(tmp_path / fonts.NOTO_FONTS["lgc"])


# ------------------------------------------------------------------ the real Comic Neue
def _comic() -> str:
    path = Settings().fonts_dir / fonts.COMIC_FONT
    if not path.is_file():
        pytest.skip("Comic Neue is not installed (setup_models.py --font)")
    return str(path)


def test_comic_neue_sets_em_dashes_and_hepburn_long_vowels():
    comic = _comic()
    s = Settings()
    for text in ("Wait—!", "Kazuya Rotō", "Ryūji", "Onmyōji"):
        assert find_font(s.font_path, s.fonts_dir, text, "English").path == comic
    assert drawable(comic, "Rotō") == "Rotō"


def _region(w: int = 260, h: int = 120) -> TextRegion:
    mask = np.full((h, w), 255, np.uint8)
    return TextRegion(x0=0, y0=0, x1=w, y1=h, mask=mask, text_box=(20, 20, w - 20, h - 20), kind="bubble")


def test_a_capital_made_by_the_uppercase_setting_is_drawn_without_the_macron_it_cannot_take():
    comic = _comic()
    a = Image.new("RGB", (260, 120), "white")
    b = Image.new("RGB", (260, 120), "white")
    letter_text(a, _region(), "Ōsaka", comic, 9, 40, uppercase=True)
    letter_text(b, _region(), "OSAKA", comic, 9, 40, uppercase=True)
    assert np.array_equal(np.asarray(a), np.asarray(b))
