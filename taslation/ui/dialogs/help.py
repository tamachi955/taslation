"""How to use TASlation: Menu > Help > How to use... (`HelpWindow`: short topics, one string per paragraph, in the
window's language; texts in `locales/features/help_guide.py` and `locales/features/one_mode.py`), and the "?" button
that opens one explanation in a box of its own (`explain_button`, `ExplainBox`). Neither holds anything up: TASlation
goes on reading behind them."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from typing import Callable

from ...i18n import _
from ..banner import break_lines
from ..layout import dialog_area, place_window, work_area
from ..wrap import wrap_line
from .notice import NoticeDialog

TOPICS: tuple[tuple[str, tuple[str, ...]], ...] = (  # (heading, its paragraphs): the keys of the window's catalogs
    ("Getting started", (
        "Open your book in its viewer. A viewer in a browser works best in a browser window of its own.",
        "At every start TASlation asks which window shows your book; the viewer you chose before comes first in the list. Choose it and press OK or Enter (Quit ends TASlation). It lays its lettering over that window; Menu > Viewer... chooses another one.",
        "Choose your language in the left pane: a click on its row lists them all, and a click on one takes it. The first time, TASlation may ask for the book's name.",
        "Read in the viewer as it is: turn the pages there, with its own keys, buttons or clicks. TASlation presses no key and sends no click to the viewer, turns no page by itself and reads only the page the viewer shows. With Auto on, each page you turn is lettered in your language.",
        "Translate translates the page on show now; the circular arrow beside it translates it again, asking every line anew. Lettering hides the translation, so that the page shows as the viewer has it, and shows it again.",
    )),
    ("The side panes", (
        "Left of the page: Translate (Stop while a page is being translated), Auto, your language, Lettering, Indicators, Reader mode, Add area, Set area..., Settings..., Menu and Quit.",
        "Right of the page, while Indicators is on: the bubble last under the pointer, its Japanese and its translation, with Copy the Japanese, Copy the translation and Ask again, then what TASlation is doing. At the bottom, in places that do not move: how much of the page is done, the mode, where the translator runs, the viewer followed, and your language with the book's name.",
        "Rest the pointer on a bubble to see the original lettering in its place. TASlation puts nothing on the clipboard by itself: only Copy the Japanese and Copy the translation do.",
        "The panes lie on the viewer's ground beside the page, and a pane hides where it would come near the page. TASlation's taskbar button then opens the Menu with the left pane's controls.",
    )),
    ("Editing", (
        "TASlation starts editing: the page's regions are outlined boxes with numbers in the reading order. Click a box to open it in the region editor, drag it to move it, drag a corner to resize it; Shift+click chooses several. A drag on empty space adds a text area there.",
        "While editing, the viewer takes the keys only: turn the pages with the keys. To use the mouse in the viewer, check Reader mode in the left pane; Settings... can start TASlation in Reader mode.",
        "Click a box's number to type its place in the reading order, then press Enter: the numbers follow, and the lines after it are translated again. Menu > Undo takes it all back.",
        "Add area in the left pane, or Insert while the viewer is in front, adds a text area in Reader mode too: drag a rectangle over the text, and it is read and translated. A right click, Insert or Add area again gives it up. Insert is the only key TASlation takes (Settings... turns it off).",
        "The numbers' colours: green translated, orange not translated, blue your own region, red worth a look (Review...).",
        "While editing, the Menu has the editing: Undo and Redo, the page's tools (Reading order, Add a text area, Skip page), and Review..., My corrections..., Lines to review..., Find and replace..., Series sheet... and Book settings... as dialogs of their own.",
    )),
    ("When something goes wrong", (
        "The viewer's page reads black: TASlation waits for it to load and, after a while, says so in the right pane. Reload the book in the viewer; TASlation goes on with the page it shows then.",
        "Some viewers do not allow their window to be read and always show black. TASlation leaves that as it is. Such a viewer cannot be used with TASlation.",
        "A bubble stays untranslated: press Translate. If it is still empty, press Add area in the left pane (or Insert) and drag a rectangle over the text; if a box is already there, drag or resize it while editing.",
        "A line of one character, or lettering far larger than the rest, is not read by itself: add it by hand.",
        "TASlation finds no page, or reads too much of the window: Set area... in the left pane lets you mark the page yourself.",
        "Nothing happens: read the lines in the right pane (Indicators on). Check Menu > Viewer... and that Auto is on.",
        "The translation program starts by itself. If new pages are not translated, press Translate in a moment; if that does not help, restart your PC.",
        "When you close TASlation, it stops the translation program it started, unless another program is using it. If you started the translation program yourself, TASlation leaves it running.",
        "With a viewer in a browser, the book's tab must be the one in front.",
        "A name comes out wrong all through the book: while editing, Find and replace... in the Menu changes it on every page at once.",
        "To report a problem: Menu > Copy a report puts what TASlation knows of the page on show on the clipboard, numbers and states with no text of the page and no titles, ready to paste where you ask for help. While editing, Copy a report of this region in the region editor does it for that region; only With this region's text adds its Japanese and its translation. Nothing is sent anywhere.",
    )),
    ("Your data", (
        "While you read, TASlation sends nothing anywhere but to the translation program on this computer. The network is used only when you install or update TASlation, when you agree to download a translation model, which TASlation offers when the model for the language you translate into is not installed, and, only if you turn it on or choose Menu > Help > Check for updates..., to look for a new version: then check_update.py, a program of its own, asks GitHub for one small file.",
        "It keeps the translated text with the place of each bubble, matched to each page by a short code made from its picture, what the book's colophon says of it (title, volume, author, publisher, ISBN), a code made with a secret key from each short line it reuses, and your corrections, series sheets and notes. The book's name is in the names of those files and, with the title of the viewer's window (and its program's name, for an app), in settings files that are not protected.",
        "No page image is ever kept, nor the Japanese lines, and there is no way to save a page. A translation shows only over its page in the viewer.",
        "Menu > Saved translations... lists the translations and deletes them. Series sheets, page marks, the viewers' and TASlation's settings, an error log with no text of a book and the time of the last look for a new version, with the newest version found, are kept too, in the folder named in Menu > Help > About TASlation.",
        "The translations, series sheets and notes are protected for your Windows user on this computer: copied to another computer, or opened by another Windows user, they cannot be read. Programs you run yourself can still read them.",
        "To keep a spare, or to move a book's translations to another computer, make an encrypted copy of them in Menu > Saved translations...; series sheets and notes stay on this computer. If the translations matter to you, keep such a copy: an administrator's reset of your Windows password, a new Windows profile or a reinstalled Windows leaves the saved files unreadable.",
    )),
)
EXPLAIN_WRAP = 600  # pixels: a "?" box's text is broken into lines this wide
HELP_SIZE = (640, 660)  # the help window's first size, less where the screen has no room
HELP_MIN = (360, 260)
HELP_PAD = 14  # pixels of the text box's own margin
HELP_FIRST_WIDTH = 600  # pixels: the text's width until the window is on the screen


def modal_up(window: tk.Misc) -> bool:
    """Whether a dialog holds the window's input: a grab (asked of Tk: a combobox's open list has one too, which has
    no Tkinter widget) or a legal notice."""
    try:
        return bool(window.tk.call("grab", "current")) or any(isinstance(c, NoticeDialog) for c in window.winfo_children())
    except tk.TclError:
        return True


class HelpWindow(tk.Toplevel):
    """Menu > Help > How to use...: `TOPICS` in the window's language in a resizable, scrolling window that holds
    nothing else up. The box never wraps by itself; `wrap_line` breaks the text for the box's width, again whenever
    the window is resized (Tk breaks lines only at spaces: not Japanese, not Thai), so it can still be selected; a
    heading at the top stays there when the text is broken again (`topics`: where each heading starts)."""

    def __init__(self, master: tk.Misc):
        super().__init__(master)
        self.withdraw()
        self.title(_("How to use TASlation"))
        self.transient(master)
        self.minsize(*HELP_MIN)
        try:  # (the work area it lands on, `place_window`'s: the viewer's monitor in see-through mode)
            left, top, right, bottom = (dialog_area(self, master)[0] if master.winfo_viewable()
                                        else work_area(self))
        except tk.TclError:
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
        """Every topic in lines of at most *width* pixels (*again*: also at the width it has); the place in the text
        stays."""
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
            for paragraph in paragraphs:
                self._insert(_(paragraph), width, self._font.measure, ("start",))
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


    def _insert(self, text: str, width: int, measure: Callable[[str], int], first: tuple[str, ...]) -> None:
        for i, line in enumerate(wrap_line(text, width, measure)):
            self.text.insert("end", line + "\n", first if i == 0 or "heading" in first else ())


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
