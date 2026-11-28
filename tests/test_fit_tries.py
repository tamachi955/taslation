"""Fitting lettering into bubbles (`Settings.fit_tries`): the rule that turns a tall, narrow bubble's line a quarter
clockwise or lets it run over the outline (`render.typeset.fitted_frame`) and where it applies (`frames_for`), the
hyphen once a word at the most and never after or before one or two letters, the setting in the file and the
dialog's section, what the pipeline measures for a turned bubble (`set_size`, `translation_room`) and the words in
every language of the window."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from taslation.config import DEFAULT_FIT_TRIES, FIT_TRIES, ConfigError, Settings
from taslation.i18n import CATALOGS, FEATURE_LANGUAGES, _, set_language
from taslation.pipeline import Pipeline, translation_room
from taslation.regions import TextRegion
from taslation.render import find_font, letter_text
from taslation.render import typeset
from taslation.render.typeset import (HYPHEN_LEAST, OVERRUN, TURNED, _try_points, fitted_frame, frames_for,
                                      overrun_region, tried)
from taslation.ui.dialogs import help as help_dialog
from taslation.ui.dialogs import review
from taslation.ui.dialogs import settings as dlg

WORD = "Unbelievable!"  # one long word: across, a narrow bubble hyphenates it or sets it small


def _font():
    spec = find_font()
    if not spec or not spec.path:
        pytest.skip("no font file on this computer")
    return spec.path


def _ellipse(w, h):
    yy, xx = np.mgrid[0:h, 0:w]
    inside = ((xx + 0.5 - w / 2) / (w / 2)) ** 2 + ((yy + 0.5 - h / 2) / (h / 2)) ** 2 <= 1.0
    return (inside * 255).astype(np.uint8)


def _bubble(w, h, x=20, y=20, kind="bubble"):
    return TextRegion(x, y, x + w, y + h, _ellipse(w, h), (x + w // 4, y + h // 4, x + 3 * w // 4, y + 3 * h // 4),
                      kind=kind)


# ---------------------------------------------------------------- the rule
def _sizes(table):
    """A `sized` for `fitted_frame` from {(frame, sets): (size, hyphenated)}, every call kept."""
    asked = []

    def sized(frame, sets):
        asked.append((frame, sets))
        return table[(frame, sets)]
    return sized, asked


def test_another_room_is_taken_only_where_across_is_poor_and_it_gains_clearly():
    full = ("condense", "hyphenate")
    tries = ("turn", *full)
    # across fine (readable, not at the smallest, no hyphen): nothing else is looked at
    sized, asked = _sizes({("", full): (14, False)})
    assert fitted_frame(tries, sized, 11, 9, ("turn",)) == "" and asked == [("", full)]
    # across hyphenated: turned 1.25 times as large and 2 px larger, no hyphen, wins
    sized, _asked = _sizes({("", full): (16, True), ("", ()): (13, False), ("turn", ()): (30, False)})
    assert fitted_frame(tries, sized, 11, 9, ("turn",)) == "turn"
    # not by a clear margin (under 1.25 times, or not 2 px): across stays
    for base, other in ((12, 14), (4, 5), (12, 15)):
        sized, _asked = _sizes({("", full): (base, True), ("", ()): (base, False), ("turn", ()): (other, False)})
        assert fitted_frame(tries, sized, 11, 9, ("turn",)) == ("turn" if other == 15 else ""), (base, other)
    # never smaller than what across would draw with every set try, and never with more hyphens
    sized, _asked = _sizes({("", full): (17, True), ("", ()): (10, False), ("turn", ()): (14, False)})
    assert fitted_frame(tries, sized, 11, 9, ("turn",)) == ""
    sized, _asked = _sizes({("", full): (10, False), ("", ()): (10, False), ("turn", ()): (20, True)})
    assert fitted_frame(tries, sized, 11, 9, ("turn",)) == ""
    # the bubble may not take it (`frames_for`), or it is not among the tries: across
    sized, _asked = _sizes({("", full): (10, False), ("", ()): (10, False), ("turn", ()): (20, False)})
    assert fitted_frame(tries, sized, 11, 9, ()) == "" and fitted_frame(full, sized, 11, 9, ("turn",)) == ""
    # a try listed after the set tries is weighed against across with them; the first that wins is taken
    later = ("condense", "hyphenate", "overrun", "turn")
    sized, asked = _sizes({("", full): (10, False), ("overrun", full): (12, False), ("turn", full): (20, False)})
    assert fitted_frame(later, sized, 11, 9, ("overrun", "turn")) == "turn"
    assert ("overrun", full) in asked
    sized, _asked = _sizes({("", full): (10, False), ("overrun", full): (13, False)})
    assert fitted_frame(later, sized, 11, 9, ("overrun", "turn")) == "overrun"


def test_a_room_that_keeps_every_word_whole_is_taken_where_across_breaks_one_as_a_last_resort():
    full = ("condense", "hyphenate")
    tries = ("turn", *full)
    # across at the smallest size has to split a word (in a narrow bubble, a long word in three pieces): turned whole
    # at no smaller a size wins without the clear margin
    for other in (9, 10):
        sized, _asked = _sizes({("", full): (9, True, True), ("", ()): (9, False, True), ("turn", ()): (other, False)})
        assert fitted_frame(tries, sized, 11, 9, ("turn",)) == "turn", other
    # turned smaller, turned with a word broken too, or with more hyphens: across stays
    for turned in ((8, False), (10, False, True), (10, True)):
        sized, _asked = _sizes({("", full): (9, False, True), ("", ()): (9, False, True), ("turn", ()): turned})
        assert fitted_frame(tries, sized, 11, 9, ("turn",)) == "", turned
    # a word broken across where across is not poor: nothing else is looked at
    sized, asked = _sizes({("", full): (14, False, True)})
    assert fitted_frame(tries, sized, 11, 9, ("turn",)) == "" and asked == [("", full)]


def test_a_narrow_bubble_whose_long_words_split_in_three_across_is_turned_with_every_word_whole():
    # (a bubble of 35 x 155 px: across at the smallest size, "unbelievable" in three pieces, one hyphen too many)
    font = _font()
    region = _bubble(35, 155)
    text = "Unbelievable, absolutely unbelievable!"
    across = letter_text(None, region, text, font, 9, 64, floor=11)
    fit = typeset.layout_text(region.mask, text, font, 9, 64, 1.12)
    assert across.size == 9 and across.broken > 0 and fit.split > 0
    done = letter_text(None, region, text, font, 9, 64, floor=11, tries=DEFAULT_FIT_TRIES)
    assert done.frame == TURNED and done.broken == 0 and done.size >= across.size


def test_the_set_tries_say_what_the_rescue_does_and_in_what_order():
    assert FIT_TRIES == ("turn", "condense", "hyphenate", "overrun")
    assert DEFAULT_FIT_TRIES == ("turn", "condense", "hyphenate") == Settings().fit_tries
    assert tried(DEFAULT_FIT_TRIES) == (True, True, False)
    assert tried(("hyphenate", "turn", "condense")) == (True, True, True)  # the hyphens before the narrower letters
    assert tried(("turn", "overrun")) == (False, False, False) and tried(()) == (False, False, False)


def test_a_room_is_tried_for_a_bubble_set_upright_and_turned_only_where_it_is_tall_and_set_in_lines():
    tall, wide = _bubble(60, 200), _bubble(200, 60)
    assert frames_for(tall, WORD, "English", FIT_TRIES) == ("turn", "overrun")
    assert frames_for(wide, WORD, "English", FIT_TRIES) == ("overrun",)
    assert frames_for(_bubble(100, 119), WORD, "English", FIT_TRIES) == ("overrun",)  # (under 1.2 times as tall)
    assert frames_for(_bubble(100, 120), WORD, "English", FIT_TRIES) == ("turn", "overrun")
    assert frames_for(tall, "这是什么", "Chinese", FIT_TRIES) == ("overrun",)  # set in columns, never turned
    assert frames_for(_bubble(60, 200, kind="text"), WORD, "English", FIT_TRIES) == ()  # lettering on the page
    slanted = _bubble(60, 200)
    slanted.angle = 8.0
    assert frames_for(slanted, WORD, "English", FIT_TRIES) == ()
    assert frames_for(tall, WORD, "English", DEFAULT_FIT_TRIES) == ("turn",)


# ---------------------------------------------------------------- lettered
def test_a_tall_narrow_bubble_s_long_word_is_turned_larger_and_its_ink_stays_in_the_bubble():
    font = _font()
    region = _bubble(70, 260)
    across = letter_text(None, region, WORD, font, 9, 64, floor=11)  # (no tries: as before)
    image = Image.new("RGB", (110, 300), "white")
    done = letter_text(image, region, WORD, font, 9, 64, floor=11, tries=DEFAULT_FIT_TRIES)
    assert across.frame == "" and "+hyphens" in across.won
    assert done.frame == TURNED and done.size >= 1.25 * across.size and "+hyphens" not in done.won
    ink = np.asarray(image.convert("L")) < 128
    ys, xs = np.nonzero(ink)
    assert xs.min() >= region.x0 and xs.max() < region.x1 and ys.min() >= region.y0 and ys.max() < region.y1
    assert np.ptp(ys) > 3 * np.ptp(xs)  # the line runs down the bubble
    # as the direction "down" letters it
    down = letter_text(None, region, WORD, font, 9, 64, floor=11, direction="down")
    assert down.size == done.size
    # unticked, a direction set (Horizontal) or lettering on the page: across
    assert letter_text(None, region, WORD, font, 9, 64, floor=11, tries=("condense", "hyphenate")).frame == ""
    assert letter_text(None, region, WORD, font, 9, 64, floor=11, tries=DEFAULT_FIT_TRIES,
                       direction="horizontal").frame == ""
    on_page = _bubble(70, 260, kind="text")
    assert letter_text(None, on_page, WORD, font, 9, 64, floor=11, tries=DEFAULT_FIT_TRIES).frame == ""


def test_lettering_that_reads_well_across_is_never_turned():
    font = _font()
    for w, h, text in ((90, 300, "What are you doing here at this hour?"), (60, 200, "No way!"),
                       (120, 200, "Don't touch that.")):
        region = _bubble(w, h)
        plain = letter_text(None, region, text, font, 9, 64, floor=11)
        fitted = letter_text(None, region, text, font, 9, 64, floor=11, tries=DEFAULT_FIT_TRIES)
        assert fitted.frame == "" and (fitted.size, fitted.won) == (plain.size, plain.won), text


def test_the_lettering_may_run_over_the_outline_only_when_asked():
    font = _font()
    region = _bubble(36, 36)
    grown = overrun_region(region)
    d = region.x0 - grown.x0
    assert d == typeset.OVERRUN_PX and (grown.x1 - region.x1, grown.y0, grown.y1) == (d, region.y0 - d, region.y1 + d)
    assert grown.mask.shape == (region.height + 2 * d, region.width + 2 * d)
    assert int((grown.mask > 0).sum()) > int((region.mask > 0).sum())
    text = "No way!"
    off = letter_text(None, region, text, font, 9, 64, floor=11, tries=DEFAULT_FIT_TRIES)
    image = Image.new("RGB", (80, 80), "white")
    on = letter_text(image, region, text, font, 9, 64, floor=11, tries=("overrun", "condense", "hyphenate"))
    assert off.frame == "" and on.frame == OVERRUN and on.size >= 1.25 * off.size
    ys, xs = np.nonzero(np.asarray(image.convert("L")) < 128)
    assert xs.size and xs.min() >= grown.x0 and xs.max() < grown.x1 and ys.min() >= grown.y0 and ys.max() < grown.y1


# ---------------------------------------------------------------- hyphens
def test_a_hyphen_at_the_limit_leaves_three_letters_or_more_and_a_word_takes_one():
    assert HYPHEN_LEAST == 3 and typeset.HYPHENS_PER_WORD == 1
    for word in ("extraordinary", "unbelievable", "hyphenation", "notwithstanding", "Geschwindigkeitsbegrenzung"):
        for language in ("English", "German", ""):
            points = _try_points(word, language)
            assert all(HYPHEN_LEAST <= p <= len(word) - HYPHEN_LEAST for p in points), (word, language, points)
    font = _font()
    text = "Nevertheless, notwithstanding the circumstances, we'll keep going."
    for w, h in ((58, 200), (58, 270), (44, 270)):
        fit = typeset.layout_text(_ellipse(w, h), text, font, 9, 64, language="English")
        lines = [t for t, _x, _y in fit.lines if t]
        broken = [i for i, line in enumerate(lines) if line.endswith("-")]
        assert fit.size >= 9 and not any(b + 1 in broken and " " not in lines[b + 1] for b in broken), lines
        for line in lines:  # (never "ex-" nor "-ly": three letters or more on either side of a hyphen)
            if line.endswith("-"):
                assert len(line.split()[-1].rstrip("-")) >= HYPHEN_LEAST, lines


def test_with_the_hyphens_off_a_word_too_wide_at_the_smallest_size_stays_whole_runs_over_and_is_flagged():
    """The "hyphenate" try left out: not even the last resort splits a Latin word with a hyphen - it is set whole at
    the smallest size, past its room, and flagged as touching the bubble's edge, never as hyphenated."""
    font = _font()
    word = "Incomprehensibilities"
    mask = _ellipse(40, 120)  # (narrower than the word at the smallest size)
    on = typeset.layout_text(mask, word, font, 9, 64, language="English")
    off = typeset.layout_text(mask, word, font, 9, 64, language="English", hyphenate=False, condense=False)
    on_lines, off_lines = [t for t, *_ in on.lines if t], [t for t, *_ in off.lines if t]
    assert len(on_lines) > 1 and any(t.endswith("-") for t in on_lines)
    assert off_lines == [word] and off.size == 9 and (off.whole, off.split, off.hyphens) == (1, 0, 0)
    assert not off.clean and "+hyphens" not in off.won
    region = _bubble(40, 120)
    image = Image.new("RGB", (100, 180), "white")
    done = letter_text(image, region, word, font, 9, 64, floor=11, tries=("condense",))
    assert done.size == 9 and typeset.TIGHT in done.flags and typeset.HYPHENATED not in done.flags
    xs = np.nonzero(np.asarray(image.convert("L")) < 128)[1]
    assert xs.min() < region.x0 and xs.max() >= region.x1  # (it runs past the bubble on both sides)
    hyphened = letter_text(Image.new("RGB", (100, 180), "white"), region, word, font, 9, 64, floor=11,
                           tries=("condense", "hyphenate"))
    assert typeset.HYPHENATED in hyphened.flags
    # as formatted in the region editor, at an automatic size: whole too, and said
    formatted = letter_text(Image.new("RGB", (100, 180), "white"), region, word, font, 9, 64,
                            fmt=typeset.TextFormat(), tries=("condense",))
    assert formatted.flags == (typeset.TIGHT,)
    # the rectangle's wrapping alike, and the counts: a word left whole is a break, and "whole"
    small = typeset.styled_font(font, 9, False)
    stats: dict[str, int] = {}
    assert typeset.wrap_lines(f"so {word} now", small, 30, "lgc", stats=stats, hyphen=False) == ["so", word, "now"]
    assert stats == {"breaks": 1, "whole": 1}
    assert len(typeset.wrap_lines(word, small, 30, "lgc")) > 1
    assert typeset._split_word(word, small, 30, "lgc", "English", hyphen=False) is None
    assert typeset._split_word(word, small, 30, "lgc", "English") is not None


# ---------------------------------------------------------------- the pipeline
def test_the_size_for_review_and_the_room_a_translator_is_told_follow_the_turned_line(settings):
    _font()
    settings.readable_font_size = 11
    p = Pipeline(settings, ocr=None, translator=None)
    mask = _ellipse(70, 260)
    anchor = (20 + 17, 20 + 65, 20 + 52, 20 + 195)
    region = _bubble(70, 260)
    lettered = p._set_text(Image.new("RGB", (120, 320), "white"), region, WORD, (255, 255, 255), None)
    assert lettered.frame == TURNED
    assert p.set_size(mask, WORD, "bubble", anchor, 20, 20) == lettered.size
    settings.fit_tries = ("condense", "hyphenate")
    across = p._set_text(Image.new("RGB", (120, 320), "white"), region, WORD, (255, 255, 255), None)
    assert across.frame == "" and across.size < lettered.size
    assert p.set_size(mask, WORD, "bubble", anchor, 20, 20) == across.size
    # the room a translator is told: the larger of across and turned, while the line may be turned
    tall = np.full((300, 60), 255, np.uint8)
    settings.fit_tries = DEFAULT_FIT_TRIES
    turned_room = translation_room(tall, (0, 0, 60, 300), "あ" * 40, settings)
    settings.fit_tries = ("condense", "hyphenate")
    across_room = translation_room(tall, (0, 0, 60, 300), "あ" * 40, settings)
    assert turned_room == 0 or (across_room and turned_room >= across_room)
    assert translation_room(tall, (0, 0, 60, 300), "あ" * 40, settings, direction="horizontal") == across_room


# ---------------------------------------------------------------- the setting
def test_the_setting_is_read_from_the_file_and_checked(tmp_path):
    path = tmp_path / "taslation.toml"
    path.write_text('fit_tries = ["hyphenate", "Turn", "overrun"]\n', encoding="utf-8")
    assert Settings.from_toml(path).fit_tries == ("hyphenate", "turn", "overrun")
    path.write_text('fit_tries = "turn, condense"\n', encoding="utf-8")
    assert Settings.from_toml(path).fit_tries == ("turn", "condense")
    path.write_text("fit_tries = []\n", encoding="utf-8")
    assert Settings.from_toml(path).fit_tries == ()
    for bad in (("turn", "squeeze"), ("turn", "turn"), "turn"):
        with pytest.raises(ConfigError):
            Settings(fit_tries=bad).validate()


def test_the_dialog_s_section_ticks_and_orders_the_tries_and_saves_them(hidden_root, tmp_path, monkeypatch):
    monkeypatch.setattr(dlg, "place_window", lambda win, parent=None: None)
    settings = Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models",
                        config_path=tmp_path / "taslation.toml")
    got = []
    d = dlg.SettingsDialog(hidden_root, settings, on_saved=got.append)
    assert "fit_tries" in dlg.KEYS and "fit_tries" in dlg.PAGE_SETTINGS
    assert d.fit_order == ["turn", "condense", "hyphenate", "overrun"] and d.values()["fit_tries"] == DEFAULT_FIT_TRIES
    assert [d.fit_ticked[k].get() for k in d.fit_order] == [True, True, True, False]
    texts = [d.fit_rows[k][1].cget("text") for k in d.fit_order]
    assert texts == ["Turn the line 90 degrees", "Narrower letters (down to 92 %)", "Hyphens (at most one in a word)",
                     "Run over the bubble's outline"]
    first, last = d.fit_rows["turn"], d.fit_rows["overrun"]
    assert first[2].instate(["disabled"]) and last[3].instate(["disabled"]) and not first[3].instate(["disabled"])
    # the smallest size sits in the section, the largest stays with the lettering
    assert d.sizes["min_font_size"].get() == "9"
    d.move_try("hyphenate", -1)
    d.move_try("hyphenate", -1)
    d.move_try("hyphenate", -1)  # (at the top already: stays)
    d.fit_ticked["turn"].set(False)
    d.fit_ticked["overrun"].set(True)
    assert d.fit_order == ["hyphenate", "turn", "condense", "overrun"]
    assert d.values()["fit_tries"] == ("hyphenate", "condense", "overrun")
    assert d.fit_rows["hyphenate"][2].instate(["disabled"]) and not d.fit_rows["turn"][2].instate(["disabled"])
    assert d.save() is True and got == [{"fit_tries": ("hyphenate", "condense", "overrun")}]
    loaded = Settings.from_toml(settings.config_path)
    assert loaded.fit_tries == ("hyphenate", "condense", "overrun")
    again = dlg.SettingsDialog(hidden_root, loaded)
    assert again.fit_order == ["hyphenate", "condense", "overrun", "turn"] and not again.fit_ticked["turn"].get()


def test_the_section_in_japanese(hidden_root, tmp_path, monkeypatch):
    monkeypatch.setattr(dlg, "place_window", lambda win, parent=None: None)
    set_language("ja")
    d = dlg.SettingsDialog(hidden_root, Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models",
                                                 config_path=tmp_path / "taslation.toml"))
    assert d.fit_rows["turn"][1].cget("text") == "行を 90° 回す"
    assert d.fit_rows["condense"][1].cget("text") == "字幅を狭める（92 % まで）"


def test_the_new_words_are_in_every_language_of_the_window():
    keys = [dlg.FIT_TITLE, dlg.FIT_TEXT, *(w for pair in dlg.FIT_ROWS.values() for w in pair), dlg.MOVE_UP,
            dlg.MOVE_DOWN, dlg.MIN_SIZE_TIP, dlg.MAX_SIZE_TIP, dlg.READABLE_TIP, review.DIRECTION_TIP]
    keys.append(next(p for _h, ps in help_dialog.TOPICS for p in ps if "Fitting lettering into bubbles" in p))
    assert review.DIRECTION_TIP.endswith("Auto: across, or turned 90° in a tall, narrow bubble where across would "
                                         "be small (Settings...).")
    for key in keys:
        for code in FEATURE_LANGUAGES:
            text = CATALOGS[code].get(key, "")
            assert text.strip() and text != key, (code, key[:40])
    assert _("Turn the line 90 degrees") == "Turn the line 90 degrees"  # (English: the key itself)
