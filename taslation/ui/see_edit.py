"""Edit on the overlay: see-through mode's editing of the page on show, in place of the Translator role's window (whose
page and regions are a canvas that is never on the screen here).

* The left pane's switch Edit is the Translator role (``role_var``; `toggle`): off at the start unless the book's
  remembered role is the Translator's (`translator.chosen_role`, kept per book as the window kept it) or the start
  asked for it (``gui --role translator``, ``role`` in the settings file); switched by the reader, it is remembered
  for the book (`TranslatorMixin._on_role_changed`).
* While it is on, the page's regions (`_page_regions`, the window's) are handed to the see-through window as marks
  (`marks_for`, `seethrough.Marks`): each box takes the mouse - beside them every click is the viewer's - and carries
  its number in the reading order on a plate of the colour the window outlined it in (translated, not translated, the
  reader's own, flagged); the box under the pointer is outlined instead of giving way to the original (whose words
  the right pane's block shows), the boxes chosen and the one in the editor too. `tick` acts on what the reader did
  there (`act`): a click opens the region editor beside the box (`open_editor`, `editor_place`: alone, on the
  viewer's monitor, taking the keys; the foreground back to the viewer once it closes), Shift+click chooses several
  (`SelectionMixin._toggle_chosen`), a drag moves the box (those chosen with it: `_move_regions`), a drag on a corner
  resizes it (`_move_region`); while the reading order is clicked, a click numbers the region; with Add a text area
  chosen in the Menu, the next drag draws a region (`_add_region`). A region in the editor keeps its patches whatever
  the frame says; the editor's Show original, held, shows the original under it (`set_bare`).
* The Menu has the rest while Edit is on (`build_menu`): Undo and Redo, the page's tools (Reading order, Add a text
  area, Skip page; what the window's Page menu does to the regions chosen), and the lists and sheets (Review..., My
  corrections..., Lines to review..., Find and replace..., Series sheet..., Book settings...), each a dialog alone.
  No key is TASlation's: every key goes to the viewer, but inside TASlation's own dialogs."""

from __future__ import annotations

from typing import Any, Callable

from .. import panes as pn
from .. import seethrough as st
from ..i18n import _
from . import seethrough

EDIT = "Edit"
EDIT_ON = ("Edit: click a bubble to edit it, drag it to move it, drag a corner to resize it; Shift+click chooses "
           "several. Beside the bubbles, clicks go to the viewer.")
EDIT_OFF = "Edit is off: every click goes to the viewer."
ORDERING = "Reading order: click the bubbles in the order they are read, then choose Finish order in the Menu."
ADD_ENTRY = "Add a text area"
ADDING = "Drag a rectangle over the text to add it; a click without a drag gives it up."
ADD_GIVEN_UP = "No text area was added."
CANCEL_ORDER = "Cancel the reading order"
DROP_CHOSEN = "Drop the chosen regions"
# the plates' colours (RGB), as the window outlined the regions (`LiveViewMixin._overlay_items`)
TRANSLATED, NOT_TRANSLATED, OWN, FLAGGED = (61, 220, 132), (255, 179, 71), (77, 163, 255), (255, 94, 94)
EDITOR_GAP = 12  # px (at 96 DPI) between a region's box and the editor beside it
PLATES_KEPT = 256


def on(app: Any) -> bool:
    """Whether Edit is on: see-through mode with TASlation's own window hidden, in the Translator role."""
    return seethrough.hidden(app) and seethrough.on(app) and _role(app) == "translator"


def _role(app: Any) -> str:
    var = getattr(app, "role_var", None)
    try:
        return str(var.get()) if var is not None else ""
    except Exception:  # noqa: BLE001 - (the window going)
        return ""


def toggle(app: Any) -> None:
    """The left pane's Edit: the Translator role on or off, chosen by the reader (kept for the book:
    `TranslatorMixin._on_role_changed`)."""
    var = getattr(app, "role_var", None)
    if var is None:
        return
    var.set("reader" if _role(app) == "translator" else "translator")
    app._see_adding = False
    app._see_bare = None
    app._on_role_changed()


# ------------------------------------------------------------------ the marks
def _colour(region: Any) -> tuple[int, int, int]:
    if getattr(region, "flags", None):
        return FLAGGED
    if str(getattr(region, "kind", "")).startswith("manual"):
        return OWN
    return TRANSLATED if getattr(region, "status", "") == "translated" else NOT_TRANSLATED


def _plate(app: Any, text: str, colour: tuple[int, int, int], dpi: int) -> Any:
    kept: dict[Any, Any] = app.__dict__.setdefault("_see_plates", {})
    key = (text, colour, dpi)
    found = kept.get(key)
    if found is None:
        if len(kept) >= PLATES_KEPT:
            kept.clear()
        found = kept[key] = pn.badge(text, colour, dpi)
    return found


def _place_plate(box: st.Box, plate: Any, size: tuple[int, int]) -> tuple[int, int]:
    """A number plate's top left: over the box's top left corner, just outside it where the frame has room."""
    h, w = plate.shape[:2]
    x = max(0, min(size[0] - w, box[0] - w // 3))
    y = box[1] - h + h // 3 if box[1] - h + h // 3 >= 0 else box[1]
    return int(x), int(max(0, min(size[1] - h, y)))


def _editor_region(app: Any) -> Any:
    editor = getattr(app, "_editor", None)
    try:
        if editor is not None and editor.winfo_exists():
            return getattr(editor, "region", None)
    except Exception:  # noqa: BLE001 - (a dialog going)
        pass
    return None


def marks_for(app: Any) -> st.Marks | None:
    """The marks of the page on show while Edit is on and the page on show is the last translated one (`_editing`):
    its regions, numbered in the reading order (while it is being clicked, the place each has been given, "?" for
    none yet), those chosen, the one in the editor, the one whose original is shown, whether a press only clicks (an
    editor open, a change being stored, the order being clicked), whether a region is to be added, the boxes of a
    change being stored. Made again only when one of those changed (the same marks are handed again)."""
    if not getattr(app, "busy", False) and getattr(app, "_see_pending", ()):  # (the change stored, or none begun:
        app._see_pending = ()  # its boxes are the page's now, or were never anything)
    if not on(app):
        return None
    result = getattr(app, "last_result", None)
    try:
        editing = result is not None and result.original is not None and app._editing()
    except Exception:  # noqa: BLE001 - (a page going)
        editing = False
    if not editing:
        return None
    from .translator import chosen_regions

    regions = app._page_regions()
    ordering = getattr(app, "_ordering", None)
    chosen = chosen_regions(app)
    held = _editor_region(app)
    bare = getattr(app, "_see_bare", None) if held is not None else None
    busy = bool(getattr(app, "busy", False))
    pending = getattr(app, "_see_pending", ())
    dpi = int(getattr(app, "_see_dpi", st.BASE_DPI))
    adding = bool(getattr(app, "_see_adding", False))
    locked = held is not None or busy or ordering is not None
    seen = int(getattr(app, "_see_edit_seen", 0))
    content = (id(result), id(result.original), tuple((id(r), tuple(r.bbox), r.status, r.kind, bool(getattr(r, "flags", None)))
                                                      for r in regions),
               None if ordering is None else tuple(id(r) for r in ordering), tuple(id(r) for r in chosen),
               id(held) if held is not None else 0, id(bare) if bare is not None else 0, locked, adding,
               tuple(pending), seen, dpi)
    memo = getattr(app, "_see_edit_memo", None)
    if memo is not None and memo[0] == content:
        return memo[1]
    size = tuple(result.original.size)
    boxes = tuple(tuple(int(v) for v in r.bbox) for r in regions)
    plates = []
    for i, r in enumerate(regions):
        if ordering is not None:
            place = next((n for n, o in enumerate(ordering, 1) if o is r), 0)
            text = str(place) if place else "?"
        else:
            text = str(i + 1)
        plate = _plate(app, text, _colour(r), dpi)
        plates.append((plate, _place_plate(boxes[i], plate, size)))  # type: ignore[arg-type]

    def index(region: Any) -> int | None:
        return next((i for i, r in enumerate(regions) if r is region), None)

    serial = int(getattr(app, "_see_edit_serial", 0)) + 1
    app._see_edit_serial = serial
    marks = st.Marks(key=id(result.original), boxes=boxes, plates=tuple(plates),
                     chosen=tuple(i for i in (index(r) for r in chosen) if i is not None),
                     held=index(held) if held is not None else None, bare=index(bare) if bare is not None else None,
                     locked=locked, adding=adding, ghosts=tuple(pending), seen=seen, serial=serial)
    app._see_edit_memo = (content, marks, list(regions))
    kept = app.__dict__.setdefault("_see_edit_regions", {})
    kept[serial] = list(regions)
    for old in [k for k in kept if k < serial - 8]:
        kept.pop(old, None)
    return marks


def tick(app: Any, over: Any) -> None:
    """Every tick: what the reader did on the regions acted on (`act`), then the marks as they are now handed to the
    see-through window (None while Edit is off or the page on show is no translated one)."""
    for event in over.take_edits():
        app._see_edit_seen = max(int(getattr(app, "_see_edit_seen", 0)), int(event.get("press", 0)))
        try:
            act(app, event)
        except Exception:  # noqa: BLE001 - one press's fault: the next is acted on
            seethrough.log.debug("see-through mode: a press in Edit could not be acted on", exc_info=True)
    marks = marks_for(app)
    if marks is None:  # (Edit off, or another page on show: a region to add and the original shown go with it)
        app._see_adding = False
        app._see_bare = None
    over.set_edit(marks)


def _regions_of(app: Any, event: dict[str, Any]) -> list[Any] | None:
    """The regions the marks of *event* numbered, while their page is still the one on show; None otherwise."""
    result = getattr(app, "last_result", None)
    if result is None or result.original is None or id(result.original) != event.get("key"):
        return None
    try:
        if not app._editing():
            return None
    except Exception:  # noqa: BLE001
        return None
    regions = (getattr(app, "_see_edit_regions", {}) or {}).get(event.get("marks"))
    from .translator import holds

    return [r for r in regions if holds(result, r)] if regions is not None else None


def act(app: Any, event: dict[str, Any]) -> None:
    """A press of the reader's on the page in Edit (`SeeThrough.take_edits`): a click edits the region (Shift: chooses
    it with the others, or no more; while the reading order is clicked: numbers it), a move or a resize stores the
    box (the regions chosen with it moved by as much), a rectangle drawn adds a region. Nothing for a page gone by now,
    nor while a change is being stored."""
    kind = event.get("kind")
    if kind == "add":
        adding, app._see_adding = getattr(app, "_see_adding", False), False
        box = event.get("box")
        if not adding:
            return
        if box is None or app.busy or not _on_page(app, event):
            app.say(ADD_GIVEN_UP)
            return
        app._see_pending = (tuple(int(v) for v in box),)
        app._add_region(tuple(int(v) for v in box))
        return
    regions = _regions_of(app, event)
    if regions is None:
        return
    all_regions = (getattr(app, "_see_edit_regions", {}) or {}).get(event.get("marks")) or []
    index = event.get("index")
    region = all_regions[index] if isinstance(index, int) and 0 <= index < len(all_regions) else None
    if region is not None and not any(r is region for r in regions):
        region = None
    if kind == "click":
        if region is None:
            return
        if getattr(app, "_ordering", None) is not None:
            if not any(r is region for r in app._ordering):
                app._ordering.append(region)
                app._redisplay()
            return
        if _editor_region(app) is not None:  # the editor open: it comes to the front (one region at a time)
            _front_editor(app)
            return
        if app.busy:
            return
        if event.get("shift"):
            app._toggle_chosen(region)
            return
        app._choose(region)
        open_editor(app, region)
        return
    if kind in ("move", "resize") and not app.busy and _editor_region(app) is None:
        # (region, its new box) pairs: a page's regions are compared by their fields, so no dict is keyed by them
        moved = [(all_regions[int(i)], tuple(int(v) for v in box)) for i, box in (event.get("boxes") or {}).items()
                 if 0 <= int(i) < len(all_regions) and any(r is all_regions[int(i)] for r in regions)]
        if not moved:
            return
        app._see_pending = tuple(box for _r, box in moved)
        if len(moved) > 1:
            first, box = moved[0]
            app._grip_box = None
            app._move_regions([r for r, _b in moved], box[0] - first.x0, box[1] - first.y0)
        else:
            (target, box), = moved
            app._choose(target)
            app._move_region(target, box)


def _on_page(app: Any, event: dict[str, Any]) -> bool:
    result = getattr(app, "last_result", None)
    try:
        return (result is not None and result.original is not None and id(result.original) == event.get("key")
                and app._editing())
    except Exception:  # noqa: BLE001
        return False


def _front_editor(app: Any) -> None:
    editor = getattr(app, "_editor", None)
    try:
        if editor is not None and editor.winfo_exists():
            seethrough.asked(app)
            editor.lift()
            editor.focus_force()
    except Exception:  # noqa: BLE001 - (a dialog going)
        pass


# ------------------------------------------------------------------ the editor beside the region
def open_editor(app: Any, region: Any) -> None:
    """The region editor on *region* of the page on show (`TranslatorMixin._open_editor`), asked for by the reader:
    it takes the keys as it shows (`seethrough.asked`) and goes beside the region's box (`editor_place`)."""
    seethrough.asked(app)
    app._open_editor(region)


def editor_place(app: Any, region: Any) -> Callable[[int, int], tuple[int, int]] | None:
    """Where the editor of *region* goes on the screen, once its size is known (a function of its width and height
    giving its top left): beside the region's box - to its right, else to its left, else as near as the monitor's work
    area lets it -, level with the box's top, on the viewer's monitor; never over the box where there is room beside
    it. None when the viewer's place on the screen is not known."""
    over = getattr(app, "_see_through", None)
    origin = over.client_origin() if over is not None else None
    if origin is None:
        return None
    box = tuple(int(v) for v in region.bbox)
    dpi = int(getattr(app, "_see_dpi", st.BASE_DPI))
    gap = st.scaled(EDITOR_GAP, dpi)
    left, top, right, bottom = origin[0] + box[0], origin[1] + box[1], origin[0] + box[2], origin[1] + box[3]

    def place(width: int, height: int) -> tuple[int, int]:
        from .layout import frame_extents, work_area

        side, title = frame_extents()
        outer_w, outer_h = width + 2 * side, height + title + side
        area = work_area(app, (left + right) // 2, (top + bottom) // 2)
        if right + gap + outer_w <= area[2]:
            x = right + gap
        elif left - gap - outer_w >= area[0]:
            x = left - gap - outer_w
        else:
            x = max(area[0], min(area[2] - outer_w, right + gap))
        y = max(area[1], min(area[3] - outer_h, top))
        return int(x), int(y)

    return place


def set_bare(app: Any, region: Any, shown: bool) -> None:
    """The editor's Show original: held (*shown*), the region's patches are left out - the viewer's original shows
    there; let go, they are back."""
    app._see_bare = region if shown else None
    over = getattr(app, "_see_through", None)
    if over is not None:
        over.set_edit(marks_for(app))


# ------------------------------------------------------------------ the Menu while Edit is on
def _asking(app: Any, command: Callable[[], Any]) -> Callable[[], None]:
    def run() -> None:
        seethrough.asked(app)
        command()
    return run


def add_region(app: Any) -> None:
    """The Menu's Add a text area: the next drag on the page draws a region of the reader's (the whole page takes the
    mouse until then; a click without a drag gives it up)."""
    try:
        if not app._editing() or app.busy:
            return
    except Exception:  # noqa: BLE001
        return
    app._see_adding = True
    app.say(ADDING)


def cancel_order(app: Any) -> None:
    if app._end_order():
        app.say("Reading order cancelled.")
        app._redisplay()


def toggle_order(app: Any) -> None:
    """The Menu's Reading order and Finish order (`TranslatorMixin.toggle_order`), the line saying how here."""
    starting = getattr(app, "_ordering", None) is None
    app.toggle_order()
    if starting and getattr(app, "_ordering", None) is not None:
        app.say(ORDERING)


def build_menu(app: Any, menu: Any, page: Any) -> None:
    """The Menu's entries while Edit is on, at its top (`see_menu.build`): Undo, Redo, the cascade Page (*page*: the
    reading order - Finish order and Cancel the reading order while it is being clicked -, Add a text area, Skip page;
    then what the window's Page menu does to the regions chosen: Set kind..., Set text size..., Place in reading
    order..., Copy format, Paste format, Paste format on every region of this kind..., Copy region, Paste region, Drop
    the chosen regions, Ignore this area on all pages of this book; and Use these areas for the series), and the
    editing lists and sheets. Every entry that opens a dialog counts as the reader asking (`seethrough.asked`)."""
    from .book_areas import IGNORE_EVERYWHERE, USE_FOR_SERIES

    page.delete(0, "end")
    menu.add_command(label=_("Undo"), command=app.undo_edit)
    menu.add_command(label=_("Redo"), command=app.redo_edit)
    if getattr(app, "_ordering", None) is not None:
        page.add_command(label=_("Finish order"), command=lambda: toggle_order(app))
        page.add_command(label=_(CANCEL_ORDER), command=lambda: cancel_order(app))
    else:
        page.add_command(label=_("Reading order"), command=lambda: toggle_order(app))
    page.add_command(label=_(ADD_ENTRY), command=lambda: add_region(app))
    page.add_command(label=_("Skip page"), command=app.toggle_skip)
    page.add_separator()
    page.add_command(label=_("Set kind..."), command=_asking(app, app.set_kind_of_selection))
    page.add_command(label=_("Set text size..."), command=_asking(app, app.set_size_of_selection))
    page.add_command(label=_("Place in reading order..."), command=_asking(app, app.place_in_order))
    page.add_command(label=_("Copy format"), command=app.copy_format)
    page.add_command(label=_("Paste format"), command=app.paste_format)
    page.add_command(label=_("Paste format on every region of this kind..."),
                     command=_asking(app, app.paste_format_on_kind))
    page.add_command(label=_("Copy region"), command=app.copy_region)
    page.add_command(label=_("Paste region"), command=app.paste_region)
    page.add_command(label=_(DROP_CHOSEN), command=app._drop_chosen)
    page.add_command(label=_(IGNORE_EVERYWHERE), command=_asking(app, app.ignore_area_everywhere))
    page.add_separator()
    ready = getattr(app, "series_areas_ready", None)
    page.add_command(label=_(USE_FOR_SERIES), command=app.use_areas_for_series_now,
                     state="normal" if ready is not None and ready() else "disabled")
    menu.add_cascade(label=_("Page"), menu=page)
    menu.add_separator()
    for label, command in (("Review...", app.open_review), ("My corrections...", app.open_corrections),
                           ("Lines to review...", app.open_lines_to_review),
                           ("Find and replace...", app.open_find_replace), ("Series sheet...", app.open_glossary),
                           ("Book settings...", app.open_book_settings)):
        menu.add_command(label=_(label), command=_asking(app, command))
    menu.add_separator()
