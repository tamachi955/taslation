"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: screens read as the window reads them, numbers only.

For a case reproduced on pictures of the viewer's screen kept on this computer (the frames of a developer measuring
session, `taslation.devmeasure`'s ``pNNNN-frame.png``, or any folder of screen pictures): each picture is taken as
the viewer's frame at its own pixel size (nothing scaled), read and translated by the pipeline as the page on show is
(`Pipeline.page_on_show`: a spread's next page unit read beside while the one before is translated, the lines sent to
the translator as they are read), one after the other in the order given and again in the reverse order, and the
analysis log's numbers printed (`taslation.analysis`): per screen its time and its stages, each unit's reading, the
time from the first unit's last request to the next unit's first, the readers' calls on the processor and on the
GPU; then the summary's tables of the page units and of the watch (`analysis.unit_lines`, `analysis.watch_lines`).

    python tools/screens_read.py FOLDER --glob "p*-frame.png" --pick 12,30,7 --margins beside --port 11436
    python tools/screens_read.py a.png b.png --margins 0,85,0,0 --canned 300 --watch compare

NUMBERS ONLY. No reading, no translation and no file's name is printed or kept by the tool: a screen is named by its
place in the list and the first number in its file's name; the program's log goes to the tool's own state folder
(made in the computer's temporary folder unless --state), which is deleted at the end unless --keep-state; there is no
cache. The pictures are read by the program alone, never shown.

* --margins: the capture area's margins (left,top,right,bottom), or "beside": each picture's from the measuring
  session's page file beside it (``pNNNN.json``: its analysis line's ``margins``), else the settings' default.
* the translator: an Ollama server of the tool's own on --port (started for the run with the models of this computer's
  Ollama, stopped after; never Ollama's usual port, 11434), or --canned MS (a stand-in that answers each line after
  MS ms, no model: what the readers do while a request is under way, without the model's work on the GPU).
* --watch compare|same|off: a thread doing the see-through window's look at the screen on show --watch-rate times a
  second while each screen is read, each time with a fresh copy of the frame as the capture makes it: "compare" -
  `seethrough.visible` of the last three screens' signs at every look; "same" - the window's own look
  (`SeeThrough._decide`: a frame of the same bytes as the one compared last is not compared again).
* --gate FILE: a lock file the tools of this computer share the GPU by (made with the tool's name and pid, waited for
  while another holds it and it is under 15 minutes old), taken before the models load and dropped at the end.
* --order given,reversed and --reps N: the list read so, each order N times (the readers' memos emptied before every
  screen, so each is read whole).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TOOLS = Path(__file__).resolve().parent
for _p in (ROOT, TOOLS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

USUAL_PORT = 11434  # Ollama's usual port: a person's own server, never this tool's
GATE_STALE_S = 900.0
REAL_STATES = (".taslation", ".selftrans", ".cleantrans")  # the program's own state folders: never the tool's
NUMBER = re.compile(r"\d+")


# ------------------------------------------------------------------ the screens
def number_of(path: Path) -> int:
    """The first number in *path*'s name (-1 for none)."""
    found = NUMBER.search(path.stem)
    return int(found.group()) if found else -1


def screens_of(given: list[str], glob: str, pick: list[int]) -> list[Path]:
    """The pictures of *given* (folders: their files matching *glob*, sorted by name; files as they are), those whose
    first number is in *pick* only and in its order when it is given."""
    found: list[Path] = []
    for item in given:
        path = Path(item)
        if path.is_dir():
            found.extend(sorted(p for p in path.glob(glob) if p.is_file()))
        elif path.is_file():
            found.append(path)
        else:
            raise SystemExit(f"no such folder or picture: the {len(found) + 1}. given")
    if pick:
        by = {}
        for p in found:
            by.setdefault(number_of(p), p)
        missing = [n for n in pick if n not in by]
        if missing:
            raise SystemExit(f"no picture numbered {missing}")
        found = [by[n] for n in pick]
    if not found:
        raise SystemExit("no pictures")
    return found


def margins_beside(path: Path) -> tuple[int, int, int, int] | None:
    """The margins the measuring session's page file beside *path* holds (``<stem up to its first '-'>.json``, its
    analysis line's ``margins``: four numbers), None where there is none. Nothing else of the file is used."""
    beside = path.with_name(path.stem.split("-")[0] + ".json")
    try:
        data = json.loads(beside.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    got = (data.get("analysis") or {}).get("margins") if isinstance(data, dict) else None
    if isinstance(got, list) and len(got) == 4 and all(isinstance(v, (int, float)) for v in got):
        return tuple(int(v) for v in got)  # type: ignore[return-value]
    return None


def margins_arg(text: str) -> tuple[int, int, int, int] | str | None:
    if not text:
        return None
    if text == "beside":
        return "beside"
    parts = [int(v) for v in text.split(",")]
    if len(parts) != 4 or any(v < 0 for v in parts):
        raise argparse.ArgumentTypeError("left,top,right,bottom: four numbers of 0 or more")
    return tuple(parts)  # type: ignore[return-value]


# ------------------------------------------------------------------ the gate
def take_gate(gate: Path, name: str) -> None:
    said = 0.0
    while True:
        try:
            fd = os.open(str(gate), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                age = time.time() - gate.stat().st_mtime
            except FileNotFoundError:
                continue
            if age > GATE_STALE_S:
                try:
                    gate.unlink()
                except FileNotFoundError:
                    pass
                continue
            if time.monotonic() - said > 60:
                print(f"[gate] held ({age:.0f} s old): waiting", flush=True)
                said = time.monotonic()
            time.sleep(5)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"{name} {time.strftime('%Y-%m-%d %H:%M:%S')} pid {os.getpid()}\n")
        return


def drop_gate(gate: Path, name: str) -> None:
    try:
        text = gate.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return
    if text.startswith(name) and f"pid {os.getpid()}" in text:
        gate.unlink()


# ------------------------------------------------------------------ the watch
class Watch:
    """The see-through window's look at the screen on show, *rate* times a second on a thread of its own: a fresh copy
    of the frame (BGRA, as the capture makes it) each time, then `visible` of the last three screens' signs
    ("compare") or the window's own look (`SeeThrough._decide`, "same")."""

    def __init__(self, mode: str, rate: float) -> None:
        self.mode, self.rate = mode, rate
        self.frame: Any = None
        self.box: tuple[int, int, int, int] | None = None
        self.sets: list[Any] = []
        self.stop = threading.Event()
        self.looks = 0
        self.ms = 0.0
        self.copy_ms = 0.0
        self.thread = threading.Thread(target=self._run, name="screens-watch", daemon=True)
        self._window: Any = None

    def show(self, rgb: Any, margins: tuple[int, int, int, int]) -> None:
        """The screen *rgb* on show now, its page's sign kept among the last three."""
        import numpy as np

        from taslation import seethrough as st

        height, width = rgb.shape[:2]
        bgra = np.empty((height, width, 4), np.uint8)
        bgra[..., :3] = rgb[..., ::-1]
        bgra[..., 3] = 255
        left, top, right, bottom = margins
        area = (left, top, width - right, height - bottom)
        sign = st.page_sign(rgb, area, (area[0], area[2]))
        store = getattr(self, "_store", None) or st.SetStore()
        self._store = store
        store.put(store.serial + 1, (width, height), (), final=True, sign=sign)
        self.sets = list(store.sets)
        self.frame, self.box = bgra, (0, 0, width, height)

    def _run(self) -> None:
        import numpy as np

        from taslation import seethrough as st
        from taslation.capture import seethrough as window

        if self.mode == "same":
            self._window = window.SeeThrough()
            self._window._dpi = 96
        period = 1.0 / max(1.0, self.rate)
        while not self.stop.is_set():
            began = time.perf_counter()
            frame, box, sets = self.frame, self.box, self.sets
            if frame is not None and box is not None:
                fresh = np.array(frame, copy=True)  # (the capture's copy of each frame it is sent)
                t = time.perf_counter()
                self.copy_ms += 1000 * (t - began)
                if self._window is not None:
                    self._window._decide(sets, fresh, box)
                else:
                    st.visible(sets, fresh[box[1]:box[3], box[0]:box[2]], st.BAR_REACH, st.MARGIN,
                               least=st.STRIP_PX)
                self.ms += 1000 * (time.perf_counter() - t)
                self.looks += 1
            self.stop.wait(max(0.0, period - (time.perf_counter() - began)))

    def __enter__(self) -> "Watch":
        self.thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.stop.set()
        self.thread.join(10)


# ------------------------------------------------------------------ one screen read
def unit_row(line: dict[str, Any]) -> str:
    """One screen's numbers: its time, ocr stage, each unit's reading (start - end, ms), the readers' processor calls
    (for a request under way), CPT's calls and ms, and the spread's gap from the first unit's last request."""
    from taslation import analysis

    units = [u for u in line.get("read_units") or [] if int(u.get("unit", -1)) >= 0]
    parts = []
    for u in units:
        readers = u.get("readers") or {}
        cpu = sum(int(r.get("cpu", 0)) for r in readers.values() if isinstance(r, dict))
        req = sum(int(r.get("cpu_translating", 0)) for r in readers.values() if isinstance(r, dict))
        cpt = readers.get("cpt") or {}
        parts.append(f"u{int(u['unit'])}{'b' if u.get('beside') else ''} {float(u.get('read_start_ms', 0)):6.0f}-"
                     f"{float(u.get('read_end_ms', 0)):6.0f} ({float(u.get('read_ms', 0)):6.0f} ms, "
                     f"{int(u.get('crops', 0)):3d} crops, cpu {cpu:3d}/{req:3d} req, cpt {int(cpt.get('calls', 0))} "
                     f"{float(cpt.get('ms', 0.0)):5.0f} ms, wait {float(u.get('wait_ms', 0.0)):4.0f})")
    outside = [u for u in line.get("read_units") or [] if int(u.get("unit", -1)) < 0]
    for u in outside:  # (the readers' calls outside any unit's reading: a unit's lines judged again as it is translated)
        readers = [r for r in (u.get("readers") or {}).values() if isinstance(r, dict)]
        parts.append(f"outside: {sum(int(r.get('calls', 0)) for r in readers)} calls, "
                     f"{sum(float(r.get('ms', 0.0)) for r in readers):5.0f} ms, wait {float(u.get('wait_ms', 0.0)):4.0f}")
    gap = analysis._spread_gap(line)
    stages = line.get("stages") or {}
    said = (f"{float(line.get('ms') or 0):7.0f} ms, ocr {float(stages.get('ocr') or 0):6.0f}, translate "
            f"{float(stages.get('translate') or 0):6.0f}; ")
    said += "; ".join(parts) if parts else "no unit read"
    if gap is not None:
        said += f"; gap {gap['gap_ms']:5.0f} ms, idle {gap['idle_ms']:5.0f} ms"
    if line.get("cached"):
        said += " (from a cache)"
    return said


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("screens", nargs="+", help="folders of screen pictures, or pictures")
    ap.add_argument("--glob", default="*.png", help="a folder's pictures (default *.png)")
    ap.add_argument("--pick", default="", help="the pictures whose first number is one of these, in this order")
    ap.add_argument("--margins", type=margins_arg, default=None, metavar="L,T,R,B|beside")
    ap.add_argument("--order", default="given,reversed", help="given, reversed or both (default)")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--port", type=int, default=0, help="an Ollama server of the tool's own on this port")
    ap.add_argument("--canned", type=int, default=0, metavar="MS", help="a stand-in translator answering after MS ms")
    ap.add_argument("--ocr-runs-on", default="auto", choices=("auto", "cpu", "gpu"))
    ap.add_argument("--models", type=Path, default=None, help="the models folder (default: TASLATION_MODELS_DIR, "
                                                              "else the program's own)")
    ap.add_argument("--watch", default="off", choices=("off", "compare", "same"))
    ap.add_argument("--watch-rate", type=float, default=40.0)
    ap.add_argument("--gate", type=Path, default=None, help="the lock file the GPU is shared by")
    ap.add_argument("--state", type=Path, default=None, help="the tool's state folder (default: a temporary one)")
    ap.add_argument("--keep-state", action="store_true", help="keep the state folder (it holds the program's log)")
    ap.add_argument("--out", type=Path, default=None, help="the analysis lines (numbers only) copied there")
    ap.add_argument("--beside-a-running-one", action="store_true",
                    help="read while another TASlation runs on this computer (a person's own window, another run of "
                         "a tool): without it the tool does not start then (exit code 3)")
    args = ap.parse_args(argv)
    if bool(args.port) == bool(args.canned):
        raise SystemExit("one translator: --port PORT (an Ollama server of the tool's own) or --canned MS")
    if args.port == USUAL_PORT:
        raise SystemExit(f"never Ollama's usual port ({USUAL_PORT}): a person's own server")
    pick = [int(v) for v in args.pick.split(",") if v.strip()]
    screens = screens_of(args.screens, args.glob, pick)
    orders = [o.strip() for o in args.order.split(",") if o.strip()]
    if not orders or any(o not in ("given", "reversed") for o in orders):
        raise SystemExit("--order: given, reversed or both")
    state = args.state or Path(tempfile.mkdtemp(prefix="taslation-screens-"))
    home = Path.home().resolve()
    if any(state.resolve() == home / n or home / n in state.resolve().parents for n in REAL_STATES):
        raise SystemExit("the tool's state folder is never the program's own")
    import standin_viewer as sv  # (tools/: the look at what else runs)

    refused = sv.refuse_beside_running("screens_read", args.beside_a_running_one)  # (before a translator or a reader)
    if refused is not None:
        if args.state is None:
            shutil.rmtree(state, ignore_errors=True)
        return refused
    state.mkdir(parents=True, exist_ok=True)
    os.environ["TASLATION_STATE_DIR"] = str(state)
    os.environ.pop("SELFTRANS_STATE_DIR", None)
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.addHandler(logging.FileHandler(state / "log.txt", encoding="utf-8"))
    root.setLevel(logging.INFO)
    logging.captureWarnings(True)
    name = f"screens_read {os.getpid()}"
    if args.gate is not None:
        take_gate(args.gate, name)
    try:
        return _run(args, screens, orders, state, name)
    finally:
        try:
            from taslation import ollama_start

            ollama_start.finish_all()
        except Exception:  # noqa: BLE001 - nothing of the tool's own left to stop
            pass
        if args.gate is not None:
            drop_gate(args.gate, name)
        if not args.keep_state and args.state is None:
            shutil.rmtree(state, ignore_errors=True)


def _run(args: argparse.Namespace, screens: list[Path], orders: list[str], state: Path, name: str) -> int:
    import numpy as np
    from PIL import Image

    from taslation import analysis, netguard
    from taslation.config import Settings
    from taslation.ocr import Readers
    from taslation.pipeline import Pipeline
    from taslation.translate.models import make_translator

    s = Settings(ocr_runs_on=args.ocr_runs_on, **({"models_dir": args.models} if args.models else {}))
    s.validate()
    default_margins = tuple(s.margins)
    canned = None
    if args.canned:
        from standin_e2e import Canned

        canned = Canned(0.0, args.canned)
        s.ollama_url = canned.url
        netguard.install(allowed_ports={canned.port})
    else:
        from taslation import ollama_start
        from taslation.cli import start_ollama_for

        s.ollama_url = f"http://127.0.0.1:{args.port}"
        os.environ["OLLAMA_HOST"] = f"127.0.0.1:{args.port}"
        os.environ["OLLAMA_NOPRUNE"] = "1"
        ollama_start.DEFAULT_PORT = args.port
        netguard.install(allowed_ports={args.port})
        start_ollama_for(s, quiet=True)
    try:
        translator = make_translator(s)
        translator.translate_page(["こんにちは"])  # (the model loaded before the first screen)
        readers = Readers(s.models_dir, s.ocr_threads, settings=s)
        pipeline = Pipeline(s, ocr=readers, translator=translator, cache=None)
        analysis.start(state, "on")
        print(f"{len(screens)} screens; readers on {getattr(readers, 'placement', None)}; translator "
              f"{'canned ' + str(args.canned) + ' ms' if canned else 'port ' + str(args.port)}; watch {args.watch}",
              flush=True)
        watch = Watch(args.watch, args.watch_rate) if args.watch != "off" else None
        if watch is not None:
            watch.__enter__()
        lines: list[dict[str, Any]] = []
        try:
            for order in orders:
                listed = list(enumerate(screens)) if order == "given" else list(reversed(list(enumerate(screens))))
                for rep in range(max(1, args.reps)):
                    print(f"-- order {order}, round {rep + 1}", flush=True)
                    for place, path in listed:
                        rgb = np.asarray(Image.open(path).convert("RGB"))
                        margins = args.margins
                        if margins == "beside":
                            margins = margins_beside(path) or default_margins
                        elif margins is None:
                            margins = default_margins
                        pipeline.set_margins(margins)
                        pipeline._ocr_memo.clear()
                        pipeline._unanimous_memo.clear()
                        if watch is not None:
                            watch.show(rgb, margins)
                            time.sleep(0.5)  # (the screen on show a moment before it is read, as in the window)
                        before = max([int(ln.get("n") or 0) for ln in analysis.records()
                                      if ln.get("type") == "page"] or [0])
                        try:
                            with pipeline.page_on_show():
                                pipeline.process(Image.fromarray(rgb), use_cache=False, cancel=threading.Event(),
                                                 events=lambda kind, data: None, progress=lambda m: None)
                        except Exception as e:  # noqa: BLE001 - said by its class, the next screen read
                            print(f"  {place + 1:3d} #{number_of(path):5d}: failed ({type(e).__name__})", flush=True)
                            continue
                        new = [ln for ln in analysis.records()
                               if ln.get("type") == "page" and int(ln.get("n") or 0) > before]
                        if not new:
                            print(f"  {place + 1:3d} #{number_of(path):5d}: no line", flush=True)
                            continue
                        line = new[-1]
                        lines.append(line)
                        print(f"  {place + 1:3d} #{number_of(path):5d} {rgb.shape[1]}x{rgb.shape[0]} "
                              f"units {int(line.get('units') or 0)}: {unit_row(line)}", flush=True)
        finally:
            if watch is not None:
                watch.__exit__()
        if watch is not None and watch.looks:
            print(f"watch ({args.watch}): {watch.looks} looks, {watch.ms / watch.looks:.2f} ms a look, the frame's "
                  f"copy {watch.copy_ms / watch.looks:.2f} ms", flush=True)
        for said in analysis.unit_lines(lines):
            print(said)
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as f:
                for line in lines:
                    f.write(json.dumps(analysis.clean(line)) + "\n")
        return 0
    finally:
        analysis.stop()
        if canned is not None:
            canned.stop()


if __name__ == "__main__":
    raise SystemExit(main())
