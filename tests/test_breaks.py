"""Line breaks by language (`render.breaks`): Thai breaks between its words only (Windows' break iterator where it is
there, a rule of clusters and syllables everywhere), its spaces kept; each target language's words take a hyphen only
where its patterns or rules allow (German, French, Spanish, Italian, Portuguese, Polish and Dutch by the bundled
patterns, Russian and Ukrainian by their vowels, Turkish and Indonesian by their syllables, Vietnamese never); English
exactly as before; the words a line should not end on, per language; and the pattern files under a permissive licence.
The samples are ordinary words and sentences written for these tests."""
from __future__ import annotations

import re
import unicodedata

import numpy as np
import pytest

from taslation.render import breaks, find_font, load_font, typeset, wrap_lines
from taslation.render.typeset import _cut, hyphen_points, layout_text

# ------------------------------------------------------------------ hyphenation per language
# a "-" at every point the language's rules allow (several ways where they allow several)
GOLD = {
    "German": ["Ge-schwin-dig-keits-be-gren-zung", "Ver-ant-wor-tung", "Ent-schul-di-gung", "Bi-b-li-o-thek",
               "Zu-sam-men-ar-beit", "Fahr-kar-ten-schal-ter", "un-glaub-lich", "Was-ser-fla-sche"],
    "French": ["mal-heu-reu-se-ment", "in-com-pré-hen-si-ble", "dé-ve-lop-pe-ment", "gou-ver-ne-ment",
               "bi-blio-thèque", "per-son-nel-le-ment"],
    "Spanish": ["res-pon-sa-bi-li-dad", "com-ple-ta-men-te", "de-s-a-for-tu-na-da-men-te", "cons-truc-ción",
                "ver-da-de-ra-men-te"],
    "Italian": ["as-so-lu-ta-men-te", "re-spon-sa-bi-li-tà", "sfor-tu-na-ta-men-te", "in-cre-di-bi-le"],
    "Portuguese (Brazil)": ["res-pon-sa-bi-li-da-de", "In-fe-liz-men-te", "i-na-cre-di-tá-vel", "bi-bli-o-te-ca"],
    "Polish": ["od-po-wie-dzial-ność", "nie-praw-do-po-dob-ne", "prze-pra-szam", "zde-cy-do-wa-nie"],
    "Dutch": ["ver-ant-woor-de-lijk-heid", "ver-schrik-ke-lijk", "waar-schijn-lijk", "zie-ken-huis"],
    "Russian": ["пред-ста-в-ле-ние", "от-вет-ствен-ность", "за-ме-ча-тель-ным", "ру-ко-во-ди-те-ле",
                "по-жа-луй-ста", "здра-в-ствуй-те"],
    "Ukrainian": ["від-по-ві-даль-ність", "біб-лі-о-те-ка", "ней-мо-вір-но"],
    "Turkish": ["kü-tüp-ha-ne", "ar-ka-daş-la-rım", "So-rum-lu-luk", "o-la-ğa-nüs-tü", "ki-tap-lık"],
    "Indonesian": ["ber-tang-gung", "per-pus-ta-ka-an", "pe-nge-ta-hu-an", "ma-sya-ra-kat", "Se-be-nar-nya"],
}


def _gold(marked: str) -> tuple[str, set[int]]:
    parts = marked.split("-")
    points, at = set(), 0
    for part in parts[:-1]:
        at += len(part)
        points.add(at)
    return "".join(parts), points


@pytest.mark.parametrize("language", GOLD)
def test_each_language_hyphenates_only_where_its_rules_allow(language):
    found_any = 0
    for marked in GOLD[language]:
        word, allowed = _gold(marked)
        points = hyphen_points(word, language)
        assert set(points) <= allowed, (language, word, points)
        assert all(typeset.HYPHEN_HEAD <= p <= len(word) - typeset.HYPHEN_EDGE for p in points), (word, points)
        found_any += bool(points)
    assert found_any == len(GOLD[language])  # every long word has somewhere to break


def test_some_points_exactly():
    assert hyphen_points("Geschwindigkeitsbegrenzung", "German") == [2, 8, 11, 16, 18, 22]
    assert hyphen_points("verantwoordelijkheid", "Dutch") == [3, 6, 10, 12, 16]
    assert hyphen_points("odpowiedzialność", "Polish") == [2, 4, 7, 12]
    assert hyphen_points("представление", "Russian") == [4, 8, 10]
    assert hyphen_points("kitaplık", "Turkish") == [2, 5] and hyphen_points("İstanbullu", "Turkish") == [2, 5]
    assert hyphen_points("pengetahuan", "Indonesian") == [2, 5, 7]


def test_the_cyrillic_rule_keeps_signs_and_short_i_with_the_letter_before():
    assert breaks._cyrillic("только", 2, 2) == [4]  # толь-ко, never тол-ько
    assert breaks._cyrillic("война", 2, 2) == [3]  # вой-на
    assert breaks._cyrillic("объезд", 2, 2) == [3]  # объ-езд
    assert breaks._cyrillic("майор", 2, 2) == [3]  # май-ор, never ма-йор
    assert breaks._cyrillic("мама", 2, 2) == [2]  # ма-ма: a lone consonant goes with the vowel after it
    for word in ("представление", "безопасность", "ответственность", "здравствуйте", "сильный", "бульон"):
        for p in breaks._cyrillic(word, 2, 2):
            assert word[p] not in "ьъй", (word, p)
            assert any(c in breaks._CYR_VOWELS for c in word[:p]) and any(c in breaks._CYR_VOWELS for c in word[p:])


def test_vietnamese_never_and_capitals_never():
    assert hyphen_points("nghiêngnghiêng", "Vietnamese") == []
    assert hyphen_points("GESCHWINDIGKEIT", "German") == [] and hyphen_points("ПРЕДСТАВЛЕНИЕ", "Russian") == []
    assert hyphen_points("Kunst", "German") == []  # under eight letters


def test_english_and_no_language_keep_their_own_rule():
    for word in ("wonderful", "children", "extraordinarily", "impossible", "unbelievably", "backpacker", "laughter",
                 "Entschuldigung", "complètement", "responsibilities", "congratulations"):
        assert hyphen_points(word, "English") == hyphen_points(word) == hyphen_points(word, ""), word
    assert hyphen_points("wonderful", "English") == [3, 6]
    # a Latin word in a Cyrillic language keeps the English-like rule; a Cyrillic word gets the vowel rule anywhere
    assert hyphen_points("wonderful", "Russian") == [3, 6]
    assert hyphen_points("представление") == hyphen_points("представление", "Russian") == [4, 8, 10]


def test_language_names_and_codes():
    assert breaks.language_key("Portuguese (Brazil)") == "portuguese" == breaks.language_key("pt")
    assert breaks.language_key("Deutsch") == "german" and breaks.language_key("") == ""
    assert hyphen_points("Geschwindigkeitsbegrenzung", "de") == hyphen_points("Geschwindigkeitsbegrenzung", "German")


def test_the_bundled_patterns_are_permissively_licensed_and_read():
    for language, (name, _left, _right) in breaks.PATTERNS.items():
        path = breaks.HERE / name
        header = path.read_text(encoding="utf-8").split("\\patterns", 1)[0]
        block = []  # the file's "licence:" entry: its lines indented under it
        for line in header.split("% licence:", 1)[1].splitlines()[1:]:
            if not line.startswith("%  "):
                break
            block.append(line)
        names = [m.group(1).strip() for line in block if (m := re.search(r"name:\s*(.+)", line))]
        assert any(re.match(r"(MIT|BSD)", n) for n in names), (name, names)
        assert not any("GPL" in n for n in names), (name, names)
        table, longest, _exceptions = breaks._patterns(language)
        assert len(table) > 100 and longest >= 5, name


def test_hyphenation_reaches_the_rescue_and_the_rectangle():
    spec = find_font()
    if not spec.path:
        pytest.skip("no font file on this computer")
    font = load_font(spec.path, 16)
    text = "Geschwindigkeitsbegrenzung"
    lines = wrap_lines(text, font, int(font.getlength("Geschwindig-")), "lgc", hyphenate=1, language="German")
    assert len(lines) >= 2 and lines[0].endswith("-")
    cuts, at = set(), 0
    for line in lines[:-1]:
        at += len(line) - 1
        cuts.add(at)
    assert cuts <= _gold("Ge-schwin-dig-keits-be-gren-zung")[1]
    # set in a bubble too small for it: the hyphens fall where German allows them
    yy, xx = np.mgrid[0:120, 0:60]
    mask = ((((xx - 29.5) / 30) ** 2 + ((yy - 59.5) / 60) ** 2) <= 1.0).astype(np.uint8) * 255
    fit = layout_text(mask, f"Die {text} gilt.", spec.path, language="German")
    texts = [t for t, _x, _y in fit.lines if t]
    at = hyphens = 0  # the letters of the long word set on the lines before
    for line in texts:
        if not line.endswith("-"):
            at = 0
            continue
        piece = line.split()[-1][:-1]
        at = at + len(piece) if at else len(piece)
        assert text[:at].endswith(piece) and at in _gold("Ge-schwin-dig-keits-be-gren-zung")[1], texts
        hyphens += 1
    assert hyphens, texts  # the word does not fit whole: it was hyphenated


# ------------------------------------------------------------------ words a line should not end on
def test_weak_words_per_language():
    pieces = _cut([["Ich", "sehe", "den", "Hund", "und", "die", "Katze"]], "lgc", "German", 0, lambda t: False)
    assert pieces.cost[3] > pieces.cost[2]  # after "den" dearer than after "sehe"
    assert pieces.cost[5] > pieces.cost[2]  # after "und"
    pieces = _cut([["Idę", "w", "stronę", "domu"]], "lgc", "Polish", 0, lambda t: False)
    assert pieces.cost[2] > pieces.cost[1]  # never "w" at a line's end
    pieces = _cut([["Я", "иду", "в", "школу"]], "lgc", "Russian", 0, lambda t: False)
    assert pieces.cost[3] > pieces.cost[2]
    english = _cut([["I", "saw", "the", "dog"]], "lgc", "English", 0, lambda t: False)
    assert english.cost[3] == pytest.approx(typeset.COST_CLAUSE + typeset.COST_WEAK)
    assert all(word == word.lower() for words in breaks.WEAK_WORDS.values() for word in words)


# ------------------------------------------------------------------ Thai
# written for these tests: "|" between two words, "·" inside a compound where a break still reads
THAI = ["ฉัน|ไม่|รู้|ว่า|เธอ|หมาย·ถึง|อะไร แต่|ฉัน|จะ|ลอง|ดู|อีก|ครั้ง",
        "เรา|ต้อง|รีบ|ไป|ที่|สถานี|ก่อน|รถ·ไฟ|ขบวน|สุด·ท้าย|จะ|ออก",
        "วัน·นี้|อากาศ|ดี|มาก ไป|เดิน·เล่น|กัน|ไหม",
        "ฉัน|ไม่|อยาก|เชื่อ|เลย|ว่า|เธอ|กิน|เค้ก|หมด|คน|เดียว",
        "ขอบ·คุณ|มาก|ที่|ช่วย|ฉัน|ไว้ ฉัน|จะ|ไม่|ลืม|เลย",
        "สะพาน|เก่า|จะ|ปิด|ถาวร|จริง|หรือ"]


def _thai(marked: str) -> tuple[str, set[int]]:
    """The sentence and where a line may break in it (offsets into the sentence, spaces as they are)."""
    out, ok = [], set()
    for ch in marked:
        if ch in "|·":
            ok.add(len(out))
            continue
        out.append(ch)
        if ch == " ":
            ok.add(len(out))
    return "".join(out), ok


@pytest.fixture
def fallback(monkeypatch):
    monkeypatch.setattr(breaks, "USE_NATIVE", False)
    typeset._LAYOUTS.clear()
    yield
    typeset._LAYOUTS.clear()


def _thai_font(size: int = 20):
    spec = find_font("", None, "สวัสดี")
    if not spec.path:
        pytest.skip("no Thai font on this computer")
    return spec, load_font(spec.path, size, spec.bold_variation)


def test_the_cluster_rule_never_breaks_inside_a_cluster():
    for marked in THAI:
        text, _ok = _thai(marked)
        for p in breaks.cluster_cuts(text):
            assert unicodedata.category(text[p]) != "Mn", (text, p)  # a vowel sign or tone mark
            assert text[p] not in "ะาำๅฯๆ", (text, p)  # a vowel written after its consonant
            assert text[p - 1] not in "เแโใไ", (text, p)  # a vowel written before it
            assert text[p] != " ", (text, p)  # (a space stays with what is before it)
    assert breaks.cluster_cuts("เป็น") == [] and breaks.cluster_cuts("กัน") == []  # the final after ็ and ั


def test_the_fallback_offers_fewer_places_inside_words(fallback):
    inside = total = 0
    for marked in THAI:
        text, ok = _thai(marked)
        cuts = set(breaks.thai_cuts(text))
        assert cuts <= set(breaks.cluster_cuts(text))
        inside += len(cuts - ok)
        total += len({p for p in range(1, len(text)) if unicodedata.category(text[p]) != "Mn"} - ok)
    assert inside < total / 4  # far fewer than between any two characters


def test_without_the_library_the_rule_is_used(monkeypatch):
    monkeypatch.setattr(breaks, "_ICU", False)  # as on a computer without it
    breaks._cuts.cache_clear()
    try:
        assert not breaks.native_available()
        text, _ok = _thai(THAI[0])
        assert breaks.thai_cuts(text) == tuple(breaks._syllable_cuts(text))
        assert "".join(breaks.thai_words(text)) == text
    finally:
        breaks._cuts.cache_clear()


def test_thai_words_keep_their_spaces(fallback):
    words = breaks.thai_words("  ฉันไม่รู้   แต่จะลอง  ")
    assert "".join(words) == "ฉันไม่รู้ แต่จะลอง"
    assert sum(w.startswith(" ") for w in words) == 1 and not words[0].startswith(" ")


@pytest.mark.skipif(not breaks.native_available(), reason="no break iterator of Windows' own here")
def test_windows_break_iterator_breaks_only_between_words():
    for marked in THAI:
        text, ok = _thai(marked)
        cuts = set(breaks.thai_cuts(text))
        assert cuts <= ok, (text, sorted(cuts - ok))
        assert len(cuts) >= len(ok) // 2


def _line_cuts(lines: list[str]) -> set[int]:
    """Where *lines* (of a Thai text) break, counted in letters with the spaces left out."""
    cuts, at = set(), 0
    for line in lines[:-1]:
        at += len(line.replace(" ", ""))
        cuts.add(at)
    return cuts


def _bare(text: str, ok: set[int]) -> set[int]:
    """*ok* (offsets into *text*) counted in letters with the spaces left out."""
    return {p - text[:p].count(" ") for p in ok}


@pytest.mark.skipif(not breaks.native_available(), reason="no break iterator of Windows' own here")
def test_thai_lines_break_between_words_in_a_bubble_and_a_rectangle():
    spec, font = _thai_font(18)
    for marked in THAI:
        text, ok = _thai(marked)
        good = _bare(text, ok)
        for width in (60, 90, 140):
            lines = wrap_lines(text, font, width, "thai")
            assert "".join(lines).replace(" ", "") == text.replace(" ", "")
            assert _line_cuts(lines) <= good, lines
        yy, xx = np.mgrid[0:150, 0:110]
        mask = ((((xx - 54.5) / 55) ** 2 + ((yy - 74.5) / 75) ** 2) <= 1.0).astype(np.uint8) * 255
        fit = layout_text(mask, text, spec.path, script="thai", language="Thai")
        lines = [t for t, _x, _y in fit.lines if t]
        if fit.clean:
            assert _line_cuts(lines) <= good, lines
        assert not any(line.startswith(" ") or line.endswith(" ") for line in lines)


def test_thai_lines_without_the_dictionary_never_break_inside_a_cluster(fallback):
    spec, font = _thai_font(18)
    for marked in THAI:
        text, _ok = _thai(marked)
        for width in (50, 80, 130):
            for line in wrap_lines(text, font, width, "thai"):
                assert unicodedata.category(line[0]) != "Mn" and line[0] not in "ะาำๅฯๆ", line
                assert line[-1] not in "เแโใไ", line


def test_a_thai_space_inside_a_line_stays():
    _spec, font = _thai_font(18)
    assert wrap_lines("ฉันไม่รู้ แต่จะลอง", font, 2000, "thai") == ["ฉันไม่รู้ แต่จะลอง"]
