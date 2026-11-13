"""What stands in the way, each line with the button that fixes it (`taslation.ui.trouble`): the viewer (tied
candidates, closed, minimised, covered, black) on the setup banner and on a run's band, Ollama down, a missing
translation model (Download model, not install.cmd), and the translator on the processor."""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from test_start_flow import DOWN, Flow, button_texts

from taslation.messages import Message
from taslation.ui import banner, jobs, trouble

MISSING = Message("translator.model_missing", model="plamo-3-translate:2b", name="PLaMo 3 Translate 2B",
                  language="English")


def _window(**kw):
    base = dict(batch=None, _batching=False, selected=None, _tied_said=(), _viewer_closed=None, _covered=False,
                _black_watch=None)
    base.update(kw)
    return SimpleNamespace(**base)


VIEWER = SimpleNamespace(hwnd=4242, title="Fake viewer (scratch)", class_name="TkTopLevel")


# ------------------------------------------------------------------ what keeps the window from the viewer
def test_the_viewer_trouble_is_named(monkeypatch):
    minimised = set()
    monkeypatch.setattr(trouble, "window_minimised", lambda hwnd: hwnd in minimised)
    assert trouble.viewer_trouble(_window()) is None  # no viewer chosen yet: the page says how to choose one
    assert trouble.viewer_trouble(_window(_tied_said=(1, 2))) == trouble.TIED
    assert trouble.viewer_trouble(_window(_viewer_closed=VIEWER)) == trouble.CLOSED
    assert trouble.viewer_trouble(_window(selected=VIEWER)) is None
    assert trouble.viewer_trouble(_window(selected=VIEWER, _covered=True)) == trouble.COVERED
    told = SimpleNamespace(told=True)
    assert trouble.viewer_trouble(_window(selected=VIEWER, _black_watch=SimpleNamespace(told=False))) is None
    assert trouble.viewer_trouble(_window(selected=VIEWER, _black_watch=told)) == trouble.BLACK
    minimised.add(VIEWER.hwnd)
    assert trouble.viewer_trouble(_window(selected=VIEWER, _covered=True)) == trouble.MINIMISED
    assert trouble.viewer_trouble(_window(selected=VIEWER, _batching=True)) is None  # a run's band says its own


def test_moving_aside_leaves_a_strip_of_the_viewer_in_view():
    area = (0, 0, 1920, 1040)
    viewer = (0, 0, 1200, 1040)
    assert trouble.aside_rect((0, 0, 1920, 1040), viewer, area) == (160, 0, 1920, 1040)  # the viewer's left shows
    right = (700, 0, 1920, 1040)
    assert trouble.aside_rect((0, 0, 1920, 1040), right, area) == (0, 0, 1760, 1040)  # ... its right, where more stays
    assert trouble.aside_rect((300, 0, 1920, 1040), viewer, area) is None  # a part of it shows already
    narrow = (0, 0, 700, 1040)  # a small screen: TASlation at least 640 px wide, at the right edge
    assert trouble.aside_rect((0, 0, 700, 1040), (0, 0, 700, 1040), narrow) == (60, 0, 700, 1040)


def test_move_aside_unmaximises_and_moves_only_tasl_windows_own(monkeypatch):
    moved, states = [], ["zoomed"]
    window = SimpleNamespace(selected=VIEWER, _own_hwnd=lambda: 77, update_idletasks=lambda: None,
                             state=lambda value=None: states.append(value) if value else states[-1])
    monkeypatch.setattr(trouble, "IS_WINDOWS", True)
    monkeypatch.setattr(trouble, "work_area", lambda hwnd: (0, 0, 1920, 1040))
    monkeypatch.setattr(trouble, "window_rect", lambda hwnd: {77: (0, 0, 1920, 1040), VIEWER.hwnd: (0, 0, 1200, 1040)}[hwnd])
    monkeypatch.setattr(trouble, "move_window", lambda hwnd, rect: moved.append((hwnd, rect)) or True)
    trouble.move_aside(window)
    assert states[-1] == "normal" and moved == [(77, (160, 0, 1920, 1040))]  # never the viewer's window


def test_show_viewer_restores_a_minimised_one_and_puts_a_black_one_in_front(monkeypatch):
    shown, raised, lowered = [], [], []
    monkeypatch.setattr(trouble, "window_exists", lambda hwnd: True)
    monkeypatch.setattr(trouble, "window_minimised", lambda hwnd: True)
    monkeypatch.setattr(trouble, "show_minimised", lambda window, win: shown.append(win.hwnd) or True)
    said = []
    window = SimpleNamespace(selected=VIEWER, status=lambda text: said.append(text()))
    trouble.show_viewer(window)
    assert shown == [VIEWER.hwnd] and said == ["Viewer: Fake viewer (scratch)  (restored from the taskbar)"]
    monkeypatch.setattr(trouble, "window_minimised", lambda hwnd: False)
    from taslation.capture.windows import Raised

    monkeypatch.setattr(trouble, "raise_window", lambda hwnd: raised.append(hwnd) or Raised(hwnd, 99))
    monkeypatch.setattr(trouble, "lower_window", lambda r: lowered.append(r))
    trouble.show_viewer(window)
    assert raised == [VIEWER.hwnd] and lowered == [Raised(VIEWER.hwnd, 0)]  # topmost a moment, then on top: no key


def test_choose_viewer_opens_the_viewer_list():
    calls = []
    box = SimpleNamespace(focus_set=lambda: calls.append("focus"))
    window = SimpleNamespace(window_box=box, tk=SimpleNamespace(call=lambda *args: calls.append(args)))
    trouble.choose_viewer(window)
    assert calls == ["focus", ("ttk::combobox::Post", box)]


# ------------------------------------------------------------------ where Ollama translates
def test_the_log_of_ollama_says_where_it_translates(tmp_path):
    log = tmp_path / "server.log"
    assert trouble.ollama_compute(log) == ""  # no log
    log.write_text('time=1 level=INFO source=types.go:32 msg="inference compute" id=0 library=CUDA compute=7.5\n',
                   encoding="utf-8")
    assert trouble.ollama_compute(log) == "gpu"
    log.write_text('time=1 level=INFO msg="inference compute" id=cpu library=cpu variant="" total="31.8 GiB"\n',
                   encoding="utf-8")
    assert trouble.ollama_compute(log) == "cpu"
    log.write_text('time=1 level=INFO msg="no compatible GPUs were discovered"\n', encoding="utf-8")
    assert trouble.ollama_compute(log) == "cpu"
    log.write_text("time=1 level=INFO msg=listening\n", encoding="utf-8")
    assert trouble.ollama_compute(log) == ""
    assert trouble.cpu_page_seconds(None) == 32 and trouble.cpu_page_seconds(0.5) == 16


# ------------------------------------------------------------------ the banner's buttons in the window
@pytest.fixture
def flow(hidden_root, tmp_path):
    yield Flow(hidden_root, tmp_path)


def _row_buttons(flow):
    return [str(b.cget("text")) if b is not None else None for b in flow.setup_banner.row_buttons]


def test_ollama_down_has_start_translator_again(flow, monkeypatch):
    started = []

    class Starter:
        def __init__(self, url, on_starting=None):
            started.append(url)

        def start(self, cancel=None):
            return None

    monkeypatch.setattr(jobs, "OllamaStarter", Starter)
    monkeypatch.setattr(flow, "_check_in_background", lambda: flow._post("health", problems=[], checked=True),
                        raising=False)
    flow._handle_event("health", {"problems": [DOWN]})
    assert _row_buttons(flow) == ["Start translator again"]
    flow.setup_banner.press("Start translator again")
    deadline = time.monotonic() + 5
    while flow._events.qsize() < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    flow.pump()
    assert started == [flow.settings.ollama_url] and flow.status_var.get() == "The translation program is running again."
    assert flow.setup_banner.texts() == []  # the check after it found Ollama running


def test_a_missing_model_has_download_model_not_install_cmd(flow, monkeypatch):
    flow._handle_event("health", {"problems": [MISSING]})
    assert flow.setup_banner.texts() == ["The translation model for this language, PLaMo 3 Translate 2B, is not "
                                         "installed. Press Download model to install it."]
    assert "install.cmd" not in flow.setup_banner.texts()[0] and _row_buttons(flow) == ["Download model"]
    offered = []
    monkeypatch.setattr(flow, "_plan", lambda language: SimpleNamespace(language=language), raising=False)
    monkeypatch.setattr(flow, "_offer_switch", lambda switch, before: offered.append(switch.language) or True,
                        raising=False)
    flow._model_state()["asked"].add("English")  # declined before: the button asks again
    flow.setup_banner.press("Download model")
    assert offered == ["English"]
    monkeypatch.setattr(flow, "_plan", lambda language: None, raising=False)
    monkeypatch.setattr(flow, "_check_in_background", lambda: None, raising=False)
    flow.setup_banner.press("Download model")
    assert flow.status_var.get() == "The translation model for English is installed already."


def test_the_viewers_trouble_comes_on_the_banner_with_its_button(flow, monkeypatch):
    monkeypatch.setattr(trouble, "window_minimised", lambda hwnd: False)
    flow.selected, flow._covered = VIEWER, True
    flow._watch_trouble(now=100.0)
    assert flow.setup_banner.texts()[0].startswith("The viewer stopped drawing because TASlation covers it")
    assert _row_buttons(flow) == ["Move TASlation aside"] and flow.setup_banner.winfo_manager() == "pack"
    moved = []
    monkeypatch.setattr(trouble, "move_aside", lambda window: moved.append(window))
    flow.setup_banner.press("Move TASlation aside")
    assert moved == [flow]
    flow._covered = False
    flow._watch_trouble(now=100.2)  # looked at every half second only
    assert _row_buttons(flow) == ["Move TASlation aside"]
    flow._watch_trouble(now=100.6)
    assert flow.setup_banner.texts() == [] and flow.setup_banner.winfo_manager() == ""
    flow.selected, flow._tied_said = None, (1, 2)
    flow._watch_trouble(now=101.2)
    assert _row_buttons(flow) == ["Choose viewer"]
    flow._handle_event("health", {"problems": [DOWN]})  # the setup's line first, then the viewer's
    assert _row_buttons(flow) == ["Start translator again", "Choose viewer"]


def test_a_runs_wait_has_its_button_on_the_band(flow):
    flow._scan = banner.ScanState(context=True)
    covered = Message("batch.waiting_covered")
    flow._scan.update(covered, "read", 3, 0, 9, 0.0, waiting=covered)
    flow._band = {"kind": "scan", "scan": flow._scan}
    flow._show_band()
    assert button_texts(flow.scan_band) == ["Move TASlation aside", "Finished reading", "Stop"]
    black = Message("batch.viewer_black")
    flow._scan.update(black, "read", 3, 0, 9, 1.0, waiting=black)
    flow._show_band()
    assert button_texts(flow.scan_band) == ["Show viewer", "Finished reading", "Stop"]
    flow._scan.update(Message("batch.read_page", page=4, lines=2, pages=4, bubbles=11, cached=0, seconds=9.0,
                              dropped=0), "read", 4, 0, 11, 2.0)
    flow._show_band()
    assert button_texts(flow.scan_band) == ["Finished reading", "Stop"]


def test_the_translator_on_the_processor_gets_a_line_once(flow):
    flow._handle_event("compute", {"where": "gpu"})
    assert flow.setup_banner.texts() == []
    flow._handle_event("compute", {"where": "cpu"})
    assert flow.setup_banner.texts() == ["The translator runs on the processor (no graphics card is used for it), so "
                                         "a page takes about 32 s to translate."]
    assert _row_buttons(flow) == ["Close"]
    flow.setup_banner.press("Close")
    assert flow.setup_banner.texts() == [] and flow._on_cpu is None
