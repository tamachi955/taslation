"""The encrypted cache export as the window explains it (the Caches dialog says what the file is for and what an
export or import did, its times in local time; a warning comes before the file dialog of an export or an import and
its Cancel asks for nothing more; the passphrase dialog says what the passphrase is and, as it is typed, what keeps
OK waiting; without the cryptography package both buttons are off and the dialog says why), and the Help menu with
its About dialog. Dialogs on the shared hidden root, never mapped where it can be helped."""
from __future__ import annotations

import gc
import importlib.metadata
import re
import sys
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import taslation
from taslation import backup, cli
from taslation.cache import CacheStore, CachedBubble, CachedPage
from taslation.config import Settings
from taslation.i18n import UI_LANGUAGES, _, set_language
from taslation.ui import app as app_mod
from taslation.ui.dialogs import about, caches
from taslation.ui.dialogs.caches import ERROR_COLOUR, CachesDialog, PassphraseDialog, WarningBox, shown_time
from taslation.ui.shortcuts import key_text

ROOT = Path(__file__).resolve().parents[1]
PASSPHRASE = "correct horse battery staple"
BOOK = "Ein Buch mit Umlauten, Band 2"
MODEL = "qwen3.5:4b"
LANGUAGE = "German"
EXPLAIN = ("Export makes an encrypted backup of the selected book's translations, for yourself or your other computer. "
           "It contains the translated text: never give it to anyone.")
MISSING = "Export and import are not installed. Double-click install.cmd in the TASlation folder."
CHOOSE = ("Choose a passphrase for this backup ({min} characters or more). Without it nobody can open the file, not "
          "even TASlation – keep it safe.")
BEFORE_EXPORT = ("This file will contain the translated text of the book. Keep it for yourself: never give it to "
                 "anyone, post it, or share it. Handing a translation to someone else infringes the author's rights "
                 "even when the book is yours.")
BEFORE_IMPORT = ("Import only a file you made yourself on this or another of your computers. Importing someone else's "
                 "translation is receiving a copy made without permission, and TASlation is built not to pass "
                 "translations between people.")


@pytest.fixture(autouse=True)
def _collected_in_the_main_thread():
    """What a test's dialogs leave in reference cycles is collected right after it, in the main thread: a later
    test's worker thread would collect it otherwise and wait a second for each of their variables and images (Tk
    takes no call from another thread while no main loop runs), long enough to break a test that times its thread."""
    yield
    gc.collect()


def _store(path: Path, *fingerprints: str, book: str = BOOK) -> CacheStore:
    store = CacheStore(path)
    cache = store.open(book, MODEL, LANGUAGE)
    for i, fp in enumerate(fingerprints):
        cache.add(CachedPage(fingerprint=fp, aspect=0.7, seq=i,
                             bubbles=[CachedBubble(box=(0.1, 0.1, 0.3, 0.2), text=f"Line {i}")]))
    cache.save()
    return store


def _texts(widget: tk.Misc) -> list[str]:
    found, stack = [], [widget]
    while stack:
        w = stack.pop()
        if "text" in w.keys():
            found.append(str(w.cget("text")))
        stack.extend(w.winfo_children())
    return found


def _shows(label, text: str, width: int) -> bool:
    """Whether *label* shows *text* broken into lines that fit *width* (the breaks and the spaces at them aside)."""
    shown = str(label.cget("text"))
    font = tkfont.nametofont("TkDefaultFont")
    same = shown.replace("\n", "").replace(" ", "") == text.replace(" ", "")
    return same and all(font.measure(line) <= width for line in shown.split("\n"))


# ------------------------------------------------------------------ times and the passphrase's length
def test_the_lists_show_times_in_local_time_to_the_minute():
    assert shown_time("2026-10-30T14:05:09") == "2026-10-30 14:05"  # as TASlation writes them: local, no zone
    utc = datetime(2026, 10, 30, 5, 5, 9, tzinfo=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    assert shown_time("2026-10-30T05:05:09+00:00") == utc == shown_time("2026-10-30T05:05:09Z")
    for odd in ("", "not a time", "0001-01-01T00:00:00+00:00"):  # shown as they are, never an error
        assert shown_time(odd) == odd
    assert shown_time(None) == "None"


def test_the_passphrase_is_counted_as_the_key_sees_it():
    assert backup.passphrase_length("twelve chars") == 12
    assert backup.passphrase_length("cafe\u0301 au lai") == 11 < len("cafe\u0301 au lai")  # é typed in two parts
    assert backup.passphrase_length("\U0001f642" * 3) == 3  # outside the BMP, whole or as two halves
    assert backup.passphrase_length("\ud83d\ude42" * 3) == 3
    assert backup.passphrase_length("ab\u3000cd") == 5  # a full-width space is one space
    with pytest.raises(backup.BrokenPassphrase):
        backup.passphrase_length("a tab\there")
    with pytest.raises(backup.BackupError, match="at least 12"):
        backup.check_passphrase("cafe\u0301 au lai")  # 12 as typed, 11 for the key


# ------------------------------------------------------------------ the passphrase dialog
def test_the_export_passphrase_dialog_says_what_keeps_ok_waiting(hidden_root):
    d = PassphraseDialog(hidden_root, confirm=True)
    ok = lambda: str(d.ok_btn.cget("state")) == "normal"  # noqa: E731
    assert d.intro_text == CHOOSE.format(min=backup.MIN_PASSPHRASE) and _shows(d.intro, d.intro_text, d.intro_width)
    assert d.hint_var.get() == "" and not ok()  # nothing typed: nothing said yet
    assert str(d.hint.cget("foreground")) == ERROR_COLOUR
    d.vars[0].set("hello")
    assert d.hint_var.get() == "Too short (5 of 12)" and not ok()
    d.vars[0].set("cafe\u0301 au lai")  # 12 as typed, 11 as the key counts
    assert d.hint_var.get() == "Too short (11 of 12)"
    d.vars[0].set(PASSPHRASE)
    assert d.hint_var.get() == "" and not ok()  # the second one not typed yet
    d.vars[1].set("correct horse")
    assert d.hint_var.get() == "" and not ok()  # still being typed, and so far the same
    d.vars[1].set("correct horsa")
    assert d.hint_var.get() == "The two passphrases differ" and not ok()  # a typo: said at once
    d.vars[1].set(PASSPHRASE + "s")
    assert d.hint_var.get() == "The two passphrases differ" and not ok()  # longer than the first
    d.vars[1].set(PASSPHRASE)
    assert d.hint_var.get() == "" and ok()  # all is well: the line says nothing
    d.vars[0].set("a tab\tin a long passphrase")
    assert d.hint_var.get() == _("The passphrase holds a broken or control character; type it again.") and not ok()
    d.destroy()


def test_ok_on_an_empty_dialog_says_why_and_show_unmasks_both_fields(hidden_root):
    d = PassphraseDialog(hidden_root, confirm=True)
    d._ok()
    assert d.passphrase is None and d.winfo_exists() and d.hint_var.get() == "Too short (0 of 12)"
    d.vars[0].set(PASSPHRASE)
    d._ok()
    assert d.passphrase is None and d.hint_var.get() == "The two passphrases differ"
    assert [str(e.cget("show")) for e in d.entries] == ["*", "*"] and str(d.show_box.cget("text")) == "Show"
    d.show_box.invoke()
    assert d.show_var.get() and [str(e.cget("show")) for e in d.entries] == ["", ""]
    d.show_box.invoke()
    assert [str(e.cget("show")) for e in d.entries] == ["*", "*"]
    d.vars[1].set(PASSPHRASE)
    d._ok()
    assert d.passphrase == PASSPHRASE


def test_the_import_passphrase_dialog(hidden_root):
    d = PassphraseDialog(hidden_root, confirm=False)
    assert d.intro_text == "Type the passphrase this backup was made with." and len(d.entries) == 1
    assert _shows(d.intro, d.intro_text, d.intro_width)
    d.vars[0].set("short")
    assert d.hint_var.get() == "Too short (5 of 12)" and str(d.ok_btn.cget("state")) == "disabled"
    d.show_box.invoke()
    assert str(d.entries[0].cget("show")) == ""
    d.vars[0].set(PASSPHRASE)
    assert d.hint_var.get() == "" and str(d.ok_btn.cget("state")) == "normal"
    d.destroy()


def test_the_passphrase_dialog_in_japanese(hidden_root):
    set_language("ja")
    d = PassphraseDialog(hidden_root, confirm=True)
    assert d.intro_text == ("このバックアップのパスフレーズを決めてください（12文字以上）。パスフレーズがないと "
                            "TASlation でもファイルを開けないので、大切に保管してください。")
    assert _shows(d.intro, d.intro_text, d.intro_width) and "TASlation" in str(d.intro.cget("text"))  # never split
    lines = str(d.intro.cget("text")).split("\n")
    font = tkfont.nametofont("TkDefaultFont")
    assert len(lines) > 1 and all(font.measure(line) > d.intro_width * 0.6 for line in lines[:-1])  # filled lines
    d.vars[0].set("abcde")
    assert d.hint_var.get() == "短すぎます（12文字中5文字）"
    d.vars[0].set(PASSPHRASE)
    d.vars[1].set(PASSPHRASE + "!")
    assert d.hint_var.get() == "2つのパスフレーズが一致しません"
    d.destroy()


# ------------------------------------------------------------------ the Caches dialog
def test_the_caches_dialog_says_what_an_export_is_and_what_export_and_import_did(tmp_path, monkeypatch, hidden_root):
    pytest.importorskip("cryptography")
    monkeypatch.setitem(backup.KDF, "n", 2 ** 14)  # a cheaper key
    home = _store(tmp_path / "home", "a" * 80, "b" * 80)
    other = _store(tmp_path / "other", "c" * 80, book="Another book")
    out = tmp_path / "picked.stcache"
    monkeypatch.setattr(CachesDialog, "_before", lambda _self, title, text: True)  # the warning: Continue
    monkeypatch.setattr(caches.filedialog, "asksaveasfilename", lambda **_k: str(out))
    monkeypatch.setattr(caches.filedialog, "askopenfilename", lambda **_k: str(out))
    monkeypatch.setattr(CachesDialog, "_passphrase", lambda _self, confirm: PASSPHRASE)
    statuses: list[str] = []
    d = CachesDialog(hidden_root, home, on_status=statuses.append)
    d.withdraw()
    explain = next(label for label in d._explanations if str(label.cget("text")) == EXPLAIN)
    order = d._frame.pack_slaves()
    assert order.index(explain) < order.index(d.export_btn.master) < order.index(d.backup_line)  # above the buttons
    assert d.backup_var.get() == "" and str(d.import_btn.cget("state")) == "normal"
    item = d.tree.get_children()[0]
    entry = d._entries[item]
    assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d", d.tree.set(item, "updated"))
    assert d.tree.set(item, "updated") == shown_time(entry["updated"]) != entry["updated"]
    d.tree.selection_set(item)
    d._sync_buttons()
    d._export()
    assert out.is_file() and d.backup_var.get() == f"Exported 2 page(s) of {BOOK} to picked.stcache."
    assert str(d.backup_line.cget("foreground")) == ""  # not a warning
    assert statuses[-1] == f"Exported {BOOK} to {out}"  # the window's status bar as before
    assert d._selected()["file"] == entry["file"]  # the list filled again, the cache still selected
    d.destroy()

    changed: list[str] = []
    d = CachesDialog(hidden_root, other, on_changed=changed.append, on_status=statuses.append)
    d.withdraw()
    assert [d._entries[i]["book"] for i in d.tree.get_children()] == ["Another book"]
    d._import()
    assert d.backup_var.get() == f"Imported 2 page(s) of {BOOK} from picked.stcache."
    assert sorted(d._entries[i]["book"] for i in d.tree.get_children()) == sorted(["Another book", BOOK])
    assert d._selected()["book"] == BOOK and changed == [BOOK]  # the list refreshed, the book's cache selected
    warnings: list[str] = []
    monkeypatch.setattr(caches, "tell", lambda _parent, text, **_k: warnings.append(text))
    monkeypatch.setattr(CachesDialog, "_passphrase", lambda _self, confirm: "not the passphrase")
    d._import()
    assert warnings == ["Wrong passphrase or damaged file."] == [d.backup_var.get()] == statuses[-1:]
    assert str(d.backup_line.cget("foreground")) == ERROR_COLOUR
    d.destroy()


def test_the_caches_dialog_in_japanese_explains_the_export(tmp_path, hidden_root):
    set_language("ja")
    d = CachesDialog(hidden_root, _store(tmp_path / "cache", "a" * 80))
    d.withdraw()
    assert ("書き出しは、選んだ本の訳文をパスフレーズで暗号化したバックアップです。自分用の控えや別のパソコンへの移行に使います。"
            "訳文が入っているので、他人には決して渡さないでください。") in _texts(d)
    d.destroy()


# ------------------------------------------------------------------ the warning before an export or an import
def _answering(monkeypatch, answer: bool, asked: list) -> tuple[list[WarningBox], list[tuple[str, ...]]]:
    """The real warning box for the Caches dialog, never on the screen, answered (Continue or Cancel) as soon as the
    dialog waits for it. Returns the boxes made and what each showed: title, text, buttons."""
    boxes: list[WarningBox] = []
    seen: list[tuple[str, ...]] = []

    class Answered(WarningBox):
        def __init__(self, master, title, text):
            super().__init__(master, title, text)
            self.withdraw()
            boxes.append(self)
            seen.append((self.title(), self.message_text, str(self.continue_btn.cget("text")),
                         str(self.cancel_btn.cget("text"))))
            asked.append("warning")
            self.after_idle((self.continue_btn if answer else self.cancel_btn).invoke)

    monkeypatch.setattr(caches, "WarningBox", Answered)
    return boxes, seen


def test_the_warning_box_shows_the_icon_and_the_text_and_waits_for_continue_or_cancel(monkeypatch, hidden_root):
    placed, focused = [], []
    monkeypatch.setattr(caches, "place_window", lambda win, parent=None: placed.append((win, parent)))
    # Tk gives an unmapped window the focus once it maps, so where it goes is seen as it is asked for
    monkeypatch.setattr(caches.ttk.Button, "focus_set", lambda self: focused.append(self))
    parent = tk.Toplevel(hidden_root)  # the Caches dialog
    parent.withdraw()

    def box() -> WarningBox:
        made = WarningBox(parent, "Before exporting", BEFORE_EXPORT)
        made.withdraw()
        return made

    b = box()
    assert placed == [(b, parent)] and focused == [b.continue_btn]  # centred over the Caches dialog, Continue focused
    assert b.title() == "Before exporting" and b.resizable() == (False, False) and str(b.transient()) == str(parent)
    assert [str(name) for name in b.icon.cget("image")] == [caches.WARNING_ICON]  # the icon of Tk's warning boxes
    assert b.message_text == BEFORE_EXPORT and _shows(b.message, BEFORE_EXPORT, b.text_width)
    assert str(b.message.cget("text")).count("\n") >= 2  # a paragraph, not one long line
    assert [str(w.cget("text")) for w in (b.continue_btn, b.cancel_btn)] == ["Continue", "Cancel"]
    assert b.continue_btn.master.pack_slaves() == [b.cancel_btn, b.continue_btn]  # Cancel on the right
    assert str(b.continue_btn.cget("default")) == "active" and b.answer is False
    b.continue_btn.invoke()
    assert b.answer is True and not b.winfo_exists()
    b = box()
    b.cancel_btn.invoke()
    assert b.answer is False and not b.winfo_exists()
    b = box()
    assert "_cancel" in b.bind("<Escape>") and "_on_return" in b.bind("<Return>")
    hidden_root.tk.eval(b.protocol("WM_DELETE_WINDOW"))  # the box's close button
    assert b.answer is False and not b.winfo_exists()
    b = box()
    b._on_return()  # Return while Continue has the focus, as it has from the start
    assert b.answer is True and not b.winfo_exists()
    b = box()
    monkeypatch.setattr(b, "focus_get", lambda: b.cancel_btn)  # the reader moved the focus to Cancel
    b._on_return()
    assert b.answer is False and not b.winfo_exists()
    parent.destroy()


@pytest.mark.parametrize("code", sorted(UI_LANGUAGES))
def test_both_warnings_fit_their_box_in_every_language(hidden_root, code):
    set_language(code)
    parent = tk.Toplevel(hidden_root)
    parent.withdraw()
    for title, text in ((_("Before exporting"), _(BEFORE_EXPORT)), (_("Before importing"), _(BEFORE_IMPORT))):
        b = WarningBox(parent, title, text)
        b.withdraw()
        shown = str(b.message.cget("text"))
        assert _shows(b.message, text, b.text_width), (code, title)
        assert "TASlation" in shown or "TASlation" not in text  # never broken inside the name
        assert len(shown.split("\n")) >= 2 and b.title() == title
        b.destroy()
    parent.destroy()


@pytest.mark.parametrize("answer", [False, True], ids=["cancel", "continue"])
def test_the_warning_comes_before_the_file_dialog_and_cancel_asks_for_nothing_more(tmp_path, monkeypatch, hidden_root,
                                                                                    answer):
    pytest.importorskip("cryptography")
    monkeypatch.setitem(backup.KDF, "n", 2 ** 14)  # a cheaper key
    home = _store(tmp_path / "home", "a" * 80, "b" * 80)
    other = _store(tmp_path / "other", "c" * 80, book="Another book")
    out = tmp_path / "picked.stcache"
    asked: list[str] = []
    boxes, seen = _answering(monkeypatch, answer, asked)
    placed = []
    monkeypatch.setattr(caches, "place_window", lambda win, parent=None: placed.append((win, parent)))
    monkeypatch.setattr(caches.filedialog, "asksaveasfilename", lambda **_k: asked.append("save") or str(out))
    monkeypatch.setattr(caches.filedialog, "askopenfilename", lambda **_k: asked.append("open") or str(out))
    monkeypatch.setattr(CachesDialog, "_passphrase", lambda _self, confirm: asked.append("passphrase") or PASSPHRASE)
    statuses: list[str] = []
    d = CachesDialog(hidden_root, home, on_status=statuses.append)
    d.withdraw()
    d.tree.selection_set(d.tree.get_children()[0])
    d._sync_buttons()
    d._export()
    assert seen == [("Before exporting", BEFORE_EXPORT, "Continue", "Cancel")] and (boxes[0], d) in placed
    if answer:
        assert asked == ["warning", "save", "passphrase"] and out.is_file()  # the warning first, then the file
        assert d.backup_var.get() == f"Exported 2 page(s) of {BOOK} to picked.stcache."
    else:
        assert asked == ["warning"] and not out.exists()  # Cancel: no file dialog, no passphrase, nothing written
        assert d.backup_var.get() == "" and statuses == []  # and nothing else changes
    d.destroy()

    asked.clear()
    files = {p.name: p.read_bytes() for p in other.cache_dir.iterdir()}
    changed: list[str] = []
    d = CachesDialog(hidden_root, other, on_changed=changed.append, on_status=statuses.append)
    d.withdraw()
    d._import()
    assert seen[1:] == [("Before importing", BEFORE_IMPORT, "Continue", "Cancel")] and (boxes[1], d) in placed
    if answer:
        assert asked == ["warning", "open", "passphrase"] and changed == [BOOK]
        assert d.backup_var.get() == f"Imported 2 page(s) of {BOOK} from picked.stcache."
    else:
        assert asked == ["warning"] and changed == [] and d.backup_var.get() == "" and statuses == []
        assert {p.name: p.read_bytes() for p in other.cache_dir.iterdir()} == files  # nothing imported
    d.destroy()
    assert cli.EXPORT_NOTE == "Note: " + BEFORE_EXPORT and cli.IMPORT_NOTE == "Note: " + BEFORE_IMPORT  # the same words


def test_the_warnings_speak_the_windows_language(tmp_path, monkeypatch, hidden_root):
    pytest.importorskip("cryptography")
    asked: list[str] = []
    _boxes, seen = _answering(monkeypatch, False, asked)
    monkeypatch.setattr(caches.filedialog, "asksaveasfilename", lambda **_k: asked.append("save") or "")
    monkeypatch.setattr(caches.filedialog, "askopenfilename", lambda **_k: asked.append("open") or "")
    set_language("ja")
    d = CachesDialog(hidden_root, _store(tmp_path / "cache", "a" * 80))
    d.withdraw()
    d.tree.selection_set(d.tree.get_children()[0])
    d._sync_buttons()
    d._export()
    d._import()
    assert seen == [
        ("書き出しの前に", "このファイルには本の訳文が入ります。自分だけで使ってください。他人に渡す、公開する、共有することは、"
                    "本が自分のものであっても著作権の侵害になります。", "続ける", "キャンセル"),
        ("取り込みの前に", "自分がこのパソコンや自分の別のパソコンで作ったファイルだけを取り込んでください。他人の訳文を取り込むことは、"
                    "無断で作られた複製を受け取ることになります。TASlation は人から人へ訳文を渡さない前提で作られています。",
         "続ける", "キャンセル")]
    assert asked == ["warning", "warning"]  # Cancel both times: no file dialog
    d.destroy()
    set_language("en")


def test_without_cryptography_export_and_import_are_off_and_the_dialog_says_why(tmp_path, monkeypatch, hidden_root):
    monkeypatch.setitem(sys.modules, "cryptography.hazmat.primitives.ciphers.aead", None)  # the import fails
    with pytest.raises(backup.LibraryMissing):
        backup.require()
    store = _store(tmp_path / "cache", "a" * 80)
    asked: list[str] = []
    monkeypatch.setattr(CachesDialog, "_before", lambda _self, title, text: asked.append("warning"))
    monkeypatch.setattr(caches.filedialog, "asksaveasfilename", lambda **_k: asked.append("save") or "")
    monkeypatch.setattr(caches.filedialog, "askopenfilename", lambda **_k: asked.append("open") or "")
    monkeypatch.setattr(CachesDialog, "_passphrase", lambda _self, confirm: asked.append("passphrase"))
    for code, text in (("en", MISSING), ("ja", "エクスポートとインポートはインストールされていません。TASlation フォルダーの install.cmd をダブルクリックしてください。"),
                       ("de", "Export und Import sind nicht installiert. Doppelklicken Sie auf install.cmd im TASlation-Ordner.")):
        set_language(code)
        d = CachesDialog(hidden_root, store)
        d.withdraw()
        assert d.backup_var.get() == text and str(d.backup_line.cget("foreground")) == ERROR_COLOUR  # from the start
        assert str(d.export_btn.cget("state")) == "disabled" and str(d.import_btn.cget("state")) == "disabled"
        item = d.tree.get_children()[0]
        d.tree.selection_set(item)
        d._sync_buttons()
        assert str(d.export_btn.cget("state")) == "disabled"
        d._export()
        d._import()
        assert asked == []  # no warning, and neither a file nor a passphrase is asked for
        d.destroy()
    set_language("en")


def test_the_package_gone_after_the_dialog_opened_is_said_in_the_windows_language(tmp_path, monkeypatch, hidden_root):
    pytest.importorskip("cryptography")
    store = _store(tmp_path / "cache", "a" * 80)
    monkeypatch.setattr(CachesDialog, "_before", lambda _self, title, text: True)
    monkeypatch.setattr(caches.filedialog, "asksaveasfilename", lambda **_k: str(tmp_path / "x.stcache"))
    monkeypatch.setattr(CachesDialog, "_passphrase", lambda _self, confirm: PASSPHRASE)
    warnings: list[str] = []
    monkeypatch.setattr(caches, "tell", lambda _parent, text, **_k: warnings.append(text))
    set_language("ru")
    d = CachesDialog(hidden_root, store)
    d.withdraw()
    d.tree.selection_set(d.tree.get_children()[0])
    d._sync_buttons()
    monkeypatch.setitem(sys.modules, "cryptography.hazmat.primitives.ciphers.aead", None)
    d._export()
    said = "Экспорт и импорт не установлены. Дважды щёлкните install.cmd в папке TASlation."
    assert warnings == [said] == [d.backup_var.get()] and not (tmp_path / "x.stcache").exists()
    assert str(d.export_btn.cget("state")) == "disabled" and str(d.import_btn.cget("state")) == "disabled"
    d.destroy()
    set_language("en")


# ------------------------------------------------------------------ the Help menu and About
class Menus(tk.Toplevel):
    """The App's menu bar on a withdrawn window, each command recording its name."""

    _build_menus = app_mod.App._build_menus

    def __init__(self, root):
        super().__init__(root)
        self.withdraw()
        self.calls: list[str] = []
        self.role_var, self.ui_lang_var = tk.StringVar(self, value="reader"), tk.StringVar(self, value="en")
        for name in ("auto_var", "original_var", "top_var", "over_var", "order_numbers_var"):
            setattr(self, name, tk.BooleanVar(self))


def _recorder(name: str):
    def record(self, *_args, **_kwargs):
        self.calls.append(name)

    return record


for _name in ("translate_now", "set_area", "clear_area", "open_page_keys",
              "open_batch_dialog", "stop_batch", "open_glossary", "open_caches", "_on_role_changed",
              "toggle_order", "toggle_skip", "retranslate_page",
              "open_book_settings", "open_review", "open_find_replace", "undo_edit", "redo_edit", "_redisplay", "_apply_on_top",
              "_on_ui_language", "open_help", "open_keys", "open_notice", "open_about", "toggle_over", "review_names",
              "open_settings"):
    setattr(Menus, _name, _recorder(_name))


def _cascades(menubar: tk.Menu) -> dict[str, tk.Menu]:
    return {str(menubar.entrycget(i, "label")): menubar.nametowidget(menubar.entrycget(i, "menu"))
            for i in range(int(menubar.index("end")) + 1) if menubar.type(i) == "cascade"}


def _entries(menu: tk.Menu) -> list[tuple[str, str]]:
    return [(menu.type(i), str(menu.entrycget(i, "label")) if menu.type(i) != "separator" else "")
            for i in range(int(menu.index("end")) + 1)]


def _invoke(w: Menus, menu: tk.Menu, label: str) -> str:
    w.calls.clear()
    menu.invoke(next(i for i in range(int(menu.index("end")) + 1)
                     if menu.type(i) != "separator" and str(menu.entrycget(i, "label")) == label))
    return w.calls[-1]


@pytest.mark.parametrize("code", ["en", "ja", "de"])
def test_the_help_menu_comes_after_language_and_alone_has_the_notice(hidden_root, code):
    set_language(code)
    w = Menus(hidden_root)
    w._build_menus()
    menus = _cascades(w.menubar)
    assert list(menus)[-2:] == [_("Language"), _("Help")]
    help_menu = menus[_("Help")]
    assert _entries(help_menu) == [("command", _("How to use...")), ("command", _("Keys...")),
                                   ("command", _("Legal notice...")), ("separator", ""), ("command", _("About TASlation"))]
    assert str(help_menu.entrycget(0, "accelerator")) == "F1"
    assert str(help_menu.entrycget(1, "accelerator")) == key_text("Shift-F1")  # Umschalt+F1 in German
    assert _invoke(w, help_menu, _("Keys...")) == "open_keys"
    assert _invoke(w, help_menu, _("Legal notice...")) == "open_notice"
    assert all(_("Legal notice...") != label
               for name in (_("Language"), _("View")) for _kind, label in _entries(menus[name]))
    assert ("separator", "") not in _entries(menus[_("Language")]) + _entries(menus[_("View")])
    assert _invoke(w, help_menu, _("About TASlation")) == "open_about"
    if code == "ja":
        assert _("Help") == "ヘルプ" and _("About TASlation") == "TASlation について"
    w.destroy()
    set_language("en")


def test_help_about_opens_with_the_state_folder_the_ollama_port_and_the_guard(tmp_path, monkeypatch):
    made = []
    monkeypatch.setattr(about, "AboutDialog", lambda master, state_dir, port, guard: made.append((master, state_dir, port, guard)))
    window = SimpleNamespace(settings=Settings(state_dir=tmp_path / "state", ollama_url="http://127.0.0.1:11500"),
                             _guard_line=lambda: "Offline guard: off.")
    app_mod.App.open_about(window)
    assert made == [(window, tmp_path / "state", 11500, "Offline guard: off.")]


def test_the_about_dialog(tmp_path, monkeypatch, hidden_root):
    placed = []
    monkeypatch.setattr(about, "place_window", lambda win, parent=None: placed.append((win, parent)))
    state = tmp_path / "state folder"
    d = about.AboutDialog(hidden_root, state, port=11434, root=ROOT)
    d.withdraw()
    assert placed == [(d, hidden_root)]  # centred over the window
    assert d.title() == "About TASlation" and d.resizable() == (False, False)
    assert d.version_text == f"Version {importlib.metadata.version('taslation')}" and d.version_text in _texts(d)
    assert d.lines == ["Free software under the MIT licence", "Built with PLaMo",
                       "Runs offline: it talks only to Ollama on this computer (localhost:11434)",
                       "Your translations, notes and settings are kept in this folder:",
                       "More in the README and in docs/THIRD_PARTY.md (the projects TASlation uses and their licences):"]
    assert all(_shows(label, text, d.text_width) for label, text in zip(d._labels, d.lines))
    assert d.paths == [str(state), str(ROOT / "README.md"), str(ROOT / "docs" / "THIRD_PARTY.md")]
    assert [field.get() for field in d._fields] == d.paths  # each path in a line of its own ...
    assert all(str(field.cget("state")) == "readonly" for field in d._fields)  # ... selectable, never edited
    source = Path(about.__file__).read_text(encoding="utf-8")
    assert "webbrowser" not in source and "startfile" not in source  # nothing opens a browser or a file
    d.destroy()
    assert about.documents(tmp_path) == []  # an installed package without the source: the sentence names them
    d = about.AboutDialog(hidden_root, state, root=tmp_path, guard="Offline guard: off.")
    assert d.paths == [str(state)]
    assert d.lines[2:4] == ["Runs offline: it talks only to Ollama on this computer (localhost:11434)", "Offline guard: off."]
    d.destroy()


def test_the_version_comes_from_the_installed_package_or_the_source(monkeypatch):
    assert about.version() == importlib.metadata.version("taslation")

    def missing(_name):
        raise importlib.metadata.PackageNotFoundError(_name)

    monkeypatch.setattr(about.importlib.metadata, "version", missing)
    assert about.version() == taslation.__version__


def test_the_about_dialog_in_japanese_and_russian(tmp_path, hidden_root):
    for code, sentence in (("ja", "オフラインで動作します。通信するのはこのパソコンの Ollama（localhost:11434）だけです"),
                           ("ru", "Работает офлайн: обращается только к Ollama на этом компьютере (localhost:11434)")):
        set_language(code)
        d = about.AboutDialog(hidden_root, tmp_path, root=ROOT)
        d.withdraw()
        assert sentence in d.lines and d.title() == _("About TASlation") != "About TASlation"
        assert all(_shows(label, text, d.text_width) for label, text in zip(d._labels, d.lines))
        assert _("Close") in _texts(d)
        d.destroy()
    set_language("en")
