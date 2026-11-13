"""The window's offer of the translator model a language needs (`ui.model_switch`): the question in plain words (the
size to download, the room freed), PLaMo's licence agreed to first, a model the person had before asked about on its
own with keeping it the default, the language put back after a no, the setup check's ``translator.model_missing``
leading to the offer once and never over the book; and the two dialogs (`ui.dialogs.translator_model`), TASlation's
own, no system message box."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from taslation import translator_install as ti
from taslation.i18n import CATALOGS, set_language
from taslation.messages import Message
from taslation.translate.models import PLAMO, QWEN
from taslation.ui import model_switch as ms
from taslation.ui.dialogs import translator_model as tm


class Var:
    def __init__(self, value: str):
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class Window(ms.ModelSwitchMixin):
    """The parts of the window the offer uses: the settings, the "To:" box, the status line, `after`."""

    def __init__(self, tmp: Path, models: list[str] | None, language: str = "English"):
        self.settings = SimpleNamespace(ollama_model="auto", state_dir=tmp / "state", models_dir=tmp / "models",
                                        ollama_url="http://127.0.0.1:11434")
        self.models = models
        self.lang_var = Var(language)
        self.statuses: list[str] = []
        self.kept: list[str] = []
        self.later: list = []
        self.reading = False
        self._over_on = False
        self.batch = None

    def _models_now(self):
        return self.models

    def status(self, text):
        self.statuses.append(str(text))

    def _target_chosen(self):
        self.kept.append(self.lang_var.get())

    def after(self, _ms, callback):
        self.later.append(callback)

    def wait_window(self, _w):
        pass


@pytest.fixture
def boxes(monkeypatch):
    """The questions asked and told (answered from ``answers`` by a piece of their text, else no), the licence (agreed
    or not), the install (its outcome; *after* run as the dialog runs it)."""
    seen = SimpleNamespace(asked=[], told=[], answers={}, agree=True, outcome="done", installs=[], removed=[])

    def ask(_parent, text, yes=None, no=None, *, no_first=False, **_k):
        seen.asked.append((text, yes, no, no_first))
        return next((a for piece, a in seen.answers.items() if piece in text), False)

    def tell(_parent, text, **_k):
        seen.told.append(text)

    class Licence:
        def __init__(self, _master):
            self.agreed = seen.agree

    class Install:
        def __init__(self, _master, model, installer, after=None):
            seen.installs.append((model, installer))
            self.outcome = ti.Outcome(seen.outcome)
            self.after_result = after() if (after and seen.outcome == "done") else None

    monkeypatch.setattr(ms, "ask", ask)
    monkeypatch.setattr(ms, "tell", tell)
    monkeypatch.setattr(ms, "LicenceDialog", Licence)
    monkeypatch.setattr(ms, "InstallDialog", Install)
    monkeypatch.setattr(ti, "find_ollama", lambda: "ollama.exe")
    monkeypatch.setattr(ti, "remove_model", lambda exe, name, state_dir, url=None: seen.removed.append(name) or True)
    return seen


PLAMO_TAG = PLAMO.ollama_name + ":latest"


def test_from_qwen_of_taslation_s_to_plamo_one_question_and_the_licence(tmp_path, boxes):
    ti.mark_installed(tmp_path / "state", QWEN)
    w = Window(tmp_path, [QWEN.ollama_name], "English")
    boxes.answers = {"needs the translation model": True}
    assert w._translator_ready("English", "Turkish")
    text, yes, no, _first = boxes.asked[0]
    assert len(boxes.asked) == 1 and (yes, no) == ("Download", "Not now")
    assert "PLaMo 3 Translate 2B" in text and "about 1.8 GB" in text
    assert "Qwen3.5 4B is not needed for English and is then removed, which frees about 3.3 GB." in text
    assert ti.has_agreed(tmp_path / "state")  # the licence's agreement written down
    assert boxes.removed == [QWEN.ollama_name]
    assert boxes.installs[0][0] == "PLaMo 3 Translate 2B" and boxes.installs[0][1].language == "English"
    assert w.statuses[-1].startswith("PLaMo 3 Translate 2B is installed.") and "Qwen3.5 4B was removed" in w.statuses[-1]


def test_a_qwen_the_person_had_is_asked_about_and_kept_by_default(tmp_path, boxes):
    w = Window(tmp_path, [QWEN.ollama_name], "English")
    boxes.answers = {"needs the translation model": True}
    assert w._translator_ready("English", "Turkish")
    offer, theirs = boxes.asked
    assert "is then removed" not in offer[0]
    assert "was on this computer before TASlation installed anything" in theirs[0]
    assert theirs[1:] == ("Remove it", "Keep it", True)  # Keep it has the focus
    assert boxes.removed == []  # (no answer: kept)
    assert "was removed" not in w.statuses[-1]


def test_its_own_yes_removes_the_person_s_model(tmp_path, boxes):
    w = Window(tmp_path, [QWEN.ollama_name], "English")
    boxes.answers = {"needs the translation model": True, "before TASlation": True}
    assert w._translator_ready("English", "Turkish")
    assert boxes.removed == [QWEN.ollama_name]


def test_to_turkish_plamo_goes_with_the_one_yes_and_no_licence(tmp_path, boxes):
    w = Window(tmp_path, [PLAMO_TAG], "Turkish")
    boxes.answers = {"needs the translation model": True}
    boxes.agree = False  # (never shown: Qwen has no licence step)
    assert w._translator_ready("Turkish", "English")
    assert "Qwen3.5 4B" in boxes.asked[0][0] and "about 3.3 GB" in boxes.asked[0][0]
    assert "PLaMo 3 Translate 2B is not needed for Turkish" in boxes.asked[0][0]
    assert boxes.removed == [PLAMO_TAG] and len(boxes.asked) == 1


def test_a_no_puts_the_language_before_back(tmp_path, boxes):
    w = Window(tmp_path, [PLAMO_TAG], "Turkish")
    assert not w._translator_ready("Turkish", "English")
    assert w.lang_var.get() == "English" and w.kept == ["English"]
    assert w.statuses == ["The language stays English: Turkish needs Qwen3.5 4B, which is not installed."]
    assert boxes.installs == []


def test_a_no_with_nothing_to_go_back_to_says_translation_is_off(tmp_path, boxes):
    w = Window(tmp_path, ["gemma3:4b"], "German")
    assert not w._translator_ready("German", "French")  # French has no model either
    assert w.lang_var.get() == "German"
    assert w.statuses[-1].startswith("Translation is off: German needs PLaMo 3 Translate 2B")


def test_no_to_the_licence_downloads_nothing(tmp_path, boxes):
    w = Window(tmp_path, [QWEN.ollama_name], "English")
    boxes.answers = {"needs the translation model": True}
    boxes.agree = False
    assert not w._translator_ready("English", "Turkish")
    assert boxes.installs == [] and not ti.has_agreed(tmp_path / "state")
    # Qwen writes English too and translates it meanwhile (translate.models.choose): the language stays, as the
    # banner's translator.other_model says
    assert w.lang_var.get() == "English"
    assert "translating with Qwen3.5 4B for now" in w.statuses[-1]


def test_no_puts_the_language_back_when_nothing_stands_in(tmp_path, boxes):
    w = Window(tmp_path, [PLAMO.ollama_name], "Turkish")
    boxes.answers = {"needs the translation model": False}
    assert not w._translator_ready("Turkish", "English")
    assert w.lang_var.get() == "English" and boxes.installs == []


def test_one_offer_when_the_box_and_the_setup_check_both_find_the_model_missing(tmp_path, boxes):
    w = Window(tmp_path, [PLAMO.ollama_name], "Turkish")
    boxes.answers = {"needs the translation model": False}
    w._model_missing_seen([_missing("Turkish")])  # the check the "To:" box started came back first
    assert not w._translator_ready("Turkish", "English")
    for call in list(w.later):
        call()
    assert len(boxes.asked) == 1


def test_a_model_of_the_person_s_own_in_the_settings_is_never_offered(tmp_path, boxes):
    w = Window(tmp_path, ["gemma3:4b"], "English")
    w.settings.ollama_model = "gemma3:4b"
    assert w._translator_ready("Turkish", "English")
    w._model_missing_seen([_missing("Turkish")])
    for call in list(w.later):
        call()
    assert boxes.asked == []


def test_a_licence_agreed_before_is_not_shown_again(tmp_path, boxes, monkeypatch):
    ti.record_agreement(tmp_path / "state", "install")
    monkeypatch.setattr(ms, "LicenceDialog", lambda _m: pytest.fail("the licence again"))
    w = Window(tmp_path, [], "English")
    boxes.answers = {"needs the translation model": True}
    assert w._translator_ready("English")


@pytest.mark.parametrize("outcome, said", [("cancelled", "Stopped. Nothing was left on the disk."),
                                           ("failed", "could not be installed"), ("no_room", "too little disk space")])
def test_an_install_that_did_not_end_well_says_so_and_puts_the_language_back(tmp_path, boxes, outcome, said):
    w = Window(tmp_path, [PLAMO_TAG], "Turkish")
    boxes.answers = {"needs the translation model": True}
    boxes.outcome = outcome
    assert not w._translator_ready("Turkish", "English")
    assert said in boxes.told[-1] and boxes.removed == []  # nothing is removed before the new one is there
    assert w.lang_var.get() == "English"


def test_a_model_that_is_there_or_an_ollama_that_does_not_answer_asks_nothing(tmp_path, boxes):
    assert Window(tmp_path, [PLAMO_TAG])._translator_ready("French", "English")
    assert Window(tmp_path, None)._translator_ready("Turkish", "English")  # (the request will say what is wrong)
    assert boxes.asked == []


def _missing(language: str) -> Message:
    """What the setup check says (`translate.models.missing_message`, the runtime's own)."""
    from taslation.translate.models import missing_message, model_for_language

    return missing_message(model_for_language(language), language)


def test_the_setup_check_leads_to_the_offer_once(tmp_path, boxes):
    w = Window(tmp_path, ["gemma3:4b"], "English")
    w._model_missing_seen([_missing("English")])
    w._model_missing_seen([_missing("English")])
    assert len(w.later) == 1
    w.later.pop()()
    assert len(boxes.asked) == 1 and "PLaMo 3 Translate 2B" in boxes.asked[0][0]
    w._model_missing_seen([_missing("English")])
    assert w.later == []  # asked once: the status line says the rest


@pytest.mark.parametrize("away", ["reading", "_over_on", "batch"])
def test_over_the_book_the_check_only_says_so_once(tmp_path, boxes, away):
    w = Window(tmp_path, ["gemma3:4b"], "English")
    setattr(w, away, True if away != "batch" else object())
    w._model_missing_seen([_missing("English")])
    w._model_missing_seen([_missing("English")])
    assert w.later == [] and boxes.asked == []
    assert w.statuses == ["Translation is off: English needs PLaMo 3 Translate 2B, which is not installed. "
                          "TASlation asks about it when you are back in its window."]
    setattr(w, away, False if away != "batch" else None)  # back in the window: the next check offers it
    w._model_missing_seen([_missing("English")])
    w.later.pop()()
    assert len(boxes.asked) == 1


def test_every_string_of_the_offer_is_in_every_language():
    from taslation.locales.features import translator_models

    for key in translator_models.TEXTS:
        for code, catalog in CATALOGS.items():
            if code != "en":
                assert catalog.get(key), (code, key)
    assert tm.LICENCE_TEXT in translator_models.TEXTS


# ---- the dialogs


def test_the_licence_waits_for_the_tick(hidden_root):
    dialog = tm.LicenceDialog(hidden_root)
    try:
        assert str(dialog.agree_btn.cget("state")) == "disabled" and not dialog.tick.get()
        dialog._agree()
        assert not dialog.agreed and dialog.winfo_exists()
        assert dialog.urls == list(ti.PLAMO_LICENCE_URLS)
        assert "article 5" in dialog.text and "18" in dialog.text
        dialog.tick_box.invoke()
        assert str(dialog.agree_btn.cget("state")) == "normal"
        dialog.agree_btn.invoke()
        assert dialog.agreed and not dialog.winfo_exists()
    finally:
        if dialog.winfo_exists():
            dialog.destroy()


def test_the_licence_speaks_the_window_s_language(hidden_root):
    set_language("ja")
    dialog = tm.LicenceDialog(hidden_root)
    try:
        assert dialog.title() == CATALOGS["ja"]["The licence of PLaMo"] and dialog.text == CATALOGS["ja"][tm.LICENCE_TEXT]
        dialog._cancel()
        assert not dialog.agreed
    finally:
        if dialog.winfo_exists():
            dialog.destroy()


class FakeInstaller:
    def __init__(self, steps, end="done", hold: threading.Event | None = None):
        self.steps, self.end, self.hold = steps, end, hold
        self.on_progress = None
        self.cancelled = threading.Event()

    def run(self):
        for step in self.steps:
            self.on_progress(step)
        if self.hold is not None:
            self.cancelled.wait(5)
            return ti.Outcome("cancelled")
        return ti.Outcome(self.end)

    def cancel(self):
        self.cancelled.set()


def _wait(dialog, root, seconds=10.0):
    end = time.monotonic() + seconds
    while dialog.winfo_exists() and time.monotonic() < end:
        root.update()
        time.sleep(0.02)


def test_the_install_dialog_shows_how_far_and_ends_with_the_outcome(hidden_root):
    gb = 1_807_192_480
    installer = FakeInstaller([{"phase": "download", "done": gb // 2, "total": gb}, {"phase": "check"},
                               {"phase": "import"}])
    after = []
    dialog = tm.InstallDialog(hidden_root, "PLaMo 3 Translate 2B", installer, after=lambda: after.append(1) or True)
    _wait(dialog, hidden_root)
    assert not dialog.winfo_exists() and dialog.outcome.state == "done" and dialog.after_result is True
    assert dialog.lines == ["Downloading PLaMo 3 Translate 2B: 0.9 of 1.8 GB", "Checking the download...",
                            "Putting PLaMo 3 Translate 2B into Ollama..."]


def test_cancel_stops_the_install_and_the_dialog_waits_for_its_cleanup(hidden_root):
    installer = FakeInstaller([{"phase": "pull", "done": 300, "total": 1000}], hold=threading.Event())
    dialog = tm.InstallDialog(hidden_root, "Qwen3.5 4B", installer, after=lambda: pytest.fail("after a cancel"))
    hidden_root.update()
    dialog.cancel_btn.invoke()
    assert installer.cancelled.is_set() and str(dialog.cancel_btn.cget("state")) == "disabled"
    _wait(dialog, hidden_root)
    assert dialog.outcome.state == "cancelled" and dialog.lines[0] == "Downloading Qwen3.5 4B: 30 %"


def test_the_dialogs_are_taslation_s_own():
    text = Path(tm.__file__).read_text("utf-8") + Path(ms.__file__).read_text("utf-8")
    assert "messagebox" not in text
