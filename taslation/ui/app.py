"""The program's Tk root, never on the screen: TASlation is the lettering laid over the viewer's own window and the two
side panes beside its page (`seethrough`, `capture.seethrough`), with the Menu of the left pane (`see_menu`) and the
dialogs. The root hosts the dialogs and holds the state the panes and the dialogs share - the viewer chosen, the
target language, Auto, the book's Series and Volume, the page's regions in Edit (`see_edit`) - in widgets of its own
that are laid out but never seen (the toolbar's boxes, the page's canvas, the status line). All heavy work runs in one
worker thread; Tk only draws. Page images live in memory only; nothing is written to disk except the text-only
translation cache and the per-window capture margins.

The program is put together here (`App`, `run_app`); its parts are the modules beside this one: the mixins `App`
is made of (`status`, `live`, `jobs`, `translator`, `viewers`), the dialogs (`dialogs/`), and what they
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

from .. import bookname, jurisdictions, notice, protect, viewerparts
from ..annotations import AnnotationStore, GlossaryStore
from ..backlog import backlog_of
from ..threads import keep_awake, release_awake
from ..cache import CacheStore
from ..capture import WindowInfo
from ..config import Settings
from ..i18n import (
    _,
    current,
    load_ui_language,
    load_ui_table,
    save_ui_entry,
    save_ui_language,
    set_language,
)
from ..notes import sheet_key
from ..ollama_start import finish_all
from ..translate.models import wanted_name
from ..pagekeys import Profiles
from ..regions import PageResult
from .constants import (
    APP_TITLE,
    BLANK_SPREAD,
    LANGUAGES,
    LIVE_CHANGE,
    QUEUE_RANK,
    READY,
    WINDOW_TARGETS,
    WINDOW_WATCH_MS,
)
from .copy_details import watch_error_boxes
from .dialogs import caches as boxes
from .dialogs.area import AreaDialog
from .dialogs.caches import CachesDialog, PassphraseDialog, import_error_text
from .dialogs.glossary import GlossaryDialog
from .dialogs.help import HelpWindow, modal_up
from .dialogs.notice import NoticeDialog, notice_due
from .dialogs.review import EditBubbleDialog, ReviewDialog, review_rows
from .dialogs.book_settings import BookSettingsDialog
from .book_areas import AreaMixin
from .book_fields import BookFields, fields_committed, kept_name, refused_line
from .font_memory import FontMemory
from .dialogs.settings import PAGE_SETTINGS, SettingsDialog, warn_ignored
from .gpu_release import apply_num_gpu
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
from .scaling import DpiWatch, apply_scale
from . import area, ime, seethrough, shortcuts, theme, updates
from .. import devices
from . import side
from .side import SideMixin
from .status import StatusMixin
from .tooltip import tip
from .replace import ReplaceMixin
from .formats import FormatMixin
from .selection import SelectionMixin
from .translator import TOOLBAR_GAP, TranslatorMixin
from .viewers import ViewerMixin, named_window
from .wrap import is_cjk, wrap_line, wrap_text


LATER_MS = 800  # the settings file's unknown keys are named this long after the start, once nothing modal is up ...
LATER_RETRY_MS = 1000  # ... looked for again this often
TARGET_TABLE, TARGET_ENTRY = "translation", "language"  # where ui.json keeps the "To:" box
VIEWER_CHARS, BOOK_CHARS = 18, 10  # the toolbar's boxes, in "0" widths
VOLUME_CHARS = 3  # (the book's Series box, and its Volume box beside it: "999"; "10.5" scrolls)
VIEWER_LIST_CHARS = 40  # ... and the Viewer list wider than its box as it opens (the style's postoffset), for whole titles


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


class App(StatusMixin, LiveViewMixin, JobsMixin, TranslatorMixin, ReplaceMixin, FormatMixin, SelectionMixin,
          ViewerMixin, SideMixin, ModelSwitchMixin, AreaMixin, seethrough.HiddenWindowMixin, tk.Tk):
    """The program's Tk root. Its state is made here (`__init__`), and its widgets (`_build_ui`, again after a
    language switch); the small dialogs open from here. What it does comes from the mixins: the status line and the
    busy state (`status`), the capture, the live frame and Auto (`live`), the worker, its events and the requests
    (`jobs`), the Translator role's regions, which Edit works on (`translator`; several regions selected and the
    reading-order numbers: `selection`), the viewer list, the area and the offline guard (`viewers`), the screens
    behind for the right pane (`side`), the root never on the screen (`seethrough.HiddenWindowMixin`)."""

    def __init__(self, settings: Settings, window_query: str | None = None, book: str | None = None, auto: bool = True):
        set_app_id()
        super().__init__()
        seethrough.quiet_start(self)  # never on the screen, nor taking the foreground
        self._apply_alpha()  # before the window is first shown: an alpha set later makes a browser behind it flicker
        apply_icon(self)
        give_icons(self)  # the taskbar takes the big one
        self.title(APP_TITLE)
        try:  # the monitor's DPI times the reader's UI scale, before anything is measured (`scaling`)
            apply_scale(self, settings.ui_scale)
        except tk.TclError:
            pass
        # the window's colours, before any widget is made (the legal notice's too): Windows' own look as it always
        # was, or dark as the setting or Windows' app mode has it; Windows' high contrast first (`theme`)
        theme.apply(self, getattr(settings, "theme", "system"))
        ime.install(self)  # every box shows the text an IME is composing in it, the notice's too (`ime`)
        self.minsize(*(min(m, s) for m, s in zip(MIN_SIZE, (self.winfo_screenwidth() - 40, self.winfo_screenheight() - 90))))
        state_dir = Path(settings.state_dir)
        # the root's size (its widgets are laid out at it; its place is off every monitor: `HiddenWindowMixin`)
        self._normal_geometry = initial_geometry(self)
        self.geometry(self._normal_geometry)
        self.quit_before_start = False
        first_start = load_ui_language(state_dir) is None
        code = settings.ui_language or load_ui_language(state_dir)
        if notice_due(state_dir):  # the legal notice, where the first start also chooses the country and language
            seethrough.quiet_end(self)  # (the notice is the reader's to answer: it takes the foreground as ever)
            self.withdraw()
            dialog = NoticeDialog(self, state_dir, code)  # (it gives itself its icons and its place on the screen)
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
        bookname.use(settings.state_dir)  # the books whose Series and Volume the reader split unlike the parser
        settings.target_language = first_target(state_dir, settings.target_language, code, first_start)
        self._target_kept = settings.target_language  # what ui.json holds of the "To:" box, or will
        self.store = CacheStore(settings.cache_dir)
        self.profiles = Profiles(Path(settings.state_dir) / "profiles.json")
        self.pipeline: Any = None
        self.translator: Any = None
        self.ready = False
        self.busy = False
        updates.setup(self)  # a newer version an earlier look found, for the Help menu (no request)
        self.windows: list[WindowInfo] = []
        self.selected: WindowInfo | None = None
        self.window_query = (window_query or "").strip()
        # the start's judgement of the GPU's memory made (`JobsMixin._job_init`): the viewer chooser may come from then
        # on (`see_menu.chooser_tick`), after the legal notice and the GPU's dialog, alone
        self._start_judged = False
        self._see_viewer_note: tuple[str, float] | None = None  # (the viewer's title, until when the right pane says it)
        self._waiting = False  # the viewer window shows another tab; Auto mode is holding back
        self.annotation_store = AnnotationStore(settings.annotations_dir)
        self.glossary_store = GlossaryStore(settings.glossary_dir)
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

        self._area_hinted = False
        self._status_render: Callable[[], str] | None = None  # the status line in the window's language, again
        self._status_key: str | None = None  # ... and its key, when it was said with `say`
        self._status_page: Image.Image | None = None  # ... and the frame of the page it speaks of (`_page_status`)
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
        self._thumbs: list[tuple[Any, Image.Image, np.ndarray]] = []  # capture-area thumbnails of recent frames
        self._lettered_memo: tuple[Image.Image, Image.Image, Image.Image] | None = None  # (page, frame, both)
        self._mask_memo: tuple[Image.Image, np.ndarray, np.ndarray] | None = None  # (page, where its lettering is, its pixels)
        self._queued: tuple[str, tuple[Any, ...]] | None = None  # a request waiting for the models or for a job
        self._help: HelpWindow | None = None  # Menu > Help > How to use..., while it is open
        # the setup checks and their banner, a book's start, the scan band, a page translation that can be cancelled
        self._init_flow_state()
        if not seethrough.start(self):  # the lettering over the viewer's own window: where it cannot be, nothing runs
            return
        self._init_selection()  # several regions selected, the reading-order numbers (`selection`)
        self.keymap = shortcuts.Keymap.load(state_dir)  # the dialogs' keys (`shortcuts`)
        shortcuts.set_current(self.keymap)
        self._build_ui()
        self.say("Starting...")  # said again in the window's language after a switch
        self.geometry(self._normal_geometry)  # (with every widget in place: off every monitor, as ever)
        if self.state() == "withdrawn":
            self.deiconify()
        # moved to a monitor of another scale: the dialogs' text follows (`scaling`)
        self._dpi_watch = DpiWatch(self, lambda: self.settings.ui_scale)
        watch_error_boxes(self)  # an error box gets Copy details (the version, the system, the last error)
        if book:
            self.book_var.set(book)
        self.auto_var.set(auto)
        self._apply_alpha()
        self.refresh_windows(select=window_query)
        self._redisplay()
        seethrough.quiet_started(self)
        self.after(WINDOW_WATCH_MS, self._watch_windows)
        threading.Thread(target=self._worker_loop, daemon=True).start()
        self._jobs.put(self._job_init)
        self.after(80, self._poll_events)
        self.after(settings.auto_interval_ms, self._auto_tick)
        if settings.ignored_keys:
            self.after(LATER_MS, self._warn_ignored)
        self.bind("<Activate>", self._colours_again, add="+")  # Windows' app mode or high contrast changed meanwhile
        self.history = EditHistory()
        self._editor: Any = None  # the open region editor, which the model's answers go to
        self._review: Any = None  # the open review list
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ the toolbar's boxes
    def _book_key(self, event: tk.Event) -> None:
        """A key in the Book box: as it goes down the box is noted, as it comes up a box that changed is a name of the
        reader's (Tab, the arrows and the like change nothing)."""
        if event.type == tk.EventType.KeyPress:
            self._book_before = self.book_var.get()
        elif self.book_var.get() != self._book_before:
            self._book_edited = True

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
        if self.auto_var.get() and self.last_result is not None:
            self.translate_now()

    # ------------------------------------------------------------------ UI
    def _open_forms(self) -> list[tk.Toplevel]:
        """The dialogs open with fields a language switch would lose (they go with the widgets; the ones that come
        back by themselves are not among them, and those that hold the window never see a switch)."""
        forms = (GlossaryDialog, BookSettingsDialog)
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
        """Menu > Help > Legal notice...: the legal notice again, modal over the window; a language chosen there relabels the
        window as the Language menu does (the dialog has saved it, and the country)."""
        before = self.ui_lang_var.get()
        dialog = NoticeDialog(self, Path(self.settings.state_dir), before, startup=False)
        self.wait_window(dialog)
        if dialog.accepted and dialog.language != before:
            self.ui_lang_var.set(dialog.language)
            self._rebuild_ui()

    def open_help(self) -> None:
        """The Menu's Help > How to use...: the help window, or the one already open brought to the front."""
        window = getattr(self, "_help", None)
        if window is not None and window.winfo_exists():
            window.bring_up()
        else:
            self._help = HelpWindow(self)

    def _rebuild_ui(self) -> None:
        """Build the widgets again in the current language, keeping every setting, the page, the status line (said
        again in the new language), and the help and find and replace when they were open."""
        keep = {name: getattr(self, name).get() for name in ("book_var", "model_var", "lang_var", "auto_var",
                                                              "original_var", "role_var")}
        render, line, key = self._status_render, self.status_var.get(), self._status_key
        ordering = self._ordering
        viewer, edited = self.selected, self._book_edited
        if self._start_dialog is not None:  # it goes with the widgets: the book's next page asks again
            self._start_dialog = self._start_pending = None
        help_window = self._help  # it goes with the widgets too, and comes back below
        help_place = help_window.geometry() if help_window is not None and help_window.winfo_exists() else None
        find_kept = self._find_kept()  # find and replace too, with what it shows
        self._help = None
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
        self._set_busy(self.busy)
        self._sync_stop()
        if self._busy_shown:
            self._show_badge()
        self._show_banner()  # the setup banner and the band in the new language
        self._show_band()
        self._status_render, self._status_key = render, key
        self.status_var.set(render() if render is not None else line)
        self._show_notes()
        self._redisplay()
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
        self.original_var = tk.BooleanVar(value=False)
        # (the Translator role is the left pane's Edit, `see_edit`)
        self.role_var = tk.StringVar(value=self.settings.role)
        self.book_var.trace_add("write", lambda *_a: self._book_for_role())  # a book opens in its role
        self._build_toolbar()
        self._build_strips()  # the setup banner and the band, between the toolbar and the page

        self.canvas = ImageCanvas(self, bg="#202020")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.on_redraw = self._page_drawn  # the reading-order badges and the selection (`selection`)
        # no more of a frame is taken than the capture area in force, which every part of TASlation reads (a browser's title bar and a viewer's bands are in the capture of its client area; a frame
        # of a new size while a page job runs, that size's own: `_margins_of`)
        self.canvas.read_area_of = lambda image: area.margins_to_box(self._margins_of(image), image.size)
        # (the canvas is never seen: what it draws is the page the lettering over the viewer is made of, and its
        # regions are those Edit works on; TASlation takes no key and no click of the reader's but on its own panes,
        # the boxes of Edit and its dialogs)

        self.notes_var = tk.StringVar(value="")  # the notes for the reader on the page, under it when there are any
        self.notes_label = ttk.Label(self, textvariable=self.notes_var, anchor="w", justify="left", wraplength=900,
                                     padding=(8, 2))
        self.notes_label.bind("<Configure>", lambda e: self._wrap(self.notes_label, e.width - 16))
        bar = ttk.Frame(self, padding=(8, 3))
        bar.pack(fill="x")
        self.status_bar = bar
        self.status_var = tk.StringVar(value=_("Starting..."))
        self.guard_var = tk.StringVar(value="")  # a warning, once the offline guard has blocked something
        self.guard_label = ttk.Label(bar, textvariable=self.guard_var, anchor="e", justify="right",
                                     foreground=theme.colour("error"))
        self.guard_label.pack(side="right")
        self.progress_holder = ttk.Frame(bar, width=90, height=16)  # keeps the bar's place while it is hidden
        self.progress_holder.pack(side="right", padx=(8, 8))
        self.progress_holder.pack_propagate(False)
        self.progress_bar = ttk.Progressbar(self.progress_holder, mode="indeterminate", length=90)  # while a job runs
        self._bar_shown = False
        self.status_label = ttk.Label(bar, textvariable=self.status_var, anchor="w", justify="left")
        self.status_label.pack(side="left", fill="x", expand=True)
        bar.bind("<Configure>", lambda _e: self._wrap_status())
        self._sync_guard()
        self._build_side()  # the pages turned past and the Reader's status slot, for the right pane (`side`)

    def _build_toolbar(self) -> None:
        """The toolbar, never seen: the boxes and buttons that hold what the panes and the dialogs share - the viewer
        list, the target language, Translate and Auto, the role, the book's Series and Volume, Stop - and under it the
        Translator role's strip (`_build_translator_tools`). The left pane's controls and Menu act on them
        (`see_menu`)."""
        top = ttk.Frame(self)
        top.pack(fill="x")
        bar = FlowBar(top, gap=TOOLBAR_GAP)
        bar.pack(fill="x")
        viewer = bar.group()
        label = ttk.Label(viewer, text=_("Viewer:"))
        label.pack(side="left")
        zero = max(1, tkfont.nametofont("TkTextFont").measure("0"))
        theme.style(self, "Viewer.TCombobox", postoffset=(0, 0, (VIEWER_LIST_CHARS - VIEWER_CHARS) * zero, 0))
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
        self.translate_btn = ttk.Button(page, text=_("Translate"), command=self.translate_now)
        self.translate_btn.pack(side="left")
        tip(_("Translate the page in the viewer now."), self.translate_btn, disabled=_("TASlation is at work on a page. Try again when it is done."))
        check = ttk.Checkbutton(page, text=_("Auto"), variable=self.auto_var)
        check.pack(side="left", padx=(8, 0))
        tip(_("Translate each new page as you turn it in the viewer."), check)

        role = bar.group()  # the Translator role's strip, once chosen, says what to do
        radio = ttk.Radiobutton(role, text=_("Reader"), value="reader", variable=self.role_var,
                                command=self._on_role_changed)
        radio.pack(side="left")
        tip(_("You read: keys and clicks on the page go to the viewer."), radio)
        radio = ttk.Radiobutton(role, text=_("Translator"), value="translator", variable=self.role_var,
                                command=self._on_role_changed)
        radio.pack(side="left", padx=(6, 0))
        tip(_("You correct: select, move, edit and add the text areas on the page."), radio)

        book = bar.group()  # the book's name as Series and Volume, bound to book_var (`book_fields`)
        fields = BookFields(book, self.book_var, series_chars=BOOK_CHARS, volume_chars=VOLUME_CHARS, short=True,
                            resolve=lambda name: kept_name(self, name),
                            on_commit=lambda _name: fields_committed(self), on_refused=lambda text: self.status(
                                lambda: refused_line(text)))
        fields.pack(side="left")
        for entry in (fields.series, fields.volume):
            for sequence in ("<KeyPress>", "<KeyRelease>"):
                entry.bind(sequence, lambda e: self._book_key(e), add="+")
        tip(_("The book's series: what its volumes share, an edition such as 完全版 included. With the volume it names the book its translations are kept under."), fields.series_label, fields.series)
        tip(_("The volume's number (3, 10.5) or 上, 中, 下, 前編, 後編; empty for a book of one volume. 第3巻, Vol. 3 and ③ are taken as 3."), fields.volume_label, fields.volume)

        stop = bar.group()
        self.stop_btn = ttk.Button(stop, text=_("Stop"), command=self.stop_page, state="disabled")
        self.stop_btn.pack(side="left")
        tip(_("Stop the page being translated."), self.stop_btn, disabled=_("Nothing is running to stop."))
        self.toolbar = bar
        self._build_translator_tools(top)
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
        GlossaryDialog(self, self.glossary_store, sheet_key(self.glossary_store, book), language,
                       on_change=lambda: self._premises_changed(book, language), fonts_dir=self.settings.fonts_dir,
                       on_renamed=lambda pairs, sheet: self._offer_sheet_renames(pairs, book, language, sheet),
                       font_memory=FontMemory(self.settings.state_dir))

    def _premises_changed(self, book: str, language: str) -> None:
        self._jobs.put(lambda: self._job_refresh_premises(book, language))

    def open_caches(self) -> None:
        CachesDialog(self, self.store,
                     on_changed=lambda book: self._jobs.put(lambda: self._job_forget_cache(book)),
                     on_status=self.status)

    def open_settings(self) -> None:
        """The Menu's Settings...: the settings a reader changes most (`dialogs.settings`), or the dialog already open
        brought to the front."""
        dialog = getattr(self, "_settings_dialog", None)
        if dialog is not None and dialog.winfo_exists():
            dialog.lift()
            return
        self._settings_dialog = SettingsDialog(self, self.settings, on_saved=self._settings_saved,
                                               pipeline=lambda: getattr(self, "pipeline", None))

    def _handle_event(self, kind: str, data: dict[str, Any]) -> None:
        """A worker's event (`JobsMixin._handle_event`: normal reading's own go to the right pane's counts,
        `SideMixin._on_reading_<kind>`), and then as the Reader's status slot takes it (`side.before`, `side.after`: a
        page that failed or had nothing to read; they never raise)."""
        noted = side.before(self, kind, data)
        JobsMixin._handle_event(self, kind, data)
        side.after(self, kind, data, noted)

    def _settings_saved(self, changed: dict[str, Any]) -> None:
        """The Settings dialog saved *changed*: set on the settings the window and its pipeline share, and shown at
        once - the dialogs' text size and colours (the side panes take theirs from the viewer: its DPI and the ground
        of its page), then (on the worker, before the page is translated again) the page models made for the new
        choice and the pages of this session lettered anew."""
        for key, value in changed.items():
            setattr(self.settings, key, value)
        if "ui_scale" in changed:
            self._dpi_watch.rescale()
        if "ollama_num_gpu" in changed:  # (the translators send it from their next request on)
            apply_num_gpu(self, changed["ollama_num_gpu"])
        if "theme" in changed:  # the dialogs take the new colours at once
            self._colours_again()
        if "see_through_indicators" in changed:  # (the banner's lines in the right pane or a dialog)
            self._show_banner()
        if set(changed) & PAGE_SETTINGS:
            self._jobs.put(self._job_settings_changed)
            if self.last_result is not None and not self.busy:
                self._start_translate(self.last_result.original, complete=True)

    def _colours_again(self, event: tk.Event | None = None) -> None:
        """The colours the setting stands for now (`theme.apply`: nothing happens while they stay as they are): when
        it is saved, and when the window comes to the front (*event*: Windows' app mode or its high contrast may have
        changed meanwhile). The strips over the page are drawn anew in the new ones."""
        if event is not None and event.widget is not self:
            return
        before = theme.mode()
        if theme.apply(self, str(getattr(self.settings, "theme", "system"))) != before:
            self._show_banner()
            self._show_band()

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
        if modal_up(self):
            self.after(LATER_RETRY_MS, self._warn_ignored)
            return
        warn_ignored(self, self.settings, boxes.tell)

    def open_about(self) -> None:
        """Menu > Help > About TASlation: the version, the licence and where its data is kept, modal (the offline
        guard's state goes with its Copy details: `errorlog.guard_line`)."""
        from .dialogs.about import AboutDialog

        AboutDialog(self, Path(self.settings.state_dir))

    def open_updates(self) -> None:
        """Menu > Help > Check for updates...: asks GitHub for the newest version now, in a process of its own
        (`dialogs.updates.UpdateDialog`); its Update now closes the window for update.cmd (`updates.update_now`)."""
        from .dialogs.updates import UpdateDialog

        UpdateDialog(self, self, on_update=lambda version: updates.update_now(self, version))

    def _on_close(self) -> None:
        """The window closes, with nothing asked: what is translated is saved, and the pages turned past and not
        translated yet are given up with their captures (`close_backlog`). A page started on a frame not confirmed
        yet is given up before anything is saved (`end_page_job`; what it changed goes back,
        `Pipeline.drop_unconfirmed`, after the steps between, which give its worker the time to put it back itself):
        neither the stage times nor the cache written at the close hold anything of it (`Pipeline.to_save`)."""
        updates.stop(self)  # a look for a new version under way ends with the window
        end_page_job(self)
        close_backlog(self)
        self._release_model()
        self._target_chosen()
        self._lower_viewer()
        pipeline = getattr(self, "pipeline", None)
        drop = getattr(pipeline, "drop_unconfirmed", None)
        if drop is not None:
            drop()
        devices.save_times(pipeline, self.settings.state_dir)  # (Settings > System, doctor)
        try:
            last_save(pipeline, self)
        finally:
            self.destroy()


def end_page_job(window: Any) -> None:
    """The window closes (`App._on_close`, before anything is saved): every gate of a page started before its frame
    settled is dropped (`pipeline.PageGate.drop`: the early start's, ``ui.live``'s ``_early``, and the page job's;
    one the window confirmed first stays confirmed, and that page is kept), and the page job's cancel is set: the job
    asks the model nothing more - a request in flight is cancelled - and gives its page up. The window's record of
    the early start goes with it, so that nothing still running on this thread at the close confirms it."""
    early = getattr(window, "_early", None)
    if early is not None:
        window._early = None
    for gate in (getattr(early, "gate", None), getattr(window, "_early_gate", None),
                 getattr(window, "_page_gate", None)):
        if gate is not None:
            gate.drop()
    cancel = getattr(window, "_page_cancel", None)
    if cancel is not None:
        cancel.set()


def close_backlog(window: Any) -> None:
    """The window closes: the pages turned past it holds go, and the backlog's thread is let go (`Backlog.close`);
    pages stored stay stored. Never in the way of the close."""
    try:
        backlog = backlog_of(window, make=False)
        if backlog is not None:
            backlog.close()
    except Exception:  # noqa: BLE001 - the window closes whatever happens here
        pass


def last_save(pipeline: Any, window: tk.Misc | None = None) -> None:
    """The window closes: what an earlier save left in memory gets one more try; when that fails too, the reader is
    told (in TASlation's own box over *window*, the window that closes), for it goes with the window. Never what a
    page job whose frame was not confirmed changed: while one may still change the cache, the cache is written as it
    was before that job (`Pipeline.to_save`) - the pages an earlier save left unsaved are, its page is not."""
    cache = getattr(pipeline, "cache", None)
    to_save = getattr(pipeline, "to_save", None)
    if cache is not None and to_save is not None:
        cache = to_save(cache)
    if cache is None or not cache.dirty:
        return
    try:
        cache.save()
    except OSError as e:
        text = _("Some translations could not be saved ({error}) and are lost when this window closes.").format(
            error=e.strerror or type(e).__name__)
        if window is not None:
            boxes.tell(window, text)


def run_app(settings: Settings, window_query: str | None = None, book: str | None = None, auto: bool = True) -> int:
    app = App(settings, window_query=window_query, book=book, auto=auto)
    if app.quit_before_start:  # the reader chose Quit at the legal notice
        app.destroy()
        return 0
    # the display and the PC stay on while the window is open: left alone for hours it must go on reading, and a viewer
    # stops repainting once the display is off (this thread's request)
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
    "BLANK_SPREAD", "LANGUAGES", "LIVE_CHANGE", "QUEUE_RANK", "READY",
    "WINDOW_WATCH_MS", "named_window", "AreaDialog", "BookSettingsDialog", "CachesDialog",
    "EditBubbleDialog", "GlossaryDialog", "NoticeDialog", "PassphraseDialog", "ReviewDialog",
    "import_error_text", "notice_due", "review_rows",
]
