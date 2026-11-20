"""The page strip in the real window with a made-up run (dev tool): `tests/fake_strip.FakeRun` sends a whole-book run's
page events into a TASlation window at a given rate, while the Tk event loop's lateness is measured, the strip's memory
taken, and pictures of the window taken from TASlation's own window only.

    python tools/strip_demo.py [--pages 200] [--rate 3] [--shots DIR]

No viewer is chosen and no other window is touched: the window list the app sees is empty, every function that sends a
key or a click to a window raises, and any choice of a viewer ends the demo. The state folder is a temporary one; the
pictures (only with --shots) are of TASlation's own window, made-up pages only. Prints the numbers as JSON."""

from __future__ import annotations

import argparse
import ctypes
import json
import statistics
import sys
import tempfile
import threading
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from fake_strip import FakeRun  # noqa: E402

from taslation import notice  # noqa: E402
from taslation.capture import windows as capture_windows  # noqa: E402
from taslation.config import Settings  # noqa: E402
from taslation.i18n import save_ui_flag, save_ui_language, set_language  # noqa: E402
from taslation.ollama_start import OllamaStarter  # noqa: E402
from taslation.ui import app as app_mod  # noqa: E402
from taslation.ui import reading as reading_mod  # noqa: E402
from taslation.ui import strip as strip_mod  # noqa: E402
from taslation.ui import translator as translator_mod  # noqa: E402
from taslation.ui import viewers as viewers_mod  # noqa: E402
from taslation.ui.dialogs.help import FIRST_STEPS_FLAG  # noqa: E402

PROBE_MS = 20
SHOOTING: list[tuple[float, float]] = []  # when pictures were taken (the loop waits for them: left out of the numbers)


class ProcessMemory(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t), ("PrivateUsage", ctypes.c_size_t)]


def private_mb() -> float:
    info = ProcessMemory()
    info.cb = ctypes.sizeof(info)
    kernel32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(info), info.cb)
    return info.PrivateUsage / 2 ** 20


def guard(sent: list[str]) -> None:
    """Nothing reaches another window: no window to choose, every way to send a key or a click raises."""
    viewers_mod.list_windows = lambda include_own=False: []
    OllamaStarter.start = lambda self, cancel=None: None
    app_mod.App._job_init = lambda self: None  # no models, no Ollama: the strip needs none

    def trap(*_a, **_k):
        sent.append("key or click")
        raise RuntimeError("the demo sends nothing to any window")

    for module in (capture_windows, translator_mod, reading_mod):
        for name in ("post_key", "post_click", "press_key", "press_briefly"):
            if hasattr(module, name):
                setattr(module, name, trap)

    chosen = app_mod.App._on_window_selected

    def refuse(self):
        if self.window_box.current() >= 0:
            print("a viewer was chosen: the demo ends", file=sys.stderr)
            self.destroy()
            sys.exit(2)
        chosen(self)

    app_mod.App._on_window_selected = refuse


def shoot(app, shots: Path | None, name: str) -> str:
    """TASlation's own window, as Windows draws it (never the screen), into *shots*."""
    if shots is None:
        return ""
    began = time.perf_counter()
    app.update()
    hwnd = app._own_hwnd()
    image = capture_windows.capture_window(hwnd, client_only=True, allow_screen_fallback=False)
    shots.mkdir(parents=True, exist_ok=True)
    path = shots / f"{name}.png"
    image.save(path)
    SHOOTING.append((began, time.perf_counter() + 0.1))
    return str(path)


def full_screen(app, on: bool) -> None:
    """The window's full screen as `ReadingMixin.enter_reading` makes it (no viewer is chosen in the demo, so that
    cannot be called): the bars away, the page area black, the window over the whole monitor."""
    app.reading = on
    if on:
        for widget in (*app._bars, app.notes_label, app.status_bar):
            widget.pack_forget()
        app.config(menu="")
        app.canvas.configure(bg="#000000")
        app.attributes("-fullscreen", True)
    else:
        app.attributes("-fullscreen", False)
        app.canvas.configure(bg="#202020")
        app.canvas.pack_forget()
        for widget in app._bars:
            widget.pack(fill="x")
        app.canvas.pack(fill="both", expand=True)
        app.status_bar.pack(fill="x")
    app.update()
    app._redisplay()


def side_main(args) -> int:
    """The indicator beside the page in the real window, a scripted story of normal reading: pages done, one being
    worked on, some waiting, two that went by too fast, two updated, the page on show moving; then 200 pages, a book
    read left to right, the Reader's three status slots, the corner brackets of a page whose words changed, the dark
    theme, and with --full the full screen. Made-up pages and words only (`tests/fake_side`); pictures of TASlation's
    own window only."""
    import fake_side
    from fake_side import Cache, result, stage, story

    from taslation.messages import Message
    from taslation.ui import side as side_mod

    sent: list[str] = []
    guard(sent)
    state = Path(tempfile.mkdtemp(prefix="taslation-side-"))
    notice.save_country(state, "JP")
    notice.dismiss(state, "en")
    save_ui_language(state, "en")
    save_ui_flag(state, FIRST_STEPS_FLAG)
    settings = Settings(state_dir=state)
    settings.validate()
    app = app_mod.App(settings, auto=False)
    app.canvas.trim = False  # (the made-up page drawn whole: its bubbles on a plain ground are not cut out)
    cache = Cache()
    app.pipeline = fake_side.pipeline(cache)
    shots, found, steps = args.shots, {}, []
    post = lambda kind, data: app._handle_event(kind, data)  # noqa: E731 - as the event pump hands them over

    def show(image, result_on_show=None):
        app._live, app.last_result = image, result_on_show
        app._redisplay()

    def size(w, h):
        app.geometry(f"{w}x{h}+30+30")
        app.update()

    def fresh(rtl=True):
        side_mod.clear(app)
        app.pipeline.rtl = rtl
        app._side.slot = type(app._side.slot)()

    def busy(frame, progress):  # a job on the page on show, as `StatusMixin._go_busy` starts one
        app._go_busy()
        app._busy_shown, app._job_frame, app._fill, app._progress = True, frame, None, progress

    def idle():  # the job done, as the window ends one
        app.busy, app._job_frame = False, None
        app._set_busy(False)

    def scene(name, wait=700):
        def deco(fn):
            steps.append((name, fn, wait))
            return fn
        return deco

    @scene("01-window-wide-spread-column")
    def _():
        size(1560, 1000)
        fresh()
        story(post, pages=12, on_show=12, spread=True, missed=(10, 11), working=(7,), waiting_from=8)
        show(fake_side.page(12, True))

    @scene("02-window-wide-spread-updated", wait=500)
    def _():
        for seq in (2, 4):
            app._side.model.screens[seq].updated = True
        app._side.view.redraw_marks()

    @scene("03-window-narrow-single-rail")
    def _():
        size(720, 1000)
        fresh()
        story(post, pages=12, on_show=6, missed=(10, 11), working=(7,), waiting_from=8)
        show(fake_side.page(6))

    @scene("04-window-narrow-single-rail-updated", wait=500)
    def _():
        for seq in (2, 4):
            app._side.model.screens[seq].updated = True
        app._side.view.redraw_marks()

    @scene("05-window-narrow-spread-rail-kept-clear")
    def _():  # (a spread fills the narrow window's width: its exit side is kept clear for the rail)
        show(fake_side.page(6, True))

    @scene("06-window-200-pages-column", wait=1500)
    def _():
        size(1000, 1000)
        fresh()
        story(post, pages=200, on_show=150, missed=(40, 41, 120), working=(147, 148), waiting_from=149)
        show(fake_side.page(150))

    @scene("07-window-200-pages-rail", wait=900)
    def _():
        size(720, 1000)
        show(fake_side.page(150))

    @scene("08-window-left-to-right-column")
    def _():
        size(1100, 1000)
        fresh(rtl=False)
        story(post, pages=9, on_show=5, missed=(8,), working=(6,), waiting_from=7)
        show(fake_side.page(5))

    @scene("09-reader-slot-reading", wait=1300)
    def _():
        size(720, 1000)
        fresh()
        story(post, pages=6, on_show=6, waiting_from=5)
        frame = fake_side.scribbled(fake_side.page(6), fake_side.bubble_boxes(6))
        show(frame)
        busy(frame, Message("pipeline.stage_reading", total=3))

    @scene("10-reader-slot-error", wait=600)
    def _():
        idle()
        failed = result(6, ["", "", ""], error="made-up failure")
        show(failed.original, failed)

    @scene("11-reader-slot-nothing-to-read", wait=600)
    def _():
        empty = result(6, [])
        empty.regions = []
        show(empty.original, empty)
        side_mod.after(app, "result", {"result": empty}, None)

    @scene("12-brackets-after-words-changed", wait=900)
    def _():
        fresh()
        story(post, pages=6, on_show=4, waiting_from=6)
        app.update()
        seen = result(4, ["Who's there?", "", "Wait for me!"])
        show(seen.original, seen)  # page 4 seen lettered, one bubble still in its original
        cache.put(4, ["Who's there?", "Wait for me!"])
        post("page_on_show", {"seq": 5})
        other = result(5, ["Over here.", "Hurry!", "Fine."])
        show(other.original, other)
        cache.put(4, ["Who is there?", "Look, a cat.", "Wait for me!"])  # the work behind finished page 4
        stage(post, 4, translate="done")
        app.update()

    @scene("13-brackets-on-the-page-turned-back-to", wait=600)
    def _():
        found["diamond_before_turning_back"] = app._side.model.screens[4].updated
        post("page_on_show", {"seq": 4})
        app.update()
        again = result(4, ["Who is there?", "Look, a cat.", "Wait for me!"])
        show(again.original, again)

    @scene("14-brackets-gone-after-read-time", wait=3600)
    def _():
        found["brackets_on_show"] = len(app.canvas.brackets)

    @scene("15-dark-theme-wide-spread")
    def _():
        found["diamond_after_read_time"] = app._side.model.screens[4].updated
        settings.theme = "dark"
        app._colours_again()
        size(1560, 1000)
        fresh()
        story(post, pages=12, on_show=12, spread=True, missed=(10, 11), working=(7,), waiting_from=8)
        show(fake_side.page(12, True))

    @scene("16-dark-theme-narrow-rail-slot", wait=1300)
    def _():
        size(720, 1000)
        fresh()
        story(post, pages=12, on_show=12, missed=(10, 11), working=(7,), waiting_from=8)
        frame = fake_side.page(12)
        show(frame)
        busy(frame, Message("pipeline.stage_translating", bubbles=3))

    if args.full:
        @scene("17-full-screen-single-column", wait=1300)
        def _():
            idle()
            settings.theme = "light"
            app._colours_again()
            size(900, 900)
            fresh()
            story(post, pages=12, on_show=12, missed=(10, 11), working=(7,), waiting_from=8)
            for seq in (2, 4):
                stage(post, seq, translate="done")
            full_screen(app, True)
            show(fake_side.page(12))
            for seq in (2, 4):
                app._side.model.screens[seq].updated = True
            app._side.view.redraw_marks()

        @scene("18-full-screen-spread-column", wait=1000)
        def _():
            show(fake_side.page(12, True))

        @scene("19-full-screen-single-rail-slot", wait=1400)
        def _():
            settings.side_indicator = "rail"
            frame = fake_side.page(12)
            show(frame)
            busy(frame, Message("pipeline.stage_reading", total=3))

        @scene("20-full-screen-error-slot", wait=700)
        def _():
            idle()
            settings.side_indicator = "column"
            failed = result(12, ["", "", ""], error="made-up failure")
            show(failed.original, failed)

    def run(i=0):
        if i > 0:
            name = steps[i - 1][0]
            found[name] = shoot(app, shots, name)
        if i >= len(steps):
            if args.full:
                full_screen(app, False)
            app.quit()
            return
        name, fn, wait = steps[i]
        fn()
        app.after(wait, lambda: run(i + 1))

    app.after(600, run)
    app.mainloop()
    model = app._side.model
    print(json.dumps({"scenes": len(steps), "keys_or_clicks_sent": len(sent), "screens_at_end": len(model),
                      "timer_running_at_end": app._side.view.animating,
                      **{k: v for k, v in found.items() if not isinstance(v, str)},
                      "shots": [v for v in found.values() if isinstance(v, str) and v]}, indent=1))
    app.destroy()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pages", type=int, default=200)
    ap.add_argument("--rate", type=float, default=3.0, help="pages a second")
    ap.add_argument("--shots", type=Path, default=None, help="folder for pictures of TASlation's own window")
    ap.add_argument("--side", action="store_true", help="the indicator beside the page in normal reading instead")
    ap.add_argument("--full", action="store_true", help="with --side: the full screen too")
    args = ap.parse_args()
    if args.side:
        return side_main(args)
    sent: list[str] = []
    guard(sent)
    state = Path(tempfile.mkdtemp(prefix="taslation-strip-"))
    notice.save_country(state, "JP")
    notice.dismiss(state, "en")
    save_ui_language(state, "en")
    save_ui_flag(state, FIRST_STEPS_FLAG)
    settings = Settings(state_dir=state)
    settings.validate()
    app = app_mod.App(settings, auto=False)
    app.update()
    late: list[float] = []
    handled: list[float] = []
    own_stage = app_mod.App._on_page_stage

    def timed(self, data):
        t0 = time.perf_counter()
        own_stage(self, data)
        handled.append((time.perf_counter() - t0) * 1000)

    app_mod.App._on_page_stage = timed
    due = [time.perf_counter() + PROBE_MS / 1000]

    def probe():
        now = time.perf_counter()
        late.append((now, max(0.0, (now - due[0]) * 1000)))
        due[0] = now + PROBE_MS / 1000
        app.after(PROBE_MS, probe)

    run = FakeRun(lambda kind, data: app._post(kind, **data), pages=args.pages)
    app.batch = run  # (as the run's reader: in a run, following the reader)
    strip_mod.new_run(app)
    mem_before = private_mb()
    shots, found = args.shots, {}
    worker = threading.Thread(target=run.run, kwargs={"rate": args.rate}, daemon=True)
    started = time.monotonic()
    app.after(PROBE_MS, probe)
    worker.start()
    half, clicked = args.pages // 2, []

    def mid():  # (a picture is taken a while after a change: a window's frame comes once it has drawn it)
        found["mid"] = shoot(app, shots, "1-light-mid-run")
        seq = app._strip_model.order[-3]
        before = app._picture()[0]
        app._pick_page(seq)  # a click on a thumbnail: a line that says to open the page in the viewer, nothing shown
        clicked.append({"page": seq, "picture_unchanged": app._picture()[0] is before})

        def shown():
            found["click"] = shoot(app, shots, "2-light-thumbnail-clicked")

        app.after(800, shown)

    def watch():
        if not found.get("mid") and len(app._strip_model) >= half:
            mid()
            found.setdefault("mid", "taken")
        if worker.is_alive():
            app.after(200, watch)
        else:
            app.after(600, finish)

    def finish():
        found["end"] = shoot(app, shots, "3-light-end")
        model = app._strip_model
        found["unfinished_at_end"] = len(model.unfinished())
        set_language("ja")
        app._rebuild_ui()

        def ja():
            found["ja"] = shoot(app, shots, "4-light-end-ja")
            set_language("en")
            app.quit()

        app.after(1200, ja)

    app.after(200, watch)
    app.mainloop()
    elapsed = time.monotonic() - started
    every = [ms for _t, ms in late]
    late = [ms for t, ms in late if not any(a <= t <= b for a, b in SHOOTING)]
    model = app._strip_model
    result = {
        "pages": len(model), "rate": args.rate, "seconds": round(elapsed, 1),
        "event_loop_late_ms": {"p50": round(statistics.median(late), 1),
                               "p99": round(sorted(late)[int(len(late) * 0.99) - 1], 1), "max": round(max(late), 1),
                               "probes": len(late), "max_with_pictures": round(max(every), 1)},
        "page_stage_handler_ms": {"p50": round(statistics.median(handled), 2),
                                  "p99": round(sorted(handled)[int(len(handled) * 0.99) - 1], 2),
                                  "max": round(max(handled), 2), "events": len(handled)},
        "strip_thumbnails_kb": round(model.memory_bytes() / 1024),
        "process_private_mb_delta": round(private_mb() - mem_before, 1),
        "fake_run_pictures_mb": round(len(run.images) * 600 * 860 * 3 / 2 ** 20, 1),
        "photos": len(app.page_strip._photos), "timer_running_at_end": app.page_strip.animating,
        "thumbnail_click": clicked, "keys_or_clicks_sent": len(sent),
        "unfinished_at_end": found.get("unfinished_at_end"),
        "shots": [v for k, v in found.items() if k in ("mid", "click", "end", "ja") and v],
    }
    print(json.dumps(result, indent=1))
    app.batch = None
    app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
