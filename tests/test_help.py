"""How to use TASlation: the help window (Menu > Help > How to use...), its topics in every language, the tooltips
and the "?" buttons. Everything here stays on the shared hidden root: nothing is ever mapped."""
from __future__ import annotations

import hashlib
import re
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace

import pytest

from taslation import i18n
from taslation.capture import WindowInfo
from taslation.config import Settings
from taslation.i18n import CATALOGS, FEATURE_LANGUAGES, UI_LANGUAGES, _, set_language
from taslation.locales.features import help_guide, help_tips
from taslation.ui import app as app_mod
from taslation.ui import tooltip
from taslation.ui.dialogs.area import AreaDialog
from taslation.ui.dialogs.book_settings import BookSettingsDialog
from taslation.ui.dialogs.caches import CachesDialog
from taslation.ui.dialogs.glossary import GlossaryDialog
from taslation.ui.dialogs.help import (
    TOPICS,
    ExplainBox,
    HelpWindow,
    explain_button,
    modal_up,
)
from taslation.ui.dialogs.notice import NoticeDialog
from taslation.ui.dialogs.review import ReviewDialog
from taslation.ui.tooltip import TIP_DELAY_MS, TIP_WRAP_PX, Tooltip, tip, tip_place

ROOT = Path(__file__).resolve().parents[1]
VIEWER = WindowInfo(hwnd=7, title="Some book - Viewer", class_name="X", pid=7, rect=(0, 0, 960, 540))
# The names of e-book stores and viewers the guide never names, kept as (length, digest) so that this file names
# none of them either (`_names_a_store`); the browsers' names, which the guide may not use either, as they are.
STORES = frozenset({
    (4, "20df3cb50d82a141"), (4, "af280ae65487b41f"), (4, "dad26be96c854877"), (5, "0ad221bf69b4ebdc"),
    (5, "2e255511df488232"), (5, "9dc992c8a302a919"), (6, "70902ec6714c5110"), (6, "a5ec98119a54abac"),
    (7, "16576e9ddcd68ea8"), (7, "20b028cd58faceb2"), (7, "25cc517f7deaab84"), (7, "3593e587fc807a4d"),
    (7, "9a127a68698f3a71"), (7, "aaf9ea51151162af"), (8, "bfdf775ed7b4b361"), (9, "f0a3b2241e2b5992"),
    (10, "3640f8b0f2995397"), (10, "539a28b0782c647e"), (10, "c16fb4df7dd87cc1"), (11, "16d3021e21726048"),
    (11, "35fc7a91b34ab3d5"), (11, "8e7deafed14e4688"), (16, "f709e3a527a31dfb"), (17, "9f16a9917dff0fc9"),
})
BROWSERS = ("chrome", "edge")
TECHNICAL = ("ocr", "ollama", " port ", "json", "pip ", "setup_models", "toml")  # (" port ": "a report " is no port)


def _digest(name: str) -> tuple[int, str]:
    low = name.casefold()
    return len(low), hashlib.blake2b(low.encode("utf-8"), digest_size=8).hexdigest()


def _names_a_store(text: str, stores: frozenset = STORES) -> bool:
    """Whether *text* has the name of a store or viewer of *stores* (`_digest`) in it, anywhere, case folded."""
    low = text.casefold()
    for size in {size for size, _digest in stores}:
        for at in range(len(low) - size + 1):
            if _digest(low[at:at + size]) in stores:
                return True
    return False


def test_a_name_kept_as_a_digest_is_found_anywhere_in_a_text():
    invented = frozenset({_digest("Yomizuq"), _digest("フォリオ書房")})  # (invented names)
    assert _names_a_store("Read in YOMIZUQ for PC", invented) and _names_a_store("フォリオ書房で読む", invented)
    assert not _names_a_store("Read in your viewer for PC", invented) and not _names_a_store("", invented)
    assert not _names_a_store("Read in your viewer for PC") and len(STORES) == 24


def tip_of(widget):
    """The tooltip given to *widget* with `tooltip.tip` (None when it has none)."""
    return getattr(widget, "_tooltip", None)


def _widgets(top):
    found, stack = [], [top]
    while stack:
        w = stack.pop()
        found.append(w)
        stack.extend(w.winfo_children())
    return found


# ------------------------------------------------------------------ the texts
def _guide_keys() -> list[str]:
    return [key for heading, paragraphs in TOPICS for key in (heading, *paragraphs)]


def test_five_topics_of_some_thirty_lines_in_every_language():
    assert [heading for heading, _p in TOPICS] == ["Getting started", "The side panes", "Editing",
                                                   "When something goes wrong", "Your data"]
    assert 30 <= sum(1 + len(paragraphs) for _h, paragraphs in TOPICS) <= 54
    missing = [(code, key[:40]) for key in _guide_keys() + ["How to use...", "How to use TASlation"]
               for code in FEATURE_LANGUAGES if not CATALOGS[code].get(key, "").strip()]
    assert missing == []


def test_every_new_string_has_all_sixteen_languages():
    assert len(FEATURE_LANGUAGES) == 16
    for texts in (help_guide.TEXTS, help_tips.TEXTS):
        for key, translations in texts.items():
            assert set(translations) == set(FEATURE_LANGUAGES), key
            assert all(text.strip() and text != key for text in translations.values()), key


def test_the_guide_names_no_store_or_viewer_and_no_technical_term():
    for key in [*_guide_keys(), *help_tips.TEXTS]:
        low = key.lower()
        assert not _names_a_store(key) and not any(word in low for word in BROWSERS), key
        assert not any(word in low for word in TECHNICAL), key
        for code in FEATURE_LANGUAGES:
            text = CATALOGS[code].get(key, "")  # (a missing one: test_five_topics_of_some_thirty_lines_...)
            assert not _names_a_store(text), (code, key)
            assert "chrome" not in text.lower(), (code, key)  # ("edge": a word in some languages)


def test_the_guide_says_nothing_of_going_back_to_page_one_nor_of_a_key_of_the_old_window():
    text = " ".join(_guide_keys()).lower()
    assert "page 1" not in text and "first page key" not in text
    assert not re.search(r"\bf\d{1,2}\b", text)  # (the panes and the Menu: no function key to press)
    for gone in ("full screen", "reader role", "page keys", "toolbar", "over the book"):
        assert gone not in text, gone


def _guide(start: str) -> str:
    """The key of the topic paragraph that starts with *start*."""
    found = [key for key in _guide_keys() if key.startswith(start)]
    assert len(found) == 1, start
    return found[0]


NAMED = (  # (the start of a topic paragraph, the window's words it names)
    ("At every start TASlation asks", ("OK", "Quit", "Menu", "Viewer...")),
    ("Translate translates the page", ("Translate", "Lettering")),
    ("Left of the page:", ("Translate", "Stop", "Auto", "Lettering", "Indicators", "Reader mode", "Add area", "Set area...",
                           "Settings...", "Menu", "Quit")),
    ("Right of the page,", ("Indicators", "Copy the Japanese", "Copy the translation", "Ask again")),
    ("Rest the pointer", ("Copy the Japanese", "Copy the translation")),
    ("The panes lie", ("Menu",)),
    ("While editing, the viewer", ("Reader mode", "Settings...")),
    ("Add area in the left pane", ("Add area", "Reader mode", "Settings...")),
    ("The numbers' colours", ("Review...",)),
    ("While editing, the Menu", ("Menu", "Undo", "Redo", "Reading order", "Add a text area", "Skip page",
                           "Review...", "My corrections...", "Lines to review...", "Find and replace...",
                           "Series sheet...", "Book settings...")),
    ("A bubble stays untranslated", ("Translate", "Add area")),
    ("TASlation finds no page", ("Set area...",)),
    ("Nothing happens", ("Indicators", "Menu", "Viewer...", "Auto")),
    ("A name comes out wrong", ("Find and replace...", "Menu")),
    ("While you read,", ("Menu", "Help", "Check for updates...")),
    ("Menu > Saved translations...", ("Menu", "Saved translations...", "Help", "About TASlation")),
    ("To keep a spare", ("Menu", "Saved translations...")),
)


def test_the_guide_names_the_controls_by_the_panes_and_the_menus_own_words():
    from taslation.ui import see_edit, seethrough

    assert see_edit.READER_MODE == "Reader mode" and see_edit.ADD_ENTRY == "Add a text area" and see_edit.ADD_AREA == "Add area"
    assert (seethrough.COPY_JAPANESE, seethrough.COPY_TRANSLATION) == ("Copy the Japanese", "Copy the translation")
    for start, words in NAMED:
        key = _guide(start)
        assert all(word in key for word in words), (start, [w for w in words if w not in key])


@pytest.mark.parametrize("code", sorted(FEATURE_LANGUAGES))
def test_the_guide_calls_the_controls_what_the_window_calls_them(code):
    """The menus and buttons named in the topics are the window's own words in that language."""
    catalog = CATALOGS[code]
    for start, words in NAMED:
        key = _guide(start)
        text = catalog.get(key, "")
        assert text, (code, key[:40])  # (translated: test_five_topics_of_some_thirty_lines_...)
        for word in words:
            assert catalog[word].lower() in text.lower(), (code, start, word)


# ------------------------------------------------------------------ the help window
class Window(tk.Toplevel):
    """The App's help on a withdrawn window of the hidden root."""

    open_help = app_mod.App.open_help

    def __init__(self, root, state_dir):
        super().__init__(root)
        self.withdraw()
        self.settings = Settings(state_dir=state_dir)
        self._help = None
        self.later: list = []

    def after(self, ms, func=None, *args):  # kept, run by the test
        self.later.append((ms, func))
        return "after#test"


def test_the_help_opens_scrolls_wraps_and_closes(tmp_path, hidden_root):
    w = Window(hidden_root, tmp_path)
    w.open_help()
    d = w._help
    assert isinstance(d, HelpWindow) and d.state() == "withdrawn"  # out of sight: the tests' parent is not on screen
    assert d.resizable() == (True, True) and tk.Toplevel.grab_current(d) is None  # not modal
    assert d.title() == "How to use TASlation" and str(d.text.cget("wrap")) == "none"
    assert str(d.text.cget("state")) == "disabled" and str(d.text.cget("yscrollcommand"))
    assert d.bind("<Escape>")  # closes with Esc too
    d.close_btn.invoke()
    assert not d.winfo_exists()
    w.open_help()  # after closing: a new one
    assert w._help is not d and w._help.winfo_exists()
    w.destroy()


def test_opening_the_help_twice_raises_the_same_window(tmp_path, hidden_root, monkeypatch):
    w = Window(hidden_root, tmp_path)
    w.open_help()
    first = w._help
    raised = []
    monkeypatch.setattr(HelpWindow, "bring_up", lambda self: raised.append(self))
    w.open_help()
    assert w._help is first and raised == [first]
    w.destroy()


def _shown_lines(d: HelpWindow) -> list[str]:
    return d.text.get("1.0", "end-1c").split("\n")


@pytest.mark.parametrize("code", ["ja", "zh", "ko", "th", "de", "ru"])
def test_the_help_breaks_its_lines_by_hand_in_every_script(tmp_path, hidden_root, code):
    set_language(code)
    w = Window(hidden_root, tmp_path)
    w.open_help()
    d = w._help
    for width in (600, 330):
        d.render(width)
        lines = _shown_lines(d)
        assert all(d._font.measure(line.rstrip(" ")) <= width for line in lines if line), (code, width)
        joined = "".join(lines)
        for heading, paragraphs in TOPICS:
            assert _(heading) in joined
            assert all(_(p).replace(" ", "") in joined.replace(" ", "") for p in paragraphs), code
        assert "TASlation" in joined and joined.count("TASlation") == sum(
            _(k).count("TASlation") for k in [h for h, _p in TOPICS] + [p for _h, ps in TOPICS for p in ps])  # never split
    d.render(330)
    before = _shown_lines(d)
    d.render(330)  # the same width: nothing is done again
    assert _shown_lines(d) == before
    w.destroy()


def test_the_help_keeps_its_place_when_wrapped_anew(tmp_path, hidden_root):
    w = Window(hidden_root, tmp_path)
    w.open_help()
    d = w._help
    d.render(320)
    d.update_idletasks()
    d.text.yview_moveto(0.5)
    at = d.text.yview()[0]
    d.render(400)
    assert abs(d.text.yview()[0] - at) < 0.2
    w.destroy()


def test_help_is_the_first_entry_of_the_menus_help(tmp_path, hidden_root):
    from taslation.ui import see_menu

    called = []
    app = SimpleNamespace(ui_lang_var=tk.StringVar(hidden_root, value="en"), _see_hidden=True, _see_through=None,
                          auto_var=tk.BooleanVar(hidden_root, value=True))
    for name in ("open_caches", "review_names", "open_help", "open_notice", "open_updates", "open_about",
                 "open_settings", "_on_ui_language", "_on_close", "translate_now", "set_area"):
        setattr(app, name, lambda _n=name: called.append(_n))
    menu, language, help_menu = (tk.Menu(hidden_root, tearoff=0) for _ in range(3))
    see_menu.build(app, menu, language, help_menu)
    assert str(help_menu.entrycget(0, "label")) == "How to use..."
    help_menu.invoke(0)
    assert called == ["open_help"]
    for each in (menu, language, help_menu):
        each.destroy()


def test_a_legal_notice_or_a_grab_holds_the_window(tmp_path, hidden_root, monkeypatch):
    from taslation import notice

    monkeypatch.setattr(notice, "default_country", lambda: None)
    w = Window(hidden_root, tmp_path)
    assert not modal_up(w)
    up = NoticeDialog(w, tmp_path, "en", startup=False)
    up.withdraw()
    assert modal_up(w)
    up.destroy()
    assert not modal_up(w)
    w.destroy()


def test_modal_up_asks_tk_for_the_grab(hidden_root):
    assert not modal_up(hidden_root)  # (a real grab needs a window on the screen: asked by name)
    fake = SimpleNamespace(tk=SimpleNamespace(call=lambda *a: ".!combobox.popdown"), winfo_children=lambda: [])
    assert modal_up(fake)


def test_nothing_starts_before_the_legal_notice_is_answered():
    import inspect

    source = inspect.getsource(app_mod.App.__init__)
    assert source.index("notice_due(state_dir)") < source.index("seethrough.start(self)")
    assert "quit_before_start = True\n                return" in source  # Quit: nothing is started


# ------------------------------------------------------------------ a language switch
def test_a_language_switch_brings_the_help_back_in_the_new_language():
    import inspect

    source = inspect.getsource(app_mod.App._rebuild_ui)
    assert source.index("help_place =") < source.index("child.destroy()") < source.index("self.open_help()")


# ------------------------------------------------------------------ tooltips
@pytest.fixture
def unseen(monkeypatch):
    """Tips that are made and placed, and never mapped."""
    shown = []
    monkeypatch.setattr(Tooltip, "_reveal", staticmethod(shown.append))
    monkeypatch.setattr(tooltip.layout, "work_area", lambda widget, x=None, y=None: (0, 0, 1920, 1040))
    return shown


def test_a_tip_appears_after_its_delay_and_hides_on_leave(hidden_root, unseen, monkeypatch):
    monkeypatch.setattr(Tooltip, "_there", lambda self: True)
    b = ttk.Button(hidden_root, text="x")
    t = Tooltip(b, "What this does", delay_ms=5)
    assert TIP_DELAY_MS == 500 and Tooltip(ttk.Button(hidden_root), "x").delay_ms == 500
    t._enter()
    assert t.tip is None and t._job is not None  # not at once
    jobs = []
    monkeypatch.setattr(b, "after", lambda ms, func: (jobs.append(ms), func())[0])
    t._cancel()
    t._enter()
    assert jobs == [5] and t.tip is not None and unseen == [t.tip] and t.tip.state() == "withdrawn"
    assert str(t.tip.winfo_children()[0].cget("text")) == "What this does"
    window = t.tip
    t._leave()
    assert t.tip is None and not window.winfo_exists()
    b.destroy()


def test_a_tip_left_before_its_time_never_shows(hidden_root, unseen, monkeypatch):
    b = ttk.Button(hidden_root)
    t = Tooltip(b, "text")
    t._enter()
    job = t._job
    assert job is not None
    t._leave()
    assert t._job is None and t.tip is None and not unseen
    t._enter()
    t._enter()  # Enter again: one timer, not two
    assert t._job is not None
    b.destroy()  # the widget going takes the timer with it
    assert t._job is None


def test_a_press_hides_the_tip_and_a_second_show_makes_no_second_window(hidden_root, unseen):
    b = ttk.Button(hidden_root)
    t = Tooltip(b, "text")
    t.show()
    window = t.tip
    t.show()
    assert t.tip is window and len(unseen) == 1
    t._leave(SimpleNamespace())  # (what a press of a button or a key calls)
    assert t.tip is None
    b.destroy()


def test_a_control_hidden_meanwhile_shows_no_tip(hidden_root, unseen):
    b = ttk.Button(hidden_root)  # (never mapped: not viewable)
    t = Tooltip(b, "text")
    t._due()
    assert t.tip is None and not unseen
    b.destroy()


def test_a_disabled_ttk_control_shows_its_tip_and_says_why(hidden_root, unseen, monkeypatch):
    """A greyed-out ttk button still gets the pointer's events: its tip comes, and says why it is greyed out."""
    monkeypatch.setattr(Tooltip, "_there", lambda self: True)
    b = ttk.Button(hidden_root, text="x", state="disabled")
    tip("What this does", b, disabled="Why it is grey")
    t = tip_of(b)
    assert t.current() == "Why it is grey"
    b.event_generate("<Enter>")
    hidden_root.update()
    assert t._job is not None  # the timer runs, as over a control that works
    t._cancel()
    t._due()
    assert unseen == [t.tip] and str(t.tip.winfo_children()[0].cget("text")) == "Why it is grey"
    t.hide()
    b.state(["!disabled"])  # asked when it shows: the code that greys it out says nothing to the tip
    assert t.current() == "What this does"
    t.show()
    assert str(t.tip.winfo_children()[0].cget("text")) == "What this does"
    t.hide()
    plain = ttk.Button(hidden_root, text="y", state="disabled")
    tip("Only this", plain)
    assert tip_of(plain).current() == "Only this"  # no reason given: what it does
    b.destroy()
    plain.destroy()


def test_no_text_no_timer(hidden_root):
    b = ttk.Button(hidden_root)
    t = Tooltip(b, "")
    t._enter()
    assert t._job is None
    b.destroy()


WORK = (0, 0, 1920, 1040)


def test_the_tip_goes_under_the_control_and_never_on_it():
    assert tip_place((200, 40), (100, 100, 200, 130), (150, 110), WORK) == (150, 134)


def test_the_tip_stays_on_the_monitor_at_every_corner():
    for pointer in ((0, 0), (1919, 0), (0, 1039), (1919, 1039), (960, 520)):
        for size in ((320, 60), (320, 200), (2, 2)):
            box = (max(0, pointer[0] - 40), max(0, pointer[1] - 10), min(1920, pointer[0] + 40), min(1040, pointer[1] + 10))
            x, y = tip_place(size, box, pointer, WORK)
            assert 0 <= x and x + size[0] <= 1920 and 0 <= y and y + size[1] <= 1040, (pointer, size)
            assert y >= box[3] or y + size[1] <= box[1]  # never over the control: no flicker


def test_the_tip_goes_above_a_control_at_the_bottom_of_the_screen():
    assert tip_place((200, 40), (100, 1000, 200, 1030), (150, 1010), WORK) == (150, 956)


def test_a_second_monitor_left_of_the_first_counts():
    work = (-1920, 0, 0, 1040)
    assert tip_place((320, 40), (-100, 100, -10, 130), (-50, 110), work) == (-320, 134)


def test_a_control_as_tall_as_the_monitor_gets_its_tip_below_the_pointer():
    assert tip_place((200, 40), (0, 0, 1000, 1040), (500, 300), WORK) == (500, 320)
    assert tip_place((200, 40), (0, 0, 1000, 1040), (500, 1030), WORK) == (500, 1000)  # still on the monitor


@pytest.mark.parametrize("code", ["en", "ja", "zh", "th", "ko", "ru"])
def test_a_tip_wraps_at_about_320_pixels_in_every_script(hidden_root, code):
    set_language(code)
    b = ttk.Button(hidden_root)
    text = " ".join(_(key) for key in list(help_tips.TEXTS)[:4])
    lines = Tooltip(b, text).lines().split("\n")
    measure = tkfont.nametofont("TkDefaultFont").measure
    assert len(lines) > 1 and all(measure(line) <= TIP_WRAP_PX for line in lines)
    assert all(not line.endswith(" ") for line in lines)
    b.destroy()


def test_the_tip_uses_colours_tk_knows(hidden_root):
    back, fore = tooltip.tip_colours(hidden_root)
    hidden_root.winfo_rgb(back), hidden_root.winfo_rgb(fore)
    theme = SimpleNamespace()

    def refuse(_name):
        raise tk.TclError("unknown colour")

    theme.winfo_rgb = refuse
    original = tooltip.ttk.Style
    try:
        tooltip.ttk.Style = lambda _w: SimpleNamespace(lookup=lambda style, option: "#123456")
        assert tooltip.tip_colours(theme) == ("#123456", "#123456")
    finally:
        tooltip.ttk.Style = original


# ------------------------------------------------------------------ every control has its tooltip
class Bars(tk.Toplevel):
    _build_toolbar = app_mod.App._build_toolbar
    _build_translator_tools = app_mod.App._build_translator_tools
    _sync_tools = app_mod.App._sync_tools

    def __init__(self, root):
        super().__init__(root)
        self.withdraw()
        self.settings = SimpleNamespace(target_language="English", ollama_model="qwen3.5:4b", role="reader")
        for name in ("window_var", "book_var", "model_var", "lang_var", "role_var"):
            setattr(self, name, tk.StringVar(self))
        for name in ("auto_var", "original_var"):
            setattr(self, name, tk.BooleanVar(self))
        self.role_var.set("reader")

    def __getattr__(self, name):
        if name.startswith(("open_", "toggle_", "_on_", "_rescan", "_redisplay", "translate_", "set_", "enter_", "stop_",
                            "retranslate", "undo_", "redo_", "_turn_direction")):
            return lambda *a: None
        raise AttributeError(name)


CONTROLS = ("TButton", "TCheckbutton", "TRadiobutton", "TCombobox", "TEntry")


@pytest.mark.parametrize("code", sorted(UI_LANGUAGES))
def test_every_control_of_the_toolbar_and_the_strip_has_a_tooltip_in_every_language(hidden_root, code):
    set_language(code)
    w = Bars(hidden_root)
    w._build_toolbar()
    controls = [c for bar in (w.toolbar, w.tools_bar) for c in _widgets(bar) if c.winfo_class() in CONTROLS]
    assert len(controls) >= 19
    for control in controls:
        t = tip_of(control)
        assert t is not None and t.text, (code, control)
        assert t.widget is control and t.delay_ms == TIP_DELAY_MS
        if code != "en":
            assert t.text not in help_tips.TEXTS, (code, t.text)  # translated
    labels = [c for c in _widgets(w.toolbar) if c.winfo_class() == "TLabel"]
    assert labels and all(tip_of(label) is not None for label in labels)  # the control's name says the same
    w.destroy()


def test_the_tooltips_of_the_toolbar_add_nothing_to_its_width(hidden_root):
    w = Bars(hidden_root)
    w._build_toolbar()
    assert not any(isinstance(c, tk.Toplevel) for c in _widgets(w)[1:])
    w.destroy()


# ------------------------------------------------------------------ explanations behind a "?"
def _explained(top) -> list[str]:
    return [c.explanation for c in _widgets(top) if hasattr(c, "explanation")]


def _labels(top) -> list[str]:
    return [" ".join(str(c.cget("text")).split()) for c in _widgets(top) if c.winfo_class() == "TLabel"]


def test_a_question_mark_opens_its_explanation_once(hidden_root):
    frame = ttk.Frame(hidden_root)
    button = explain_button(frame, "What this dialog is for.")
    assert str(button.cget("text")) == "?"
    button.invoke()
    box = button.box
    assert isinstance(box, ExplainBox) and box.message_text == "What this dialog is for." and box.state() == "withdrawn"
    button.invoke()
    assert button.box is box  # the same box
    box.close_btn.invoke()
    assert not box.winfo_exists()
    button.invoke()
    assert button.box is not box
    frame.destroy()


def test_a_long_explanation_is_broken_into_lines(hidden_root):
    set_language("ja")
    key = "Facts the model is told before translating: names and terms with their renderings, who the characters are and how they talk, and how the series should read. Never lines of the book."
    box = ExplainBox(hidden_root, _(key) * 3)
    shown = str(box.label.cget("text"))
    assert shown.count("\n") >= 2 and shown.replace("\n", "") == _(key) * 3
    box.destroy()


def test_the_area_dialogs_instructions_are_behind_the_question_mark(hidden_root):
    from PIL import Image

    d = AreaDialog(hidden_root, Image.new("RGB", (400, 300), "white"), lambda box, size: None, clear=lambda: None)
    d.withdraw()
    assert any(text.startswith("Drag the handles") for text in _explained(d))
    assert not any(text.startswith("Drag the handles") for text in _labels(d))
    assert not hasattr(d, "margins_var") and not any("Margins" in text for text in _labels(d))
    assert [c.explanation for c in d.winfo_children()[0].winfo_children()]  # the "?" stays in the head row
    buttons = {str(c.cget("text")): c for c in _widgets(d) if c.winfo_class() == "TButton"}
    assert "Reset" not in buttons and tip_of(buttons["Clear area"]) is not None  # one way back to no area
    d.destroy()


def test_the_book_settings_explanation_is_behind_the_question_mark(hidden_root):
    pipeline = SimpleNamespace(annotations=SimpleNamespace(settings={}), _base_settings=Settings(),
                               set_book_settings=lambda values: None)
    d = BookSettingsDialog(hidden_root, pipeline, on_change=lambda: None)
    d.withdraw()
    assert any(text.startswith("These choices apply") for text in _explained(d))
    assert not any(text.startswith("These choices apply") for text in _labels(d))
    d.destroy()


def test_the_caches_dialog_keeps_the_export_warning_in_view(hidden_root, tmp_path):
    from taslation.cache import CacheStore

    d = CachesDialog(hidden_root, CacheStore(tmp_path / "cache"))
    d.withdraw()
    held = _explained(d)
    assert any(text.startswith("Each file holds") for text in held)
    labels = _labels(d)
    assert any("never give it to anyone" in text for text in labels)  # a warning stays
    assert not any(text.startswith("Each file holds") for text in labels)
    d.destroy()


def test_the_series_sheet_hints_became_tooltips_and_no_translation_was_lost(hidden_root, tmp_path):
    from taslation.annotations import GlossaryStore

    set_language("ja")
    d = GlossaryDialog(hidden_root, GlossaryStore(tmp_path), "A series", "English", on_change=lambda: None)
    d.withdraw()
    assert any(text.startswith("翻訳前にモデルへ伝える前提情報") for text in _explained(d))
    labels = _labels(d)
    assert not any(text.startswith(("（keep:", "（このパソコンに", "（種別ごとの")) for text in labels)
    tips = [tip_of(c).text for c in _widgets(d) if tip_of(c) is not None]
    assert any("敬称の訳し方" in text for text in tips)
    assert any(text.startswith("このパソコンにインストール") for text in tips)  # without its brackets
    assert any(text.startswith("種別ごとのフォントファミリー") for text in tips)
    assert not any(text[0] in "(（" or text[-1] in ")）" for text in tips)
    assert any(text.startswith("種類ごとの書体") for text in labels)  # the heading of the lettering list stays
    assert "心の声" in labels and "thought" not in labels and "sfx" not in labels  # the kinds in the window's words
    assert any(text.startswith("この人物がほかの人をどう呼ぶか") for text in tips)  # and the fields say what they want
    d.destroy()


def test_the_review_list_keeps_its_explanation_behind_the_question_mark(hidden_root):
    d = ReviewDialog(hidden_root, [], on_edit=lambda region: None)
    d.withdraw()
    assert any(text.startswith("Regions flagged for a look") for text in _explained(d))
    assert not any(text.startswith("Regions flagged for a look") for text in _labels(d))
    d.destroy()


def test_the_moved_strings_keep_every_translation():
    moved = [key for key in CATALOGS["ja"] if key.startswith((
        "Drag the handles to resize", "These choices apply to this", "Each file holds translated",
        "Facts the model is told", "Regions flagged for a look", "How honorifics such as", "(a font installed", "(font family per kind"))]
    assert len(moved) == 8
    for key in moved:
        assert all(key in CATALOGS[code] for code in FEATURE_LANGUAGES), key


def test_the_architecture_document_names_the_new_modules():
    text = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "taslation/ui/tooltip.py" in text and "taslation/ui/dialogs/help.py" in text


def test_the_window_can_be_told_where_its_flag_lives(tmp_path):
    assert i18n.load_ui_flag(tmp_path, "x") is False
    i18n.save_ui_flag(tmp_path, "x")
    assert i18n.load_ui_flag(tmp_path, "x") is True
    i18n.save_ui_flag(tmp_path, "x", False)
    assert i18n.load_ui_flag(tmp_path, "x") is False
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ui.json"]
