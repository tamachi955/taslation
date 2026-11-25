"""The start's dialog when the GPU's memory is short for everything TASlation puts there (`ui.dialogs.gpu_short`) and the
window's one judgement at the start (`JobsMixin._judge_gpu`): the dialog says by how much and what would go to the
processor, and has three ways out - Check again, Start on the processor, Quit (closing it or Escape is Quit) - and a box,
Do not ask again on this computer, that keeps ``gpu_short`` "processor"; the start asks only when it is short, never
without an NVIDIA GPU, with the choice remembered, or with a setting that forces a part onto the GPU. Facts and needs are
stand-ins: no GPU, no Ollama. Every other test of the suite refuses this dialog (conftest's `no_gpu_dialog_unless_asked`)."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from types import SimpleNamespace

import pytest

from taslation import devices
from taslation.config import Settings
from taslation.i18n import set_language
from taslation.ocr import place
from taslation.ocr.place import LAMA, LAYOUT, LAMA_MIB, LAYOUT_MIB, NAR_MIB, CHARSPOT_MIB, READERS, TRANSLATOR
from taslation.ocr.place import GpuFacts, Need
from taslation.ui import jobs
from taslation.ui.dialogs import gpu_short

pytestmark = pytest.mark.usefixtures("gpu_dialog_allowed")

PLAMO_WINDOW = 2100


def _needs(fixed=()) -> list[Need]:
    parts = ((TRANSLATOR, PLAMO_WINDOW), (READERS, CHARSPOT_MIB + NAR_MIB), (LAMA, LAMA_MIB), (LAYOUT, LAYOUT_MIB))
    return [Need(part, mib, part in fixed) for part, mib in parts]


# ------------------------------------------------------------------ the dialog
@pytest.fixture
def answers():
    return []


def _dialog(root, answers, short=296, parts=(READERS,)):
    return gpu_short.GpuShortDialog(root, short, parts, lambda choice, remember: answers.append((choice, remember)))


def test_the_dialog_says_by_how_much_and_what_would_go_and_names_its_three_ways(hidden_root, answers):
    d = _dialog(hidden_root, answers, 996, (READERS, LAMA))
    assert d.shown_mb == 1000 and d.parts == (READERS, LAMA)  # (MB, rounded up to 10)
    assert d.message_text == (gpu_short.TEXT.format(mb=1000) + "\n\nOn the processor: the OCR readers, the erase model on "
                              "the art (LaMa).")
    assert "short by 1000 MB" in d.message_text and "(slower)" in d.message_text
    assert [b.cget("text") for b in (d.again_btn, d.processor_btn, d.quit_btn)] == [
        "Check again", "Start on the processor", "Quit"]
    assert d.title() == "TASlation" and d.remember.get() is False
    assert str(d.again_btn.cget("default")) == "active"  # (it has the focus: Return checks again)
    d.choose("again")


def test_check_again_starts_on_the_processor_and_quit_each_answer_once_and_close_it(hidden_root, answers):
    for button, want in (("again_btn", ("again", False)), ("processor_btn", ("processor", False)),
                         ("quit_btn", ("quit", False))):
        d = _dialog(hidden_root, answers)
        getattr(d, button).invoke()
        assert answers[-1] == want and not d.winfo_exists()
        d.choose("processor")  # (answered: nothing more is told)
        assert answers[-1] == want
    assert len(answers) == 3


def test_do_not_ask_again_goes_with_start_on_the_processor_alone(hidden_root, answers):
    d = _dialog(hidden_root, answers)
    d.remember.set(True)
    d.processor_btn.invoke()
    assert answers == [("processor", True)]
    for way in ("again", "quit"):
        d = _dialog(hidden_root, answers)
        d.remember.set(True)
        d.choose(way)
        assert answers[-1] == (way, False)


def test_escape_closing_it_or_its_window_going_is_quit(hidden_root, answers):
    d = _dialog(hidden_root, answers)
    assert d.bind("<Escape>")  # (bound: a hidden window gets no key events here)
    d._on_escape()
    d2 = _dialog(hidden_root, answers)
    d2.tk.call(d2.protocol("WM_DELETE_WINDOW"))  # (the title bar's close)
    d3 = _dialog(hidden_root, answers)
    d3.destroy()  # (the window closed under it)
    assert answers == [("quit", False)] * 3


def test_return_presses_the_button_that_has_the_focus(hidden_root, answers):
    d = _dialog(hidden_root, answers)
    assert d.bind("<Return>")
    d._on_return()  # (no other button has the focus: Check again)
    d = _dialog(hidden_root, answers)
    d.focus_get = lambda: d.processor_btn  # (the person moved the focus with Tab)
    d._on_return()
    assert answers == [("again", False), ("processor", False)]


def test_the_dialog_in_japanese_says_the_owner_s_words(hidden_root, answers):
    set_language("ja")
    d = _dialog(hidden_root, answers, 296, (READERS,))
    assert d.message_text.startswith("VRAM の空き容量が 300 MB 不足しています。")
    assert d.message_text.endswith("CPU で動かすもの: OCR の読み取り。")
    assert [b.cget("text") for b in (d.again_btn, d.processor_btn, d.quit_btn)] == ["もう一度確認", "CPU モードで起動",
                                                                                       "終了"]
    d.choose("quit")


HELD = (place.Loaded("qwen3.5:4b", 3203, True), place.Loaded("someones-model:7b", 896, False))


def test_the_dialog_names_the_models_ollama_holds_and_offers_to_release_taslation_s_own(hidden_root, answers):
    d = gpu_short.GpuShortDialog(hidden_root, 296, (READERS,), lambda c, r: answers.append((c, r)), HELD)
    assert d.message_text == (gpu_short.TEXT.format(mb=300) + "\n\n"
                              "TASlation's models still loaded in Ollama: qwen3.5:4b (3210 MB).\n"
                              "Other programs' models loaded in Ollama: someones-model:7b (900 MB).\n\n"
                              "On the processor: the OCR readers.")
    assert [b.cget("text") for b in d.buttons] == ["Release and check again", "Check again", "Start on the processor",
                                                   "Quit"]
    assert str(d.release_btn.cget("default")) == "active" and str(d.again_btn.cget("default")) != "active"
    d._on_return()  # (Return: the first, Release and check again)
    assert answers == [("release", False)]


def test_with_only_other_programs_models_there_is_nothing_to_release(hidden_root, answers):
    d = gpu_short.GpuShortDialog(hidden_root, 296, (), lambda c, r: answers.append((c, r)), HELD[1:])
    assert d.release_btn is None and len(d.buttons) == 3 and str(d.again_btn.cget("default")) == "active"
    assert d.message_text.endswith("\n\nOther programs' models loaded in Ollama: someones-model:7b (900 MB).")
    d.choose("again")


def test_the_models_in_japanese(hidden_root, answers):
    set_language("ja")
    d = gpu_short.GpuShortDialog(hidden_root, 296, (READERS,), lambda c, r: answers.append((c, r)), HELD)
    assert "Ollama に読み込まれたままの TASlation のモデル: qwen3.5:4b（3210 MB）。" in d.message_text
    assert "Ollama に読み込まれているほかのプログラムのモデル: someones-model:7b（900 MB）。" in d.message_text
    assert d.release_btn.cget("text") == "解放してもう一度確認"
    d.choose("quit")


def test_here_the_dialog_is_the_real_one():
    assert gpu_short.GpuShortDialog.__init__.__name__ == "__init__"  # (elsewhere conftest's refusal: test_ocr_place)


# ------------------------------------------------------------------ the window's start
class Window:
    """The parts of the App the start's judgement uses; the Tk side answers the "gpu_short" event as *answers* say
    (a thread that stands in for the event pump), and what it posts is kept."""

    _judge_gpu = jobs.JobsMixin._judge_gpu
    _ask_gpu_short = jobs.JobsMixin._ask_gpu_short
    _keep_gpu_short = jobs.JobsMixin._keep_gpu_short
    _post = jobs.JobsMixin._post

    def __init__(self, settings, replies=()):
        self.settings = settings
        self._events: queue.Queue = queue.Queue()
        self.replies = list(replies)
        self.asked: list[tuple[int, tuple[str, ...]]] = []
        self.named: list[tuple] = []  # the other models each dialog named
        self.released: list[list[str]] = []  # what Release and check again released
        self.posted: list[str] = []
        self._stop = threading.Event()
        self._pump = threading.Thread(target=self._answer, daemon=True)
        self._pump.start()

    def _answer(self):
        while not self._stop.is_set():
            try:
                kind, data = self._events.get(timeout=0.05)
            except queue.Empty:
                continue
            self.posted.append(kind)
            if kind == "gpu_short":
                self.asked.append((data["short"], tuple(data["parts"])))
                self.named.append(tuple(data["loaded"]))
                data["answer"](*self.replies.pop(0))

    def _release_loaded(self, models):
        self.released.append([m.name for m in models])

    def judge(self, asks_ollama=True) -> bool:
        try:
            return self._judge_gpu(asks_ollama)
        finally:
            self._stop.set()
            self._pump.join(2)


@pytest.fixture
def card(monkeypatch):
    """The facts the start reads, one per judgement (the last one again), and the default settings' needs."""
    seen = SimpleNamespace(facts=[GpuFacts(total=6144, used=1000)], needs=_needs(), asked_ollama=[])

    def gather(settings, memory=None, own=None, ask=True):
        seen.asked_ollama.append(ask)
        return seen.facts.pop(0) if len(seen.facts) > 1 else seen.facts[0]

    monkeypatch.setattr(place, "gather", gather)
    monkeypatch.setattr(place, "needs", lambda settings, cuda=None, ask=True: seen.needs)
    return seen


def _settings(tmp_path, **kw):
    return Settings(state_dir=tmp_path / "state", models_dir=tmp_path / "models",
                    config_path=tmp_path / "taslation.toml", **kw)


def test_enough_asks_nothing_and_everything_goes_on_the_gpu(tmp_path, card):
    w = Window(_settings(tmp_path))
    assert w.judge() is True and not w.asked
    plan = place.session()
    assert plan.why == place.ROOM and plan.gpu == (TRANSLATOR, READERS, LAMA, LAYOUT) and plan.cpu == ()


def test_short_asks_once_and_start_on_the_processor_sends_only_what_does_not_fit(tmp_path, card):
    card.facts = [GpuFacts(total=6144, used=2000)]  # (short by 296 MiB)
    w = Window(_settings(tmp_path), replies=[("processor", False)])
    assert w.judge() is True and w.asked == [(296, (READERS,))]
    plan = place.session()
    assert plan.why == place.PROCESSOR and plan.cpu == (READERS,) and "gpu_short_kept" not in w.posted
    assert not (tmp_path / "taslation.toml").exists()  # (nothing kept: the next start asks again)


def test_check_again_judges_anew_on_the_facts_of_that_moment(tmp_path, card):
    card.facts = [GpuFacts(total=6144, used=2700), GpuFacts(total=6144, used=1500)]  # (the person closed something)
    w = Window(_settings(tmp_path), replies=[("again", False)])
    assert w.judge() is True and w.asked == [(996, (READERS, LAMA))]
    assert place.session().why == place.ROOM and place.session().cpu == ()


def test_check_again_while_still_short_asks_again(tmp_path, card):
    card.facts = [GpuFacts(total=6144, used=2700), GpuFacts(total=6144, used=2000)]
    w = Window(_settings(tmp_path), replies=[("again", False), ("processor", False)])
    assert w.judge() is True and w.asked == [(996, (READERS, LAMA)), (296, (READERS,))]
    assert place.session().cpu == (READERS,)


def test_release_and_check_again_releases_taslation_s_own_models_alone_then_judges_anew(tmp_path, card):
    card.facts = [GpuFacts(total=6144, used=5203, loaded=HELD), GpuFacts(total=6144, used=1700, loaded=HELD[1:])]
    w = Window(_settings(tmp_path), replies=[("release", False)])
    assert w.judge() is True and w.named == [HELD] and w.released == [["qwen3.5:4b"]]
    assert place.session().why == place.ROOM  # (judged anew on the facts after the release)


def test_the_window_s_release_unloads_taslation_s_own_and_waits_for_the_card(tmp_path, monkeypatch):
    from fake_ollama import FakeOllama

    from taslation import netguard

    with FakeOllama() as fake:
        netguard.install(allowed_ports={fake.port}, audit_hook=False)
        try:
            fake.tracks_loads = True
            fake.loaded.update({"qwen3.5:4b", "someones-model:7b"})
            waited = []
            monkeypatch.setattr(place, "card_memory", lambda: (6144, 5000))
            monkeypatch.setattr(place, "wait_freed", lambda before, mib, timeout=3.0: waited.append((before, mib)))
            w = SimpleNamespace(settings=_settings(tmp_path, ollama_url=fake.url))
            jobs.JobsMixin._release_loaded(w, list(HELD))
        finally:
            netguard.uninstall()
    assert fake.loaded == {"someones-model:7b"}  # (another program's model is never asked to go)
    assert [r["model"] for r in fake.requests] == ["qwen3.5:4b"] and waited == [((6144, 5000), 3203)]


def test_quit_ends_the_start_with_no_plan(tmp_path, card):
    card.facts = [GpuFacts(total=6144, used=2000)]
    w = Window(_settings(tmp_path), replies=[("quit", False)])
    assert w.judge() is False and place.session() is None


def test_do_not_ask_again_keeps_the_choice_and_the_next_start_asks_nothing(tmp_path, card):
    card.facts = [GpuFacts(total=6144, used=2000)]
    s = _settings(tmp_path)
    w = Window(s, replies=[("processor", True)])
    assert w.judge() is True and "gpu_short_kept" in w.posted
    w._keep_gpu_short()  # (the event on the Tk thread)
    assert s.gpu_short == "processor" and Settings.from_toml(tmp_path / "taslation.toml").gpu_short == "processor"
    place.reset()
    again = Window(Settings.from_toml(tmp_path / "taslation.toml"))
    again.settings.state_dir, again.settings.models_dir = s.state_dir, s.models_dir
    assert again.judge() is True and not again.asked  # (silent: what does not fit on the processor)
    assert place.session().cpu == (READERS,) and devices.plan_text().startswith("At the start the GPU's memory was short by 300 MB")


def test_a_setting_that_forces_a_part_onto_the_gpu_never_asks(tmp_path, card):
    card.facts = [GpuFacts(total=6144, used=2000)]
    card.needs = _needs(fixed=(READERS,))  # (``ocr_runs_on`` "gpu")
    w = Window(_settings(tmp_path, ocr_runs_on="gpu"))
    assert w.judge() is True and not w.asked
    plan = place.session()
    assert plan.why == place.SHORT and plan.short == 296 and plan.cpu == () and READERS in plan.gpu
    assert devices.plan_text() == devices.PLAN_FIXED.format(mb=300)  # (the System page says by how much)
    assert place.readers_placement(w.settings, cuda=True) == place.Placement("gpu", place.SET)


def test_without_an_nvidia_gpu_nothing_is_judged_or_asked(tmp_path, card, monkeypatch):
    monkeypatch.setattr(place, "gather", lambda settings, memory=None, own=None, ask=True: None)
    monkeypatch.setattr(place, "needs", lambda *a, **k: pytest.fail("the needs were asked without a GPU"))
    w = Window(_settings(tmp_path))
    assert w.judge() is True and not w.asked and place.session().why == place.NO_GPU
    assert devices.plan_text() == ""


def test_ollama_down_at_the_setup_check_is_not_asked_by_the_judgement(tmp_path, card):
    w = Window(_settings(tmp_path))
    assert w.judge(asks_ollama=False) is True and card.asked_ollama == [False]


def test_the_window_shows_the_dialog_keeps_it_while_open_and_quit_closes_the_window(hidden_root):
    class Win(tk.Toplevel):
        _show_gpu_short = jobs.JobsMixin._show_gpu_short

        def __init__(self, master):
            super().__init__(master)
            self._gpu_dialog = None
            self.closed = []

        def _on_close(self):
            self.closed.append(1)

    w = Win(hidden_root)
    got = []
    w._show_gpu_short(296, (READERS,), lambda choice, remember=False: got.append((choice, remember)))
    assert isinstance(w._gpu_dialog, gpu_short.GpuShortDialog)
    w._gpu_dialog.choose("processor")  # (a tool answers it through the window's own object, so: no input)
    assert got == [("processor", False)] and w._gpu_dialog is None and not w.closed
    w._show_gpu_short(296, (READERS,), lambda choice, remember=False: got.append((choice, remember)))
    w._gpu_dialog.choose("quit")
    w.update()
    assert got[-1] == ("quit", False) and w.closed == [1]
    w.destroy()
