"""Page > Page keys...: the keys a page key pressed in TASlation's window is passed on to the chosen viewer as
(`pagekeys.passed_on`: the window's next and previous keys as these, a key of the viewer's own as it is, one press one
key), with the two reading directions that set both at once. Nothing is pressed in the viewer from here."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from ...i18n import _
from ...pagekeys import BUILTIN_PRESETS, KEY_NAMES, MEANINGS, PageKeys, normal_key, page_keys_for, same_key, valid_key
from ..banner import break_lines
from ..layout import place_window
from ..tooltip import tip
from .caches import ERROR_COLOUR

PRESET_LABELS = {  # the built-in presets as the dialog names them
    "right-to-left": "Right-to-left reading: Left arrow turns to the next page",
    "left-to-right": "Left-to-right reading: Right arrow turns to the next page",
}
FIELD_LABELS = {
    "next": "Next page",
    "prev": "Previous page",
}
WRAP_PX = 560  # the dialog's long lines wrap at this width


def check_keys(values: dict[str, str]) -> tuple[PageKeys | None, str]:
    """The keys of the dialog's fields (*values*: next, prev -> the text typed), or None and
    what is wrong with them in the window's language."""
    keys = {m: normal_key(values.get(m, "")) for m in MEANINGS}
    if not keys["next"] or not keys["prev"]:
        return None, _("The next page and the previous page need a key each.")
    for m in MEANINGS:
        if not valid_key(keys[m]):
            return None, _("Unknown key name: {key}. Use one of the names listed above.").format(key=keys[m])
    if same_key(keys["next"], keys["prev"]):
        return None, _("The next page and the previous page cannot have the same key.")
    return PageKeys(**keys), ""


class PageKeysDialog(tk.Toplevel):
    """Page keys of the viewer whose window has the title *title*: the two built-in directions (choosing one fills the
    fields; other presets are the command line's, `taslation keys`), and the keys - next page, previous page.
    "Apply to this viewer" keeps them in the viewer's profile, "Apply
    to all viewers" in every viewer's profile and as the defaults of the viewers without one (`Profiles.apply_to_all`),
    "Reset to the defaults" drops the viewer's own keys; *on_saved* follows each of them."""

    def __init__(self, master: tk.Misc, title: str, profiles: Any, settings: Any,
                 on_saved: Callable[[], None] | None = None):
        super().__init__(master)
        self.title(_("Page keys"))
        self.transient(master)
        self.resizable(False, False)
        self.viewer_title = title
        self.profiles = profiles
        self.settings = settings
        self.on_saved = on_saved
        self.saved = False  # one of the Apply buttons (or Reset) changed the profiles
        keys = page_keys_for(profiles, settings, title)
        self.vars = {m: tk.StringVar(self, value=getattr(keys, m)) for m in MEANINGS}
        self.preset_var = tk.StringVar(self, value="")
        self.error_var = tk.StringVar(self, value="")

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        label = ttk.Label(frm, justify="left")
        label.configure(text=break_lines(_("Viewer: {title}").format(title=title), WRAP_PX, label))
        label.pack(anchor="w")
        self.source_label = ttk.Label(frm, text=self._source_words())
        self.source_label.pack(anchor="w", pady=(2, 0))

        box = ttk.LabelFrame(frm, text=_("Presets"), padding=8)
        box.pack(fill="x", pady=(10, 0))
        self.preset_frame = ttk.Frame(box)
        self.preset_frame.pack(fill="x")
        self._build_presets()

        grid = ttk.Frame(frm)
        grid.pack(fill="x", pady=(10, 0))
        for i, m in enumerate(MEANINGS):
            ttk.Label(grid, text=_(FIELD_LABELS[m])).grid(row=i, column=0, sticky="w", pady=2)
            ttk.Entry(grid, textvariable=self.vars[m], width=12).grid(row=i, column=1, sticky="w", padx=(6, 0))
        ttk.Label(frm, justify="left", wraplength=WRAP_PX, text=_("Key names: {names}.").format(
            names=", ".join(KEY_NAMES))).pack(anchor="w", pady=(6, 0))
        ttk.Label(frm, textvariable=self.error_var, foreground=ERROR_COLOUR, wraplength=WRAP_PX).pack(anchor="w",
                                                                                                    pady=(6, 0))

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(8, 0))
        button = ttk.Button(btns, text=_("Reset to the defaults"), command=self.reset)
        button.pack(side="left")
        tip(_("Drop this viewer's own keys and use the default keys."), button)
        ttk.Button(btns, text=_("Cancel"), command=self.destroy).pack(side="right")
        button = ttk.Button(btns, text=_("Apply to all viewers"), command=self.apply_all)
        button.pack(side="right", padx=(0, 6))
        tip(_("Use these keys in every viewer."), button)
        button = ttk.Button(btns, text=_("Apply to this viewer"), command=self.apply)
        button.pack(side="right", padx=(0, 6))
        tip(_("Keep these keys for this viewer."), button)
        for var in self.vars.values():
            var.trace_add("write", lambda *_a: self._match_preset())
        self._match_preset()
        self.bind("<Escape>", lambda _e: self.destroy())
        place_window(self, master)

    # ---------------------------------------------------------------- presets
    def _source_words(self) -> str:
        return _("This viewer has keys of its own.") if self.profiles.own_keys(self.viewer_title) else ""

    def _build_presets(self) -> None:
        """A radio button for each of the two directions."""
        self.presets = BUILTIN_PRESETS
        for name in self.presets:
            ttk.Radiobutton(self.preset_frame, text=_(PRESET_LABELS[name]), value=name, variable=self.preset_var,
                            command=lambda name=name: self.choose(name)).pack(anchor="w")

    def _match_preset(self) -> None:
        """The preset the fields hold now, chosen (none when they hold no preset's keys)."""
        values = {m: normal_key(v.get()) for m, v in self.vars.items()}
        found = next((n for n, k in self.presets.items() if all(same_key(values[m], getattr(k, m))
                                                               or values[m] == getattr(k, m) for m in MEANINGS)), "")
        if self.preset_var.get() != found:
            self.preset_var.set(found)

    def choose(self, name: str) -> None:
        """A preset chosen: its keys fill the fields."""
        keys = self.presets.get(name)
        if keys is None:
            return
        for m in MEANINGS:
            self.vars[m].set(getattr(keys, m))
        self.preset_var.set(name)
        self.error_var.set("")

    # ---------------------------------------------------------------- the keys
    def values(self) -> dict[str, str]:
        return {m: v.get() for m, v in self.vars.items()}

    def _checked(self) -> PageKeys | None:
        keys, error = check_keys(self.values())
        self.error_var.set(error)
        return keys

    def _done(self, close: bool = True) -> None:
        self.saved = True
        if self.on_saved is not None:
            self.on_saved()
        if close:
            self.destroy()

    def apply(self) -> None:
        """Apply to this viewer: the keys kept in the viewer's profile."""
        keys = self._checked()
        if keys is None:
            return
        self.profiles.set_keys(self.viewer_title, keys)
        self._done()

    def apply_all(self) -> None:
        """Apply to all viewers: the keys in every viewer's profile and as the defaults (profiles.json's
        "default_keys", above the settings')."""
        keys = self._checked()
        if keys is None:
            return
        self.profiles.apply_to_all(keys)
        self._done()

    def reset(self) -> None:
        """Reset to the defaults: the viewer's own keys dropped (it uses the defaults again, which fill the
        fields); the dialog stays open."""
        self.profiles.set_keys(self.viewer_title, None)
        keys = self.profiles.default_keys(self.settings)
        for m in MEANINGS:
            self.vars[m].set(getattr(keys, m))
        self.error_var.set("")
        self.source_label.configure(text=self._source_words())
        self._done(close=False)
