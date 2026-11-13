"""Settings for TASlation.

Defaults are chosen so that nothing leaves the machine and nothing that could
be abused is left behind: translation goes to a loopback Ollama server, the OCR
model is loaded from a local directory that ``setup_models.py`` filled in
advance, page images only ever live in memory, and the on-disk cache holds
translated text plus bubble geometry keyed by page fingerprints (never images,
never the original text).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_DIR = PACKAGE_DIR.parent


@dataclass(frozen=True)
class OcrModel:
    """One of the OCR's models: where it comes from, its folder under the models folder, the files it cannot read
    without (*required*) and the others that come with it (*notices*), the SHA-256 of its SHA256SUMS at *revision*,
    and its download size."""

    repo: str
    revision: str
    dirname: str
    required: tuple[str, ...]
    notices: tuple[str, ...]
    sums_sha256: str
    mb: int

    def missing(self, models_dir: Path) -> list[str]:
        """The *required* files that are not in this model's folder under *models_dir*."""
        return [name for name in self.required if not (Path(models_dir) / self.dirname / name).is_file()]


# The OCR models. Their weights are CC BY-NC-SA 4.0: never bundled, never fetched by the application; setup_models.py
# fetches them from these exact revisions after a person agreed to the licence (install.ps1).
OCR_CHARSPOT = OcrModel("muscgab/manga-ocr-charspot-small", "72ca29202673880ca9c67b1c02c107535be4472b",
                        "manga-ocr-charspot-small", ("model.safetensors", "vocab.json", "config.json"),
                        ("LICENSE_MODEL", "NOTICE.md"),
                        "4983b5f415556edfbf64cd57385e4520e9ca063dfafc0e58729106df5f2e133e", 44)
OCR_NAR = OcrModel("muscgab/manga-ocr-nar-small", "81ff4f3313263d1da349946a9dd20d14e0fb0e66",
                   "manga-ocr-nar-small", ("model.safetensors", "nar_vocabulary_6817.json", "config.json"),
                   ("LICENSE_MODEL", "NOTICE.md", "THIRD_PARTY_LICENSE_MONKEYOCRV2"),
                   "07b878928bcd4178af6747562680dd7d3cc8c5316d907e9f83e5036bb8727bd4", 217)
OCR_CPT = OcrModel("muscgab/manga-ocr-base-CPT-flex", "9cc15742f8dc37cb5222a6569839bc774dfc0392",
                   "manga-ocr-base-CPT-flex", ("model.safetensors", "nar_vocabulary_6817.json", "config.json"),
                   ("LICENSE_MODEL", "NOTICE.md"),
                   "6a69b29ea9bbe76b04d9b5beccab994ae82d475a967a32aed7efd089b98c0bab", 444)
OCR_SECOND_READERS = (OCR_NAR, OCR_CPT)
OCR_MODELS = (OCR_CHARSPOT, *OCR_SECOND_READERS)
OCR_MODEL_DIRNAME = OCR_CHARSPOT.dirname
OCR_REQUIRED_FILES = OCR_CHARSPOT.required


@dataclass(frozen=True)
class PagedModel:
    """A model of the page's layout or of its erase: where it comes from, its folder under the models folder, the files
    fetched with their SHA-256 (these repositories keep no sums of their own), its licence as stated and its download
    size; *installed*: what is in the folder once set up, when that is not what was fetched (a checkpoint converted)."""

    repo: str
    revision: str
    dirname: str
    files: tuple[tuple[str, str], ...]
    licence: str
    mb: int
    installed: tuple[str, ...] = ()

    def missing(self, models_dir: Path) -> list[str]:
        """The files of a set-up model that are not in its folder under *models_dir*."""
        names = self.installed or tuple(name for name, _sha in self.files)
        return [name for name in names if not (Path(models_dir) / self.dirname / name).is_file()]


# Never bundled, never fetched by the application; setup_models.py fetches them from these exact revisions and checks
# each file after a person agreed (install.ps1). Licences, lineage and what is not stated: docs/THIRD_PARTY.md.
LAYOUT_MODEL = PagedModel("ogkalu/comic-text-and-bubble-detector", "16e8a622f91fabc6b5b65c96d32d1183f8843546",
                          "comic-text-and-bubble-detector",
                          (("model.safetensors", "037930a861e67870eb345be01b28cc70d7e2b7956528e48ee0ebdb0c093df80d"),
                           ("config.json", "b6d707933e12e9593a7025604be1c95add70a6db371fdd1532e8854e2256e072")),
                          "Apache-2.0", 164)
# LaMa: its checkpoint holds tensors only; setup_models.py reads it once (torch.load, weights_only) and keeps the
# generator as safetensors (`render.lama.convert`), which is all the application reads.
LAMA_MODEL = PagedModel("dreMaz/AnimeMangaInpainting", "2953a4e935bf01ad1471f6cbfd26ab81abeeb92d", "lama-manga",
                        (("lama_large_512px.ckpt", "11d30fbb3000fb2eceae318b75d9ced9229d99ae990a7f8b3ac35c8d31f2c935"),),
                        "MIT", 195, installed=("lama-manga.safetensors",))
PAGE_MODELS = (LAYOUT_MODEL, LAMA_MODEL)

CONFIG_FILENAME = "taslation.toml"
MIN_UI_SCALE, MAX_UI_SCALE = 0.5, 3.0  # the bounds of `Settings.ui_scale`
TEXT_SCALE_RANGE = (0.5, 2.0)  # the bounds of `Settings.text_scale` (the dialogs offer 80-130 %)


def default_models_dir() -> Path:
    env = os.environ.get("TASLATION_MODELS_DIR") or os.environ.get("SELFTRANS_MODELS_DIR")  # the old name is still read
    if env:
        return Path(env).expanduser()
    if (REPO_DIR / "setup_models.py").exists():  # running from a checkout / editable install
        return REPO_DIR / "models"
    return Path.home() / ".taslation" / "models"


def default_state_dir() -> Path:
    env = os.environ.get("TASLATION_STATE_DIR") or os.environ.get("SELFTRANS_STATE_DIR")  # the old name is still read
    if env:
        return Path(env).expanduser()
    new = Path.home() / ".taslation"
    if new.exists():
        return new
    for former in (".selftrans", ".cleantrans"):  # the project's former names: an existing state folder is carried over once
        old = Path.home() / former
        if old.is_dir():
            try:
                old.rename(new)
            except OSError:
                return old
            return new
    return new


class ConfigError(ValueError):
    pass


# settings of older versions: a file that has them still loads, and they do nothing. The second line: the model's own
# notes, its review pass and its shorter versions, removed 2026-11-06 (both translators only translate), and the
# prompt styles for translation-only models ("mt", "index"), removed the same day: the chat prompts only; and the
# viewer's full-screen key, which TASlation pressed at the first read (fullscreen_key), and the reload of a viewer that
# stays black (reload_key, black_reload_*), removed the same day: TASlation presses no key the person did not press
DROPPED_SETTINGS: set[str] = {"first_page_key", "fullscreen_key", "reload_key", "black_reload_wait_s",
                              "black_reload_gap_s", "black_reload_max", "ocr_device", "ocr_batch", "ocr_precision", "ocr_reader", "ocr_reread_below",
                              "ocr_upscale", "ocr_upscale_below",
                              "notes_pages_per_request", "series_notes", "revision_flag_distance", "revision_changes_only",
                              "review_pass", "ollama_prompt_style"}


@dataclass
class Settings:
    # --- translation (local Ollama only) ---
    ollama_url: str = "http://127.0.0.1:11434"
    # "auto": the target language chooses the model (`translate.models`): PLaMo 3 Translate 2B (the PLaMo Community
    # License; 1.8 GB, raw prompts: `translate.plamo`) for every language it writes, Qwen3.5 4B (Apache-2.0, 3.3 GB,
    # the chat prompts) for Brazilian Portuguese and Turkish. Any other value is an Ollama model of the reader's own,
    # translated with the chat prompts. See docs/MANUAL.md, the section on choosing the model.
    ollama_model: str = "auto"
    ollama_timeout: float = 900.0
    ollama_temperature: float = 0.2
    ollama_num_ctx: int = 16384  # the chat translator's context window (0 = server default); a batch request needs ~10K; PLaMo has its own (8192)
    # How long Ollama keeps the model loaded after a request, in Ollama's own format: a duration ("30m", "2h") or
    # seconds ("0": unloads after every request). Every request carries it; the first line to translate loads the
    # model, and the end of a whole-book run or the window closed releases it; "-1": loaded at the start, before the
    # OCR model, and never released (`translate.ollama.never_unloads`).
    ollama_keep_alive: str = "5m"
    target_language: str = "English"
    context_pages: int = 2  # live mode: previous pages passed to the model as context (memory only)

    # --- whole-book batch: every page read as it is turned, then all of them translated with the whole book as context ---
    context_mode: bool = True  # False: page by page (each page translated as it is captured)
    chunk_bubbles: int = 30  # lines per request of the whole-book translation (3-5 pages; in runs of 100 the replies drift off their lines)
    lookahead_bubbles: int = 60  # upcoming bubbles shown to the chat translator for context only (PLaMo has no place for them)
    context_pairs: int = 40  # previous (source, translation) pairs carried into the next request

    # --- OCR ---
    models_dir: Path = field(default_factory=default_models_dir)
    ocr_threads: int = 0  # threads the OCR model computes with (0 = torch's default, one per core); while other programs keep the CPU busy, half the cores can be faster

    # --- detection ---
    white_threshold: int = 225
    dark_threshold: int = 140
    min_bubble_area_ratio: float = 0.0006
    max_bubble_area_ratio: float = 0.20
    min_bubble_size: int = 24
    min_short_bubble: int = 60  # px; a smaller region read as 1-2 characters is treated as noise (a bubble's short line the OCR is sure of excepted: Pipeline._short_line)
    ocr_min_confidence: float = 0.65  # drop OCR readings whose confidence (the characters' mean heat times their mean classifier probability) is below this: on the gold set 8 of 197 crops without text reach 0.65 alone, lettering about 0.9
    detect_text_blocks: bool = True  # also find text lettered straight onto light areas (no bubble)
    detect_dark_bubbles: bool = True  # also find dark bubbles / light lettering on dark areas
    split_joined_bubbles: bool = True  # bubbles that touch or overlap (one white area): one region per bubble, cut at the neck or at the junction's notches
    take_columns_beyond: bool = False  # dark bubbles: also read a column that goes on past the interior on the bubble's own black (off: speed lines there read as text)
    slant_text: bool = True  # lettering set at a slant: measured, read turned upright and lettered at its slant (off: all upright, as before)
    translate_sfx: bool = True  # also translate short katakana sound effects found outside bubbles
    # the layout model first, the classical detectors adding what it missed: "auto" (where lettering on the art is
    # inpainted too, as `art_erase` decides for this computer: the extra regions lie on the art, and the paper fill
    # would damage it), "on" (with or without that) or "off" (the classical detectors alone; the default while the
    # layout model is measured on more books)
    detect_model: str = "off"
    margins: tuple[int, int, int, int] = (0, 0, 0, 0)  # left, top, right, bottom pixels of the capture to ignore

    # --- rendering ---
    font_path: str = ""  # empty = auto-detect (see render.fonts)
    min_font_size: int = 9
    max_font_size: int = 64
    # the lettering's size, book-wide (a book may have its own: `annotations.BOOK_SETTING_KEYS`): under 1.0 every
    # translation smaller by so much, over it larger where the page's sizes held it back, never larger than its bubble
    # holds nor than max_font_size, nor smaller than min_font_size (`Pipeline._scaled_top`); 1.0 sets it as before
    text_scale: float = 1.0
    line_spacing: float = 1.12
    uppercase: bool = False
    readable_font_size: int = 11  # a translation set smaller than this is flagged "small" for review (0 = never)
    enforce_terms: bool = True  # a translation that misses a rendering from the series sheet is flagged "rendering"
    spellcheck: bool = True  # flag a translation with a word the dictionary does not know (needs the optional pyspellchecker package)
    erase_mode: str = "fill"  # "fill" | "inpaint" | "classic" (the erase of before 2026-10-30, byte for byte)
    # with erase_mode "fill", lettering set on the drawing is inpainted by LaMa (bubbles keep their paper): "auto" (the
    # default) only where torch has a CUDA GPU, and a computer without one erases as with "off"; "lama" always, on the
    # CPU too (about 4 s a screen against 0.6 on a GPU); "off" never. Its weights must be installed for any of it; the
    # rule is `render.artwork.runs_here` (torch is asked only then, never when the settings are read)
    art_erase: str = "auto"

    # --- translation cache (text + geometry only, never images) ---
    state_dir: Path = field(default_factory=default_state_dir)
    cache_enabled: bool = True
    fingerprint_max_distance: int = 36  # Hamming distance (of 320 bits) still considered the same page
    match_min_iou: float = 0.4  # cached bubble vs live bubble overlap needed to reuse a translation
    render_unmatched_cached: bool = False  # draw cached bubbles even where the live page shows no text region

    # --- batch reading (follows the viewer) ---
    # The viewer's page keys, which a page key the person presses in TASlation's window is passed on as (names: Left,
    # Right, Up, Down, PageUp, PageDown, Home, End, Space, Enter, Tab, Backspace, Escape, F1-F12, a letter or a digit).
    # A viewer's own keys (Page > Page keys..., kept in profiles.json with the capture area) and the defaults "Apply to
    # all viewers" keeps there come first (`pagekeys.page_keys_for`); these are the keys of a viewer without either.
    # TASlation passes on only the keys the person presses: it presses none of its own.
    next_page_key: str = "Left"  # Japanese books read right-to-left: Left arrow = next page in most viewers
    prev_page_key: str = "Right"  # the previous page
    black_wait_s: float = 30.0  # a viewer black this long may just be loading; then the person is told to reload it
    page_turn_wait_ms: int = 3000  # how long to wait for the viewer to show the next page
    settle_ms: int = 400  # frame must stay unchanged this long before it is processed
    batch_max_pages: int = 2000
    # MB of page images a whole-book run keeps in memory, packed without loss and never on disk: the pages waiting to be
    # read (the reader is asked to wait only when they fill it), the pages read and erased ahead for the session; at most
    # a quarter of the machine's memory (`pageimages.memory_cap`). A 200-screen volume takes about 130-300 MB.
    batch_memory_mb: int = 2048

    # --- app ---
    scan_mode: str = "page"  # "page": page by page (default) | "book": the whole book read and translated first
    role: str = "reader"  # the window's starting mode: "reader" | "translator" (mark text, fix translations)
    ui_language: str = ""  # language of the window (a code from i18n.UI_LANGUAGES); empty = the first-start choice
    # the size of the window's text, times what Windows sets for its monitor (1.0 = as Windows has it): applied at the
    # start and again whenever the window moves to a monitor of another scale (`ui.scaling`)
    ui_scale: float = 1.0
    always_on_top: bool = False  # the window starts above the others (as View > Always on top, or gui --on-top)
    auto_interval_ms: int = 700
    # over a viewer in full screen on the same monitor, the window stays on top without taking the foreground (the
    # viewer keeps the keys); View > Over the full-screen viewer turns it off for the next starts too (`ui.overbook`)
    over_book: bool = True
    bubble_zoom: bool = True  # reading mode and the Reader role: a translated bubble the pointer rests on shows enlarged beside its original (`ui.zoom`)
    flash_when_done: bool = True  # a whole-book run that ends while TASlation is not in front flashes its taskbar button
    sound_when_done: bool = False  # ... and plays the system's default sound (`ui.attention`)
    follow: str = "events"  # how the window follows the viewer: "events" (Windows: captured after TASlation turns its page, every auto_interval_ms only while the viewer itself is in front, never while neither is) | "poll" (every auto_interval_ms)
    debug: bool = False

    # --- where these came from (never keys of the file: `INTERNAL_FIELDS`) ---
    config_path: Path | None = field(default=None, compare=False, repr=False)  # the taslation.toml read (None: none)
    ignored_keys: tuple[str, ...] = field(default=(), compare=False, repr=False)  # its keys this version does not know

    # ------------------------------------------------------------------
    @property
    def ocr_model_dir(self) -> Path:
        return Path(self.models_dir) / OCR_MODEL_DIRNAME

    @property
    def fonts_dir(self) -> Path:
        return Path(self.models_dir) / "fonts"

    @property
    def cache_dir(self) -> Path:
        return Path(self.state_dir) / "cache"

    @property
    def annotations_dir(self) -> Path:
        return Path(self.state_dir) / "annotations"

    @property
    def glossary_dir(self) -> Path:
        return Path(self.state_dir) / "glossary"

    @property
    def ollama_host(self) -> str:
        return urlparse(self.ollama_url).hostname or "127.0.0.1"

    @property
    def ollama_port(self) -> int:
        parsed = urlparse(self.ollama_url)
        return parsed.port or (443 if parsed.scheme == "https" else 11434)

    def validate(self) -> None:
        from .netguard import is_loopback_host

        if not is_loopback_host(self.ollama_host):
            raise ConfigError(
                f"ollama_url must point at this machine (loopback); got {self.ollama_url!r}. "
                "TASlation never sends text to another host."
            )
        try:
            port = self.ollama_port
        except ValueError as e:
            raise ConfigError(f"ollama_url has an invalid port: {self.ollama_url!r}") from e
        if not 1 <= port <= 65535:
            raise ConfigError(f"ollama_url has an invalid port: {self.ollama_url!r}")
        if self.erase_mode not in ("fill", "inpaint", "classic"):
            raise ConfigError("erase_mode must be 'fill', 'inpaint' or 'classic'")
        if self.art_erase not in ("auto", "lama", "off"):
            raise ConfigError("art_erase must be 'auto', 'lama' or 'off'")
        if self.detect_model not in ("auto", "on", "off"):
            raise ConfigError("detect_model must be 'auto', 'on' or 'off'")
        from .translate.ollama import keep_alive_value

        try:
            keep_alive_value(self.ollama_keep_alive)
        except ValueError as e:
            raise ConfigError("ollama_keep_alive must be a duration such as '30m' or '2h', or seconds such as '600' "
                              f"('-1': never unload, '0': unload after every request); got {self.ollama_keep_alive!r}") from e
        if self.min_font_size < 4 or self.max_font_size < self.min_font_size:
            raise ConfigError("font sizes out of range")
        if self.readable_font_size and not self.min_font_size <= self.readable_font_size <= self.max_font_size:
            raise ConfigError("readable_font_size must be 0 or between the minimum and maximum font sizes")
        if not TEXT_SCALE_RANGE[0] <= float(self.text_scale) <= TEXT_SCALE_RANGE[1]:
            raise ConfigError(f"text_scale must be between {TEXT_SCALE_RANGE[0]} and {TEXT_SCALE_RANGE[1]} (1.0: as it fits)")
        if any(m < 0 for m in self.margins):
            raise ConfigError("margins must be >= 0")
        from .pagekeys import PageKeys

        problems = PageKeys.from_settings(self).problems()
        if problems:
            raise ConfigError("; ".join(problems))
        if float(self.black_wait_s) <= 0:
            raise ConfigError("black_wait_s must be more than 0")
        if int(self.batch_memory_mb) < 64:
            raise ConfigError("batch_memory_mb must be 64 or more (MB of page images a whole-book run keeps in memory)")
        if not MIN_UI_SCALE <= float(self.ui_scale) <= MAX_UI_SCALE:
            raise ConfigError(f"ui_scale must be between {MIN_UI_SCALE} and {MAX_UI_SCALE} (1.0: as Windows sets it)")
        if self.scan_mode not in ("book", "page"):
            raise ConfigError("scan_mode must be 'book' or 'page'")
        if self.follow not in ("events", "poll"):
            raise ConfigError("follow must be 'events' or 'poll'")
        if self.role not in ("reader", "translator"):
            raise ConfigError("role must be 'reader' or 'translator'")
        if self.ui_language:
            from .i18n import UI_LANGUAGES

            if self.ui_language not in UI_LANGUAGES:
                raise ConfigError(f"ui_language must be one of: {', '.join(UI_LANGUAGES)}")

    def with_overrides(self, **overrides: Any) -> "Settings":
        clean = {k: v for k, v in overrides.items() if v is not None}
        return replace(self, **_coerce(clean))

    # ------------------------------------------------------------------
    @staticmethod
    def config_file(path: Path | str | None = None) -> Path | None:
        """The ``taslation.toml`` that `load` reads: *path* (``--config``) when given, else the first that exists of
        ``./taslation.toml`` in the working directory, the one at the root of a checkout and
        ``<state dir>/taslation.toml`` (``~/.taslation``, or ``TASLATION_STATE_DIR``: an installed program's place
        for it); None for none (the defaults). ConfigError when *path* is given and is no file."""
        if path is not None:
            if not Path(path).is_file():
                raise ConfigError(f"config file not found: {path}")
            return Path(path)
        for cand in (Path.cwd() / CONFIG_FILENAME, REPO_DIR / CONFIG_FILENAME, default_state_dir() / CONFIG_FILENAME):
            if cand.is_file():
                return cand
        return None

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Settings":
        """Load ``taslation.toml`` (`config_file`: ``--config``, the working directory, a checkout's root, the state
        directory). No file = defaults."""
        found = cls.config_file(path)
        return cls() if found is None else cls.from_toml(found)

    @classmethod
    def from_toml(cls, path: Path) -> "Settings":
        """The settings of the file at *path* (``config_path``). A key this version does not know is no reason to stop:
        it is left out and named in ``ignored_keys`` (the window says so once, the command line on every run); the
        settings of older versions (`DROPPED_SETTINGS`) are left out without a word. A file that is no TOML, or a
        value that does not fit its setting, is a ConfigError."""
        data = _file_table(path)
        unknown = tuple(sorted(set(data) - setting_names() - DROPPED_SETTINGS))
        values = {k: v for k, v in data.items() if k in setting_names()}
        try:
            return cls(**_coerce(values), config_path=Path(path), ignored_keys=unknown)
        except (TypeError, ValueError) as e:
            raise ConfigError(f"a value in {path} does not fit its setting: {e}") from None

    def changed_from_defaults(self) -> dict[str, Any]:
        """The settings that differ from the defaults (the file's and the command line's), by name."""
        default = Settings(state_dir=self.state_dir, models_dir=self.models_dir)
        return {name: getattr(self, name) for name in sorted(setting_names())
                if getattr(self, name) != getattr(default, name)}


INTERNAL_FIELDS = frozenset({"config_path", "ignored_keys"})  # fields of `Settings` that no file sets
EXAMPLE_FILENAME = "taslation.toml.example"


def setting_names() -> frozenset[str]:
    """The keys a taslation.toml may set: the fields of `Settings` but `INTERNAL_FIELDS`."""
    return frozenset(f.name for f in fields(Settings)) - INTERNAL_FIELDS


def _file_table(path: Path | str) -> dict[str, Any]:
    """The keys of the file at *path*: its ``[taslation]`` table when it has one, else its top level."""
    import tomllib

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path} is not a valid settings file: {e}") from None
    if "taslation" in data and isinstance(data["taslation"], dict):
        data = data["taslation"]
    return data


# ---------------------------------------------------------------- the file written by the Settings dialog

def settings_file(settings: Settings | None = None) -> Path:
    """The taslation.toml the Settings dialog writes and opens: the one *settings* were read from, else the first the
    loader finds (`Settings.config_file`), else ``taslation.toml`` in the state folder - the loader's last place, which
    an update of the program files leaves alone."""
    kept = getattr(settings, "config_path", None)
    if kept is not None:
        return Path(kept)
    found = Settings.config_file()
    if found is not None:
        return found
    state = Path(settings.state_dir) if settings is not None else default_state_dir()
    return state / CONFIG_FILENAME


_ACTIVE_KEY = re.compile(r"^(?P<lead>[ \t]*)(?P<key>[A-Za-z_][A-Za-z0-9_-]*)(?P<eq>[ \t]*=[ \t]*)(?P<rest>.*)$")
_COMMENTED_KEY = re.compile(r"^(?P<lead>[ \t]*)#[ \t]?(?P<key>[A-Za-z_][A-Za-z0-9_-]*)(?P<eq>[ \t]*=[ \t]*)(?P<rest>.*)$")
_TABLE = re.compile(r"^[ \t]*\[\[?[ \t]*(?P<name>[^\]]+?)[ \t]*\]\]?[ \t]*(#.*)?$")

NEW_FILE_HEADER = """# TASlation's settings. Tools > Settings... changes the common ones; this file has them all.
# A line that starts with "#" is a note, or a setting left at its default: delete the "#" before a setting
# to change it. TASlation reads this file when it starts.
"""


def new_settings_text(example: Path | None = None) -> str:
    """The text of a new taslation.toml: `NEW_FILE_HEADER`, then the example (``taslation.toml.example`` of the
    program) with every setting turned into a note that names its default - so that nothing in a new file holds a
    default fast that a later version changes - or the header alone where the program has no example."""
    path = Path(example) if example is not None else REPO_DIR / EXAMPLE_FILENAME
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return NEW_FILE_HEADER
    out = []
    for line in lines:
        if _ACTIVE_KEY.match(line) and not line.lstrip().startswith("#"):
            out.append("# " + line)
        else:
            out.append(line)
    return NEW_FILE_HEADER + "\n" + "\n".join(out) + "\n"


def create_settings_file(path: Path | str, example: Path | None = None) -> bool:
    """A taslation.toml at *path* made from the example (`new_settings_text`) when there is none; whether one was made."""
    from .atomic import write_atomic

    target = Path(path)
    if target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(target, new_settings_text(example).encode("utf-8"))
    return True


def toml_value(value: Any) -> str:
    """*value* as TOML writes it: true/false, a number, a string in double quotes (JSON's escapes are TOML's), an
    array of these."""
    import json

    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        text = repr(value)
        return text if any(c in text for c in ".eE") or text in ("inf", "-inf", "nan") else text + ".0"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    return json.dumps(str(value), ensure_ascii=False)


def _value_end(rest: str) -> int | None:
    """Where the value at the start of *rest* (what follows a key's ``=``) ends; None for one this writer does not
    edit (a multi-line string or array)."""
    if rest.startswith(('"""', "'''")):
        return None
    i, depth, quote = 0, 0, ""
    while i < len(rest):
        c = rest[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 2
                continue
            if c == quote:
                quote = ""
                if depth == 0:
                    return i + 1
        elif c in "\"'":
            quote = c
        elif c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return i + 1
        elif c == "#" and depth == 0:
            return len(rest[:i].rstrip())
        i += 1
    if quote or depth:
        return None
    return len(rest.rstrip())


def _with_value(match: re.Match, value: str) -> str | None:
    """The key's line of *match* with *value* in place of its own, its note kept where it was (when there is room)."""
    rest = match.group("rest")
    end = _value_end(rest)
    if end is None:
        return None
    note = rest[end:].lstrip()
    head = match.group("lead") + match.group("key") + match.group("eq") + value
    if not note:
        return head
    column = match.start("rest") + end + (len(rest[end:]) - len(note))  # where the note began
    return head + " " * max(2, column - len(head)) + note if note.startswith("#") else None


def edit_settings_text(text: str, values: dict[str, Any]) -> str:
    """*text* of a taslation.toml with each of *values* (setting -> value) set: a key's own line gets the new value
    (its note kept), else a line where it is a note (``# key = ...``) becomes the setting, else a line is added at the
    end of the settings (the ``[taslation]`` table when the file has one). Every other line stays as it was."""
    lines = text.splitlines()
    tables = [(i, m.group("name")) for i, line in enumerate(lines) if (m := _TABLE.match(line))]
    named = [i for i, name in tables if name.strip("\"' ") == "taslation"]
    if named:
        first = named[0] + 1
        later = [i for i, _name in tables if i > named[0]]
        last = later[0] if later else len(lines)
    else:
        first, last = 0, tables[0][0] if tables else len(lines)
    for key, value in values.items():
        rendered = toml_value(value)
        done = False
        for pattern in (_ACTIVE_KEY, _COMMENTED_KEY):
            for i in range(first, last):
                if pattern is _ACTIVE_KEY and lines[i].lstrip().startswith("#"):
                    continue
                m = pattern.match(lines[i])
                if m and m.group("key") == key:
                    edited = _with_value(m, rendered)
                    if edited is not None:
                        lines[i] = edited
                        done = True
                        break
            if done:
                break
        if not done:
            at = last
            while at > first and not lines[at - 1].strip():  # before the blank lines that end the part
                at -= 1
            lines.insert(at, f"{key} = {rendered}")
            last += 1
    return "\n".join(lines) + "\n"


def write_settings(path: Path | str, values: dict[str, Any], example: Path | None = None) -> Path:
    """*values* (setting -> value) written into the taslation.toml at *path* (made from the example first when there
    is none: `create_settings_file`), its notes and its other lines kept (`edit_settings_text`). The new text is read
    back before it replaces the file: each value must come back as it was given and the settings must validate, else
    ConfigError and the file is left as it was. The file written."""
    import tomllib

    from .atomic import write_atomic

    target = Path(path)
    unknown = sorted(set(values) - setting_names())
    if unknown:
        raise ConfigError(f"unknown settings: {', '.join(unknown)}")
    create_settings_file(target, example)
    with open(target, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8-sig")
    new = edit_settings_text(text, values)
    try:
        data = tomllib.loads(new)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"the settings could not be written into {target}: {e}") from None
    if "taslation" in data and isinstance(data["taslation"], dict):
        data = data["taslation"]
    for key, value in values.items():
        if _coerce({key: data.get(key)}).get(key) != _coerce({key: value}).get(key):
            raise ConfigError(f"the setting {key} could not be written into {target}")
    known = {k: v for k, v in data.items() if k in setting_names()}
    Settings(**_coerce(known)).validate()
    if "\r\n" in text:  # a file kept with Windows line ends keeps them
        new = new.replace("\r\n", "\n").replace("\n", "\r\n")
    write_atomic(target, new.encode("utf-8"))
    return target


def _coerce(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    for key in ("models_dir", "state_dir"):
        if key in out:
            out[key] = Path(str(out[key])).expanduser()
    if "margins" in out:
        m = out["margins"]
        if isinstance(m, str):
            m = [int(x) for x in m.replace(" ", "").split(",") if x]
        m = tuple(int(x) for x in m)
        if len(m) != 4:
            raise ConfigError("margins must be four integers: left, top, right, bottom")
        out["margins"] = m
    if "font_path" in out and out["font_path"] is not None:
        out["font_path"] = str(out["font_path"])
    keep_alive = out.get("ollama_keep_alive")
    if isinstance(keep_alive, (int, float)) and not isinstance(keep_alive, bool):
        out["ollama_keep_alive"] = str(keep_alive)  # ollama_keep_alive = -1 in the file: seconds, as "-1" says them
    return out
