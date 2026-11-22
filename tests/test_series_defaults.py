"""A new volume starts from its series' defaults: the detection settings, the reading direction and the areas ignored on
every page that a series keeps (`annotations.SeriesDefaults`, a file per series in the annotations folder). A book with
no annotations of its own yet follows them where it has no value of its own; its own values win, clearing them falls
back to the series' defaults; a book of one volume has none; older spellings of a volume's name find the same
defaults; a book whose annotations were kept before is left as it was. Book settings saves the values as the series'
defaults and says beside a value that it is the series', and so does the Page menu's Use these areas for the series
(greyed while it cannot act). A rename into another series moves the defaults, copies them while another volume
follows them, keeps the new series' own, and a book that followed its series keeps the values it had in force. On the
real stores and pipeline, with fake OCR and translator; names invented."""

from __future__ import annotations

import json
import tkinter as tk
from types import SimpleNamespace

import pytest
from helpers import EN_TEXTS, FakeOcr, store_json

from taslation import protect
from taslation.annotations import (SERIES_DIRNAME, AnnotationStore, BookAnnotations, BookArea, SeriesDefaults,
                                   SeriesDefaultsStore, series_id, series_of)
from taslation.cache import CacheStore, CachedBubble, CachedPage
from taslation.config import Settings
from taslation.pipeline import Pipeline
from taslation.rename import RenameRefused, Stores, plan_rename, rename_book
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


# ------------------------------------------------------------------ the Page menu's Use these areas for the series
class _Window(book_areas.AreaMixin):
    """The window's part that the Page menu's entry uses: the pipeline, the Book box, the status line."""

    def __init__(self, ann, book=None):
        self.saved = 0
        self.pipeline = SimpleNamespace(annotations=ann, save_annotations=self._save)
        self.book_var = SimpleNamespace(get=lambda: ann.book if book is None else book)
        self.busy, self.said = False, []

    def _save(self):
        self.saved += 1
        self.pipeline.annotations.save()

    def say(self, key, /, **values):
        self.said.append(key.format(**values))


def _entry(hidden_root, w):
    menu = tk.Menu(hidden_root, tearoff=0)
    menu.add_command(label=book_areas.USE_FOR_SERIES, command=w.use_areas_for_series_now, state="disabled")
    w._series_areas_entry = (menu, 0)
    return menu


def test_the_page_menu_entry_keeps_the_book_s_areas_as_the_series(hidden_root, store):
    ann = store.open(f"{SERIES} 16")
    ann.add_area(NUMBER_AREA)
    ann.add_area(TITLE_AREA)
    ann.save()
    w = _Window(ann)
    menu = _entry(hidden_root, w)
    w._sync_series_areas_entry()  # (the menu's postcommand)
    assert menu.entrycget(0, "state") == "normal"
    menu.invoke(0)
    assert w.said == [book_areas.AREAS_SHARED.format(series=SERIES, n=2)] and w.saved == 1
    assert store.series.open(SERIES).areas == [NUMBER_AREA, TITLE_AREA] and ann.own_areas is None
    assert store.open(f"{SERIES} 17").areas == [NUMBER_AREA, TITLE_AREA]  # a new volume starts with them
    menu.destroy()


def test_the_page_menu_entry_is_greyed_while_it_cannot_act(hidden_root, store, monkeypatch):
    ann = store.open(f"{SERIES} 16")
    ann.add_area(NUMBER_AREA)
    w = _Window(ann)
    menu = _entry(hidden_root, w)
    for change, back in ((lambda: setattr(w, "busy", True), lambda: setattr(w, "busy", False)),
                         (lambda: setattr(w, "book_var", SimpleNamespace(get=lambda: f"{SERIES} 17")),
                          lambda: setattr(w, "book_var", SimpleNamespace(get=lambda: f" {SERIES} 16 ")))):
        change()  # a job, another book typed in the Book box
        w._sync_series_areas_entry()
        assert menu.entrycget(0, "state") == "disabled"
        w.use_areas_for_series_now()
        assert w.said == [] and not store.series.path_for(SERIES).exists()
        back()
        w._sync_series_areas_entry()
        assert menu.entrycget(0, "state") == "normal"
    for book in (SERIES, "Untitled 2026-11-16 0930"):  # a book of one volume, a temporary name: no series
        w.pipeline.annotations = store.open(book)
        w.book_var = SimpleNamespace(get=lambda b=book: b)
        w._sync_series_areas_entry()
        assert menu.entrycget(0, "state") == "disabled" and not w.series_areas_ready()
    w.pipeline.annotations = None  # no book read yet
    w._sync_series_areas_entry()
    assert menu.entrycget(0, "state") == "disabled"
    menu.destroy()
    w._sync_series_areas_entry()  # (a menu gone with its window: nothing to grey)

    def refuse(self):
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(SeriesDefaults, "save", refuse)
    w.pipeline.annotations, w.book_var = ann, SimpleNamespace(get=lambda: ann.book)
    w.use_areas_for_series_now()
    assert len(w.said) == 1 and w.said[0].startswith("Could not save the series' defaults:")


# ------------------------------------------------------------------ a rename into another series
def _following(store, book):
    """A volume that follows its series (nothing of its own but a region ignored on one page, so a file)."""
    ann = store.open(book)
    ann.add_box("f" * 80, 0.7, (0.8, 0.8, 0.9, 0.9), "ignore")
    ann.save()
    return ann


def _in_force(ann):
    return dict(ann.settings), ann.rtl, list(ann.areas)


def _values(path):
    data = store_json(path)
    return data["settings"], data["reading_direction"], data["areas"]


def _files(*roots):
    return {str(p.relative_to(root)): p.read_bytes() for root in roots if root.is_dir() for p in root.rglob("*")
            if p.is_file()}


def test_a_rename_moves_the_defaults_when_no_other_volume_has_them(settings, store):
    _series_from(store)  # volume 16, the only one kept
    old_path = store.series.path_for(SERIES)
    values = _values(old_path)
    stores = Stores.of(settings)
    plan = plan_rename(stores, f"{SERIES} 16", "Harbor Lights 16")
    assert (plan.defaults, plan.values_kept) == ("moved", False) and old_path.exists()  # a plan writes nothing
    result = rename_book(stores, f"{SERIES} 16", "Harbor Lights 16")
    assert (result.defaults, result.values_kept, result.left) == ("moved", False, [])
    fresh = AnnotationStore(settings.annotations_dir)
    new_path = fresh.series.path_for("Harbor Lights")
    assert not old_path.exists() and protect.is_protected(new_path.read_bytes()) and _values(new_path) == values
    assert (store_json(new_path)["key"], store_json(new_path)["series"]) == ("harborlights", "Harbor Lights")
    assert [row["series"] for row in fresh.series.list()] == ["Harbor Lights"]
    renamed = fresh.open("Harbor Lights 16")
    assert renamed.follows_series and renamed.areas == [NUMBER_AREA] and renamed.inherited.series == "Harbor Lights"
    assert _in_force(fresh.open("Harbor Lights 17"))[1:] == (False, [NUMBER_AREA])  # the next volume starts from them


@pytest.mark.parametrize("kept_as", ["annotations", "cache"])
def test_a_rename_copies_the_defaults_another_volume_still_follows(settings, store, kept_as):
    _series_from(store)
    if kept_as == "annotations":
        _following(store, f"{SERIES} 17")
    else:  # a volume with a cache alone
        cache = CacheStore(settings.cache_dir).open(f"{SERIES} 17", "m")
        cache.add(CachedPage(fingerprint="e" * 80, aspect=0.7, bubbles=[CachedBubble(box=(0.1, 0.1, 0.2, 0.2),
                                                                                     text="Hello")]))
        cache.save()
    values = _values(store.series.path_for(SERIES))
    result = rename_book(Stores.of(settings), f"{SERIES} 16", "Harbor Lights 16")
    assert (result.defaults, result.values_kept) == ("copied", False)
    fresh = AnnotationStore(settings.annotations_dir)
    assert _values(fresh.series.path_for(SERIES)) == _values(fresh.series.path_for("Harbor Lights")) == values
    assert sorted(row["series"] for row in fresh.series.list()) == ["Harbor Lights", SERIES]
    assert fresh.open(f"{SERIES} 17").areas == [NUMBER_AREA] and fresh.open("Harbor Lights 16").follows_series


def test_a_rename_into_a_series_with_defaults_keeps_them_and_the_book_its_values(settings, store):
    _series_from(store)  # Lantern Quay's: text size 1.2, left to right, the page number ignored
    in_force = _in_force(_following(store, f"{SERIES} 17"))
    theirs = store.series.open("Harbor Lights")
    theirs.settings, theirs.reading_direction = {"text_scale": 0.8}, "rtl"
    theirs.save()
    before = _files(settings.annotations_dir / SERIES_DIRNAME)
    stores = Stores.of(settings)
    plan = plan_rename(stores, f"{SERIES} 17", "Harbor Lights 17")
    assert (plan.defaults, plan.values_kept) == ("kept", True)
    result = rename_book(stores, f"{SERIES} 17", "Harbor Lights 17")
    assert (result.defaults, result.values_kept) == ("kept", True)
    assert _files(settings.annotations_dir / SERIES_DIRNAME) == before  # neither series' defaults written over
    fresh = AnnotationStore(settings.annotations_dir)
    renamed = fresh.open("Harbor Lights 17")
    assert not renamed.follows_series and _in_force(renamed) == in_force  # what it had in force, now its own
    assert renamed.own_settings == in_force[0] and renamed.own_areas == [NUMBER_AREA]
    assert fresh.open("Harbor Lights 18").settings == {"text_scale": 0.8} and fresh.open("Harbor Lights 18").rtl
    assert _in_force(fresh.open(f"{SERIES} 18")) == in_force  # the old series keeps its own for its volumes


def test_a_rename_into_a_series_with_the_same_defaults_keeps_following(settings, store):
    old = _series_from(store).inherited
    _following(store, f"{SERIES} 17")
    same = store.series.open("Harbor Lights")
    same.settings, same.reading_direction, same.areas = dict(old.settings), old.reading_direction, list(old.areas)
    same.areas.reverse()  # (one area: the same list in any order)
    same.save()
    result = rename_book(Stores.of(settings), f"{SERIES} 17", "Harbor Lights 17")
    assert (result.defaults, result.values_kept) == ("kept", False)
    renamed = AnnotationStore(settings.annotations_dir).open("Harbor Lights 17")
    assert renamed.follows_series and renamed.own_settings == {} and renamed.own_areas is None


def test_a_rename_out_of_any_series_or_into_one_from_none_keeps_the_values_in_force(settings, store):
    _series_from(store)
    in_force = _in_force(_following(store, f"{SERIES} 17"))
    old_values = _values(store.series.path_for(SERIES))
    result = rename_book(Stores.of(settings), f"{SERIES} 17", "Harbor Lights")  # one volume: no series
    assert (result.defaults, result.values_kept) == ("", True)
    fresh = AnnotationStore(settings.annotations_dir)
    alone = fresh.open("Harbor Lights")
    assert not alone.follows_series and _in_force(alone) == in_force
    assert _values(fresh.series.path_for(SERIES)) == old_values  # (no series to give them to: they stay)
    # a volume of a series without defaults, into one that has some: what it had (its own, nothing else) stays
    pebble = store.open("Pebble Harbor 3")
    pebble.set_settings({"text_scale": 1.1})
    pebble.save()
    in_force = _in_force(pebble)
    result = rename_book(Stores.of(settings), "Pebble Harbor 3", f"{SERIES} 3")
    assert (result.defaults, result.values_kept) == ("", True)
    renamed = AnnotationStore(settings.annotations_dir).open(f"{SERIES} 3")
    assert not renamed.follows_series and _in_force(renamed) == in_force == ({"text_scale": 1.1}, True, [])
    assert not AnnotationStore(settings.annotations_dir).series.path_for("Pebble Harbor").exists()


def test_a_rename_leaves_alone_a_book_that_follows_no_series_and_a_series_that_stays(settings, store):
    old = BookAnnotations(store.path_for(f"{SERIES} 5"), f"{SERIES} 5")  # kept before the series' defaults
    old.set_settings({"detect_text_blocks": False})
    old.save()
    _series_from(store)
    before = {k: v for k, v in store_json(old.path).items() if k not in ("updated", "book")}
    result = rename_book(Stores.of(settings), f"{SERIES} 5", "Harbor Lights 5")
    assert (result.defaults, result.values_kept) == ("copied", False)  # (volume 16 still follows them)
    fresh = AnnotationStore(settings.annotations_dir)
    after = store_json(fresh.path_for("Harbor Lights 5"))
    assert {k: v for k, v in after.items() if k not in ("updated", "book")} == before
    assert not fresh.open("Harbor Lights 5").follows_series
    one = store.open("Harbor Lights")  # a book of one volume follows nothing: into a series, nothing of it changes
    one.set_settings({"text_scale": 0.9})
    one.save()
    result = rename_book(Stores.of(settings), "Harbor Lights", "Harbor Lights 1")
    assert (result.defaults, result.values_kept) == ("", False)
    assert AnnotationStore(settings.annotations_dir).open("Harbor Lights 1").settings == {"text_scale": 0.9}
    # the series stays (another volume number, another spelling): its defaults stay where they are, as they are
    before = _files(settings.annotations_dir / SERIES_DIRNAME)
    _following(store, f"{SERIES} 17")
    for old_name, new_name in ((f"{SERIES} 17", f"{SERIES} 18"), (f"{SERIES} 18", f"{SERIES} 第十九巻")):
        result = rename_book(Stores.of(settings), old_name, new_name)
        assert (result.defaults, result.values_kept) == ("", False)
        assert AnnotationStore(settings.annotations_dir).open(new_name).follows_series
    assert _files(settings.annotations_dir / SERIES_DIRNAME) == before


@pytest.mark.parametrize("unreadable", ["old", "new"])
def test_a_rename_refuses_when_a_series_defaults_file_cannot_be_read(settings, store, unreadable):
    _series_from(store)
    path = store.series.path_for(SERIES if unreadable == "old" else "Harbor Lights")
    path.write_bytes(b"not a file of series defaults")
    before = _files(settings.annotations_dir, settings.cache_dir)
    stores = Stores.of(settings)
    with pytest.raises(RenameRefused):
        plan_rename(stores, f"{SERIES} 16", "Harbor Lights 16")
    with pytest.raises(RenameRefused):
        rename_book(stores, f"{SERIES} 16", "Harbor Lights 16")
    assert _files(settings.annotations_dir, settings.cache_dir) == before
