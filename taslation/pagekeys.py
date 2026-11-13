"""The viewer's page keys - what a key the person presses in TASlation's window is passed on as - and the capture
profiles that keep them per viewer.

What a key means (`PageKeys`): the next page and the previous page - the keys the person presses in TASlation's window,
passed on to the viewer (`ui.reading.forward_key`); TASlation presses no key of its own. A manga reader reads right to
left - its next page is the Left arrow -, an image viewer or a Western
book left to right - the Right arrow -: the two built-in presets (`BUILTIN_PRESETS`). The names a key can have are
`KEY_NAMES` (as `capture.windows.key_code` takes them, any case): the arrows, PageUp / PageDown, Home / End, Space,
Enter, Tab, Backspace, Escape, F1-F12, and a single letter or digit.

The capture profiles (`Profiles`, ``profiles.json`` in the state folder; plain JSON, no images, no text of a book)
keep per viewer - the viewer being the window's title without the book's name (`cache.viewer_key_from_title`; for
a title in which no known viewer is found, the text after its last " - ", as an image viewer's title names the file
it shows, and for a window that is no browser's whose title is a file name or a number alone, the window's class:
`profile_names`) - its capture area and its keys, and beside the viewers the defaults and the reader's own
presets::

    {"<viewer>": {"margins": [0, 85, 0, 0], "margins_large": [0, 120, 0, 0],
                  "keys": {"next": "Right", "prev": "Left"},
                  "while_covered": "draws", "key_way": "real"},
     "default_keys": {"next": "Left", "prev": "Right"},
     "key_presets": {"<the reader's name>": {"next": "Down", "prev": "Up"}}}

"margins" is the area set on the window at the size the reader gave it, "margins_large" the one set on the window
TASlation enlarged (`capture.enlarge_window`): the frames differ, so neither says anything about the other. What older
versions kept here as "fullscreen_reading", and a "first" or "fullscreen" among the keys (the viewer's full-screen
key, which TASlation no longer presses), is ignored.

What TASlation has seen of a viewer that is no browser, so that a later session need not find it out again at the
first key: "while_covered" - "draws" when frames of it came while other windows hid it wholly, "stops" when they came
only once it was raised (`covered_for`, `set_covered`; a browser follows the published rule instead:
`capture.covered_by_opaque`) - and "key_way" - "real" when a posted key did nothing and the same key pressed for real
turned the page, "posted" when a posted key turned it (`key_way_for`, `set_key_way`, `KeyWays.seed`).

Where a viewer's keys come from (`page_keys_for`), key by key: the viewer's own (its profile's "keys"), else the
defaults of ``profiles.json`` ("default_keys": what "Apply to all viewers" wrote), else the settings
(``next_page_key``, ``prev_page_key`` in taslation.toml, which TASlation never rewrites). Every place that passes a key on
to the viewer asks here.

A key pressed in TASlation's window goes on to the viewer as the viewer's own key of the same meaning
(`passed_on`): the window's next and previous keys - the defaults above, the keys a person turns pages with
everywhere - as the viewer's saved next and previous keys, and every other key, a key of the viewer's own among them,
as it is. One press is one key, at the person's pace: the mapping changes which key, never how many, as a keyboard
layout does. `pressed_for` goes the other way (the key to press here for a key of the viewer's: the key back a page).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .atomic import write_atomic

KEY_CODES: dict[str, int] = {  # (lower-case) name -> Windows virtual-key code; `capture.windows.key_code` presses them
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "pageup": 0x21, "pagedown": 0x22, "prior": 0x21, "next": 0x22,
    "home": 0x24, "end": 0x23, "space": 0x20, "enter": 0x0D, "return": 0x0D,
    "escape": 0x1B, "esc": 0x1B, "tab": 0x09, "backspace": 0x08,
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
}
KEY_NAMES = ("Left", "Right", "Up", "Down", "PageUp", "PageDown", "Home", "End", "Space", "Enter", "Tab", "Backspace",
             "Escape", "F1-F12", "A-Z", "0-9")  # the names as they are written in the settings and the dialog
MEANINGS = ("next", "prev")  # PageKeys' fields, as profiles.json names them
SETTING_OF = {"next": "next_page_key", "prev": "prev_page_key"}  # the meanings' settings in taslation.toml
DEFAULT_KEYS = "default_keys"  # profiles.json: the keys of every viewer without its own (above the settings')
KEY_PRESETS = "key_presets"  # profiles.json: the reader's own presets, name -> keys
RESERVED = (DEFAULT_KEYS, KEY_PRESETS)  # top-level entries of profiles.json that are no viewer
COVERED = "while_covered"  # a viewer's profile: "draws" or "stops" while other windows hide it wholly
KEY_WAY = "key_way"  # a viewer's profile: "real" or "posted", how it took a key passed on
KEY_WAYS = ("real", "posted")
OPPOSITE_KEYS = {"left": "Right", "right": "Left", "pagedown": "PageUp", "pageup": "PageDown", "next": "Prior",
                 "prior": "Next", "down": "Up", "up": "Down"}  # a page-turn key -> the key that turns the other way


def valid_key(name: str) -> bool:
    """Whether *name* is a key TASlation can press (`KEY_NAMES`, any case; "" is none)."""
    key = str(name or "").strip().lower()
    return key in KEY_CODES or (len(key) == 1 and key.isascii() and key.isalnum())


def normal_key(name: str) -> str:
    """*name* as it is kept: without the spaces around it; a single letter in capitals ("" stays "")."""
    key = str(name or "").strip()
    return key.upper() if len(key) == 1 else key


def opposite_key(key: str | None) -> str | None:
    """The key that turns the other way for the page-turn key *key* (Left: Right, PageDown: PageUp, ...); None for a
    key without an opposite."""
    return OPPOSITE_KEYS.get(str(key or "").strip().lower())


def same_key(a: str, b: str) -> bool:
    """Whether *a* and *b* press the same key ("PageUp" and "prior" do; "" is no key and never the same)."""
    ka, kb = str(a or "").strip().lower(), str(b or "").strip().lower()
    if not ka or not kb:
        return False
    return KEY_CODES.get(ka, ka) == KEY_CODES.get(kb, kb)


def passed_on(pressed: str, viewer: "PageKeys", window: "PageKeys") -> str:
    """The key the viewer gets for the key *pressed* in TASlation's window: a key of the viewer's own (*viewer*, its
    saved keys) as it is; else the window's next or previous key (*window*: `default_keys`) as the viewer's next or
    previous key; any other key as it is. One press, one key."""
    if same_key(pressed, viewer.next) or same_key(pressed, viewer.prev):
        return pressed
    if same_key(pressed, window.next):
        return viewer.next
    if same_key(pressed, window.prev):
        return viewer.prev
    return pressed


def pressed_for(key: str | None, viewer: "PageKeys", window: "PageKeys", forwarded: Any = ()) -> str | None:
    """The key to press in TASlation's window for the viewer to get *key* (`passed_on`), among the keys the window
    passes on (*forwarded*); None when there is none."""
    if not key:
        return None
    for candidate in (key, window.next, window.prev):
        if any(same_key(candidate, f) for f in forwarded) and same_key(passed_on(candidate, viewer, window), key):
            return candidate
    return None


@dataclass(frozen=True)
class PageKeys:
    """The keys of one viewer: *next* and *prev* turn a page forward and back."""

    next: str = "Left"
    prev: str = "Right"

    def as_dict(self) -> dict[str, str]:
        return {m: getattr(self, m) for m in MEANINGS}

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], base: "PageKeys | None" = None) -> "PageKeys":
        """The keys *data* gives (a profile's "keys": next, prev or both; anything else is ignored), the others
        *base*'s."""
        base = base or cls()
        given = {m: normal_key(data[m]) for m in MEANINGS if isinstance(data.get(m), str)}
        return cls(**{**base.as_dict(), **given})

    @classmethod
    def from_settings(cls, settings: Any) -> "PageKeys":
        """The keys the settings give (`config.Settings`; a missing setting has its default)."""
        default = cls()
        return cls(**{m: normal_key(getattr(settings, SETTING_OF[m], getattr(default, m))) for m in MEANINGS})

    def problems(self) -> list[str]:
        """What is wrong with these keys, in English (the settings, the command line); [] when nothing is."""
        out = []
        for m in MEANINGS:
            key = getattr(self, m)
            if not valid_key(key):
                out.append(f"{SETTING_OF[m]}: unknown key name {key!r} (use {', '.join(KEY_NAMES)})")
        if same_key(self.next, self.prev):
            out.append(f"next_page_key and prev_page_key are the same key ({self.next!r})")
        return out

    def describe(self) -> str:
        """The keys in one line, in English (the command line)."""
        return f"next {self.next}, previous {self.prev}"


BUILTIN_PRESETS: dict[str, PageKeys] = {  # never named after a store or a viewer
    "right-to-left": PageKeys(next="Left", prev="Right"),  # manga readers
    "left-to-right": PageKeys(next="Right", prev="Left"),  # image viewers
}


def _keys_in(data: Any) -> dict[str, str]:
    """The keys an entry of profiles.json holds (only the strings of the meanings; anything else is ignored)."""
    if not isinstance(data, dict):
        return {}
    return {m: normal_key(data[m]) for m in MEANINGS if isinstance(data.get(m), str)}


def default_keys(data: Mapping[str, Any], settings: Any) -> PageKeys:
    """The keys of a viewer without its own: profiles.json's "default_keys" over the settings'."""
    return PageKeys.from_mapping(_keys_in(data.get(DEFAULT_KEYS)), PageKeys.from_settings(settings))


# a window title that is the file an image viewer shows ("000.jpg", "Scan_0012.PNG") or a page number alone ("12",
# "12 / 200"): it changes with every page, so it names no viewer
FILE_TITLE = re.compile(r"(?:.*\.(?:jpe?g|png|webp|gif|bmp|tiff?)|[\d\s/.,_-]*\d[\d\s/.,_-]*)", re.IGNORECASE)


class ViewerTitle(str):
    """A window's title that also carries the window's class name (`viewer_title`), for code that takes the viewer
    as its title (shows it, hands it on) while the profile is looked up by the class (`profile_names`)."""

    class_name: str = ""


def viewer_title(win: Any) -> str:
    """The title of the window *win* (`capture.WindowInfo`) as a `ViewerTitle` that knows the window's class."""
    title = ViewerTitle(str(getattr(win, "title", "") or ""))
    title.class_name = str(getattr(win, "class_name", "") or "")
    return title


def _title_and_class(viewer: Any) -> tuple[str, str]:
    """The title (its spaces as single spaces) and the class name of *viewer*: a window title (a str: no class, unless
    it is a `ViewerTitle`) or a window (`capture.WindowInfo`, or anything with its ``title`` and ``class_name``)."""
    if viewer is None or isinstance(viewer, str):
        return " ".join(str(viewer or "").split()), str(getattr(viewer, "class_name", "") or "")
    return " ".join(str(getattr(viewer, "title", "") or "").split()), str(getattr(viewer, "class_name", "") or "")


def names_a_file(title: str) -> bool:
    """Whether the window title *title* is a file name with an image's extension or a number alone (`FILE_TITLE`)."""
    return bool(FILE_TITLE.fullmatch(str(title or "").strip()))


def class_key(viewer: Any) -> str:
    """The window class a viewer is known by - a window that is no browser's (`capture.is_browser_class`) and whose
    title names the file or the page it shows rather than the viewer (`names_a_file`: an image viewer's "000.jpg",
    then "001.jpg") - else "" (a title alone has no class)."""
    from .capture.windows import is_browser_class

    title, class_name = _title_and_class(viewer)
    return class_name if class_name and not is_browser_class(class_name) and names_a_file(title) else ""


class KeyWays:
    """How the viewers take a key passed on, as this session has seen (by window handle): a viewer that ignored a posted
    key and turned at the same key pressed for real gets real presses first from then on, for a posted key would make
    it wait page_turn_wait_ms each time; one that turned at a posted key keeps getting posted keys. What was seen last
    counts."""

    def __init__(self) -> None:
        self._real: set[int] = set()
        self._posted: set[int] = set()

    def real(self, hwnd: int) -> bool:
        """Whether the window *hwnd* takes only keys pressed for real. A browser always does: measured on a real
        browser-based viewer behind other windows, a posted key does nothing, and its own bars fading away look like a
        key taken; with throwaway Chrome and Edge 156 windows, 0 of 9 posted keys reached the page of a browser that was
        not in front (2026-11-03). What looked like a posted key taken is never learned for a browser."""
        from .capture.windows import BROWSER_CLASSES, window_class

        return hwnd in self._real or window_class(hwnd) in BROWSER_CLASSES

    def posted(self, hwnd: int) -> bool:
        """Whether the window *hwnd* is known to take posted keys."""
        return hwnd in self._posted

    def seed(self, hwnd: int, way: str) -> None:
        """What a session before found of the viewer whose window is *hwnd* (its profile's "key_way": "real" or
        "posted"), unless this session has seen it already; anything else says nothing."""
        if hwnd in self._real or hwnd in self._posted:
            return
        if way == "real":
            self._real.add(hwnd)
        elif way == "posted":
            self._posted.add(hwnd)

    def learned(self, hwnd: int, real: bool, posted: bool) -> None:
        """A key turned the page of the window *hwnd*: *real*, pressed for real after a posted one did nothing, else
        *posted*, a posted one; neither (a key pressed for real at once, a click) says nothing new."""
        if real:
            self._real.add(hwnd)
            self._posted.discard(hwnd)
        elif posted:
            self._posted.add(hwnd)
            self._real.discard(hwnd)


def key_ways(window: Any) -> KeyWays:
    """The notes of the window *window* (`app.App`) on how viewers take keys, made at the first need."""
    ways = getattr(window, "_key_ways", None)
    if ways is None:
        ways = window._key_ways = KeyWays()
    return ways


def viewer_key(viewer: Any) -> str:
    """The name a viewer is known by while TASlation runs (the page panel found in its frames, the area offered once):
    `class_key` for an image viewer whose title is the file it shows, else the viewer's name in the title
    (`cache.viewer_key_from_title`). *viewer* is a window (`capture.WindowInfo`) or its title."""
    from .cache import viewer_key_from_title

    return class_key(viewer) or viewer_key_from_title(_title_and_class(viewer)[0])


def profile_names(viewer: Any) -> tuple[str, ...]:
    """The names the profile of the viewer *viewer* - its window (`capture.WindowInfo`) or the window's title - may
    have, the first one that exists taken: the viewer's name in the title (`cache.viewer_key_from_title`: "<book> - <a
    viewer learned on this computer>" -> the viewer). When no such viewer is found in it - the whole title - a name that
    stays from file to file comes second: for a window that is no browser's whose title is a file name or a page
    number alone ("000.jpg", then "001.jpg": `class_key`), the window's class; else, when the title has " - ", the
    text after the last one: an image viewer's title names the file it shows ("page01.png - Photos"), so the whole
    title changed with every file. A profile kept under a whole title before goes on being found first."""
    from .cache import viewer_key_from_title

    t = _title_and_class(viewer)[0]
    name = viewer_key_from_title(t)
    if name != t:
        return (name,)
    by_class = class_key(viewer)
    if by_class and by_class != name:
        return name, by_class
    if " - " in t:
        tail = t.rsplit(" - ", 1)[1].strip()
        if tail:
            return name, tail
    return (name,)


def profile_key(data: Mapping[str, Any], viewer: Any) -> str:
    """The name of the viewer's profile in *data*: the first of `profile_names` that *data* has, else the last of
    them (the one a new profile is kept under)."""
    names = profile_names(viewer)
    return next((n for n in names if isinstance(data.get(n), dict)), names[-1])


def page_keys_for(profiles: Any, settings: Any, viewer: Any) -> PageKeys:
    """The keys to press in the viewer *viewer* (its window, `capture.WindowInfo`, or the window's title): its
    profile's, else profiles.json's defaults, else the settings', key by key. *profiles* is a `Profiles` or anything
    with its ``data`` (a dict)."""
    data = getattr(profiles, "data", None)
    data = data if isinstance(data, dict) else {}
    base = default_keys(data, settings)
    if class_key(viewer):  # an image viewer shows files in reading order: the Right arrow is its next page
        base = PageKeys.from_mapping(dict(data.get("default_keys") or {}), BUILTIN_PRESETS["left-to-right"])
    return PageKeys.from_mapping(_keys_in(_entry_of(profiles, viewer).get("keys")), base)


def _entry_of(profiles: Any, viewer: Any) -> dict[str, Any]:
    """The profile of the viewer *viewer* ({} for none); *profiles* and *viewer* as `page_keys_for`."""
    data = getattr(profiles, "data", None)
    entry = data.get(profile_key(data, viewer)) if isinstance(data, dict) and _title_and_class(viewer)[0] else None
    return entry if isinstance(entry, dict) else {}


def margin_key(large: bool) -> str:
    """The name in a viewer's profile of its area on the enlarged window (*large*) or on its window as it was."""
    return "margins_large" if large else "margins"


def own_keys(profiles: Any, viewer: Any) -> dict[str, str]:
    """The keys the viewer's profile sets itself ({} for none: it uses the defaults)."""
    return _keys_in(_entry_of(profiles, viewer).get("keys"))


class Profiles:
    """The capture profiles (``profiles.json``): per viewer its capture areas (`margin_key`) and its keys; beside the
    viewers the default keys and the reader's own presets. Every change is written at once, onto the file as it is then (a change made meanwhile by the command line or an import is
    kept), all or nothing."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: dict[str, Any] = self._read()

    def _read(self) -> dict[str, Any]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _change(self, change: Callable[[dict[str, Any]], None]) -> None:
        """*change* applied to the file as it is now (and to ``data``), and the file written."""
        data = self._read() if self.path.exists() else dict(self.data)
        change(data)
        self.data = data
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            write_atomic(self.path, json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"))
        except OSError:
            pass

    # ---------------------------------------------------------------- the viewers
    # (a viewer is its window, `capture.WindowInfo`, or the window's title: `profile_names`)
    def key_of(self, title: Any) -> str:
        """The name of the viewer's profile (`profile_key`: the one it has, else the one a new one gets)."""
        return profile_key(self.data, title)

    def viewers(self) -> list[str]:
        """The viewers that have a profile (their keys in profiles.json)."""
        return [k for k, v in self.data.items() if k not in RESERVED and isinstance(v, dict)]

    def _entry(self, data: dict[str, Any], key: str) -> dict[str, Any]:
        entry = data.get(key)
        if not isinstance(entry, dict):
            entry = data[key] = {}
        return entry

    @staticmethod
    def _drop_if_empty(data: dict[str, Any], key: str) -> None:
        if isinstance(data.get(key), dict) and not data[key]:
            data.pop(key, None)

    def margins_for(self, title: Any, large: bool = False) -> tuple[int, int, int, int] | None:
        """The viewer's capture area: the one set on its enlarged window with *large*, else on its window as it was."""
        m = _entry_of(self, title).get(margin_key(large))
        if isinstance(m, list) and len(m) == 4:
            return tuple(int(v) for v in m)  # type: ignore[return-value]
        return None

    def set_margins(self, title: Any, margins: tuple[int, int, int, int] | None, large: bool = False) -> None:
        """The viewer's capture area (None: none of its own) on its enlarged window with *large*, else on its window
        as it was; the other area and its keys stay."""
        name = margin_key(large)

        def change(data: dict[str, Any]) -> None:
            key = profile_key(data, title)  # (of the file as it is now)
            if margins is None:
                if isinstance(data.get(key), dict):
                    data[key].pop(name, None)
                    self._drop_if_empty(data, key)
                else:
                    data.pop(key, None)
            else:
                self._entry(data, key)[name] = [int(v) for v in margins]

        self._change(change)

    def own_keys(self, title: Any) -> dict[str, str]:
        """The keys the viewer's profile sets itself ({} for none: it uses the defaults)."""
        return own_keys(self, title)

    def set_keys(self, title: Any, keys: PageKeys | Mapping[str, str] | None) -> None:
        """The viewer's own keys (None: none, it uses the defaults again)."""
        values = keys.as_dict() if isinstance(keys, PageKeys) else _keys_in(keys) if keys is not None else None

        def change(data: dict[str, Any]) -> None:
            key = profile_key(data, title)
            if values is None:
                if isinstance(data.get(key), dict):
                    data[key].pop("keys", None)
                    self._drop_if_empty(data, key)
            else:
                self._entry(data, key)["keys"] = dict(values)

        self._change(change)

    def apply_to_all(self, keys: PageKeys) -> int:
        """*keys* for every viewer: each profile that exists gets them, and so does the defaults entry (every viewer
        without a profile yet). Returns how many viewers' profiles were changed."""
        values = keys.as_dict()
        count = 0

        def change(data: dict[str, Any]) -> None:
            nonlocal count
            for name, entry in data.items():
                if name not in RESERVED and isinstance(entry, dict):
                    entry["keys"] = dict(values)
                    count += 1
            data[DEFAULT_KEYS] = dict(values)

        self._change(change)
        return count

    def default_keys(self, settings: Any) -> PageKeys:
        return default_keys(self.data, settings)

    # ---------------------------------------------------------------- what was seen of the viewer
    def covered_for(self, title: Any) -> bool | None:
        """Whether the viewer draws while other windows hide it wholly, as a session before saw it ("while_covered":
        True for "draws", False for "stops"); None when nothing was seen."""
        seen = _entry_of(self, title).get(COVERED)
        return True if seen == "draws" else False if seen == "stops" else None

    def set_covered(self, title: Any, draws: bool) -> None:
        """What was seen: the viewer draws while covered (*draws*), or only once raised. Written only when it
        changes; the viewer's areas and keys stay."""
        if self.covered_for(title) is draws:
            return

        def change(data: dict[str, Any]) -> None:
            self._entry(data, profile_key(data, title))[COVERED] = "draws" if draws else "stops"

        self._change(change)

    def key_way_for(self, title: Any) -> str:
        """How the viewer took a key passed on, as a session before saw it ("key_way": "real" or "posted"; "" for
        nothing seen)."""
        way = _entry_of(self, title).get(KEY_WAY)
        return way if way in KEY_WAYS else ""

    def set_key_way(self, title: Any, way: str) -> None:
        """What was seen of how the viewer takes a key (*way*: "real" or "posted"; anything else is not kept).
        Written only when it changes."""
        if way not in KEY_WAYS or self.key_way_for(title) == way:
            return

        def change(data: dict[str, Any]) -> None:
            self._entry(data, profile_key(data, title))[KEY_WAY] = way

        self._change(change)

    def keys_for(self, title: Any, settings: Any) -> PageKeys:
        return page_keys_for(self, settings, title)

    # ---------------------------------------------------------------- presets
    def user_presets(self) -> dict[str, PageKeys]:
        """The reader's own presets, by name."""
        presets = self.data.get(KEY_PRESETS)
        if not isinstance(presets, dict):
            return {}
        return {str(n): PageKeys.from_mapping(_keys_in(v)) for n, v in presets.items() if isinstance(v, dict)}

    def presets(self) -> dict[str, PageKeys]:
        """Every preset: the built-in ones first, then the reader's (a reader's preset never hides a built-in)."""
        return {**BUILTIN_PRESETS, **{n: k for n, k in self.user_presets().items() if n not in BUILTIN_PRESETS}}


__all__ = [
    "BUILTIN_PRESETS", "COVERED", "DEFAULT_KEYS", "FILE_TITLE", "KEY_CODES", "KEY_NAMES", "KEY_PRESETS", "KEY_WAY",
    "KEY_WAYS", "KeyWays", "MEANINGS",
    "OPPOSITE_KEYS", "RESERVED", "SETTING_OF", "PageKeys", "Profiles", "ViewerTitle", "class_key",
    "default_keys", "margin_key", "names_a_file", "normal_key", "opposite_key", "own_keys", "page_keys_for",
    "passed_on", "pressed_for", "profile_key", "profile_names", "same_key", "valid_key", "viewer_key", "viewer_title",
]
