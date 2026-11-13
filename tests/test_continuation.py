"""A sentence split across bubbles (`taslation.translate.continuation`) and a short kana line answered with its romaji
(`taslation.translate.base.bare_romanisation`, `ask_again_romanised`): which lines go on in the next bubble (an open
ending, the next region near it on the same page unit), the runs they make, the joined request and its answer split
back onto the bubbles, the PLaMo translator asking a run as one request and each line alone when the answer cannot be
split, and the romanised line asked for again with its neighbours."""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from taslation.messages import Cancelled
from taslation.translate import TranslationError, continuation
from taslation.translate.base import ask_again_romanised, bare_romanisation
from taslation.translate.continuation import (MAX_JOINED, continues, ends_open, facts_of, going_on, joined, near,
                                              runs, split_back)
from taslation.translate.plamo import PlamoTranslator

UNIT = (0, 0, 1000, 1500)  # a page unit; its shorter side 1000, so a region within 300 of another is near it


# ------------------------------------------------------------------ the rule
@pytest.mark.parametrize("text", ["お前もしかして", "だから…", "俺が", "それで、", "あの子のことは……", "行くけど",
                                  "見てたら ー", "雨なのに"])
def test_a_line_ending_on_a_particle_or_connective_is_open(text):
    assert ends_open(text)


@pytest.mark.parametrize("text", ["女か?", "そうだ。", "行くぞ!", "ありがとう", "「待って」", "…", "", "何で?"])
def test_a_sentence_end_or_another_word_closes_it(text):
    assert not ends_open(text)


def test_the_next_region_must_be_near_and_on_the_same_unit():
    box, close, far = (100, 100, 200, 300), (250, 100, 350, 300), (100, 900, 200, 1100)
    assert near(box, close, UNIT) and not near(box, far, UNIT)
    assert continues("お前もしかして", box, close, UNIT)
    assert not continues("お前もしかして", box, far, UNIT)  # across the page: another sentence
    assert not continues("お前もしかして", box, close, UNIT, same_unit=False)  # the other page of a spread
    assert not continues("お前もしかして", box, None, UNIT)  # the last region
    assert not continues("女か?", box, close, UNIT)


def test_going_on_reads_each_line_with_the_next():
    lines = [("お前もしかして", (100, 100, 200, 300), 0, UNIT), ("女か?", (250, 100, 350, 300), 0, UNIT),
             ("俺は", (100, 400, 200, 600), 0, UNIT), ("行く", (10, 10, 50, 50), 1, UNIT)]
    assert going_on(lines) == [True, False, False, False]  # 俺は: the next region is on the other unit


def test_facts_of_adds_the_page_and_the_rule_to_the_readers_facts(monkeypatch):
    regions = [SimpleNamespace(source_text="お前もしかして", bbox=(100, 100, 200, 300), speaker="Aki"),
               SimpleNamespace(source_text="女か?", bbox=(250, 100, 350, 300)),
               SimpleNamespace(source_text="そうだ", bbox=(100, 400, 200, 600), continues=True)]
    units = [(0, UNIT)] * 3
    facts = facts_of(regions, units)
    assert facts == [{"speaker": "Aki", "page": 0, "continues": True}, {"page": 0},
                     {"page": 0, "continues": True}]  # the reader's mark stands as it is
    monkeypatch.setattr(continuation, "AUTO", False)
    assert [f.get("continues", False) for f in facts_of(regions, units)] == [False, False, True]


def test_runs_join_lines_that_go_on_at_most_max_joined():
    meta = [{"continues": True}, {}, {"continues": True}, {"continues": True}, {"continues": True}, {}, {}]
    assert runs(meta, 7) == [[0, 1], [2, 3, 4], [5], [6]]
    assert runs(meta, 7, limit=1) == [[i] for i in range(7)]
    assert runs(None, 2) == [[0], [1]]
    assert MAX_JOINED == 3


# ------------------------------------------------------------------ the joined request and its answer
def test_joined_puts_a_line_break_between_bubbles():
    assert joined(["お前  もしかして", "女か?"]) == "お前 もしかして\n女か?"


def test_split_back_takes_exactly_one_line_per_bubble():
    assert split_back("Wait, are you...\n\n  a girl?  ", 2) == ["Wait, are you...", "a girl?"]
    assert split_back("Wait, are you a girl?", 2) is None  # merged
    assert split_back("Wait,\nare you\na girl?", 2) is None  # split further
    assert split_back("...\nA girl?", 2) == ["...", "A girl?"]  # dots alone are a bubble's answer
    assert split_back("", 1) is None


def _plamo(answers):
    """A PLaMo translator whose model answers from *answers* (the source -> the reply), recording each prompt."""
    tr = PlamoTranslator("http://127.0.0.1:9", seed=1)
    prompts = []

    def generate(prompt, max_tokens, seed, cancel, on_slow):
        source = prompt.rsplit("<|plamo:msg|>", 2)[-2].split("<|plamo:tag|>")[0]
        prompts.append((source, prompt))
        return answers(source)

    tr._generate = generate
    return tr, prompts


def test_plamo_asks_a_run_as_one_request_and_splits_the_answer_back():
    tr, prompts = _plamo(lambda s: "Wait, are you...\na girl?" if "\n" in s else "EN:" + s)
    got = []
    out = tr.translate_page(["お前もしかして", "女か?", "そうだ"], meta=[{"continues": True}, {}, {}],
                            on_item=lambda i, t: got.append(i))
    assert out == ["Wait, are you...", "a girl?", "EN:そうだ"] and got == [0, 1, 2]
    assert [s for s, _p in prompts] == ["お前もしかして\n女か?", "そうだ"]
    assert "<|plamo:msg|>女か?<|plamo:tag|>output" in prompts[1][1]  # both halves are earlier pairs of the next


def test_plamo_asks_each_line_alone_with_the_next_as_context_when_the_answer_does_not_split():
    tr, prompts = _plamo(lambda s: "Wait, are you a girl?" if "\n" in s else "EN:" + s)
    out = tr.translate_page(["お前もしかして", "女か?"], meta=[{"continues": True}, {}])
    assert out == ["EN:お前もしかして", "EN:女か?"]
    assert [s for s, _p in prompts] == ["お前もしかして\n女か?", "お前もしかして", "女か?"]
    context = prompts[1][1].split("<|plamo:tag|>context<|plamo:msg|>")[1].split("<|plamo:tag|>")[0]
    assert context.endswith("女か?")  # the line that goes on is asked with its continuation as context
    assert "<|plamo:tag|>context" not in prompts[2][1]


def test_plamo_does_not_join_two_speakers_and_takes_no_context_from_another_page():
    tr, prompts = _plamo(lambda s: "EN:" + s)
    tr.translate_page(["お前もしかして", "女か?"], meta=[{"continues": True, "speaker": "A"}, {"speaker": "B"}])
    assert [s for s, _p in prompts] == ["お前もしかして", "女か?"]
    assert "女か?" in prompts[0][1].split("<|plamo:tag|>input")[0]  # but the next line is still its context
    # the reader's own mark joins across the pages of a spread; asked alone, a line gets no context from another page
    tr, prompts = _plamo(lambda s: "one line" if "\n" in s else "EN:" + s)
    tr.translate_page(["お前もしかして", "女か?"], meta=[{"continues": True, "page": 0}, {"page": 1}])
    assert [s for s, _p in prompts] == ["お前もしかして\n女か?", "お前もしかして", "女か?"]
    assert "<|plamo:tag|>context" not in prompts[1][1]


def test_plamo_gives_a_line_asked_alone_the_lines_after_it():
    tr, prompts = _plamo(lambda s: "EN:" + s)
    tr.translate_page(["えっ"], [("前", "Before")], "", ["次の行", "その次", "三つ目"])
    context = prompts[0][1].split("<|plamo:tag|>context<|plamo:msg|>")[1].split("<|plamo:tag|>")[0]
    assert context == "次の行\nその次"  # `FOLLOW_ALONE` of them
    tr, prompts = _plamo(lambda s: "EN:" + s)
    tr.translate_page(["一", "二"], upcoming=["三"])  # a request of several lines: only what goes on gets them
    assert all("<|plamo:tag|>context" not in p for _s, p in prompts)


# ------------------------------------------------------------------ a short kana line left as romaji
@pytest.mark.parametrize("source, output", [("なに?", "Nani?"), ("はい", "Hai."), ("ふーん", "Fuun"),
                                            ("うん…", "Un..."), ("ナニ!?", "nani!?"), ("そう", "Sou")])
def test_bare_romanisation_is_the_kana_spelt_in_latin(source, output):
    assert bare_romanisation(source, output)


@pytest.mark.parametrize("source, output", [("なに?", "What?"), ("おっ!", "Oh!"), ("え?", "Eh?"), ("あはは", "Ahaha"),
                                            ("なにそれ", "Nanisore"), ("何?", "Nani?"), ("なに?", ""),
                                            ("Ok", "Ok")])
def test_a_translation_an_interjection_or_a_longer_line_is_not(source, output):
    assert not bare_romanisation(source, output)


class FakeTranslator:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def translate_page(self, texts, context=(), notes="", upcoming=(), meta=None, **kwargs):
        self.calls.append({"texts": list(texts), "context": list(context), "upcoming": list(upcoming), "meta": meta,
                           "notes": notes, **kwargs})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return [answer]


def test_a_romanised_line_is_asked_again_with_its_neighbours_on_its_page():
    tr = FakeTranslator(["What?"])
    texts = ["来たぞ", "なに?", "見ろ", "次のページ"]
    meta = [{"page": 0}, {"page": 0, "speaker": "Aki"}, {"page": 0}, {"page": 1}]
    cancel = threading.Event()
    out, asked, left = ask_again_romanised(tr, texts, ["Here it comes", "Nani?", "Look", "Next page"],
                                           context=[("前", "Before")], notes="premises", upcoming=["後"], meta=meta,
                                           call_args={"cancel": cancel}, cancel=cancel)
    assert out == ["Here it comes", "What?", "Look", "Next page"] and (asked, left) == (1, 0)
    call, = tr.calls
    assert call["texts"] == ["なに?"] and call["notes"] == "premises" and call["cancel"] is cancel
    assert call["context"] == [("前", "Before"), ("来たぞ", "Here it comes")]
    assert call["upcoming"] == ["見ろ"]  # the next page's line, and what comes after it, left out
    assert call["meta"] == [{"page": 0, "speaker": "Aki"}]


def test_the_first_answer_stays_when_the_second_is_romaji_again_or_fails():
    texts, first = ["なに?", "はい"], ["Nani?", "Hai"]
    out, asked, left = ask_again_romanised(FakeTranslator(["Nani!?", TranslationError("ollama.bad_answer")]),
                                           texts, first)
    assert out == first and (asked, left) == (2, 2)
    out, asked, left = ask_again_romanised(FakeTranslator([]), ["来た"], ["It came"])
    assert out == ["It came"] and (asked, left) == (0, 0)  # nothing to ask


def test_asking_again_stops_when_cancelled():
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        ask_again_romanised(FakeTranslator(["What?"]), ["なに?"], ["Nani?"], cancel=cancel)
