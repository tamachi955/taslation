"""The translator model the target language needs, offered by the window (a part of `app.App`): only one of PLaMo 3
Translate 2B and Qwen3.5 4B is installed at a time (`translator_install`). When the "To:" box is left with a language
whose model is not installed (`_translator_ready`), or a setup check says so (``translator.model_missing``,
`_model_missing_seen`), the window asks, in plain words, whether to download it (its size) and to remove the one no
longer needed (the room freed); a model TASlation did not install is the person's own and is asked about on its own,
keeping it the default. PLaMo's licence is agreed to first (`LicenceDialog`), and the install runs with how far it
is and Cancel (`InstallDialog`). A no puts the language back when the one before still has its model, else the
status line says that translating is off and why.

All of it waits while the window is over the book or in reading mode, or while a whole-book run reads: a check that
found the model missing then only says so in the status line, once, and asks when the window is back. One offer at a
time, and one per language: the "To:" box and the setup check that follows it (`JobsMixin._follow_target`) find the
same missing model, and only the first asks. A setting ``ollama_model`` naming a model of the person's own is theirs:
nothing is offered then (`translator_install.plan`).

The setup banner's Download model (`download_model`) makes the same offer for the language in the "To:" box
whenever it is pressed, after a no too."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import health
from .. import translator_install as tinstall
from ..i18n import _
from ..translate.models import MODEL_MISSING, OTHER_MODEL, choose
from .constants import LANGUAGES
from .dialogs.caches import ask, tell
from .dialogs.translator_model import InstallDialog, LicenceDialog
from .progress import code_of

MISSING_CODE = MODEL_MISSING  # {model, name, language}: the setup check's (`translate.models.missing_message`)


def _shown(language: str) -> str:
    """A target language as the window shows it (as `app.shown_target`)."""
    return _(language) if language in LANGUAGES else language


def offer_text(switch: tinstall.Switch) -> str:
    """The question of the offer: what is needed and its size, and what goes afterwards and the room it frees."""
    text = _("Translating into {language} needs the translation model {model}, which is not on this computer yet. TASlation can download it now: about {size} GB.").format(
        language=_shown(switch.language), model=tinstall.shown_name(switch.needed),
        size=tinstall.size_text(switch.needed.size_gb))
    if switch.unneeded is not None and switch.ours:
        text += "\n\n" + _("{old} is not needed for {language} and is then removed, which frees about {freed} GB.").format(
            old=tinstall.shown_name(switch.unneeded), language=_shown(switch.language),
            freed=tinstall.size_text(switch.freed_gb))
    return text


def theirs_text(switch: tinstall.Switch) -> str:
    assert switch.unneeded is not None
    return _("{old} was on this computer before TASlation installed anything, and {language} does not need it. Remove it too, to free about {freed} GB?").format(
        old=tinstall.shown_name(switch.unneeded), language=_shown(switch.language),
        freed=tinstall.size_text(switch.freed_gb))


class ModelSwitchMixin:
    """A part of `app.App` (no `__init__`: what it keeps is made on first use)."""

    def _model_state(self) -> dict[str, Any]:
        state = getattr(self, "_model_switch", None)
        if state is None:
            state = self._model_switch = {"asked": set(), "noted": set(), "offered": set(), "installing": False,
                                          "offering": False}
        return state

    def _models_now(self) -> list[str] | None:
        """The models Ollama has now (None: it does not answer)."""
        return health.installed_models(self.settings.ollama_url)

    def _away(self) -> bool:
        """The window is not where a box nobody asked for may come up: over the book, in reading mode, in a run."""
        return bool(getattr(self, "reading", False) or getattr(self, "_over_on", False)
                    or getattr(self, "batch", None) is not None)

    def _translator_ready(self, language: str, before: str | None = None) -> bool:
        """The "To:" box was left with *language* (*before*: the language it had): whether its translator model is
        there, after the offer when it was not (the person's own choice: asked at once)."""
        state = self._model_state()
        if state["installing"] or state["offering"]:
            return False
        switch = self._plan(language)
        if switch is None:
            return True
        return self._offer_switch(switch, before)

    def _plan(self, language: str) -> tinstall.Switch | None:
        return tinstall.plan(language, self._models_now(), Path(self.settings.state_dir), self.settings.ollama_model)

    def download_model(self) -> None:
        """The setup banner's Download model: the offer for the language in the "To:" box (`_offer_switch`: its size,
        PLaMo's licence, the install with Cancel), asked again even after a no; when nothing needs installing, the
        status line says so and the setup is checked again."""
        state = self._model_state()
        if state["installing"] or state["offering"]:
            return
        language = self.lang_var.get().strip() or "English"
        switch = self._plan(language)
        if switch is None:
            self.status(_("The translation model for {language} is installed already.").format(language=_shown(language)))
            recheck = getattr(self, "_check_in_background", None)
            if recheck is not None:
                import threading

                threading.Thread(target=recheck, name="taslation-setup-check", daemon=True).start()
            return
        self._offer_switch(switch, None)

    def _model_missing_seen(self, problems: list[Any] | None) -> None:
        """A setup check's problems: one that says the language's translator model is missing leads to the offer, once
        per language - later, when the window is not over the book (only the status line says so meanwhile)."""
        state = self._model_state()
        for message in problems or ():
            if code_of(message) != MISSING_CODE:
                continue
            params = getattr(message, "params", {}) or {}
            language = str(params.get("language") or self.lang_var.get().strip() or "English")
            if language in state["asked"] or state["installing"] or state["offering"]:
                continue
            if self._away():
                if language not in state["noted"]:
                    state["noted"].add(language)
                    self.status(self._off_text(language, away=True))
                continue
            state["asked"].add(language)
            self.after(0, lambda language=language: self._offer_missing(language))

    def _offer_missing(self, language: str) -> None:
        state = self._model_state()
        if language in state["offered"]:  # the "To:" box asked already
            return
        if state["installing"] or state["offering"] or self._away():
            state["asked"].discard(language)
            return
        switch = self._plan(language)
        if switch is not None:
            self._offer_switch(switch, None)

    def _offer_switch(self, switch: tinstall.Switch, before: str | None) -> bool:
        """The offer of *switch*: the question, PLaMo's licence when it was not agreed to yet, whether to remove a
        model of the person's own, then the install and the removal. Whether the model is there now."""
        state = self._model_state()
        state["asked"].add(switch.language)
        state["offered"].add(switch.language)
        state["offering"] = True
        try:
            agreed = self._agreed_to(switch)
        finally:
            state["offering"] = False
        if agreed is None:
            self._switch_declined(switch, before)
            return False
        remove = agreed
        state_dir = Path(self.settings.state_dir)
        name = tinstall.shown_name(switch.needed)
        installer = tinstall.Installer(switch.language, self.settings.models_dir, state_dir, self.settings.ollama_url)
        after = None
        if remove and switch.unneeded is not None:
            def after() -> bool:
                exe = tinstall.find_ollama()
                return bool(exe) and tinstall.remove_model(exe, switch.unneeded_name, state_dir,
                                                           self.settings.ollama_url)
        state["installing"] = True
        try:
            dialog = InstallDialog(self, name, installer, after)
            self.wait_window(dialog)
        finally:
            state["installing"] = False
        outcome = dialog.outcome or tinstall.Outcome("cancelled")
        if outcome.state != "done":
            if outcome.state == "cancelled":
                tell(self, _("Stopped. Nothing was left on the disk."), icon="info")
            elif outcome.state == "no_room":
                tell(self, _("There is too little disk space for {model}. Nothing was downloaded.").format(model=name))
            elif outcome.state == "refused":  # the file this version names is gone: trying again would not help
                tell(self, _("{model} could not be installed: the publisher's server refused the download or no longer has this file. Trying again will not help: update TASlation (a newer version names the current file), or look at the project's issues page. Nothing was left on the disk.").format(model=name))
            else:
                tell(self, _("{model} could not be installed. Check the network and the disk space, and try again. Nothing was left on the disk.").format(model=name))
            self._switch_declined(switch, before)
            return False
        text = _("{model} is installed. TASlation translates into {language} now.").format(
            model=name, language=_shown(switch.language))
        if dialog.after_result and switch.unneeded is not None:
            text += " " + _("{old} was removed, freeing about {freed} GB.").format(
                old=tinstall.shown_name(switch.unneeded), freed=tinstall.size_text(switch.freed_gb))
        self.status(text)
        recheck = getattr(self, "_check_in_background", None)
        if recheck is not None:  # the banner and the models the window knows follow
            import threading

            threading.Thread(target=recheck, name="taslation-setup-check", daemon=True).start()
        return True

    def _agreed_to(self, switch: tinstall.Switch) -> bool | None:
        """The questions before an install: the offer, PLaMo's licence when it was not agreed to yet, and whether to
        remove the person's own model. None for a no; else whether the one no longer needed goes."""
        state_dir = Path(self.settings.state_dir)
        if not ask(self, offer_text(switch), _("Download"), _("Not now")):
            return None
        if switch.needed.ollama_name == tinstall.PLAMO.ollama_name and not tinstall.has_agreed(state_dir):
            dialog = LicenceDialog(self)
            self.wait_window(dialog)
            if not dialog.agreed:
                return None
            tinstall.record_agreement(state_dir, "window")
        if switch.unneeded is not None and not switch.ours:
            return ask(self, theirs_text(switch), _("Remove it"), _("Keep it"), no_first=True)
        return switch.ours

    def _off_text(self, language: str, away: bool = False) -> str:
        model = tinstall.shown_name(tinstall.model_for_language(language))
        if away:
            return _("Translation is off: {language} needs {model}, which is not installed. TASlation asks about it when you are back in its window.").format(language=_shown(language), model=model)
        return _("Translation is off: {language} needs {model}, which is not installed. Choose {language} in the To list again to install it.").format(language=_shown(language), model=model)

    def _switch_declined(self, switch: tinstall.Switch, before: str | None) -> None:
        """No to the offer (or a stopped install): when Qwen can translate the language meanwhile (PLaMo's languages,
        ``translator.other_model``), the language stays and the status line says so; else the language before comes
        back when its model is there, else translating stays off, and the status line says which."""
        model = tinstall.shown_name(switch.needed)
        models = self._models_now()
        stand_in = choose(self.settings.ollama_model, switch.language, models).problem
        back = before and before != switch.language and tinstall.plan(
            before, models, Path(self.settings.state_dir), self.settings.ollama_model) is None
        if code_of(stand_in) == OTHER_MODEL:  # translating is not off: the banner says the same
            self.status(stand_in)
        elif back:
            self.lang_var.set(before)
            self._target_chosen()
            self.status(_("The language stays {before}: {language} needs {model}, which is not installed.").format(
                before=_shown(before), language=_shown(switch.language), model=model))
        else:
            self.status(self._off_text(switch.language))
