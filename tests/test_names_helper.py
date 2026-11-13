"""The window's side of the name helper (`ui.name_check`, `ui.dialogs.names`): what a run found kept for its book and
offered on the band and in the Tools menu; a rendering chosen changes the name's other lines through the replace
machinery (one step: the dialog's Take back and Ctrl+Z take it back) and goes to the series sheet, which Take back
gives back as it was; the dialog lists the renderings and says what Apply changes. Synthetic lines only."""
from __future__ import annotations

import inspect
import random
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from taslation.annotations import CharacterSheet, GlossaryStore
from taslation.cache import CachedBubble, CachedPage, CacheStore
from taslation.fingerprint import FINGERPRINT_HEX_LEN
from taslation.i18n import CATALOGS
from taslation.locales.features import names_helper
from taslation.name_variants import RunLine, find_variants
from taslation.ui import app as app_mod
from taslation.ui import name_check, status
from taslation.ui.dialogs.names import NamesDialog, labels, list_line
from taslation.ui.history import EditHistory

ROOT = Path(__file__).resolve().parents[1]

PAIRS = [("竜司さん、おはよう", "Morning, Ryuji-san."), ("竜司さんは？", "Where's Ryuji-san?"),
         ("竜司さん！", "Ryūji-san!"), ("竜司が来た", "Ryuji is here."), ("竜司くんか", "Ryūji, huh."),
         ("おはよう", "Good morning."), ("時間がない", "There is no time."), ("行こう", "Let's go."),
         ("隠れて", "Hide here."), ("待って", "Wait for me.")]


def fingerprint(seed: int) -> str:
    return f"{random.Random(seed).getrandbits(FINGERPRINT_HEX_LEN * 4):0{FINGERPRINT_HEX_LEN}x}"


def box(i: int) -> tuple[float, float, float, float]:
    return (0.1, 0.05 + 0.15 * (i % 5), 0.3, 0.15 + 0.15 * (i % 5))


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
    """The parts of the App the name helper uses."""

    _batching = False
    batch = None
    _names_dialog = None
    _names_found = None
    _ordering = None
    review_names = app_mod.App.review_names
    _book_cache = app_mod.App._book_cache
    _stored = app_mod.App._stored
    _carry_replacement = app_mod.App._carry_replacement
    undo_edit = app_mod.App.undo_edit
    redo_edit = app_mod.App.redo_edit
    _step_through = app_mod.App._step_through

    def __init__(self, cache, sheets):
        self.pipeline = SimpleNamespace(
            cache=cache, annotations=None, last=None, check_sheet=lambda: None, rerender=lambda r: None,
            settings=SimpleNamespace(fingerprint_max_distance=36, match_min_iou=0.3))
        self.glossary_store = sheets
        self.last_result = None
        self.history = EditHistory()
        self.role_var, self.book_var, self.lang_var = Var("translator"), Var("Book"), Var("English")
        self.reading = self.busy = False
        self.events: list[str] = []
        self.said: list[str] = []
        self.lines: list[str] = []
        self.refreshed: list[tuple[str, str]] = []
        self._jobs = Jobs()

    def _job_refresh_premises(self, book, language):
        self.refreshed.append((book, language))

    def _post(self, kind, **data):
        self.events.append(kind)
        if kind == "translate_done":
            self.busy = False
        elif kind == "names_applied":
            name_check.names_applied(self, data)

    def _go_busy(self):
        self.busy = True

    def say(self, key, **values):
        self.said.append(key)

    def status(self, render):
        self.lines.append(render())

    def _result_on_show(self):
        return True


@pytest.fixture
def cache(tmp_path):
    c = CacheStore(tmp_path / "cache").open("Book", "m")
    c.pages = [CachedPage(fingerprint=fingerprint(p), aspect=0.7, seq=p,
                          bubbles=[CachedBubble(box=box(i), text=en) for i, (_ja, en) in enumerate(PAIRS) if i // 5 == p])
               for p in range(2)]
    c.dirty = True
    c.save()
    return c


@pytest.fixture
def sheets(tmp_path):
    return GlossaryStore(tmp_path / "glossary")


@pytest.fixture
def window(cache, sheets):
    w = Window(cache, sheets)
    lines = [RunLine(ja, en, (fingerprint(i // 5), box(i))) for i, (ja, en) in enumerate(PAIRS)]
    progress = SimpleNamespace(names=find_variants(lines), name_lines=[line._replace(source="") for line in lines])
    assert name_check.keep_found(w, progress, "Book", "English") == 1
    return w


def texts(cache):
    return [b.text for p in sorted(cache.pages, key=lambda p: p.seq) for b in p.bubbles]


def character(sheets, name="竜司"):
    return next((c for c in sheets.open("Book", "English").characters if c.name == name), None)


BEFORE = [en for _ja, en in PAIRS]
AFTER = ["Morning, Ryūji-san.", "Where's Ryūji-san?", "Ryūji-san!", "Ryūji is here.", "Ryūji, huh.", *BEFORE[5:]]


def test_what_a_run_found_is_for_its_book_and_language_only(window):
    assert name_check.found_for(window) is not None
    window.lang_var.set("German")
    assert name_check.found_for(window) is None
    window.lang_var.set("English")
    window.book_var.set("Another book")
    window.review_names()
    assert window.said[-1].startswith("No whole-book run in this session found a name")
    nothing = SimpleNamespace(names=[], name_lines=[])
    assert name_check.keep_found(window, nothing, "Another book", "English") == 0
    assert window._names_found.book == "Book"  # (a run that found nothing keeps what the last one found)


def test_a_rendering_chosen_changes_the_other_lines_and_goes_to_the_sheet(window, cache, sheets, tmp_path):
    (v,) = window._names_found.variants
    assert name_check.apply_name(window, v, "Ryūji", True)
    assert texts(cache) == AFTER and texts(CacheStore(tmp_path / "cache").open("Book", "m")) == AFTER
    assert character(sheets).rendering == "Ryūji" and window.refreshed == [("Book", "English")]
    assert not window.busy and window.events[-1] == "translate_done"
    assert window.lines[-1] == '竜司 is "Ryūji" now: changed in 3 line(s).'
    assert v.renderings == [("Ryūji", [0, 1, 2, 3, 4])] and len(window.history) == 1
    assert [line.text for line in window._names_found.lines] == AFTER  # the run's lines follow
    assert not name_check.apply_name(window, v, "Ryuji", True)
    assert window.said[-1] == "Take back the change made first, then choose again."

    assert name_check.take_back_name(window, v)
    assert texts(cache) == BEFORE and character(sheets) is None  # the sheet had no such character
    assert texts(CacheStore(tmp_path / "cache").open("Book", "m")) == BEFORE
    assert v.counts() == [("Ryuji", 3), ("Ryūji", 2)] and not window._names_found.done
    assert [line.text for line in window._names_found.lines] == BEFORE
    assert window.lines[-1] == "竜司: the change is taken back (3 line(s))."


def test_a_sheet_rendering_is_given_back_and_a_change_can_skip_the_sheet(window, cache, sheets):
    sheet = sheets.open("Book", "English")
    sheet.set_character(CharacterSheet(name="竜司", rendering="Ryuuji", role="kept"))
    sheet.save()
    (v,) = window._names_found.variants
    assert name_check.apply_name(window, v, "Ryuji", True)
    assert texts(cache)[2] == "Ryuji-san!" and texts(cache)[4] == "Ryuji, huh."
    assert character(sheets).rendering == "Ryuji" and character(sheets).role == "kept"
    assert name_check.take_back_name(window, v)
    assert character(sheets).rendering == "Ryuuji" and character(sheets).role == "kept"
    assert name_check.apply_name(window, v, "Ryouji", False)  # typed, and not for the sheet
    assert texts(cache)[:5] == ["Morning, Ryouji-san.", "Where's Ryouji-san?", "Ryouji-san!", "Ryouji is here.",
                                "Ryouji, huh."]
    assert character(sheets).rendering == "Ryuuji" and window.refreshed == [("Book", "English")] * 2
    assert name_check.take_back_name(window, v)
    assert texts(cache) == BEFORE and character(sheets).rendering == "Ryuuji"


def test_ctrl_z_takes_the_lines_back_and_take_back_then_gives_the_sheet_back(window, cache, sheets):
    (v,) = window._names_found.variants
    assert name_check.apply_name(window, v, "Ryūji", True)
    window.undo_edit()
    assert texts(cache) == BEFORE
    assert name_check.take_back_name(window, v)
    assert texts(cache) == BEFORE and character(sheets) is None and not window._names_found.done
    window.redo_edit()  # nothing of the name's left to make again
    assert texts(cache) == BEFORE


def test_a_line_changed_since_stays_as_it_is(window, cache):
    cache.pages[0].bubbles[1].text = "Where's Ryuji now?"
    (v,) = window._names_found.variants
    assert name_check.apply_name(window, v, "Ryūji", True)
    assert texts(cache)[:5] == ["Morning, Ryūji-san.", "Where's Ryuji now?", "Ryūji-san!", "Ryūji is here.",
                                "Ryūji, huh."]
    assert window.lines[-1] == '竜司 is "Ryūji" now: changed in 2 line(s).'


def test_nothing_is_asked_while_the_window_is_at_work(window, cache):
    (v,) = window._names_found.variants
    window.busy = True
    assert not name_check.apply_name(window, v, "Ryūji", True)
    assert window.said[-1] == "TASlation is at work on a page. Try again when it is done." and texts(cache) == BEFORE
    window.busy = False
    window.pipeline = None
    assert not name_check.apply_name(window, v, "Ryūji", True)


def test_the_band_offers_the_names_after_a_run():
    source = inspect.getsource(status)
    assert '"{n} name(s) rendered in more than one way across the book."' in source
    assert '_("Review names..."), self.review_names' in source
    assert "name_check.keep_found" in inspect.getsource(app_mod.App._batch_done)
    assert 'command=self.review_names' in inspect.getsource(app_mod.App)


# ------------------------------------------------------------------ the dialog
def test_the_dialog_lists_the_renderings_and_says_what_apply_changes(hidden_root, window):
    (v,) = window._names_found.variants
    asked: list[tuple[str, bool]] = []
    d = NamesDialog(hidden_root, [v], on_apply=lambda v_, chosen, to_sheet: asked.append((chosen, to_sheet)) or True,
                    on_take_back=lambda v_: True)
    assert labels(d) == ["Ryuji - 3 line(s)", "Ryūji - 2 line(s)"]
    assert d.picked() == "Ryuji" and str(d.preview.cget("text")) == "Changes 2 line(s)."
    assert d.back_btn.instate(["disabled"])
    d.choice.set("Ryūji")
    d._preview()
    assert str(d.preview.cget("text")) == "Changes 3 line(s)."
    d.choice.set("\x00other")
    d.other.set("Ryuuji")
    assert str(d.preview.cget("text")) == "Changes 5 line(s)."
    d.to_sheet.set(False)
    d.apply()
    assert asked == [("Ryuuji", False)]
    d.applied(v, "Ryuuji", "done")
    assert d.listbox.get(0) == list_line(v, "Ryuuji") and str(d.line.cget("text")) == "done"
    assert d.back_btn.instate(["!disabled"]) and d.picked() == "Ryuuji"
    d.other.set("")
    d.choice.set("\x00other")
    d.apply()
    assert str(d.line.cget("text")) == "Choose a rendering, or type one." and len(asked) == 1
    d.destroy()


def test_the_sheets_rendering_is_named_and_picked(hidden_root, window):
    (v,) = window._names_found.variants
    v.sheet = "Ryūji"
    d = NamesDialog(hidden_root, [v], on_apply=lambda *a: True, on_take_back=lambda v_: True)
    assert labels(d) == ["Ryuji - 3 line(s)", "Ryūji - 2 line(s) (series sheet)"] and d.picked() == "Ryūji"
    d.destroy()


def test_the_helpers_words_are_in_every_language():
    languages = set(CATALOGS) - {"en"}
    assert len(languages) == 16
    for key, by_language in names_helper.TEXTS.items():
        assert set(by_language) == languages, key
        for lang, text in by_language.items():
            assert CATALOGS[lang][key] == text and text.strip(), (lang, key)


# ------------------------------------------------------------------ the measuring tool
def test_the_eval_tools_second_spellings_are_what_the_helper_finds():
    sys.path.insert(0, str(ROOT / "tools"))
    import names_eval

    assert names_eval.second_spelling("Tsubasa") == "Tubasa" and names_eval.second_spelling("Ichikawa") == "Ichigawa"
    assert names_eval.second_spelling("Lena") == "Rena"
    lines = [RunLine(ja, en.replace("Ryūji", "Ryuji"), ("f", box(i))) for i, (ja, en) in enumerate(PAIRS)]
    assert find_variants(lines) == []
    injected, given = names_eval.inject(lines)
    assert given == {"竜司": {"ryuji", "ryuzi"}}
    (v,) = find_variants(injected)
    assert {spelling for spelling, _at in v.renderings} == {"Ryuji", "Ryuzi"}
    assert names_eval.shuffled_offers(lines, 2) == (6, 0)
