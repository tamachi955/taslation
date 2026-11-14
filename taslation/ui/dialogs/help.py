"""How to use TASlation, in the window: Help > How to use... (F1; `HelpWindow`: short topics, one string per paragraph,
in the window's language; texts in `locales/features/help_guide.py`), whose Keys topic lists every key as the keymap
has it (`topic_lines`: `shortcuts.help_lines`) and which Help > Keys... (Shift+F1) opens at that topic
(`HelpWindow.show_topic`), the small popup of a first start (`FirstSteps`, `first_steps_due`) and the "?" button that
opens one explanation in a box of its own (`explain_button`, `ExplainBox`). None of them holds anything up: the window
goes on reading behind them."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk
from typing import Callable

from ...i18n import _, load_ui_flag
from .. import shortcuts
from ..banner import break_lines
from ..layout import place_by_book, place_window, work_area
from ..wrap import wrap_line
from .notice import NoticeDialog

TOPICS: tuple[tuple[str, tuple[str, ...]], ...] = (  # (heading, its paragraphs): the keys of the window's catalogs
    ("Getting started", (
        "Open your book in its viewer. A viewer in a browser works best in a browser window of its own.",
        "TASlation finds the viewer by itself. If it does not, choose the viewer's window in the Viewer list.",
        "Choose your language in the To list. The first time, TASlation may ask for the book's name.",
        "Turn the pages here, in TASlation's window: press the viewer's page keys or click the page, and TASlation passes them on to the viewer. With Auto on, it shows each page translated.",
        "F5 translates the page on show now. Keep a strip of the viewer visible, or use reading mode.",
        "TASlation may enlarge the viewer's window so that the page reads well; the window goes back to its size when you close TASlation.",
    )),
    ("Reading mode", (
        "Press F11, or the Reading mode button, to see the page alone on the full screen.",
        "The page keys and clicks on the page still go to the viewer, and new pages are followed.",
        "F11 or Esc leaves reading mode and gives the window back as it was.",
        "View > Show original shows the page as it is in the viewer. Reading mode always shows the translation.",
        "Optional: you can put the viewer in its own full screen yourself, in the viewer (often with F11 there). TASlation never does it for you.",
        "With the viewer in full screen on TASlation's monitor, TASlation stays on top of it without taking its keys, as the on-screen keyboard does: turn the pages in the viewer as usual and TASlation follows. F5 still translates, and in reading mode F11 and Esc leave it.",
        "Clicks on TASlation's buttons and page strip work as ever. A box you type in, and every dialog, takes the keys while you use it. View > Over the full-screen viewer turns this off; with the book on another monitor nothing changes.",
    )),
    ("Reading a whole book", (
        "This is optional: page by page, as you read, is the normal way. Check your store's terms of use first.",
        "Open the book at the first page you want, then choose Read whole book... and Start.",
        "TASlation never turns a page itself. You turn the pages at your own pace and it reads each one; when you press Finished reading it translates the whole book at once, without the viewer.",
        "Going back reads nothing twice. If you turn very fast, the line above the page asks you to wait a moment. Stop ends the run: while you read nothing is translated yet; afterwards what is translated stays.",
        "While a whole book is read, a strip under the page shows each page you have turned, with three bars: R reads the text, E erases the Japanese, T is its translation. An empty bar has not started, a moving one is under way, a filled one is done, a crossed one did not work, a hatched one was not needed.",
        "The T bars fill only after Finished reading, when the whole book is translated together; meanwhile the page being translated is shown here, and the viewer's page again once the run ends. The strip only shows how far each page has come: to read a page, open it in the viewer, and TASlation shows the translation over it. The line beside the strip says how much memory the pages take.",
        "If a page goes by before it could be read, the line above the page says so at once and the strip shows a dashed frame with a question mark in its place. Turn back to it in the viewer and it is read like any other.",
    )),
    ("Page keys", (
        "Arrow keys, Page Up, Page Down, Home, End and Space pressed on the page go on to the viewer.",
        "Page > Page keys... sets the keys that turn pages in your viewer. A right-to-left book often turns with the left arrow.",
        "Apply keeps the keys. Try them on the page in TASlation's window: TASlation presses no key by itself.",
        "To go back to an earlier page, use the viewer's own seek bar.",
    )),
    ("The Translator role", (
        "Press F5 first, then double-click a box to edit it.",
        "Green: translated. Orange: not translated, its label says why. Blue: your own rectangle. Red ?: worth a look (Review...).",
        "Under the toolbar, this role has its tools: Series sheet..., Review..., Find and replace..., Undo and Redo.",
    )),
    ("Keys", ()),  # every key as the keymap has it (`topic_lines`)
    ("When something goes wrong", (
        "The viewer stays black: TASlation may be covering it completely. Make TASlation smaller or move it so that a strip of the viewer shows.",
        "If it stays black, TASlation tries to bring it back by itself. If that does not help, check the viewer and press F5.",
        "Some viewers do not allow their window to be read and always show black. TASlation leaves that as it is. Such a viewer cannot be used with TASlation.",
        "A bubble stays untranslated: press F5. If it is still empty, choose the Translator role and drag from outside the text to draw a rectangle round it; if an orange box is already there, drag or resize that box instead.",
        "A line of one character, or lettering far larger than the rest, is not read by itself: add it by hand.",
        "TASlation finds no page, or reads too much of the window: Page > Set area... lets you mark the page yourself.",
        "Nothing happens: read the line under the page, and the coloured line above it if there is one. Check the Viewer list and that Auto is on.",
        "The translation program starts by itself. If new pages are not translated, press F5 in a moment; if that does not help, restart your PC.",
        "When you close TASlation, it stops the translation program it started, unless another program is using it. If you started the translation program yourself, TASlation leaves it running.",
        "With a viewer in a browser, the book's tab must be the one in front.",
        "A name comes out wrong all through the book: in the Translator role, Find and replace... changes it on every page at once.",
    )),
    ("Your data", (
        "Everything stays on this computer: TASlation sends nothing out.",
        "It keeps the translated text with the place of each bubble, matched to each page by a short code made from its picture. Your series sheet and notes are kept too.",
        "No page image is ever kept, nor the Japanese lines, and there is no way to save a page. A translation shows only over its page in the viewer.",
        "Tools > Saved translations... lists the translations and deletes them. Series sheets, page marks and viewer settings are kept too, in the folder named in Help > About TASlation.",
        "The translations, series sheets and notes are protected for your Windows user on this computer: copied to another computer, or opened by another Windows user, they cannot be read. Programs you run yourself can still read them.",
        "To keep a spare, or to move a book's translations to another computer, make an encrypted copy of them in Tools > Saved translations...; series sheets and notes stay on this computer. If the translations matter to you, keep such a copy: an administrator's reset of your Windows password, a new Windows profile or a reinstalled Windows leaves the saved files unreadable.",
    )),
)
FIRST_LINES = (  # the popup of a first start
    "1. Open your book in its viewer.",
    "2. If TASlation does not find it by itself, choose its window in the Viewer list.",
    "3. Turn the pages here, with the page keys or a click on the page: TASlation shows them translated.",
)
FIRST_STEPS_FLAG = "first_steps_done"  # in ui.json: true once the popup has shown
EXPLAIN_WRAP = 600  # pixels: a "?" box's text is broken into lines this wide
FIRST_WRAP = 440  # pixels: the first start's lines
HELP_SIZE = (640, 660)  # the help window's first size, less where the screen has no room
HELP_MIN = (360, 260)
HELP_PAD = 14  # pixels of the text box's own margin
HELP_FIRST_WIDTH = 600  # pixels: the text's width until the window is on the screen
KEYS_TOPIC = "Keys"  # every key as the keymap in force has it (`topic_lines`); Help > Keys... opens the help there


def topic_lines(heading: str, paragraphs: tuple[str, ...]) -> list[str]:
    """The paragraphs of a topic in the window's language: for the Keys every key as the window has it, the fixed
    ones and the mouse gestures after them (`shortcuts.help_lines`), with where they are changed."""
    if heading != KEYS_TOPIC:
        return [_(p) for p in paragraphs]
    return [*shortcuts.help_lines(shortcuts.current()), _("Tools > Settings... > Shortcuts changes these keys.")]


def first_steps_due(state_dir: Path | str) -> bool:
    """Whether the popup of a first start still has to show on this machine (ui.json)."""
    return not load_ui_flag(Path(state_dir), FIRST_STEPS_FLAG)


def modal_up(window: tk.Misc) -> bool:
    """Whether a dialog holds the window's input: a grab (asked of Tk: a combobox's open list has one too, which has
    no Tkinter widget) or a legal notice."""
    try:
        return bool(window.tk.call("grab", "current")) or any(isinstance(c, NoticeDialog) for c in window.winfo_children())
    except tk.TclError:
        return True


class HelpWindow(tk.Toplevel):
    """Help > How to use...: `TOPICS` in the window's language in a resizable, scrolling window that holds nothing
    else up. The box never wraps by itself; `wrap_line` breaks the text for the box's width, again whenever the window
    is resized (Tk breaks lines only at spaces: not Japanese, not Thai), so it can still be selected. `show_topic`
    brings a topic's heading to the top (Help > Keys...: the Keys); a heading at the top stays there when the text is
    broken again (`topics`: where each heading starts)."""

    def __init__(self, master: tk.Misc):
        super().__init__(master)
        self.withdraw()
        self.title(_("How to use TASlation"))
        self.transient(master)
        self.minsize(*HELP_MIN)
        left, top, right, bottom = work_area(self)
        self.geometry(f"{min(HELP_SIZE[0], right - left - 40)}x{min(HELP_SIZE[1], bottom - top - 100)}")
        self._font = tkfont.nametofont("TkDefaultFont")
        self._bold = tkfont.Font(self, font=self._font)
        self._bold.configure(weight="bold")
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill="both", expand=True)
        row = ttk.Frame(frm)  # packed before the text so that it always shows
        row.pack(side="bottom", fill="x", pady=(8, 0))
        self.close_btn = ttk.Button(row, text=_("Close"), command=self.destroy)
        self.close_btn.pack(side="right")
        body = ttk.Frame(frm)
        body.pack(fill="both", expand=True)
        self.text = tk.Text(body, width=40, height=10, font=self._font, padx=HELP_PAD, pady=8, wrap="none",
                            cursor="arrow", takefocus=0)
        self.text.tag_configure("heading", font=self._bold, spacing1=12, spacing3=2)
        self.text.tag_configure("start", spacing1=5)
        self.scroll = ttk.Scrollbar(body, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.wrapped_at = 0
        self._job: str | None = None
        self.topics: dict[str, str] = {}  # heading (English) -> the index its line starts at
        self.render(HELP_FIRST_WIDTH)
        self.text.bind("<Configure>", self._resized)
        self.bind("<Escape>", lambda _e: self.destroy())
        for keysym, amount, what in (("Up", -1, "units"), ("Down", 1, "units"), ("Prior", -1, "pages"), ("Next", 1, "pages")):
            self.bind(f"<{keysym}>", lambda _e, a=amount, w=what: self.text.yview_scroll(a, w))
        place_window(self, master)
        self.bring_up()

    def bring_up(self) -> None:
        """On the screen and in front; with a window not on the screen (the tests' root) it stays out of sight."""
        if self.master.winfo_viewable():
            self.deiconify()
            self.lift()
            self.close_btn.focus_set()

    def _resized(self, event: tk.Event) -> None:
        width = max(HELP_MIN[0] // 2, event.width - 2 * HELP_PAD - 6)
        if width != self.wrapped_at and self._job is None:
            self._job = self.after_idle(self._rewrap)

    def _rewrap(self) -> None:
        self._job = None
        try:
            self.render(max(HELP_MIN[0] // 2, self.text.winfo_width() - 2 * HELP_PAD - 6))
        except tk.TclError:  # the window is going
            pass

    def render(self, width: int, again: bool = False) -> None:
        """Every topic in lines of at most *width* pixels (*again*: also at the width it has, the keys changed); the
        place in the text stays."""
        if width == self.wrapped_at and not again:
            return
        self.wrapped_at = width
        at = self.text.yview()[0]
        top = self._heading_on_top()
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.topics = {}
        for heading, paragraphs in TOPICS:
            self.topics[heading] = self.text.index("end-1c")
            self._insert(_(heading), width, self._bold.measure, ("heading",))
            for paragraph in topic_lines(heading, paragraphs):
                self._insert(paragraph, width, self._font.measure, ("start",))
        self.text.configure(state="disabled")
        if top is not None:
            self.text.yview(self.topics[top])
        else:
            self.text.yview_moveto(at)

    def _heading_on_top(self) -> str | None:
        """The topic whose heading is the first line shown, if one is."""
        try:
            first = self.text.index("@0,0")
        except tk.TclError:
            return None
        return next((heading for heading, index in self.topics.items() if index == first), None)

    def show_topic(self, heading: str) -> None:
        """The topic *heading* (English, as in `TOPICS`) at the top of the text, as far as the text goes on."""
        index = self.topics.get(heading)
        if index is not None:
            self.text.yview(index)

    def _insert(self, text: str, width: int, measure: Callable[[str], int], first: tuple[str, ...]) -> None:
        for i, line in enumerate(wrap_line(text, width, measure)):
            self.text.insert("end", line + "\n", first if i == 0 or "heading" in first else ())


class FirstSteps(tk.Toplevel):
    """The first start's popup over the window: what to do first and a button that opens the help. It shows once, and
    holds nothing up. *on_close* follows its closing; *on_help* follows the help button, which closes it too."""

    def __init__(self, master: tk.Misc, on_close: Callable[[], None], on_help: Callable[[], None]):
        super().__init__(master)
        self.withdraw()
        self.title("TASlation")
        self.transient(master)
        self.resizable(False, False)
        self.on_close, self.on_help = on_close, on_help
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)
        for key in FIRST_LINES:
            label = ttk.Label(frm, justify="left")
            label.configure(text=break_lines(_(key), FIRST_WRAP, label))
            label.pack(anchor="w", pady=(0, 4))
        row = ttk.Frame(frm)
        row.pack(fill="x", pady=(12, 0))
        self.close_btn = ttk.Button(row, text=_("Close"), command=self.close)
        self.close_btn.pack(side="right")
        self.help_btn = ttk.Button(row, text=_("How to use..."), command=self.open_help)
        self.help_btn.pack(side="right", padx=(0, 6))
        self.bind("<Escape>", lambda _e: self.close())
        self.protocol("WM_DELETE_WINDOW", self.close)
        place_by_book(self, master)  # where the reader looks; it takes no key (a click closes it)
        if master.winfo_viewable():  # (a window not on the screen, as in the tests, keeps it out of sight)
            self.deiconify()

    def close(self) -> None:
        self.destroy()
        self.on_close()

    def open_help(self) -> None:
        self.close()
        self.on_help()


class ExplainBox(tk.Toplevel):
    """One explanation in a small box of its own over the dialog that has it, its text broken into lines by hand."""

    def __init__(self, master: tk.Misc, text: str):
        super().__init__(master)
        self.withdraw()
        self.title("TASlation")
        owner = master.winfo_toplevel()
        self.transient(owner)
        self.resizable(False, False)
        self.message_text = text
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)
        self.label = ttk.Label(frm, justify="left")
        self.label.configure(text=break_lines(text, EXPLAIN_WRAP, self.label))
        self.label.pack(anchor="w")
        self.close_btn = ttk.Button(frm, text=_("Close"), command=self.destroy)
        self.close_btn.pack(anchor="e", pady=(12, 0))
        for keysym in ("Escape", "Return", "KP_Enter"):
            self.bind(f"<{keysym}>", lambda _e: self.destroy())
        place_window(self, owner)
        if owner.winfo_viewable():
            self.deiconify()
            self.close_btn.focus_set()


def explain_button(parent: tk.Misc, text: str) -> ttk.Button:
    """A small "?" button that opens *text* in an `ExplainBox`: the explanation of a dialog, out of its way."""

    def show() -> None:
        box = getattr(button, "box", None)
        if box is not None and box.winfo_exists():
            box.lift()
        else:
            button.box = ExplainBox(parent, text)  # type: ignore[attr-defined]

    button = ttk.Button(parent, text="?", width=3, command=show)
    button.explanation = text  # type: ignore[attr-defined]
    return button
