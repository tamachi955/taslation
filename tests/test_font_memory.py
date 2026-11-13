"""Starred and recently used fonts, first in every font list: the memory kept in ui.json by family name only, the
star beside a font field (a button reached with Tab), the region editor's Font list and the series sheet's lettering
font and fonts per kind."""

from __future__ import annotations

import json
import tkinter as tk

import numpy as np
import pytest

from taslation.annotations import GlossaryStore
from taslation.i18n import CATALOGS, ui_settings_path
from taslation.pipeline import manual_region
from taslation.ui import app as app_mod
from taslation.ui import font_memory as fm
from taslation.ui.dialogs import glossary as glossary_mod
from taslation.ui.dialogs import review
from taslation.ui.font_memory import FontMemory, StarButton, family_name, font_choices


@pytest.fixture
def memory(tmp_path):
    return FontMemory(tmp_path / "state")


def test_the_memory_keeps_family_names_only_the_last_ten_used_and_the_stars(memory):
    assert memory.first() == [] and font_choices(memory, ["Arial"], ["(automatic)"]) == ["(automatic)", "Arial"]
    for i in range(12):
        memory.used(f"Font {i:02d}")
    assert memory.recent() == [f"Font {i:02d}" for i in range(11, 1, -1)]  # the newest first, ten of them
    memory.used("Font 05")
    assert memory.recent()[0] == "Font 05" and len(memory.recent()) == fm.MAX_RECENT
    assert memory.toggle("Comic Neue") and memory.toggle("Anime Ace") and memory.is_starred("Comic Neue")
    assert memory.first()[:3] == ["Anime Ace", "Comic Neue", "Font 05"]  # the starred ones, then the recent
    assert not memory.toggle("Comic Neue") and not memory.is_starred("Comic Neue")
    memory.used("", "  ", "Two\nlines", "x" * 80)  # no name, not a name, too long: kept short
    assert "" not in memory.recent() and memory.recent()[0] == "x" * fm.MAX_NAME
    assert family_name("  Comic   Neue ") == "Comic Neue" and family_name("\x07") == ""
    data = json.loads(ui_settings_path(memory.state_dir).read_text(encoding="utf-8"))
    assert set(data) == {fm.RECENT_TABLE, fm.STARRED_TABLE} and data[fm.STARRED_TABLE] == {"Anime Ace": "1"}
    assert font_choices(memory, ["Arial", "Anime Ace"], ["(automatic)", "Arial"])[:4] == [
        "(automatic)", "Arial", "Anime Ace", "x" * fm.MAX_NAME]  # each once, where it comes first
    for i in range(fm.MAX_STARRED + 5):
        memory.toggle(f"Star {i:02d}")
    assert len(memory.starred()) == fm.MAX_STARRED


def test_the_star_follows_the_field_and_toggles(hidden_root, memory):
    var = tk.StringVar(hidden_root, value="")
    told = []
    star = StarButton(hidden_root, var, memory, blank=("(automatic)",), on_toggle=lambda: told.append(1))
    assert star.button.cget("text") == fm.NOT_STARRED and "disabled" in star.button.state()
    assert str(star.button.cget("takefocus")) in ("1", "True", "true")  # reached with Tab, pressed with Space
    var.set("Comic Neue")
    assert "disabled" not in star.button.state()
    star.button.invoke()
    assert memory.is_starred("Comic Neue") and star.button.cget("text") == fm.STARRED and told == [1]
    var.set("Arial")
    assert star.button.cget("text") == fm.NOT_STARRED
    var.set("(automatic)")
    assert "disabled" in star.button.state()
    star.press()
    assert told == [1]  # nothing to star
    star.button.destroy()
    var.set("Comic Neue")  # (the field outlives its star: nothing breaks)


def _region():
    r = manual_region(np.full((300, 400, 3), 255, np.uint8), (20, 20, 198, 199))
    r.status, r.translated_text, r.source_text = "translated", "Nice weather today, huh?", "今日はいい天気だね"
    return r


def test_the_editors_font_list_starts_with_the_starred_and_recent_fonts(hidden_root, memory):
    memory.toggle("Comic Neue")
    memory.used("Bangers")
    saved = []
    d = review.EditBubbleDialog(hidden_root, _region(), [], on_save=saved.append, on_drop=lambda: None,
                                families=lambda: ["Arial", "Bangers", "Comic Neue"], font_memory=memory)
    assert list(d.font_box.cget("values")) == ["(automatic)", "Comic Neue", "Bangers"]  # before the list is looked up
    d._fill_families()
    assert list(d.font_box.cget("values")) == ["(automatic)", "Comic Neue", "Bangers", "Arial"]
    assert d.font_star is not None and "disabled" in d.font_star.button.state()  # automatic: nothing to star
    d.font_var.set("Arial")
    d.font_star.button.invoke()  # starred: first in the list next time it opens
    d._fill_families()
    assert list(d.font_box.cget("values"))[:3] == ["(automatic)", "Arial", "Comic Neue"]
    d._save()
    assert saved and saved[-1]["style"].font == "Arial" and memory.recent()[0] == "Arial"
    d.destroy()
    plain = review.EditBubbleDialog(hidden_root, _region(), [], on_save=saved.append, on_drop=lambda: None,
                                    families=lambda: ["Arial"])
    assert plain.font_star is None  # without the memory: as before
    plain._fill_families()
    assert list(plain.font_box.cget("values")) == ["(automatic)", "Arial"]
    plain.destroy()


def test_the_series_sheets_font_fields_list_the_starred_and_recent_fonts(hidden_root, memory, tmp_path, monkeypatch):
    monkeypatch.setattr(glossary_mod, "font_families", lambda fonts_dir=None: ["Arial", "Bangers"])
    memory.toggle("Comic Neue")
    store = GlossaryStore(tmp_path / "glossary")
    d = glossary_mod.GlossaryDialog(hidden_root, store, "Series", "English", on_change=lambda: None,
                                    font_memory=memory)
    d.withdraw()
    assert len(d.font_boxes) == 1 + len(d.kind_vars) and d.font_star is not None
    box = d.font_boxes[0]
    assert list(box.cget("values")) == ["Comic Neue"]
    d._fill_fonts(box)
    assert list(box.cget("values")) == ["Comic Neue", "Arial", "Bangers"]
    d.font_var.set("Bangers")
    d.kind_vars["shout"][0].set("Arial")
    d._set_style()
    assert memory.recent()[:2] == ["Bangers", "Arial"]  # the sheet's lettering font the newest
    assert d.glossary.style.font == "Bangers" and d.glossary.style.lettering_for("shout").font == "Arial"
    d.font_star.button.invoke()
    assert memory.is_starred("Bangers")
    d.destroy()
    plain = glossary_mod.GlossaryDialog(hidden_root, store, "Series", "English", on_change=lambda: None)
    plain.withdraw()
    assert plain.font_star is None and plain.font_boxes  # lists all the same, without stars
    plain.destroy()


def test_the_window_hands_the_memory_to_the_editor_and_the_sheet():
    import inspect

    assert "font_memory=FontMemory(self.settings.state_dir)" in inspect.getsource(app_mod.App.open_glossary)
    from taslation.ui import translator

    assert "font_memory=FontMemory(" in inspect.getsource(translator.TranslatorMixin._open_editor)


def test_every_word_in_every_language():
    for code, catalog in CATALOGS.items():
        if code != "en":
            assert fm.STAR_TIP in catalog, code
