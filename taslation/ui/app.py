"""The reader window.

Layout: menus for what is used seldom, a toolbar for what is used all the time, whose
groups of controls flow into as many rows as the window's width needs (the viewer,
the target language, Translate / Auto / Reading mode, the role, the book and the
batch), translator mode's strip under it while the Translator role is chosen, a
canvas and a status bar: every command has one place. The canvas shows the chosen viewer
live - its latest frame, with the translation laid over it while it shows a
translated page - and a page being translated fills in on it bubble by bubble.
Reading mode (F11) shows the page alone, full screen. All heavy work runs in
one worker thread; Tk only draws. Page images live in memory only; nothing is
written to disk except the text-only translation cache and the per-window
capture margins.

The window is put together here (`App`, `run_app`); its parts are the modules beside this one: the mixins `App`
is made of (`status`, `live`, `jobs`, `reading`, `translator`, `viewers`), the dialogs (`dialogs/`), and what they
share (`layout`, `progress`, `wrap`, `constants`). Every public name defined here before still imports from here
(`__all__`), but `work_area` and `frame_extents`: a test patches those in `layout`, where they are used. A test
that patches a name the window's code looks up patches it in the module that uses it (`live.capture_window`).
"""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk
from typing import Any, Callable

import numpy as np
from PIL import Image

from .. import jurisdictions, notice, protect, viewerparts
from ..annotations import AnnotationStore, GlossaryStore
from ..batch import BatchReader, keep_awake, release_awake
from ..cache import CacheStore, viewer_key_from_title
from ..capture import WindowInfo
from ..config import Settings
from ..i18n import (
    UI_LANGUAGES,
    _,
    current,
    load_ui_language,
    load_ui_table,
    save_ui_entry,
    save_ui_flag,
    save_ui_language,
    set_language,
)
from ..notes import series_key
from ..ollama_start import finish_all
from ..translate.models import wanted_name
from ..pagekeys import Profiles
from ..regions import PageResult
from .constants import (
    APP_TITLE,
    BLANK_SPREAD,
    FORWARDED_KEYS,
    LANGUAGES,
    LIVE_CHANGE,
    NO_VIEWER,
    QUEUE_RANK,
    READING_MODE,
    READING_NOTE_MS,
    READING_ONLY,
    READY,
    WINDOW_ALPHA,
    WINDOW_TARGETS,
    WINDOW_WATCH_MS,
    in_a_run,
)
from .copy_details import watch_error_boxes
from .dialogs import caches as boxes
from .dialogs.area import AreaDialog
from .dialogs.batch import BatchDialog
from .dialogs.caches import CachesDialog, PassphraseDialog, WarningBox, import_error_text
from .dialogs.glossary import GlossaryDialog
from .dialogs.help import FIRST_STEPS_FLAG, KEYS_TOPIC, FirstSteps, HelpWindow, first_steps_due, modal_up
from .dialogs.notice import NoticeDialog, notice_due
from .dialogs.review import EditBubbleDialog, ReviewDialog, review_rows
from .dialogs.book_settings import BookSettingsDialog
from .book_areas import IGNORE_EVERYWHERE, IGNORE_TIP, AreaMixin
from .font_memory import FontMemory
from .dialogs.settings import PAGE_SETTINGS, SettingsDialog, warn_ignored
from .history import EditHistory
from .jobs import JobsMixin
from .layout import (
    APP_ID,
    ASSETS,
    DEFAULT_SIZE,
    ICON_ICO,
    ICON_PNG,
    MIN_SIZE,
    FlowBar,
    apply_icon,
    fit_columns,
    fit_combobox,
    give_icons,
    initial_geometry,
    place_window,
    set_app_id,
    wrap_label,
)
from .live import LiveViewMixin
from .model_switch import ModelSwitchMixin
from .overbook import MOVE_BUTTON, MOVE_OFFER, OverBookMixin, opening_place
from .preview import ImageCanvas
from .progress import (
    FILL_COLOUR,
    LOADING,
    STATUS_WORDS,
    WORK_STAGES,
    Filling,
    busy_line,
    progress_line,
    reads_page,
    stage_of,
    status_word,
)
from .reading import ReadingMixin
from .scaling import DpiWatch, apply_scale
from . import shortcuts
from .. import devices
from .status import StatusMixin
from .strip import StripMixin, close_warning, release_run_images
from .tooltip import tip, tip_menu
from .replace import ReplaceMixin
from .formats import PAGE_FORMAT_TIPS, FormatMixin
from .selection import ORDER_NUMBERS_TIP, PAGE_SELECTION_TIPS, SelectionMixin
from .translator import NUDGES, TOOLBAR_GAP, TranslatorMixin
from .viewers import NOT_VIEWERS, ViewerMixin, choose_viewer, looks_like_viewer
from .wrap import is_cjk, wrap_line, wrap_text


FIRST_STEPS_MS = 800  # the first start's popup comes this long after the window, once nothing modal is up ...
FIRST_STEPS_RETRY_MS = 1000  # ... looked for again this often
TARGET_TABLE, TARGET_ENTRY = "translation", "language"  # where ui.json keeps the "To:" box
VIEWER_CHARS, BOOK_CHARS = 18, 14  # the toolbar's boxes, in "0" widths: narrow enough for one row at the first size ...
VIEWER_LIST_CHARS = 40  # ... and the Viewer list wider than its box as it opens (the style's postoffset), for whole titles
PAGE_KEY_CLASSES = ("TButton", "TCheckbutton", "TRadiobutton")  # controls that take the focus from the page when clicked


def shown_target(language: str) -> str:
    """A target language as the "To:" box shows it: one of the list by its name in the window's language, any other as
    it was typed. What is kept and what the model is told stay the English name (`stored_target`)."""
    return _(language) if language in LANGUAGES else language


def stored_target(shown: str) -> str:
    """What the "To:" box's text stands for: the English name of the list's language it names (in the window's language
    or in English), else the text as it is."""
    typed = shown.strip()
    return next((language for language in LANGUAGES if typed in (language, _(language))), shown)


def protect_saved_files(state_dir: Path) -> protect.Tally | None:
    """At the window's start, before any store reads them: the saved files with text of a book still in plain text
    (an earlier version's caches, annotations and series sheets, with the copies kept beside them) replaced by their
    protected form, each in its own atomic step (`protect.migrate`; a file that fails stays as it was and is tried
    again at the next start). On the Tk thread, so that no save of this window runs meanwhile: once, a fraction of a
    second for a few dozen books; then only a look at each file's first bytes. The counts it found (the log has them
    too, never a name), or None where this system cannot protect files (a save says so itself) or it failed."""
    if not protect.available():
        return None
    try:
        return protect.migrate(state_dir)
    except Exception as e:  # noqa: BLE001 - the window starts all the same; the files stay as they were
        protect.LOG.warning("the saved files could not be protected at the start: %s", type(e).__name__)
        return None


def first_target(state_dir: Path, configured: str, window_language: str, first_start: bool) -> str:
    """The target language the window starts with: one given by --language or the configuration; else the one last
    chosen (ui.json); else, at the very first start, the window's language when it is one of the list, kept from
    then on; else the default."""
    if configured != Settings.target_language:
        return configured
    saved = load_ui_table(state_dir, TARGET_TABLE).get(TARGET_ENTRY, "").strip()
    if saved:
        return saved
    if first_start and window_language in WINDOW_TARGETS:
        save_ui_entry(state_dir, TARGET_TABLE, TARGET_ENTRY, WINDOW_TARGETS[window_language])
        return WINDOW_TARGETS[window_language]
    return configured


class App(StatusMixin, LiveViewMixin, JobsMixin, ReadingMixin, TranslatorMixin, ReplaceMixin, FormatMixin, SelectionMixin,
          ViewerMixin, StripMixin, OverBookMixin, ModelSwitchMixin, AreaMixin, tk.Tk):
    """The reader window. Its state is made here (`__init__`), and its widgets (`_build_ui`, again after a language
    switch); the small dialogs open from here. What it does comes from the mixins: the status line and the busy badge
    (`status`), the capture, the live picture and Auto (`live`), the worker, its events and the requests (`jobs`),
    reading mode and the window's size and place (`reading`), translator mode (`translator`; several regions selected
    and the reading-order badges: `selection`), the viewer list, the area and the offline guard (`viewers`), the
    window over a full-screen viewer (`overbook`)."""

    def __init__(self, settings: Settings, window_query: str | None = None, book: str | None = None, auto: bool = True,
                 on_top: bool = False, reading: bool = False):
        set_app_id()
        super().__init__()
        self._apply_alpha()  # before the window is first shown: an alpha set later makes a browser behind it flicker
        apply_icon(self)
        give_icons(self)  # the taskbar takes the big one
        self.title(APP_TITLE)
        try:  # the monitor's DPI times the reader's UI scale, before anything is measured (`scaling`)
            apply_scale(self, settings.ui_scale)
        except tk.TclError:
            pass
        self.minsize(*(min(m, s) for m, s in zip(MIN_SIZE, (self.winfo_screenwidth() - 40, self.winfo_screenheight() - 90))))
        state_dir = Path(settings.state_dir)
        # where the reader put the window last, once it had been over the book (overbook: the next start opens there,
        # before any viewer is followed); else in the middle of the primary monitor
        place = opening_place(state_dir)
        self._opening_zoomed = bool(place and place[1])
        # the window's size and place while neither maximised nor full screen
        self._normal_geometry = place[0] if place else initial_geometry(self)
        self._restoring = False  # a saved size and place is being put back: what Tk reports meanwhile is not kept
        self.geometry(self._normal_geometry)
        self.quit_before_start = False
        first_start = load_ui_language(state_dir) is None
        code = settings.ui_language or load_ui_language(state_dir)
        if notice_due(state_dir):  # the legal notice, where the first start also chooses the country and language
            self.withdraw()
            dialog = NoticeDialog(self, state_dir, code)
            give_icons(dialog)  # before the window, it has a taskbar button of its own
            place_window(dialog)  # the window is not on the screen yet: in the middle of the screen
            try:
                dialog.grab_set()
                dialog.focus_force()
            except tk.TclError:
                pass
            self.wait_window(dialog)
            if not dialog.accepted:  # Quit: run_app closes the window, nothing starts
                self.quit_before_start = True
                return
            code = dialog.language
        code = set_language(code or jurisdictions.default_language(notice.country(state_dir)) or "en")
        self.ui_lang_var = tk.StringVar(value=code)
        self._models: list[str] = []

        self.settings = settings
        # the saved files with text of a book an earlier version left in plain text, protected for this Windows user
        # before any store reads them (once; `protect_saved_files`); the worker's start says how many (`_job_init`)
        self._protection = protect_saved_files(state_dir)
        viewerparts.use(settings.state_dir)  # what was learned of the viewers on this computer (an older folder: once)
        settings.target_language = first_target(state_dir, settings.target_language, code, first_start)
        self._target_kept = settings.target_language  # what ui.json holds of the "To:" box, or will
        self.store = CacheStore(settings.cache_dir)
        self.profiles = Profiles(Path(settings.state_dir) / "profiles.json")
        self.pipeline: Any = None
        self.translator: Any = None
        self.ready = False
        self.busy = False
        self.batch: BatchReader | None = None
        self.windows: list[WindowInfo] = []
        self.selected: WindowInfo | None = None
        self.window_query = (window_query or "").strip()
        self._tied_said: tuple[int, ...] = ()  # the windows said to look like a viewer equally well (the reader picks)
        self._waiting = False  # the viewer window shows another tab; Auto mode is holding back
        self.annotation_store = AnnotationStore(settings.annotations_dir)
        self.glossary_store = GlossaryStore(settings.glossary_dir)
        self._book_scanned = False  # whole-book mode: the batch has been started for this book in this session
        self._resume_auto = False  # turn Auto back on when the automatic whole-book batch finishes
        self._drag_start: tuple[int, int] | None = None
        self._drag_rect: int | None = None
        self._ordering: list[Any] | None = None  # translator mode: regions clicked so far while setting the reading order
        self.tool_btns: list[ttk.Button] = []
        self.last_result: PageResult | None = None
        self._book_edited = bool(book)
        self._book_given = bool(book)  # --book: the name stays whatever viewer is chosen
        self._book_before = ""  # the Book box as a key found it
        self._viewer_closed: WindowInfo | None = None  # the viewer whose window was closed (`_viewer_gone`)
        self._auto_last: Any = None
        self._auto_candidate: Any = None
        self._events: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        self._jobs: queue.Queue[Callable[[], None]] = queue.Queue()

        self.reading = False  # the reading window: the page alone, full screen, above the viewer
        self._reading_at_start = reading  # --reading: the reading window opens once a viewer is chosen
        # before the reading window: ((size and place, maximised), Auto, alpha)
        self._reading_saved: tuple[tuple[str, bool], bool, float] = (("", False), True, 1.0)
        self._original_saved = False  # Show original before the reading window, which has no way to change it
        self._viewer_hidden = False  # reading mode: the viewer gives no frame of its own behind the reading window
        self._enlarged: Enlarged | None = None  # the chosen viewer's window as TASlation enlarged it, to put back
        self._enlarge_asked: int | None = None  # the viewer whose window was enlarged, or looked at for it, once
        self._enlarging: dict[str, Any] | None = None  # the enlarged window being waited for (`_enlarge_wait`)
        self._area_large = False  # the area in use is the one of the enlarged window (`_sync_area`)
        self._scan_waits_told = False
        self._batching = False
        self._area_hinted = False
        self._status_render: Callable[[], str] | None = None  # the status line in the window's language, again
        self._status_key: str | None = None  # ... and its key, when it was said with `say`
        self._manual_area = False  # the reader set the chosen viewer's area: the page is looked for inside it only
        self._hand_area: tuple[int, int, int, int] | None = None  # ... that area, as the reader set it (margins)
        self._page_areas: dict[str, tuple[tuple[int, int], tuple[int, int, int, int] | None]] = {}  # viewer -> (size, page box)
        # viewer -> (size, the reader's area, the page box found inside it): the capture area is what they share
        self._inner_areas: dict[str, tuple[tuple[int, int], tuple[int, int, int, int],
                                           tuple[int, int, int, int] | None]] = {}
        self._busy_since = time.monotonic()
        self._progress = ""  # the pipeline's latest progress message
        self._busy_shown = False  # the busy band is on the page
        self._chosen_region: Any = None  # translator mode: the region selected on the page ...
        self._grip: str | None = None  # ... what a press took hold of ("move" or a handle) ...
        self._grip_start: tuple[float, float] | None = None  # ... where (image pixels) ...
        self._grip_box: tuple[int, int, int, int] | None = None  # ... and its box as it is dragged or stored
        self._turn: dict[str, Any] | None = None  # ... or its rotate handle's drag (`TranslatorMixin._on_press`)
        self._frame_cache: Any = None  # the selected region's turned frame, kept while it stays as it is
        self._live: Image.Image | None = None  # the viewer's latest frame on show (the live view; memory only) ...
        self._live_thumb: np.ndarray | None = None  # ... and its thumbnail (None: the next frame is shown)
        self._job_frame: Image.Image | None = None  # the frame the running translation reads ...
        self._job_thumb: np.ndarray | None = None  # ... and its thumbnail, when known
        self._fill: Filling | None = None  # the page filling in while it is translated
        self._fill_dirty = False  # page events came in: the page is drawn again once the queue is empty
        self._covered = False  # the viewer draws nothing behind TASlation: the last good frame stays, with a line
        self._thumbs: list[tuple[Any, Image.Image, np.ndarray]] = []  # capture-area thumbnails of recent frames
        self._lettered_memo: tuple[Image.Image, Image.Image, Image.Image] | None = None  # (page, frame, both)
        self._mask_memo: tuple[Image.Image, np.ndarray, np.ndarray] | None = None  # (page, where its lettering is, its pixels)
        self._queued: tuple[str, tuple[Any, ...]] | None = None  # a request waiting for the models or for a job
        self._help: HelpWindow | None = None  # Help > How to use..., while it is open
        self._first_steps: FirstSteps | None = None  # the first start's popup, while it is open
        # the setup checks and their banner, a book's start, the scan band, a page translation that can be cancelled
        self._init_flow_state()
        self._init_over()  # (its setting is on the View menu)
        self._init_selection()  # several regions selected, the reading-order badges (`selection`; View menu too)
        self.keymap = shortcuts.Keymap.load(state_dir)  # the window's keys (`_bind_shortcuts`), Tools > Settings...
        shortcuts.set_current(self.keymap)
        self._bound_keys: list[tuple[str, str]] = []
        self._build_ui()
        self.say("Starting...")  # said again in the window's language after a switch
        # With the menu bar in place, the size again (a menu bar attached to a window already made takes its room
        # from the inside), and once more after Tk's own resizing.
        self.geometry(self._normal_geometry)
        if self.state() == "withdrawn":
            self.deiconify()
        self._restore_geometry((self._normal_geometry, self._opening_zoomed))
        self.bind("<Configure>", self._track_geometry, add="+")
        # moved to a monitor of another scale: the text follows (`scaling`)
        self._dpi_watch = DpiWatch(self, lambda: self.settings.ui_scale)
        watch_error_boxes(self)  # an error box gets Copy details (the version, the system, the last error)
        if book:
            self.book_var.set(book)
        self.auto_var.set(auto)
        self.top_var.set(on_top)
        self._apply_on_top()
        self._apply_alpha()
        self._put_back_left_enlarged()  # a viewer's window a session that ended without closing left enlarged
        self.refresh_windows(select=window_query)
        self._redisplay()  # with no viewer yet, the hint says what to do
        self.after(WINDOW_WATCH_MS, self._watch_windows)
        threading.Thread(target=self._worker_loop, daemon=True).start()
        self._jobs.put(self._job_init)
        self.after(80, self._poll_events)
        self.after(settings.auto_interval_ms, self._auto_tick)
        self.after(FIRST_STEPS_MS, self._offer_first_steps)
        if settings.ignored_keys:
            self.after(FIRST_STEPS_MS, self._warn_ignored)
        self.bind_class("Toplevel", "<Map>", self._first_steps_wait, add="+")
        self.bind("<Escape>", self._escape_key)  # (the other keys: `_bind_shortcuts`)
        for name in PAGE_KEY_CLASSES:  # (after the class's own binding: the command has run)
            self.bind_class(name, "<ButtonRelease-1>", self._after_control, add="+")
        self.bind_class("TCombobox", "<<ComboboxSelected>>", self._after_control, add="+")
        self.history = EditHistory()
        self._editor: Any = None  # the open region editor, which the model's answers go to
        self._review: Any = None  # the open review list
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ the keys and the page
    def _edit_key(self, event: tk.Event, step: Callable[[], None]) -> None:
        """Ctrl+Z or Ctrl+Y: *step*, unless they were typed in a box of the toolbar (the Book or To box), where they
        have nothing to do with the page's edits."""
        if not isinstance(event.widget, (tk.Entry, tk.Text)):
            step()

    def _escape_key(self, event: tk.Event) -> None:
        """Esc in the window: in a box of its own (the Book box, the To box) the page takes the keys back and nothing
        else happens; anywhere else what Esc does there (`_on_escape`)."""
        widget = event.widget
        if isinstance(widget, (tk.Entry, tk.Text)) and widget.winfo_toplevel() is self:
            self._focus_page()
            return
        self._on_escape()

    def _after_control(self, event: tk.Event) -> None:
        """A button, a check box or a list of the window was used: the page takes the keys back (a ttk control keeps
        the focus it took, where Space would press it and the page keys go nowhere), once the command has done what
        it does."""
        try:
            own = event.widget.winfo_toplevel() is self
        except (AttributeError, tk.TclError):  # its command took it away (the band's Close)
            own = True
        if own:
            self.after_idle(self._focus_page)

    def _focus_page(self) -> None:
        """The page takes the keys, unless a dialog has them by now."""
        try:
            focus = self.focus_get()
            if focus is None or focus.winfo_toplevel() is self:
                self.canvas.focus_set()
        except (KeyError, tk.TclError):  # (a list's popdown, a window going)
            pass

    def _book_key(self, event: tk.Event) -> None:
        """A key in the Book box: as it goes down the box is noted, as it comes up a box that changed is a name of the
        reader's (Tab, the arrows and the like change nothing)."""
        if event.type == tk.EventType.KeyPress:
            self._book_before = self.book_var.get()
        elif self.book_var.get() != self._book_before:
            self._book_edited, self._book_scanned = True, False

    def _target_typed(self) -> None:
        """The "To:" box changed: the target language follows, by its English name."""
        language = stored_target(self.lang_shown.get())
        if language != self.lang_var.get():
            self.lang_var.set(language)

    def _target_set(self) -> None:
        """The target language changed by itself (a language switch keeping it): the "To:" box follows."""
        if stored_target(self.lang_shown.get()) != self.lang_var.get():
            self.lang_shown.set(shown_target(self.lang_var.get()))

    def _target_chosen(self) -> None:
        """The "To:" box chosen or typed: kept in ui.json for the next start."""
        language = self.lang_var.get().strip()
        if language and language != self._target_kept:
            self._target_kept = language
            save_ui_entry(Path(self.settings.state_dir), TARGET_TABLE, TARGET_ENTRY, language)

    def _target_picked(self) -> None:
        """The "To:" box left with another language: a language whose translator model is not installed is offered
        first (`ModelSwitchMixin._translator_ready`: a no puts the language before back); then, with Auto on, the page
        on show follows it (from the cache when it is there), as the next page would."""
        before = self._target_kept
        self._target_chosen()
        if self._target_kept == before or not self._translator_ready(self._target_kept, before):
            return
        if self.auto_var.get() and self.last_result is not None and self.batch is None:
            self.translate_now()

    # ------------------------------------------------------------------ UI
    def _open_forms(self) -> list[tk.Toplevel]:
        """The dialogs open with fields a language switch would lose (they go with the widgets; the ones that come
        back by themselves are not among them, and those that hold the window never see a switch)."""
        from .dialogs.pagekeys import PageKeysDialog

        forms = (GlossaryDialog, BookSettingsDialog, BatchDialog, PageKeysDialog)
        return [w for w in self.winfo_children() if isinstance(w, forms) and w.winfo_exists()]

    def _on_ui_language(self) -> None:
        """The Language menu: switch the window's language now and remember it; with dialogs open whose fields the
        switch would lose, the reader is asked first."""
        if self._open_forms() and not boxes.ask(self, _("Changing the language closes the open dialogs; what you typed in them and did not save is lost. Change it now?"),
                                                _("Change it now"), _("Not now")):
            self.ui_lang_var.set(current())
            return
        code = set_language(self.ui_lang_var.get())
        self.ui_lang_var.set(code)
        save_ui_language(Path(self.settings.state_dir), code)
        self._rebuild_ui()

    def open_notice(self) -> None:
        """Help > Legal notice...: the legal notice again, modal over the window; a language chosen there relabels the
        window as the Language menu does (the dialog has saved it, and the country)."""
        before = self.ui_lang_var.get()
        dialog = NoticeDialog(self, Path(self.settings.state_dir), before, startup=False)
        self.wait_window(dialog)
        if dialog.accepted and dialog.language != before:
            self.ui_lang_var.set(dialog.language)
            self._rebuild_ui()

    def open_keys(self) -> None:
        """Help > Keys... (Shift+F1): the help at its Keys topic, which lists every key as the keymap has it."""
        self.open_help()
        self._help.show_topic(KEYS_TOPIC)

    def open_help(self) -> None:
        """Help > How to use... (F1): the help window, or the one already open brought to the front."""
        window = getattr(self, "_help", None)
        if window is not None and window.winfo_exists():
            window.bring_up()
        else:
            self._help = HelpWindow(self)

    def _offer_first_steps(self) -> None:
        """A first start on this machine: the small popup on what to do first, once: closed, it does not come again
        (ui.json). It waits while a dialog holds the window (the legal notice among them), while a book's start is
        under way (the start dialog comes first: its answer is what the popup's last step goes on from) and in
        reading mode; it is no dialog itself: the start's work goes on behind it. One window at a time: a dialog that
        holds the window while the popup is up puts it away until that dialog is answered (`_first_steps_wait`)."""
        if getattr(self, "_first_steps", None) is not None or not first_steps_due(self.settings.state_dir):
            return
        starting = getattr(self, "_start_dialog", None) is not None or getattr(self, "_start_pending", None) is not None
        if self.reading or starting or modal_up(self):
            self.after(FIRST_STEPS_RETRY_MS, self._offer_first_steps)
            return
        self._first_steps = FirstSteps(self, on_close=self._first_steps_closed, on_help=self.open_help)

    def _first_steps_wait(self, event: tk.Event) -> None:
        """A dialog came on the screen while the first start's popup is up: one that holds the window (the start
        dialog) puts the popup away - unclosed, so it comes again once nothing holds the window - for two windows at
        once, one of them not taking a click, is what the reader would see."""
        steps = getattr(self, "_first_steps", None)
        if steps is None or event.widget is steps or not isinstance(event.widget, tk.Toplevel) or not modal_up(self):
            return
        self._first_steps = None
        try:
            steps.destroy()
        except tk.TclError:
            pass
        self.after(FIRST_STEPS_RETRY_MS, self._offer_first_steps)

    def _first_steps_closed(self) -> None:
        self._first_steps = None
        save_ui_flag(Path(self.settings.state_dir), FIRST_STEPS_FLAG)

    def _rebuild_ui(self) -> None:
        """Build the widgets again in the current language, keeping every setting, the page on screen, the status
        line (said again in the new language), the window's size and place, and the help and the first start's popup
        when they were open."""
        left_reading = self.reading
        saved = self._reading_saved[0] if left_reading else self._current_geometry()
        if left_reading:
            self.leave_reading(restore=False)
        keep = {name: getattr(self, name).get() for name in ("book_var", "model_var", "lang_var", "auto_var",
                                                              "original_var", "top_var", "role_var")}
        render, line, key = self._status_render, self.status_var.get(), self._status_key
        ordering = self._ordering
        viewer, edited = self.selected, self._book_edited
        if self._start_dialog is not None:  # it goes with the widgets: the book's next page asks again
            self._start_dialog = self._start_pending = None
        help_window, steps = self._help, self._first_steps  # they go with the widgets too, and come back below
        help_place = help_window.geometry() if help_window is not None and help_window.winfo_exists() else None
        find_kept = self._find_kept()  # find and replace too, with what it shows
        self._help = self._first_steps = None
        for child in list(self.winfo_children()):
            child.destroy()
        self._build_ui()
        for name, value in keep.items():
            getattr(self, name).set(value)
        self._ordering = ordering
        if ordering is not None:
            self._label_order(_("Finish order"))
        self.refresh_windows()
        if viewer is not None and self.selected is not None and viewer.hwnd == self.selected.hwnd:
            self.book_var.set(keep["book_var"])  # a language switch is no choice of a viewer: another tab may be on show
            self._book_edited = edited
        self._sync_tools()
        self._apply_on_top()
        self._set_busy(self.busy)
        self._sync_stop()
        if self._busy_shown:
            self.canvas.set_busy(self._busy_text)
        if self._covered:  # the new canvas says it again
            self._covered = False
            self._set_covered(True)
        self._show_banner()  # the setup banner and the scan band in the new language
        self._show_band()
        self._status_render, self._status_key = render, key
        self.status_var.set(render() if render is not None else line)
        self._show_notes()
        self._redisplay()
        self._restore_geometry(saved, rezoom=left_reading)
        if steps is not None:
            self._offer_first_steps()
        if help_place is not None:
            self.open_help()
            self._help.geometry(help_place)
        if find_kept is not None:
            self.open_find_replace(find_kept)

    def _build_ui(self) -> None:
        self.window_var = tk.StringVar()
        self.book_var = tk.StringVar()
        # the Ollama model the window translates with: the one the target language needs, until Ollama's models are
        # known (`_choose_model`)
        self.model_var = tk.StringVar(value=wanted_name(self.settings.ollama_model, self.settings.target_language))
        self.lang_var = tk.StringVar(value=self.settings.target_language)
        self.auto_var = tk.BooleanVar(value=False)
        self.auto_var.trace_add("write", lambda *_a: self._auto_switched())  # turned off by a run: said once
        self.original_var = tk.BooleanVar(value=False)
        self.top_var = tk.BooleanVar(value=False)
        self.role_var = tk.StringVar(value=self.settings.role)
        self.book_var.trace_add("write", lambda *_a: self._book_for_role())  # a book opens in its role
        self._build_menus()
        self._build_toolbar()
        self._build_strips()  # the setup banner and the scan band, between the toolbar and the page

        self.canvas = ImageCanvas(self, bg="#202020")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.on_redraw = self._page_drawn  # the reading-order badges and the selection (`selection`)
        # Single-screen use: the viewer may sit behind this window. Keys pressed on the
        # page turn its pages; clicks on the page are passed through to the same spot
        # (reader) or select, move, resize and edit the regions (translator).
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Double-Button-1>", self._on_double)
        self.canvas.bind("<ButtonPress-1>", self._over_page_press, add="+")  # the Translator's page takes the keys
        self.canvas.bind("<Motion>", self._on_motion)
        self._watch_bubbles()  # a translated bubble the pointer rests on, enlarged beside its original (ui.zoom)
        for keysym, key in FORWARDED_KEYS.items():
            self.canvas.bind(f"<{keysym}>", lambda _e, k=key: self.forward_key(k))
        # Enter, Delete, T, Tab, Alt+arrows, Ctrl+Shift+C/V, Ctrl+C/V and the reader's own keys on the page; F1, F5,
        # F11, Ctrl+Z, Ctrl+Y on the window (`shortcuts.ACTIONS`)
        self._bind_shortcuts()
        self.canvas.focus_set()

        self.notes_var = tk.StringVar(value="")  # the notes for the reader on the page, under it when there are any
        self.notes_label = ttk.Label(self, textvariable=self.notes_var, anchor="w", justify="left", wraplength=900,
                                     padding=(8, 2))
        self.notes_label.bind("<Configure>", lambda e: self._wrap(self.notes_label, e.width - 16))
        bar = ttk.Frame(self, padding=(8, 3))
        bar.pack(fill="x")
        self.status_bar = bar
        self.status_var = tk.StringVar(value=_("Starting..."))
        self.guard_var = tk.StringVar(value="")  # a warning, once the offline guard has blocked something
        self.guard_label = ttk.Label(bar, textvariable=self.guard_var, anchor="e", justify="right", foreground="#b3261e")
        self.guard_label.pack(side="right")
        self.progress_holder = ttk.Frame(bar, width=90, height=16)  # keeps the bar's place while it is hidden
        self.progress_holder.pack(side="right", padx=(8, 8))
        self.progress_holder.pack_propagate(False)
        self.progress_bar = ttk.Progressbar(self.progress_holder, mode="indeterminate", length=90)  # while a job runs
        self._bar_shown = False
        self.status_label = ttk.Label(bar, textvariable=self.status_var, anchor="w", justify="left")
        self.status_label.pack(side="left", fill="x", expand=True)
        # shown while the book is full screen on another monitor (`overbook._over_offer`)
        self.move_btn = ttk.Button(bar, text=_(MOVE_BUTTON), command=self.move_to_book)
        tip(_(MOVE_OFFER), self.move_btn)
        bar.bind("<Configure>", lambda _e: self._wrap_status())
        self._sync_guard()
        self._build_page_strip()  # a whole-book run's pages, under the page (`strip`)

    def _build_menus(self) -> None:
        """The menu bar: what is used seldom, one place each; what is used all the time is on the toolbar, and
        translator mode's tools are on its strip, each in that one place alone. Page has Set area... and Page keys...
        (Clear area is in the Set area dialog), then translator mode's Ignore this area on all pages of this book
        (`book_areas`), Copy format, Paste format (also on every region of a kind), Copy region and Paste region
        (`formats`), then Set kind..., Set text size... and Place in reading order... for the selected regions
        (`selection`), Tools has Saved translations..., Names rendered in more than one way... and Settings..., View
        has Show original, Always on top, Over the full-screen viewer and Reading-order numbers, and Help, last, has how
        to use TASlation, the help's Keys topic (Keys...), the legal notice and About TASlation. An entry that is an
        action of `shortcuts.ACTIONS` shows its key as the keymap has it (`keyed`, `_show_keys`)."""
        menubar = tk.Menu(self)
        # the entries whose keys the menus name (`_show_keys`): (menu, index, `shortcuts.ACTIONS` name), each taken
        # right after its entry is added, so an entry added elsewhere in a menu moves nothing
        self._menu_keys: list[tuple[tk.Menu, int, str]] = []
        keymap = getattr(self, "keymap", None) or shortcuts.current()

        def keyed(menu: tk.Menu, name: str) -> None:
            self._menu_keys.append((menu, int(menu.index("end")), name))
            menu.entryconfigure("end", accelerator=keymap.shown(name))

        page = tk.Menu(menubar, tearoff=0)
        page.add_command(label=_("Set area..."), command=self.set_area)
        keyed(page, "set_area")
        page.add_command(label=_("Page keys..."), command=self.open_page_keys)
        keyed(page, "page_keys")
        page.add_separator()  # translator mode: an area ignored on all pages (`book_areas`), the formatting and the
        # region copied and pasted (`formats`)
        page.add_command(label=_(IGNORE_EVERYWHERE), command=lambda: self.ignore_area_everywhere())
        keyed(page, "ignore_area")
        page.add_command(label=_("Copy format"), command=lambda: self.copy_format())
        keyed(page, "copy_format")
        page.add_command(label=_("Paste format"), command=lambda: self.paste_format())
        keyed(page, "paste_format")
        page.add_command(label=_("Paste format on every region of this kind..."),
                         command=lambda: self.paste_format_on_kind())
        keyed(page, "paste_format_on_kind")
        page.add_command(label=_("Copy region"), command=lambda: self.copy_region())
        keyed(page, "copy_region")
        page.add_command(label=_("Paste region"), command=lambda: self.paste_region())
        keyed(page, "paste_region")
        page.add_separator()  # translator mode: the selected regions, one or several (`selection`)
        page.add_command(label=_("Set kind..."), command=lambda: self.set_kind_of_selection())
        keyed(page, "set_kind")
        page.add_command(label=_("Set text size..."), command=lambda: self.set_size_of_selection())
        keyed(page, "set_text_size")
        page.add_command(label=_("Place in reading order..."), command=lambda: self.place_in_order())
        keyed(page, "place_in_order")
        menubar.add_cascade(label=_("Page"), menu=page)
        tools = tk.Menu(menubar, tearoff=0)
        tools.add_command(label=_("Saved translations..."), command=self.open_caches)
        keyed(tools, "saved_translations")
        tools.add_command(label=_("Names rendered in more than one way..."), command=self.review_names)
        tools.add_command(label=_("Settings..."), command=self.open_settings)
        keyed(tools, "settings")
        menubar.add_cascade(label=_("Tools"), menu=tools)
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_checkbutton(label=_("Show original"), variable=self.original_var, command=self._redisplay)
        keyed(view_menu, "show_original")
        view_menu.add_checkbutton(label=_("Always on top"), variable=self.top_var, command=self._apply_on_top)
        keyed(view_menu, "always_on_top")
        view_menu.add_checkbutton(label=_("Over the full-screen viewer"), variable=self.over_var,
                                  command=self.toggle_over)
        keyed(view_menu, "over_viewer")
        view_menu.add_checkbutton(label=_("Reading-order numbers"), variable=self.order_numbers_var,
                                  command=lambda: self.toggle_order_numbers())
        keyed(view_menu, "order_numbers")
        menubar.add_cascade(label=_("View"), menu=view_menu)
        lang_menu = tk.Menu(menubar, tearoff=0)
        for code, name in UI_LANGUAGES.items():
            lang_menu.add_radiobutton(label=name, value=code, variable=self.ui_lang_var, command=self._on_ui_language)
        menubar.add_cascade(label=_("Language"), menu=lang_menu)
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label=_("How to use..."), command=self.open_help)
        keyed(help_menu, "how_to_use")
        help_menu.add_command(label=_("Keys..."), command=self.open_keys)
        keyed(help_menu, "keys_help")
        help_menu.add_command(label=_("Legal notice..."), command=self.open_notice)
        help_menu.add_separator()
        help_menu.add_command(label=_("About TASlation"), command=self.open_about)
        menubar.add_cascade(label=_("Help"), menu=help_menu)
        tip_menu(self, page, _("Mark the part of the viewer's window that shows the page."),
                 _("The keys that turn pages in your viewer."), _(IGNORE_TIP), *(_(t) for t in PAGE_FORMAT_TIPS),
                 *(_(t) for t in PAGE_SELECTION_TIPS))
        tip_menu(self, tools, _("See and delete the translations and notes kept on this computer."),
                 _("Names rendered in more than one way"),
                 _("Change the lettering, the window and the optional page models."))
        tip_menu(self, view_menu, _("Show the page as it is in the viewer, without the translation."),
                 _("Keep this window above the others."),
                 _("Over a viewer in full screen, stay on top without taking its keys: you turn the pages there."),
                 _(ORDER_NUMBERS_TIP))
        tip_menu(self, help_menu, _("How to use TASlation, topic by topic."), _("Every key TASlation knows, in one list."),
                 _("Read the legal notice again."), _("The version, the licence and where your data is kept."))
        self.menubar = menubar
        self.config(menu=menubar)

    def _build_toolbar(self) -> None:
        """The toolbar: groups of controls that flow into as many rows as the window's width needs (`FlowBar`), the
        viewer first, then the target language, Translate / Auto / Reading mode, the role, the book and the batch; under
        it, while the Translator role is chosen, translator mode's strip with its tools and a line on what the pointer
        does (`_build_translator_tools`). Every command has one place: what is used seldom is in the menus only. Every
        control says what it does in a tooltip."""
        top = ttk.Frame(self)  # the toolbar and translator mode's strip, hidden together in reading mode
        top.pack(fill="x")
        bar = FlowBar(top, gap=TOOLBAR_GAP)
        bar.pack(fill="x")
        viewer = bar.group()
        label = ttk.Label(viewer, text=_("Viewer:"))
        label.pack(side="left")
        zero = max(1, tkfont.nametofont("TkTextFont").measure("0"))
        ttk.Style(self).configure("Viewer.TCombobox", postoffset=(0, 0, (VIEWER_LIST_CHARS - VIEWER_CHARS) * zero, 0))
        self.window_box = ttk.Combobox(viewer, textvariable=self.window_var, state="readonly", width=VIEWER_CHARS,
                                       style="Viewer.TCombobox", postcommand=self._rescan_windows)
        self.window_box.pack(side="left", padx=(4, 0))
        self.window_box.bind("<<ComboboxSelected>>", lambda _e: self._on_window_selected(picked=True))
        tip(_("The window that shows your book. TASlation reads the page from it."), label, self.window_box)

        target = bar.group()
        label = ttk.Label(target, text=_("To:"))
        label.pack(side="left")
        langs = list(LANGUAGES)
        if self.settings.target_language not in langs:
            langs.insert(0, self.settings.target_language)
        names = [shown_target(language) for language in langs]  # in the window's language; `lang_var` stays the English name
        self.lang_shown = tk.StringVar(self, value=shown_target(self.lang_var.get()))
        self.lang_shown.trace_add("write", lambda *_a: self._target_typed())
        self.lang_var.trace_add("write", lambda *_a: self._target_set())
        self.lang_var.trace_add("write", lambda *_a: self._follow_target())  # the translator follows the language
        self.lang_box = ttk.Combobox(target, textvariable=self.lang_shown, values=names)
        fit_combobox(self.lang_box, names, max_chars=30)
        self.lang_box.pack(side="left", padx=(4, 0))
        tip(_("The language the book is translated into."), label, self.lang_box)
        for sequence in ("<<ComboboxSelected>>", "<FocusOut>", "<Return>", "<KP_Enter>"):
            self.lang_box.bind(sequence, lambda _e: self._target_picked(), add="+")

        page = bar.group()
        self.translate_btn = ttk.Button(page, text=_("Translate (F5)"), command=self.translate_now)
        self.translate_btn.pack(side="left")
        tip(_("Translate the page in the viewer now."), self.translate_btn, disabled=_("TASlation is at work on a page. Try again when it is done."))
        check = ttk.Checkbutton(page, text=_("Auto"), variable=self.auto_var)
        check.pack(side="left", padx=(8, 0))
        tip(_("Translate each new page as you turn it in the viewer."), check)
        button = self.reading_btn = ttk.Button(page, text=_("Reading mode") + " (F11)", command=self.enter_reading)
        button.pack(side="left", padx=(8, 0))
        tip(_("Show the page alone on the full screen. F11 or Esc leaves it."), button)

        role = bar.group()  # the Translator role's strip, once chosen, says what to do
        radio = ttk.Radiobutton(role, text=_("Reader"), value="reader", variable=self.role_var,
                                command=self._on_role_changed)
        radio.pack(side="left")
        tip(_("You read: keys and clicks on the page go to the viewer."), radio)
        radio = ttk.Radiobutton(role, text=_("Translator"), value="translator", variable=self.role_var,
                                command=self._on_role_changed)
        radio.pack(side="left", padx=(6, 0))
        tip(_("You correct: select, move, edit and add the text areas on the page."), radio)

        book = bar.group()
        label = ttk.Label(book, text=_("Book:"))
        label.pack(side="left")
        book_entry = ttk.Entry(book, textvariable=self.book_var, width=BOOK_CHARS)
        book_entry.pack(side="left", padx=(4, 0))
        for sequence in ("<KeyPress>", "<KeyRelease>"):
            book_entry.bind(sequence, lambda e: self._book_key(e))
        for sequence in ("<FocusOut>", "<Return>", "<KP_Enter>"):  # a name typed: what it says of the title
            book_entry.bind(sequence, lambda _e: self._book_typed(), add="+")
        tip(_("The book's name. Its translations are kept under this name."), label, book_entry)

        batch = bar.group()
        self.batch_btn = ttk.Button(batch, text=_("Read whole book..."), command=self.open_batch_dialog)
        self.batch_btn.pack(side="left")
        tip(_("Read the pages you turn, then translate the whole book."), self.batch_btn, disabled=_("TASlation is at work on a page. Try again when it is done."))
        self.stop_btn = ttk.Button(batch, text=_("Stop (Esc)"), command=self.stop_batch, state="disabled")
        self.stop_btn.pack(side="left", padx=(4, 0))
        tip(_("Stop the whole-book run, or the page being translated."), self.stop_btn, disabled=_("Nothing is running to stop."))
        self.toolbar = bar
        self._build_translator_tools(top)
        self._bars = (top,)  # hidden in reading mode
        self._sync_tools()

    _wrap = staticmethod(wrap_label)  # a label wraps at a width (`layout.wrap_label`)

    def open_book_settings(self) -> None:
        """Book settings... on translator mode's strip: the detection settings kept with this book's premises. A Book box that names
        no book gets its name first (`_ask_name`: nothing is kept under such a name); the settings are those of the
        book whose page was translated last under that name."""
        if self._name_needed():
            self._ask_name(lambda _name: self.open_book_settings(), getattr(self, "_live", None))
            return
        annotations = getattr(self.pipeline, "annotations", None)
        if annotations is None or annotations.book != self.book_var.get().strip():
            boxes.tell(self, _("Translate a page first (the book needs a name)."), icon="info")
            return
        BookSettingsDialog(self, self.pipeline, on_change=self._after_book_settings)

    def _after_book_settings(self) -> None:
        self._warm_page_models()  # the book may use other page models now
        if self.last_result is not None and not self.busy:
            self._start_translate(self.last_result.original, complete=True)

    def open_glossary(self) -> None:
        """Series sheet... on translator mode's strip: the sheet of the book's series. A Book box that names no book gets its name first
        (`_ask_name`): no series sheet is ever kept under such a name."""
        if self._name_needed():
            self._ask_name(lambda _name: self.open_glossary(), getattr(self, "_live", None))
            return
        book = self.book_var.get().strip()
        language = self.lang_var.get().strip() or "English"
        GlossaryDialog(self, self.glossary_store, series_key(book), language,
                       on_change=lambda: self._premises_changed(book, language), fonts_dir=self.settings.fonts_dir,
                       on_renamed=lambda pairs, sheet: self._offer_sheet_renames(pairs, book, language, sheet),
                       font_memory=FontMemory(self.settings.state_dir))

    def _premises_changed(self, book: str, language: str) -> None:
        self._jobs.put(lambda: self._job_refresh_premises(book, language))

    def open_caches(self) -> None:
        CachesDialog(self, self.store,
                     on_changed=lambda book: self._jobs.put(lambda: self._job_forget_cache(book)), on_status=self.status,
                     in_use=lambda book: in_a_run(self) and book == self._batch_for[0])

    def open_settings(self) -> None:
        """Tools > Settings...: the settings a reader changes most (`dialogs.settings`), or the dialog already open
        brought to the front."""
        dialog = getattr(self, "_settings_dialog", None)
        if dialog is not None and dialog.winfo_exists():
            dialog.lift()
            return
        self._settings_dialog = SettingsDialog(self, self.settings, on_saved=self._settings_saved,
                                               keymap=self.keymap, on_keys=self._shortcuts_saved,
                                               pipeline=lambda: getattr(self, "pipeline", None))

    # ------------------------------------------------------------------ the window's keys (`shortcuts`)
    def _shortcut_handlers(self) -> dict[str, Callable[[tk.Event], Any]]:
        """What each action of `shortcuts.ACTIONS` does on its key (translator mode's tools nothing in the Reader
        role, as their buttons are not there)."""

        def flip(var: tk.Variable, then: Callable[[], Any]) -> Callable[[tk.Event], None]:
            def flipped(_event: tk.Event) -> None:  # as the View menu's tick does
                var.set(not var.get())
                then()
            return flipped

        def plain(step: Callable[[], Any]) -> Callable[[tk.Event], None]:
            return lambda _event: step()

        handlers: dict[str, Callable[[tk.Event], Any]] = {
            "translate_now": plain(self.translate_now), "reading_mode": plain(self.toggle_reading),
            "undo": lambda e: self._edit_key(e, self.undo_edit), "redo": lambda e: self._edit_key(e, self.redo_edit),
            "show_original": flip(self.original_var, self._redisplay),
            "always_on_top": flip(self.top_var, self._apply_on_top), "over_viewer": flip(self.over_var, self.toggle_over),
            "read_whole_book": plain(self.open_batch_dialog), "set_area": plain(self.set_area),
            "page_keys": plain(self.open_page_keys), "saved_translations": plain(self.open_caches),
            "settings": plain(self.open_settings), "how_to_use": plain(self.open_help),
            "keys_help": plain(self.open_keys),
            "order_numbers": flip(self.order_numbers_var, self.toggle_order_numbers),
            "edit_box": plain(self._edit_chosen), "remove_box": plain(self._drop_chosen),
            "text_direction": plain(self._turn_direction)}
        for direction in NUDGES:  # outside translator mode Alt+arrows go on to the viewer as the arrows (`_nudge_key`)
            handlers[f"nudge_{direction.lower()}"] = lambda e, d=direction: self._nudge_key(e, d)
        tools = {"reading_order": self.toggle_order, "skip_page": self.toggle_skip,
                 "translate_again": self.retranslate_page, "book_settings": self.open_book_settings,
                 "series_sheet": self.open_glossary, "review": self.open_review,
                 "find_replace": self.open_find_replace,
                 # Tab and Shift+Tab: "break" holds the keys on the page; in the Reader role Tab moves the focus
                 "next_region": lambda: self._tab_region(1), "previous_region": lambda: self._tab_region(-1),
                 "copy_format": self.copy_format, "paste_format": self.paste_format,
                 "copy_region": self.copy_region, "paste_region": self.paste_region,
                 "ignore_area": self.ignore_area_everywhere, "paste_format_on_kind": self.paste_format_on_kind,
                 "set_kind": self.set_kind_of_selection, "set_text_size": self.set_size_of_selection,
                 "place_in_order": self.place_in_order}
        for name, step in tools.items():
            handlers[name] = lambda _e, step=step: step() if self.role_var.get() == "translator" else None
        return handlers

    def _bind_shortcuts(self) -> None:
        """The window's keys as the reader has them (`self.keymap`): the window's on the window, the page's on the
        page, what was bound before let go first (`shortcuts.bind_keys`); then the menus and buttons name them."""
        self._bound_keys = shortcuts.bind_keys({"window": self, "page": self.canvas}, self.keymap,
                                               self._shortcut_handlers(), getattr(self, "_bound_keys", ()))
        self._show_keys()

    def _show_keys(self) -> None:
        """The keys of the menus' entries, of the toolbar's buttons and of translator mode's strip (its buttons and
        its hint: `TranslatorMixin._show_tool_keys`) as the keymap has them (the defaults' words as they always
        were)."""
        keymap = self.keymap
        for menu, index, name in getattr(self, "_menu_keys", ()):
            try:
                menu.entryconfigure(index, accelerator=keymap.shown(name))
            except tk.TclError:
                pass
        if getattr(self, "hint_label", None) is not None:
            self._show_tool_keys(keymap)
        shown = keymap.shown("translate_now")
        if getattr(self, "translate_btn", None) is not None:
            text = (_("Translate (F5)") if shown == "F5" else
                    _("Translate") + (f" ({shown})" if shown else ""))
            self.translate_btn.configure(text=text)
        if getattr(self, "reading_btn", None) is not None:
            shown = keymap.shown("reading_mode")
            self.reading_btn.configure(text=_("Reading mode") + (f" ({shown})" if shown else ""))

    def _shortcuts_saved(self, keymap: shortcuts.Keymap) -> None:
        """The Settings dialog saved the window's keys: bound at once, and Help's Keys say them."""
        self.keymap = keymap
        shortcuts.set_current(keymap)
        self._bind_shortcuts()
        if self._help is not None and self._help.winfo_exists():
            self._help.render(self._help.wrapped_at, again=True)

    def _settings_saved(self, changed: dict[str, Any]) -> None:
        """The Settings dialog saved *changed*: set on the settings the window and its pipeline share, and shown at
        once - the window on top, the text size, then (on the worker, before the page is translated again) the page
        models made for the new choice and the pages of this session lettered anew."""
        for key, value in changed.items():
            setattr(self.settings, key, value)
        if "always_on_top" in changed:
            self.top_var.set(bool(changed["always_on_top"]))
            self._apply_on_top()
        if "ui_scale" in changed:
            self._dpi_watch.rescale()
        if set(changed) & PAGE_SETTINGS:
            self._jobs.put(self._job_settings_changed)
            if self.last_result is not None and not self.busy and self.batch is None:
                self._start_translate(self.last_result.original, complete=True)

    def _job_settings_changed(self) -> None:
        """(worker) The settings of the page changed: the detectors and page models made for them (nothing is loaded
        here; the warm-up loads what is used), and this session's lettered pages forgotten."""
        pipeline = self.pipeline
        if pipeline is None:
            return
        pipeline._build_detectors()
        pipeline.shown_pages.clear()
        self._warm_page_models()

    def _warn_ignored(self) -> None:
        """Once the window is up: the settings file's keys this version does not know, named once (`warn_ignored`),
        when no dialog holds the window."""
        if modal_up(self) or self.reading:
            self.after(FIRST_STEPS_RETRY_MS, self._warn_ignored)
            return
        warn_ignored(self, self.settings, boxes.tell)

    def open_about(self) -> None:
        """Help > About TASlation: the version, the licence, that it runs offline with the offline guard's state, and
        where its data is kept, modal and centred over the window."""
        from .dialogs.about import AboutDialog

        AboutDialog(self, Path(self.settings.state_dir), self.settings.ollama_port, guard=self._guard_line())

    def _close_allowed(self) -> bool:
        """At closing: with pages read and not translated yet (a run reading them, or what a stopped run left) or
        pages of the run not finished, whether to close all the same (`strip.close_warning` says what is lost; what is
        translated is saved). Asked only then, in TASlation's own box (`WarningBox`): a system box takes the words
        of its buttons from Windows' language, not the window's. Over the full-screen viewer the box is in sight above
        it, and when the reader keeps TASlation open the viewer gets the foreground back as the box closes
        (`overbook`)."""
        text = close_warning(self)
        if text is not None:
            box = WarningBox(self, "TASlation", text, go=_("Close anyway"), stay=_("Keep TASlation open"),
                             stay_first=True)
            if box.winfo_exists():
                self.wait_window(box)
            if not box.answer:
                return False
        release_run_images(self)  # (the window closes: the pictures go now)
        return True

    def _on_close(self) -> None:
        if not self._close_allowed():  # pages of a run not finished: their pictures would be lost
            return
        if self.batch is not None:
            self.batch.stop()
        self._release_model()
        self._target_chosen()
        self._restore_enlarged()
        self._lower_viewer()
        self._over_close()
        devices.save_times(getattr(self, "pipeline", None), self.settings.state_dir)  # (Settings > System, doctor)
        try:
            last_save(getattr(self, "pipeline", None), self)
        finally:
            self.destroy()


def last_save(pipeline: Any, window: tk.Misc | None = None) -> None:
    """The window closes: what an earlier save left in memory gets one more try; when that fails too, the reader is
    told (in TASlation's own box over *window*, the window that closes), for it goes with the window."""
    cache = getattr(pipeline, "cache", None)
    if cache is None or not cache.dirty:
        return
    try:
        cache.save()
    except OSError as e:
        text = _("Some translations could not be saved ({error}) and are lost when this window closes.").format(
            error=e.strerror or type(e).__name__)
        if window is not None:
            boxes.tell(window, text)


def run_app(settings: Settings, window_query: str | None = None, book: str | None = None, auto: bool = True,
            on_top: bool = False, reading: bool = False) -> int:
    app = App(settings, window_query=window_query, book=book, auto=auto, on_top=on_top, reading=reading)
    if app.quit_before_start:  # the reader chose Quit at the legal notice
        app.destroy()
        return 0
    # the display and the PC stay on while the window is open: left alone for hours it must go on reading, and a viewer
    # stops repainting once the display is off (this thread's request: the batch's own worker asks separately)
    keep_awake(display=True)
    try:
        app.mainloop()
    finally:
        release_awake()
        # the window has gone (its close released the model): the Ollama it started stops now, unless another
        # TASlation or another program still uses it (`ollama_start.finish_all`: a few seconds at most; the log says
        # how it went)
        finish_all()
    return 0


__all__ = [
    "App", "Profiles", "run_app", "APP_ID", "ASSETS", "DEFAULT_SIZE", "ICON_ICO", "ICON_PNG", "MIN_SIZE", "FlowBar",
    "apply_icon", "fit_columns", "fit_combobox", "give_icons", "initial_geometry", "place_window", "set_app_id",
    "wrap_label", "is_cjk", "wrap_line", "wrap_text", "FILL_COLOUR", "LOADING", "STATUS_WORDS",
    "WORK_STAGES", "Filling", "busy_line", "progress_line", "reads_page", "stage_of", "status_word",
    "BLANK_SPREAD", "FORWARDED_KEYS", "LANGUAGES", "LIVE_CHANGE", "NO_VIEWER", "QUEUE_RANK", "READING_MODE",
    "READING_NOTE_MS", "READING_ONLY", "READY", "WINDOW_ALPHA", "WINDOW_WATCH_MS", "NOT_VIEWERS",
    "choose_viewer", "looks_like_viewer", "AreaDialog", "BatchDialog", "BookSettingsDialog", "CachesDialog",
    "EditBubbleDialog", "GlossaryDialog", "NoticeDialog", "PassphraseDialog", "ReviewDialog",
    "import_error_text", "notice_due", "review_rows",
]
