"""English hyphenation (`render.breaks`, `typeset.hyphen_points`, `typeset._split_word`): Liang's algorithm with the
bundled American English patterns and their list of exceptions, never nearer a word's edge than two letters before a
hyphen and three after it; a word in capitals, with an apostrophe, with a hyphen of its own or with letters outside
ASCII; every name the English target may have reaching the patterns; the rescue hyphenating at those points and the
last resort splitting a word there (for-ward, never forw-ard) where one fits, the other languages' splits as before.
The samples are ordinary English words and sentences written for these tests."""
from __future__ import annotations

import numpy as np
import pytest

from taslation.render import breaks, find_font, load_font, typeset, wrap_lines
from taslation.render.typeset import _cut, _split_points, _split_word, hyphen_points, layout_text


def _marked(word: str, points) -> str:
    out, prev = "", 0
    for p in points:
        out += word[prev:p] + "-"
        prev = p
    return out + word[prev:]


def _points(marked: str) -> tuple[str, set[int]]:
    parts = marked.split("-")
    points, at = set(), 0
    for part in parts[:-1]:
        at += len(part)
        points.add(at)
    return "".join(parts), points


def _english(word: str) -> str:
    return _marked(word, breaks.hyphen_points(word, "english", typeset.HYPHEN_HEAD, typeset.HYPHEN_EDGE))


# where the patterns break, exactly (two letters before a hyphen at least, three after)
EXACT = ["for-ward", "mem-bers", "work-ing", "hy-phen-ation", "re-mem-ber", "some-thing", "every-thing", "won-der-ful",
         "chil-dren", "ex-tra-or-di-nary", "im-pos-si-ble", "un-be-liev-ably", "un-der-stand", "beau-ti-ful",
         "dif-fer-ent", "Every-body", "yes-ter-day", "com-puter", "to-mor-row", "busi-ness", "what-ever", "an-other",
         "how-ever", "them-selves", "noth-ing", "ques-tion", "prob-a-bly", "dan-ger-ous", "at-ten-tion", "lis-ten",
         "se-ri-ously", "re-turn", "be-come", "be-tween", "nec-es-sary", "ex-pe-ri-ence", "in-for-ma-tion",
         "com-mu-ni-ca-tion", "knowl-edge", "laugh-ter", "back-packer", "ul-ti-mately",
         "strength", "through", "straight", "rhythm"]  # (none of these four takes a hyphen)
# the file's list of exceptions (Knuth's): only where it says, and a word listed whole never
EXCEPTIONS = ["as-so-ciate", "as-so-ciates", "dec-li-na-tion", "oblig-a-tory", "phil-an-thropic", "present",
              "presents", "project", "projects", "reci-procity", "re-cog-ni-zance", "ref-or-ma-tion", "ret-ri-bu-tion",
              "ta-ble"]
# a dictionary's syllables (American spelling): every point the patterns find is one of them
DICTIONARY = ["for-ward", "mem-bers", "hy-phen-ation", "ev-ery-thing", "ev-ery-body", "com-put-er", "what-ev-er",
              "an-oth-er", "how-ev-er", "nec-es-sary", "ul-ti-mate-ly", "back-pack-er", "se-ri-ous-ly",
              "un-be-liev-ably", "won-der-ful", "chil-dren", "im-pos-si-ble", "to-mor-row", "in-for-ma-tion",
              "com-mu-ni-ca-tion", "knowl-edge", "ex-pe-ri-ence", "dan-ger-ous", "at-ten-tion", "ques-tion"]


@pytest.mark.parametrize("marked", EXACT + EXCEPTIONS)
def test_english_words_break_where_english_breaks_them(marked):
    word, _points_ = _points(marked)
    assert _english(word) == marked


def test_the_exceptions_are_read_from_the_file():
    _table, _longest, exceptions = breaks._patterns("english")
    assert set(exceptions) == {_points(m)[0].lower() for m in EXCEPTIONS}
    assert exceptions["present"] == () and exceptions["table"] == (2,)


@pytest.mark.parametrize("marked", DICTIONARY)
def test_every_point_found_is_a_syllable_the_dictionary_has(marked):
    word, allowed = _points(marked)
    found = breaks.hyphen_points(word, "english", 2, 3)
    assert found and set(found) <= allowed, (word, found)


def test_never_nearer_the_edge_than_the_minimums():
    words = [_points(m)[0] for m in EXACT + EXCEPTIONS + DICTIONARY] + [
        "about", "even", "only", "music", "baby", "ready", "away", "open", "very", "electric", "abbreviated",
        "obviously", "evening", "really", "family", "idea", "area", "radio", "video", "heavy", "money"]
    for word in words:
        n = len(word)
        for head, edge in ((1, 1), (2, 2), (2, 3)):  # the file's own two and three hold even when less is asked
            points = breaks.hyphen_points(word, "english", head, edge)
            assert all(2 <= p <= n - 3 for p in points), (word, head, edge, points)
        stricter = breaks.hyphen_points(word, "english", 3, 4)  # a stricter minimum asked holds too
        assert all(3 <= p <= n - 4 for p in stricter), (word, stricter)
        assert set(stricter) <= set(breaks.hyphen_points(word, "english", 2, 3))
    assert breaks.PATTERNS["english"][1:] == (2, 3)  # as the file's header asks
    assert (typeset.HYPHEN_HEAD, typeset.HYPHEN_EDGE) == (2, 3)  # the typesetter's own: the same
    assert breaks.hyphen_points("hyphenation", "english", 3, 4) == (6,)  # hyphen-ation, never hy-phenation


def test_capitals():
    assert hyphen_points("Everybody", "English") == [5]  # a capital at the start: the patterns read it in lower case
    assert breaks.hyphen_points("EVERYBODY", "english", 2, 3) == (5,)
    assert hyphen_points("EVERYBODY", "English") == []  # in capitals only, the rescue leaves it whole as before
    assert breaks.hyphen_points("PROJECT", "english", 2, 3) == ()  # an exception in capitals is still one


def test_apostrophes_and_a_word_with_its_own_hyphen():
    for word in ("everybody's", "everybody’s", "shouldn't", "self-confidence", "well-known"):
        assert hyphen_points(word, "English") == [], word  # the rescue never hyphenates them, as before
        assert breaks.hyphen_points(word, "english", 2, 3) is None, word  # not all letters
    # the rescue's pieces: a word of its own hyphen breaks after it only
    pieces = _cut([["self-confidence", "matters"]], "lgc", "English", 2, lambda t: False)
    assert pieces.text[:2] == ["self-", "confidence"] and pieces.glue[1] == 3
    # the last resort: at the points of each run of letters, and after the word's own hyphen
    for word, want in (("everybody's", [5]), ("everybody’s", [5]), ("self-confidence", [5, 8, 10]),
                       ("well-known", [5]), ("*members*", [4]), ("“forward,”", [4])):
        letters = [i for i, ch in enumerate(word) if ch.isalpha()]
        cuts = [i for i in letters[3: len(letters) - 2] if word[i - 1].isalpha() or word[i - 1] == "-"]
        assert _split_points(word, cuts, "English") == want, word
        assert _split_points(word, cuts, "") == [] == _split_points(word, cuts, "German"), word


def test_letters_outside_ascii():
    # the patterns know only a to z: they find no point next to another letter, and the word is still theirs
    assert breaks.hyphen_points("coöperation", "english", 2, 3) == (6, 7)  # coöper-a-tion
    assert breaks.hyphen_points("résumés", "english", 2, 3) == (2,)
    for word in ("naïveté", "jalapeños", "façades", "Brontë"):
        assert breaks.hyphen_points(word, "english", 2, 3) == (), word
    assert hyphen_points("представление", "English") == [4, 8, 10]  # a Cyrillic word keeps the vowel rule


def test_every_name_of_the_english_target_reaches_the_patterns():
    from taslation.ui.constants import LANGUAGES

    assert breaks.language_key(LANGUAGES[0]) == "english" and LANGUAGES[0] == "English"
    for name in ("English", "english", " English ", "ENGLISH", "en", "EN", "en-US", "en_us", "en-GB", "en_GB",
                 "English (US)", "English (UK)", "American English", "British English"):
        assert breaks.language_key(name) == "english", name
        assert hyphen_points("hyphenation", name) == [2, 6], name
    assert hyphen_points("hyphenation") == [2, 5, 7] == hyphen_points("hyphenation", "Japanese")  # the own rule
    for name in LANGUAGES:  # every target the window offers: patterns, a rule, or the own rule
        assert breaks.language_key(name) in {*breaks.PATTERNS, *breaks.NO_HYPHENS, "russian", "ukrainian", "turkish",
                                             "indonesian", "thai", "chinese", "korean", "arabic", "hebrew", "hindi",
                                             "bengali"}, name


# ------------------------------------------------------------------ the typesetter
def _font(size: int = 12):
    spec = find_font()
    if not spec.path:
        pytest.skip("no font file on this computer")
    return spec, load_font(spec.path, size)


def test_the_last_resort_splits_an_english_word_at_a_point():
    """A word that fits nowhere is split where English breaks it, where a point's first part fits (for-ward, where
    forw- also fits); in no language, and in German, as before: as many letters as fit."""
    _spec, font = _font()
    for word, head, old in (("forward", "for-", "forw-"), ("members", "mem-", "memb-"), ("return", "re-", "ret-"),
                            ("EVERYBODY", "EVERY-", "EVERYB-"), ("everybody's", "every-", "everybo-")):
        width = int(font.getlength(old))
        assert font.getlength(word) > width
        assert _split_word(word, font, width, "lgc", "English") == (head, word[len(head) - 1:]), word
        assert _split_word(word, font, width, "lgc", "") == (old, word[len(old) - 1:]), word
        lines = wrap_lines(f"Go {word}", font, width, "lgc", language="English")
        assert lines[1] == head, lines
    # no point fits (knowl-edge): as many letters as do, as before
    width = int(font.getlength("know-"))
    assert font.getlength("knowl-") > width
    assert _split_word("knowledge", font, width, "lgc", "English") == ("know-", "ledge")
    assert _split_word("knowledge", font, width, "lgc", "English") == _split_word("knowledge", font, width, "lgc")
    # nothing fits at all: the shortest first part, a point where it is the shorter (An-other, never Ano-ther)
    assert _split_word("Another", font, 1, "lgc", "English") == ("An-", "other")
    assert _split_word("Another", font, 1, "lgc", "") == ("Ano-", "ther")
    assert _split_word("knowledge", font, 1, "lgc", "English") == ("kno-", "wledge")  # (knowl- is longer)
    # a word too short to split stays whole; an exception listed whole is split only as before
    assert _split_word("table", font, 5, "lgc", "English") is None
    width = int(font.getlength("proj-"))
    assert _split_word("project", font, width, "lgc", "English") == ("proj-", "ect")
    # the other languages split as before
    for word, language in (("Kunstwerk", "German"), ("biblioteca", "Spanish"), ("malheureux", "French")):
        for width in (20, 30, 40, 50):
            assert _split_word(word, font, width, "lgc", language) == _split_word(word, font, width, "lgc"), word


def _ellipse(w: int, h: int) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    inside = ((xx + 0.5 - w / 2) / (w / 2)) ** 2 + ((yy + 0.5 - h / 2) / (h / 2)) ** 2 <= 1.0
    return (inside * 255).astype(np.uint8)


def _splits(lines: list[str]) -> list[tuple[str, int]]:
    """Each break inside a word split over lines with a hyphen at a line's end (the texts here have no hyphen of
    their own): (the word's letters, where in them the line broke)."""
    out: list[tuple[str, int]] = []
    carry, at = "", []
    for line in lines:
        pieces = line.split()
        for k, piece in enumerate(pieces):
            if k == len(pieces) - 1 and piece.endswith("-") and len(piece) > 1:
                carry += piece[:-1]
                at.append(len(carry))
                continue
            if carry:
                word = carry + piece
                lead = len(word) - len(word.lstrip("“\"*"))
                out.extend(("".join(ch for ch in word if ch.isalpha()), a - lead) for a in at)
            carry, at = "", []
    return out


# invented lines in bubbles too small for them: (the text, the ellipse's width and height); the earlier rule broke
# several of them elsewhere (hyphe-nation, irres-ponsible, Congra-tulations, Abso-lutely, Ano-ther, Rem-ember)
CRAMPED = [("The communication was extraordinary.", (60, 150)), ("Go forward, members!", (34, 160)),
           ("Unbelievably, everybody remembered.", (52, 170)), ("Nothing happened yesterday.", (40, 150)),
           ("The hyphenation looks wonderful.", (50, 160)), ("Whatever happens, keep breathing.", (54, 170)),
           ("That's unbelievably irresponsible of you.", (66, 210)), ("Congratulations on your graduation!", (60, 190)),
           ("Absolutely, positively, definitely not.", (58, 190)), ("Another problem, captain!", (30, 170)),
           ("Remember, nothing happens.", (30, 170))]


def test_a_bubble_hyphenates_english_words_at_their_points():
    """In a bubble too small for its words the rescue (a long word) breaks English words only where the patterns do,
    and so does the last resort (a word that fits nowhere) where a point's first part fits: a break elsewhere comes
    only before the word's first point (no point's first part fit there: pro-blem where prob- is too wide); the
    words read back."""
    spec, _font12 = _font()
    seen = at_points = 0
    for text, size in CRAMPED:
        fit = layout_text(_ellipse(*size), text, spec.path, language="English")
        lines = [t for t, _x, _y in fit.lines if t]
        assert "".join(" ".join(lines).replace("- ", "").split()) == "".join(text.split()), lines
        for word, at in _splits(lines):
            points = breaks.hyphen_points(word, "english", 2, 3)
            assert at in points or not any(p < at for p in points), (word, at, points, lines)
            seen += 1
            at_points += at in points
    assert seen and at_points >= seen - 3, (seen, at_points)
