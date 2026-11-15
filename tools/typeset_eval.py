"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: a yardstick for the typesetter, on synthetic bubbles, numbers only.

The corpus is fixed and seeded (`SEED`): invented lines (`TEXTS`: English of 1 to 40 words - short exclamations, long
words, invented names, punctuation, *stressed* words -, a few in German, Spanish and French for their long words,
two in Japanese, wrapped by character, and one in Arabic, set right to left), each in `SHAPES_PER_TEXT` bubbles drawn
here: ellipses of several aspect ratios, round-cornered boxes, clouds, ellipses with a tail, two bubbles joined at a
neck, and narrow tall bubbles as vertical Japanese leaves them. A bubble is sized for its text, so that most land
between 13 and 26 px and some are cramped. Each case is set by the real typesetter (`typeset.letter_text`, as
`Pipeline._set_text` calls it, with the app's lettering font) on a white image, and measured:

* ``size/fit``: the size reached against the largest at which the text could fit at all (`oracle_size`: every word
  whole, each line anywhere in its rows, its ink band ``ORACLE_EM`` of the size (at least ``ORACLE_PX``) off the
  outline, any number of lines, any height); ``<0.9``: the share of cases under nine tenths of it.
* ``over``: cases with ink outside the bubble; ``tight``: cases whose ink comes nearer the outline than ``TIGHT_EM``
  of the size (at least ``TIGHT_PX``); ``margin``: the mean of the ink's nearest distance to the outline, in ems.
* ``rect``, ``cond``: the share of cases set in a rectangle rather than along the shape, and condensed at the limit.
* ``hyph``: words split with a hyphen (in all cases); ``lone1/lone/lone9``: of the cases on two lines or more in a
  spaced script with ``LONE_WORDS`` words or more, the share with a first, inner or last line of one word of at most
  ``LONE_LETTERS`` letters.
* ``weak``: English line ends (the last line left out) on an article, a preposition or a conjunction, per 100 line ends;
  ``pstart``: lines starting with punctuation that belongs to the line before.
* ``hourgl``, ``pyram``, ``prof``: of the cases in a round bubble (ellipse, cloud, tailed, joined, narrow) on three
  lines or more, the share with an inner line narrower than both its neighbours by 15 % or more, with a first or last
  line the widest, and the mean distance of the line widths (of the widest) from an oval's (`oval_profile`).
* ``offx/offy``: how far the ink box's centre is from the centroid of the bubble's body (the tail left out; for two
  joined bubbles, the lobe that holds most of the ink), in % of the body's width and height (mean of the absolute);
  ``off>5``: the share of cases more than 5 % off either way.
* ``p90/p10`` and ``max/med``: on pages of `PAGE_SIZE` English speech cases, lettered as `Pipeline.cap_sizes` and
  `_set_text` do (`typeset.page_caps`), the 90th over the 10th percentile of the sizes and the largest over the
  median (mean over the pages).
* ``ms``: the layout of one bubble without the cache (`typeset._layout_text`), best of `TIMING_RUNS`; ``ms95``: its 95th
  percentile.
* ``checks``: the share of cases each check of the lettering flags for review (`typeset.lettering_flags`), and of
  cases with any.

    python tools/typeset_eval.py                    # the corpus, aggregated (all, and per shape)
    python tools/typeset_eval.py --cases            # and one row per case
    python tools/typeset_eval.py --png DIR          # contact sheets of the cases as set, to look at
    python tools/typeset_eval.py --json FILE        # the numbers, for comparing two runs
    python tools/typeset_eval.py --openmantra       # the earlier yardstick on OpenMantra (`openmantra_eval`)
    python tools/typeset_eval.py --breaks           # line breaks by language (`break_eval`): hyphens, Thai words
    python tools/typeset_eval.py --breaks --thai-fallback   # the same with Thai by the rule, without Windows' ICU

The ``--openmantra`` series set the translations of the book caches ``~/.taslation/cache/OpenMantra_*`` (read only)
on the dataset's pages (``tools/openmantra.py``; CC BY-NC, never shipped): see `openmantra_eval`. Synthetic shapes and
invented lines only otherwise; no model, no GPU, no network; nothing is written but what ``--png`` / ``--json`` ask for.
"""

from __future__ import annotations

import argparse
import inspect
import json
import math
import sys
import time
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from taslation import netguard  # noqa: E402
from taslation.config import Settings  # noqa: E402
from taslation.regions import TextRegion  # noqa: E402
from taslation.render import find_font, make_lettering, script_of, typeset  # noqa: E402
from taslation.render.fonts import NO_SPACE_SCRIPTS  # noqa: E402

SEED = 20261115
SHAPES_PER_TEXT = 4
PAGE_SIZE = 6  # English speech cases per page, for the size spread
MIN_SIZE, MAX_SIZE, LINE_SPACING, READABLE = 9, 64, 1.12, 11  # the defaults of `Settings`
PAD = 3  # px of nothing round a bubble, so that its outline is everywhere in the image
ORACLE_EM, ORACLE_PX = 0.3, 3  # the margin the largest fitting size is measured with
TIGHT_EM, TIGHT_PX = 0.25, 2  # ink nearer the outline than this is too tight
LONE_LETTERS = 5
LONE_WORDS = 4  # a lone word is counted only in a text of so many words or more (in "Hey, / you!" it has no way out)
HOURGLASS = 0.85  # an inner line at most this much of the narrower of its neighbours
OFF_LIMIT = 0.05
TIMING_RUNS = 3
ROUND_SHAPES = ("ellipse", "cloud", "tailed", "joined", "narrow")
SHAPE_KINDS = ("ellipse", "rounded", "cloud", "tailed", "joined", "narrow")
# English words that should not end a line: articles, prepositions, conjunctions
WEAK_EN = frozenset("""a an the of to in on at by for with from into onto upon about over under after before
    between through during without within against toward towards across behind beyond near off out up per via
    and or but nor so yet as if than because although though while when where unless until whether since""".split())
CLOSING = set(",.;:!?…)]}»”’、。，．！？")

# Invented lines (no book's), by kind: (language, kind, text).
TEXTS: list[tuple[str, str, str]] = [
    ("en", "short", "Huh?"),
    ("en", "short", "What?!"),
    ("en", "short", "No way!"),
    ("en", "short", "Wait!"),
    ("en", "short", "Ow..."),
    ("en", "short", "Hey, you!"),
    ("en", "short", "Stop right there!"),
    ("en", "short", "Thank you."),
    ("en", "medium", "I told you not to touch that button."),
    ("en", "medium", "Where did everyone go all of a sudden?"),
    ("en", "medium", "If we leave now, we can still catch the last train."),
    ("en", "medium", "You call this a plan? It's a wish list."),
    ("en", "medium", "The rain won't stop until the festival is over."),
    ("en", "medium", "Don't look at me like that. I didn't do it."),
    ("en", "medium", "So this is the famous lighthouse of the northern cape."),
    ("en", "medium", "I can't believe you ate the whole cake by yourself."),
    ("en", "medium", "Is it true that the old bridge is closing for good?"),
    ("en", "medium", "Give me one good reason to trust you, just one."),
    ("en", "long", "When I was little, my grandmother used to tell me that the stars were holes in a curtain, and that "
                   "the light behind it was the morning of another world."),
    ("en", "long", "Listen carefully, because I am only going to say this once: the package goes to the third door on "
                   "the left, and nobody opens it before noon."),
    ("en", "long", "You have been late every single day this week, and the manager is starting to ask questions that "
                   "I really do not want to answer for you."),
    ("en", "long", "It's not that I don't want to help. It's that every time I help, something explodes, and then "
                   "everyone looks at me."),
    ("en", "long", "We searched the whole valley from the river to the pass and found nothing but footprints that "
                   "stopped in the middle of a field."),
    ("en", "long", "The train to the coast leaves at seven, but if the snow keeps falling like this, I doubt it will "
                   "leave at all tonight."),
    ("en", "long", "I know what you're thinking, and the answer is no. I'm not going back in there, not for money, not "
                   "for glory, and definitely not for you."),
    ("en", "long", "Every summer the whole town gathers by the harbour to watch the boats come in, and every summer my "
                   "brother swears he will win the race, and every summer he finishes last and laughs louder than "
                   "anyone else on the pier."),
    ("en", "longword", "That's absolutely unbelievable!"),
    ("en", "longword", "Incomprehensible!"),
    ("en", "longword", "Your responsibilities are extraordinarily complicated."),
    ("en", "longword", "Congratulations on your unprecedented achievement."),
    ("en", "longword", "The experimental transportation authorization was revoked."),
    ("en", "longword", "Unfortunately, the international representatives disagreed."),
    ("en", "names", "Captain Velasquez, the harbour master wants to see you."),
    ("en", "names", "Did Mirela Hartwell really say that about the Ostrander twins?"),
    ("en", "names", "Professor Ashworth and Doctor Kimura are waiting downstairs."),
    ("en", "names", "Tell Rikuto that Hanabishi is coming back tomorrow."),
    ("en", "punct", "Wait... what? You mean... the whole time?"),
    ("en", "punct", "I -- I didn't mean it like that!"),
    ("en", "punct", "\"Later,\" she said. \"Always later.\""),
    ("en", "punct", "Fine. Whatever. Go, then!"),
    ("en", "punct", "Well, well, well... look who finally showed up."),
    ("en", "punct", "No... no, no, no! Not again!"),
    ("en", "punct", "Wait ... what? You mean ... all of it ?"),
    ("en", "emph", "I *told* you it was a bad idea."),
    ("en", "emph", "This is *not* what I meant, and you *know* it."),
    ("en", "emph", "You *really* think so?"),
    ("en", "emph", "Whatever happens, *do not* open the door until I come back for you."),
    ("de", "longword", "Das ist eine Unverschämtheit!"),
    ("de", "longword", "Die Geschwindigkeitsbegrenzung gilt auch für dich."),
    ("de", "medium", "Ich habe keine Ahnung, wovon du eigentlich redest."),
    ("de", "longword", "Herzlichen Glückwunsch zur Beförderung!"),
    ("es", "longword", "¡Eso es completamente inaceptable!"),
    ("es", "longword", "Desafortunadamente, no tenemos más tiempo."),
    ("es", "medium", "¿De verdad crees que ella va a volver mañana?"),
    ("fr", "longword", "C'est absolument incompréhensible !"),
    ("fr", "medium", "Je ne sais pas ce que tu veux dire par là."),
    ("fr", "longword", "Malheureusement, la bibliothèque est fermée aujourd'hui."),
    ("ja", "medium", "今日はとても良い天気だね。散歩にでも行こうか。"),
    ("ja", "short", "そんなこと、一度も言ってないよ！"),
    ("ar", "medium", "لا أعرف ماذا تقصد بذلك."),
]
LANGUAGE_NAMES = {"en": "English", "de": "German", "es": "Spanish", "fr": "French", "ja": "Japanese", "ar": "Arabic",
                  "it": "Italian", "pt": "Portuguese (Brazil)", "pl": "Polish", "nl": "Dutch", "ru": "Russian",
                  "tr": "Turkish", "id": "Indonesian", "vi": "Vietnamese", "th": "Thai"}

# --- the line-break yardstick (``--breaks``) ---------------------------------------------------------------------
# Invented lines in the target languages, set in cramped bubbles so that their long words take hyphens and their
# lines break often. Thai is marked with its word boundaries as written for this tool: "|" between two words, "·"
# inside a compound where a break still reads (รถ·ไฟ), a space where the line has one; a line break anywhere else is
# a break inside a word.
BREAK_TEXTS: list[tuple[str, str]] = [
    ("de", "Ich habe keine Ahnung, wovon du eigentlich redest, aber die Verantwortung trägst du."),
    ("de", "Herzlichen Glückwunsch zur Beförderung, das ist wirklich unglaublich!"),
    ("de", "Entschuldigung, wo ist die Bibliothek? Ich suche die Fahrkartenschalter."),
    ("de", "Unsere Zusammenarbeit war eine Unverschämtheit, ehrlich gesagt."),
    ("de", "Die Geschwindigkeitsbegrenzung gilt auch für dich."),
    ("fr", "Malheureusement, la bibliothèque est fermée aujourd'hui."),
    ("fr", "C'est absolument incompréhensible, personnellement je ne comprends rien."),
    ("fr", "Le gouvernement annonce un développement extraordinaire, certainement."),
    ("fr", "Le professeur trouve cette situation complètement impossible."),
    ("es", "¡Eso es completamente inaceptable, verdaderamente!"),
    ("es", "Desafortunadamente, la responsabilidad es tuya y no mía."),
    ("es", "La construcción de la biblioteca es absolutamente increíble."),
    ("it", "È assolutamente incredibile, sfortunatamente non abbiamo tempo."),
    ("it", "La responsabilità della biblioteca è veramente straordinaria."),
    ("pt", "Infelizmente, a responsabilidade é completamente sua."),
    ("pt", "Isso é inacreditável, a biblioteca é extraordinária!"),
    ("pt", "Verdadeiramente impossível, absolutamente!"),
    ("pl", "To jest niesamowite, przepraszam za odpowiedzialność."),
    ("pl", "Zdecydowanie nieprawdopodobne, ale biblioteka jest niemożliwie daleko."),
    ("nl", "Dat is verschrikkelijk, het is onmogelijk om te wachten."),
    ("nl", "De verantwoordelijkheid van het ziekenhuis is waarschijnlijk belangrijk."),
    ("ru", "Это невероятно, ваше представление было замечательным."),
    ("ru", "Здравствуйте, пожалуйста, подумайте о безопасности."),
    ("ru", "Ответственность лежит на руководителе библиотеки."),
    ("tr", "Bu kütüphane gerçekten inanılmaz, arkadaşlarım da öyle düşünüyor."),
    ("tr", "Sorumluluk sende, olağanüstü bir durum değil."),
    ("id", "Kita harus bertanggung jawab atas perpustakaan ini."),
    ("id", "Sebenarnya pengetahuan masyarakat kita sangat luas."),
    ("vi", "Tôi không biết bạn đang nói về chuyện gì nữa, thật sự không biết."),
    ("th", "ฉัน|ไม่|รู้|ว่า|เธอ|หมาย·ถึง|อะไร แต่|ฉัน|จะ|ลอง|ดู|อีก|ครั้ง"),
    ("th", "เรา|ต้อง|รีบ|ไป|ที่|สถานี|ก่อน|รถ·ไฟ|ขบวน|สุด·ท้าย|จะ|ออก"),
    ("th", "อย่า|แตะ|ปุ่ม|นั้น|นะ มัน|อันตราย|มาก"),
    ("th", "วัน·นี้|อากาศ|ดี|มาก ไป|เดิน·เล่น|กัน|ไหม"),
    ("th", "ทุก·คน|หาย|ไป|ไหน|กัน|หมด"),
    ("th", "ถ้า|เรา|ออก|เดิน·ทาง|ตอน·นี้ เรา|ยัง|ทัน|รถ·ไฟ|เที่ยว|สุด·ท้าย"),
    ("th", "ฉัน|ไม่|อยาก|เชื่อ|เลย|ว่า|เธอ|กิน|เค้ก|หมด|คน|เดียว"),
    ("th", "ห้อง·สมุด|ปิด|แล้ว|ตั้ง·แต่|เมื่อ·วาน"),
    ("th", "ขอบ·คุณ|มาก|ที่|ช่วย|ฉัน|ไว้ ฉัน|จะ|ไม่|ลืม|เลย"),
    ("th", "สะพาน|เก่า|จะ|ปิด|ถาวร|จริง|หรือ"),
    ("th", "ประภาคาร|แห่ง|นี้|มี|ชื่อ·เสียง|มาก|ใน|หมู่|นัก·ท่อง·เที่ยว"),
    ("th", "เมื่อ|ฉัน|ยัง|เด็ก ยาย|เคย|เล่า|ให้|ฟัง|ว่า|ดวง·ดาว|คือ|รู|บน|ผ้า·ม่าน"),
    ("th", "ฝน|จะ|ไม่|หยุด|ตก|จน·กว่า|งาน|เทศกาล|จะ|จบ"),
    ("th", "อย่า|มอง|ฉัน|แบบ|นั้น ฉัน|ไม่·ได้|ทำ"),
]
# Every word of eight letters or more in BREAK_TEXTS, a "-" at every point where it may take a hyphen by its
# language's rules as written for this tool (several ways where the rules allow several: Bi-b-li-o-thek)
GOLD_HYPHENS: dict[str, list[str]] = {
    "de": ["ei-gent-lich", "Ver-ant-wor-tung", "Herz-li-chen", "Glück-wunsch", "Be-för-de-rung", "wirk-lich",
           "un-glaub-lich", "Ent-schul-di-gung", "Bi-b-li-o-thek", "Fahr-kar-ten-schal-ter", "Zu-sam-men-ar-beit",
           "Un-ver-schämt-heit", "Ge-schwin-dig-keits-be-gren-zung"],
    "fr": ["Mal-heu-reu-se-ment", "bi-blio-thèque", "ab-so-lu-ment", "in-com-pré-hen-si-ble",
           "per-son-nel-le-ment", "com-prends", "gou-ver-ne-ment", "dé-ve-lop-pe-ment", "ex-tra-or-di-naire",
           "cer-tai-ne-ment", "pro-fes-seur", "si-tua-tion", "com-plè-te-ment", "im-pos-si-ble"],
    "es": ["com-ple-ta-men-te", "i-n-a-cep-ta-ble", "ver-da-de-ra-men-te", "de-s-a-for-tu-na-da-men-te",
           "res-pon-sa-bi-li-dad", "cons-truc-ción", "bi-blio-te-ca", "ab-so-lu-ta-men-te", "in-cre-í-ble"],
    "it": ["as-so-lu-ta-men-te", "in-cre-di-bi-le", "sfor-tu-na-ta-men-te", "re-spon-sa-bi-li-tà", "bi-blio-te-ca",
           "ve-ra-men-te", "stra-or-di-na-ria"],
    "pt": ["In-fe-liz-men-te", "res-pon-sa-bi-li-da-de", "com-ple-ta-men-te", "i-na-cre-di-tá-vel",
           "bi-bli-o-te-ca", "ex-tra-or-di-ná-ri-a", "Ver-da-dei-ra-men-te", "im-pos-sí-vel", "ab-so-lu-ta-men-te"],
    "pl": ["nie-sa-mo-wi-te", "prze-pra-szam", "od-po-wie-dzial-ność", "Zde-cy-do-wa-nie",
           "nie-praw-do-po-dob-ne", "bi-b-lio-te-ka", "nie-moż-li-wie"],
    "nl": ["ver-schrik-ke-lijk", "on-mo-ge-lijk", "ver-ant-woor-de-lijk-heid", "zie-ken-huis", "waar-schijn-lijk",
           "be-lang-rijk"],
    "ru": ["не-ве-ро-я-т-но", "пред-ста-в-ле-ние", "за-ме-ча-тель-ным", "здра-в-ствуй-те", "по-жа-луй-ста",
           "по-ду-май-те", "без-опа-с-но-сти", "От-вет-ствен-ность", "ру-ко-во-ди-те-ле", "би-б-лио-те-ки"],
    "tr": ["kü-tüp-ha-ne", "ger-çek-ten", "i-na-nıl-maz", "ar-ka-daş-la-rım", "dü-şü-nü-yor", "So-rum-lu-luk",
           "o-la-ğa-nüs-tü"],
    "id": ["ber-tang-gung", "per-pus-ta-ka-an", "Se-be-nar-nya", "pe-nge-ta-hu-an", "ma-sya-ra-kat"],
    "vi": [],
}
BREAK_SHAPES = ("narrow", "ellipse", "rounded", "cloud")


# --- the shapes ---------------------------------------------------------------------------------------------------

@dataclass
class Shape:
    kind: str
    mask: np.ndarray  # uint8 0/255: the region's mask, as the typesetter gets it
    body: np.ndarray  # bool: the bubble without its tail
    lobes: list[np.ndarray]  # bool: what the text should be centred in (two for joined bubbles)

    @property
    def round(self) -> bool:
        return self.kind in ROUND_SHAPES


def _canvas(w: int, h: int) -> np.ndarray:
    return np.zeros((h + 2 * PAD, w + 2 * PAD), np.uint8)


def _ellipse(canvas: np.ndarray, cx: float, cy: float, rx: float, ry: float) -> np.ndarray:
    out = np.zeros_like(canvas)
    cv2.ellipse(out, (int(round(cx)), int(round(cy))), (max(1, int(round(rx))), max(1, int(round(ry)))), 0, 0, 360,
                255, -1)
    return out


def make_shape(kind: str, area: float, rng: np.random.Generator) -> Shape:
    """A bubble of *kind* whose body has about *area* px."""
    if kind == "ellipse":
        aspect = float(rng.choice([0.6, 0.8, 1.0, 1.3, 1.7, 2.2]))
    elif kind == "rounded":
        aspect = float(rng.choice([0.7, 1.0, 1.6, 2.5]))
    elif kind == "narrow":
        aspect = float(rng.choice([0.3, 0.38, 0.45]))
    else:
        aspect = float(rng.choice([0.8, 1.0, 1.3]))
    if kind == "rounded":
        h = math.sqrt(area / (0.95 * aspect))
        w = aspect * h
        c = _canvas(int(w), int(h))
        r = int(rng.uniform(0.15, 0.3) * min(w, h))
        x0, y0, x1, y1 = PAD, PAD, PAD + int(w) - 1, PAD + int(h) - 1
        cv2.rectangle(c, (x0 + r, y0), (x1 - r, y1), 255, -1)
        cv2.rectangle(c, (x0, y0 + r), (x1, y1 - r), 255, -1)
        for cx, cy in ((x0 + r, y0 + r), (x1 - r, y0 + r), (x0 + r, y1 - r), (x1 - r, y1 - r)):
            cv2.circle(c, (cx, cy), r, 255, -1)
        return Shape(kind, c, c > 0, [c > 0])
    if kind == "joined":
        lobe = area / 2.0
        h1 = math.sqrt(lobe / (math.pi / 4 * aspect))
        w1 = aspect * h1
        second = float(rng.uniform(0.7, 1.0))
        w2, h2 = w1 * math.sqrt(second), h1 * math.sqrt(second)
        way = int(rng.integers(3))  # side by side, one above the other, diagonal
        overlap = float(rng.uniform(0.12, 0.22))
        if way == 0:
            dx, dy = (w1 + w2) / 2 * (1 - overlap), float(rng.uniform(-0.15, 0.15)) * h1
        elif way == 1:
            dx, dy = float(rng.uniform(-0.15, 0.15)) * w1, (h1 + h2) / 2 * (1 - overlap)
        else:
            dx, dy = (w1 + w2) / 2 * (1 - overlap) * 0.75, (h1 + h2) / 2 * (1 - overlap) * 0.75
        xs = [-w1 / 2, w1 / 2, dx - w2 / 2, dx + w2 / 2]
        ys = [-h1 / 2, h1 / 2, dy - h2 / 2, dy + h2 / 2]
        c = _canvas(int(max(xs) - min(xs)) + 1, int(max(ys) - min(ys)) + 1)
        ox, oy = PAD - min(xs), PAD - min(ys)
        a = _ellipse(c, ox, oy, w1 / 2 - 0.5, h1 / 2 - 0.5)
        b = _ellipse(c, ox + dx, oy + dy, w2 / 2 - 0.5, h2 / 2 - 0.5)
        mask = np.maximum(a, b)
        return Shape(kind, mask, mask > 0, [a > 0, b > 0])
    fill = 0.82 if kind == "cloud" else math.pi / 4
    h = math.sqrt(area / (fill * aspect))
    w = aspect * h
    if kind == "cloud":
        c = _canvas(int(w), int(h))
        cx, cy = PAD + w / 2, PAD + h / 2
        bump = float(rng.uniform(0.16, 0.22)) * min(w, h)
        mask = _ellipse(c, cx, cy, w / 2 - bump, h / 2 - bump)
        n = int(rng.integers(9, 15))
        start = float(rng.uniform(0, 2 * math.pi))
        for i in range(n):
            t = start + 2 * math.pi * i / n + float(rng.uniform(-0.12, 0.12))
            r = bump * float(rng.uniform(0.85, 1.1))
            px, py = cx + (w / 2 - bump) * math.cos(t), cy + (h / 2 - bump) * math.sin(t)
            cv2.circle(mask, (int(round(px)), int(round(py))), max(1, int(round(r))), 255, -1)
        return Shape(kind, mask, mask > 0, [mask > 0])
    if kind == "tailed":
        angle = float(rng.choice([0.25, 0.75, 1.25, 1.75, 0.5, 1.5])) * math.pi + float(rng.uniform(-0.15, 0.15))
        reach = float(rng.uniform(0.3, 0.45))
        tx, ty = (w / 2) * (1 + reach) * math.cos(angle), (h / 2) * (1 + reach) * math.sin(angle)
        xs, ys = [-w / 2, w / 2, tx], [-h / 2, h / 2, ty]
        c = _canvas(int(max(xs) - min(xs)) + 1, int(max(ys) - min(ys)) + 1)
        ox, oy = PAD - min(xs), PAD - min(ys)
        body = _ellipse(c, ox, oy, w / 2 - 0.5, h / 2 - 0.5)
        spread = float(rng.uniform(0.18, 0.28))
        base = [(ox + 0.8 * (w / 2) * math.cos(angle + s), oy + 0.8 * (h / 2) * math.sin(angle + s))
                for s in (-spread, spread)]
        tail = np.zeros_like(c)
        cv2.fillPoly(tail, [np.round(np.array([base[0], (ox + tx, oy + ty), base[1]])).astype(np.int32)], 255)
        mask = np.maximum(body, tail)
        return Shape(kind, mask, body > 0, [body > 0])
    c = _canvas(int(w), int(h))  # an ellipse, or a narrow tall one
    mask = _ellipse(c, PAD + w / 2, PAD + h / 2, w / 2 - 0.5, h / 2 - 0.5)
    return Shape(kind, mask, mask > 0, [mask > 0])


# --- the corpus ---------------------------------------------------------------------------------------------------

@dataclass
class Case:
    n: int
    language: str
    kind: str
    text: str
    shape: Shape
    page: int = -1

    @property
    def script(self) -> str:
        return script_of(self.text, LANGUAGE_NAMES[self.language])


def _lettering(text: str, language: str) -> Any:
    s = Settings()
    spec = find_font(s.font_path, s.fonts_dir, text, LANGUAGE_NAMES[language])
    return make_lettering(spec, str(s.fonts_dir))


def corpus(seed: int = SEED) -> list[Case]:
    """The cases: each text in `SHAPES_PER_TEXT` bubbles, sized so that it would land at a size drawn between 13 and
    26 px (one in six between 9 and 12: cramped), the kinds of bubble dealt out in turn."""
    rng = np.random.default_rng(seed)
    cases: list[Case] = []
    turn = 0
    for language, kind, text in TEXTS:
        lettering = _lettering(text, language)
        unit = typeset.text_width(typeset.styled_font(lettering, 100), typeset.display_form(text, script_of(text)))
        for _ in range(SHAPES_PER_TEXT):
            shape_kind = SHAPE_KINDS[turn % len(SHAPE_KINDS)]
            turn += 1
            size = float(rng.uniform(9, 12)) if rng.random() < 1 / 6 else float(rng.uniform(13, 26))
            fill = float(rng.uniform(0.38, 0.5))  # how much of a bubble's body its lettering covers
            area = max(2500.0, unit / 100.0 * size * size * LINE_SPACING / fill)
            if shape_kind == "narrow":
                area = max(area, 5000.0)
            cases.append(Case(len(cases), language, kind, text, make_shape(shape_kind, area, rng)))
    speech = [c for c in cases if c.language == "en" and c.kind in ("medium", "long", "names", "punct", "emph")]
    for i, c in enumerate(speech[: len(speech) // PAGE_SIZE * PAGE_SIZE]):
        c.page = i // PAGE_SIZE
    return cases


# --- setting a case as the app does ---------------------------------------------------------------------------------

def _region(case: Case) -> TextRegion:
    h, w = case.shape.mask.shape
    return TextRegion(0, 0, w, h, case.shape.mask, (w // 4, h // 4, 3 * w // 4, 3 * h // 4))


def _layout_kwargs(case: Case) -> dict[str, Any]:
    """What `letter_text` passes to `layout_text` beyond the mask, the text and the lettering (the language only where
    the typesetter takes one)."""
    region = _region(case)
    tx0, ty0, tx1, ty1 = region.text_box
    kwargs: dict[str, Any] = {"min_size": MIN_SIZE, "line_spacing": LINE_SPACING, "bold_variation": False,
                              "script": case.script, "on_page": False, "anchor": (tx0, ty0, tx1, ty1)}
    if "language" in inspect.signature(typeset.layout_text).parameters:
        kwargs["language"] = LANGUAGE_NAMES[case.language]
    return kwargs


FLAGGED: dict[int, tuple[str, ...]] = {}  # per case: what the checks of its lettering said (`Lettered.flags`)


def set_case(case: Case, top: int = MAX_SIZE) -> tuple[Any, Image.Image]:
    """The `Fit` of *case* as `letter_text` sets it at most at *top*, and the image it draws (what the lettering's
    checks said goes to `FLAGGED`)."""
    lettering = _lettering(case.text, case.language)
    region = _region(case)
    image = Image.new("RGB", (region.width, region.height), "white")
    done = typeset.letter_text(image, region, case.text, lettering, MIN_SIZE, top, LINE_SPACING, False,
                               (255, 255, 255), False, LANGUAGE_NAMES[case.language])
    FLAGGED[case.n] = tuple(getattr(done, "flags", ()))
    fit = typeset.layout_text(case.shape.mask, case.text, lettering, max_size=top, **_layout_kwargs(case))
    return fit, image


def time_case(case: Case) -> float:
    """ms for the layout of *case* without the cache, best of `TIMING_RUNS`."""
    lettering = _lettering(case.text, case.language)
    kwargs = _layout_kwargs(case)
    best = float("inf")
    for _ in range(TIMING_RUNS):
        t0 = time.perf_counter()
        typeset._layout_text(case.shape.mask, case.text, lettering, max_size=MAX_SIZE, **kwargs)
        best = min(best, time.perf_counter() - t0)
    return 1000.0 * best


# --- the largest size that could fit ------------------------------------------------------------------------------

def _depth(mask: np.ndarray) -> np.ndarray:
    return cv2.distanceTransform((mask > 0).astype(np.uint8), cv2.DIST_L2, 5)


def _ink_band(lettering: Any, size: int) -> tuple[int, int]:
    """Where a line's ink lies below its top: from a capital's top to a descender's foot."""
    from taslation.render import load_font

    font = load_font(lettering.path, size, lettering.bold_variation)
    return int(font.getbbox("H")[1]), int(font.getbbox("gjpqy")[3])


def _tokens(text: str, script: str) -> list[str]:
    return list(text.replace(" ", "")) if script in NO_SPACE_SCRIPTS else text.split()


def oracle_size(case: Case) -> int:
    """The largest size at which *case*'s text fits its bubble with every word whole: lines `LINE_SPACING` apart, each
    line's ink band (`_ink_band`) wholly at least ``max(ORACLE_PX, ORACLE_EM * size)`` from the outline in the widest
    run of its rows, filled greedily (the most words a line takes; with fixed rooms nothing fits more), any top."""
    lettering = _lettering(case.text, case.language)
    script = case.script
    depth = _depth(case.shape.mask)
    glue = "" if script in NO_SPACE_SCRIPTS else " "
    tokens = _tokens(case.text, script)
    h = depth.shape[0]
    unit = typeset.text_width(typeset.styled_font(lettering, 100), typeset.display_form(case.text, script)) / 100.0
    usable = float((depth > ORACLE_PX).sum())
    start = int(min(MAX_SIZE, math.sqrt(usable / max(1e-6, 0.85 * unit * LINE_SPACING)) + 2))
    for size in range(start, MIN_SIZE - 1, -1):
        font = typeset.styled_font(lettering, size)
        ok = depth > max(ORACLE_PX, ORACLE_EM * size)
        lh = size * LINE_SPACING
        ink_top, ink_bottom = _ink_band(lettering, size)
        widths: dict[tuple[int, int], int] = {}
        rooms: dict[tuple[int, int], int] = {}

        def width(j: int, i: int) -> int:
            if (j, i) not in widths:
                widths[j, i] = typeset.text_width(font, typeset.display_form(glue.join(tokens[j:i]), script))
            return widths[j, i]

        def room(a: int, b: int) -> int:
            if (a, b) not in rooms:
                band = ok[max(0, a):min(h, b)].all(axis=0) if 0 <= a < b <= h else np.zeros(1, bool)
                padded = np.concatenate(([0], band.astype(np.int8), [0]))
                edges = np.flatnonzero(np.diff(padded))
                rooms[a, b] = int((edges[1::2] - edges[::2]).max()) if edges.size else 0
            return rooms[a, b]

        rows = np.flatnonzero(ok.any(axis=1))
        if rows.size == 0:
            continue
        step = max(1, int(lh / 6))
        for top in range(int(rows[0]) - ink_top, int(rows[-1]) + 1, step):
            j, line = 0, 0
            while j < len(tokens):
                a = int(round(top + line * lh)) + ink_top
                b = int(round(top + line * lh)) + ink_bottom
                r = room(a, b)
                i = j
                while i < len(tokens) and width(j, i + 1) <= r:
                    i += 1
                if i == j:
                    break
                j, line = i, line + 1
            if j == len(tokens):
                return size
    return MIN_SIZE


# --- the measures -------------------------------------------------------------------------------------------------

def oval_profile(n: int) -> list[float]:
    """The widths of an oval block of *n* lines, of its widest: for five lines about 62/87/100/87/62 %, shallower for
    fewer lines."""
    depth = 0.38 * min(1.0, (n - 1) / 4.0)
    return [1.0 - depth * abs((2 * k - (n - 1)) / max(1, n - 1)) ** 1.5 for k in range(n)]


def _letters(word: str) -> int:
    return sum(ch.isalpha() for ch in word)


def _hyphenated(lines: list[str], text: str) -> int:
    """Words the lines split with a hyphen of their own (a word's own hyphen does not count)."""
    words = set(text.split())
    count = 0
    for k, line in enumerate(lines[:-1]):
        if not line.endswith("-") or not line.split():
            continue
        head = line.split()[-1]
        tail = lines[k + 1].split()[0] if lines[k + 1].split() else ""
        if head not in words or head[:-1] + tail in words:
            count += 1
    return count


def measure(case: Case, fit: Any, image: Image.Image, oracle: int) -> dict[str, float]:
    script = case.script
    lines = [t for t, _x, _y in fit.lines if t]
    size = int(fit.size)
    mask = case.shape.mask > 0
    gray = np.asarray(image.convert("L"))
    ink = gray < 160
    depth = _depth(case.shape.mask)
    out: dict[str, float] = {"size": float(size), "fit": float(oracle), "ratio": size / max(1, oracle),
                             "lines": float(len(lines))}
    out["over"] = float((ink & ~mask).sum() > 0)
    out["rect"] = float(fit.method == "rect")
    out["cond"] = float(fit.condense < 1.0)
    near = float(depth[ink & mask].min()) if (ink & mask).any() else 0.0
    out["margin"] = near / max(1, size)
    out["tight"] = float(near < max(TIGHT_PX, TIGHT_EM * size))
    out["hyph"] = float(_hyphenated(lines, case.text)) if script == "lgc" else 0.0
    spaced = script not in NO_SPACE_SCRIPTS
    multi = len(lines) >= 2 and spaced and len(case.text.split()) >= LONE_WORDS
    lone = [len(t.split()) == 1 and _letters(t) <= LONE_LETTERS for t in lines]
    out["multi"] = float(multi)
    out["lone1"] = float(multi and lone[0])
    out["lone"] = float(multi and any(lone[1:-1]))
    out["lone9"] = float(multi and lone[-1])
    ends = [t.split()[-1] for t in lines[:-1] if t.split()]
    out["ends"] = float(len(ends)) if case.language == "en" else 0.0
    out["weak"] = float(sum(w.lower().strip("*\"'") in WEAK_EN for w in ends)) if case.language == "en" else 0.0
    out["pstart"] = float(sum(t[0] in CLOSING for t in lines[1:] if t))
    widths = [typeset.text_width(fit.font, typeset.display_form(t, script)) for t in lines]
    shaped = case.shape.round and len(lines) >= 3
    out["shaped"] = float(shaped)
    if shaped:
        widest = max(widths)
        out["hourgl"] = float(any(widths[k] < HOURGLASS * min(widths[k - 1], widths[k + 1])
                                  for k in range(1, len(widths) - 1)))
        out["pyram"] = float(max(widths[0], widths[-1]) >= widest and max(widths[1:-1]) < widest)
        out["prof"] = float(np.mean([abs(w / widest - p) for w, p in zip(widths, oval_profile(len(widths)))]))
    else:
        out["hourgl"] = out["pyram"] = out["prof"] = 0.0
    ys, xs = np.nonzero(ink & mask)
    if xs.size:
        lobe = max(case.shape.lobes, key=lambda part: int((part & ink).sum()))
        by, bx = np.nonzero(lobe)
        bw, bh = bx.max() - bx.min() + 1, by.max() - by.min() + 1
        out["offx"] = ((xs.min() + xs.max() + 1) / 2.0 - bx.mean() - 0.5) / bw
        out["offy"] = ((ys.min() + ys.max() + 1) / 2.0 - by.mean() - 0.5) / bh
    else:
        out["offx"] = out["offy"] = 0.0
    out["off"] = float(max(abs(out["offx"]), abs(out["offy"])) > OFF_LIMIT)
    return out


def page_spread(cases: list[Case]) -> dict[str, float]:
    """The sizes of each page of English speech, lettered as the app letters a page: the sizes it fits at, the page's
    caps (`page_caps`, the readable size the least), then each set at most at its cap."""
    pages: dict[int, list[Case]] = {}
    for c in cases:
        if c.page >= 0:
            pages.setdefault(c.page, []).append(c)
    ratios, tallest, before = [], [], []
    for page in pages.values():
        free = [set_case(c)[0].size for c in page]
        caps = typeset.page_caps([("", s, 0.0) for s in free], READABLE)
        sizes = [set_case(c, min(MAX_SIZE, cap) if cap else MAX_SIZE)[0].size for c, cap in zip(page, caps)]
        p10, p90 = np.percentile(sizes, [10, 90])
        ratios.append(p90 / max(1.0, p10))
        tallest.append(max(sizes) / float(np.median(sizes)))
        before.append(float(np.percentile(free, 90) / max(1.0, np.percentile(free, 10))))
    return {"pages": float(len(pages)), "p90/p10": float(np.mean(ratios)), "max/med": float(np.mean(tallest)),
            "uncapped p90/p10": float(np.mean(before))}


COLUMNS = ["n", "size/fit", "<0.9", "over", "tight", "margin", "rect", "cond", "hyph", "lone1", "lone", "lone9", "weak",
           "pstart", "hourgl", "pyram", "prof", "offx", "offy", "off>5", "ms", "ms95"]


def aggregate(rows: list[dict[str, float]]) -> dict[str, float]:
    if not rows:
        return {}
    n = len(rows)
    multi = max(1.0, sum(r["multi"] for r in rows))
    shaped = max(1.0, sum(r["shaped"] for r in rows))
    ends = max(1.0, sum(r["ends"] for r in rows))
    ms = [r["ms"] for r in rows]
    return {"n": float(n), "size/fit": float(np.mean([r["ratio"] for r in rows])),
            "<0.9": 100.0 * sum(r["ratio"] < 0.9 for r in rows) / n, "over": sum(r["over"] for r in rows),
            "tight": 100.0 * sum(r["tight"] for r in rows) / n, "margin": float(np.mean([r["margin"] for r in rows])),
            "rect": 100.0 * sum(r["rect"] for r in rows) / n, "cond": 100.0 * sum(r["cond"] for r in rows) / n,
            "hyph": sum(r["hyph"] for r in rows), "lone1": 100.0 * sum(r["lone1"] for r in rows) / multi,
            "lone": 100.0 * sum(r["lone"] for r in rows) / multi,
            "lone9": 100.0 * sum(r["lone9"] for r in rows) / multi,
            "weak": 100.0 * sum(r["weak"] for r in rows) / ends, "pstart": sum(r["pstart"] for r in rows),
            "hourgl": 100.0 * sum(r["hourgl"] for r in rows) / shaped,
            "pyram": 100.0 * sum(r["pyram"] for r in rows) / shaped,
            "prof": float(sum(r["prof"] for r in rows) / shaped),
            "offx": 100.0 * float(np.mean([abs(r["offx"]) for r in rows])),
            "offy": 100.0 * float(np.mean([abs(r["offy"]) for r in rows])),
            "off>5": 100.0 * sum(r["off"] for r in rows) / n, "ms": float(np.mean(ms)),
            "ms95": float(np.percentile(ms, 95))}


def _table(named: Sequence[tuple[str, dict[str, float]]]) -> str:
    width = max(len(name) for name, _ in named) + 1
    out = [" ".join(["".ljust(width), *(c.rjust(max(6, len(c))) for c in COLUMNS)])]
    for name, row in named:
        if not row:
            continue
        cells = []
        for c in COLUMNS:
            v = row[c]
            if c in ("n", "over", "hyph", "pstart"):
                text = f"{v:.0f}"
            else:
                text = f"{v:.3f}" if c in ("size/fit", "margin", "prof") else f"{v:.1f}"
            cells.append(text.rjust(max(6, len(c))))
        out.append(" ".join([name.ljust(width), *cells]))
    return "\n".join(out)


# --- sheets to look at --------------------------------------------------------------------------------------------

def contact_sheets(cases: list[Case], images: list[Image.Image], folder: Path, per_sheet: int = 24) -> list[Path]:
    """The cases as set, the bubble's outline in grey and its body's centroid as a red cross, *per_sheet* to a PNG."""
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    cell = 260
    for start in range(0, len(cases), per_sheet):
        chunk = list(zip(cases[start:start + per_sheet], images[start:start + per_sheet]))
        cols = 6
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cell, rows * (cell + 16)), (235, 235, 235))
        draw = ImageDraw.Draw(sheet)
        for i, (case, image) in enumerate(chunk):
            tile = np.asarray(image).copy()
            edge = cv2.morphologyEx(case.shape.mask, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
            tile[edge] = (150, 150, 150)
            lobe_ys, lobe_xs = np.nonzero(case.shape.lobes[0] if len(case.shape.lobes) == 1 else case.shape.body)
            cx, cy = int(lobe_xs.mean()), int(lobe_ys.mean())
            tile[max(0, cy - 4):cy + 5, cx] = (220, 0, 0)
            tile[cy, max(0, cx - 4):cx + 5] = (220, 0, 0)
            im = Image.fromarray(tile)
            im.thumbnail((cell - 8, cell - 8))
            x, y = (i % cols) * cell, (i // cols) * (cell + 16)
            sheet.paste(im, (x + 4, y + 4))
            draw.text((x + 4, y + cell), f"#{case.n} {case.shape.kind} {case.language}", fill=(0, 0, 0))
        path = folder / f"typeset_{start // per_sheet:02d}.png"
        sheet.save(path)
        paths.append(path)
    return paths


# --- the run ------------------------------------------------------------------------------------------------------

def evaluate(cases: list[Case], timing: bool = True) -> tuple[list[dict[str, float]], list[Image.Image]]:
    rows, images = [], []
    for case in cases:
        fit, image = set_case(case)
        row = measure(case, fit, image, oracle_size(case))
        row["ms"] = time_case(case) if timing else 0.0
        rows.append(row)
        images.append(image)
    return rows, images


def synthetic(args: argparse.Namespace) -> int:
    cases = corpus(args.seed)
    rows, images = evaluate(cases, not args.no_timing)
    named = [("all", aggregate(rows))]
    spaced = [r for c, r in zip(cases, rows) if c.language not in ("ja", "ar")]
    named.append(("latin", aggregate(spaced)))
    for kind in SHAPE_KINDS:
        named.append((kind, aggregate([r for c, r in zip(cases, rows) if c.shape.kind == kind])))
    for kind in ("short", "medium", "long", "longword", "names", "punct", "emph"):
        english = [r for c, r in zip(cases, rows) if c.kind == kind and c.language == "en"]
        named.append((f"t:{kind}", aggregate(english)))
    named.append(("other lang", aggregate([r for c, r in zip(cases, rows) if c.language != "en"])))
    spread = page_spread(cases)
    print(f"{len(cases)} cases, seed {args.seed}")
    print(_table(named))
    print(" ".join(f"{k} {v:.3f}" for k, v in spread.items()))
    codes = sorted({f for c in cases for f in FLAGGED.get(c.n, ())})
    flagged = {code: 100.0 * sum(code in FLAGGED.get(c.n, ()) for c in cases) / len(cases) for code in codes}
    print("checks " + (" ".join(f"{code} {share:.1f}%" for code, share in flagged.items()) or "none") +
          f" (any {100.0 * sum(bool(FLAGGED.get(c.n)) for c in cases) / len(cases):.1f}%)")
    if args.cases:
        print("case shape lang kind size fit lines over tight margin hyph lone1 lone lone9 weak hourgl pyram prof "
              "offx offy ms")
        for c, r in zip(cases, rows):
            print(f"{c.n:4d} {c.shape.kind:8s} {c.language} {c.kind:8s} {r['size']:3.0f} {r['fit']:3.0f} "
                  f"{r['lines']:2.0f} {r['over']:.0f} {r['tight']:.0f} {r['margin']:.2f} {r['hyph']:.0f} "
                  f"{r['lone1']:.0f} {r['lone']:.0f} {r['lone9']:.0f} {r['weak']:.0f} {r['hourgl']:.0f} "
                  f"{r['pyram']:.0f} {r['prof']:.3f} {100 * r['offx']:+5.1f} {100 * r['offy']:+5.1f} {r['ms']:6.1f}")
    if args.png:
        for path in contact_sheets(cases, images, Path(args.png)):
            print(path)
    if args.json:
        Path(args.json).write_text(json.dumps({"aggregate": dict(named), "pages": spread, "checks": flagged,
                                               "cases": rows}, indent=1), encoding="utf-8")
    return 0


# --- the line-break yardstick --------------------------------------------------------------------------------------

def _gold_points() -> dict[str, dict[str, set[int]]]:
    """Per language, per word of `GOLD_HYPHENS` in lower case, where it may take a hyphen."""
    out: dict[str, dict[str, set[int]]] = {}
    for code, words in GOLD_HYPHENS.items():
        for marked in words:
            parts = marked.lower().split("-")
            points, at = set(), 0
            for part in parts[:-1]:
                at += len(part)
                points.add(at)
            out.setdefault(code, {})["".join(parts)] = points
    return out


def _thai_gold(marked: str) -> tuple[str, set[int]]:
    """A Thai line of `BREAK_TEXTS` as it is set (its marks left out) and where a line may break in it, counted in
    its letters with the spaces left out."""
    text, ok, letters = [], set(), 0
    for ch in marked:
        if ch in "|·":
            ok.add(letters)
            continue
        if ch == " ":
            ok.add(letters)
        else:
            letters += 1
        text.append(ch)
    return "".join(text), ok


def _hyphen_points(word: str, language: str) -> list[int]:
    """`typeset.hyphen_points` in *language*, or, in a typesetter whose rule knows no language, as it is."""
    if "language" in inspect.signature(typeset.hyphen_points).parameters:
        return typeset.hyphen_points(word, language)
    return typeset.hyphen_points(word)


def _line_hyphens(lines: list[str], text: str, gold: dict[str, set[int]]) -> tuple[int, int, int]:
    """The words *lines* split (a line ending in a hyphen that is not the word's own, or a line ending inside a word
    with no hyphen): (all of them, those at a point *gold* does not allow, those whose word *gold* does not know)."""
    marks = ".,;:!?¡¿\"'«»"
    own = {w.strip(marks) for w in text.split()}
    split = bad = unknown = 0
    k = 0
    while k < len(lines) - 1:
        words, after = lines[k].split(), lines[k + 1].split()
        if not words or not after:
            k += 1
            continue
        head = words[-1]
        hyphen = head.endswith("-")
        if (head + after[0]).strip(marks) in own if hyphen else (head + after[0]).strip(marks) not in own:
            k += 1
            continue  # a word's own hyphen (well- / known), or two words with a line between them
        parts = [head[:-1] if hyphen else head]
        j = k + 1
        while True:  # the word followed over the lines it runs on
            tokens = lines[j].split()
            more = len(tokens) == 1 and tokens[0].endswith("-") and j + 1 < len(lines) and bool(lines[j + 1].split())
            parts.append(tokens[0][:-1] if more else tokens[0])
            if not more:
                break
            j += 1
        word = "".join(ch for ch in "".join(parts) if ch.isalpha()).lower()
        cut = 0
        for part in parts[:-1]:
            cut += sum(ch.isalpha() for ch in part)
            split += 1
            if word not in gold:
                unknown += 1
            elif cut not in gold[word]:
                bad += 1
            if (word not in gold or cut not in gold[word]) and SHOW_SPLITS:
                print(f"   {'unknown' if word not in gold else 'bad'}: {'-'.join(parts)} at {cut}")
        k = j
    return split, bad, unknown


SHOW_SPLITS = False  # (--cases with --breaks: each bad or unknown split printed)


def break_eval(args: argparse.Namespace) -> int:
    """The line breaks by language, numbers only. Per language the hyphenation points `typeset.hyphen_points` finds
    in the words of `GOLD_HYPHENS` (``points``, of them ``bad``: where the language's rules allow none; ``found``: the
    share of the allowed ones, within the letters a hyphen must leave, that it finds); then each line of
    `BREAK_TEXTS` set by `letter_text` as the app sets it, in cramped bubbles of `BREAK_SHAPES` at sizes drawn between
    9 and 14 px: ``lines``, ``splits`` (words split over two lines, by a hyphen or, in Thai, by a line break inside a
    word), ``bad`` (splits where the language allows none: in Thai every split), ``unknown`` (splits of a word gold
    does not know), and ``ms`` per bubble (the layout without the cache, best of `TIMING_RUNS`)."""
    global SHOW_SPLITS
    SHOW_SPLITS = bool(args.cases)
    gold = _gold_points()
    print("hyphenation points of the gold words")
    print(f"{'lang':5s} {'words':>5s} {'points':>6s} {'bad':>4s} {'found':>6s}")
    for code, words in gold.items():
        if not words:
            continue
        points = bad = allowed = good = 0
        for word, ok in words.items():
            found = set(_hyphen_points(word, LANGUAGE_NAMES[code]))
            n = len(word)
            reachable = {p for p in ok if typeset.HYPHEN_HEAD <= p <= n - typeset.HYPHEN_EDGE} \
                if n >= typeset.HYPHEN_MIN_LETTERS else set()
            points += len(found)
            bad += len(found - ok)
            good += len(found & reachable)
            allowed += len(reachable)
        print(f"{code:5s} {len(words):5d} {points:6d} {bad:4d} {100.0 * good / max(1, allowed):5.1f}%")
    offered = inside = allowed = kept = 0
    for code, marked in BREAK_TEXTS:
        if code != "th":
            continue
        text, ok = _thai_gold(marked)
        bare = text.replace(" ", "")
        if hasattr(typeset, "_units"):  # the places the typesetter may break a line at, in the letters
            at, cuts = 0, set()
            for unit in typeset._units(text, "thai")[:-1]:
                at += len(unit.replace(" ", ""))
                cuts.add(at)
        else:  # between any two characters but before a combining mark or a character that may not start a line
            cuts = {p for p in range(1, len(bare)) if unicodedata.category(bare[p]) != "Mn"
                    and bare[p] not in typeset._NO_LINE_START}
        offered += len(cuts)
        inside += len(cuts - ok)
        allowed += len(ok - {0, len(bare)})
        kept += len(cuts & ok)
    print(f"Thai: {offered} places a line may break, {inside} of them inside a word, "
          f"{100.0 * kept / max(1, allowed):.1f}% of the places between words")
    rng = np.random.default_rng(args.seed + 1)
    rows: dict[str, list[float]] = {}
    for code, marked in BREAK_TEXTS:
        text, thai_ok = _thai_gold(marked) if code == "th" else (marked, set())
        language = LANGUAGE_NAMES[code]
        lettering = _lettering(text, code)
        script = script_of(text, language)
        unit = typeset.text_width(typeset.styled_font(lettering, 100), typeset.display_form(text, script))
        for shape_kind in BREAK_SHAPES:
            size = float(rng.uniform(9, 14))
            area = max(1500.0, unit / 100.0 * size * size * LINE_SPACING / float(rng.uniform(0.42, 0.55)))
            if shape_kind == "narrow":
                area = max(area, 5000.0)  # (as in the corpus)
            case = Case(0, code, "break", text, make_shape(shape_kind, area, rng))
            fit, _image = set_case(case)
            lines = [t for t, _x, _y in fit.lines if t]
            if code == "th":
                at, cuts = 0, []
                for line in lines[:-1]:
                    at += len(line.replace(" ", ""))
                    cuts.append(at)
                split = sum(c not in thai_ok for c in cuts)
                bad, unknown = split, 0
                if split and SHOW_SPLITS:
                    print("   inside a word:", " / ".join(lines))
            else:
                split, bad, unknown = _line_hyphens(lines, text, gold.get(code, {}))
            ms = time_case(case) if not args.no_timing else 0.0
            row = rows.setdefault(code, [0.0] * 6)
            for k, v in enumerate((1.0, float(len(lines)), float(split), float(bad), float(unknown), ms)):
                row[k] += v
    print("lines set in cramped bubbles")
    print(f"{'lang':5s} {'cases':>5s} {'lines':>5s} {'splits':>6s} {'bad':>4s} {'unknown':>7s} {'ms':>6s}")
    total = [0.0] * 6
    for code, row in rows.items():
        print(f"{code:5s} {row[0]:5.0f} {row[1]:5.0f} {row[2]:6.0f} {row[3]:4.0f} {row[4]:7.0f} {row[5] / row[0]:6.1f}")
        total = [a + b for a, b in zip(total, row)]
    print(f"{'all':5s} {total[0]:5.0f} {total[1]:5.0f} {total[2]:6.0f} {total[3]:4.0f} {total[4]:7.0f} "
          f"{total[5] / max(1.0, total[0]):6.1f}")
    return 0


# --- the earlier yardstick: OpenMantra --------------------------------------------------------------------------------

def openmantra_eval(args: argparse.Namespace) -> int:
    """The typesetter on the OpenMantra pages, before and after, numbers only (the yardstick of 2026-11-13).

    The translations come from the book caches of earlier OpenMantra runs (``~/.taslation/cache/OpenMantra_*``, read
    only), the pages from the dataset (``tools/openmantra.py``; CC BY-NC, never shipped). Each cached page is found by
    its fingerprint, the page's regions are detected (on the CPU, no OCR) and paired with its bubbles by
    ``Pipeline._apply_cached``, as for a page from the cache, erased on the page in memory as the app erases them and
    set by the real typesetter, once per configuration: ``before``: greedy lines, no cap; ``balanced``:
    `typeset._balanced`; ``capped k``: `Pipeline.cap_sizes` at that k; ``both k``: the two together. Printed for
    each: the orphan rate and the like, the spread of the line widths, the mean size, the lines below
    ``readable_font_size``, the page's 90th to 10th percentile of size, lines wider than their room, ms per region."""
    import openmantra  # noqa: F401  (the dataset reader, next to this tool)
    from taslation import fingerprint as fp
    from taslation import protect
    from taslation.cache import CachedPage
    from taslation.pipeline import Pipeline, is_dark
    from taslation.render import erase_region

    caches = {"balloon_dream": "OpenMantra_balloon", "boureisougi": "OpenMantra_boureisougi",
              "rasetugari": "OpenMantra_rasetugari_full", "tencho_isoro": "OpenMantra_tencho",
              "tojime_no_siora": "OpenMantra_tojime"}
    match_bits, orphan_letters, lone_letters = 24, 5, 3

    def cached_pages(series: str) -> list[CachedPage]:
        path = Path.home() / ".taslation" / "cache" / f"{caches[series]}.json"
        return [CachedPage.from_json(p) for p in json.loads(protect.read(path).decode("utf-8-sig"))["pages"]]

    settings = Settings(render_unmatched_cached=True)
    pipeline = Pipeline(settings)
    pages: list[list[TextRegion]] = []
    for name in args.series or list(caches):
        cached = cached_pages(name)
        done = 0
        for page in openmantra.load(args.root, name):
            if args.pages and done >= args.pages:
                break
            rgb = np.array(page.open())
            regions: list[TextRegion] = []
            units = fp.analyze(rgb, settings.margins)
            live = pipeline._detect(rgb)
            owners = pipeline._owners(rgb, live, units)
            for unit in units:
                near = min(cached, key=lambda c: fp.hamming(unit.fingerprint, c.fingerprint), default=None)
                if near is None or fp.hamming(unit.fingerprint, near.fingerprint) > match_bits:
                    continue
                mine = [r for r in live if owners[id(r)] is unit]
                regions += pipeline._apply_cached(unit, near, mine, rgb)
            regions = [r for r in regions if r.translated_text]
            for r in regions:
                erase_region(rgb, r, settings.erase_mode, settings.white_threshold, settings.dark_threshold,
                             is_dark(r))
            if regions:
                pages.append(regions)
                done += 1

    def set_page(regions: list[TextRegion]) -> list[Any]:
        fits = []
        for r in regions:
            lettering = pipeline.lettering_for(r.translated_text, r.tag)
            top = min(settings.max_font_size, r.size_cap) if r.size_cap else settings.max_font_size
            fits.append(typeset.layout_text(r.mask, r.translated_text, lettering, settings.min_font_size, top,
                                            settings.line_spacing, False,
                                            script_of(r.translated_text, settings.target_language)))
        return fits

    def score(fits_by_page: list[list[Any]]) -> dict[str, float]:
        orphans = avoidable = lone = multi = thin = lines = small = 0
        spreads: list[float] = []
        sizes: list[int] = []
        ratios: list[float] = []
        for fits in fits_by_page:
            page_sizes = [f.size for f in fits]
            sizes += page_sizes
            if len(page_sizes) >= 4:
                p10, p90 = np.percentile(page_sizes, [10, 90])
                ratios.append(float(p90 / max(1.0, p10)))
            for fit in fits:
                texts = [t for t, _x, _y in fit.lines if t]
                lines += len(texts)
                small += len(texts) if fit.size < settings.readable_font_size else 0
                if len(texts) < 2:
                    continue
                multi += 1
                widths = [typeset.text_width(fit.font, typeset.display_form(t, "lgc")) for t in texts]
                words = texts[-1].split()
                orphan = len(words) == 1 and _letters(words[0]) <= orphan_letters
                orphans += orphan
                avoidable += orphan and len(texts[-2].split()) >= 2
                lone += any(len(t.split()) == 1 and _letters(t) <= lone_letters for t in texts[1:-1])
                thin += widths[-1] < 0.4 * max(widths)
                spreads.append((max(widths) - min(widths)) / max(widths))
        share = 100.0 / max(1, multi)
        return {"multi": float(multi), "orphan %": orphans * share, "avoidable %": avoidable * share,
                "lone %": lone * share, "thin last %": thin * share,
                "width spread": float(np.mean(spreads)) if spreads else 0.0, "mean size": float(np.mean(sizes)),
                "below readable %": 100.0 * small / max(1, lines), "p90/p10": float(np.mean(ratios)) if ratios else 0.0}

    def run(balance: bool, k: float | None) -> dict[str, float]:
        typeset.BALANCE_LINES, typeset.SIZE_CAP = balance, k
        n = max(1, sum(len(p) for p in pages))
        setting = float("inf")
        fits: list[list[Any]] = []
        for _ in range(TIMING_RUNS):
            for p in pages:
                pipeline.cap_sizes(p, [r.translated_text for r in p])
            t0 = time.perf_counter()
            fits = [set_page(p) for p in pages]
            setting = min(setting, time.perf_counter() - t0)
        return {**score(fits), "ms/region": 1000.0 * setting / n}

    configs: list[tuple[str, bool, float | None]] = [("before", False, None), ("balanced", True, None)]
    for k in args.k:
        configs += [(f"capped {k}", False, k), (f"both {k}", True, k)]
    results = {name: run(balance, k) for name, balance, k in configs}
    keys = list(next(iter(results.values())))
    print(f"{len(pages)} pages")
    print(" | ".join(["config".ljust(12), *(k.rjust(max(len(k), 7)) for k in keys)]))
    for name, row in results.items():
        print(" | ".join([name.ljust(12), *(f"{row[k]:.2f}".rjust(max(len(k), 7)) for k in keys)]))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--cases", action="store_true", help="also one row per case")
    parser.add_argument("--png", default="", help="a folder for contact sheets of the cases as set")
    parser.add_argument("--json", default="", help="a file for the numbers")
    parser.add_argument("--no-timing", action="store_true", help="leave out the timing (faster)")
    parser.add_argument("--openmantra", action="store_true", help="the earlier yardstick on OpenMantra instead")
    parser.add_argument("--breaks", action="store_true", help="the line breaks by language instead (`break_eval`)")
    parser.add_argument("--thai-fallback", action="store_true",
                        help="Thai words by the rule that stands in for Windows' break iterator (breaks.USE_NATIVE off)")
    parser.add_argument("--root", type=Path, default=None, help="(--openmantra) the OpenMantra folder")
    parser.add_argument("--pages", type=int, default=0, help="(--openmantra) only the first N pages of each series")
    parser.add_argument("--series", nargs="*", default=None, help="(--openmantra) the series")
    parser.add_argument("--k", type=float, nargs="*", default=[1.2, 1.3, 1.4], help="(--openmantra) the caps to try")
    args = parser.parse_args(argv)
    netguard.install()
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    if args.thai_fallback:
        from taslation.render import breaks

        breaks.USE_NATIVE = False
    if args.breaks:
        return break_eval(args)
    return openmantra_eval(args) if args.openmantra else synthetic(args)


if __name__ == "__main__":
    raise SystemExit(main())
