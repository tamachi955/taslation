"""Where a translation's counterpart of a bubble's larger lettering is (`taslation.locate_large`), and how the part
found goes with the translation: found once the page's translations are final, by requests beside the page's that
change no word of it (`Pipeline.large_part`, `_locate_large`; the whole-book run's `settle`), kept in the cache as the
optional bubble key ``large`` (offsets into the translation, never the Japanese), taken back from it without a request,
following an edit of the text that leaves it be and dropped by one that touches it. Versions 0.1.0 and 0.2.0 read a
file with the key (their readers, copied below as they were, ignore keys they do not know). Invented lines only."""
from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pytest

from taslation import fingerprint as fp
from taslation import linememo
from taslation import locate_large as ll
from taslation.batch import BatchReader
from taslation.cache import BookCache, CacheStore, CachedBubble, CachedPage, TextEdit
from taslation.messages import Cancelled, Message
from taslation.pipeline import Pipeline, ScannedRegion, ScannedUnit
from taslation.regions import PageResult, TextRegion
from taslation.size_mix import SizeMix
from taslation.translate import DictTranslator, TranslationError

FP = "b" * 80
SOURCE = "お前は今すぐ出て行け"  # the last four characters lettered larger
SPAN = (6, 10)
PART = SOURCE[6:10]
TRANSLATION = "You, get out right now!"
PLAIN, PLAIN_EN = "普通の行です。", "A plain line."
MIX = SizeMix(start=6, end=10, ratio=1.6, base=20.0)


class Aside(DictTranslator):
    """A stand-in translator that answers requests beside a page's from *aside* (Japanese -> answer), each kept with
    the pairs it started from; *fail*: each fails; *cancel*: the first sets the event and is cancelled, as a model's
    request is when a turn comes."""

    def __init__(self, mapping, aside=None, fail=False, cancel: threading.Event | None = None):
        super().__init__(mapping)
        self.aside = dict(aside or {})
        self.fail, self.cancel = fail, cancel
        self.asides: list[tuple[str, list[tuple[str, str]], str]] = []

    def translate_aside(self, text, context=(), notes="", cancel=None, on_slow=None):
        self.asides.append((text, list(context), str(notes)))
        if self.cancel is not None:
            self.cancel.set()
            raise Cancelled()
        if self.fail:
            raise TranslationError(Message("ollama.timeout", seconds=1.0))
        return self.aside.get(text, "")


MAPPING = {SOURCE: TRANSLATION, PLAIN: PLAIN_EN}
FOUND_ALONE = {PART: "Get out!"}
FOUND_MARKED = {PART: "Get out of here", ll.marked_source(SOURCE, SPAN): "You, <b>get out</b> right now!"}


def _region(source: str, row: int = 0, mix: SizeMix | None = None) -> TextRegion:
    y0 = 300 * row
    r = TextRegion(0, y0, 400, y0 + 300, np.full((300, 400), 255, np.uint8), (100, y0 + 100, 300, y0 + 200),
                   status="untranslated", source_text=source)
    r.size_mix = mix
    return r


def _pipeline(settings, translator, name: str = "Large") -> Pipeline:
    cache = CacheStore(settings.cache_dir).open(name, "fake")
    return Pipeline(settings, ocr=None, translator=translator, cache=cache)


# ------------------------------------------------------------------------------------------------ the locating rule
def test_the_part_alone_is_found_once_at_word_edges_and_snapped_with_its_closing_marks():
    at = ll.from_alone(TRANSLATION, "Get out!")
    assert TRANSLATION[at[0]:at[1]] == "get out"
    whole = "Wait. Run away!! Now."
    at = ll.from_alone(whole, "run away")
    assert whole[at[0]:at[1]] == "Run away!!"  # (the marks that close it along)
    assert ll.from_alone("No, no, no.", "no") is None  # there more than once
    assert ll.from_alone("Run!", "Run") is None  # all of it
    assert ll.from_alone("Running late.", "run") is None  # inside a word: no edge


def test_a_marked_part_counts_only_when_it_is_plausible_and_the_part_alone_bears_it_out():
    answer = "You, <b>get out</b> right now!"
    at = ll.from_marked(TRANSLATION, answer, SOURCE, SPAN, "Get out of here")
    assert TRANSLATION[at[0]:at[1]] == "get out"
    assert ll.from_marked(TRANSLATION, answer, SOURCE, SPAN, "Leave.") is None  # nothing of it in the part alone
    assert ll.from_marked(TRANSLATION, answer, SOURCE, SPAN, "You get out of here right now, OK?") is None  # a line
    assert ll.from_marked(TRANSLATION, "<b>You, get out right now!</b>", SOURCE, SPAN, "Get out") is None  # all of it
    assert ll.from_marked(TRANSLATION, "You, get out right now!", SOURCE, SPAN, "Get out") is None  # no marker
    longer = "You, get out of here right now!"
    assert ll.from_marked(longer, "You, get out <b>of</b> here", SOURCE, SPAN, "of") is None  # its share too small


def test_locate_asks_the_part_alone_first_and_the_marked_line_only_when_that_found_nothing():
    asked: list[str] = []

    def ask_from(answers):
        def ask(text):
            asked.append(text)
            return answers.get(text, "")
        return ask

    found = ll.locate(SOURCE, SPAN, TRANSLATION, ask_from(FOUND_ALONE))
    assert found == ll.Located((5, 12), "alone", 1) and asked == [PART]
    asked.clear()
    found = ll.locate(SOURCE, SPAN, TRANSLATION, ask_from(FOUND_MARKED))
    assert found == ll.Located((5, 12), "marked", 2) and asked == [PART, ll.marked_source(SOURCE, SPAN)]
    asked.clear()
    assert ll.locate(SOURCE, SPAN, TRANSLATION, ask_from({})) == ll.Located(None, "", 2)
    asked.clear()  # a part the book translated before as a line of its own: no request for it
    found = ll.locate(SOURCE, SPAN, TRANSLATION, ask_from({}), known=lambda part: "Get out!" if part == PART else None)
    assert found == ll.Located((5, 12), "alone", 0) and asked == []
    # nothing to look for: a part that is all of the line, or nothing
    assert ll.locate(SOURCE, (0, len(SOURCE)), TRANSLATION, ask_from(FOUND_ALONE)).requests == 0
    assert ll.locate(SOURCE, (3, 3), TRANSLATION, ask_from(FOUND_ALONE)).at is None


def test_a_line_broken_in_two_is_asked_as_one_line_and_the_part_follows():
    text, at = ll.one_line("お前は\n今すぐ出て行け", (7, 11))
    assert text == "お前は 今すぐ出て行け" and text[at[0]:at[1]] == PART


# ------------------------------------------------------------------------------------------------ the kept part
def test_a_part_is_checked_against_its_text():
    assert ll.checked("abc", [0, 2, 1.5]) == (0, 2, 1.5)
    for bad in ((0, 4, 1.5), (2, 2, 1.5), (-1, 2, 1.5), (0, 2, 1.0), (0, 2, 2.5), (0, 2, math.nan), (0.0, 2, 1.5),
                (True, 2, 1.5), (0, 2, True), (0, 2), "0,2,1.5", None, (0, 2, "1.5")):
        assert ll.checked("abc", bad) is None, bad
    assert ll.checked("a  b", (1, 3, 1.5)) is None  # spaces alone


def test_a_part_follows_an_edit_that_leaves_it_be_and_goes_with_one_that_touches_it():
    large = (5, 12, 1.6)
    assert ll.follow(TRANSLATION, "Hey, you, get out right now!", large) == (10, 17, 1.6)  # before it: moved
    assert ll.follow(TRANSLATION, "You, get out right now, OK?", large) == large  # after it: as it was
    assert ll.follow(TRANSLATION, TRANSLATION, large) == large
    assert ll.follow(TRANSLATION, "You, get lost right now!", large) is None  # a word of it changed
    assert ll.follow(TRANSLATION, "You, get right out right now!", large) is None  # a word put inside it
    assert ll.follow(TRANSLATION, "Right now!", large) is None  # it went
    assert ll.follow(TRANSLATION, "x", None) is None


# ------------------------------------------------------------------------------------------------ the cache file
def test_the_key_is_written_only_when_set_and_dropped_when_it_does_not_fit_the_text():
    plain = CachedBubble(box=(0.1, 0.1, 0.5, 0.5), text=TRANSLATION)
    assert "large" not in plain.to_json()
    bubble = CachedBubble(box=(0.1, 0.1, 0.5, 0.5), text=TRANSLATION, large=(5, 12, 1.6))
    d = bubble.to_json()
    assert d["large"] == [[5, 12, 1.6]]
    assert CachedBubble.from_json(json.loads(json.dumps(d))).large == (5, 12, 1.6)
    for bad in ([[5, 99, 1.6]], [[5, 12, 3.0]], [[5, 12, 0.5]], [[5, 12]], [5, 12, 1.6], "5-12", [[5, 12, 1.6]] * 2,
                [["5", "12", "1.6"]]):
        kept = CachedBubble.from_json({**d, "large": bad})
        assert kept.large is None and kept.text == TRANSLATION, bad  # (the bubble itself stays)


def test_no_japanese_and_no_offset_into_it_goes_to_the_file(settings):
    tr = Aside(MAPPING, FOUND_ALONE)
    p = _pipeline(settings, tr)
    regions = [_region(SOURCE, 0, MIX), _region(PLAIN, 1)]
    assert p._translate_regions(regions, lambda _m: None) == ""
    unit = fp.PageUnit((0, 0, 400, 600), FP, 0)
    p._store_regions(unit, regions)
    from helpers import store_text

    raw = store_text(p.cache.path)
    bubbles = json.loads(raw)["pages"][0]["bubbles"]
    assert [b.get("large") for b in bubbles] == [[[5, 12, 1.6]], None]
    assert SOURCE not in raw and PART not in raw and PLAIN not in raw and raw.count('"large"') == 1


# the readers of versions 0.1.0 and 0.2.0 (taslation/cache.py at v0.1.0 and v0.2.0), copied as they were: a key they
# do not know is ignored
MAX_COORD = 1e5
FINGERPRINT_HEX_LEN = 80
SCHEMA_VERSION = 1


def _finite(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("not a finite number")
    return number


def _coord(value: Any) -> float:
    number = _finite(value)
    if abs(number) > MAX_COORD:
        raise ValueError("not a position on the page")
    return number


@dataclass
class Bubble010:
    box: Any
    text: str
    poly: list = field(default_factory=list)
    flags: list = field(default_factory=list)
    note: str = ""
    angle: float = 0.0

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Bubble010":
        box = tuple(_coord(v) for v in d["box"])
        if len(box) != 4:
            raise ValueError("bad box")
        poly = [(_coord(p[0]), _coord(p[1])) for p in d.get("poly", [])]
        flags = [str(f) for f in d.get("flags", []) if f]
        angle = _finite(d.get("angle", 0.0))
        return cls(box=box, text=str(d.get("text", "")), poly=poly, flags=flags,  # type: ignore[arg-type]
                   note=str(d.get("note", "") or ""), angle=angle if abs(angle) < 90 else 0.0)


@dataclass
class Bubble020(Bubble010):
    reused: bool = False
    edited: bool = False

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Bubble020":
        box = tuple(_coord(v) for v in d["box"])
        if len(box) != 4:
            raise ValueError("bad box")
        poly = [(_coord(p[0]), _coord(p[1])) for p in d.get("poly", [])]
        flags = [str(f) for f in d.get("flags", []) if f]
        angle = _finite(d.get("angle", 0.0))
        return cls(box=box, text=str(d.get("text", "")), poly=poly, flags=flags,  # type: ignore[arg-type]
                   note=str(d.get("note", "") or ""), angle=angle if abs(angle) < 90 else 0.0,
                   reused=d.get("reused") is True, edited=d.get("edited") is True)


def _old_pages(data: dict[str, Any], bubble: Any) -> list[tuple[str, list[Any]]]:
    """`BookCache.from_json` and `CachedPage.from_json` of both versions (the same in each): the schema checked,
    each page read, one that fails to read skipped."""
    if not isinstance(data, dict) or data.get("schema") != SCHEMA_VERSION:
        raise ValueError("unsupported cache schema")
    pages = data.get("pages", [])
    if not isinstance(pages, list):
        raise ValueError("no list of pages")
    out = []
    for raw in pages:
        try:
            f = str(raw["fp"]).lower()
            if len(f) != FINGERPRINT_HEX_LEN or any(c not in "0123456789abcdef" for c in f):
                raise ValueError("bad fingerprint")
            _finite(raw.get("aspect", 0.0))
            int(raw.get("seq", 0))
            out.append((f, [bubble.from_json(b) for b in raw.get("bubbles", [])]))
        except (ValueError, TypeError, KeyError, OverflowError):
            continue
    return out


def test_versions_0_1_0_and_0_2_0_read_a_file_written_with_the_key(settings):
    cache = CacheStore(settings.cache_dir).open("Old readers", "fake")
    cache.add(CachedPage(fingerprint=FP, aspect=0.7, seq=-1, bubbles=[
        CachedBubble(box=(0.1, 0.1, 0.5, 0.5), text=TRANSLATION, large=(5, 12, 1.6), edited=True),
        CachedBubble(box=(0.1, 0.6, 0.5, 0.9), text=PLAIN_EN)]))
    data = json.loads(json.dumps(cache.to_json()))
    assert data["pages"][0]["bubbles"][0]["large"] == [[5, 12, 1.6]]
    for bubble in (Bubble010, Bubble020):
        pages = _old_pages(data, bubble)
        assert len(pages) == 1 and [b.text for b in pages[0][1]] == [TRANSLATION, PLAIN_EN]
    assert _old_pages(data, Bubble020)[0][1][0].edited is True
    back = BookCache.from_json(data, cache.path)  # (and this version takes it back)
    assert [b.large for b in back.pages[0].bubbles] == [(5, 12, 1.6), None]


# ------------------------------------------------------------------------------------------------ edits of the text
def _book_with(settings, large=(5, 12, 1.6)) -> BookCache:
    cache = CacheStore(settings.cache_dir).open("Edits", "fake")
    cache.add(CachedPage(fingerprint=FP, aspect=0.7, seq=-1,
                         bubbles=[CachedBubble(box=(0.1, 0.1, 0.5, 0.5), text=TRANSLATION, large=large)]))
    return cache


def test_find_and_replace_moves_the_part_or_drops_it_and_undo_puts_it_back(settings):
    cache = _book_with(settings)
    box = (0.1, 0.1, 0.5, 0.5)
    made = cache.put_texts([TextEdit(FP, box, TRANSLATION, "Hey, " + TRANSLATION, mark=True)])
    assert cache.pages[0].bubbles[0].large == (10, 17, 1.6)
    cache.put_texts([made[0].undone()])
    assert cache.pages[0].bubbles[0].large == (5, 12, 1.6) and cache.pages[0].bubbles[0].text == TRANSLATION
    made = cache.put_texts([TextEdit(FP, box, TRANSLATION, "You, go away right now!", mark=True)])
    assert cache.pages[0].bubbles[0].large is None  # the edit touched it
    cache.put_texts([made[0].undone()])
    assert cache.pages[0].bubbles[0].large == (5, 12, 1.6)  # undone: back as it was
    # an edit that says what the part becomes (an editor that set it on a selection, or cleared it)
    cache.put_texts([TextEdit(FP, box, TRANSLATION, TRANSLATION + " ", large=(0, 3, 1.5))])
    assert cache.pages[0].bubbles[0].large == (0, 3, 1.5)
    cache.put_texts([TextEdit(FP, box, TRANSLATION + " ", TRANSLATION, large=None)])
    assert cache.pages[0].bubbles[0].large is None


def test_a_name_respelt_moves_the_part_and_a_name_inside_it_drops_it(settings):
    cache = _book_with(settings)
    cache.rename([("You", "Thou")])
    assert cache.pages[0].bubbles[0].large == (6, 13, 1.6)
    assert cache.pages[0].bubbles[0].text[6:13] == "get out"
    cache.rename([("out", "oot")])
    assert cache.pages[0].bubbles[0].large is None


# ------------------------------------------------------------------------------------------------ a page read
def test_a_page_finds_the_part_once_its_translations_are_final_and_changes_no_word(settings):
    tr = Aside(MAPPING, FOUND_ALONE)
    p = _pipeline(settings, tr)
    p.reset_context()
    first = [_region("前のページの行です。", 0)]
    tr.mapping["前のページの行です。"] = "A line of the page before."
    p._translate_regions(first, lambda _m: None)
    regions = [_region(PLAIN, 0), _region(SOURCE, 1, MIX)]
    assert p._translate_regions(regions, lambda _m: None) == ""
    plain, mixed = regions
    assert mixed.translated_text == TRANSLATION and mixed.large == (5, 12, 1.6)
    assert plain.large is None
    assert [a[0] for a in tr.asides] == [PART]  # one request, for the bubble with a part, of the part alone
    # it starts from the pairs the next page's request starts from: the pages before, then this page's
    assert tr.asides[0][1] == [("前のページの行です。", "A line of the page before."), (PLAIN, PLAIN_EN),
                               (SOURCE, TRANSLATION)]
    assert tr.asides[0][2] == str(p.premises())
    assert p.context_pairs()[-1] == (SOURCE, TRANSLATION)  # (the requests beside left the pairs alone)
    assert len(tr.calls) == 2  # (the page's own request as ever)
    assert (p.large_tally.bubbles, p.large_tally.requests, p.large_tally.alone) == (1, 1, 1)


def test_step_two_a_failure_and_the_setting_off(settings):
    tr = Aside(MAPPING, FOUND_MARKED)
    p = _pipeline(settings, tr)
    regions = [_region(SOURCE, 0, MIX)]
    p._translate_regions(regions, lambda _m: None)
    assert regions[0].large == (5, 12, 1.6) and len(tr.asides) == 2
    tr = Aside(MAPPING, fail=True)  # the model fails: lettered at one size, the page translated as ever
    p = _pipeline(settings, tr, "Failing")
    regions = [_region(SOURCE, 0, MIX)]
    assert p._translate_regions(regions, lambda _m: None) == ""
    assert regions[0].status == "translated" and regions[0].large is None and len(tr.asides) == 1
    settings.size_emphasis = False  # off: no request, nothing set larger
    tr = Aside(MAPPING, FOUND_ALONE)
    p = _pipeline(settings, tr, "Off")
    regions = [_region(SOURCE, 0, MIX)]
    p._translate_regions(regions, lambda _m: None)
    assert regions[0].large is None and tr.asides == []


def test_a_turn_during_the_look_cancels_the_page_as_any_request_of_it(settings):
    cancel = threading.Event()
    tr = Aside(MAPPING, FOUND_ALONE, cancel=cancel)
    p = _pipeline(settings, tr)
    regions = [_region(SOURCE, 0, MIX)]
    with pytest.raises(Cancelled):
        p._translate_regions(regions, lambda _m: None, cancel=cancel)
    assert p.context_pairs() == []  # nothing of the page kept


def test_a_part_the_book_translated_before_takes_no_request(settings):
    settings.reuse_lines = True  # (the default; the tests' settings turn it off)
    tr = Aside(MAPPING, {})
    p = _pipeline(settings, tr)
    key = linememo.material(PART, {"speaker": "", "kind": ""})
    p.cache.lines.put(linememo.scope(tr, settings.target_language), key, "Get out!")
    regions = [_region(SOURCE, 0, MIX)]
    p._translate_regions(regions, lambda _m: None)
    assert regions[0].large == (5, 12, 1.6) and tr.asides == []
    assert p.line_tally.reused == 0  # (looked up, not counted as a line reused)


def test_a_page_from_the_cache_takes_its_part_back_without_a_request(settings):
    tr = Aside(MAPPING, FOUND_ALONE)
    p = _pipeline(settings, tr)
    regions = [_region(SOURCE, 0, MIX)]
    p._translate_regions(regions, lambda _m: None)
    unit = fp.PageUnit((0, 0, 400, 600), FP, 0)
    p._store_regions(unit, regions)
    reopened = CacheStore(settings.cache_dir).open("Large", "fake")
    page = reopened.pages[0]
    assert page.bubbles[0].large == (5, 12, 1.6)
    asked = len(tr.asides)
    live = [_region("", 0)]
    live[0].status = "unmatched"
    shown = p._apply_cached(unit, page, live, np.full((600, 400, 3), 255, np.uint8))
    assert [r.large for r in shown if r.status == "translated"] == [(5, 12, 1.6)]
    assert len(tr.asides) == asked


def test_the_editor_asks_again_finds_the_part_of_the_answer_and_its_save_keeps_or_follows_it(settings):
    tr = Aside(MAPPING, FOUND_ALONE)
    p = _pipeline(settings, tr)
    regions = [_region(SOURCE, 0, MIX)]
    p._translate_regions(regions, lambda _m: None)
    region = regions[0]
    result = PageResult(image=None, original=None, regions=regions, units=[fp.PageUnit((0, 0, 400, 600), FP, 0)])
    p.rerender = lambda _result: None  # (no picture to letter here)
    answer = "Hey you, get out right now!"
    assert p.large_of(result, region, answer) == (9, 16, 1.6)
    # Save of the text as it is keeps the part; an edit before it moves it; one inside it drops it
    assert p.set_translation(result, region, TRANSLATION, edited=True)
    assert region.large == (5, 12, 1.6) and p.cache.pages[0].bubbles[0].large == (5, 12, 1.6)
    assert p.set_translation(result, region, "Hey! " + TRANSLATION)
    assert region.large == (10, 17, 1.6)
    assert p.set_translation(result, region, "Hey! You, get lost right now!")
    assert region.large is None and p.cache.pages[0].bubbles[0].large is None
    assert p.set_translation(result, region, answer, edited=False, large=(9, 16, 1.6))  # the answer as it came
    assert region.large == (9, 16, 1.6) and p.cache.pages[0].bubbles[0].large == (9, 16, 1.6)


def test_the_page_caps_are_the_same_with_a_part_set_larger(settings):
    p = Pipeline(settings, ocr=None, translator=None)
    regions = [_region(PLAIN, 0), _region(SOURCE, 1)]
    texts = [PLAIN_EN, TRANSLATION]
    for r, t in zip(regions, texts):
        r.status, r.translated_text = "translated", t
    p.cap_sizes(regions, texts)
    before = [r.size_cap for r in regions]
    regions[1].large = (5, 12, 1.6)
    p.cap_sizes(regions, texts)
    assert [r.size_cap for r in regions] == before


# ------------------------------------------------------------------------------------------------ the translator's side
def test_plamos_request_beside_a_page_keeps_nothing(settings):
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from taslation import netguard
    from taslation.translate.models import PLAMO
    from taslation.translate.plamo import PlamoTranslator

    prompts: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, obj) -> None:
            body = json.dumps(obj).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._send({"models": [{"name": PLAMO.ollama_name + ":latest"}]})

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
            if payload.get("prompt"):
                prompts.append(payload["prompt"])
            self._send({"response": "Get  out!", "done": True, "done_reason": "stop"})

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    netguard.install(allowed_ports={srv.server_address[1]}, audit_hook=False)
    try:
        tr = PlamoTranslator(url=f"http://127.0.0.1:{srv.server_address[1]}", seed=1)
        p = Pipeline(settings, ocr=None, translator=tr)
        names = repr(vars(p.book_names))
        got = tr.translate_aside(PART, [(PLAIN, PLAIN_EN)], p.premises())
        assert got == "Get out!" and len(prompts) == 1
        assert PART in prompts[0] and PLAIN in prompts[0] and PLAIN_EN in prompts[0]  # after the pairs given
        assert tr.draws() == {} and repr(vars(p.book_names)) == names  # no draw counted, no name learnt
        with pytest.raises(Cancelled):
            cancel = threading.Event()
            cancel.set()
            tr.translate_aside(PART, [], "", cancel=cancel)
    finally:
        netguard.uninstall()
        srv.shutdown()
        srv.server_close()


# ------------------------------------------------------------------------------------------------ a whole-book run
def test_a_whole_book_run_finds_the_part_after_settling_and_stores_it(settings):
    tr = Aside(MAPPING, FOUND_ALONE)
    p = _pipeline(settings, tr)
    regions = [ScannedRegion((10, 10, 200, 100), (10, 10, 200, 100), [(0.0, 0.0), (190.0, 0.0), (190.0, 90.0)],
                             PLAIN, "untranslated"),
               ScannedRegion((10, 110, 200, 200), (10, 110, 200, 200), [(0.0, 0.0), (190.0, 0.0), (190.0, 90.0)],
                             SOURCE, "untranslated", order=1, size_mix=MIX)]
    unit = ScannedUnit(0, (0, 0, 400, 600), FP, 0.67, regions)
    reader = BatchReader(p, 0, settings, context_mode=True, book="Large")
    reader._translation_pass([unit], time.monotonic())
    stored = p.cache.pages[0].bubbles
    assert [(b.text, b.large) for b in stored] == [(PLAIN_EN, None), (TRANSLATION, (5, 12, 1.6))]
    assert [a[0] for a in tr.asides] == [PART]
    assert tr.asides[0][1][-2:] == [(PLAIN, PLAIN_EN), (SOURCE, TRANSLATION)]  # after the run's pairs
