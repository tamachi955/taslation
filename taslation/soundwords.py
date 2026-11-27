"""Japanese sound words - the giongo and gitaigo a manga letters on its drawing, and the short cries - and the reading
of such lettering set right.

The list is the program's own, written from general knowledge of the language (no dictionary or site was copied):
some 680 base forms in katakana (`BASES`), from which the forms a page letters come by rule. A reading is
compared through its `skeleton`, where the ways lettering stretches and repeats a sound are folded away:

* hiragana is katakana (どきっ is ドキッ), half-width is full width, and the kanji hand lettering is read as when
  it is a kana's look-alike (力 for カ, 口 for ロ, 一 for ー: `LOOKALIKES`);
* a long mark, a small tsu, a wave dash, the marks ! ? and dots are left out (ドッカーーン！！ is ドカン);
* a small vowel is its vowel, and a vowel that only lengthens the one before it is left out (ハァァ, ハアア: ハ;
  ウォオ: ウオ);
* a sound repeated at once is said once (ドキドキ: ドキ; ゴゴゴゴ: ゴ; アハハハ: アハ).

The first sound of every base form is taken voiced, unvoiced and half-voiced as well (カタ, ガタ; ハタ, バタ, パタ),
as lettering voices a sound to make it heavier. A reading is a candidate (`candidate`) when it is short and kana
alone once its look-alikes are read; `find` takes the readers' readings of a region and gives the sound word they
read alike, or - where no two of them read alike - the one that is a sound word, else one a single kana the readers
mix up in hand lettering (`CONFUSABLE`) makes one, which corrects the reading. Nothing here holds a text of a book;
it is used on readings in memory only.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Sequence

# The base forms, katakana, by what they sound like. Each stands for its lengthened, repeated, small-tsu and voiced
# forms (`skeleton`, `_voicings`): ドン is ドーン, ドンッ, ドンドン and トン as well.
BASES = """
ドン ドカン ドゴン ドガン ドスン ドシン ズドン ズシン バン ガン ゴン ゴツン コツン ゴキン ガキン キン カキン カン
コン ポカ ボカ バキ ボキ ベキ ポキ バコ ボコ ドゴ ドガ ズガ ガツン ガシ ビシ パシ ペシ ベチ パチン バチン ビタン
ベタン ドサ ボテ ドテ ゴロン ドム ズン ボン ボム バフ ボフ ダン タン トン コトン ゴトン ガタン ガシャン ガチャン
ガラン カラン ドボン ザブン ジャボン ポチャン チャポン パリン バリン ゴツ ズガン ボガン バゴン ズバン ゴシャ グシャ
ベシャ ビチャ グチャ メキ メリ ミシ パキン ポキン ドグシャ バシッ ドカッ
シュ ヒュン ビュン ブン ブオン ヴン ザシュ ズバ ザク サク ズシャ ズザ ザン スパ スパン シャキン ジャキン チャキ カチャ
ガチャ カチ カチリ チン キイン ギン バシュ プシュ ブシュ シュパ シャッ
ダ タ ザ サ ス バ パ ガバ ムク ヌ ズイ グイ クル クルリ グル グルン クルン ゴロ コロ コロン ヒョイ ピョン ピョコ
ピョコン ポン スタ テク トコ トテ ドタ ドタバタ バタ パタ ノシ ズカ ドス ノソ ソロ コソ ウロ オロ ヨロ ヨタ フラ ユラ
グラ ガク ブル プル ワナ フル ビク ピク ギク ドキ ゾク ゾワ ヒヤ ゾ ハ ギョ バク ドクン ドク トクン トク ザワ ソワ
ウズ ムズ イラ ムカ モヤ ワク ドギマギ ニヤ ニヤリ ニコ ニ ニカ ニパ ム ムス プイ ツン ジロ ジロリ ギロ ギロリ キ
キリ チラ チラリ キョロ ジ ジー パチ パチクリ ポカン ボー ポー ポ カア カ ボ ボウ メラ ゴウ ゴオ ゴ ドド ズゴゴ ズズ
ダダ タタ パラ バラ ガラ ザー シト ポツ ポタ ピチャ ピチャン ピチョン ポチャ チャプ チャポ バシャ ザバ ジャー ジャバ
チョロ ドバ ブク ゴボ グツ コト ジュー ジュワ ジリ ビリ バリ バチ パリ ピシャ ピカ キラ ギラ チカ ドロ ネバ ベタ ヌル
ツル スベ サラ フワ フンワリ モフ モコ プニ ムニ ムニュ プルン ブルン ボヨン ポヨン ブヨ カチコチ コチ ピン ピーン
ピタ ピタリ ピッタリ ギュ ギュウ グ ググ ギリギシ キシ ギイ キイ キキー ガタ ゴト コトリ カタ カラ カランコロン
カシャ パシャ ピロ ピロリン ピコ ピコン ピポ ピポパ ピ ピピ ピンポン ブー ブブ ブーン ブロロ ブオオ ヴォン ドルン
キュル キュ キュイ ウイーン ウィン ガー ガガガ チクタク チ チク ジリリ リーン リン チリン シャラン シャラ ジャラ
チャリン チャリ カツ コツ ペタ ヒタ ズル ズリ ザザ ガサ カサ ゴソ モゾ ゴシ フキ スリ ナデ ポンポン トントン
ヒュー ビュー ビュウ ビュオ サワ ソヨ シーン シン ミンミン チュン ピヨ ホー ケロ ゲロ ワン ニャー ニャン ニャオ
ゴロゴロ モー メー ブヒ ヒヒーン パカ ガルル グルル ガオ ウー シャー チュー
ア アア ウ ウウ エ オ オオ イ ン ンン フ フフ ウフフ ハハ アハハ ワハハ ガハハ ギャハハ ケケ ヒヒ イヒヒ クク クス
プ ププ ニシシ ヘヘ エヘヘ ウヘヘ ムフ グフ ホホ オホホ キャ キャー キャア ギャ ギャー ギャア ヒイ ヒ ヒャ ヒャア ヒエ
ウワ ウワア ワア ワー ワ オワ ドワ ウオ ウオオ ウガー オラ ムキー キー ゲ ゲゲ ゲホ ゴホ コホ ケホ ゴフ グハ ガハ ブハ
プハ ハア ゼエ ゼイ ハフ フウ ホ ホウ ヘエ ホオ フム ウン ウーン ムム ヌヌ グヌヌ ギギ グス グスン ヒック シク メソ エーン
ワーン ウエーン ウエエ オギャー ハクション クシュン ヘックション ゲップ グウ クー スー スピー スヤ グガー ムニャ
パク モグ ムシャ バリボリ ボリ ポリ カリ シャキ ゴク ゴクン ゴクリ チュ ペロ ペコ ペコリ ハム アム アーン ガブ カプ
ガツ ズキ ズキン ヒリ ジン ジーン クラ タラ ダラ ジワ ポロ ボロ ツー ブワ ゾゾ
ガーン ズーン ドヨーン チーン ポツン ガックリ シュン ショボン ムカッ カチン プチ ブチ ピキ ドーン バーン ババーン
ジャーン ジャジャーン パンパカパーン チャンチャン キラーン ピカーン ビシィ ドヤ ヌウ ニュ ニュル ヒョコ ヒョッコリ
ソ ソー ササ スス ツツツ ガタンゴトン ゴー ピーポー ファン カンカン パフ プップー ブッブー ピピー
バタン パタン ドタン ポトン ポト ストン ドテン コテン ペタン ポテ ボト ドサリ バサ ファサ フサ ヒラ ハラ ヒラリ ハラリ
ユサ ブチン プツン プツ ブツ ボソ ヒソ ガヤ ワイ ジャリ ズボ スポン ボロン ポロン ピロン ペラ ベラ パラリ ズラ ズラリ
ゾロ ゾロリ ギョロ ジタバタ ドギャン バギャ グワ ゴワ ボワ ポワ ホワ ヌク ホカ ジメ ムシ カラッ スカ スッキリ ハキ
シャン ビシャ ポチ ピョイ ニョキ モク プク プー ブス グサ ズブ ジュク ジュル ジュルリ ゴロリ コロリ ドロン ポワン
ホワン フワン ムワ モワ ウギャ ウギャー ギャン キャン キャイン ワオ ワオーン アオーン ヒャッホー イエーイ オリャ
トリャ セイ テヤ デヤ ウリャ ソリャ ドリャ ドキン ムグ クン モソ
"""

# kanji the hand lettering of a kana is read as (and the dash and bar a long mark is read as)
LOOKALIKES = {"力": "カ", "口": "ロ", "一": "ー", "二": "ニ", "八": "ハ", "工": "エ", "夕": "タ", "卜": "ト",
              "|": "ー", "｜": "ー", "-": "ー", "－": "ー", "―": "ー", "—": "ー", "‐": "ー", "ｰ": "ー",
              "〜": "ー", "～": "ー", "~": "ー"}
MARKS = set("ー!！?？…‥・、。.,，♡♥☆★♪〃゛゜")
SMALL_VOWELS = {"ァ": "ア", "ィ": "イ", "ゥ": "ウ", "ェ": "エ", "ォ": "オ", "ヮ": "ワ", "ヵ": "カ", "ヶ": "ケ"}
SMALL_Y = set("ャュョ")
MOST_MORAE = 6  # a candidate's skeleton holds so many sounds at the most ...
MOST_CHARS = 16  # ... and its reading so many characters

_VOWEL_ROWS = {"ア": "アカガサザタダナハバパマヤャラワ", "イ": "イキギシジチヂニヒビピミリ",
               "ウ": "ウクグスズツヅヌフブプムユュルヴ", "エ": "エケゲセゼテデネヘベペメレ",
               "オ": "オコゴソゾトドノホボポモヨョロヲ"}
VOWEL_OF = {k: v for v, ks in _VOWEL_ROWS.items() for k in ks}
_VOICED = dict(zip("カキクケコサシスセソタチツテトハヒフヘホウ", "ガギグゲゴザジズゼゾダヂヅデドバビブベボヴ"))
_HALF = dict(zip("ハヒフヘホ", "パピプペポ"))
_PLAIN = {**{v: k for k, v in _VOICED.items()}, **{v: k for k, v in _HALF.items()}}


def kana_form(text: str) -> str | None:
    """*text* in katakana, its look-alike kanji and bars read as kana and its spaces left out; None when anything in
    it is no kana nor a mark (`MARKS`)."""
    out = []
    for ch in unicodedata.normalize("NFKC", str(text)):
        if ch.isspace():
            continue
        ch = LOOKALIKES.get(ch, ch)
        if "ぁ" <= ch <= "ゖ":
            ch = chr(ord(ch) + 0x60)
        if not ("ァ" <= ch <= "ヺ" or ch in MARKS):
            return None
        out.append(ch)
    return "".join(out)


def _morae(kana: str) -> list[str]:
    """*kana* (katakana, no marks) cut into its sounds: a kana with the small ャ, ュ or ョ after it is one."""
    out: list[str] = []
    for ch in kana:
        if ch in SMALL_Y and out:
            out[-1] += ch
        else:
            out.append(ch)
    return out


def _once(morae: list[str]) -> list[str]:
    """*morae* with every run of a sound or of a few sounds repeated at once said once (ドキドキ: ドキ)."""
    i = 0
    out = list(morae)
    while i < len(out):
        for size in (1, 2, 3, 4):
            unit = out[i:i + size]
            if len(unit) < size:
                break
            j = i + size
            while out[j:j + size] == unit:
                del out[j:j + size]
        i += 1
    return out


def skeleton(text: str) -> str:
    """What is left of the reading *text* once the ways lettering stretches and repeats a sound are folded away (see
    the module); "" when it is no kana or has none."""
    kana = kana_form(text)
    if not kana:
        return ""
    kept: list[str] = []
    for ch in kana:
        if ch in MARKS or ch == "ッ":
            continue
        ch = SMALL_VOWELS.get(ch, ch)
        before = kept[-1][-1] if kept else ""
        if ch in "アイウエオ" and before and VOWEL_OF.get(before) == ch:
            continue  # (a vowel that lengthens the sound before it)
        kept.append(ch)
    return "".join(_once(_morae("".join(kept))))


def _voicings(skel: str) -> set[str]:
    """*skel* with its first sound unvoiced, voiced and half-voiced as well; a sound alone only as it is (the list
    has the ones lettered alone)."""
    if len(skel) < 2:
        return {skel}
    first, rest = skel[0], skel[1:]
    plain = _PLAIN.get(first, first)
    forms = {first, plain, _VOICED.get(plain, plain), _HALF.get(plain, plain)}
    return {f + rest for f in forms}


def _known() -> frozenset[str]:
    out: set[str] = set()
    for base in BASES.split():
        out |= _voicings(skeleton(base))
    out.discard("")
    return frozenset(out)


KNOWN = _known()


def known(text: str) -> bool:
    """Whether the reading *text* is a sound word of the list (its `skeleton`)."""
    return skeleton(text) in KNOWN


def candidate(text: str) -> bool:
    """Whether the reading *text* may be a sound word: kana alone (`kana_form`), at most MOST_CHARS characters and
    MOST_MORAE sounds."""
    if not text or len(text) > MOST_CHARS:
        return False
    skel = skeleton(text)
    return bool(skel) and len(_morae(skel)) <= MOST_MORAE


# Kana the readers mix up in hand lettering: each reads as any of the others (`find` tries one at a time, only where
# no two readers read alike). Measured on the sample set's 214 pages at full size: the kana one reader read for
# another's in the 33 regions of hand-lettered sound words among those the readers read as short kana (judged by eye;
# ウ and カ 4 times, ジ and バ twice), and a reader's against the gold lines' sound words (ウ and ラ twice, ワ and ア
# once); a small vowel for a large one, as common (5 times between readers, 3 against the gold), `skeleton` folds
# already. The other pairs between readers came from drawing read as kana.
CONFUSABLE_GROUPS = ("ウカ", "ジバ", "ウラ", "ワア")
CONFUSABLE: dict[str, tuple[str, ...]] = {}
for _group in CONFUSABLE_GROUPS:
    for _ch in _group:
        CONFUSABLE[_ch] = tuple(sorted(set(CONFUSABLE.get(_ch, ())) | (set(_group) - {_ch})))


@dataclass(frozen=True)
class Found:
    """A sound word found among a region's readings: its *text* as it is to stand (a reading, its look-alikes written
    as kana, or a reading with one kana changed), and *how*: "read" (as a reader read it, look-alikes aside) or
    "changed" (one kana changed)."""

    text: str
    how: str
    readers: int  # how many of the readings come to it


def _form(reading: str) -> str:
    """*reading* with its look-alike kanji and bars written as kana and its spaces left out, all else as it was
    (hiragana stays, and so do its dots)."""
    return "".join(LOOKALIKES.get(ch, ch) for ch in reading if not ch.isspace())


def find(readings: Sequence[str]) -> Found | None:
    """The sound word among *readings* (a region's, the first reader's first). Readers that come to one skeleton -
    two of them, or the one reading there is - are taken at their word: it stands when it is a sound word of the list
    (the first reader's reading when it is among them, else the one most of them read; "read"), and nothing is found
    when it is none: a short line in kana that they read alike is no reading to set right. Only where no two of them
    come to one skeleton is a reading that is a sound word taken (the earlier first), else the one most of them come
    to with a single kana changed for one it is mixed up with (`CONFUSABLE`, "changed"). None when nothing is (or no
    reading is a `candidate`)."""
    readings = [r for r in readings if r and candidate(r)]
    if not readings:
        return None
    groups: dict[str, list[str]] = {}
    for text in readings:
        groups.setdefault(skeleton(text), []).append(text)
    best = max(groups, key=lambda k: (len(groups[k]), -readings.index(groups[k][0])))
    if len(groups[best]) >= 2 or len(readings) == 1:
        if best not in KNOWN:
            return None
        group = groups[best]
        text = readings[0] if readings[0] in group else max(group, key=lambda t: (group.count(t), -group.index(t)))
        return Found(_form(text), "read", len(group))
    for text in readings:
        if skeleton(text) in KNOWN:
            return Found(_form(text), "read", 1)
    votes: dict[str, list[str]] = {}
    for text in readings:
        seen: set[str] = set()
        for form in _variants(_form(text)):
            skel = skeleton(form)
            if skel in KNOWN and skel not in seen:
                seen.add(skel)
                votes.setdefault(skel, []).append(form)
    if not votes:
        return None
    best = max(votes, key=lambda k: len(votes[k]))  # (ties: the earlier reading's, as dicts keep their order)
    return Found(votes[best][0], "changed", len(votes[best]))


def _variants(text: str) -> list[str]:
    """*text* with one kana changed for one it is mixed up with (`CONFUSABLE`), each way once; *text* itself not."""
    out = []
    for i, ch in enumerate(text):
        k = LOOKALIKES.get(ch, ch)
        hira = "ぁ" <= k <= "ゖ"
        kata = chr(ord(k) + 0x60) if hira else k
        for other in CONFUSABLE.get(kata, ()):
            other = chr(ord(other) - 0x60) if hira and "ァ" <= other <= "ヶ" else other
            out.append(text[:i] + other + text[i + 1:])
    return out


def agree(readings: Iterable[str]) -> bool:
    """Whether two of the readers read alike, or one alone read (their readings compared once spaces and
    compatibility forms are folded); not where each read another thing."""
    texts = [re.sub(r"\s+", "", unicodedata.normalize("NFKC", t)) for t in readings if t is not None]
    return len(texts) <= 1 or len(set(texts)) < len(texts)
