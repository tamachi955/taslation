"""The legal notice, with the reader's country and the window's language chosen at its top (`NoticeDialog`), and
whether the start shows it (`notice_due`)."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk

from ... import jurisdictions, notice
from ...i18n import CATALOGS, UI_LANGUAGES, save_ui_language, set_language
from ..layout import fit_combobox, place_window
from ..wrap import wrap_line


def notice_due(state_dir: Path) -> bool:
    """Whether the start shows the legal notice: until the reader ticks "do not show this again" for this
    version, and once more for a reader who has not chosen a country yet."""
    return not notice.dismissed(state_dir) or notice.country(state_dir) is None


class NoticeDialog(tk.Toplevel):
    """The legal notice: the general part and the part for the reader's country (under a heading in bold), with the
    country and the language chosen at its top; the whole dialog speaks the chosen language, at one fixed size for
    every language and country. The text is broken into lines here (`wrap_text`), never inside a run of Latin
    letters and digits such as "TASlation" or "§ 184b". "I understand" saves both and what the box says. At the
    start it comes before the window, and ``accepted`` stays False when the reader quits or closes it (the app does
    not start then); from the Help menu (``startup=False``) it is modal over the window and its second button
    only closes it."""

    def __init__(self, master: tk.Misc, state_dir: Path, language: str | None = None, startup: bool = True):
        super().__init__(master)
        self.state_dir, self.startup = Path(state_dir), startup
        self.accepted = False
        listed = jurisdictions.sorted_jurisdictions()
        self._countries = [j.code for j in listed] + [jurisdictions.OTHER]
        self._names = [j.label() for j in listed]
        country = notice.country(self.state_dir) or notice.default_country() or jurisdictions.OTHER
        self.country = country if country in self._countries else jurisdictions.OTHER
        self.language = language if language in UI_LANGUAGES else self._suggested() or "en"
        self._by_hand = False  # the reader chose the language here: choosing a country no longer changes it
        self._was_dismissed = notice.dismissed(self.state_dir)
        self.resizable(False, False)  # the text is broken into lines for this size
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        # The choosers have fixed widths and stay, with their labels in any language, narrower than the text:
        # choosing a language or a country never changes the dialog's size.
        choosers = ttk.Frame(frm)
        choosers.pack(fill="x", pady=(0, 8))
        self.country_label = ttk.Label(choosers)
        self.country_label.grid(row=0, column=0, sticky="w")
        self.country_box = ttk.Combobox(choosers, state="readonly", height=16)
        fit_combobox(self.country_box, self._names + list(jurisdictions.OTHER_NAMES.values()), max_chars=56)
        self.country_box.grid(row=0, column=1, sticky="w", padx=(6, 0), pady=(0, 4))
        self.country_box.bind("<<ComboboxSelected>>", lambda _e: self._on_country())
        self.language_label = ttk.Label(choosers)
        self.language_label.grid(row=1, column=0, sticky="w")
        self.language_box = ttk.Combobox(choosers, state="readonly", values=list(UI_LANGUAGES.values()), height=16)
        fit_combobox(self.language_box, UI_LANGUAGES.values())
        self.language_box.grid(row=1, column=1, sticky="w", padx=(6, 0))
        self.language_box.bind("<<ComboboxSelected>>", lambda _e: self._on_language())
        row = ttk.Frame(frm)  # packed before the text so that it always shows
        row.pack(side="bottom", fill="x", pady=(10, 0))
        self.never_var = tk.BooleanVar(value=self._was_dismissed)
        self.never_box = ttk.Checkbutton(row, variable=self.never_var)
        self.never_box.pack(side="left")
        self.leave_btn = ttk.Button(row, command=self._quit, padding=(12, 1))
        self.leave_btn.pack(side="right")
        self.ok_btn = ttk.Button(row, default="active", command=self._acknowledge, padding=(12, 1))
        self.ok_btn.pack(side="right", padx=(0, 6))
        body = ttk.Frame(frm)
        body.pack(fill="both", expand=True)
        self._font = tkfont.nametofont("TkDefaultFont")
        self._bold = tkfont.Font(self, font=self._font)
        self._bold.configure(weight="bold")
        self.text = tk.Text(body, width=88, height=31, font=self._font, padx=10, pady=8, wrap="none")
        self.text.tag_configure("heading", font=self._bold)
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.notice_text = ""  # the notice on show, as notice.full_text gives it
        self._render()
        self.protocol("WM_DELETE_WINDOW", self._quit)
        self.bind("<Return>", lambda _e: self._acknowledge())
        if not startup:
            self.transient(master)
            place_window(self, master)
        self.grab_set()
        self.focus_force()

    def _render(self) -> None:
        """Every label in the chosen language, and the notice with the chosen country's part."""
        lang = self.language
        self.title(notice.title(lang))
        self.country_label.configure(text=notice.country_label(lang))
        self.language_label.configure(text=notice.language_label(lang))
        self.country_box.configure(values=self._names + [notice.other_name(lang)])
        self.country_box.current(self._countries.index(self.country))
        self.language_box.current(list(UI_LANGUAGES).index(lang))
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.notice_text = notice.full_text(lang, self.country)
        heading = notice.country_heading(self.country, lang) if hasattr(notice, "country_heading") else None
        self._insert_wrapped(self.notice_text, heading)
        self.text.configure(state="disabled")
        self.text.yview_moveto(0)
        self.never_box.configure(text=notice.checkbox(lang))
        acknowledge, leave = notice.buttons(lang)
        self.ok_btn.configure(text=acknowledge)
        self.leave_btn.configure(text=leave if self.startup else CATALOGS.get(lang, {}).get("Close", "Close"))

    def _insert_wrapped(self, text: str, heading: str | None) -> None:
        """*text* in lines that fit the text box, broken by `wrap_line` (the box itself never wraps, so Tk cannot
        break "TASlation" in two); the line breaks added are tagged "soft", and the
        heading line of the country's part, the line after the first paragraph, is set in bold."""
        width = int(self.text.cget("width")) * self._font.measure("0") - 2
        lines = text.split("\n")
        try:
            blank = lines.index("")
        except ValueError:
            blank = -2
        bold = blank + 1 if heading and blank + 1 < len(lines) and lines[blank + 1] == heading else -1
        for i, line in enumerate(lines):
            tags: tuple[str, ...] = ("heading",) if i == bold else ()
            pieces = wrap_line(line, width, (self._bold if i == bold else self._font).measure)
            for j, piece in enumerate(pieces):
                self.text.insert("end", piece, tags)
                if j < len(pieces) - 1:
                    self.text.insert("end", "\n", ("soft", *tags))
            if i < len(lines) - 1:
                self.text.insert("end", "\n", tags)

    def _suggested(self) -> str | None:
        """The chosen country's first language, when the window speaks it."""
        code = jurisdictions.default_language(self.country)
        return code if code in UI_LANGUAGES else None

    def _on_country(self) -> None:
        index = self.country_box.current()
        if index < 0:
            return
        self.country = self._countries[index]
        if not self._by_hand:
            self.language = self._suggested() or self.language
        self._render()

    def _on_language(self) -> None:
        index = self.language_box.current()
        if index < 0:
            return
        self.language = list(UI_LANGUAGES)[index]
        self._by_hand = True
        self._render()

    def _acknowledge(self) -> None:
        save_ui_language(self.state_dir, self.language)
        notice.save_country(self.state_dir, self.country)
        if self.never_var.get():
            notice.dismiss(self.state_dir, self.language)
        elif self._was_dismissed:  # the box was cleared: the notice shows at the start again
            notice.reset(self.state_dir)
        set_language(self.language)
        self.accepted = True
        self.destroy()

    def _quit(self) -> None:
        self.accepted = False
        self.destroy()
