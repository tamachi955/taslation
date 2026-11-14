#!/usr/bin/env python
"""One-time model download for TASlation.

This is the ONLY part of TASlation that uses the network, and it is a separate
script you run once, by hand. It fetches:

* the three OCR models (muscgab/manga-ocr-charspot-small, muscgab/manga-ocr-nar-small, muscgab/manga-ocr-base-CPT-flex)
  from Hugging Face, each into its folder under ``<models>`` (about 700 MB in all), at fixed revisions and checked
  against their SHA256SUMS; one already there stays. Their weights are CC BY-NC-SA 4.0: non-commercial use only, so a
  person agrees first (install.ps1 asks; run by hand, this script asks);
* the layout model and the inpainting model (ogkalu/comic-text-and-bubble-detector, Apache-2.0;
  dreMaz/AnimeMangaInpainting, LaMa, MIT; about 360 MB), each into its folder under ``<models>``, at fixed revisions and
  checked file by file, after a person agreed too (Enter agrees where torch has a CUDA GPU, which the inpainting model
  then runs on by default, and does not elsewhere). LaMa's checkpoint is read once, as tensors only, and kept as
  safetensors (``taslation.render.lama.convert``); the checkpoint is then deleted. Without them TASlation reads and
  erases as it did before them;
* optionally (``--font``) the OFL-licensed Comic Neue Bold and Bold Italic fonts from the
  google/fonts repository on GitHub, for nicer lettering, and (``--fonts``)
  the Noto Sans family for non-Latin target languages;
* with ``--translator-for LANGUAGE``, the translator model translating into LANGUAGE needs, and nothing else: PLaMo 3
  Translate 2B (pfnet/plamo-3-translate-2b-GGUF, the PLaMo Community License, about 1.8 GB) for every language but two,
  after a person agreed to its licence: one GGUF file at a fixed revision (its licence texts, saved beside it, from
  the same revision), checked against its SHA256, imported into
  Ollama as ``taslation-plamo3-translate-2b`` and then deleted (Ollama's copy is the one used); for Portuguese (Brazil)
  and Turkish, Qwen3.5 4B (Apache-2.0, about 3.3 GB) with ``ollama pull``. What it installed is written down in the
  data folder (``translator_models.json``, `taslation.translator_install`), so that TASlation never removes a model
  the person had before;
* optionally (``--ollama-model [NAME]``) runs ``ollama pull NAME`` for you; without NAME (or with ``auto``) it
  installs the translator model the configured target language needs, as ``--translator-for`` does.

The TASlation application itself never imports this file and never touches the
network; it loads the model from the local directory this script fills.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from taslation import translator_install as tinstall  # noqa: E402
from taslation.config import (OCR_MODELS, PAGE_MODELS, ConfigError, OcrModel, PagedModel, Settings,  # noqa: E402
                              default_models_dir, default_state_dir)
from taslation.health import has_model  # noqa: E402
from taslation.translate.models import AUTO, PLAMO, is_auto, model_for_language  # noqa: E402

OCR_TERMS = f"""The OCR models ({', '.join(m.dirname for m in OCR_MODELS)}; about {sum(m.mb for m in OCR_MODELS) // 100 * 100} MB) are free for non-commercial use only.
Their weights are licensed under CC BY-NC-SA 4.0: https://creativecommons.org/licenses/by-nc-sa/4.0/
TASlation cannot read pages without them."""
PAGE_TERMS = f"""The layout and inpainting models ({', '.join(m.dirname for m in PAGE_MODELS)}; about {sum(m.mb for m in PAGE_MODELS) // 10 * 10} MB)
find lettering on the drawing and take it out. The layout model is tagged Apache-2.0, the inpainting model (LaMa) MIT.
Neither says where its training images come from. See docs/THIRD_PARTY.md.
TASlation works without them, as it did before them."""

GOOGLE_FONTS = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
FONT_BASE = GOOGLE_FONTS + "comicneue/"
FONT_FILES = ("ComicNeue-Bold.ttf", "ComicNeue-BoldItalic.ttf", "OFL.txt")
# Noto Sans per script (variable fonts, SIL Open Font License 1.1): directory -> file name.
NOTO_FONTS = {
    "notosans": "NotoSans[wdth,wght].ttf",
    "notosanssc": "NotoSansSC[wght].ttf",
    "notosanstc": "NotoSansTC[wght].ttf",
    "notosansjp": "NotoSansJP[wght].ttf",
    "notosanskr": "NotoSansKR[wght].ttf",
    "notosansthai": "NotoSansThai[wdth,wght].ttf",
    "notosansarabic": "NotoSansArabic[wdth,wght].ttf",
    "notosanshebrew": "NotoSansHebrew[wdth,wght].ttf",
    "notosansdevanagari": "NotoSansDevanagari[wdth,wght].ttf",
    "notosansbengali": "NotoSansBengali[wdth,wght].ttf",
}


_brief = False  # install.ps1's run: only the downloads themselves are said
TIMEOUT_S = 120  # a connection that gives nothing for this long counts as dropped
RETRIES = 3  # a dropped connection is taken up again so many times in one run, from where it stopped (HTTP Range)
RETRY_WAIT_S = 2.0  # ... after a wait this long times the try
RETRIED_HTTP = frozenset({408, 429, 500, 502, 503, 504})  # the server's own trouble: tried again (a 404 is not)
CHUNK = 1 << 20
QUIET_BYTES = 2 << 20  # a file smaller than this downloads without progress lines


class IncompleteDownload(OSError):
    """The connection ended before the whole file came (the part stays, to be taken up again)."""


class _Shown:
    """A download's progress for the person at the console (`tinstall.progress_text`: percent and MB): in a console
    one line written over at every percent, else a line every *step* percent; nothing in the window's run (which
    reads its own lines, `_report`) or for a file under `QUIET_BYTES`."""

    def __init__(self, step: int = 10, stream=None):
        self.stream = stream if stream is not None else sys.stdout
        try:
            self.over = bool(self.stream.isatty())
        except (AttributeError, ValueError, OSError):
            self.over = False
        self.step = 1 if self.over else max(1, int(step))
        self.last: tuple | None = None
        self.written = False

    def show(self, percent: int | None, done_mb: float | None = None, total_mb: float | None = None) -> None:
        if _progress:
            return
        if percent is not None:
            key: tuple = ("%", min(100, int(percent)) // self.step)
        elif done_mb is not None:
            key = ("MB", int(done_mb // 10))  # every 10 MB
        else:
            return
        if key == self.last:
            return
        self.last = key
        text = tinstall.progress_text(percent, done_mb, total_mb)
        try:
            if self.over:
                self.stream.write("\r" + text.ljust(40))
                self.written = True
            else:
                self.stream.write(text + "\n")
            self.stream.flush()
        except (OSError, ValueError):  # a console gone: the download goes on
            pass

    def update(self, done: int, total: int | None) -> None:
        """*done* of *total* bytes (None: a size the server did not say)."""
        if total is not None and total < QUIET_BYTES:
            return
        if total:
            self.show(done * 100 // total, done / 1e6, total / 1e6)
        else:
            self.show(None, done / 1e6)

    def end(self) -> None:
        if self.over and self.written:
            try:
                self.stream.write("\n")
                self.stream.flush()
            except (OSError, ValueError):
                pass
            self.written = False


def _say(text: str) -> None:
    if not _brief:
        print(text)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _base(model: OcrModel) -> str:
    return f"https://huggingface.co/{model.repo}/resolve/{model.revision}/"


def report_dir(model: OcrModel, models_dir: Path) -> bool:
    model_dir = models_dir / model.dirname
    _say(f"\nOCR model directory: {model_dir}")
    if not model_dir.is_dir():
        _say("  (missing)")
        return False
    ok = True
    for name in model.required:
        p = model_dir / name
        if p.is_file():
            _say(f"  {name:28s} {p.stat().st_size:>12,d} bytes  sha256 {sha256_of(p)[:16]}...")
        else:
            _say(f"  {name:28s} MISSING")
            ok = False
    _say("  status: " + ("ready" if ok else "incomplete"))
    return ok


def agreed_to_ocr_licence() -> bool:
    """Whether the person at the console agrees to the OCR models' licence."""
    print(OCR_TERMS)
    if not sys.stdin.isatty():
        return False
    return input("Do you agree to these terms? [y/N] ").strip().lower() in ("y", "yes", "\uff59", "\uff59\uff45\uff53", "\u306f\u3044")


YES = ("y", "yes", "\uff59", "\uff59\uff45\uff53", "\u306f\u3044")  # (also what a Japanese input method gives)


def gpu_here() -> bool:
    """Whether TASlation erases lettering on the drawing with the inpainting model by default on this computer: torch
    has a CUDA GPU (`devices.cuda_available`, the answer art_erase "auto" asks for; no torch, or a CPU build, is no).
    install.ps1 decides the same before torch is there, from the NVIDIA GPU and the GPU build it installs for it."""
    from taslation.devices import cuda_available

    return cuda_available()


def agreed_to_page_models(default_yes: bool | None = None) -> bool:
    """Whether the person at the console wants the layout and inpainting models on what is known of them. Enter is yes
    where TASlation would use the inpainting model by default (*default_yes*; `gpu_here` when None), else no; without
    a console nobody agreed, whatever the default."""
    print(PAGE_TERMS)
    if not sys.stdin.isatty():
        return False
    if default_yes is None:
        default_yes = gpu_here()
    if default_yes:
        print("With this computer's GPU TASlation uses the inpainting model by default, so Enter here means yes.")
    answer = input(f"Download them on these terms? {'[Y/n]' if default_yes else '[y/N]'} ").strip().lower()
    return answer in YES or (default_yes and not answer)


def _ocr_sums(model: OcrModel, folder: Path) -> dict[str, str]:
    """File name -> sha256 from the model's SHA256SUMS, fetched into *folder* and itself checked."""
    path = folder / "SHA256SUMS"
    _fetch(_base(model) + "SHA256SUMS", path)
    if sha256_of(path) != model.sums_sha256:
        raise SystemExit(f"The SHA256SUMS of {model.dirname} is not the expected one; it was not installed.")
    return {name.lstrip("*"): digest for digest, name in (line.split() for line in path.read_text("utf-8").splitlines() if line.strip())}


def download_ocr(model: OcrModel, models_dir: Path) -> Path:
    """*model* into a folder of its own, moved into place once every file has its checksum: a stopped download
    leaves no model that looks installed, and what is left is picked up by the next run."""
    target = models_dir / model.dirname
    part = models_dir / (model.dirname + ".part")
    part.mkdir(parents=True, exist_ok=True)
    _say(f"Downloading {model.repo} at {model.revision[:10]} (weights CC BY-NC-SA 4.0) from Hugging Face ...")
    sums = _ocr_sums(model, part)
    for name in (*model.required, *model.notices):
        path = part / name
        _fetch(_base(model) + name, path)
        if sha256_of(path) != sums[name]:
            path.unlink()
            raise SystemExit(f"{name} of {model.dirname} failed its checksum and was removed; please run this again.")
    if target.exists():
        shutil.rmtree(target)
    part.replace(target)
    return target


def download_paged(model: PagedModel, models_dir: Path) -> Path:
    """*model* into a folder of its own, as `download_ocr` does; these repositories keep no sums: the file's own are here."""
    target = models_dir / model.dirname
    part = models_dir / (model.dirname + ".part")
    part.mkdir(parents=True, exist_ok=True)
    _say(f"Downloading {model.repo} at {model.revision[:10]} ({model.licence}) from Hugging Face ...")
    for name, sha in model.files:
        path = part / name
        _fetch(f"https://huggingface.co/{model.repo}/resolve/{model.revision}/{name}", path)
        if sha256_of(path) != sha:
            path.unlink()
            raise SystemExit(f"{name} of {model.dirname} failed its checksum and was removed; please run this again.")
    if model.installed:  # a checkpoint, checked above, kept as safetensors
        from taslation.render.lama import convert

        _say(f"Converting {model.files[0][0]} to {model.installed[0]} ...")
        convert(part / model.files[0][0], part / model.installed[0])
        for name, _sha in model.files:
            (part / name).unlink()
    if target.exists():
        shutil.rmtree(target)
    part.replace(target)
    return target


def _content_range(value: str | None) -> tuple[int | None, int | None]:
    """Where a part begins and how large the whole file is, from a Content-Range ("bytes 100-999/1000",
    "bytes */1000"); None for what it does not say."""
    if not value or not value.strip().lower().startswith("bytes"):
        return None, None
    span, _, whole = value.strip()[5:].strip().partition("/")
    start = int(span.split("-", 1)[0]) if span and span[0].isdigit() else None
    return start, int(whole) if whole.strip().isdigit() else None


def _hash_file(path: Path, h) -> None:
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)


def _download_once(url: str, part: Path, progress: Callable[[int, int | None], None],
                   cancel: threading.Event | None, hashing: bool) -> tuple[int, "hashlib._Hash | None"]:
    """One try of `_download`: what *part* has already is asked for no more (``Range``), and what comes is added to
    it - unless the server sends the whole file (200), which then starts it anew. Its size and, with *hashing*, the
    SHA256 of all of it."""
    have = part.stat().st_size if part.is_file() else 0
    h = hashlib.sha256() if hashing else None
    request = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
    try:
        resp = urllib.request.urlopen(request, timeout=TIMEOUT_S)
    except urllib.error.HTTPError as e:
        if e.code == 416 and have:  # nothing after what is there: the whole file, or a part of another one
            _start, whole = _content_range(e.headers.get("Content-Range") if e.headers else None)
            if whole == have:
                if h is not None:
                    _hash_file(part, h)
                return have, h
            part.unlink()
            return _download_once(url, part, progress, cancel, hashing)
        raise
    with resp:
        start, total = 0, None
        if have and resp.status == 206:
            start, total = _content_range(resp.headers.get("Content-Range"))
            if start != have:  # a part that begins elsewhere: not ours to add to
                resp.close()
                part.unlink()
                return _download_once(url, part, progress, cancel, hashing)
        else:
            length = resp.headers.get("Content-Length")
            total = int(length) if length and length.strip().isdigit() else None
        if start and h is not None:
            _hash_file(part, h)
        done = start
        with open(part, "ab" if start else "wb") as out:
            while True:
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                piece = resp.read(CHUNK)
                if not piece:
                    break
                out.write(piece)
                if h is not None:
                    h.update(piece)
                done += len(piece)
                progress(done, total)
    if total is not None and done != total:
        name = part.name[:-len(".part")] if part.name.endswith(".part") else part.name
        raise IncompleteDownload(f"{name} arrived incomplete ({done:,d} of {total:,d} bytes)")
    return done, h


# what a connection that drops raises (a full disk or a file that cannot be written is no reason to try again)
_DROPPED = (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError, IncompleteDownload)


def refused_code(error: BaseException) -> int | None:
    """The HTTP status of a download the server refused or no longer has (`tinstall.REFUSED_HTTP`: 401, 403, 404,
    410), which trying again does not change; None for any other error (the network, the disk)."""
    if isinstance(error, urllib.error.HTTPError) and error.code in tinstall.REFUSED_HTTP:
        return int(error.code)
    return None


def refused_text(what: str, code: int) -> str:
    """What a person reads when *what* could not be downloaded because the server refused it (`refused_code`)."""
    return (f"{what} was not installed: the publisher's server refused the download or no longer has this file "
            f"(HTTP {code}). Running this again will not help: update TASlation (a newer version names the current "
            "file), or look at the project's issues page. Nothing was left behind.")


def _on_a_line_of_its_own() -> str:
    try:
        return "\n" if sys.stdout.isatty() else ""  # (after a progress line written over)
    except (AttributeError, ValueError, OSError):
        return ""


def _download(url: str, part: Path, progress: Callable[[int, int | None], None],
              cancel: threading.Event | None = None, hashing: bool = False) -> tuple[int, "hashlib._Hash | None"]:
    """*url* into the file *part*, taken up from where it stopped: a part already there (an earlier run) is asked for
    no more than the rest, and a connection that drops is taken up again so, `RETRIES` times, where the server allows
    it (HTTP Range; else the file starts anew). *progress* hears done and total bytes. The size, and the SHA256 of
    the whole file with *hashing*. What stays after a failure is the part, for the next run."""
    tries = 0
    while True:
        try:
            return _download_once(url, part, progress, cancel, hashing)
        except Cancelled:
            raise
        except urllib.error.HTTPError as e:
            if e.code not in RETRIED_HTTP or tries >= RETRIES:
                raise
            error: Exception = e
        except _DROPPED as e:
            if tries >= RETRIES:
                raise
            error = e
        tries += 1
        have = part.stat().st_size if part.is_file() else 0
        print(f"{_on_a_line_of_its_own()}  the connection broke off ({type(error).__name__}); going on from "
              f"{have / 1e6:,.1f} MB (try {tries + 1} of {RETRIES + 1}) ...", flush=True)
        time.sleep(RETRY_WAIT_S * tries)


def _fetch(url: str, dest: Path) -> None:
    """*url* into *dest*, in place only once it is whole: a connection that drops mid-file ends a read like the end of
    the file does, and a short file left in place would count as present on every later run. It comes as
    ``<name>.part`` first, with its percent and MB as it comes (`_Shown`), taken up from where it stopped
    (`_download`); the callers then check its SHA256 (a file taken up included) and remove it when it is wrong."""
    if dest.is_file() and dest.stat().st_size > 0:
        _say(f"already present: {dest.name}")
        return
    print(f"Downloading {dest.name} ...", flush=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    shown = _Shown()
    try:
        _download(url, tmp, shown.update)
    finally:
        shown.end()
    tmp.replace(dest)


def download_font(models_dir: Path) -> None:
    fonts_dir = models_dir / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    for name in FONT_FILES:
        _fetch(FONT_BASE + name, fonts_dir / name)
    _say("Fonts installed (Comic Neue Bold and Bold Italic, SIL Open Font License 1.1; license text saved alongside).")


def download_noto_fonts(models_dir: Path) -> None:
    """Noto Sans for every script TASlation can render (about 55 MB in total)."""
    fonts_dir = models_dir / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    for directory, name in NOTO_FONTS.items():
        _fetch(GOOGLE_FONTS + directory + "/" + urllib.parse.quote(name), fonts_dir / name)
    _fetch(GOOGLE_FONTS + "notosans/OFL.txt", fonts_dir / "OFL-NotoSans.txt")
    _say("Noto Sans fonts installed (SIL Open Font License 1.1; license text saved alongside).")


def pull_ollama(model: str) -> None:
    exe = shutil.which("ollama")
    if not exe:
        sys.exit("ollama was not found on PATH. Install it from https://ollama.com and run: ollama pull " + model)
    print(f"Running: ollama pull {model}")
    subprocess.run([exe, "pull", model], check=False)


# ---------------------------------------------------------------- the translator model


_progress = False  # the window's run: progress lines (`tinstall.progress_line`) and "cancel" on stdin


class Cancelled(Exception):
    """The window asked to stop (or went away)."""


def _report(phase: str, done: float = 0, total: float = 0, **extra) -> None:
    if _progress:
        print(tinstall.progress_line(phase, done, total, **extra), flush=True)


def _watch_for_cancel() -> threading.Event:
    """Set when the window writes "cancel" on our stdin, or closes it (it went away)."""
    cancel = threading.Event()

    def watch() -> None:
        try:
            for line in sys.stdin:
                if line.strip() == "cancel":
                    break
        except (OSError, ValueError):
            pass
        cancel.set()

    if _progress:
        threading.Thread(target=watch, name="setup-cancel", daemon=True).start()
    return cancel


def agreed_to_plamo() -> bool:
    """Whether the person at the console agrees to the PLaMo Community License."""
    print(tinstall.PLAMO_TERMS)
    if not sys.stdin.isatty():
        return False
    return input("Do you agree to the PLaMo Community License? [y/N] ").strip().lower() in (
        "y", "yes", "ｙ", "ｙｅｓ", "はい")


def _check(path: Path, sha: str, what: str) -> None:
    if sha256_of(path) != sha:
        path.unlink()
        raise OSError(f"{what} failed its checksum and was removed")


def download_plamo(models_dir: Path, cancel: threading.Event) -> Path:
    """PLaMo's licence texts and its GGUF into its folder, each checked against its SHA256; the GGUF arrives as a
    ``.part`` file first, hashed as it comes (a connection that drops is taken up from where it stopped: `_download`),
    with its percent and MB, and is put in place only whole and right. *cancel* stops it between two pieces
    (`Cancelled`; the ``.part`` file is removed by the caller, as after a failure: nothing is left half done)."""
    folder = tinstall.plamo_dir(models_dir)
    folder.mkdir(parents=True, exist_ok=True)
    for path, sha, name in tinstall.PLAMO_LICENCE_FILES:
        target = folder / name
        if not target.is_file() or sha256_of(target) != sha:
            target.unlink(missing_ok=True)
            _fetch(tinstall.plamo_url(path), target)
            _check(target, sha, name)
    gguf = folder / tinstall.PLAMO_FILE
    part = gguf.with_name(gguf.name + ".part")
    total = tinstall.PLAMO_BYTES
    print(f"Downloading {tinstall.PLAMO_FILE} ({total / 1e9:.1f} GB) from {tinstall.PLAMO_REPO} at "
          f"{tinstall.PLAMO_REVISION[:10]} ...", flush=True)
    shown = _Shown(step=5)

    def progress(done: int, _size: int | None) -> None:
        _report("download", done, total)
        shown.update(done, total)

    try:  # a dropped connection is taken up from where it stopped (the part hashed again first)
        done, h = _download(tinstall.plamo_url(tinstall.PLAMO_FILE), part, progress, cancel, hashing=True)
    finally:
        shown.end()
    assert h is not None
    if done != total:
        part.unlink(missing_ok=True)
        raise OSError(f"{tinstall.PLAMO_FILE} arrived incomplete ({done:,d} of {total:,d} bytes)")
    _report("check", 0, 0)
    if h.hexdigest() != tinstall.PLAMO_SHA256:
        part.unlink(missing_ok=True)
        raise OSError(f"{tinstall.PLAMO_FILE} failed its checksum and was removed")
    part.replace(gguf)
    (folder / "Modelfile").write_text(tinstall.modelfile_text(), encoding="utf-8")
    return gguf


def _ollama_progress(phase: str) -> Callable[[str], None]:
    """What ``ollama pull`` / ``ollama create`` say, passed on: to the window as progress lines (`_report`), by hand as
    it is, and in install.ps1's run as percent and MB (`_Shown`), so that a long pull is seen to go on."""
    shown = _Shown()

    def seen(text: str) -> None:
        share = tinstall.percent_of(text)
        if share is not None:
            _report(phase, round(share * 1000), 1000)
        if _progress:
            return
        if not _brief:
            print(f"  {text.strip()}", flush=True)
            return
        if share is not None:
            sizes = tinstall.sizes_of(text)
            shown.show(round(share * 100), *(sizes or (None, None)))

    seen.end = shown.end  # type: ignore[attr-defined]
    return seen


def _room(needed_gb: float, *folders: Path) -> str | None:
    """What stands in the way when *needed_gb* do not fit (on a disk shared by *folders*, or on each), else None."""
    drives: dict[str, Path] = {}
    for folder in folders:
        drives.setdefault(Path(folder).resolve().anchor.lower(), Path(folder))
    share = needed_gb if len(drives) == 1 else needed_gb / len(drives)
    for folder in drives.values():
        free = tinstall.free_gb(folder)
        if free is not None and free < share:
            return f"{free:.1f} GB free on {Path(folder).resolve().anchor or folder}, about {share:.1f} GB needed"
    return None


def install_translator(language: str, models_dir: Path, state_dir: Path, url: str | None = None,
                       ollama_exe: str | None = None, agreed: str | None = None,
                       cancel: threading.Event | None = None) -> int:
    """The translator model translating into *language* needs, installed (`tinstall`): PLaMo after the person agreed
    to its licence (*agreed*: where they did, "install" or "window", or "TASLATION_AGREE_PLAMO_LICENCE" for an
    automated check's install whose variable said so; else asked here), downloaded, checked, imported
    into Ollama, its GGUF then deleted; Qwen3.5 4B pulled. A model that is there already is left as it is. Nothing is
    left half done: a stopped or failed install removes its download and an import Ollama did not finish. The exit
    code: 0 ready, 1 failed, CANCELLED, NO_ROOM, REFUSED (the server refused the file or no longer has it: running
    this again does not help, `refused_text`)."""
    cancel = cancel or threading.Event()
    needed = model_for_language(language)
    name = tinstall.shown_name(needed)
    exe = ollama_exe or tinstall.find_ollama()
    if not exe:
        print("Ollama was not found. Install it from https://ollama.com and run this again.")
        _report("error", text="ollama_missing")
        return 1
    before = tinstall.listed(exe, url)
    if before is None:
        print("Ollama does not answer. Start it (or restart the PC) and run this again.")
        _report("error", text="ollama_down")
        return 1
    if has_model(before, needed.ollama_name):
        print(f"{name} is already installed.")
        if needed.ollama_name == PLAMO.ollama_name:
            tinstall.mark_installed(state_dir, needed)
        _report("done", already=True)
        return 0
    try:
        if needed.ollama_name == PLAMO.ollama_name:
            if not agreed and not tinstall.has_agreed(state_dir):
                if not agreed_to_plamo():
                    print("Not agreed: PLaMo was not downloaded. TASlation cannot translate without a translator model.")
                    return 1
                agreed = "console"
            tinstall.record_agreement(state_dir, agreed or "console")
            short = _room(tinstall.PLAMO_ROOM_GB, models_dir, tinstall.ollama_models_dir())
            if short:
                print(f"Too little disk space for {name}: {short}. Nothing was downloaded.")
                _report("error", text=short)
                return tinstall.NO_ROOM
            _report("download", 0, tinstall.PLAMO_BYTES)
            download_plamo(models_dir, cancel)
            print(f"Importing {name} into Ollama as {needed.ollama_name} ...", flush=True)
            _report("import", 0, 0)
            watch = _ollama_progress("import")
            code = tinstall.run_watched([exe, "create", needed.ollama_name, "-f",
                                         str(tinstall.plamo_dir(models_dir) / "Modelfile")],
                                        cancel, watch, tinstall.ollama_env(url))
            watch.end()  # type: ignore[attr-defined]
        else:
            short = _room(needed.size_gb + 0.2, tinstall.ollama_models_dir())
            if short:
                print(f"Too little disk space for {name}: {short}. Nothing was downloaded.")
                _report("error", text=short)
                return tinstall.NO_ROOM
            print(f"Running: ollama pull {needed.ollama_name}", flush=True)
            _report("pull", 0, 1000)
            watch = _ollama_progress("pull")
            code = tinstall.run_watched([exe, "pull", needed.ollama_name], cancel, watch, tinstall.ollama_env(url))
            watch.end()  # type: ignore[attr-defined]
        if code is None:
            raise Cancelled()
        now = tinstall.listed(exe, url)
        if code != 0 or now is None or not has_model(now, needed.ollama_name):
            raise OSError(f"Ollama could not install {name} (exit code {code})")
    except Cancelled:
        _undo(exe, url, needed, before, models_dir, state_dir)
        print("Stopped: nothing was left behind.")
        _report("cancelled")
        return tinstall.CANCELLED
    except KeyboardInterrupt:
        _undo(exe, url, needed, before, models_dir, state_dir)
        print("Stopped: nothing was left behind.")
        return tinstall.CANCELLED
    except (OSError, http.client.HTTPException, subprocess.SubprocessError) as e:
        _undo(exe, url, needed, before, models_dir, state_dir)
        refused = refused_code(e)
        if refused is not None:  # the file this version names is gone: a newer TASlation names the current one
            print(refused_text(name, refused))
            _report("error", text=f"HTTP {refused}", refused=refused)
            return tinstall.REFUSED
        print(f"{name} was not installed: {e}. Nothing was left behind; check the network and the disk space, and "
              "run this again.")
        _report("error", text=str(e))
        return 1
    tinstall.remove_leftovers(models_dir)  # the GGUF: Ollama's copy is the one used
    tinstall.mark_installed(state_dir, needed)
    print(f"{name} is installed.")
    _report("done")
    return 0


def _undo(exe: str, url: str | None, needed, before: list[str], models_dir: Path, state_dir: Path) -> None:
    """What a stopped or failed install began, removed: its download, and the model if Ollama has it only now."""
    tinstall.remove_leftovers(models_dir)
    now = tinstall.listed(exe, url)
    if now is not None and has_model(now, needed.ollama_name) and not has_model(before, needed.ollama_name):
        tinstall.remove_model(exe, needed.ollama_name, state_dir, url)


def _settings_for_translator() -> tuple[Path, str | None, str]:
    """The data folder, Ollama's URL and the target language of the settings (the defaults when they do not load)."""
    try:
        settings = Settings.load()
        return Path(settings.state_dir), settings.ollama_url, settings.target_language
    except (ConfigError, OSError, ValueError):
        return default_state_dir(), None, Settings.target_language


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models-dir", type=Path, default=None,
                    help=f"where to put the models (default: {default_models_dir()}; env TASLATION_MODELS_DIR)")
    ap.add_argument("--check", action="store_true", help="only verify what is installed (no network)")
    ap.add_argument("--skip-ocr", action="store_true", help="do not download the OCR models")
    ap.add_argument("--skip-page-models", action="store_true", help="do not download the layout and inpainting models")
    ap.add_argument("--agreed", action="store_true", help=argparse.SUPPRESS)  # install.ps1: the person has agreed there
    ap.add_argument("--brief", action="store_true", help=argparse.SUPPRESS)  # install.ps1: no paths, sizes or checksums
    ap.add_argument("--font", action="store_true", help="also download Comic Neue Bold and Bold Italic (OFL-1.1) for lettering")
    ap.add_argument("--fonts", action="store_true",
                    help="also download Noto Sans (OFL-1.1) for Chinese, Korean, Thai, Arabic, Hebrew, Hindi, Bengali, "
                         "Cyrillic, Greek and Vietnamese targets (~55 MB)")
    ap.add_argument("--ollama-model", metavar="NAME", nargs="?", const=AUTO,
                    help="also run `ollama pull NAME`; without NAME (or with \"auto\"), install the translator model "
                         "the configured target language needs (as --translator-for)")
    ap.add_argument("--translator-for", metavar="LANGUAGE",
                    help="only install the translator model for translating into LANGUAGE (English, Turkish, ...): "
                         "PLaMo 3 Translate 2B, after you agree to its licence, or for Portuguese (Brazil) and Turkish "
                         "Qwen3.5 4B")
    ap.add_argument("--plamo-agreed", metavar="WHERE", nargs="?", const="install",
                    help=argparse.SUPPRESS)  # install.ps1 or the window: the person agreed to PLaMo's licence there
    ap.add_argument("--progress", action="store_true", help=argparse.SUPPRESS)  # the window: progress lines, cancel
    ap.add_argument("--ollama-exe", help=argparse.SUPPRESS)  # install.ps1: the ollama.exe winget just installed
    args = ap.parse_args(argv)
    global _brief, _progress
    _brief = args.brief
    _progress = args.progress
    for stream in (sys.stdout, sys.stderr):  # a path this console's code page has no letters for
        try:
            stream.reconfigure(errors="backslashreplace")  # type: ignore[union-attr]
        except Exception:
            pass

    models_dir = (args.models_dir or default_models_dir()).expanduser().resolve()

    if args.translator_for:
        state_dir, url, _language = _settings_for_translator()
        return install_translator(args.translator_for, models_dir, state_dir, url, args.ollama_exe, args.plamo_agreed,
                                  _watch_for_cancel())

    if args.check:
        ok = all([report_dir(model, models_dir) for model in OCR_MODELS])
        for paged in PAGE_MODELS:
            lacking = paged.missing(models_dir)
            print(f"{paged.dirname}: " + (f"not installed ({', '.join(lacking)}); TASlation works without it" if lacking else "ready"))
        fonts = sorted((models_dir / "fonts").glob("*.ttf")) if (models_dir / "fonts").is_dir() else []
        print(f"Fonts in {models_dir / 'fonts'}: {', '.join(f.name for f in fonts) or '(none; system fonts will be used)'}")
        return 0 if ok else 1

    _say("TASlation model setup - this step uses the network; nothing else in TASlation does.")
    try:
        wanted = [model for model in OCR_MODELS if model.missing(models_dir)] if not args.skip_ocr else []
        if wanted:
            if not args.agreed and not agreed_to_ocr_licence():
                print("Not agreed: nothing was downloaded. TASlation cannot read pages without the OCR models.")
                return 1
            for model in wanted:
                download_ocr(model, models_dir)
                if not report_dir(model, models_dir):
                    print("The OCR model download is incomplete; please re-run this script.")
                    return 1
        paged = [model for model in PAGE_MODELS if model.missing(models_dir)] if not args.skip_page_models else []
        if paged and (args.agreed or agreed_to_page_models()):
            for model in paged:
                download_paged(model, models_dir)
        elif paged:
            print("Not agreed: the layout and inpainting models were not downloaded. TASlation works without them.")
        if args.font:
            download_font(models_dir)
        if args.fonts:
            download_noto_fonts(models_dir)
    except (OSError, http.client.HTTPException) as e:
        refused = refused_code(e)
        if refused is not None:
            print(f"The download failed: the server refused it or no longer has the file (HTTP {refused}). Running "
                  "this again will not help: update TASlation (a newer version names the current files), or look at "
                  "the project's issues page.")
            return tinstall.REFUSED
        print(f"The download failed: {e}. Check the network and the disk space, and run this again.")
        return 1
    if args.ollama_model and is_auto(args.ollama_model):
        state_dir, url, language = _settings_for_translator()
        if install_translator(language, models_dir, state_dir, url, args.ollama_exe, args.plamo_agreed) != 0:
            return 1
    elif args.ollama_model:
        pull_ollama(args.ollama_model)
    _say("\nDone. You can go offline now; TASlation itself never needs the network again.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
