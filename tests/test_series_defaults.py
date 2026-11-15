"""A new volume starts from its series' defaults: the detection settings, the reading direction and the areas ignored on
every page that a series keeps (`annotations.SeriesDefaults`, a file per series in the annotations folder). A book with
no annotations of its own yet follows them where it has no value of its own; its own values win, clearing them falls
back to the series' defaults; a book of one volume has none; older spellings of a volume's name find the same
defaults; a book whose annotations were kept before is left as it was. Book settings saves the values as the series'
defaults and says beside a value that it is the series'. On the real stores and pipeline, with fake OCR and
translator; names invented."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from helpers import EN_TEXTS, FakeOcr, store_json

from taslation import protect
from taslation.annotations import (SERIES_DIRNAME, AnnotationStore, BookAnnotations, BookArea, SeriesDefaults,
                                   SeriesDefaultsStore, series_id, series_of)
from taslation.cache import CacheStore
from taslation.config import Settings
from taslation.pipeline import Pipeline
from taslation.translate import DictTranslator
from taslation.ui import book_areas
from taslation.ui.dialogs import book_settings as dlg
from taslation.ui.dialogs import caches

SERIES = "Lantern Quay"
NUMBER_AREA = BookArea.around((0.45, 0.95, 0.55, 0.98), "right", 0.7)
TITLE_AREA = BookArea.around((0.05, 0.01, 0.3, 0.04), "left", 0.7)


@pytest.fixture
def store(settings):
    return AnnotationStore(settings.annotations_dir)


def _series_from(store, book=f"{SERIES} 16"):
    """Volume 16, a book with annotations of its own, whose values become the series' defaults."""
    ann = store.open(book)
    ann.set_settings({"translate_sfx": False, "text_scale": 1.2, "white_threshold": 230})
    ann.reading_direction = "ltr"
    ann.add_area(NUMBER_AREA)
    ann.save()
    ann.share_settings()
    ann.share_areas()
    return ann


# ------------------------------------------------------------------ who has a series
def test_a_book_s_series_is_its_series_field_when_it_has_a_volume():
    assert series_of(f"{SERIES} 17") == SERIES
    for older in (f"{SERIES} 第十七巻", f"{SERIES} (17)", f"{SERIES} Vol. 17", f"{SERIES} 17巻", "Ｌａｎｔｅｒｎ　Ｑｕａｙ　１７"):
        assert series_of(older) == SERIES, older
    assert series_of(SERIES) == "" and series_of("") == "" and series_of("   ") == ""  # one volume: no series
    assert series_of("Untitled 2026-11-16 0930") == ""  # a temporary name
    assert series_id("Lantern Quay") == series_id("lantern  QUAY") == series_id("Ｌａｎｔｅｒｎ Ｑｕａｙ") == "lanternquay"


# ------------------------------------------------------------------ a new volume starts from them
def test_a_new_volume_inherits_the_series_settings_direction_and_areas(store):
    _series_from(store)
    new = store.open(f"{SERIES} 17")
    assert new.follows_series and new.own_settings == {} and new.own_direction == "" and new.own_areas is None
    assert new.settings == {"translate_sfx": False, "text_scale": 1.2, "white_threshold": 230}
    assert new.reading_direction == "ltr" and not new.rtl
    assert new.areas == [NUMBER_AREA] and new.areas_from_series and new.areas_for("right", 0.7) == [NUMBER_AREA]
    new.save()  # what the book keeps is its own values only, and that it follows its series
    data = store_json(new.path)
    assert data["follows_series"] is True and data["settings"] == {} and data["reading_direction"] == ""
    assert "areas" not in data


def test_the_pipeline_works_with_the_inherited_values(settings, store):
    _series_from(store)
    ann = store.open(f"{SERIES} 17")
    cache = CacheStore(settings.cache_dir).open(f"{SERIES} 17", "m")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache,
                        annotations=ann)
    assert pipeline.settings.translate_sfx is False and pipeline.settings.white_threshold == 230
    assert pipeline.settings.text_scale == 1.2 and not pipeline.rtl
    pipeline.set_book_settings({"white_threshold": 210})  # its own value, over the series' others
    assert pipeline.settings.white_threshold == 210 and pipeline.settings.translate_sfx is False
    assert store_json(ann.path)["settings"] == {"white_threshold": 210}
    assert pipeline.set_reading_direction("rtl") and pipeline.rtl and store_json(ann.path)["reading_direction"] == "rtl"


def test_the_book_s_own_values_win_and_clearing_falls_back_to_the_series(store):
    _series_from(store)
    ann = store.open(f"{SERIES} 17")
    assert ann.set_settings({"translate_sfx": True, "max_font_size": 40}) == {
        "translate_sfx": True, "text_scale": 1.2, "white_threshold": 230, "max_font_size": 40}
    ann.reading_direction = "rtl"
    assert ann.rtl and ann.inherited_direction == "ltr"
    ann.save()
    again = store.open(f"{SERIES} 17")
    assert again.settings["translate_sfx"] is True and again.settings["text_scale"] == 1.2 and again.rtl
    assert again.set_settings({}) == {"translate_sfx": False, "text_scale": 1.2, "white_threshold": 230}
    again.reading_direction = ""
    assert again.reading_direction == "ltr"  # the series' direction again
    again.set_settings({"text_scale": 0.9})
    again.save()
    # a later change of the series' defaults reaches the volume where it has no value of its own, never past one
    defaults = store.series.open(SERIES)
    defaults.settings = {"text_scale": 1.1, "white_threshold": 200}
    defaults.save()
    later = store.open(f"{SERIES} 17")
    assert later.settings == {"text_scale": 0.9, "white_threshold": 200}


def test_the_areas_are_the_series_list_until_the_volume_changes_one(store):
    _series_from(store)
    ann = store.open(f"{SERIES} 17")
    assert ann.add_area(TITLE_AREA) and ann.own_areas == [NUMBER_AREA, TITLE_AREA] and not ann.areas_from_series
    assert ann.remove_area(TITLE_AREA) and ann.own_areas is None and ann.areas_from_series  # Ctrl+Z: the series' again
    assert ann.remove_area(NUMBER_AREA) and ann.own_areas == [] and ann.areas == []  # none at all, of its own
    ann.save()
    assert store_json(ann.path)["areas"] == []
    assert store.open(f"{SERIES} 17").areas == []  # (an empty list of its own is not the series')
    assert not ann.remove_area(NUMBER_AREA)
    ann.add_area(NUMBER_AREA)
    assert ann.own_areas is None  # the series' areas exactly: it follows them again


# ------------------------------------------------------------------ who has none, and who is left alone
def test_books_without_a_series_have_no_defaults(store, settings):
    _series_from(store)
    for book in (SERIES, "Untitled 2026-11-16 0930"):
        ann = store.open(book)
        assert not ann.follows_series and ann.inherited is None and not ann.can_share and ann.series_name == ""
        assert ann.settings == {} and ann.reading_direction == "" and ann.areas == []
        with pytest.raises(ValueError):
            ann.share_settings()
        with pytest.raises(ValueError):
            ann.share_areas()
        ann.save()
        assert "follows_series" not in store_json(ann.path)
    assert [d["series"] for d in store.series.list()] == [SERIES]


def test_older_spellings_of_a_volume_find_the_same_defaults(store):
    _series_from(store)
    for book in (f"{SERIES} 第十七巻", f"{SERIES} (18)", f"{SERIES} Vol. 19", "Ｌａｎｔｅｒｎ　Ｑｕａｙ　２０",
                 "lantern quay 21"):
        ann = store.open(book)
        assert ann.follows_series and ann.settings["text_scale"] == 1.2 and ann.areas == [NUMBER_AREA], book
    files = sorted(p.name for p in (store.annotations_dir / SERIES_DIRNAME).glob("*.json"))
    assert files == ["lanternquay.json"]  # one file for the series, however its volumes are spelt


def test_a_book_with_annotations_kept_before_is_left_as_it_was(store):
    old = BookAnnotations(store.path_for(f"{SERIES} 5"), f"{SERIES} 5")  # as a version before the series' defaults
    old.set_settings({"detect_text_blocks": False})
    old.save()
    plain = BookAnnotations(store.path_for(f"{SERIES} 6"), f"{SERIES} 6")  # one with nothing of its own but a file
    plain.save()
    before = (store_json(old.path), store_json(plain.path))
    _series_from(store)
    for ann, settings in ((store.open(f"{SERIES} 5"), {"detect_text_blocks": False}), (store.open(f"{SERIES} 6"), {})):
        assert not ann.follows_series and ann.inherited is None and ann.can_share
        assert ann.settings == settings and ann.reading_direction == "" and ann.areas == []
        ann.save()
    after = (store_json(old.path), store_json(plain.path))
    assert [{k: v for k, v in d.items() if k != "updated"} for d in after] == [
        {k: v for k, v in d.items() if k != "updated"} for d in before]
    # saving one as the series' default keeps its own values its own, and it does not start following
    kept = store.open(f"{SERIES} 5")
    kept.share_settings("rtl")
    assert store.series.open(SERIES).settings == {"detect_text_blocks": False}
    assert store.series.open(SERIES).reading_direction == "rtl" and not kept.follows_series


# ------------------------------------------------------------------ the file
def test_the_series_file_round_trips_protected_and_an_unreadable_one_is_set_aside(store):
    _series_from(store)
    path = store.series.path_for(SERIES)
    assert path.parent == store.annotations_dir / SERIES_DIRNAME and path.name == "lanternquay.json"
    assert protect.is_protected(path.read_bytes())  # protected at rest, as the annotations
    data = store_json(path)
    assert data["kind"] == "series_defaults" and data["key"] == "lanternquay" and data["series"] == SERIES
    assert data["settings"] == {"translate_sfx": False, "text_scale": 1.2, "white_threshold": 230}
    assert data["reading_direction"] == "ltr" and data["areas"] == [NUMBER_AREA.to_json()]
    loaded = SeriesDefaults.load(path)
    assert (loaded.settings, loaded.reading_direction, loaded.areas) == (
        data["settings"], "ltr", [NUMBER_AREA]) and loaded.to_json()["settings"] == data["settings"]
    data["settings"]["detect_model"] = "nonsense" * 20  # what is no setting of a book is cut or left out
    data["settings"]["min_bubble_size"] = "x"
    data["areas"].append({"box": "x"})
    data["reading_direction"] = "up"
    path.write_text(json.dumps(data), encoding="utf-8")  # (a plain file, as an earlier version would read)
    odd = store.series.open(SERIES)
    assert odd.reading_direction == "" and odd.areas == [NUMBER_AREA] and len(odd.settings["detect_model"]) == 40
    path.write_text("{not json", encoding="utf-8")
    fresh = store.series.open(SERIES)
    assert fresh.is_empty and not path.exists()
    assert list(path.parent.glob("lanternquay.unreadable-*.json"))  # kept beside, never written over
    assert [row["book"] for row in store.list()] == [f"{SERIES} 16"]  # the folder is no book's annotations


def test_another_series_whose_key_gives_the_same_file_name_gets_its_own_file(settings):
    shelf = SeriesDefaultsStore(settings.annotations_dir / SERIES_DIRNAME)
    first = shelf.open("Quill:Pond")  # the keys "quill:pond" and "quill_pond" give the same file name
    first.settings = {"translate_sfx": False}
    first.save()
    second = shelf.open("Quill_Pond")
    assert second.is_empty and second.path != first.path
    second.reading_direction = "ltr"
    second.save()
    assert shelf.open("quill:pond").settings == {"translate_sfx": False} and shelf.open("QUILL_POND").reading_direction == "ltr"
    assert sorted(row["series"] for row in shelf.list()) == ["Quill:Pond", "Quill_Pond"]


# ------------------------------------------------------------------ Book settings
@pytest.fixture
def no_placing(monkeypatch):
    monkeypatch.setattr(dlg, "place_window", lambda win, parent=None: None)


def _dialog(hidden_root, settings, ann):
    cache = CacheStore(settings.cache_dir).open(ann.book, "m")
    pipeline = Pipeline(settings, ocr=FakeOcr(), translator=DictTranslator(EN_TEXTS, default="ok"), cache=cache,
                        annotations=ann)
    changes = []
    d = dlg.BookSettingsDialog(hidden_root, pipeline, on_change=lambda: changes.append(1))
    d.withdraw()
    return d, pipeline, changes


def test_book_settings_saves_the_values_as_the_series_default(hidden_root, settings, store, no_placing):
    ann = store.open(f"{SERIES} 16")
    d, pipeline, changes = _dialog(hidden_root, settings, ann)
    assert not any(h.winfo_manager() for h in d.hints.values())  # nothing comes from the series yet
    assert d.series_var.get() == dlg.SERIES_LINE.format(series=SERIES)
    d.choices["translate_sfx"].set(False)
    d.scale_var.set("120 %")
    d.direction_var.set(dlg.DIRECTIONS["ltr"])
    d._share()
    assert d.winfo_exists() and changes == [1] and d.said_var.get() == dlg.SHARED.format(series=SERIES)
    defaults = store.series.open(SERIES)
    assert defaults.settings == {"translate_sfx": False, "text_scale": 1.2} and defaults.reading_direction == "ltr"
    # applied to this book too, as its own values; it follows the series where it has none
    assert ann.own_settings == {"translate_sfx": False, "text_scale": 1.2} and ann.own_direction == "ltr"
    assert not pipeline.rtl and pipeline.settings.translate_sfx is False
    assert d.hints["translate_sfx"].winfo_manager() == "grid"  # the same as the series' default
    assert d.scale_var.get() == "120 %" and d.yours_scale == dlg.AS_SERIES.format(value="120 %")
    assert list(d.scale_box.cget("values"))[0] == d.yours_scale
    assert d.direction_var.get() == dlg.DIRECTIONS["ltr"]  # the book's own direction
    assert list(d.direction_box.cget("values"))[0] == dlg.AS_SERIES.format(value=dlg.DIRECTIONS["ltr"])
    assert d.series_var.get() == dlg.FOLLOWS_LINE.format(series=SERIES)
    assert str(d.undo_btn.cget("state")) == "disabled"
    d.destroy()
    new = store.open(f"{SERIES} 17")
    assert new.settings == {"translate_sfx": False, "text_scale": 1.2} and new.reading_direction == "ltr"


def test_book_settings_marks_what_comes_from_the_series(hidden_root, settings, store, no_placing):
    _series_from(store)
    ann = store.open(f"{SERIES} 17")
    d, pipeline, _changes = _dialog(hidden_root, settings, ann)
    assert d.choices["translate_sfx"].get() is False and d.hints["translate_sfx"].winfo_manager() == "grid"
    assert not d.hints["detect_text_blocks"].winfo_manager()  # not in the series' defaults: the reader's own
    assert d.scale_var.get() == dlg.AS_SERIES.format(value="120 %") and d.sizes() == {}
    assert list(d.direction_box.cget("values"))[0] == d.direction_var.get() == dlg.AS_SERIES.format(
        value=dlg.DIRECTIONS["ltr"]) and d.direction() == "ltr"
    assert d.areas_list.get(0, "end") == (dlg.area_line(NUMBER_AREA),)
    assert d.areas_hint.winfo_manager() == "pack" and d.share_areas_btn is not None
    d.choices["translate_sfx"].set(True)  # the book's own, against the series' (and as the reader's own setting)
    assert not d.hints["translate_sfx"].winfo_manager()
    d.direction_var.set(dlg.DIRECTIONS["rtl"])
    d._apply()
    assert ann.own_settings == {"translate_sfx": True} and ann.own_direction == "rtl" and pipeline.rtl
    assert pipeline.settings.translate_sfx is True and pipeline.settings.text_scale == 1.2
    d, pipeline, _changes = _dialog(hidden_root, settings, ann)
    assert d.direction_var.get() == dlg.DIRECTIONS["rtl"] and d.choices["translate_sfx"].get() is True
    d.direction_var.set(dlg.AS_SERIES.format(value=dlg.DIRECTIONS["ltr"]))  # back to the series' direction
    d.choices["translate_sfx"].set(False)  # as the series': no value of the book's own
    d._apply()
    assert ann.own_settings == {} and ann.own_direction == "" and not pipeline.rtl
    assert store_json(ann.path)["reading_direction"] == ""


def test_clear_all_goes_back_to_the_series_defaults(hidden_root, settings, store, no_placing, monkeypatch):
    asked = []
    monkeypatch.setattr(caches, "ask", lambda _parent, text, *a, **k: asked.append(text) or True)
    _series_from(store)
    ann = store.open(f"{SERIES} 17")
    d, pipeline, _changes = _dialog(hidden_root, settings, ann)
    d._clear()
    assert not asked and d.said_var.get() == dlg.NOTHING_TO_CLEAR_SERIES
    pipeline.set_book_settings({"translate_sfx": True, "text_scale": 0.9})
    d._show(d._current())
    d._clear()
    assert asked == [dlg.CLEAR_QUESTION_SERIES.format(n=2)] and d.said_var.get() == dlg.CLEARED_SERIES
    assert ann.own_settings == {} and pipeline.settings.translate_sfx is False and pipeline.settings.text_scale == 1.2
    assert d.choices["translate_sfx"].get() is False and d.scale_var.get() == d.yours_scale
    d._undo()
    assert ann.own_settings == {"translate_sfx": True, "text_scale": 0.9}
    d.destroy()


def test_use_these_areas_for_the_series(hidden_root, settings, store, no_placing):
    ann = store.open(f"{SERIES} 16")
    ann.add_area(NUMBER_AREA)
    ann.add_area(TITLE_AREA)
    ann.save()
    d, pipeline, _changes = _dialog(hidden_root, settings, ann)
    assert not d.areas_hint.winfo_manager()  # the book's own areas
    d._share_areas()
    assert d.said_var.get() == book_areas.AREAS_SHARED.format(series=SERIES, n=2)
    assert store.series.open(SERIES).areas == [NUMBER_AREA, TITLE_AREA]
    assert ann.own_areas is None and "areas" not in store_json(ann.path)  # it follows the series' areas now
    assert d.areas_hint.winfo_manager() == "pack"
    d.areas_list.selection_clear(0, "end")
    d.areas_list.selection_set(1)
    d._remove_area()  # one of the series' areas, for this book only
    assert ann.own_areas == [NUMBER_AREA] and store.series.open(SERIES).areas == [NUMBER_AREA, TITLE_AREA]
    assert not d.areas_hint.winfo_manager()
    d._undo()
    assert ann.own_areas is None and d.areas_hint.winfo_manager() == "pack"
    assert store.open(f"{SERIES} 17").areas == [NUMBER_AREA, TITLE_AREA]
    d.destroy()


def test_book_settings_of_a_book_without_a_series_offers_no_series_default(hidden_root, settings, store, no_placing):
    ann = store.open(SERIES)  # one volume
    d, _pipeline, _changes = _dialog(hidden_root, settings, ann)
    texts = []
    stack = [d]
    while stack:
        w = stack.pop()
        stack.extend(w.winfo_children())
        try:
            texts.append(str(w.cget("text")))
        except Exception:
            pass
    assert dlg.SHARE not in texts and book_areas.USE_FOR_SERIES not in texts and d.share_areas_btn is None
    d.destroy()


def test_book_settings_says_when_the_series_file_cannot_be_written(hidden_root, settings, store, no_placing,
                                                                     monkeypatch):
    ann = store.open(f"{SERIES} 16")
    d, _pipeline, _changes = _dialog(hidden_root, settings, ann)

    def refuse(self):
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(SeriesDefaults, "save", refuse)
    d.choices["translate_sfx"].set(False)
    d._share()
    assert str(d.problem.cget("text")).startswith("Could not save the series' defaults:")
    assert ann.own_settings == {"translate_sfx": False}  # applied to the book all the same
    d._share_areas()
    assert str(d.problem.cget("text")).startswith("Could not save the series' defaults:")
    d.destroy()


def test_stand_in_annotations_without_a_series_still_work(hidden_root, no_placing):
    applied = []
    pipeline = SimpleNamespace(annotations=SimpleNamespace(settings={"text_scale": 1.1}), _base_settings=Settings(),
                               set_book_settings=applied.append)
    d = dlg.BookSettingsDialog(hidden_root, pipeline, on_change=lambda: None)
    d.withdraw()
    assert d.series_values == {} and not any(h.winfo_manager() for h in d.hints.values())
    d._apply()
    assert applied == [{"text_scale": 1.1}]
