"""The window's part of the session's analysis log and of developer measuring (`taslation.analysis`,
`taslation.devmeasure`).

* `start` (`App.__init__`): the analysis log started as the settings say (``analysis_log``: on in a source checkout,
  off in an installed copy). Developer measuring is off at every start, whatever was done before: nothing remembers it.
* `on_result` (each finished page as it reaches the window, before it becomes ``last_result``) and `close`: the
  ``"type": "ui"`` line of what the person saw of the page before - numbers and kinds only: the looks that found one of
  its lettered regions not on show, by why (``withheld``: `seethrough.unshown_tick`'s kinds, summed); each lettered
  region whose patch was not on show at its last look for no meant reason ("not drawn"), as an S1 case
  (``patch_not_shown``); a press on the page or a pane that could not make the viewer the foreground window
  (``keys_not_back``, S1); the side panes hidden over the page, by why (``panes``); the guard's hand-backs, the
  foreground's changes and the see-through window's counts since the line before (``counts``); the times the window
  took outside any page (``loose``).
* Developer measuring (a source checkout only: `devmeasure.available`): the Menu's cascade Developer measuring
  (`menu_entries`) - Measure (ticked while on: `switch_on` asks once, in a plain box that says what is kept and where,
  then starts a `devmeasure.Session`; again, `switch_off`), Open the folder, Delete all sessions... (asked first). While
  it is on, the right pane's lasting rows begin with DEV (`seethrough.foot_rows`), the pipeline reads every page afresh
  (`Pipeline.measuring`, a cache of the session's own, the series sheet and the book's marks read only:
  `devmeasure.ReadOnly`), and the input record watches the keys and the mouse only while the viewer or TASlation is
  in front (`devmeasure.InputWatch`).

The words of developer measuring are English and Japanese only (`WORDS`, by the window's language: Japanese for "ja",
else English), never put into the 16 languages: the mode exists only in a source checkout, for the developer's own
measurements, and no reader of an installed copy ever sees them."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from .. import analysis, devmeasure
from ..i18n import current as ui_language

log = logging.getLogger(__name__)

# (English and Japanese only: see the module's notes)
WORDS = {
    "en": {
        "menu": "Developer measuring",
        "measure": "Measure",
        "open": "Open the folder",
        "delete": "Delete all sessions...",
        "dev": "DEV",
        "start": "Start measuring",
        "cancel": "Cancel",
        "remove": "Delete",
        "keep": "Keep them",
        "confirm": ("Developer measuring keeps every page read from now on until it is switched off or TASlation "
                    "closes: the frame as captured, the page erased and the page lettered as pictures, each region's "
                    "readings and translation, the requests to the translator with their answers, the log's lines, "
                    "and the kind of each key pressed while the viewer or TASlation is in front "
                    "(never a character).\n\n"
                    "While it is on, every page is read and translated afresh: the saved translations are neither "
                    "read nor written, no line is reused, nothing is read ahead, and the series sheet and the book's "
                    "marks are read and not saved.\n\nIt is kept in:\n{folder}\n\nThat folder holds pages of your "
                    "books and their text: keep it private. Nothing of it is sent anywhere."),
        "ask_delete": "Delete the {n} kept session(s) of developer measuring? This cannot be undone.",
        "none": "No session of developer measuring is kept.",
        "deleted": "{n} session(s) deleted.",
    },
    "ja": {
        "menu": "開発者計測",
        "measure": "計測する",
        "open": "フォルダーを開く",
        "delete": "すべてのセッションを削除...",
        "dev": "DEV",
        "start": "計測を始める",
        "cancel": "キャンセル",
        "remove": "削除",
        "keep": "残す",
        "confirm": ("開発者計測は、オフにするか TASlation を閉じるまで、これから読むすべてのページを保存します: 取り込んだ"
                    "フレーム、消去したページと文字を入れたページの画像、各領域の読み取りと翻訳、翻訳器への依頼とその"
                    "回答、ログの行、そしてビューアーか TASlation が前面にある間に押されたキーの種類 (文字は保存しませ"
                    "ん)。\n\nオンの間は、どのページも新たに読み取って翻訳します: 保存済みの翻訳は読みも書きもせず、行"
                    "の再利用も先読みもせず、シリーズシートと本の印は読むだけで保存しません。\n\n保存先:\n{folder}\n\n"
                    "このフォルダーには本のページとその文章が入ります。他人に見せないでください。どこにも送信されませ"
                    "ん。"),
        "ask_delete": "開発者計測で保存したセッション {n} 件をすべて削除しますか? 元に戻せません。",
        "none": "開発者計測のセッションは保存されていません。",
        "deleted": "{n} 件のセッションを削除しました。",
    },
}
# the side panes' reasons for hiding (`seethrough._clear_of_page`) as the log names them
PANE_CODES = {"its place lay over the page box of the frame on show": "over_page",
              "its place lay inside the capture area set by hand": "in_area",
              "the frame on show has no page box, and its place came from an older page's": "no_box"}


def word(key: str) -> str:
    """Developer measuring's *key* in the window's language: Japanese for "ja", else English."""
    return WORDS["ja" if ui_language() == "ja" else "en"][key]


def _code(text: Any) -> str:
    """A kind as the log names it: lowercase, spaces as "_", no apostrophe; of a part in brackets only a dialog's
    kind is kept ("a dialog (viewer chooser)": ``a_dialog:viewer_chooser``; a window class is left out).
    Anything else that is not a name becomes "other" as it is written (`analysis.clean`)."""
    head, _, inner = str(text).replace("'", "").partition(" (")
    code = "_".join(head.strip().lower().split())
    if code.endswith("a_dialog") and inner.strip(") "):
        code += ":" + "_".join(inner.strip(") ").lower().split())
    return code


# ------------------------------------------------------------------ the analysis log's window lines
def start(app: Any) -> None:
    """The analysis log started as the settings say (`analysis.start`); developer measuring off."""
    settings = getattr(app, "settings", None)
    try:
        analysis.start(getattr(settings, "state_dir", None), getattr(settings, "analysis_log", "auto"))
    except OSError:
        log.info("the analysis log could not be started")
    app._measure = None  # the developer measuring session while it is on (never at a start)
    app._measure_watch = None
    app._measure_real = None  # the stores the session stands in for
    app._measure_seen = _counters(app)  # the window's counts as the last ui line left them
    app._measure_page = None  # (the page whose ui line is written next: key, the analysis log's number)


def _counters(app: Any) -> dict[str, dict[str, float]]:
    over = getattr(app, "_see_through", None)
    counts = getattr(over, "counts", None)

    def numbers(value: Any) -> dict[str, float]:
        return {str(k): float(v) for k, v in dict(value or {}).items()
                if isinstance(v, (int, float)) and not isinstance(v, bool)}

    return {"over": numbers(counts if isinstance(counts, dict) else {}),
            "guarded": numbers(getattr(app, "_see_guarded", None)),
            "foreground": numbers(getattr(app, "_see_foreground", None)),
            "front": numbers(getattr(app, "_see_front", None)),
            "panes": {PANE_CODES.get(k, k): v for k, v in numbers(getattr(app, "_see_pane_hid", None)).items()}}


def ui_line(app: Any) -> dict[str, Any] | None:
    """The ``ui`` line of the page on show until now (see the module's notes), the window's counts taken as its
    start for the next one; None while the log is off."""
    if not analysis.on():
        return None
    before = getattr(app, "_measure_seen", None) or {}
    now = _counters(app)
    app._measure_seen = now
    deltas: dict[str, dict[str, float]] = {}
    for part, values in now.items():
        old = before.get(part, {})
        got: dict[str, float] = {}
        for k, v in values.items():
            if v - old.get(k, 0.0):
                got[_code(k)] = got.get(_code(k), 0.0) + v - old.get(k, 0.0)
        deltas[part] = {k: (int(v) if float(v).is_integer() else round(v, 1)) for k, v in got.items()}
    result = getattr(app, "last_result", None)
    line: dict[str, Any] = {"type": "ui", "page": int(getattr(result, "analysis_n", 0) or 0)}
    cases: list[dict[str, Any]] = []
    withheld: dict[str, int] = {}
    original = getattr(result, "original", None)
    entry = (getattr(app, "_see_unshown", None) or {}).get(id(original)) if original is not None else None
    if entry:
        said = app.__dict__.setdefault("_measure_said", {})  # page key -> what its lines said (said once)
        told = said.pop(id(original), None) or {"kinds": {}, "cases": set()}
        said[id(original)] = told
        for old in list(said)[:-64]:
            said.pop(old, None)
        for kind, n in (entry.get("kinds_seen") or {}).items():
            more = int(n) - int(told["kinds"].get(kind, 0))
            told["kinds"][kind] = int(n)
            if more > 0:
                withheld[_code(kind)] = withheld.get(_code(kind), 0) + more
        boxes = dict((entry.get("last") or {}).get("boxes") or ())
        for i, seen in sorted((entry.get("regions") or {}).items()):
            gone = seen.get("unshown_at") is not None and (seen.get("shown_at") is None
                                                           or seen["unshown_at"] > seen["shown_at"])
            if gone and seen.get("kind") == "not drawn" and i not in told["cases"]:
                told["cases"].add(i)
                cases.append({"code": "patch_not_shown", "level": analysis.LEVELS["patch_not_shown"], "i": int(i),
                              "box": [int(v) for v in boxes.get(i, (0, 0, 0, 0))],
                              "shown_before": seen.get("shown_at") is not None})
        line["looks"] = int(entry.get("looks", 0))
    failed = int(deltas["over"].get("woke_failed", 0) or 0)
    if failed:
        cases.append({"code": "keys_not_back", "level": analysis.LEVELS["keys_not_back"], "n": failed})
    loose_times, loose_counts = analysis.log().take_loose() if analysis.log() is not None else ({}, {})
    line.update({"withheld": withheld, "panes": deltas.pop("panes"), "cases": cases,
                 "counts": {f"{part}.{k}": v for part, values in deltas.items() for k, v in values.items()},
                 "loose": {k: [round(1000 * v[0], 2), int(v[1])] for k, v in sorted(loose_times.items())},
                 "loose_counts": dict(loose_counts), "dev": on(app)})
    return analysis.write(line)


def on_result(app: Any, result: Any) -> None:
    """A finished page reaches the window (before it becomes ``last_result``): the ``ui`` line of the page before."""
    if not analysis.on():
        return
    try:
        if getattr(app, "last_result", None) is not None:
            ui_line(app)
    except Exception:  # noqa: BLE001 - the log never stops a page
        log.debug("the analysis log's window line could not be written", exc_info=True)


def close(app: Any) -> None:
    """The window closes (after its last save): the last ``ui`` line; developer measuring ended (its files written,
    its stores deleted)."""
    try:
        if analysis.on() and getattr(app, "last_result", None) is not None:
            ui_line(app)
    except Exception:  # noqa: BLE001 - the window closes whatever happens here
        pass
    session = getattr(app, "_measure", None)
    if session is not None:
        app._measure = None
        _stop_watch(app)
        try:
            session.close()
        except Exception:  # noqa: BLE001
            pass


# ------------------------------------------------------------------ developer measuring
def on(app: Any) -> bool:
    """Whether developer measuring is on."""
    return getattr(app, "_measure", None) is not None


def menu_entries(app: Any, menu: Any, asking: Callable[[Callable[[], Any]], Callable[[], None]]) -> None:
    """The Menu's cascade Developer measuring (a source checkout only; nothing in an installed copy): Measure (ticked
    while on), Open the folder, Delete all sessions.... *asking* wraps a command that opens a box (the reader asked)."""
    if not devmeasure.available():
        return
    import tkinter as tk

    sub = getattr(menu, "_see_dev", None)
    if sub is None:
        sub = menu._see_dev = tk.Menu(menu, tearoff=0)
    sub.delete(0, "end")
    menu._see_dev_on = tk.BooleanVar(menu, value=on(app))  # (kept: Tk's variable)
    sub.add_checkbutton(label=word("measure"), variable=menu._see_dev_on, command=asking(lambda: toggle(app)))
    sub.add_command(label=word("open"), command=asking(lambda: open_folder(app)))
    sub.add_command(label=word("delete"), command=asking(lambda: delete_all(app)))
    menu.add_cascade(label=word("menu"), menu=sub)


def toggle(app: Any) -> bool:
    """Measure in the Menu: on when off (asked first), off when on. Whether it is on now."""
    if on(app):
        switch_off(app)
        return False
    return switch_on(app)


def switch_on(app: Any, ask: bool = True) -> bool:
    """Developer measuring started (see the module's notes), *ask*: after the plain box that says what is kept and
    where (the e2e tool's switch asks nothing). Refused in an installed copy (`devmeasure.available`: no such mode
    there, and `devmeasure.Session` refuses too). Whether it is on."""
    if on(app):
        return True
    if not devmeasure.available():
        return False
    state_dir = app.settings.state_dir
    if ask:
        from .dialogs.caches import ask as ask_box

        text = word("confirm").format(folder=devmeasure.base_folder(state_dir))
        if not ask_box(app, text, word("start"), word("cancel"), icon="warning"):
            return False
    try:
        session = devmeasure.Session(state_dir)
    except (devmeasure.Refused, OSError) as e:
        log.info("developer measuring could not start (%s)", type(e).__name__)
        return False
    app._measure = session
    _stand_in(app, session)
    viewer_root = lambda: devmeasure.root_of(int(getattr(getattr(app, "selected", None), "hwnd", 0) or 0))  # noqa: E731
    me = os.getpid()

    def in_front() -> bool:
        front = devmeasure.foreground_root()
        return bool(front) and (front == viewer_root() or devmeasure.window_pid(front) == me)

    watch = devmeasure.InputWatch(session.input, in_front, lambda hwnd: devmeasure.window_pid(hwnd) == me,
                                  lambda hwnd: bool(hwnd) and devmeasure.root_of(hwnd) == viewer_root())
    watch.start()
    app._measure_watch = watch
    log.info("developer measuring on")
    return True


def switch_off(app: Any) -> None:
    """Developer measuring ended: the hooks removed, the stores given back to the pipeline, the session's files written
    and its own stores deleted (on the worker, after the job under way)."""
    session = getattr(app, "_measure", None)
    if session is None:
        return
    app._measure = None
    _stop_watch(app)
    real = getattr(app, "_measure_real", None)
    app._measure_real = None

    def back() -> None:
        if real is not None:
            app.store, app.annotation_store, app.glossary_store = real
        pipeline = getattr(app, "pipeline", None)
        if pipeline is not None:
            pipeline.measuring = False
            _fresh(pipeline)
        session.close()

    _on_worker(app, back)


def _stop_watch(app: Any) -> None:
    watch = getattr(app, "_measure_watch", None)
    app._measure_watch = None
    if watch is not None:
        try:
            watch.stop()
        except Exception:  # noqa: BLE001
            pass


def _stand_in(app: Any, session: Any) -> None:
    """The pipeline given the session's stores (on the worker, after the job under way): a cache of its own, the
    series sheet and the book's marks read only; every page read afresh (`Pipeline.measuring`)."""
    from ..cache import CacheStore

    real = (app.store, app.annotation_store, app.glossary_store)
    app._measure_real = real

    def swap() -> None:
        if getattr(app, "_measure", None) is not session:
            return  # (switched off meanwhile)
        app.store = CacheStore(session.stores / "cache")
        app.annotation_store = devmeasure.ReadOnly(real[1], "book's marks")
        app.glossary_store = devmeasure.ReadOnly(real[2], "series sheet")
        pipeline = getattr(app, "pipeline", None)
        if pipeline is not None:
            pipeline.measuring = True
            _fresh(pipeline)

    _on_worker(app, swap)


def _fresh(pipeline: Any) -> None:
    """The pipeline's stores let go (the next page opens them anew: `JobsMixin._ensure_cache`) and this session's
    lettered pages forgotten."""
    try:
        pipeline.set_cache(None)
    except Exception:  # noqa: BLE001
        pass
    forget = getattr(pipeline, "forget_shown", None)
    if callable(forget):
        forget()


def _on_worker(app: Any, job: Callable[[], None]) -> None:
    jobs = getattr(app, "_jobs", None)
    if jobs is None:
        job()
    else:
        jobs.put(job)


def open_folder(app: Any) -> None:
    """Open the folder of the kept sessions in Explorer (made first)."""
    folder = devmeasure.base_folder(app.settings.state_dir)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(str(folder))  # noqa: S606 - the person's own folder, at their click
    except OSError as e:
        log.info("the folder of developer measuring could not be opened (%s)", type(e).__name__)


def delete_all(app: Any) -> int:
    """Delete all sessions... (asked first; the one under way stays): how many were deleted."""
    from .dialogs.caches import ask as ask_box, tell

    state_dir = app.settings.state_dir
    current = getattr(getattr(app, "_measure", None), "folder", None)
    kept = [s for s in devmeasure.sessions(state_dir) if s != current]
    if not kept:
        tell(app, word("none"), icon="info")
        return 0
    if not ask_box(app, word("ask_delete").format(n=len(kept)), word("remove"), word("keep"), no_first=True,
                   icon="warning"):
        return 0
    gone = devmeasure.delete_sessions(state_dir, keep=current)
    tell(app, word("deleted").format(n=gone), icon="info")
    return gone
