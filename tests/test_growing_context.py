"""Earlier pairs that only grow, cut back rarely (`taslation.translate.base.GrowingContext`): for PLaMo, whose server
reuses the beginning of a prompt only when the next prompt extends the one before byte for byte, the pairs a page's
request starts from grow from page to page and are cut back to the newest 20 once they pass
60, earlier when a request would not fit after them. Checked on the final prompt strings against a stand-in server
that keeps what a server keeps (the last prompt and its answer): every request extends the one before it but the
first after a cut. The chat translator keeps the last pages' pairs as before, and what resets the pairs (another book,
"Translate again") or leaves them alone (a model switch, Ask again, a corrected reading) does so as before.
Invented lines only."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pytest

from taslation import netguard
from taslation.pipeline import Pipeline
from taslation.regions import PageResult, TextRegion
from taslation.translate.base import (CONTEXT_CUT_TO, CONTEXT_GROWS_TO, GrowingContext, SentPair, grown_pairs,
                                     grows_context)
from taslation.translate.models import PLAMO
from taslation.translate.plamo import BOS, PlamoTranslator

LINES_A_PAGE = 7


class Server(HTTPServer):
    """/api/generate answering "EN:" + the line, keeping what a server keeps of the last request (its prompt and its
    answer): ``extends`` says for every request whether its prompt began with that."""

    prompts: list[str]
    extends: list[bool]
    kept: str


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code: int, obj) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send(200, {"models": [{"name": PLAMO.ollama_name + ":latest"}]})
        else:
            self._send(404, {"error": "404 page not found"})

    def do_POST(self):
        server = self.server
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
        prompt = payload.get("prompt") or ""
        if not prompt:
            self._send(200, {"response": "", "done": True})
            return
        source = prompt.rsplit("<|plamo:msg|>", 2)[-2].split("<|plamo:tag|>")[0]
        answer = "\n".join(english(part) for part in source.split("\n"))  # (a joined run: a line per bubble)
        server.extends.append(bool(server.kept) and prompt.startswith(server.kept))
        server.prompts.append(prompt)
        server.kept = prompt + answer
        self._send(200, {"response": answer, "done": True, "done_reason": "stop"})


@pytest.fixture
def server():
    srv = Server(("127.0.0.1", 0), Handler)
    srv.prompts, srv.extends, srv.kept = [], [], ""
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    netguard.install(allowed_ports={port}, audit_hook=False)
    try:
        yield srv, f"http://127.0.0.1:{port}"
    finally:
        netguard.uninstall()
        srv.shutdown()
        srv.server_close()


def line(page: int, k: int) -> str:
    return f"頁{page}の行{k}です。"  # (a sentence that ends: no line goes on into the next)


def english(source: str) -> str:
    """The stand-in model's translation of a line: its numbers in English words' place (with a stray asterisk, which
    the pipeline drops from the line as it is set, for a line with a star)."""
    import re

    return "Line " + " ".join(re.findall(r"\d+", source)) + "." + ("*" if "星" in source else "")


def region(source: str, row: int = 0) -> TextRegion:
    y0 = 300 * row
    return TextRegion(0, y0, 400, y0 + 300, np.full((300, 400), 255, np.uint8), (100, y0 + 100, 300, y0 + 200),
                      status="untranslated", source_text=source)


def page_regions(page: int, n: int = LINES_A_PAGE) -> list[TextRegion]:
    return [region(line(page, k), k) for k in range(n)]


# ------------------------------------------------------------------------------------------------ the store itself
def test_the_pairs_grow_and_are_cut_back_to_the_newest_once_they_pass_the_bound():
    assert (CONTEXT_GROWS_TO, CONTEXT_CUT_TO) == (60, 20)  # the measured thresholds
    grown = GrowingContext()
    grown.extend((f"j{i}", f"e{i}") for i in range(60))
    assert len(grown.take()) == 60 and grown.cuts == 0  # 60 is within the bound
    grown.append(("j60", "e60"))
    taken = grown.take()
    assert taken == [(f"j{i}", f"e{i}") for i in range(41, 61)] and grown.cuts == 1  # the newest 20
    assert grown.take() == taken and grown.cuts == 1  # (taken again: no second cut)
    grown.clear()
    assert grown.take() == [] and len(grown) == 0


def test_the_pairs_are_cut_earlier_when_a_request_would_not_fit_after_them():
    grown = GrowingContext()
    grown.extend((f"j{i}", f"e{i}") for i in range(30))
    assert len(grown.take(lambda pairs: len(pairs) <= 30)) == 30 and grown.cuts == 0
    assert len(grown.take(lambda pairs: len(pairs) <= 25)) == CONTEXT_CUT_TO and grown.cuts == 1
    grown.extend((f"k{i}", f"f{i}") for i in range(10))  # 30 again
    assert len(grown.take(lambda pairs: len(pairs) <= 8)) == 5  # 20 do not fit either: halved until they do
    assert grown.take()[-1] == ("k9", "f9")  # the newest kept


def test_plamo_fits_the_pairs_into_its_context_and_only_it_grows_them():
    tr = PlamoTranslator(num_ctx=8192)
    assert grows_context(tr) and not grows_context(object())
    from taslation.translate import OllamaTranslator

    assert not grows_context(OllamaTranslator())
    few = [("短い行です。", "A short line.")] * 60
    assert tr.context_fits(few, "")
    long = [("長" * 200, "long " * 100)] * 60  # ~400 tokens reckoned high a pair
    assert not tr.context_fits(long, "")
    assert not tr.context_fits(few, "注" * 7000)  # premises that leave no room


# ------------------------------------------------------------------------------------------------ pages read one by one
def test_each_pages_prompts_extend_the_page_befores_until_the_cut(server, settings):
    srv, url = server
    tr = PlamoTranslator(url=url, seed=1)
    p = Pipeline(settings, ocr=None, translator=tr)
    starts: list[int] = []  # the first request of each page
    for page in range(12):
        starts.append(len(srv.prompts))
        regions = page_regions(page)
        assert p._translate_regions(regions, lambda _m: None) == ""
        assert all(r.status == "translated" for r in regions)
    assert len(srv.prompts) == 12 * LINES_A_PAGE
    # 9 pages make 63 pairs (> 60): the 10th page starts from the newest 20, and its first prompt is new
    cut_at = starts[9]
    assert [i for i, extends in enumerate(srv.extends) if not extends] == [0, cut_at]
    first_after = srv.prompts[cut_at]
    assert first_after.count("<|plamo:tag|>input") == CONTEXT_CUT_TO + 1  # 20 earlier pairs and the line itself
    assert line(6, 1) in first_after and line(6, 0) not in first_after  # pairs 43-62: from page 6's second line on
    assert p._grown.cuts == 1
    # within the bound the prompt holds every line since the book began, in order
    last_before_cut = srv.prompts[cut_at - 1]
    assert last_before_cut.startswith(BOS) and last_before_cut.count("<|plamo:tag|>input") == 9 * LINES_A_PAGE


def test_the_chat_translator_keeps_the_last_pages_pairs(settings):
    class Chat:
        name = "chat"

        def __init__(self):
            self.contexts: list[list[tuple[str, str]]] = []

        def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None):
            self.contexts.append(list(context))
            return [english(t) for t in texts]

    tr = Chat()
    p = Pipeline(settings, ocr=None, translator=tr)
    for page in range(4):
        p._translate_regions(page_regions(page, 25), lambda _m: None)
    # context_pages 2: the last two pages, 40 pairs at most, sliding at every page as before
    assert tr.contexts[1] == [(line(0, k), english(line(0, k))) for k in range(25)]
    assert tr.contexts[3] == [(line(p_, k), english(line(p_, k))) for p_ in (1, 2) for k in range(25)][-40:]


def test_no_pairs_at_all_with_context_pages_0(server, settings):
    srv, url = server
    settings.context_pages = 0
    p = Pipeline(settings, ocr=None, translator=PlamoTranslator(url=url))
    for page in range(2):
        p._translate_regions(page_regions(page, 2), lambda _m: None)
    assert p.context_pairs() == [] and srv.prompts[2].count("<|plamo:tag|>input") == 1


def test_what_resets_the_pairs_and_what_leaves_them_as_they_were(server, settings):
    srv, url = server
    tr = PlamoTranslator(url=url)
    p = Pipeline(settings, ocr=None, translator=tr)
    for page in range(2):
        p._translate_regions(page_regions(page), lambda _m: None)
    held = p.context_pairs()
    assert len(held) == 2 * LINES_A_PAGE
    # Ask again: the page's own lines before the region, nothing of the pairs, which stay
    regions = page_regions(5, 3)
    for r in regions[:2]:
        r.status, r.translated_text = "translated", "x"
    result = PageResult(image=None, original=None, regions=regions)
    srv.prompts.clear()
    p.ask_again(result, regions[2])
    assert srv.prompts[0].count("<|plamo:tag|>input") == 3 and line(0, 0) not in srv.prompts[0]
    assert p.context_pairs() == held
    # a reading corrected: the pairs stay
    p.correct_reading(result, regions[2], "直した行です。")
    assert p.context_pairs() == held
    # another translator for the language (a model switch): the pairs stay, as the pages' pairs did
    p.set_translator(PlamoTranslator(url=url))
    assert p.context_pairs() == held
    # another book, or the page's translations forgotten (Translate again): all of them go
    p.reset_context()
    assert p.context_pairs() == [] and p._context.maxlen == settings.context_pages and not p._context


def test_a_line_reused_without_a_request_is_left_out_of_pairs_that_only_grow(server, settings):
    srv, url = server
    p = Pipeline(settings, ocr=None, translator=PlamoTranslator(url=url))

    class Plan:  # (the lines `linememo` reuses: here the second one)
        def __init__(self, plan):
            self._plan = plan
            plan.served = {1: "Reused line."}
            plan.asked = [i for i in range(len(plan.texts)) if i != 1]

        def __getattr__(self, name):
            return getattr(self._plan, name)

    import taslation.linememo as linememo

    real = linememo.plan_for
    linememo.plan_for = lambda *a, **k: Plan(real(*a, **k))
    try:
        p._translate_regions(page_regions(0, 3), lambda _m: None)
    finally:
        linememo.plan_for = real
    assert [src for src, _dst in p.context_pairs()] == [line(0, 0), line(0, 2)]
    assert [src for src, _dst in p._context[-1]] == [line(0, 0), line(0, 1), line(0, 2)]  # (the chat's: all of them)


# ------------------------------------------------------------------------------------------------ what the server computed
def open_regions(page: int, n: int = LINES_A_PAGE) -> list[TextRegion]:
    """A page whose first line goes on in the second (a joined run, one request), and whose third has a star (its
    answer comes with a stray asterisk, which the line as set leaves out)."""
    out = page_regions(page, n)
    out[0].source_text = f"頁{page}の行0で、"
    out[2].source_text = f"頁{page}の星2です。"
    return out


def test_a_joined_run_and_an_answer_set_otherwise_leave_the_next_pages_prompt_extending_this_ones(server, settings):
    """The pairs that only grow hold what the server computed: a joined run as one pair, as it was asked and answered,
    and an answer as the model wrote it, though the page shows it otherwise (a stray asterisk dropped): every request
    extends the one before it, the first of each page too."""
    srv, url = server
    p = Pipeline(settings, ocr=None, translator=PlamoTranslator(url=url, seed=1))
    for page in range(3):
        regions = open_regions(page)
        assert p._translate_regions(regions, lambda _m: None, unit_box=(0, 0, 400, 300 * LINES_A_PAGE)) == ""
        assert [r.translated_text for r in regions[:3]] == [f"Line {page} 0.", f"Line {page} 1.", f"Line {page} 2."]
    assert len(srv.prompts) == 3 * (LINES_A_PAGE - 1)  # (the first two lines of each page in one request)
    assert srv.extends == [False] + [True] * (len(srv.prompts) - 1)
    last = srv.prompts[-1]
    assert "頁2の行0で、\n頁2の行1です。<|plamo:tag|>output" in last and "Line 2 2.*" in last  # as computed
    pairs = p._grown.take()
    assert pairs[-LINES_A_PAGE + 1] == ("頁2の行0で、\n頁2の行1です。", "Line 2 0.\nLine 2 1.")
    assert pairs[-LINES_A_PAGE + 2] == ("頁2の星2です。", "Line 2 2.*")
    assert all(isinstance(pair, SentPair) for pair in pairs)


def test_a_request_beside_a_page_that_took_the_pairs_past_their_bound_extends_its_last_prompt(server, settings):
    """The pairs given to a request beside the page (where a bubble's larger lettering is) are taken whole: after a
    page whose lines took them past `CONTEXT_GROWS_TO`, its prompt still begins as the page's last prompt and its
    answer, which the server holds."""
    srv, url = server
    tr = PlamoTranslator(url=url, seed=1)
    before = [(line(0, k), english(line(0, k))) for k in range(CONTEXT_GROWS_TO - 2)]
    computed: list = []
    texts = [line(1, k) for k in range(LINES_A_PAGE)]
    assert tr.translate_page(texts, before, "", computed=computed) == [english(t) for t in texts]
    assert len(before) + len(computed) > CONTEXT_GROWS_TO
    tr.translate_aside("頁1の行3", [*before, *computed], "")
    assert srv.extends == [False] + [True] * LINES_A_PAGE  # the aside too
    assert line(0, 0) in srv.prompts[-1]  # (the oldest pair kept)


def test_grown_pairs_keep_what_was_computed_and_add_a_line_filled_later_at_the_end():
    def usable(src, dst):
        return dst != "?"

    computed = [SentPair("一", "One."), SentPair("二で、\n三", "Two,\nthree."), SentPair("四", "?"),
                SentPair("五で、\n六", "Five, six.")]  # (the last did not split back: not taken)
    finals = [("一", "One*."), ("二で、", "Two,"), ("三", "three."), ("四", "Four."), ("七", "Seven.")]
    got = grown_pairs(computed, finals, usable)
    assert got == [("一", "One."), ("二で、\n三", "Two,\nthree."), ("四", "Four."), ("七", "Seven.")]
    assert isinstance(got[0], SentPair) and isinstance(got[1], SentPair) and not isinstance(got[2], SentPair)
    grown = GrowingContext()
    grown.extend(got)
    assert isinstance(grown.take()[1], SentPair)  # (kept as computed: never made one line)


def test_grown_pairs_hold_a_name_as_the_page_respelt_it_and_the_rest_as_computed():
    """An answer the page sets otherwise than by its spaces and stray asterisks (a name respelt as the series sheet
    spells it) is held as the page sets it, a joined run's still a line per bubble; the others as the model wrote
    them."""
    computed = [SentPair("一", "Tanaka  came."), SentPair("二で、\n三", "Tanaka said,\nthree*"),
                SentPair("四", "Four*")]
    finals = [("一", "Tanaka came."), ("二で、", "Tanakah said,"), ("三", "three"), ("四", "Four")]
    got = grown_pairs(computed, finals, lambda _s, _d: True)
    assert got == [("一", "Tanaka  came."), ("二で、\n三", "Tanakah said,\nthree"), ("四", "Four*")]
    assert all(isinstance(pair, SentPair) for pair in got)
