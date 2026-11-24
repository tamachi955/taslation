"""The library of saved translations ("Saved translations..."): the Size column and the total under the list, sorting
by a click on a heading, several rows at once for Delete (one question naming how many) and Export (one file, with
the books' page information and series sheets), Ctrl+A, Rename... through the window's rename, and the review an
import shows when the file holds several books or meets the reader's own corrections, page information or sheet
values. Dialogs on the shared hidden root, never mapped; the stores in scratch folders."""
from __future__ import annotations

import gc
import os
import tkinter as tk

import pytest

from taslation import backup, rename
from taslation.annotations import AnnotationStore, GlossaryStore
from taslation.cache import CacheStore, CachedBubble, CachedPage
from taslation.ui.dialogs import caches
from taslation.ui.dialogs.caches import CachesDialog, RenameBookDialog, shown_size
from taslation.ui.dialogs.import_review import ImportChoice, ImportReviewDialog

PASSPHRASE = "correct horse battery staple"
MODEL = "unusual-model:7b-test"
SERIES, OTHER = "Lantern Quay", "Pebble Harbor"
BOX = (0.1, 0.1, 0.3, 0.2)


@pytest.fixture(autouse=True)
def _collected_in_the_main_thread():
    yield
    gc.collect()


def _stores(root) -> rename.Stores:
    return rename.Stores(CacheStore(root / "cache"), AnnotationStore(root / "annotations"),
                         GlossaryStore(root / "glossary"))


def _cache(stores, book: str, pages: int, language: str = "English", text: str = "Line", edited: bool = False):
    cache = stores.cache.open(book, MODEL, language)
    for i in range(pages):
        cache.add(CachedPage(fingerprint="0123456789abcdef"[i] * 80, aspect=0.7, seq=i,  # pages far apart
                             bubbles=[CachedBubble(box=BOX, text=f"{text} {i}", edited=edited)]))
    cache.save()
    return cache


def _library(root) -> rename.Stores:
    stores = _stores(root)
    _cache(stores, f"{SERIES} 10", 3)
    _cache(stores, f"{SERIES} 2", 1)
    _cache(stores, f"{SERIES} 2", 2, language="French")
    _cache(stores, f"{OTHER} 1", 5)
    return stores


def _dialog(hidden_root, stores, **kwargs) -> CachesDialog:
    d = CachesDialog(hidden_root, stores.cache, annotations=stores.annotations, sheets=stores.sheets, **kwargs)
    d.withdraw()
    return d


def _rows(d) -> list[tuple[str, str, str]]:
    return [(d.tree.item(i, "text"), d.tree.set(i, "volume"), d.tree.set(i, "language")) for i in d.tree.get_children()]


def _choose(d, *wanted: tuple[str, str]) -> None:
    d.tree.selection_set([i for i, e in d._entries.items() if (e["book"], e["language"]) in wanted])
    d._sync_buttons()


@pytest.fixture
def quick_keys(monkeypatch):
    pytest.importorskip("cryptography")
    monkeypatch.setitem(backup.KDF, "n", 2 ** 14)


# ------------------------------------------------------------------ size, total, sorting
def test_sizes_are_shown_in_kilobytes_or_megabytes():
    assert [shown_size(n) for n in (0, 1, 1024, 1025, 1024 * 1024 - 1)] == ["0 KB", "1 KB", "1 KB", "2 KB", "1024 KB"]
    assert shown_size(1024 * 1024) == "1.0 MB" and shown_size(int(2.25 * 1024 * 1024)) == "2.2 MB"


def test_the_list_shows_each_files_size_and_the_total_and_sorts_by_a_heading(hidden_root, tmp_path):
    stores = _library(tmp_path)
    d = _dialog(hidden_root, stores)
    assert tuple(d.tree.cget("columns")) == caches.COLUMNS and d.tree.heading("size", "text") == "Size"
    assert _rows(d) == [(SERIES, "2", "English"), (SERIES, "2", "French"), (SERIES, "10", "English"),
                        (OTHER, "1", "English")]  # by series, volume (2 before 10) and language at first
    sizes = []
    for item, entry in d._entries.items():
        size = os.stat(entry["file"]).st_size
        assert d.tree.set(item, "size") == shown_size(size) and entry["size"] == size
        sizes.append(size)
    assert d.empty_var.get() == f"In all: 4 translation file(s), 11 page(s), {shown_size(sum(sizes))}."
    assert all(str(d.tree.heading(c, "command")) for c in ("#0", *caches.COLUMNS))  # each heading sorts
    assert d.tree.heading("#0", "text") == "Series"  # no arrow until the reader sorts
    _choose(d, (f"{OTHER} 1", "English"))
    d._sort_by("pages")
    assert [d._entries[i]["pages"] for i in d.tree.get_children()] == [1, 2, 3, 5]
    assert d.tree.heading("pages", "text") == "Pages ▲" and d.tree.heading("#0", "text") == "Series"
    d._sort_by("pages")  # again: the other way round
    assert [d._entries[i]["pages"] for i in d.tree.get_children()] == [5, 3, 2, 1]
    assert d.tree.heading("pages", "text") == "Pages ▼"
    assert [d._entries[i]["book"] for i in d.tree.selection()] == [f"{OTHER} 1"]  # the choice stays
    d._sort_by("language")
    assert [d._entries[i]["language"] for i in d.tree.get_children()] == ["English"] * 3 + ["French"]
    d._sort_by("size")
    assert [d._entries[i]["size"] for i in d.tree.get_children()] == sorted(sizes)
    d.destroy()


def test_ctrl_a_chooses_every_row_and_export_and_rename_follow_the_choice(hidden_root, tmp_path):
    pytest.importorskip("cryptography")
    stores = _library(tmp_path)
    d = _dialog(hidden_root, stores, rename=lambda *a: None)
    assert str(d.export_btn.cget("state")) == "disabled" and str(d.rename_btn.cget("state")) == "disabled"
    assert str(d.tree.cget("selectmode")) == "extended" and d.tree.bind("<Control-a>")
    assert d._select_all() == "break" and len(d.tree.selection()) == 4
    d._sync_buttons()
    assert str(d.export_btn.cget("state")) == "normal" and str(d.rename_btn.cget("state")) == "disabled"
    _choose(d, (f"{SERIES} 2", "French"))
    assert str(d.rename_btn.cget("state")) == "normal"  # one book: it can be renamed
    d.destroy()
    d = _dialog(hidden_root, stores)  # a dialog that is not the window's: there is no rename to hand it to
    _choose(d, (f"{SERIES} 2", "French"))
    assert str(d.rename_btn.cget("state")) == "disabled"
    d.destroy()


# ------------------------------------------------------------------ Delete of several rows
def test_several_rows_go_to_the_recycle_bin_after_one_question(hidden_root, tmp_path, monkeypatch):
    stores = _library(tmp_path)
    asked, changed, binned = [], [], []
    monkeypatch.setattr(caches, "ask", lambda _parent, text, *a, **k: asked.append((text, a, k)) or True)
    d = _dialog(hidden_root, stores, on_changed=changed.append)
    d.recycle = lambda paths: [binned.append(p.name) or p.unlink() for p in paths]
    _choose(d, (f"{SERIES} 2", "French"), (f"{OTHER} 1", "English"))
    d._delete()
    ((text, buttons, options),) = asked
    assert text == caches.DELETE_MANY_QUESTION.format(
        n=2, names=f"{SERIES} 2 (French), {OTHER} 1 (English)") and buttons == ("Delete", "Keep them")
    assert options == {"no_first": True} and len(binned) == 2
    assert sorted((b["book"], b["language"]) for b in stores.cache.list()) == [
        (f"{SERIES} 10", "English"), (f"{SERIES} 2", "English")]
    assert d.backup_var.get() == caches.IN_THE_BIN_MANY.format(n=2) and changed == [f"{SERIES} 2", f"{OTHER} 1"]
    d.destroy()


def test_keep_them_and_a_file_the_bin_refuses(hidden_root, tmp_path, monkeypatch):
    stores = _library(tmp_path)
    answer, asked, told = [False], [], []
    monkeypatch.setattr(caches, "ask", lambda _parent, text, *a, **k: asked.append(text) or answer[0])
    monkeypatch.setattr(caches, "tell", lambda _parent, text, **_k: told.append(text))
    d = _dialog(hidden_root, stores)
    d.recycle = lambda paths: pytest.fail("nothing is to go")
    _choose(d, (f"{SERIES} 2", "French"), (f"{SERIES} 10", "English"))
    d._delete()  # Keep them
    assert len(asked) == 1 and len(stores.cache.list()) == 4
    answer[0] = True

    def bin_some(paths):
        for p in paths:
            if "10" in p.name:
                raise OSError("no bin")
            p.unlink()

    d.recycle = bin_some
    _choose(d, (f"{SERIES} 2", "French"), (f"{SERIES} 10", "English"))
    d._delete()
    assert told == [caches.NOT_ALL_DELETED.format(n=1, names=f"{SERIES} 10 (English)")] == [d.backup_var.get()]
    assert len(stores.cache.list()) == 3
    d.destroy()


# ------------------------------------------------------------------ Export of several books
def test_the_books_chosen_go_into_one_file_with_their_page_information_and_sheets(hidden_root, tmp_path, monkeypatch,
                                                                                  quick_keys):
    stores = _library(tmp_path)
    marks = stores.annotations.open(f"{SERIES} 2")
    marks.add_box("b" * 80, 0.7, (0.8, 0.8, 0.9, 0.9), "ignore")
    marks.save()
    sheet = stores.sheets.open(SERIES, "English")
    sheet.set("灯台", "the lighthouse")
    sheet.save()
    out = tmp_path / "picked.stcache"
    monkeypatch.setattr(CachesDialog, "_before", lambda _self, title, text: True)
    monkeypatch.setattr(caches.filedialog, "asksaveasfilename", lambda **_k: str(out))
    monkeypatch.setattr(CachesDialog, "_passphrase", lambda _self, confirm: PASSPHRASE)
    statuses: list[str] = []
    d = _dialog(hidden_root, stores, on_status=statuses.append)
    _choose(d, (f"{SERIES} 2", "English"), (f"{SERIES} 10", "English"))
    d._export()
    assert d.backup_var.get() == ("Exported 2 books, 4 page(s), to picked.stcache. With them: the page information "
                                  "of 1 book(s) and 1 series sheet(s).")
    assert statuses == [f"Exported 2 books, 4 page(s), to {out}."]
    assert len(d.tree.selection()) == 2  # the list filled again, the books still chosen
    held = backup.open_export(out, PASSPHRASE).held
    assert sorted((h.book, h.annotations, h.sheet) for h in held) == [(f"{SERIES} 10", False, SERIES),
                                                                      (f"{SERIES} 2", True, SERIES)]
    _choose(d, (f"{OTHER} 1", "English"))
    d._export()  # one book: as before, the sheet and page information it has none of
    assert d.backup_var.get() == f"Exported 5 page(s) of {OTHER} 1 to picked.stcache."
    d.destroy()


# ------------------------------------------------------------------ Import, with the review
def _file_of(tmp_path, books, marks=None, root="home") -> tuple:
    """An export of *books* (name, pages, edited) made on another computer of the reader's, with a speaker noted on a
    page of the books of *marks* (book: speaker)."""
    home = _stores(tmp_path / root)
    for book, pages, edited in books:
        _cache(home, book, pages, text="Theirs", edited=edited)
    for book, speaker in (marks or {}).items():
        ann = home.annotations.open(book)
        ann.page("b" * 80, 0.7).set_note(BOX, speaker=speaker)
        ann.save()
    out = tmp_path / f"{root}.stcache"
    backup.export_books(home, [(b, "English") for b, _p, _e in books], out, PASSPHRASE)
    return home, out


def _importing(monkeypatch, out, review=None):
    reviewed = []
    monkeypatch.setattr(CachesDialog, "_before", lambda _self, title, text: True)
    monkeypatch.setattr(caches.filedialog, "askopenfilename", lambda **_k: str(out))
    monkeypatch.setattr(CachesDialog, "_passphrase", lambda _self, confirm: PASSPHRASE)
    monkeypatch.setattr(CachesDialog, "_review",
                        lambda _self, opened, plan, file: reviewed.append((opened, plan, file)) or (
                            review(opened, plan) if review else None))
    return reviewed


def test_a_file_of_one_new_book_imports_without_a_review(hidden_root, tmp_path, monkeypatch, quick_keys):
    _home, out = _file_of(tmp_path, [(f"{SERIES} 3", 2, False)])
    reviewed = _importing(monkeypatch, out)
    here, changed = _stores(tmp_path / "laptop"), []
    d = _dialog(hidden_root, here, on_changed=changed.append)
    d._import()
    assert not reviewed and changed == [f"{SERIES} 3"]
    assert d.backup_var.get() == f"Imported 2 page(s) of {SERIES} 3 from home.stcache."
    assert [d._entries[i]["book"] for i in d.tree.selection()] == [f"{SERIES} 3"]
    d.destroy()


def test_a_file_of_several_books_is_reviewed_and_imports_what_was_chosen(hidden_root, tmp_path, monkeypatch, quick_keys):
    _home, out = _file_of(tmp_path, [(f"{SERIES} 3", 2, False), (f"{SERIES} 4", 1, False)])
    statuses = []
    reviewed = _importing(monkeypatch, out, review=lambda opened, plan: ImportChoice(
        [h.index for h in opened.held if h.book == f"{SERIES} 4"]))
    here = _stores(tmp_path / "laptop")
    d = _dialog(hidden_root, here, on_status=statuses.append)
    d._import()
    ((opened, plan, file),) = reviewed
    assert file == "home.stcache" and len(opened.held) == 2 and len(plan.books) == 2
    assert [b["book"] for b in here.cache.list()] == [f"{SERIES} 4"]
    assert d.backup_var.get() == f"Imported 1 page(s) of {SERIES} 4 from home.stcache."
    monkeypatch.setattr(CachesDialog, "_review", lambda *_a: None)  # Cancel in the review: nothing is imported
    before = sorted(p.name for p in here.cache.cache_dir.iterdir())
    d._import()
    assert sorted(p.name for p in here.cache.cache_dir.iterdir()) == before
    monkeypatch.setattr(CachesDialog, "_review", lambda _self, opened, plan, file: ImportChoice(list(range(2))))
    d._import()
    assert d.backup_var.get() == "Imported 2 books, 3 page(s), from home.stcache."
    assert statuses[-1] == f"Imported 2 books, 3 page(s), from {out}." and len(d.tree.selection()) == 2
    d.destroy()


def test_the_review_comes_for_the_readers_own_and_the_choice_is_what_is_written(hidden_root, tmp_path, monkeypatch,
                                                                                 quick_keys):
    book = f"{SERIES} 3"
    _home, out = _file_of(tmp_path, [(book, 2, False)], {book: "Hanako"})
    here = _stores(tmp_path / "laptop")
    _cache(here, book, 1, text="Mine", edited=True)  # my corrections on the file's first page
    mine = here.annotations.open(book)
    mine.page("b" * 80, 0.7).set_note(BOX, speaker="The Keeper")
    mine.save()
    reviewed = _importing(monkeypatch, out, review=lambda opened, plan: ImportChoice([0]))  # the defaults
    d = _dialog(hidden_root, here)
    d._import()
    ((_opened, plan, _file),) = reviewed
    assert plan.kept == 1 and [m.state for m in plan.differing] == ["differs"]
    texts = [b.text for p in here.cache.open(book, MODEL).pages for b in p.bubbles]
    assert sorted(texts) == ["Mine 0", "Theirs 1"]  # my correction kept, the file's other page added
    assert here.annotations.open(book).page("b" * 80, 0.7).note_at(BOX).speaker == "The Keeper"
    assert d.backup_var.get() == (f"Imported 2 page(s) of {book} from home.stcache. 1 page(s) added, 0 replaced, 1 of "
                                  f"your corrections kept. Page information: 0 added, 0 taken from the file, 1 kept "
                                  f"as yours.")
    _importing(monkeypatch, out, review=lambda opened, plan: ImportChoice([0], keep_corrections=False,
                                                                          take_annotations=True))
    d._import()
    texts = [b.text for p in here.cache.open(book, MODEL).pages for b in p.bubbles]
    assert sorted(texts) == ["Theirs 0", "Theirs 1"]
    assert here.annotations.open(book).page("b" * 80, 0.7).note_at(BOX).speaker == "Hanako"
    d.destroy()


def test_the_review_dialog_lists_the_books_counts_the_choice_and_asks_only_what_there_is(hidden_root, tmp_path,
                                                                                         quick_keys):
    book = f"{SERIES} 3"
    home, out = _file_of(tmp_path, [(book, 2, False), (f"{OTHER} 1", 1, False)], {book: "Hanako"})
    sheet = home.sheets.open(SERIES, "English")
    sheet.set("灯台", "the Lighthouse")
    sheet.save()
    backup.export_books(home, [(book, "English"), (f"{OTHER} 1", "English")], out, PASSPHRASE)
    here = _stores(tmp_path / "laptop")
    _cache(here, book, 1, text="Mine", edited=True)
    mine = here.annotations.open(book)
    mine.page("b" * 80, 0.7).set_note(BOX, speaker="The Keeper")
    mine.save()
    sheet = here.sheets.open(SERIES, "English")
    sheet.set("灯台", "the lighthouse tower")
    sheet.save()
    opened = backup.open_export(out, PASSPHRASE)
    plan = backup.plan_import(here, opened)
    r = ImportReviewDialog(hidden_root, opened, plan, "home.stcache")
    r.withdraw()
    assert r.title() == "Import from home.stcache"
    rows = sorted((r.tree.item(i, "text"), r.tree.set(i, "volume"), r.tree.set(i, "here")) for i in r.tree.get_children())
    assert rows == [(SERIES, "3", "Joins yours"), (OTHER, "1", "New here")]
    assert len(r.tree.selection()) == 2 and str(r.import_btn.cget("state")) == "normal"
    assert r.counts_var.get() == "3 page(s) of 2 book(s): 2 new, 0 replacing yours, 1 of your corrections kept."
    assert r.corrections_box is not None and r.marks_box is not None
    assert r.rows == [("Term: 灯台", "the lighthouse tower", "the Lighthouse")]  # the values, never a line of the book
    r.corrections_var.set("take")
    assert r.counts_var.get() == "3 page(s) of 2 book(s): 2 new, 1 replacing yours, 0 of your corrections kept."
    r.tree.selection_set([i for i in r.tree.get_children() if r.tree.item(i, "text") == OTHER])
    r._sync()
    assert r.counts_var.get() == "1 page(s) of 1 book(s): 1 new, 0 replacing yours, 0 of your corrections kept."
    r.tree.selection_set(())
    r._sync()
    assert str(r.import_btn.cget("state")) == "disabled"
    r._select_all()
    r._sync()
    r.marks_var.set("take")
    (_key, var), = r.choices
    var.set("theirs")
    r.apply()
    assert r.choice == ImportChoice([0, 1], keep_corrections=False, take_annotations=True,
                                    answers={plan.keyed()[0][0]: True}) and not r.winfo_exists()

    plan = backup.plan_import(_stores(tmp_path / "empty"), opened)  # nothing of the reader's own: no question
    r = ImportReviewDialog(hidden_root, opened, plan, "home.stcache")
    r.withdraw()
    assert r.corrections_box is None and r.marks_box is None and r.defaults_box is None and r.choices == []
    r.cancel()
    assert r.choice is None and not r.winfo_exists()


def test_series_defaults_of_the_readers_own_bring_the_review_and_stay_unless_taken(hidden_root, tmp_path, monkeypatch,
                                                                                    quick_keys):
    book = f"{SERIES} 3"
    home, out = _file_of(tmp_path, [(book, 2, False)])
    theirs = home.annotations.series.open(SERIES)
    theirs.settings = {"text_scale": 1.2}
    theirs.save()
    backup.export_books(home, [(book, "English")], out, PASSPHRASE)
    here = _stores(tmp_path / "laptop")
    mine = here.annotations.series.open(SERIES)
    mine.settings = {"text_scale": 0.9}
    mine.save()
    opened = backup.open_export(out, PASSPHRASE)
    r = ImportReviewDialog(hidden_root, opened, backup.plan_import(here, opened), "home.stcache")
    r.withdraw()
    assert r.defaults_box is not None and r.corrections_box is None and r.marks_box is None
    r.defaults_var.set("take")
    r.apply()
    assert r.choice == ImportChoice([0], take_defaults=True)

    reviewed = _importing(monkeypatch, out, review=lambda opened, plan: ImportChoice([0]))  # the defaults: mine stay
    d = _dialog(hidden_root, here)
    d._import()
    assert len(reviewed) == 1 and [x.state for x in reviewed[0][1].defaults] == ["differs"]  # one book, yet asked
    assert here.annotations.series.open(SERIES).settings == {"text_scale": 0.9}
    assert d.backup_var.get().endswith("Series defaults: 0 added, 0 taken from the file, 1 kept as yours.")
    _importing(monkeypatch, out, review=lambda opened, plan: ImportChoice([0], take_defaults=True))
    d._import()
    assert here.annotations.series.open(SERIES).settings == {"text_scale": 1.2}
    assert d.backup_var.get().endswith("Series defaults: 0 added, 1 taken from the file, 0 kept as yours.")
    d.destroy()


# ------------------------------------------------------------------ Rename...
class Window(tk.Toplevel):
    """The window's part a rename from the list goes through: its rename (`_plan_rename`, here done at once with the
    rename module, as the window does it in its worker), busy, and the dialog of the start it may wait for."""

    def __init__(self, master, stores, refuse=False):
        super().__init__(master)
        self.withdraw()
        self.stores, self.refuse, self.asked = stores, refuse, []
        self.busy, self._start_dialog = False, None

    def _plan_rename(self, old, new, model, language, col):
        self.asked.append((old, new, model, language, col))
        if not self.refuse:
            rename.rename_book(self.stores, old, new, language)


def test_rename_hands_the_new_name_to_the_windows_rename_and_the_list_follows(hidden_root, tmp_path, monkeypatch):
    stores = _library(tmp_path)
    window = Window(hidden_root, stores)
    d = CachesDialog(window, stores.cache)
    d.withdraw()
    assert d.rename_flow == window._plan_rename and d.stores is stores.cache  # a window with no other stores
    names = iter([f"{SERIES} 12"])
    monkeypatch.setattr(CachesDialog, "_ask_name", lambda _self, book, then: then(next(names)))
    _choose(d, (f"{SERIES} 10", "English"))
    d._rename()
    assert window.asked == [(f"{SERIES} 10", f"{SERIES} 12", MODEL, "English", None)]
    assert d.backup_var.get() == f"Renamed {SERIES} 10 to {SERIES} 12."
    assert [d._entries[i]["book"] for i in d.tree.selection()] == [f"{SERIES} 12"]
    assert f"{SERIES} 10" not in {b["book"] for b in stores.cache.list()}

    window.refuse = True  # the window said why in its status line
    monkeypatch.setattr(CachesDialog, "_ask_name", lambda _self, book, then: then(f"{OTHER} 9"))
    _choose(d, (f"{OTHER} 1", "English"))
    d._rename()
    assert d.backup_var.get() == f"{OTHER} 1 keeps its name; the status line in the right pane says why."
    window._start_dialog = object()  # the window waits for an answer of its own
    d._rename()
    assert d.backup_var.get() == "Answer TASlation's question about the book's name first." and len(window.asked) == 2
    d.destroy()
    window.destroy()


def test_the_rename_waits_while_the_window_is_busy(hidden_root, tmp_path, monkeypatch):
    stores = _library(tmp_path)
    window = Window(hidden_root, stores)
    window.busy = True
    d = CachesDialog(window, stores.cache)
    d.withdraw()
    later = []
    monkeypatch.setattr(d, "after", lambda ms, then: later.append((ms, then)))
    d._watch_rename(f"{SERIES} 10", f"{SERIES} 12")
    assert [ms for ms, _then in later] == [caches.RENAME_POLL_MS] and d.backup_var.get() == ""
    window.busy = False
    later[0][1]()
    assert d.backup_var.get() == f"{SERIES} 10 keeps its name; the status line in the right pane says why."
    d.destroy()
    window.destroy()


def test_the_new_name_is_asked_for_in_series_and_volume(hidden_root):
    given = []
    r = RenameBookDialog(hidden_root, f"{SERIES} 10", given.append)
    r.withdraw()
    assert r.title() == f"Rename {SERIES} 10"
    assert (r.fields.series_var.get(), r.fields.volume_var.get()) == (SERIES, "10")
    r.fields.volume_var.set("完全版")  # no volume: said under the fields, the dialog stays
    r.apply()
    assert not given and r.winfo_exists() and "完全版 is not a volume" in r.hint_var.get()
    r.fields.volume_var.set("11")
    r.apply()
    assert given == [f"{SERIES} 11"] and not r.winfo_exists()
    r = RenameBookDialog(hidden_root, f"{SERIES} 10", given.append)
    r.withdraw()
    r.apply()  # the same name: nothing to rename
    assert given == [f"{SERIES} 11"] and not r.winfo_exists()
