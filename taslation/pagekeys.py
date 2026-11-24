"""The capture profiles, kept per viewer, and the names of the keys the tools press in their own stand-in viewer.

The capture profiles (`Profiles`, ``profiles.json`` in the state folder; plain JSON, no images, no text of a book)
keep per viewer - the viewer being the window's title without the book's name (`cache.viewer_key_from_title`; for
a title in which no known viewer is found, the text after its last " - ", as an image viewer's title names the file
it shows, and for a window that is no browser's whose title is a file name or a number alone, the window's class:
`profile_names`) - its capture area and what TASlation has seen of it::

    {"<viewer>": {"margins": [0, 85, 0, 0], "while_covered": "draws"}}

"margins" is the area set on the viewer's window (`set_margins`). "while_covered" is what TASlation has seen of a
viewer that is no browser, so that a later session need not find it out again: "draws" when frames of it came while
other windows hid it wholly, "stops" when they came only once it was raised (`covered_for`, `set_covered`; a browser
follows the published rule instead: `capture.covered_by_opaque`).

What versions up to 1.0.1 kept here besides - the page keys passed on to the viewer ("keys", and "default_keys" and
"key_presets" beside the viewers), the area set on a window TASlation had enlarged ("margins_large"), how a viewer took
a key passed on ("key_way"), and older entries still ("fullscreen_reading", "settle_seen") - is left in the file as it
is and ignored: TASlation passes no key on and never enlarges the viewer's window.

`KEY_CODES` names the keys `capture.windows.key_code` knows (the tools press them in their own stand-in viewer:
TASlation itself presses none)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Mapping

from .atomic import write_atomic

KEY_CODES: dict[str, int] = {  # (lower-case) name -> Windows virtual-key code (`capture.windows.key_code`)
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "pageup": 0x21, "pagedown": 0x22, "prior": 0x21, "next": 0x22,
    "home": 0x24, "end": 0x23, "space": 0x20, "enter": 0x0D, "return": 0x0D,
    "escape": 0x1B, "esc": 0x1B, "tab": 0x09, "backspace": 0x08,
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
}
RESERVED = ("default_keys", "key_presets")  # top-level entries of an older profiles.json that are no viewer
COVERED = "while_covered"  # a viewer's profile: "draws" or "stops" while other windows hide it wholly


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


def _entry_of(profiles: Any, viewer: Any) -> dict[str, Any]:
    """The profile of the viewer *viewer* ({} for none); *profiles* is a `Profiles` or anything with its ``data`` (a
    dict), *viewer* a window (`capture.WindowInfo`) or the window's title."""
    data = getattr(profiles, "data", None)
    entry = data.get(profile_key(data, viewer)) if isinstance(data, dict) and _title_and_class(viewer)[0] else None
    return entry if isinstance(entry, dict) else {}


class Profiles:
    """The capture profiles (``profiles.json``): per viewer its capture area and what was seen of it. Every change is
    written at once, onto the file as it is then (a change made meanwhile by the command line or an import is kept),
    all or nothing; what this version does not use stays in the file as it is."""

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
        """The viewers that have a profile."""
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

    def margins_for(self, title: Any) -> tuple[int, int, int, int] | None:
        """The viewer's capture area, None for none of its own."""
        m = _entry_of(self, title).get("margins")
        if isinstance(m, list) and len(m) == 4:
            return tuple(int(v) for v in m)  # type: ignore[return-value]
        return None

    def set_margins(self, title: Any, margins: tuple[int, int, int, int] | None) -> None:
        """The viewer's capture area (None: none of its own); the rest of its profile stays."""

        def change(data: dict[str, Any]) -> None:
            key = profile_key(data, title)  # (of the file as it is now)
            if margins is None:
                if isinstance(data.get(key), dict):
                    data[key].pop("margins", None)
                    self._drop_if_empty(data, key)
                else:
                    data.pop(key, None)
            else:
                self._entry(data, key)["margins"] = [int(v) for v in margins]

        self._change(change)

    # ---------------------------------------------------------------- what was seen of the viewer
    def covered_for(self, title: Any) -> bool | None:
        """Whether the viewer draws while other windows hide it wholly, as a session before saw it ("while_covered":
        True for "draws", False for "stops"); None when nothing was seen."""
        seen = _entry_of(self, title).get(COVERED)
        return True if seen == "draws" else False if seen == "stops" else None

    def set_covered(self, title: Any, draws: bool) -> None:
        """What was seen: the viewer draws while covered (*draws*), or only once raised. Written only when it
        changes; the viewer's area stays."""
        if self.covered_for(title) is draws:
            return

        def change(data: dict[str, Any]) -> None:
            self._entry(data, profile_key(data, title))[COVERED] = "draws" if draws else "stops"

        self._change(change)


__all__ = [
    "COVERED", "FILE_TITLE", "KEY_CODES", "RESERVED", "Profiles", "ViewerTitle", "class_key", "names_a_file",
    "profile_key", "profile_names", "viewer_key", "viewer_title",
]
