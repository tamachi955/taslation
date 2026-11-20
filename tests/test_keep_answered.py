"""A page the reader turned away from while it was translated keeps the lines answered by then (`pipeline.turn_away`,
`Pipeline._keep_answered`): set as the page done whole sets them, stored with the page marked as lacking the rest
(`CachedPage.incomplete`), the earlier pairs grown with them as the request computed them; the page read again asks
only for the rest and ends complete, the kept lines as they were. Stop keeps nothing, nor does a frame never confirmed
(`Provisional`). A sharper picture of the page puts back an entry the job added to (`PageWork.replaced`). Against a
stand-in PLaMo server; invented lines only."""
from __future__ import annotations

import threading
import time

import numpy as np
import pytest
from helpers import FakeOcr
from test_early_start_pipeline import _state
from test_growing_context import page_regions, server  # noqa: F401 - the stand-in server and its fixture

from taslation.cache import CacheStore
from taslation.messages import Cancelled
from taslation.pipeline import PageFill, PageGate, Pipeline, keeps_answered, turn_away
from taslation.translate.plamo import PlamoTranslator


def _source(prompt: str) -> str:
    return prompt.rsplit("<|plamo:msg|>", 2)[-2].split("<|plamo:tag|>")[0]


def _turned_after(tr: PlamoTranslator, cancel: threading.Event, requests: int, stop: bool = False) -> None:
    """The reader turns away (or presses Stop, *stop*) once *requests* of the translator's requests are answered."""
    real = tr._generate
    done = [0]

    def generate(*a, **k):
        out = real(*a, **k)
        done[0] += 1
        if done[0] == requests:
            cancel.set() if stop else turn_away(cancel)
        return out

    tr._generate = generate


def _pipeline(settings, url: str, book: str = "Kept") -> Pipeline:
    cache = CacheStore(settings.cache_dir).open(book, "plamo")
    return Pipeline(settings, ocr=FakeOcr(), translator=PlamoTranslator(url=url, seed=1), cache=cache)


def test_turn_away_marks_the_cancel_and_stop_does_not():
    a, b = threading.Event(), threading.Event()
    turn_away(a)
    b.set()
    assert a.is_set() and keeps_answered(a) and b.is_set() and not keeps_answered(b) and not keeps_answered(None)


@pytest.mark.parametrize("stop", [False, True])
def test_the_lines_answered_before_the_turn_are_set_and_grow_the_history(server, settings, stop):  # noqa: F811
    srv, url = server
    p = Pipeline(settings, ocr=None, translator=PlamoTranslator(url=url, seed=1))
    regions = page_regions(0)
    cancel = threading.Event()
    _turned_after(p.translator, cancel, 3, stop)
    fill = PageFill(p, np.zeros((10, 10, 3), np.uint8), lambda kind, data: None)
    with pytest.raises(Cancelled):
        p._translate_regions(regions, lambda _m: None, fill, cancel)
    done = [r for r in regions if r.status == "translated"]
    if stop:  # Stop: nothing of the page
        assert done == [] and list(p._grown) == []
        return
    assert [r.source_text for r in done] == [r.source_text for r in regions[:3]]
    assert all(r.status == "untranslated" for r in regions[3:])
    assert all(r.translated_text == f"Line 0 {k}." for k, r in enumerate(done))
    assert [tuple(x) for x in p._grown] == [(r.source_text, r.translated_text) for r in done]
    # the next page's first prompt extends what the server holds: the history is what was translated
    p.translator._generate = PlamoTranslator._generate.__get__(p.translator)
    srv.extends.clear()
    assert p._translate_regions(page_regions(1, 2), lambda _m: None) == ""
    assert srv.extends == [True, True]


@pytest.mark.parametrize("second", ["What is it?", "Nani?"])
def test_a_romanised_line_asked_again_before_the_turn_is_kept_and_one_not_asked_again_yet_is_not(  # noqa: F811
        server, settings, monkeypatch, second):
    import test_growing_context as stand_in
    from test_growing_context import region

    srv, url = server
    seen: dict[str, int] = {}
    english = stand_in.english

    def answer(source: str) -> str:  # (a short kana line: its romaji at first, *second* when asked again)
        seen[source] = seen.get(source, 0) + 1
        if source in ROMAJI:
            return ROMAJI[source] if seen[source] == 1 else second
        return english(source)

    monkeypatch.setattr(stand_in, "english", answer)
    p = Pipeline(settings, ocr=None, translator=PlamoTranslator(url=url, seed=1))
    regions = [region("なに?", 0), region("はい?", 1), region("頁0の行2です。", 2)]
    cancel = threading.Event()
    _turned_after(p.translator, cancel, 4)  # the three lines, then the first asked again: the turn
    fill = PageFill(p, np.zeros((10, 10, 3), np.uint8), lambda kind, data: None)
    with pytest.raises(Cancelled):
        p._translate_regions(regions, lambda _m: None, fill, cancel)
    assert seen == {"なに?": 2, "はい?": 1, "頁0の行2です。": 1}
    # (asked again, the line is final as a page done whole leaves it - romaji again, the first answer stays -; the
    # line not asked again yet is left for the page's next reading)
    assert [r.status for r in regions] == ["translated", "untranslated", "translated"]
    assert [r.translated_text for r in regions if r.status == "translated"] == [second, "Line 0 2."]


ROMAJI = {"なに?": "Nani?", "はい?": "Hai?"}


def test_asking_again_tells_each_lines_final_answer():
    from taslation.translate.base import ask_again_romanised

    class Fake:
        def __init__(self, answers):
            self.answers = list(answers)

        def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None, **kwargs):
            return [self.answers.pop(0)]

    told: list[tuple[int, str]] = []
    out, asked, left = ask_again_romanised(Fake(["What?", "Hai?"]), ["来た", "なに?", "はい?"],
                                           ["It came", "Nani?", "Hai?"], on_answer=lambda i, t: told.append((i, t)))
    assert out == ["It came", "What?", "Hai?"] and (asked, left) == (2, 1)
    assert told == [(1, "What?"), (2, "Hai?")]  # (the first answer, when the second is romaji again)


def test_a_page_turned_away_from_is_stored_incomplete_and_read_again_asks_only_the_rest(server, settings,  # noqa: F811
                                                                                        sample_page):
    srv, url = server
    p = _pipeline(settings, url)
    cancel = threading.Event()
    _turned_after(p.translator, cancel, 2)
    with pytest.raises(Cancelled):
        p.process(sample_page, cancel=cancel, events=lambda kind, data: None)
    assert len(p.cache.pages) == 1
    page = p.cache.pages[0]
    kept = {tuple(b.box): b.text for b in page.bubbles}
    assert page.incomplete and 0 < len(kept)
    asked_before = len(srv.prompts)
    p.translator._generate = PlamoTranslator._generate.__get__(p.translator)
    result = p.process(sample_page, events=lambda kind, data: None)  # the reader comes back to it
    again = [_source(prompt) for prompt in srv.prompts[asked_before:]]
    lines_again = sum(s.count("\n") + 1 for s in again)
    assert lines_again == len([r for r in result.regions if r.status == "translated"]) - len(kept)
    page = p.cache.pages[0]
    assert not page.incomplete and len(page.bubbles) == len(result.translated)
    assert all(kept[box] == text for box, text in ((tuple(b.box), b.text) for b in page.bubbles) if box in kept)


def test_a_completion_turned_away_from_adds_what_came_and_tells_the_entry_it_replaced(server, settings,  # noqa: F811
                                                                                      sample_page):
    srv, url = server
    p = _pipeline(settings, url, "Completed")
    cancel = threading.Event()
    _turned_after(p.translator, cancel, 1)
    with pytest.raises(Cancelled):
        p.process(sample_page, cancel=cancel, events=lambda kind, data: None)
    before = [b.text for b in p.cache.pages[0].bubbles]
    p.translator._generate = PlamoTranslator._generate.__get__(p.translator)
    cancel = threading.Event()
    _turned_after(p.translator, cancel, 1)
    with p.page_on_show() as work:
        with pytest.raises(Cancelled):
            p.process(sample_page, cancel=cancel, events=lambda kind, data: None)
    page = p.cache.pages[0]
    assert page.incomplete and len(page.bubbles) == len(before) + 1  # (one more line came)
    assert [x[0] for x in work.stored] == [page.fingerprint]
    assert [b.text for b in work.replaced[0].bubbles] == before  # (the entry as it was: a sharper picture puts it back)
    p.forget_page(type("R", (), {"units": [type("U", (), {"fingerprint": page.fingerprint,
                                                           "aspect": page.aspect})()]})())
    p.restore_pages(work.replaced)
    assert [b.text for b in p.cache.pages[0].bubbles] == before


def test_nothing_is_kept_of_a_frame_never_confirmed(server, settings, sample_page):  # noqa: F811
    srv, url = server
    p = _pipeline(settings, url, "Unconfirmed")
    state = _state(p)
    gate = PageGate()
    cancel = threading.Event()
    _turned_after(p.translator, cancel, 2)
    errors: list[BaseException] = []

    def job():
        try:
            with p.page_on_show(gate):
                p.process(sample_page, cancel=cancel, events=lambda kind, data: None)
        except BaseException as e:  # noqa: BLE001 - looked at below
            errors.append(e)

    thread = threading.Thread(target=job, daemon=True)
    thread.start()
    end = time.monotonic() + 30
    while thread.is_alive() and time.monotonic() < end:
        gate.seen(time.monotonic())  # (the window sees the frame on show: the model is asked, never confirmed)
        time.sleep(0.02)
    thread.join(5)
    assert errors and isinstance(errors[0], Cancelled) and len(srv.prompts) >= 2
    assert _state(p) == state  # nothing of the job lasts: no page, no pairs, no lines
