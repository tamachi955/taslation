"""Command line entry points.

The network guard is installed first, before any heavy library is imported, so
nothing that follows can reach anything but the local Ollama port.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

from . import __version__, errorlog, jurisdictions, netguard, notice
from .config import ConfigError, Settings

LOG = errorlog.LOG.getChild("cli")
# a failed start's box offers the details for a report (Windows' own box: its Yes and No are in Windows' language)
COPY_QUESTION = ("\n\nCopy the details for a report to the clipboard? (The version, the system and the error; "
                 "nothing from your books.)")


def _utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


def build_parser() -> argparse.ArgumentParser:
    from .i18n import UI_LANGUAGES

    p = argparse.ArgumentParser(
        prog="taslation",
        description="Clean, offline manga translation for books you own. "
                    "Everything stays on this machine; the only network peer is a local Ollama server.",
    )
    p.add_argument("--version", action="version", version=f"taslation {__version__}")
    p.add_argument("--config", type=Path, help="path to taslation.toml (default: ./taslation.toml, else the one in the state "
                                                "folder, ~/.taslation, when present)")
    p.add_argument("--models-dir", type=Path, help="where setup_models.py put the models")
    p.add_argument("--model", help="Ollama model name (default from the configuration, ollama_model = \"auto\": the "
                                   "target language chooses, PLaMo 3 Translate 2B for most, Qwen3.5 4B for Brazilian "
                                   "Portuguese and Turkish)")
    p.add_argument("--ollama-url", help="Ollama URL; must be a loopback address")
    p.add_argument("--margins", help="pixels of the capture to ignore: left,top,right,bottom")
    p.add_argument("--font", help="TTF/OTF font for the rendered text")
    p.add_argument("--uppercase", action="store_true", help="render translations in capitals (scanlation style)")
    p.add_argument("--language", help="target language (default from the configuration, target_language: English)")
    p.add_argument("--ui-language", choices=list(UI_LANGUAGES), metavar="CODE",
                   help=f"language of the window: {', '.join(UI_LANGUAGES)} (default: as chosen on the first start)")
    p.add_argument("--debug", action="store_true")

    sub = p.add_subparsers(dest="command")

    g = sub.add_parser("gui", help="open the reader window (default)")
    g.add_argument("--window", help="pick the viewer window whose title contains this text")
    g.add_argument("--book", help="name used for the translation cache (default: derived from the window title)")
    g.add_argument("--auto", action=argparse.BooleanOptionalAction, default=True,
                   help="Auto (on by default): every page turn in the viewer is translated; --no-auto starts with it off")
    g.add_argument("--on-top", action="store_true",
                   help="keep the window above the viewer (single screen: turn pages with the arrow keys on it)")
    g.add_argument("--reading", action="store_true",
                   help="start in reading mode (the page alone, full screen) once the viewer is chosen; F11 or Esc leaves it")
    g.add_argument("--mode", choices=["book", "page"],
                   help="'page' (default): page by page; 'book': read and translate the whole book first")
    g.add_argument("--role", choices=["reader", "translator"],
                   help="start as a reader (default) or as a translator (mark text, fix translations, keep a glossary)")

    sub.add_parser("windows", help="list capturable windows")
    sub.add_parser("doctor", help="check models, fonts, Ollama and the network guard")
    nt = sub.add_parser("notice", help="print the legal notice shown at the start (--reset: show it again on the next start)")
    nt.add_argument("--country", metavar="CODE",
                    help="print the part for this country: a two-letter code such as JP, GB or US, or 'other' "
                         "(default: the country chosen in the window)")
    nt.add_argument("--reset", action="store_true",
                    help="forget that the notice was dismissed in the window or printed on the command line")

    t = sub.add_parser("translate", help="translate an image file of your own (test images, screenshots); nothing is written to disk")
    t.add_argument("image", type=Path)
    t.add_argument("--show", action="store_true", help="show the result in a preview window")
    t.add_argument("--translator", choices=["ollama", "echo", "none"], default="ollama")
    t.add_argument("--no-translate", action="store_true", help="detect and OCR only")
    t.add_argument("--book", help="use/fill the translation cache for this book name")
    t.add_argument("--json", action="store_true", help="print the full result as JSON")

    r = sub.add_parser("read", help="capture the viewer window once, translate it and show the result")
    r.add_argument("--window", required=True)
    r.add_argument("--book")
    r.add_argument("--translator", choices=["ollama", "echo", "none"], default="ollama")
    r.add_argument("--json", action="store_true")

    b = sub.add_parser("batch", help="read the pages you turn in the viewer and fill the translation cache "
                                     "(press Enter when you have finished the book)")
    b.add_argument("--window", required=True, help="viewer window title (substring)")
    b.add_argument("--book", help="cache name (default: derived from the window title)")
    b.add_argument("--series", help="series name for the series sheet (default: book name without volume number)")
    b.add_argument("--max-pages", type=int)
    b.add_argument("--wait", type=float, default=600.0,
                   help="seconds to wait for the viewer window to appear before giving up (default 600)")
    b.add_argument("--no-context", action="store_true",
                   help="translate page by page as it goes, without reading the book first")
    b.add_argument("--retranslate", action="store_true",
                   help="translate every page again (after changing the series sheet or the premises); cached pages are replaced")
    b.add_argument("--translator", choices=["ollama", "echo", "none"], default="ollama")

    rv = sub.add_parser("review", help="list the cached translations flagged for a second look (set small, a "
                                        "rendering missed, far longer or shorter than the Japanese, the OCR unsure)")
    rv.add_argument("--book", required=True, help="the book (see `taslation cache list`)")
    rv.add_argument("--language", default=argparse.SUPPRESS,  # as given before the command, or the configured one
                    help="target language of the cache (default: the configured one)")
    rv.add_argument("--notes", action="store_true", help="also list the notes for the reader kept with the translations")
    c = sub.add_parser("cache", help="list, delete, export or import translation caches (text only, never images); "
                                     "protect: protect the saved files still in plain text, and count them")
    c.add_argument("action", choices=["list", "delete", "path", "export", "import", "protect"])
    c.add_argument("target", nargs="?", metavar="BOOK|FILE", help="delete, export: the book; import: the file")
    c.add_argument("--out", type=Path,
                   help="export: the file to write, encrypted with a passphrase (asked for, or TASLATION_PASSPHRASE)")
    c.add_argument("--force", action="store_true", help="export: write over the --out file when it exists")
    c.add_argument("--replace", action="store_true",
                   help="import: replace the book's cache instead of merging the file's pages into it")
    c.add_argument("--confirm", action="store_true",
                   help="export, import: after the note on what the file is for, ask \"Continue? [y/N]\" before the "
                        "passphrase (without it the note is printed and nothing is asked: scripts)")

    an = sub.add_parser("annotations", help="list the books with local annotations (rectangles, notes, skipped pages, "
                                             "reading orders): counts and files, never page text")
    an.add_argument("action", choices=["list"])
    an.add_argument("--json", action="store_true", help="print the raw list as JSON")

    gl = sub.add_parser("glossary", help="the reader's glossary per series: names and terms with their renderings")
    gl.add_argument("action", choices=["list", "show", "set", "delete", "apply", "font", "lettering", "path"])
    gl.add_argument("series", nargs="?")
    gl.add_argument("term", nargs="?", help="the term as written in the book (set/delete); the font's family name (font); "
                                            "the kind of region (lettering: thought, shout, narration, handwritten, sfx)")
    gl.add_argument("--clear", action="store_true", help="font: suggest no font (the automatic one is used)")
    gl.add_argument("--family", help="lettering: the font family for the kind (\"\" = the sheet's lettering font)")
    gl.add_argument("--italic", action=argparse.BooleanOptionalAction, default=None, help="lettering: italic on or off")
    gl.add_argument("--bold", action=argparse.BooleanOptionalAction, default=None, help="lettering: bold on or off")
    gl.add_argument("--reset", action="store_true", help="lettering: back to the built-in style for the kind")
    gl.add_argument("rendering", nargs="?", help="how to write it in the target language (set)")
    gl.add_argument("--note", default="", help="who or what it is, tone (set)")
    gl.add_argument("--book", help="apply: the cached volume to fix (default: every cached volume of the series)")
    gl.add_argument("--rename", action="append", default=[], metavar="OLD=NEW",
                    help="apply: an extra rendering to replace, e.g. --rename Hja=Hya (repeatable)")
    gl.add_argument("--dry-run", action="store_true", help="apply: only report what would change")

    ky = sub.add_parser("keys", help="the viewer's page keys your keys are passed on as: presets, a viewer's keys, every viewer's")
    ky.add_argument("action", choices=["list", "show", "set", "apply"],
                    help="list: the presets and the viewers with keys of their own; show: the keys a viewer gets (and "
                         "where from); set: keys for a viewer or all viewers; apply PRESET: a preset's keys")
    ky.add_argument("preset", nargs="?", help="apply: the preset (see `taslation keys list`)")
    where = ky.add_mutually_exclusive_group()
    where.add_argument("--viewer", metavar="TITLE",
                       help="the viewer, by its window's title (the book's name in it does not matter)")
    where.add_argument("--all", action="store_true",
                       help="every viewer: each viewer's profile and the defaults of the viewers without one")
    for meaning, what in (("next", "the next page"), ("prev", "the previous page")):
        ky.add_argument(f"--{meaning}", metavar="KEY", help=f"set: the key for {what}")
    ky.add_argument("--reset", action="store_true",
                    help="set --viewer: drop the viewer's own keys (the defaults again)")

    a = sub.add_parser("audit", help="run the pipeline on an image and print every network call that happened")
    a.add_argument("image", type=Path)
    a.add_argument("--translator", choices=["ollama", "echo", "none"], default="ollama")
    return p


def load_settings(args: argparse.Namespace) -> Settings:
    settings = Settings.load(args.config)
    overrides: dict[str, Any] = {
        "models_dir": args.models_dir,
        "ollama_model": args.model,
        "ollama_url": args.ollama_url,
        "margins": args.margins,
        "font_path": args.font,
        "target_language": args.language or None,
        "ui_language": getattr(args, "ui_language", None),
        "debug": True if args.debug else None,
    }
    if args.uppercase:
        overrides["uppercase"] = True
    settings = settings.with_overrides(**overrides)
    settings.validate()
    if settings.ignored_keys and sys.stderr is not None:  # (the window names them itself, once)
        print(f"warning: {settings.config_path} has settings this version does not know, left out: "
              f"{', '.join(settings.ignored_keys)}", file=sys.stderr)
    return settings


# --- helpers -------------------------------------------------------------------

def build_translator(settings: Settings, kind: str, model: str | None = None):
    """The translator *kind* ("ollama", "echo", "none") for the settings; for Ollama with *model* (the Ollama name
    `translation_model` chose; asked for here when not given)."""
    from .translate import EchoTranslator, NullTranslator
    from .translate.models import make_translator

    if kind == "echo":
        return EchoTranslator()
    if kind == "none":
        return NullTranslator()
    return make_translator(settings, model or translation_model(settings).name)


def translation_model(settings: Settings) -> Any:
    """What `taslation.translate.models.choose` makes of the settings: the model to translate with (with ``"auto"``,
    the one the target language needs, or Qwen standing in for a PLaMo not installed yet) and what to say of it
    (``translator.model_missing``, ``translator.other_model``). Ollama is asked for its models once, briefly; when it
    does not answer, the wanted model (the request then says what is wrong)."""
    from . import health
    from .translate.models import choose

    return choose(settings.ollama_model, settings.target_language, health.installed_models(settings.ollama_url))


TRANSLATING_COMMANDS = ("translate", "read", "batch")  # the commands --language gives a translator model to


def _console_yes(question: str) -> bool:
    """A yes at the console (y, yes, or what a Japanese input method gives); no console to ask is a no."""
    if not sys.stdin or not sys.stdin.isatty():
        print(f"{question} n (no console to ask)")
        return False
    try:
        answer = input(question + " ")
    except (EOFError, OSError):
        return False
    return answer.strip().lower() in ("y", "yes", "ｙ", "ｙｅｓ", "はい")


def ensure_translator(settings: Settings, language: str) -> bool:
    """--language asks for a language whose translator model is not installed (only one of PLaMo and Qwen is at a
    time, `translator_install`): the person is asked, in plain words, to download it (its size) and to have the one
    no longer needed removed (the room freed; a model they had before is asked about on its own, default keep);
    PLaMo's licence comes first. The install is setup_models.py's, in a process of its own (this one stays offline).
    Whether the model is there now; when not, the command translates nothing."""
    from . import health
    from . import translator_install as ti

    state_dir = Path(settings.state_dir)
    start_ollama_for(settings, quiet=True)  # (Ollama says which models it has; the command says it when it is down)
    switch = ti.plan(language, health.installed_models(settings.ollama_url), state_dir, settings.ollama_model)
    if switch is None:
        return True
    name = ti.shown_name(switch.needed)
    print(f"Translating into {language} needs the translation model {name}, which is not installed: about "
          f"{ti.size_text(switch.needed.size_gb)} GB to download.")
    if switch.unneeded is not None and switch.ours:
        print(f"{ti.shown_name(switch.unneeded)} is not needed for {language} and is then removed, which frees about "
              f"{ti.size_text(switch.freed_gb)} GB.")
    missing = f"Translation is off: {language} needs {name}, which is not installed."
    off = (f"{missing} Run the command again and answer y, "
           f"or run: python setup_models.py --translator-for \"{language}\"")
    if not _console_yes("Download it now? [y/N]"):
        print(off)
        return False
    if switch.needed.ollama_name == ti.PLAMO.ollama_name and not ti.has_agreed(state_dir):
        print(ti.PLAMO_TERMS)
        if not _console_yes("Do you agree to the PLaMo Community License? [y/N]"):
            print(off)
            return False
        ti.record_agreement(state_dir, "console")
    remove = switch.ours
    if switch.unneeded is not None and not switch.ours:
        remove = _console_yes(f"{ti.shown_name(switch.unneeded)} was on this computer before TASlation installed "
                              f"anything, and {language} does not need it. Remove it too, to free about "
                              f"{ti.size_text(switch.freed_gb)} GB? [y/N]")
    shown = [-1]

    def progress(data: dict[str, Any]) -> None:
        done, total = float(data.get("done") or 0), float(data.get("total") or 0)
        if total and int(20 * done / total) != shown[0]:
            shown[0] = int(20 * done / total)
            print(f"  {data['phase']}: {int(100 * done / total):3d} %", flush=True)
        elif data.get("phase") in ("check", "import"):
            print(f"  {data['phase']} ...", flush=True)

    installer = ti.Installer(language, settings.models_dir, state_dir, settings.ollama_url, on_progress=progress,
                             where="console")
    print(f"Installing {name} (Ctrl+C stops; nothing is left half done) ...", flush=True)
    try:
        outcome = installer.run()
    except KeyboardInterrupt:
        installer.cancel()
        outcome = ti.Outcome("cancelled")
    if outcome.state != "done":
        print({"cancelled": "Stopped. Nothing was left on the disk.",
               "no_room": f"There is too little disk space for {name}. Nothing was downloaded.",
               "refused": f"{name} could not be installed: the publisher's server refused the download or no longer "
                          "has this file. Trying again will not help: update TASlation (a newer version names the "
                          "current file), or look at the project's issues page. Nothing was left on the disk."}.get(
            outcome.state, f"{name} could not be installed ({outcome.detail}). Check the network and the disk space, and "
                           "try again. Nothing was left on the disk."))
        print(missing if outcome.state == "refused" else off)  # (running it again would not help then)
        return False
    print(f"{name} is installed.")
    if remove and switch.unneeded is not None:
        exe = ti.find_ollama()
        if exe and ti.remove_model(exe, switch.unneeded_name, state_dir, settings.ollama_url):
            print(f"{ti.shown_name(switch.unneeded)} was removed, freeing about {ti.size_text(switch.freed_gb)} GB.")
    return True


def _note(message: Any) -> None:
    print(f"note: {message}", file=sys.stderr, flush=True)


def build_ocr(settings: Settings):
    """The OCR engine, on the CPU; a model that is not installed ends the command with what to do."""
    from .ocr import ModelNotInstalled, Readers

    try:
        return Readers(settings.models_dir, settings.ocr_threads)
    except ModelNotInstalled as e:
        raise SystemExit(f"error: {e}") from e


def warm_ollama(settings: Settings, translator: Any) -> bool:
    """Ollama's model loaded now (`OllamaTranslator.warm_up`), when Ollama runs and has the configured model: before
    the OCR model, for a reader whose ``ollama_keep_alive`` keeps it for good (anyone else's model is loaded by the
    first request that needs it). How long it took is said on stderr; nothing when Ollama is down or lacks the model
    (the command says so itself when it needs them); meanwhile the OCR's libraries are imported.
    Whether the model was loaded."""
    import threading

    from . import health
    from .ocr.charspot import import_libraries
    from .translate import TranslationError
    from .translate.ollama import loaded_message, never_unloads

    if not never_unloads(settings.ollama_keep_alive):
        return False
    model = getattr(translator, "model", "")
    if not model or not health.model_installed(settings.ollama_url, model):
        return False
    importing = threading.Thread(target=import_libraries, name="taslation-import", daemon=True)
    importing.start()
    try:
        seconds = translator.warm_up(model)
    except TranslationError:
        return False
    finally:
        importing.join()
    _note(loaded_message(model, seconds))
    return True


def start_ollama_for(settings: Settings, translator: Any = None, quiet: bool = False) -> Any:
    """Before a command translates: Ollama started when it does not answer (said on stderr, and what stands in the
    way unless *quiet*; the command goes on and says it itself when it needs Ollama), and - given the *translator* -
    started again once when a request finds it gone (`OllamaTranslator.revive`). An Ollama started so is TASlation's
    (recorded in the state folder) and stops when the command ends (`main`: `ollama_start.finish_all`), unless another
    TASlation or another program still uses it. `build_translator` alone starts nothing. The `OllamaStarter`, to hand
    a translator made afterwards (`attach_starter`)."""
    from .ollama_start import OllamaStarter, own_models

    starter = OllamaStarter(settings.ollama_url, lambda: _note("Starting the translation program..."),
                            state_dir=settings.state_dir, own=own_models(settings))
    failed = starter.start()
    if failed is not None and not quiet:
        _note(failed)
    if translator is not None:
        attach_starter(translator, starter)
    return starter


def attach_starter(translator: Any, starter: Any) -> None:
    """*translator* starts Ollama again through *starter* when a request finds it gone, and says on stderr what a load
    of its model says (`OllamaTranslator.ensure_loaded`)."""
    translator.revive = starter.revive
    translator.on_status = _note


def ollama_down_line(url: str, tried: bool = False) -> str:
    """Doctor's line when nothing answers at *url*, with what to do; *tried*: doctor started Ollama for its check, and
    it did not answer."""
    from .ollama_start import find_ollama, startable

    if not startable(url):
        return f"Ollama: not running at {url} (TASlation starts it only at its default address)"
    if find_ollama() is None:
        return "Ollama: not installed. Run install.cmd again to install it."
    if tried:
        return (f"Ollama: not running at {url}, and it did not answer when it was started for this check. Restart "
                "your PC, then run this check again; if it still does not answer, run install.cmd again.")
    return (f"Ollama: not running at {url}. TASlation starts it when it translates; if that fails, restart your PC, "
            "then open TASlation again.")


DOCTOR_STARTED = "  (it was not running: it was started for this check, and is stopped again when the check ends)"


def doctor_ollama(settings: Settings) -> bool:
    """Doctor's look at Ollama starts it when it does not answer, as a command that translates would
    (`start_ollama_for`), so that the check says whether translating would work; an Ollama started so is stopped
    again when doctor ends (`main`), which leaves it as it was. Whether it was started for the check."""
    from . import health
    from .ollama_start import find_ollama, startable

    if (health.ollama_running(settings.ollama_url) or not startable(settings.ollama_url)
            or find_ollama() is None):
        return False
    start_ollama_for(settings, quiet=True)
    return True


def build_pipeline(settings: Settings, translator_kind: str = "ollama", book: str | None = None, with_ocr: bool = True,
                   series: str | None = None, warm_first: bool = False):
    """The pipeline a command runs: the translator (with the Ollama translator, Ollama started first when it does not
    answer: `start_ollama_for`), the OCR engine (*with_ocr*), the book's stores. *warm_first*: a model the settings keep
    for good is loaded before the OCR model (`warm_ollama`; the Ollama translator only)."""
    from .cache import CacheStore
    from .notes import series_key
    from .pipeline import Pipeline

    starter = None
    if translator_kind == "ollama":
        starter = start_ollama_for(settings)  # first: the model is chosen from the models Ollama has
        chosen = translation_model(settings)
        if chosen.problem is not None:
            _note(chosen.problem)
    translator = build_translator(settings, translator_kind, chosen.name if starter is not None else None)
    if starter is not None:
        attach_starter(translator, starter)
    if warm_first and with_ocr and translator_kind == "ollama":
        warm_ollama(settings, translator)
    ocr = build_ocr(settings) if with_ocr else None
    cache = None
    if book and settings.cache_enabled:
        if translator_kind == "ollama":
            cache = CacheStore(settings.cache_dir).open(book, translator.model, settings.target_language)
        else:
            # The echo/none translators produce no translations, so there is nothing worth
            # caching - and the cache must never receive the original text.
            print(f"note: translation cache not used with the {translator_kind!r} translator", file=sys.stderr)
    pipeline = Pipeline(settings, ocr=ocr, translator=translator, cache=cache)
    if book:
        from .annotations import AnnotationStore, GlossaryStore

        annotations = AnnotationStore(settings.annotations_dir).open(book)
        if len(annotations):
            pipeline.set_annotations(annotations)
            print(f"note: using {annotations.box_count} reader-made text rectangle(s) on {len(annotations)} page(s)",
                  file=sys.stderr)
        else:
            pipeline.set_annotations(annotations)
        glossary = GlossaryStore(settings.glossary_dir).open(series or series_key(book), settings.target_language)
        pipeline.glossary = glossary
        pipeline.glossary_text = glossary.format()
        if len(glossary):
            print(f"note: using the reader's glossary ({len(glossary)} term(s))", file=sys.stderr)
        font_name, font_file = pipeline.font_status()
        if font_name:
            print(font_message(font_name, font_file), file=sys.stderr)
    return pipeline


def _print_result(result, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=1))
        return
    print(f"page units: {len(result.fingerprints)}  cache hits: {result.cache_hits}  misses: {result.cache_misses}")
    for r in result.regions:
        src = r.source_text or "-"
        dst = r.translated_text or "-"
        tag = " (cache)" if r.from_cache else ""
        print(f"[{r.order:2d}] {r.status:13s} {src}  =>  {dst}{tag}")
    if result.error:
        print(f"error: {result.error}")
    print("timings: " + ", ".join(f"{k} {v:.2f}s" for k, v in result.timings.items()))


def _ui_language(settings: Settings) -> str:
    """The window's language: --ui-language or the config, else the one chosen on the first start, else English."""
    from .i18n import load_ui_language

    return settings.ui_language or load_ui_language(Path(settings.state_dir)) or "en"


def _notice_country(settings: Settings, code: str | None = None) -> str:
    """The country whose part of the notice is printed: *code* (`notice --country`), else the one chosen in the
    window, else the region setting's, else "other" (a code not in the list gets the "other" part too)."""
    if code:
        code = code.strip().upper()
        return code if code in jurisdictions.JURISDICTIONS else jurisdictions.OTHER
    return notice.country(Path(settings.state_dir)) or notice.default_country() or jurisdictions.OTHER


def _notice_once(settings: Settings) -> None:
    """The legal notice on stderr, the first time a command reads a book or an image (`taslation notice` shows it)."""
    notice.print_once(Path(settings.state_dir), _ui_language(settings), _notice_country(settings))


def _book_name(given: str | None, title: str, settings: Settings | None = None) -> str:
    """The book a command reads the window titled *title* for: *given* (``--book``), else the name its title gives
    (`viewerparts.book_for_title`: the viewer's parts learned on this computer left out, a book kept under a fuller or
    an older name found again in the cache folder of *settings*). SystemExit when that names no book
    (`bookid.generic_book_name`: a browser-based viewer's tab can be titled with the viewer's name whatever book it
    shows) - nothing is ever kept under such a name - and so when ``--book`` itself gives one; and when the title
    may be the viewer's own name (`viewerparts.unconfirmed`, which the window asks about)."""
    from . import viewerparts
    from .bookid import generic_book_name
    from .cache import CacheStore

    if given is not None and given.strip():
        if generic_book_name(given):
            raise SystemExit(f"error: --book {given!r} names no book; pass the book's own name")
        return given
    store = CacheStore(settings.cache_dir) if settings is not None else None
    book = viewerparts.book_for_title(title, store)
    if generic_book_name(book):
        raise SystemExit(f"error: the window is titled {title!r}, which names no book; pass --book NAME")
    if viewerparts.unconfirmed(title, book):
        raise SystemExit(f"error: the window is titled {title!r}, which may be the viewer's name rather than the "
                         "book's; pass --book NAME")
    return book


WINDOW_POLL_S = 2.0
ENLARGE_LOOKS = 10  # the enlarged window's frame is looked at this many times at most before reading goes on


def _pick_window(query: str, wait: float = 0.0):
    """The viewer window *query* names (`capture.match_windows`: its exact title, its tab's title in a browser, the
    start of that, ...); with *wait*, keep looking for that many seconds while no window matches. When several
    match, none is guessed: they are listed and the command ends (exit code 2) asking for a fuller title - a chat
    page whose title begins with the viewer's name must not be driven for the reader's tab."""
    from .capture import list_windows, match_windows

    deadline = time.monotonic() + wait
    announced = False
    while True:
        wins = list_windows()
        found = match_windows(query, wins)
        if len(found) == 1:
            win = found[0]
            if announced:
                print(f"found {win.label()}", flush=True)
            return win
        if found:
            print(f"several windows match {query!r}:")
            for w in found:
                print("  " + w.label())
            print("pass a fuller title with --window: the window's whole title, or a browser tab's whole title")
            raise SystemExit(2)
        if time.monotonic() >= deadline:
            print(f"no window title contains {query!r}. Capturable windows:")
            for w in wins:
                print("  " + w.label())
            raise SystemExit(2)
        if not announced:
            announced = True
            print(f"waiting for a window whose title contains {query!r} (up to {wait:.0f}s; open the book in its viewer)...",
                  flush=True)
        time.sleep(WINDOW_POLL_S)


# --- commands ------------------------------------------------------------------

def cmd_windows(_args: argparse.Namespace, _settings: Settings) -> int:
    from .capture import IS_WINDOWS, list_windows

    if not IS_WINDOWS:
        print("window capture is only available on Windows; use `taslation translate IMAGE` here")
        return 1
    for w in list_windows():
        print(f"{w.hwnd:>10d}  {w.label()}")
    return 0


def _config_line(path: Path | None) -> str:
    """The taslation.toml the settings were read from (`Settings.config_file`), or what says there is none."""
    try:
        found = Settings.config_file(path)
    except ConfigError as e:
        return str(e)
    return str(found) if found is not None else "none (the defaults)"


def font_line(name: str, settings: Settings) -> str:
    """The font a series sheet suggests and what it is on this computer."""
    from .render import resolve_font

    spec = resolve_font(name, settings.fonts_dir)
    return f"Lettering font: {name} ({'installed here: ' + str(spec.path) if spec else 'NOT installed on this computer; the automatic font is used'})"


def font_message(name: str, file: str | None) -> str:
    """One line on the lettering font the series sheet suggests: where it is on this computer, or a warning."""
    if file:
        return f"note: lettering font {name!r} from the series sheet: {file}"
    return (f"warning: the series sheet suggests the lettering font {name!r}, which is not installed on this "
            f"computer; the automatic font is used instead (install it, or set font_path)")


def cmd_doctor(args: argparse.Namespace, settings: Settings) -> int:
    import importlib

    from .capture import capture_route
    from .health import is_default_model, page_models_missing, pull_command
    from .config import OCR_SECOND_READERS
    from .ocr.charspot import check_model_dir
    from .ocr.readers import missing_readers
    from .render import find_font

    ok = True
    print(f"taslation {__version__}  python {sys.version.split()[0]}  {sys.platform}")
    print(netguard.describe())
    print(f"Config file: {_config_line(getattr(args, 'config', None))}")
    print(f"Capture: {capture_route()}")
    for mod in ("torch", "safetensors", "cv2", "numpy", "PIL"):
        try:
            m = importlib.import_module(mod)
            print(f"  {mod:13s} {getattr(m, '__version__', '?')}")
        except Exception as e:  # pragma: no cover
            print(f"  {mod:13s} MISSING ({e})")
            ok = False
    missing = check_model_dir(settings.ocr_model_dir)
    if missing:
        ok = False
        print(f"OCR model: NOT INSTALLED in {settings.ocr_model_dir} (missing {', '.join(missing)})")
        print("  -> run install.cmd again to install it")
    else:
        print(f"OCR model: ready in {settings.ocr_model_dir} (non-commercial use only: CC BY-NC-SA 4.0)")
        fewer = missing_readers(settings.models_dir)
        if fewer:
            print(f"  reading with this model alone: {', '.join(fewer)} not installed -> run install.cmd again to read better")
        else:
            print(f"  and {', '.join(m.dirname for m in OCR_SECOND_READERS)} (the same licence)")
    if page_models_missing(settings):
        print(f"Layout and inpainting models: not all in {settings.models_dir} -> run install.cmd again; "
              "until then pages are read and erased the classical way")
    else:
        print(f"Layout and inpainting models: ready in {settings.models_dir} (or not used here: switched off in the "
              "settings, or art_erase \"auto\" on a computer without a CUDA GPU)")
    font = find_font(settings.font_path, settings.fonts_dir)
    print(f"Font: {font if font else 'Pillow default (run install.cmd again, or set font_path)'}")
    try:
        tried = doctor_ollama(settings)
        tr = build_translator(settings, "ollama")
        if tr.ping():
            from .translate.models import is_auto, wanted_name

            models = tr.list_models()
            wanted = wanted_name(settings.ollama_model, settings.target_language)
            have = tr.has_model(wanted)
            print(f"Ollama: reachable at {settings.ollama_url} (v{tr.version()}); {len(models)} model(s) installed")
            if tried:
                print(DOCTOR_STARTED)
            how = "run install.cmd again" if is_default_model(wanted) else pull_command(wanted)
            which = (f"for {settings.target_language} (ollama_model \"auto\")" if is_auto(settings.ollama_model)
                     else "configured")
            print(f"  translation model {wanted!r} {which}: {'installed' if have else 'NOT INSTALLED -> ' + how}")
            if not have and tr.model != wanted:
                print(f"  translating with {tr.model!r} for now")
            if models:
                print("  available: " + ", ".join(models))
            ok = ok and have
        else:
            ok = False
            print(ollama_down_line(settings.ollama_url, tried))
    except Exception as e:
        ok = False
        print(f"Ollama: error {e}")
    from .cache import CacheStore

    books = CacheStore(settings.cache_dir).list()
    print(f"Translation cache: {settings.cache_dir} ({len(books)} book(s); text only, no images)")
    print(f"Target language: {settings.target_language}")
    try:
        from .capture import IS_WINDOWS, list_windows

        print(f"Capture: {len(list_windows())} window(s) visible" if IS_WINDOWS else "Capture: not available on this OS")
    except Exception as e:  # pragma: no cover
        print(f"Capture: error {e}")
    try:
        from . import devices

        print("Where each stage runs:")
        for line in devices.lines(settings):
            print(line)
    except Exception as e:  # pragma: no cover - said, never fatal
        print(f"Where each stage runs: could not look ({type(e).__name__})")
    from .ollama_start import finish_all

    for line in finish_all():  # (the Ollama started for the check, stopped before the last line)
        print(line)
    print("Result:", "ready" if ok else "something is missing (see above)")
    return 0 if ok else 1


def cmd_notice(args: argparse.Namespace, settings: Settings) -> int:
    """The legal notice the window shows at the start; --reset makes it show (and print) again."""
    if args.reset:
        print("The notice will show again on the next start." if notice.reset(Path(settings.state_dir))
              else "Nothing to reset.")
        return 0
    print(notice.console_text(_ui_language(settings), _notice_country(settings, args.country)))
    return 0


def cmd_translate(args: argparse.Namespace, settings: Settings) -> int:
    from PIL import Image

    _notice_once(settings)
    if not args.image.is_file():
        raise SystemExit(f"error: {args.image} not found")
    pipeline = build_pipeline(settings, args.translator, args.book)
    image = Image.open(args.image)
    result = pipeline.process(image, use_cache=bool(args.book), translate=not args.no_translate, progress=_progress)
    pipeline.release_translator()
    _print_result(result, args.json)
    if args.show:
        from .ui.preview import show_preview

        show_preview(result.image, f"TASlation - {args.image.name}")
    return 0 if not result.error else 1


def enlarge_viewer(hwnd: int, settings: Settings):
    """The viewer before a command-line read of one page: its window enlarged (`capture.enlarge_window`: no key, no
    change of the foreground; a maximised window stays as it is), waited for until two frames settle_ms apart are
    alike; what to put back with `capture.restore_window`, None for a window that was left as it is."""
    from .batch import frames_differ, thumbnail
    from .capture import CaptureError, capture_window, enlarge_window, window_rect

    enlarged = enlarge_window(hwnd)
    if enlarged is None:
        return None
    last = None
    for _ in range(ENLARGE_LOOKS):
        time.sleep(settings.settle_ms / 1000.0)
        try:
            thumb = thumbnail(capture_window(hwnd, allow_screen_fallback=False))
        except CaptureError:
            continue
        if last is not None and not frames_differ(last, thumb, 0.5):
            break
        last = thumb
    try:
        enlarged.given = window_rect(hwnd)
    except CaptureError:
        pass
    return enlarged


def _enlarged(hwnd: int, settings: Settings):
    """The viewer's window enlarged and settled before it is read (`enlarge_viewer`); what to restore at the end, or
    None. A window that keeps its size is said in one line."""
    enlarged = enlarge_viewer(hwnd, settings)
    if enlarged is not None and not enlarged.changed:
        print("the viewer's window keeps its size: it is read as it is")
        return None
    return enlarged


def cmd_read(args: argparse.Namespace, settings: Settings) -> int:
    from .capture import capture_window, enable_dpi_awareness, restore_window

    _notice_once(settings)
    enable_dpi_awareness()
    win = _pick_window(args.window)
    book = _book_name(args.book, win.title, settings)
    print(f"capturing {win.label()}  (cache: {book})")
    enlarged = _enlarged(win.hwnd, settings)
    try:
        image = capture_window(win.hwnd)
    finally:
        if enlarged is not None:
            restore_window(enlarged)
    pipeline = build_pipeline(settings, args.translator, book)
    result = pipeline.process(image, progress=_progress)
    pipeline.release_translator()
    _print_result(result, args.json)
    from .ui.preview import show_preview

    show_preview(result.image, f"TASlation - {win.title}")
    return 0


def _finish_at_enter(reader: Any) -> None:
    """Enter at the command line says the book is done (`BatchReader.finish`); without a console nothing does."""
    try:
        input()
    except (EOFError, OSError, ValueError):
        return
    reader.finish()


def cmd_batch(args: argparse.Namespace, settings: Settings) -> int:
    from .batch import BatchReader
    from .capture import enable_dpi_awareness

    from .notes import series_key

    _notice_once(settings)
    enable_dpi_awareness()
    win = _pick_window(args.window, wait=max(0.0, args.wait))
    book = _book_name(args.book, win.title, settings)
    series = args.series or series_key(book)
    pipeline = build_pipeline(settings, args.translator, book, series=series, warm_first=True)
    cache_note = str(pipeline.cache.path) if pipeline.cache is not None else "(disabled)"
    mode = "page by page" if args.no_context else "whole book (every page you turn is read, then translated)"
    print(f"batch reading {win.label()} -> cache {cache_note}\nmode: {mode}; series: {series!r}")
    print("Turn the pages in the viewer at your own pace: TASlation reads each page you turn, and never turns one "
          "itself. Press Enter when you have finished the book. Ctrl+C stops.")

    def on_progress(p, _result):
        print(p.message)

    reader = BatchReader(pipeline, win.hwnd, settings, on_progress, max_pages=args.max_pages,
                         context_mode=not args.no_context, book=book,
                         series=series, title=win.title, query=args.window, retranslate=args.retranslate)
    threading.Thread(target=_finish_at_enter, args=(reader,), name="batch-enter", daemon=True).start()
    try:
        reader.run()
    except KeyboardInterrupt:
        reader.stop()
        print("stopped")
    for note in reader.progress.notes:
        print("note:", note)
    return 0


def _profiles(settings: Settings):
    from .pagekeys import Profiles

    return Profiles(Path(settings.state_dir) / "profiles.json")


def cmd_keys(args: argparse.Namespace, settings: Settings) -> int:
    """taslation keys list|show|set|apply: the viewer's page keys, kept in profiles.json (`pagekeys`)."""
    from .pagekeys import BUILTIN_PRESETS, MEANINGS, PageKeys, own_keys

    profiles = _profiles(settings)
    if args.action == "list":
        print("presets:")
        for name, keys in profiles.presets().items():
            print(f"  {name}{' (built-in)' if name in BUILTIN_PRESETS else ''}: {keys.describe()}")
        print(f"defaults (viewers without keys of their own): {profiles.default_keys(settings).describe()}")
        viewers = [v for v in profiles.viewers() if own_keys(profiles, v)]
        print("viewers with keys of their own:" + ("" if viewers else " none"))
        for viewer in viewers:
            print(f"  {viewer}: {profiles.keys_for(viewer, settings).describe()}")
        return 0
    if args.action == "show":
        if args.viewer:
            own = profiles.own_keys(args.viewer)
            print(f"{profiles.key_of(args.viewer)}: {profiles.keys_for(args.viewer, settings).describe()}")
            mine = ", ".join(f"{m} {v or '(none)'}" for m, v in own.items()) if own else "none (the defaults)"
            print(f"  its own keys: {mine}")
        else:
            print(f"defaults: {profiles.default_keys(settings).describe()}")
        return 0
    if not args.viewer and not args.all:
        raise SystemExit(f"error: keys {args.action} needs --viewer TITLE or --all")
    if args.action == "set" and args.reset:
        if not args.viewer:
            raise SystemExit("error: keys set --reset needs --viewer TITLE")
        profiles.set_keys(args.viewer, None)
        keys = profiles.keys_for(args.viewer, settings)
        print(f"{profiles.key_of(args.viewer)}: the defaults again ({keys.describe()})")
        return 0
    if args.action == "apply":
        presets = profiles.presets()
        if args.preset not in presets:
            raise SystemExit(f"error: no preset {args.preset!r}; the presets: {', '.join(presets)}")
        keys = presets[args.preset]
    else:
        given = {m: getattr(args, m) for m in MEANINGS if getattr(args, m) is not None}
        if not given:
            raise SystemExit("error: keys set needs at least one of --next, --prev")
        base = profiles.keys_for(args.viewer, settings) if args.viewer else profiles.default_keys(settings)
        keys = PageKeys.from_mapping(given, base)
    problems = keys.problems()
    if problems:
        raise SystemExit("error: " + "; ".join(problems))
    if args.all:
        count = profiles.apply_to_all(keys)
        print(f"every viewer ({count} with a profile, and the defaults): {keys.describe()}")
    else:
        profiles.set_keys(args.viewer, keys)
        print(f"{profiles.key_of(args.viewer)}: {keys.describe()}")
    return 0


def cmd_annotations(args: argparse.Namespace, settings: Settings) -> int:
    """The books that have local annotation files (`AnnotationStore.list`): counts and the file, never page text."""
    from .annotations import AnnotationStore

    store = AnnotationStore(settings.annotations_dir)
    books = store.list()
    if getattr(args, "json", False):
        print(json.dumps(books, ensure_ascii=False, indent=2))
        return 0
    if not books:
        print(f"no annotations in {store.annotations_dir}")
    for b in books:
        print(f"{b['book']!r}: {b['pages']} page(s) with rectangles or facts; rectangles {b['add']} add, "
              f"{b['ignore']} ignore; {b['region_notes']} note(s), {b['skipped']} skipped page(s), "
              f"{b['orders']} reading order(s); updated {b['updated']}")
        print(f"    {b['file']}")
    _say_not_here(settings)
    return 0


def cmd_glossary(args: argparse.Namespace, settings: Settings) -> int:
    from .annotations import GlossaryStore

    store = GlossaryStore(settings.glossary_dir)
    if args.action == "path":
        print(store.glossary_dir)
        return 0
    if args.action == "list":
        entries = store.list()
        if not entries:
            print(f"no glossaries in {store.glossary_dir}")
        for e in entries:
            print(f"{e['series']!r} [{e['language']}]: {e['entries']} term(s)\n    {e['file']}")
        _say_not_here(settings)
        return 0
    if not args.series:
        raise SystemExit(f"error: glossary {args.action} needs a series name")
    glossary = store.open(args.series, settings.target_language)
    if args.action == "show":
        print(glossary.format(limit_chars=100000) or "(empty glossary)")
        if glossary.style.font:
            print(font_line(glossary.style.font, settings))
        return 0
    if args.action == "lettering":
        from .annotations import LETTERING_KINDS

        kind = (args.term or "").strip()
        if kind not in LETTERING_KINDS:
            raise SystemExit(f"error: glossary lettering needs a kind: {', '.join(LETTERING_KINDS)}")
        if args.reset:
            glossary.style.lettering.pop(kind, None)
            glossary.save()
        elif args.family is not None or args.italic is not None or args.bold is not None:
            ls = glossary.style.lettering_for(kind)
            if args.family is not None:
                ls.font = args.family.strip()[:60]
            if args.italic is not None:
                ls.italic = args.italic
            if args.bold is not None:
                ls.bold = args.bold
            glossary.style.lettering[kind] = ls
            glossary.save()
        ls = glossary.style.lettering_for(kind)
        words = [w for w, on in (("italic", ls.italic), ("bold", ls.bold)) if on] or ["plain"]
        print(f"{kind}: {' '.join(words)}" + (f", font {ls.font}" if ls.font else "")
              + ("" if kind in glossary.style.lettering else " (the built-in style)"))
        if ls.font:
            print(font_line(ls.font, settings))
        return 0
    if args.action == "font":
        if args.clear:
            glossary.style.font = ""
            glossary.save()
        elif args.term and args.term.strip():
            glossary.style.font = args.term.strip()[:60]
            glossary.save()
        if not glossary.style.font:
            print('no suggested font; the automatic font is used (suggest one: taslation glossary font SERIES "Comic Neue")')
        else:
            print(font_line(glossary.style.font, settings))
        return 0
    if args.action == "apply":
        from . import protect
        from .cache import CacheStore
        from .notes import series_key

        pairs: list[tuple[str, str]] = []
        for item in args.rename:
            if "=" not in item:
                raise SystemExit(f"error: --rename needs OLD=NEW, got {item!r}")
            old, new = item.split("=", 1)
            if old.strip() and new.strip():
                pairs.append((old.strip(), new.strip()))
        if not pairs:
            print("nothing to rename: give the renderings to change as --rename OLD=NEW")
            return 0
        print("renderings: " + ", ".join(f"{old} -> {new}" for old, new in pairs))
        store = CacheStore(settings.cache_dir)
        books = [b for b in store.list() if (args.book and b["book"] == args.book) or
                 (not args.book and series_key(b["book"]) == args.series and b.get("language", "English") == settings.target_language)]
        for entry in books:
            cache = store.open(entry["book"], "", settings.target_language)
            changed = cache.rename(pairs)
            print(f"{entry['book']!r}: {changed} cached bubble(s) {'would change' if args.dry_run else 'changed'}")
            if changed and not args.dry_run:
                backup = cache.path.with_suffix(time.strftime(".before-apply.%Y%m%d-%H%M%S.json"))
                try:
                    if not backup.exists():  # never overwrite an earlier backup; protected as the cache is
                        protect.write(backup, cache.path.read_bytes())
                except OSError:
                    pass
                cache.save()
        return 0
    if args.action == "set":
        if not args.term or not args.rendering:
            raise SystemExit("error: glossary set needs SERIES TERM RENDERING [--note NOTE]")
        glossary.set(args.term, args.rendering, args.note)
        glossary.save()
        print(f"{len(glossary)} term(s) in {glossary.path}")
        return 0
    if args.term:
        print("removed" if glossary.remove(args.term) else "no such term")
        glossary.save()
        return 0
    print("deleted" if store.delete(args.series) else "no such series")
    return 0


def cmd_review(args: argparse.Namespace, settings: Settings) -> int:
    """List the cached translations that carry review flags, page by page: each reason in the window's language with its code after it, "label (code)" (`review.reason_label`)."""
    from .cache import CacheStore
    from .names import language_key
    from .review import reason_label

    language = _ui_language(settings)

    store = CacheStore(settings.cache_dir)
    target = args.language or settings.target_language
    cache = store.open(args.book, "", target)
    pages = sorted(cache.pages, key=lambda pg: (pg.seq if pg.seq >= 0 else 10**9, pg.fingerprint))
    with_notes = getattr(args, "notes", False)
    flagged = total = noted = 0
    for pg in pages:
        for i, b in enumerate(pg.bubbles):
            total += 1
            where = f"page {pg.seq + 1}" if pg.seq >= 0 else f"page {pg.fingerprint[:8]}"
            if with_notes and b.note:
                noted += 1
                print(f"{where} bubble {i + 1}: note for the reader\n    {b.note}")
            if not b.flags:
                continue
            flagged += 1
            reasons = "; ".join(f"{reason_label(code, language)} ({code})" for code in b.flags)
            print(f"{where} bubble {i + 1}: {reasons}\n    {b.text}")
    if total:
        print(f"{flagged} of {total} cached translation(s) flagged")
    else:
        others = sorted({b["language"] for b in store.list() if b["book"] == args.book and b["bubbles"]
                         and language_key(b["language"]) != language_key(target)})
        print(f"no cached translations for {args.book!r}" + (
            f" in {target}; it has some in {', '.join(others)} (--language)" if others else ""))
    if with_notes:
        print(f"{noted} note(s) for the reader")
    return 0


def cmd_cache(args: argparse.Namespace, settings: Settings) -> int:
    from .cache import CacheStore

    store = CacheStore(settings.cache_dir)
    if args.action == "path":
        print(store.cache_dir)
        return 0
    if args.action == "protect":
        return _protect_files(settings)
    if args.action == "list":
        books = store.list()
        if not books:
            print(f"no caches in {store.cache_dir}")
        for b in books:
            print(f"{b['book']!r}: {b['pages']} page(s), {b['bubbles']} bubble(s), model {b['model']}, updated {b['updated']}")
            print(f"    {b['file']}")
        _say_not_here(settings)
        return 0
    if args.action in ("export", "import"):
        return _cache_backup(args, settings, store)
    if not args.target:
        raise SystemExit("error: cache delete needs a book name (see `taslation cache list`)")
    print("deleted" if store.delete(args.target) else "no such cache")
    return 0


def _protect_files(settings: Settings) -> int:
    """`cache protect`: every saved file with text of a book (the caches, annotations and series sheets, with the
    copies kept beside them) still in plain text replaced by its protected form, each in its own atomic step
    (`protect.migrate`, which every start does too), then what the folder holds (`protect.survey`: each protected
    file opened to see whether this Windows user can open it here). Counts only, never a name. Status 1 when a file
    is left in plain text (another program holds it: tried again at the next start); files that cannot be opened here
    are never written over, and the advice says how to bring them here. Where this system cannot protect files, it
    says so and changes nothing (status 1)."""
    from . import protect
    from .names import NOT_HERE_ADVICE

    if not protect.available():
        raise SystemExit("error: this system cannot protect saved files (Windows data protection is missing); "
                         "nothing was changed")
    done = protect.migrate(settings.state_dir)
    found = protect.survey(settings.state_dir)
    # the survey counts the files protected now among the protected ones, and opened them again
    found.protected, found.sealed = done.protected, max(0, found.sealed - done.protected)
    found.opened = max(0, found.opened - done.protected)
    for line in found.lines():
        print(line)
    if found.not_here:
        print(f"    {NOT_HERE_ADVICE}")
    return 1 if found.plain or found.unreadable else 0


def _say_not_here(settings: Settings) -> None:
    """After `cache list`: on stderr, how many saved files this Windows user cannot open on this computer (copied
    from another computer or another user's folder, or damaged; `protect.survey`), and what to do; counts only."""
    from . import protect
    from .names import NOT_HERE_ADVICE

    found = protect.survey(settings.state_dir)
    if found.not_here and sys.stderr is not None:
        print(f"note: {found.not_here} saved file(s) {protect.NOT_HERE}; TASlation never writes over them. "
              f"{NOT_HERE_ADVICE[0].upper()}{NOT_HERE_ADVICE[1:]}", file=sys.stderr)


# the commands that read or write the saved files with text of a book: at their start the plain ones are protected
# (`_protect_at_start`; the window does it itself, `ui.app`). `audit` only counts them: it reports what is on disk.
STORE_COMMANDS = frozenset({"translate", "read", "batch", "review", "cache", "annotations", "glossary"})


def _protect_at_start(args: argparse.Namespace, settings: Settings) -> None:
    """At the start of a command of `STORE_COMMANDS`, the saved files with text of a book still in plain text (an
    earlier version's) protected for this Windows user, each in its own atomic step (`protect.migrate`): one line on
    stderr when some were, one when some could not be (another program holds them: tried again at the next start),
    counts only. Never stops the command: a file left plain is read as it is and protected at its next save; where
    this system cannot protect files nothing is tried, and a save says so itself."""
    from . import protect
    from .messages import Message

    if args.command not in STORE_COMMANDS or (args.command == "cache" and args.action in ("protect", "path")):
        return
    if not protect.available():
        return
    try:
        tally = protect.migrate(settings.state_dir)
    except Exception as e:  # noqa: BLE001 - the command goes on; the files stay as they were
        LOG.warning("the saved files could not be protected at the start: %s", type(e).__name__)
        return
    if sys.stderr is None:
        return
    if tally.protected:
        print(f"note: {Message('store.protected', files=tally.protected)}", file=sys.stderr)
    if tally.plain or tally.unreadable:
        print(f"note: {Message('store.not_protected', files=tally.plain + tally.unreadable)}", file=sys.stderr)


# What `cache export` and `cache import` say before the passphrase, as the Caches dialog's warnings do.
EXPORT_NOTE = ("Note: This file will contain the translated text of the book. Keep it for yourself: never give it to "
               "anyone, post it, or share it. Handing a translation to someone else infringes the author's rights "
               "even when the book is yours.")
IMPORT_NOTE = ("Note: Import only a file you made yourself on this or another of your computers. Importing someone "
               "else's translation is receiving a copy made without permission, and TASlation is built not to pass "
               "translations between people.")
NOTE_WIDTH = 78


def _before_backup(note: str, confirm: bool) -> bool:
    """*note* on stderr as a paragraph, before the passphrase is asked for (or read from the environment); with
    *confirm* (`--confirm`) then "Continue? [y/N]" there too, and whether the answer was yes: anything else, an empty
    line or no input at all is no. Without *confirm* nothing is asked (scripts) and it is True. The question goes to
    stderr, as getpass's prompt goes to the terminal: stdout keeps the one line of result."""
    import textwrap

    print(textwrap.fill(note, width=NOTE_WIDTH, break_on_hyphens=False) + "\n", file=sys.stderr, flush=True)
    if not confirm:
        return True
    print("Continue? [y/N] ", end="", file=sys.stderr, flush=True)
    try:
        answer = sys.stdin.readline() if sys.stdin is not None else ""
    except (OSError, ValueError):  # no input to read from (closed, or none at all): as good as no
        answer = ""
    if not answer.endswith("\n"):  # the end of the input: the next line starts on a line of its own
        print(file=sys.stderr, flush=True)
    return answer.strip().lower() in ("y", "yes")


def _passphrase(confirm: bool) -> str:
    """The passphrase from TASLATION_PASSPHRASE when it is set (scripts), else typed unseen, twice when *confirm*;
    never from the command line, where other programs could read it."""
    import getpass

    from .backup import PASSPHRASE_ENV, check_passphrase

    phrase = os.environ.get(PASSPHRASE_ENV) or os.environ.get("SELFTRANS_PASSPHRASE")  # the old name is still read
    if phrase is None:
        phrase = getpass.getpass("Passphrase: ")
        if confirm and getpass.getpass("Repeat the passphrase: ") != phrase:
            raise SystemExit("error: the two passphrases differ")
    check_passphrase(phrase)
    return phrase


def _cache_backup(args: argparse.Namespace, settings: Settings, store: Any) -> int:
    """`cache export BOOK --out FILE [--force]` and `cache import FILE [--replace]`: a cache as a file encrypted
    with a passphrase, for the reader's own backup or other computer. Once the command can go ahead, a note on
    stderr says what the file is for (EXPORT_NOTE, IMPORT_NOTE) before the passphrase is asked for; with --confirm
    an answer other than yes ends it there with status 1, nothing read or written. One line of result, never the
    book's text; an existing --out file is written over only with --force."""
    from . import backup

    confirm = getattr(args, "confirm", False)
    try:
        backup.require()
        if args.action == "export":
            if not args.target or args.out is None:
                raise SystemExit("error: cache export needs a book name and --out FILE (see `taslation cache list`)")
            backup.cache_file(store, args.target, settings.target_language)  # before the passphrase is asked for
            if args.out.exists() and not args.out.is_dir() and not args.force:  # a folder: export_cache says so
                raise SystemExit(f"error: {args.out} exists; pass --force to overwrite")
            if not _before_backup(EXPORT_NOTE, confirm):
                print("cancelled: nothing was exported", file=sys.stderr)
                return 1
            pages = backup.export_cache(store, args.target, args.out, _passphrase(confirm=True),
                                        settings.target_language)
            print(f"exported {args.target!r}: {pages} page(s) to {args.out}")
            return 0
        if not args.target:
            raise SystemExit("error: cache import needs the file to read")
        if not Path(args.target).is_file():
            raise SystemExit(f"error: {args.target} not found")
        if not _before_backup(IMPORT_NOTE, confirm):
            print("cancelled: nothing was imported", file=sys.stderr)
            return 1
        book, pages = backup.import_cache(store, args.target, _passphrase(confirm=False), replace=args.replace)
    except (backup.BackupError, OSError) as e:
        raise SystemExit(f"error: {e}") from None
    print(f"imported {pages} page(s) into {book!r} ({'replacing its cache' if args.replace else 'merged'}) "
          f"from {args.target}")
    return 0


def cmd_audit(args: argparse.Namespace, settings: Settings) -> int:
    """Evidence run: process an image and list every network call the process made."""
    from PIL import Image

    netguard.record_allowed(True)
    pipeline = build_pipeline(settings, args.translator, None, warm_first=True)
    result = pipeline.process(Image.open(args.image), use_cache=False, progress=_progress)
    pipeline.release_translator()
    _print_result(result, False)
    st = netguard.state()
    assert st is not None
    print("\n--- network audit ---")
    print(netguard.describe())
    seen: list[str] = []
    for ev in st.allowed:
        if not seen or seen[-1] != ev:
            seen.append(ev)
    if seen:
        print("allowed calls (all loopback):")
        for ev in seen:
            print("  " + ev)
    else:
        print("allowed calls: none (no network call at all)")
    if st.blocked:
        print("blocked attempts:")
        for b in st.blocked:
            print("  " + b)
    else:
        print("blocked attempts: none")
    _audit_saved_files(settings)
    return 0


def _audit_saved_files(settings: Settings) -> None:
    """The audit's second part: whether a saved file with text of a book is left in plain text in the state folder
    (`protect.survey`, nothing changed: the audit reports what is on disk), counts only, never a name."""
    from . import protect

    found = protect.survey(settings.state_dir)
    print("\n--- saved files (at rest) ---")
    if not protect.available():
        print("this system cannot protect saved files (Windows data protection is missing)")
    for line in found.lines():
        print(line)
    if not found.plain and not found.unreadable:
        print("plain files with text of a book: none")


def cmd_gui(args: argparse.Namespace, settings: Settings) -> int:
    from .capture import enable_dpi_awareness

    enable_dpi_awareness()
    from .ui.app import run_app

    overrides = {k: v for k, v in (("scan_mode", getattr(args, "mode", None)), ("role", getattr(args, "role", None))) if v}
    if overrides:
        settings = settings.with_overrides(**overrides)
        settings.validate()
    return run_app(settings, window_query=args.window, book=args.book, auto=getattr(args, "auto", True),
                   on_top=getattr(args, "on_top", False) or bool(settings.always_on_top),
                   reading=getattr(args, "reading", False))


def _complain(text: str, details: bool = False) -> None:
    """*text* where the person who started this looks: stderr, or a message box from the Start menu, where ``pythonw``
    has neither stderr nor anything else that shows. *details*: the box asks whether to copy the details for a report
    (`errorlog.details_text`: the version, the system, the last error; nothing of the books) and copies them on Yes."""
    if sys.stderr is not None:
        print(text, file=sys.stderr)
    elif sys.platform == "win32":
        import ctypes

        if not details:
            ctypes.windll.user32.MessageBoxW(None, text, "TASlation", 0x10)  # MB_ICONERROR
            return
        answer = ctypes.windll.user32.MessageBoxW(None, text + COPY_QUESTION, "TASlation", 0x10 | 0x4)  # MB_YESNO
        if answer == 6:  # IDYES
            errorlog.copy_to_clipboard(errorlog.details_text())


def _gui(args: argparse.Namespace, settings: Settings) -> int:
    """`cmd_gui`, with a failure said aloud when no console would show its traceback."""
    try:
        return cmd_gui(args, settings)
    except netguard.NetworkBlocked:
        raise
    except Exception as e:
        LOG.exception("the window could not start")
        if sys.stderr is not None:
            raise
        _complain(f"TASlation could not start.\n\n{type(e).__name__}: {e}\n\nRun install.cmd again.", details=True)
        return 1


def _progress(msg: str) -> None:
    print("  " + msg, file=sys.stderr, flush=True)


COMMANDS = {
    "gui": _gui,
    "windows": cmd_windows,
    "doctor": cmd_doctor,
    "notice": cmd_notice,
    "translate": cmd_translate,
    "read": cmd_read,
    "batch": cmd_batch,
    "cache": cmd_cache, "review": cmd_review,
    "annotations": cmd_annotations,
    "glossary": cmd_glossary,
    "keys": cmd_keys,
    "audit": cmd_audit,
}


def main(argv: list[str] | None = None) -> int:
    _utf8_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        args.command = "gui"
        args.window = None
        args.book = None
        args.auto = True
        args.on_top = False
        args.reading = False
        args.mode = None
        args.role = None
    try:
        settings = load_settings(args)
    except ConfigError as e:
        _complain(f"config error: {e}")
        return 2
    if args.command == "gui":  # <state dir>/log.txt: what went wrong and on what, never what is read
        errorlog.setup(settings)
    from . import viewerparts

    viewerparts.use(settings.state_dir)  # what was learned of the viewers on this computer (`_book_name`)
    # Nothing but the local Ollama port, from here on.
    netguard.install(settings.ollama_port)
    try:
        _protect_at_start(args, settings)
        if (args.command in TRANSLATING_COMMANDS and args.language and getattr(args, "translator", "ollama") == "ollama"
                and not getattr(args, "no_translate", False) and not ensure_translator(settings, settings.target_language)):
            return 1
        return COMMANDS[args.command](args, settings)
    except netguard.NetworkBlocked as e:
        _complain(f"\n{e}\nThis should never happen in normal use; please report it.")
        return 3
    except KeyboardInterrupt:
        return 130
    finally:
        _finish_ollama(args.command)


def _finish_ollama(command: str) -> None:
    """The command ends (Ctrl+C included): the Ollama it started stopped when nothing else uses it
    (`ollama_start.finish_all`), said on stderr; the window's end is in its log. Never raises."""
    from .ollama_start import finish_all

    try:
        said = finish_all()
    except KeyboardInterrupt:  # (a second Ctrl+C: the interpreter's exit tries again)
        return
    if command != "gui":
        for line in said:
            _note(line)
