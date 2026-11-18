"""Typing through an input method (Windows' IME: Japanese, Chinese, Korean) in the window's text boxes: the text being
composed shows in the box it goes into, whatever the IME's own window does (`install`).

Tk 8.6 on Windows (8.6.15 here) never draws the text being composed. It only puts the IME's composition window at
the caret of the box with the keys (``ImmSetCompositionWindow`` with CFS_POINT, each time it draws that caret
somewhere new; the font is left as the IME has it) and gets the text once the IME commits it, as key presses
(``GCS_RESULTSTR``); in between the IME draws that text in a small window of its own. Where that window cannot be
seen, whatever the cause, the reader types blind: the IME's list of candidates shows, and the text comes into the
box only once committed. So:

* `read_composition`: what the IME is composing for the window with the keyboard focus (``ImmGetCompositionStringW``:
  GCS_COMPSTR, GCS_COMPATTR for the clause being converted, GCS_CURSORPOS), None when nothing is. Read only.
* `install`: every text box of the window and of its dialogs (`TYPING_CLASSES`) shows it at its caret while it has
  the keys (`CompositionView`: looked at `KEY_MS` after each key, every `FAST_MS` while composing or just after a
  key, every `SLOW_MS` otherwise): the text underlined, the clause being converted in the selection's colours with
  a thicker line, the IME's cursor before anything is converted. It is a picture over the box (a canvas of the
  box's window, placed in the box; moved left so that its end shows when it would run past the window), which takes
  no key and goes as soon as the composition ends or the box loses the keys. Nothing is written into the box: its
  text, caret and selection change only as the IME commits text, so no trace, check or binding of the box runs for
  the text being composed.
* The IME's own window is given the picture's place and the box's font (``ImmSetCompositionWindow``,
  ``ImmSetCompositionFontW``): where it does show, it lies over the picture, the same text at the same size.

The keys the IME takes while it composes (Enter that commits, Esc that cancels, Space, the arrows, Tab) reach Tk as
VK_PROCESSKEY (229), which Tk maps to no key name: none of the window's bindings of keys runs for them (a dialog's
Enter = OK and Esc = Cancel, the window's keys - those are bound on the main window and its page, which a dialog's
boxes do not carry in their binding tags). Windows only; elsewhere `install` does nothing, and a call that fails
leaves the box as Tk has it."""

from __future__ import annotations

import bisect
import sys
import time
import tkinter as tk
from dataclasses import dataclass
from typing import Any, Callable

from . import theme

IS_WINDOWS = sys.platform == "win32"
TYPING_CLASSES = ("Entry", "TEntry", "TCombobox", "Text", "Spinbox", "TSpinbox")  # the boxes one types in
KEY_MS = 5  # after a key: the IME has the key by then
FAST_MS = 30  # while composing, and for KEY_HOLD_S after a key
SLOW_MS = 150  # while a box has the keys and nothing is composed
AWAY_MS = 500  # while a box has Tk's focus but TASlation is not in front
KEY_HOLD_S = 1.5
GCS_COMPSTR, GCS_COMPATTR, GCS_CURSORPOS = 0x0008, 0x0010, 0x0080
TARGET_ATTRS = (1, 3)  # ATTR_TARGET_CONVERTED, ATTR_TARGET_NOTCONVERTED: the clause being converted
CFS_POINT = 0x0002
DEFAULT_CHARSET = 1
GA_ROOT = 2
MAX_BYTES = 4096  # what is read of a composition at most
VK_PROCESSKEY = 229  # the virtual key of a key the IME took


@dataclass(frozen=True)
class Composition:
    """What the IME is composing: *text*; the clause being converted, (start, end) in *text*, or None before any is;
    where the IME's cursor is in *text*."""

    text: str
    target: tuple[int, int] | None = None
    cursor: int = -1

    def parts(self) -> list[tuple[str, bool]]:
        """The text in pieces, each with whether it is the clause being converted."""
        if self.target is None:
            return [(self.text, False)]
        start, end = self.target
        pieces = [(self.text[:start], False), (self.text[start:end], True), (self.text[end:], False)]
        return [piece for piece in pieces if piece[0]]


def parse_composition(raw: bytes, attrs: bytes = b"", cursor: int = -1) -> Composition | None:
    """The composition the IME gave as UTF-16 (*raw*), with one attribute byte per UTF-16 unit (*attrs*) and its
    cursor in UTF-16 units (*cursor*, -1: at the end); None for no text."""
    raw = bytes(raw[: len(raw) - len(raw) % 2])
    text = raw.decode("utf-16-le", errors="replace")
    if not text:
        return None
    starts, unit = [], 0  # the UTF-16 unit each character starts at
    for ch in text:
        starts.append(unit)
        unit += 2 if ord(ch) > 0xFFFF else 1
    marked = [k for k, attr in enumerate(bytes(attrs)[:unit]) if attr in TARGET_ATTRS]
    target = None
    if marked:
        start = bisect.bisect_right(starts, marked[0]) - 1
        end = bisect.bisect_left(starts, marked[-1] + 1) if marked[-1] + 1 < unit else len(text)
        target = (start, max(start + 1, end))
    at = len(text) if cursor < 0 or cursor >= unit else bisect.bisect_left(starts, cursor)
    return Composition(text, target, at)


# ------------------------------------------------------------------ Windows' side
_api: Any = None


def _load() -> Any:
    """imm32 and user32, loaders of this module's own (the argument types set here stay here)."""
    global _api
    if _api is None:
        import ctypes
        from ctypes import wintypes
        from types import SimpleNamespace

        class CompositionForm(ctypes.Structure):
            _fields_ = [("dwStyle", wintypes.DWORD), ("ptCurrentPos", wintypes.POINT), ("rcArea", wintypes.RECT)]

        class LogFont(ctypes.Structure):  # LOGFONTW
            _fields_ = [("lfHeight", wintypes.LONG), ("lfWidth", wintypes.LONG), ("lfEscapement", wintypes.LONG),
                        ("lfOrientation", wintypes.LONG), ("lfWeight", wintypes.LONG), ("lfItalic", wintypes.BYTE),
                        ("lfUnderline", wintypes.BYTE), ("lfStrikeOut", wintypes.BYTE), ("lfCharSet", wintypes.BYTE),
                        ("lfOutPrecision", wintypes.BYTE), ("lfClipPrecision", wintypes.BYTE),
                        ("lfQuality", wintypes.BYTE), ("lfPitchAndFamily", wintypes.BYTE),
                        ("lfFaceName", wintypes.WCHAR * 32)]

        imm, user = ctypes.WinDLL("imm32"), ctypes.WinDLL("user32")
        imm.ImmGetContext.argtypes, imm.ImmGetContext.restype = [wintypes.HWND], wintypes.HANDLE
        imm.ImmReleaseContext.argtypes, imm.ImmReleaseContext.restype = [wintypes.HWND, wintypes.HANDLE], wintypes.BOOL
        imm.ImmGetCompositionStringW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        imm.ImmGetCompositionStringW.restype = wintypes.LONG
        imm.ImmSetCompositionWindow.argtypes = [wintypes.HANDLE, ctypes.POINTER(CompositionForm)]
        imm.ImmSetCompositionWindow.restype = wintypes.BOOL
        imm.ImmSetCompositionFontW.argtypes = [wintypes.HANDLE, ctypes.POINTER(LogFont)]
        imm.ImmSetCompositionFontW.restype = wintypes.BOOL
        user.GetFocus.argtypes, user.GetFocus.restype = [], wintypes.HWND
        user.GetAncestor.argtypes, user.GetAncestor.restype = [wintypes.HWND, wintypes.UINT], wintypes.HWND
        user.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        user.ScreenToClient.restype = wintypes.BOOL
        _api = SimpleNamespace(ctypes=ctypes, wintypes=wintypes, imm=imm, user=user, CompositionForm=CompositionForm,
                               LogFont=LogFont)
    return _api


def focus_in_window(widget: tk.Misc) -> int:
    """The window with Windows' keyboard focus (``GetFocus``) when it is *widget*'s window (the same top-level
    frame); 0 when it is another one's, none (TASlation not in front) or outside Windows."""
    if not IS_WINDOWS:
        return 0
    try:
        api = _load()
        focus = int(api.user.GetFocus() or 0)
        if not focus:
            return 0
        mine = int(api.user.GetAncestor(widget.winfo_toplevel().winfo_id(), GA_ROOT) or 0)
        return focus if mine and int(api.user.GetAncestor(focus, GA_ROOT) or 0) == mine else 0
    except (AttributeError, OSError, ValueError, tk.TclError):
        return 0


def _string(api: Any, himc: Any, which: int) -> bytes:
    size = int(api.imm.ImmGetCompositionStringW(himc, which, None, 0))
    if size <= 0:
        return b""
    size = min(size, MAX_BYTES)
    buffer = api.ctypes.create_string_buffer(size)
    got = int(api.imm.ImmGetCompositionStringW(himc, which, buffer, size))
    return buffer.raw[:got] if got > 0 else b""


def read_composition(hwnd: int) -> Composition | None:
    """What the IME is composing for the window *hwnd* (the one with the keyboard focus), or None: nothing, no IME,
    outside Windows, a call that failed. Nothing is changed."""
    if not IS_WINDOWS or not hwnd:
        return None
    try:
        api = _load()
        himc = api.imm.ImmGetContext(hwnd)
        if not himc:
            return None
        try:
            raw = _string(api, himc, GCS_COMPSTR)
            if not raw:
                return None
            attrs = _string(api, himc, GCS_COMPATTR)
            cursor = int(api.imm.ImmGetCompositionStringW(himc, GCS_CURSORPOS, None, 0))
        finally:
            api.imm.ImmReleaseContext(hwnd, himc)
    except (AttributeError, OSError, ValueError, TypeError):
        return None
    return parse_composition(raw, attrs, cursor)


def place_ime_window(hwnd: int, x: int, y: int) -> bool:
    """The IME's composition window of *hwnd* at the screen point (*x*, *y*) (CFS_POINT). Whether Windows took it."""
    if not IS_WINDOWS or not hwnd:
        return False
    try:
        api = _load()
        point = api.wintypes.POINT(int(x), int(y))
        if not api.user.ScreenToClient(hwnd, api.ctypes.byref(point)):
            return False
        form = api.CompositionForm(CFS_POINT, point, api.wintypes.RECT())
        himc = api.imm.ImmGetContext(hwnd)
        if not himc:
            return False
        try:
            return bool(api.imm.ImmSetCompositionWindow(himc, api.ctypes.byref(form)))
        finally:
            api.imm.ImmReleaseContext(hwnd, himc)
    except (AttributeError, OSError, ValueError, TypeError):
        return False


def set_ime_font(hwnd: int, family: str, pixels: int, bold: bool = False, italic: bool = False) -> bool:
    """The IME's composition window of *hwnd* draws in *family*, *pixels* high. Whether Windows took it."""
    if not IS_WINDOWS or not hwnd or pixels <= 0:
        return False
    try:
        api = _load()
        font = api.LogFont()
        font.lfHeight, font.lfWeight = -int(pixels), 700 if bold else 400
        font.lfItalic, font.lfCharSet = 1 if italic else 0, DEFAULT_CHARSET
        font.lfFaceName = str(family)[:31]
        himc = api.imm.ImmGetContext(hwnd)
        if not himc:
            return False
        try:
            return bool(api.imm.ImmSetCompositionFontW(himc, api.ctypes.byref(font)))
        finally:
            api.imm.ImmReleaseContext(hwnd, himc)
    except (AttributeError, OSError, ValueError, TypeError):
        return False


# ------------------------------------------------------------------ the box's side
def typable(widget: tk.Misc) -> bool:
    """Whether *widget* takes typing now (not disabled, not read-only)."""
    try:
        if hasattr(widget, "instate"):
            return not widget.instate(("disabled",)) and not widget.instate(("readonly",))
        return str(widget.cget("state")) not in ("disabled", "readonly")
    except tk.TclError:
        return False


def caret_box(widget: tk.Misc) -> tuple[int, int, int] | None:
    """Where *widget*'s caret is, inside it: (x, top of the line, height of the line); None when it is not shown."""
    try:
        if widget.winfo_class() == "Text":
            box = widget.bbox("insert")
            return (int(box[0]), int(box[1]), int(box[3])) if box else None
        count = int(widget.index("end"))  # (Tk's characters: UTF-16 units)
        index = int(widget.index("insert"))
        if count == 0:
            box = widget.bbox(0)
            return int(box[0]), int(box[1]), int(box[3])
        if index >= count:  # after the last character: its right edge
            box = widget.bbox(count - 1)
            return int(box[0]) + int(box[2]), int(box[1]), int(box[3])
        box = widget.bbox(index)
        return int(box[0]), int(box[1]), int(box[3])
    except (tk.TclError, TypeError, IndexError, ValueError):
        return None


def anchor_x(caret: int, width: int, right: int | None) -> int:
    """Where a picture *width* wide that begins at the caret *caret* goes, so that its end shows before *right* (the
    window's inner edge; None: no window on the screen to keep it in): at the caret, or moved left as far as needed
    (wider than the window, its beginning is cut off: its end is where the typing goes on)."""
    if right is None or caret + width <= right:
        return caret
    return right - width


def font_of(widget: tk.Misc) -> str:
    try:
        return str(widget.cget("font")) or "TkTextFont"
    except tk.TclError:
        return "TkTextFont"


def ime_font(widget: tk.Misc, font: str) -> tuple[str, int, bool, bool] | None:
    """*font* as the IME is given it: (family, height in pixels as Tk draws it, bold, italic)."""
    try:
        actual = widget.tk.splitlist(widget.tk.call("font", "actual", font, "-displayof", widget))
        options = {str(k): v for k, v in zip(actual[::2], actual[1::2])}
        size = int(options.get("-size", 0))
        pixels = round(widget.winfo_fpixels(f"{size}p")) if size > 0 else -size
        return (str(options.get("-family", "")), int(pixels), str(options.get("-weight")) == "bold",
                str(options.get("-slant")) == "italic")
    except (tk.TclError, ValueError, TypeError):
        return None


class CompositionView:
    """The text being composed, shown in the box with the keys, for one interpreter (`install`; see the module)."""

    def __init__(self, root: tk.Misc):
        self.root = root
        self.widget: tk.Misc | None = None  # the box with the keys
        self.canvas: tk.Canvas | None = None  # the picture of the text being composed, while there is one
        self._job: str | None = None
        self._keyed = 0.0  # when the last key came
        self._drawn: tuple | None = None  # what the picture shows
        self._placed: tuple[int, int, int] | None = None  # where the IME's own window was put: (window, x, y)
        self._fonted: tuple[int, Any] | None = None  # the font it was given: (window, font)

    # ------------------------------------------------------------------ the box's events
    def focus_in(self, event: tk.Event) -> None:
        widget = event.widget
        if not isinstance(widget, tk.Misc):
            return  # (a window tkinter does not know by name)
        self._drop()
        self.widget, self._placed, self._fonted = widget, None, None
        self._give_font(widget, focus_in_window(widget))
        self._schedule(KEY_MS)

    def focus_out(self, event: tk.Event) -> None:
        if event.widget is not self.widget:
            return
        self.widget = None
        self._drop()
        self._cancel()

    def key(self, event: tk.Event) -> None:
        if event.widget is not self.widget:
            self.focus_in(event)
        self._keyed = time.monotonic()
        self._schedule(KEY_MS)

    # ------------------------------------------------------------------ looking
    def tick(self) -> None:
        self._cancel()  # (a look that was due goes: this one is it)
        widget = self.widget
        if widget is None:
            self._drop()
            return
        try:
            alive = bool(widget.winfo_exists())
        except tk.TclError:
            alive = False
        if not alive:
            self.widget = None
            self._drop()
            return
        hwnd = focus_in_window(widget)
        composition = read_composition(hwnd) if hwnd and typable(widget) else None
        if composition is None:
            self._drop()
        else:
            self._show(widget, composition, hwnd)
        if not hwnd:
            self._schedule(AWAY_MS)
        elif composition is not None or time.monotonic() - self._keyed < KEY_HOLD_S:
            self._schedule(FAST_MS)
        else:
            self._schedule(SLOW_MS)

    def _schedule(self, ms: int) -> None:
        self._cancel()
        try:
            self._job = self.root.after(ms, self.tick)
        except tk.TclError:  # the window is going
            self._job = None

    def _cancel(self) -> None:
        if self._job is not None:
            try:
                self.root.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    # ------------------------------------------------------------------ the picture
    def _give_font(self, widget: tk.Misc, hwnd: int) -> None:
        """The IME's own window in the box's font, once for each box that gets the keys."""
        font = font_of(widget)
        if not hwnd or self._fonted == (hwnd, font):
            return
        self._fonted = (hwnd, font)
        given = ime_font(widget, font)
        if given is not None:
            set_ime_font(hwnd, *given)

    def _show(self, widget: tk.Misc, composition: Composition, hwnd: int) -> None:
        try:
            self._draw(widget, composition, hwnd)
        except tk.TclError:  # the box or its window going
            self._drop()

    def _draw(self, widget: tk.Misc, composition: Composition, hwnd: int) -> None:
        caret = caret_box(widget)
        if caret is None:
            self._drop()
            return
        top = widget.winfo_toplevel()
        cx, cy, height = caret
        font = font_of(widget)
        measure: Callable[[str], int] = lambda text: int(widget.tk.call("font", "measure", font, "-displayof",
                                                                         widget, text))
        line = int(widget.tk.call("font", "metrics", font, "-displayof", widget, "-linespace"))
        width, tall = measure(composition.text) + 2, max(height, line) + 2
        offset = widget.winfo_rootx() - top.winfo_rootx()  # the box's left edge in its window
        right = top.winfo_width() - 2 if top.winfo_width() > 1 else None  # (none while the window is not shown)
        x = anchor_x(offset + cx, width, right) - offset
        y = cy - 1
        colours = (theme.colour("field"), theme.colour("text"), theme.colour("selection"),
                   theme.colour("selection_text"))
        drawn = (composition, x, y, width, tall, font, colours, str(widget))
        canvas = self.canvas
        if canvas is not None and drawn == self._drawn and canvas.winfo_exists():
            return
        if canvas is None or not canvas.winfo_exists() or str(canvas.master) != str(top):
            self._drop()
            canvas = self.canvas = tk.Canvas(top, highlightthickness=0, borderwidth=0, takefocus=0)
        field, ink, selection, selected = colours
        canvas.configure(width=width, height=tall, background=field)
        canvas.delete("all")
        at, text_y = 0, max(0, (tall - line) // 2)
        for piece, target in composition.parts():
            w = measure(piece)
            if target:
                canvas.create_rectangle(at, 0, at + w, tall, fill=selection, width=0)
            canvas.create_text(at, text_y, text=piece, anchor="nw", font=font, fill=selected if target else ink,
                               tags=("composition",))
            canvas.create_line(at, tall - (2 if target else 1), at + w, tall - (2 if target else 1), fill=ink,
                               width=2 if target else 1)
            at += w
        if composition.target is None:  # the IME's cursor, before anything is converted
            cursor = measure(composition.text[: max(0, composition.cursor)])
            canvas.create_line(cursor, text_y, cursor, text_y + line, fill=ink, tags=("cursor",))
        canvas.place(in_=widget, x=x, y=y)
        canvas.tk.call("raise", str(canvas))  # above the box (Canvas.lift raises items, not the canvas)
        self._drawn = drawn
        self._give_font(widget, hwnd)
        point = (hwnd, widget.winfo_rootx() + x, widget.winfo_rooty() + cy)
        if point != self._placed:
            self._placed = point
            place_ime_window(*point)

    def _drop(self) -> None:
        """No picture (the composition ended, or the box lost the keys)."""
        canvas, self.canvas, self._drawn = self.canvas, None, None
        if canvas is not None:
            try:
                canvas.destroy()
            except tk.TclError:
                pass

    def shown(self) -> str:
        """The text the picture shows ("" with none): for the tests."""
        canvas = self.canvas
        if canvas is None or not canvas.winfo_exists():
            return ""
        return "".join(str(canvas.itemcget(item, "text")) for item in canvas.find_withtag("composition"))


_views: dict[str, CompositionView] = {}


def install(root: tk.Misc, enabled: bool | None = None) -> CompositionView | None:
    """Every text box of *root*'s interpreter shows the text being composed (`CompositionView`), once per interpreter;
    the view, or None outside Windows (*enabled*: whatever the system, for the tests)."""
    if not (IS_WINDOWS if enabled is None else enabled):
        return None
    interp = str(root.tk.interpaddr())
    if interp in _views:
        return _views[interp]
    view = _views[interp] = CompositionView(root)
    for cls in TYPING_CLASSES:  # (after the class's own bindings: the box has done its part)
        root.bind_class(cls, "<FocusIn>", view.focus_in, add="+")
        root.bind_class(cls, "<FocusOut>", view.focus_out, add="+")
        root.bind_class(cls, "<KeyPress>", view.key, add="+")

    def gone(event: tk.Event) -> None:
        if event.widget is root:
            view._cancel()
            _views.pop(interp, None)

    root.bind("<Destroy>", gone, add="+")
    return view


__all__ = ["Composition", "CompositionView", "TYPING_CLASSES", "VK_PROCESSKEY", "anchor_x", "caret_box",
           "focus_in_window", "install", "parse_composition", "place_ime_window", "read_composition",
           "set_ime_font", "typable"]
