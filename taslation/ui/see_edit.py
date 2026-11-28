"""Editing on the overlay: see-through mode's editing of the page on show, in place of the Translator role's window
(whose page and regions are a canvas that is never on the screen here).

* Editing is the Translator role (``role_var`` "translator"); the left pane's switch Reader mode, checked, is the
  Reader role (`toggle`). A book starts as the reader last chose for it (`translator.chosen_role`, kept per book as
  the window kept it), else as the start asks (``gui --role``, ``role`` in the settings file - Settings' "Start in
  Reader mode" -; editing by default); switched by the reader, it is remembered for the book
  (`TranslatorMixin._on_role_changed`).
* While editing, the see-through window takes the mouse over the whole picture (`SeeThrough.set_ground`: a page
  with no marks of its own too) - the viewer gets the keys alone: the pages are turned with the keys - but where a
  window lies over the viewer. The page's regions (`_page_regions`, the window's) are handed to it as marks
  (`marks_for`, `seethrough.Marks`): each box is outlined all the time in the colour the window outlined it in
  (translated, not translated, the reader's own, flagged) and carries its number in the reading order on a plate of
  that colour; the box under the pointer gets the stronger outline and, once the pointer has rested on it the hover
  delay, gives way to the original as in Reader mode (its words in the right pane's block), the boxes chosen and the
  one in the editor are outlined too, the one chosen alone with its corner handles. `tick` acts on what the reader
  did there (`act`): a click chooses the region, a double click opens the region editor beside the box
  (`open_editor`, `editor_place`: alone, on the viewer's monitor, taking the keys; the foreground back to the viewer
  once it closes; following its page taken again at another size of the viewer's window, and beside the box again
  should it now lie over it, `editor_beside`), Shift+click chooses several (`SelectionMixin._toggle_chosen`), the
  Delete key drops those chosen (`_drop_chosen`: Menu > Undo brings them back; the key is TASlation's only while a
  region is chosen, `delete_wanted`), a drag moves the box (those chosen with it: `_move_regions`), a drag on a
  corner resizes it (`_move_region`), a click on its plate types its place in the reading order (`PlaceEntry`: the
  region kept on its own page of a spread, the order made again, the lines whose context changed translated again,
  as every tool's new order is; a drag from the plate moves the box); a drag on the empty ground draws a region to
  add, a click there drops the choice; while the reading order is clicked, a click numbers the region. A region in
  the editor keeps its patches whatever the frame says; the editor's Show original, held, shows the original under
  it (`set_bare`).
* Adding a text area, editing or in Reader mode (`toggle_adding`): the left pane's Add area, the Insert key while
  the viewer is in front (``Settings.add_area_key``, `capture.seethrough.SeeThrough.set_add_key`; Delete, while a
  region is chosen, is the only other key TASlation takes) and the Menu's Add a text area (editing) - once the page
  on show is the last translated one, no job at work, the lettering shown and the book named (`why_not_adding`).
  The next drag on the page draws the region (the whole page takes the mouse until then: `marks_for`'s marks, of no
  box in Reader mode), which is read and translated (`_add_region`); a click without a drag, a right click, Insert
  or Add area again gives it up. In Reader mode every click is the viewer's again after it.
* The Menu has the rest while editing (`build_menu`): Undo and Redo, the page's tools (Reading order, Add a text
  area, Skip page; what the window's Page menu does to the regions chosen), and the lists and sheets (Review..., My
  corrections..., Lines to review..., Find and replace..., Series sheet..., Book settings...), each a dialog alone.
  Every key goes to the viewer - Insert excepted, while it adds a text area, and Delete while a region is chosen -,
  but inside TASlation's own dialogs and the plate's place entry."""

from __future__ import annotations

import time
from typing import Any, Callable

from .. import panes as pn
from .. import seethrough as st
from ..i18n import _
from . import seethrough

READER_MODE = "Reader mode"  # (the left pane's switch: checked, every click is the viewer's; unchecked, editing)
EDIT_ON = ("Editing: click a bubble to select it, double-click it to edit it, drag it to move it, press Delete to "
           "drop it; drag on empty space to add one, click its number to change its place in the reading order. Turn "
           "pages with the keys.")
EDIT_OFF = "Reader mode: every click and the wheel go to the viewer."
PLACE_ASK = "Type the bubble's place in the reading order (1 to {n}) and press Enter; Esc gives it up."
# (... on a spread: the bubble stays on its own page, `selection.placed_order`)
PLACE_ASK_SPREAD = ("Type the bubble's place in the reading order (1 to {n}) and press Enter; Esc gives it up. It "
                    "stays on its own page: a place on the facing page puts it first or last there.")
ORDERING = "Reading order: click the bubbles in the order they are read, then choose Finish order in the Menu."
ADD_ENTRY = "Add a text area"
ADD_AREA = "Add area"  # (the left pane's row: the Insert key is named in the help and the manual, the pane no wider)
ADDING = ("Drag a rectangle over the text to add it. A click without a drag, a right click or Add area again gives "
          "it up.")
ADD_GIVEN_UP = "No text area was added."
ADD_NOT_NOW = "A text area can be added once the page on show is translated."
ADD_NO_LETTERING = "Turn Lettering on to add a text area."
ADD_NO_BOOK = "Could not record the rectangle: give the book a name first (Menu > Series and Volume...)."
CANCEL_ORDER = "Cancel the reading order"
DROP_CHOSEN = "Drop the chosen regions"
# the plates' colours (RGB), as the window outlined the regions (`LiveViewMixin._overlay_items`)
TRANSLATED, NOT_TRANSLATED, OWN, FLAGGED = (61, 220, 132), (255, 179, 71), (77, 163, 255), (255, 94, 94)
EDITOR_GAP = 12  # px (at 96 DPI) between a region's box and the editor beside it
PLATES_KEPT = 256


def on(app: Any) -> bool:
    """Whether the page is being edited: see-through mode with TASlation's own window hidden, in the Translator role
    (Reader mode unchecked), once the role of the book named is known (`role_known`)."""
    return seethrough.hidden(app) and seethrough.on(app) and _role(app) == "translator" and role_known(app)


def role_known(app: Any) -> bool:
    """Whether the role of the book named is known: not while it is still to be decided - the Book box rests a moment
    first, `TranslatorMixin._book_for_role`, and a book opens as the reader last chose for it -, so that the start's
    default never applies to the lettering meanwhile: until then it takes no mouse and shows no boxes, as in Reader
    mode, and nothing is said."""
    return getattr(app, "_role_job", None) is None


def reader_mode(app: Any) -> bool:
    """Whether the left pane's Reader mode shows checked, and the right pane's foot says Reader mode: the role in
    force (whatever the lettering applies now: `on`)."""
    return _role(app) != "translator"


def _role(app: Any) -> str:
    var = getattr(app, "role_var", None)
    try:
        return str(var.get()) if var is not None else ""
    except Exception:  # noqa: BLE001 - (the window going)
        return ""


def toggle(app: Any) -> None:
    """The left pane's Reader mode: the Reader role (checked) or editing, chosen by the reader (kept for the book:
    `TranslatorMixin._on_role_changed`)."""
    var = getattr(app, "role_var", None)
    if var is None:
        return
    drop_place_entry(app)
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


def _bgr(colour: tuple[int, int, int]) -> tuple[int, int, int]:
    return colour[2], colour[1], colour[0]


def _plate(app: Any, text: str, colour: tuple[int, int, int], dpi: int) -> Any:
    kept: dict[Any, Any] = app.__dict__.setdefault("_see_plates", {})
    key = (text, colour, dpi)
    found = kept.get(key)
    if found is None:
        if len(kept) >= PLATES_KEPT:
            kept.clear()
        found = kept[key] = pn.badge(text, colour, dpi)
    return found


def _place_plate(box: st.Box, plate: Any, size: tuple[int, int], dpi: int = st.BASE_DPI) -> tuple[int, int]:
    """A number plate's top left: on the box's top edge, just above it where the frame has room (inside its top
    else), in from its top left corner by the corner's grip (`seethrough.GRIP_PX`: a press there resizes the box, one
    on the plate types its place)."""
    h, w = plate.shape[:2]
    x = max(0, min(size[0] - w, box[0] + st.scaled(st.GRIP_PX, dpi) + 1))
    y = box[1] - h if box[1] - h >= 0 else box[1]
    return int(x), int(max(0, min(size[1] - h, y)))


def _editor_region(app: Any) -> Any:
    editor = getattr(app, "_editor", None)
    try:
        if editor is not None and editor.winfo_exists():
            return getattr(editor, "region", None)
    except Exception:  # noqa: BLE001 - (a dialog going)
        pass
    return None


def _lettered(region: Any) -> bool:
    """Whether *region* is lettered or erased on the page (`pipeline.erases`): its box is marked when none of that
    shows (`seethrough.Marks.lettered`)."""
    from ..pipeline import erases

    try:
        return bool(erases(region))
    except AttributeError:  # (a region with no translation kept: nothing lettered)
        return False


def marks_for(app: Any) -> st.Marks | None:
    """The marks of the page on show while editing and the page on show is the last translated one (`_editing`): its
    regions, numbered in the reading order (while it is being clicked, the place each has been given, "?" for none
    yet) and outlined in their colours, those chosen, the one in the editor, the one whose original is shown, whether
    a press only clicks (an editor open, a change being stored, the order being clicked), whether a region is to be
    added, the boxes of a change being stored. In Reader mode, while a region is to be added on the page on show
    (`toggle_adding`): marks of no box, the whole page taking the mouse for the rectangle alone. Made again only when
    one of those changed (the same marks are handed again)."""
    if not getattr(app, "busy", False) and getattr(app, "_see_pending", ()):  # (the change stored, or none begun:
        app._see_pending = ()  # its boxes are the page's now, or were never anything)
    edit = on(app)
    adding = bool(getattr(app, "_see_adding", False))
    if not edit and not (adding and seethrough.hidden(app) and seethrough.on(app)):
        return None
    result = getattr(app, "last_result", None)
    try:
        editing = result is not None and result.original is not None and (
            app._editing() if edit else app._result_on_show())
    except Exception:  # noqa: BLE001 - (a page going)
        editing = False
    if not editing:
        return None
    from .translator import chosen_regions

    regions = app._page_regions() if edit else []
    ordering = getattr(app, "_ordering", None) if edit else None
    chosen = chosen_regions(app) if edit else []
    held = _editor_region(app) if edit else None
    bare = getattr(app, "_see_bare", None) if held is not None else None
    busy = bool(getattr(app, "busy", False))
    pending = getattr(app, "_see_pending", ()) if edit else ()
    dpi = int(getattr(app, "_see_dpi", st.BASE_DPI))
    locked = held is not None or busy or ordering is not None
    seen = int(getattr(app, "_see_edit_seen", 0))
    content = (edit, id(result), id(result.original),
               tuple((id(r), tuple(r.bbox), r.status, r.kind, bool(getattr(r, "flags", None))) for r in regions),
               None if ordering is None else tuple(id(r) for r in ordering), tuple(id(r) for r in chosen),
               id(held) if held is not None else 0, id(bare) if bare is not None else 0, locked, adding,
               tuple(pending), seen, dpi)
    memo = getattr(app, "_see_edit_memo", None)
    if memo is not None and memo[0] == content:
        return memo[1]
    size = tuple(result.original.size)
    boxes = tuple(tuple(int(v) for v in r.bbox) for r in regions)
    plates = []
    colours = []
    for i, r in enumerate(regions):
        if ordering is not None:
            place = next((n for n, o in enumerate(ordering, 1) if o is r), 0)
            text = str(place) if place else "?"
        else:
            text = str(i + 1)
        colour = _colour(r)
        plate = _plate(app, text, colour, dpi)
        plates.append((plate, _place_plate(boxes[i], plate, size, dpi)))  # type: ignore[arg-type]
        colours.append(_bgr(colour))

    def index(region: Any) -> int | None:
        return next((i for i, r in enumerate(regions) if r is region), None)

    serial = int(getattr(app, "_see_edit_serial", 0)) + 1
    app._see_edit_serial = serial
    marks = st.Marks(key=id(result.original), boxes=boxes, plates=tuple(plates),
                     chosen=tuple(i for i in (index(r) for r in chosen) if i is not None),
                     held=index(held) if held is not None else None, bare=index(bare) if bare is not None else None,
                     locked=locked, adding=adding, ghosts=tuple(pending), seen=seen, serial=serial,
                     colours=tuple(colours), lettered=tuple(_lettered(r) for r in regions))
    app._see_edit_memo = (content, marks, list(regions))
    kept = app.__dict__.setdefault("_see_edit_regions", {})
    kept[serial] = list(regions)
    for old in [k for k in kept if k < serial - 8]:
        kept.pop(old, None)
    return marks


def tick(app: Any, over: Any) -> None:
    """Every tick: the presses of the Insert key (`toggle_adding`) and what the reader did on the regions acted on
    (`act`), then the presses of the Delete key (the regions chosen dropped, `delete_wanted`), then the marks as they
    are now handed to the see-through window (None in Reader mode with no region to be added, or while the page on
    show is no translated one), whether the whole page takes the mouse (editing: `SeeThrough.set_ground`) and
    whether the Delete key is wanted now (`SeeThrough.set_delete_key`)."""
    place_entry_tick(app)
    take_keys = getattr(over, "take_keys", None)
    for _when in (take_keys() if take_keys is not None else ()):
        seethrough.did(app, "the Insert key")
        toggle_adding(app)
    for event in over.take_edits():
        app._see_edit_seen = max(int(getattr(app, "_see_edit_seen", 0)), int(event.get("press", 0)))
        try:
            act(app, event)
        except Exception:  # noqa: BLE001 - one press's fault: the next is acted on
            seethrough.log.debug("see-through mode: a press in editing could not be acted on", exc_info=True)
    take_deletes = getattr(over, "take_deletes", None)
    for _when in (take_deletes() if take_deletes is not None else ()):
        seethrough.did(app, "the Delete key")
        if delete_wanted(app):
            app._drop_chosen()
    marks = marks_for(app)
    if marks is None:  # (Reader mode, or another page on show: a region to add and the original shown go with it)
        app._see_adding = False
        app._see_bare = None
        drop_place_entry(app)
    set_ground = getattr(over, "set_ground", None)
    if set_ground is not None:
        set_ground(on(app))
    over.set_edit(marks)
    set_delete_key = getattr(over, "set_delete_key", None)
    if set_delete_key is not None:
        set_delete_key(delete_wanted(app))


def delete_wanted(app: Any) -> bool:
    """Whether the Delete key drops the regions chosen now (the see-through window holds it then, and only then:
    `SeeThrough.set_delete_key` - the viewer has its own Delete at all other times): editing (`on`) the page on show,
    the last translated one, with a region of it chosen; no editor, no place entry open, the reading order not being
    clicked, no region to be added and no change being stored."""
    if not on(app) or getattr(app, "busy", False) or adding(app):
        return False
    if _editor_region(app) is not None or getattr(app, "_ordering", None) is not None:
        return False
    if getattr(app, "_see_place_entry", None) is not None:
        return False
    result = getattr(app, "last_result", None)
    region = getattr(app, "_chosen_region", None)
    try:
        if result is None or result.original is None or region is None or not app._editing():
            return False
    except Exception:  # noqa: BLE001 - (a page going)
        return False
    from .translator import holds

    return holds(result, region)


def _hand_over(app: Any) -> None:
    """The marks as they are now handed to the see-through window at once (the whole page takes the mouse for a
    region to add before the next tick)."""
    over = getattr(app, "_see_through", None)
    if over is None:
        return
    marks = marks_for(app)
    if marks is None:
        app._see_adding = False
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
    """A press of the reader's on the page while editing (`SeeThrough.take_edits`): a click chooses the region alone
    (Shift: chooses it with the others, or no more; while the reading order is clicked: numbers it), a double click
    edits it (`open_editor`), a click on its number plate types its place in the reading order (`PlaceEntry`), a move
    or a resize stores the box (the regions chosen with it moved by as much), a rectangle drawn adds a region (Add
    area's, or one drawn on the empty ground), a click on the empty ground drops the choice. With the editor open, a
    click or a double click on a region brings it to the front (one region at a time). A place entry open goes first,
    whatever the press. Nothing for a page gone by now, nor while a change is being stored."""
    kind = event.get("kind")
    seethrough.did(app, f"a press on the page: {kind}")
    drop_place_entry(app, give_back=True)
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
    if kind == "draw":  # (a rectangle drawn on the empty ground while editing: a region added as Add area adds one)
        box = event.get("box")
        if box is None or not on(app):
            return
        why = why_not_adding(app)
        if why is None and not _on_page(app, event):
            why = ADD_NOT_NOW
        if why is not None:
            app.say(why)
            return
        app._see_pending = (tuple(int(v) for v in box),)
        app._add_region(tuple(int(v) for v in box))
        return
    if kind == "ground":  # (a click on the empty ground: the choice dropped)
        from .translator import chosen_regions

        if on(app) and chosen_regions(app) and not app.busy and _editor_region(app) is None:
            app._choose(None)
            app._redisplay()
        return
    regions = _regions_of(app, event)
    if regions is None:
        return
    all_regions = (getattr(app, "_see_edit_regions", {}) or {}).get(event.get("marks")) or []
    index = event.get("index")
    region = all_regions[index] if isinstance(index, int) and 0 <= index < len(all_regions) else None
    if region is not None and not any(r is region for r in regions):
        region = None
    if kind == "plate":
        if region is None:
            return
        if (getattr(app, "_ordering", None) is None and _editor_region(app) is None and not app.busy
                and not event.get("shift")):
            open_place_entry(app, region)
            return
        kind = "click"  # (the order being clicked, the editor open, a change stored: as a click on the box)
    if kind in ("click", "double"):
        if region is None:
            return
        if getattr(app, "_ordering", None) is not None:  # (a double click numbers it once)
            if not any(r is region for r in app._ordering):
                app._ordering.append(region)
                app._redisplay()
            return
        if _editor_region(app) is not None:  # the editor open: it comes to the front (one region at a time)
            _front_editor(app)
            return
        if app.busy:
            return
        if kind == "click" and event.get("shift"):
            app._toggle_chosen(region)
            return
        app._choose(region)
        if kind == "double":
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
    """Whether the page of *event* is the one on show still, the last translated one (editing or in Reader mode)."""
    result = getattr(app, "last_result", None)
    try:
        return (result is not None and result.original is not None and id(result.original) == event.get("key")
                and app._result_on_show())
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


# ------------------------------------------------------------------ a region's place typed on its plate
def place_ask(regions: Any) -> str:
    """What the status says while a place is typed on a plate: on a spread (the regions on show on two page units)
    also that the bubble stays on its own page."""
    return PLACE_ASK_SPREAD if len({getattr(r, "unit", 0) for r in regions}) > 1 else PLACE_ASK


class PlaceEntry:
    """A small entry over a region's number plate (a click on the plate while editing, `open_place_entry`): the
    region's place in the reading order typed there, 1 to the regions on show - Enter takes it
    (`SelectionMixin._place_regions`: the region kept on its own page of a spread, the order made again as one
    "order" change, the plates numbered anew, the lines whose context changed translated again), Esc gives it up,
    and so does a press anywhere else (on the page: `act`; a side pane: `pane_click`; the viewer or another window:
    the entry's focus lost). It takes the keys as it shows, and gives the foreground back to the viewer as it goes at
    Enter or Esc (`seethrough.closing`)."""

    def __init__(self, app: Any, region: Any, place: int, total: int, at: tuple[int, int, int, int],
                 ask: str = PLACE_ASK) -> None:
        import tkinter as tk

        self.app, self.region, self.total, self.ask = app, region, total, ask
        self.result = getattr(app, "last_result", None)
        self.opened = time.monotonic()
        self.focused = self.closed = False
        self.top = top = tk.Toplevel(app)
        top._see_name = seethrough.PLACE_ENTRY  # type: ignore[attr-defined]  # (the log of the foreground's name)
        top.withdraw()
        top.wm_overrideredirect(True)
        try:
            top.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        self.entry = entry = tk.Entry(top, width=max(3, len(str(total)) + 1), justify="center")
        entry.insert(0, str(place))
        entry.select_range(0, "end")
        entry.pack()
        entry.bind("<Return>", self._take)
        entry.bind("<KP_Enter>", self._take)
        entry.bind("<Escape>", self._give_up)
        entry.bind("<FocusIn>", self._focus_in)
        entry.bind("<FocusOut>", self._focus_out)
        self.hwnd = int(entry.winfo_id())  # (the entry's own window: what the developer tools post their keys to)
        top.update_idletasks()
        from .layout import work_area

        middle = ((at[0] + at[2]) // 2, (at[1] + at[3]) // 2)
        x, y = entry_spot(at, (top.winfo_reqwidth(), top.winfo_reqheight()), work_area(app, *middle))
        top.wm_geometry(f"+{int(x)}+{int(y)}")
        seethrough.asked(app)
        top.deiconify()
        top.lift()
        entry.focus_force()

    def alive(self) -> bool:
        try:
            return bool(self.top.winfo_exists())
        except Exception:  # noqa: BLE001 - (the window going)
            return False

    def _focus_in(self, _event: Any = None) -> None:
        self.focused = True

    def _focus_out(self, _event: Any = None) -> None:
        if self.focused:  # (a click on the viewer or another window: given up, the keys where the click took them)
            self.close(give_back=False)

    def _give_up(self, _event: Any = None) -> str:
        self.close(give_back=True)
        return "break"

    def _take(self, _event: Any = None) -> str:
        try:
            place = int(self.entry.get().strip())
        except ValueError:
            place = 0
        if not 1 <= place <= self.total:
            self.app.say(self.ask, n=self.total)
            self.entry.select_range(0, "end")
            return "break"
        self.close(give_back=True)
        from .translator import holds

        app = self.app
        if (app.busy or app.last_result is not self.result or not holds(self.result, self.region)
                or getattr(app, "_ordering", None) is not None or _editor_region(app) is not None or not on(app)):
            return "break"
        app._place_regions([self.region], place)
        return "break"

    def close(self, give_back: bool) -> None:
        if getattr(self.app, "_see_place_entry", None) is self:
            self.app._see_place_entry = None
        if self.closed or not self.alive():
            self.closed = True
            return
        self.closed = True
        if give_back:
            try:
                seethrough.closing(self.app, self.top)
            except Exception:  # noqa: BLE001 - (the foreground comes back to the viewer as ever: `hand_back`)
                pass
        try:
            self.top.destroy()
        except Exception:  # noqa: BLE001 - (the window going)
            pass


def entry_spot(plate: tuple[int, int, int, int], size: tuple[int, int], area: tuple[int, int, int, int]
               ) -> tuple[int, int]:
    """The top left of a place entry of *size* (it has no frame): centred on the number plate's screen rectangle
    *plate*, moved as needed to lie on *area* (the work area of the monitor the plate is on)."""
    width, height = int(size[0]), int(size[1])
    x = (plate[0] + plate[2]) // 2 - width // 2
    y = (plate[1] + plate[3]) // 2 - height // 2
    return max(area[0], min(int(x), area[2] - width)), max(area[1], min(int(y), area[3] - height))


PLACE_FOCUS_S = 1.5  # a place entry that never got the keys in this long goes (the viewer kept them)


def open_place_entry(app: Any, region: Any) -> bool:
    """The place entry over *region*'s number plate (`PlaceEntry`), its place now typed in it, chosen; the status
    says what to type. False when the viewer's place on the screen or the region's place is not known."""
    over = getattr(app, "_see_through", None)
    origin = over.client_origin() if over is not None else None
    result = getattr(app, "last_result", None)
    regions = app._page_regions()
    now = next((i for i, r in enumerate(regions) if r is region), None)
    if origin is None or now is None or result is None or result.original is None:
        return False
    dpi = int(getattr(app, "_see_dpi", st.BASE_DPI))
    plate = _plate(app, str(now + 1), _colour(region), dpi)
    x, y = _place_plate(tuple(int(v) for v in region.bbox), plate, tuple(result.original.size), dpi)  # type: ignore[arg-type]
    h, w = plate.shape[:2]
    drop_place_entry(app)
    app._choose(region)
    ask = place_ask(regions)
    app._see_place_entry = PlaceEntry(app, region, now + 1, len(regions),
                                      (origin[0] + x, origin[1] + y, origin[0] + x + w, origin[1] + y + h), ask)
    app.say(ask, n=len(regions))
    return True


def drop_place_entry(app: Any, give_back: bool = False) -> None:
    """A place entry open given up (another press, Reader mode, another page): nothing changes. With *give_back* (a
    press on the page or a click on a side pane: neither takes the foreground) the foreground goes back to the viewer
    as the entry goes, where the entry has it (`seethrough.closing`)."""
    entry = getattr(app, "_see_place_entry", None)
    if entry is not None:
        entry.close(give_back=give_back)
        app._see_place_entry = None


def place_entry_tick(app: Any) -> None:
    """(every tick) A place entry that never got the keys (`PLACE_FOCUS_S`) goes: the reader types into the viewer."""
    entry = getattr(app, "_see_place_entry", None)
    if entry is None:
        return
    if not entry.alive():
        app._see_place_entry = None
    elif not entry.focused and time.monotonic() - entry.opened > PLACE_FOCUS_S:
        drop_place_entry(app)


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
    it. To the left rather than over a side pane where the left has room clear of the panes (`pane_boxes`: a pane
    under a window hides, `capture.SeeThrough._place_panes`). None when the viewer's place on the screen is not
    known."""
    over = getattr(app, "_see_through", None)
    origin = over.client_origin() if over is not None else None
    if origin is None:
        return None
    box = tuple(int(v) for v in region.bbox)
    dpi = int(getattr(app, "_see_dpi", st.BASE_DPI))
    gap = st.scaled(EDITOR_GAP, dpi)
    left, top, right, bottom = origin[0] + box[0], origin[1] + box[1], origin[0] + box[2], origin[1] + box[3]
    panes = pane_boxes(app, origin)

    def place(width: int, height: int) -> tuple[int, int]:
        from .layout import frame_extents, work_area

        middle = ((left + right) // 2, (top + bottom) // 2)
        side, title = frame_extents(middle)  # (its frame as the box's monitor draws it)
        outer_w, outer_h = width + 2 * side, height + title + side
        area = work_area(app, *middle)
        y = max(area[1], min(area[3] - outer_h, top))
        to_right, to_left = right + gap, left - gap - outer_w

        def clear(x: int) -> bool:
            return not any(seethrough._meets((x, y, x + outer_w, y + outer_h), p) for p in panes)

        fits_right, fits_left = to_right + outer_w <= area[2], to_left >= area[0]
        if fits_right and (clear(to_right) or not (fits_left and clear(to_left))):
            x = to_right
        elif fits_left:
            x = to_left
        else:
            x = to_right
        x = max(area[0], min(area[2] - outer_w, x))  # (a box partly off the screen: the editor on it all the same)
        return int(x), int(y)

    return place


def pane_boxes(app: Any, origin: tuple[int, int]) -> list[tuple[int, int, int, int]]:
    """The side panes' screen boxes as last handed to the see-through window (`seethrough.panes_tick`: the left one,
    and the right one as the indicators or the bubble's block), the viewer's client area at *origin*; hidden ones none."""
    memo = getattr(app, "_see_pane_memo", None) or {}
    out = []
    for side in ("left", "right", "bubble"):
        entry = memo.get(side)
        box = entry[2] if entry else None
        if box is not None:
            out.append((origin[0] + int(box[0]), origin[1] + int(box[1]), origin[0] + int(box[2]),
                        origin[1] + int(box[3])))
    return out


def editor_beside(app: Any, editor: Any, region: Any) -> bool:
    """The open editor *editor* beside *region* again (`editor_place`) where it now lies over the region's box on the
    screen - its page taken again at another size of the viewer's window (`TranslatorMixin._carry_editor`) -; left
    where it is otherwise, as a dialog the reader works in is. True when it was moved."""
    over = getattr(app, "_see_through", None)
    origin = over.client_origin() if over is not None else None
    place = editor_place(app, region)
    if origin is None or place is None:
        return False
    box = tuple(int(v) for v in region.bbox)
    screen_box = (origin[0] + box[0], origin[1] + box[1], origin[0] + box[2], origin[1] + box[3])
    try:
        editor.update_idletasks()
        x, y = int(editor.winfo_rootx()), int(editor.winfo_rooty())
        width, height = int(editor.winfo_width()), int(editor.winfo_height())
    except Exception:  # noqa: BLE001 - (a dialog going)
        return False
    if not seethrough._meets((x, y, x + width, y + height), screen_box):
        return False
    to = place(width, height)
    try:
        editor.geometry(f"+{int(to[0])}+{int(to[1])}")
    except Exception:  # noqa: BLE001 - (a dialog going)
        return False
    return True


def set_bare(app: Any, region: Any, shown: bool) -> None:
    """The editor's Show original: held (*shown*), the region's patches are left out - the viewer's original shows
    there; let go, they are back."""
    app._see_bare = region if shown else None
    over = getattr(app, "_see_through", None)
    if over is not None:
        over.set_edit(marks_for(app))


# ------------------------------------------------------------------ the Menu while editing
def _asking(app: Any, command: Callable[[], Any]) -> Callable[[], None]:
    def run() -> None:
        seethrough.asked(app)
        command()
    return run


def adding(app: Any) -> bool:
    """Whether a region is to be added: the next drag on the page draws it (the left pane's Add area shows pressed)."""
    return bool(getattr(app, "_see_adding", False))


def why_not_adding(app: Any) -> str | None:
    """Why no text area can be added now (the line the status says then), None when one can: TASlation's own window
    hidden (the one mode), the page on show the last translated one (`_result_on_show`), no job at work, the lettering
    shown (its window takes the drag) and the book named (a region of the reader's is kept with the book)."""
    if not (seethrough.hidden(app) and seethrough.on(app)):
        return ADD_NOT_NOW
    if not getattr(app._see_through, "on", True):
        return ADD_NO_LETTERING
    result = getattr(app, "last_result", None)
    try:
        ready = result is not None and result.original is not None and bool(app._result_on_show())
    except Exception:  # noqa: BLE001 - (a page going)
        ready = False
    if not ready or getattr(app, "busy", False):
        return ADD_NOT_NOW
    if getattr(getattr(app, "pipeline", None), "annotations", True) is None:
        return ADD_NO_BOOK
    return None


def start_adding(app: Any) -> bool:
    """A region of the reader's to be added on the page on show, editing or in Reader mode: the next drag on the page draws it
    (the whole page takes the mouse until then, `marks_for`); a click without a drag, a right click, Insert or Add
    area again gives it up. Where none can be added now, the status says why (`why_not_adding`). Whether it began."""
    why = why_not_adding(app)
    if why is not None:
        app.say(why)
        return False
    app._see_adding = True
    app.say(ADDING)
    _hand_over(app)
    return True


def give_up_adding(app: Any) -> None:
    """The region to be added given up (Add area again, Insert again): nothing is added."""
    app._see_adding = False
    app.say(ADD_GIVEN_UP)
    _hand_over(app)


def toggle_adding(app: Any) -> None:
    """The left pane's Add area and the Insert key: a region to add begun (`start_adding`), or given up while one is
    to be added (`give_up_adding`)."""
    if adding(app):
        give_up_adding(app)
    else:
        start_adding(app)


def add_region(app: Any) -> None:
    """The Menu's Add a text area (editing): as the left pane's Add area begins it (`start_adding`)."""
    if not adding(app):
        start_adding(app)


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
    """The Menu's entries while editing, at its top (`see_menu.build`): Undo, Redo, the cascade Page (*page*: the
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
