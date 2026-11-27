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
ピタ ピタリ ピッタリ ギュ ギュウ グ ググ ギリ ギシ キシ ギイ キイ キキー ガタ ゴト コトリ カタ カラ カランコロン
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


# The base forms PLaMo 3 Translate gets wrong as a sound effect into English - romanised (Zugan for ズガン) or made
# another word (Cotton for コトン) -, each with an English rendering and its meaning in a few words, written for
# TASlation like the list. Measured on 2026-11-28 on every base form of the list lettered as a page letters it
# (tools/sfx_eval.py, docs/OFFLINE_VERIFICATION.md, "Sound effects, the kind of a line and PLaMo"): the ones it got
# wrong told that the line is a sound effect drawn on the art, with no earlier pairs, and the ones it got wrong after
# ten earlier pairs with nothing said, as the app asks; the cries and laughs it romanised as English letters them (Ah,
# Ahaha, Kyaa) are not here. `rendering` looks a reading up; `plamo.PlamoTranslator._sound` gives a sound effect's
# rendering to the model as the line's glossary entry.
RENDERINGS_TEXT = """
ドゴン Boom | a heavy blow or crash
ドガン Kaboom | an explosion or a heavy blow
ガン Clang | a hard hit on metal
ゴキン Crack | a hard knock, a bone cracking
キン Clink | a high metallic ring
カン Clang | a knock on metal or wood
コン Knock | a light knock
ポカ Bonk | a light hit on the head
ボカ Wham | a punch landing
ボコ Pow | a punch, or bubbling
ドガ Wham | a heavy kick or blow
ガシ Grab | a firm grab or block
ペシ Slap | a light slap
ビタン Splat | slapping flat against something
ベタン Splat | falling flat
ボテ Flop | a soft clumsy fall
ドム Thud | a heavy dull blow
ズン Thoom | a heavy deep impact
バフ Fwump | flopping onto something soft
ダン Bam | a hard stomp or slam
タン Tap | a light tap or step
トン Tap | a light tap
コトン Clunk | a small thing set down
ゴトン Clunk | a heavy thing falling
ガラン Clang | a hollow metal clatter
カラン Clink | a light hollow ring
ジャボン Sploosh | a heavy splash
チャポン Plop | something dropping into water
パリン Shatter | glass breaking
バリン Smash | something breaking hard
ズガン Blam | a heavy shot or blow
ボガン Kaboom | an explosion
バゴン Wham | a heavy blow
ズバン Blam | a sharp heavy hit
メリ Creak | something giving way
ミシ Creak | wood creaking under weight
ドグシャ Crunch | a crushing blow
ヒュン Whoosh | something flying past
ブン Whoosh | a swing through the air
ブオン Vwoom | a heavy swing or an engine
ヴン Vmmm | a low hum
ズバ Slash | a swift cut
ザク Shnk | a stab or a cut into something
ズシャ Skrsh | a skid or a slash
ズザ Skid | sliding along the ground
ザン Slash | a clean cut
スパ Slice | a clean slice
スパン Shing | a clean cut or a sharp slap
シャキン Shing | a blade drawn
ジャキン Chak | a weapon made ready
チャキ Chak | a weapon or a tool made ready
キイン Keeen | a high ringing
ギン Clang | blades clashing, or a fierce glare
シュパ Shwip | a swift movement
シャッ Shak | a swift swish
ダ Dash | a sudden dash
タ Tap | a quick step
ザ Shff | a sudden step or move
サ Swish | a quick movement
ス Shh | a smooth quick movement
ガバ Jolt | springing up suddenly
ムク Stir | sitting up
ヌ Loom | appearing suddenly
ズイ Lean in | pushing forward
グイ Tug | a firm pull or push
クル Turn | a quick turn
クルリ Twirl | turning round
グル Spin | turning round
グルン Spin | a full turn
クルン Twirl | a light turn
ゴロ Roll | rolling over
コロ Roll | something small rolling
コロン Roll | rolling over
ヒョイ Hup | a light quick move
ピョン Hop | a hop
ピョコ Pop | popping up
ピョコン Boing | a little hop
スタ Tap | landing on one's feet
テク Step | walking along
トコ Pitter | small steps
トテ Pitter | toddling steps
バタ Thud | falling over
パタ Flap | a light flap or fall
ノシ Stomp | a heavy step
ソロ Tiptoe | moving quietly
ウロ Pace | wandering about
オロ Fluster | at a loss
ヨロ Stagger | staggering
ヨタ Totter | tottering
フラ Woozy | swaying, dizzy
ユラ Sway | swaying
グラ Wobble | shaking, about to fall
ガク Slump | buckling, collapsing
ブル Shiver | shuddering
プル Jiggle | trembling, wobbling
ワナ Tremble | trembling with anger
フル Shiver | quivering
ビク Flinch | flinching
ドキ Ba-dump | the heart skipping a beat
バク Chomp | a big bite, or a pounding heart
トクン Thump | a soft heartbeat
トク Thump | a soft heartbeat
ザワ Murmur | a stir in a crowd, unease
ソワ Fidget | restless
ウズ Itch | itching to act
ムズ Itch | an itch, restless
ムカ Grr | getting annoyed
モヤ Mope | a gloomy, unclear feeling
ワク Thrill | excitement
ニ Grin | a grin
ニカ Grin | a broad grin
ニパ Beam | a bright smile
ム Hmph | sulking
ムス Sulk | a sulky look
プイ Hmph | turning away in a huff
ツン Hmph | aloof, turning away
ジロ Glare | a hard look
ジロリ Glare | a sidelong glare
ギロ Glare | a fierce glare
ギロリ Glare | a fierce glare
キ Glare | a sharp look
キョロ Look | looking around
ジ Stare | a fixed stare
ジー Stare | a long stare
パチクリ Blink | blinking in surprise
ボー Daze | absent-minded, or a fire burning
ポー Blush | flushed, dazed
カア Flush | blushing hot
カ Flash | a sudden flash or flare
ボ Fwoosh | catching fire
メラ Flare | flames rising
ゴウ Roar | a roaring blast
ゴオ Roar | a roaring fire or wind
ゴ Rumble | a heavy rumble
ドド Thunder | many heavy steps, a rush
ズゴゴ Rumble | a deep menacing rumble
ダダ Dash | running feet
パラ Flip | pages turning, a sprinkle
ガラ Slide | a door sliding open
ザー Shhhh | pouring rain, static
シト Pitter | quiet rain
ピチョン Drip | a drop falling
チャプ Splish | water lapping
チャポ Splish | a small splash
ザバ Splash | water pouring over
ジャー Whoosh | running water
ジャバ Splash | water splashing
チョロ Trickle | a trickle
ドバ Gush | a gush
ブク Blub | bubbling
グツ Bubble | simmering
ジリ Inch | edging closer
ビリ Rip | tearing, or a jolt
ギラ Glint | a fierce gleam
チカ Flicker | a flicker
ドロ Ooze | sludge, something thick
ネバ Sticky | sticky
ヌル Slime | slimy
ツル Slip | slipping
スベ Smooth | smooth
サラ Silky | smooth, flowing
モフ Fluff | fluffy
モコ Puff | fluffy, bulging
プニ Squish | soft, squishy
ムニ Squish | soft
プルン Jiggle | a soft jiggle
ブルン Jiggle | a jiggle
ボヨン Boing | a springy bounce
ポヨン Boing | a light bounce
ブヨ Squish | flabby
カチコチ Stiff | frozen stiff
コチ Tick | a clock ticking
ピン Ping | something taut, a flash of insight
ピタ Halt | stopping dead
ギュウ Squeeze | squeezing tight
グ Grip | a firm grip, straining
ググ Nngh | straining
ギリ Grind | teeth grinding, a bowstring drawn
ギシ Creak | creaking
キシ Creak | a creak
ギイ Creak | a door creaking
キキー Screech | brakes screeching
コトリ Click | a small thing set down
カラ Rattle | a hollow rattle, a door sliding
ピロ Bleep | an electronic chime
ピロリン Ding | a cheerful chime
ピコ Blip | a little beep
ピポパ Beep | dialling
ピンポン Ding-dong | a doorbell
ブー Bzzt | a buzzer
ブロロ Vroom | an engine
ブオオ Vrooom | a roaring engine
ヴォン Vwom | an engine revving
ドルン Vroom | an engine starting
キュル Squeal | wheels squealing, a stomach growling
キュイ Whirr | a small machine
ウイーン Whirr | a motor
ウィン Whirr | a motor, an automatic door
ガー Whirr | a loud machine
ガガガ Ratatat | drilling, gunfire
チク Prick | a prick, a sting
ジリリ Rrring | an alarm bell
リーン Ring | a bell
リン Ring | a small bell
シャラン Jingle | a light jingle
シャラ Jingle | a light jingle
ジャラ Jangle | chains or coins
チャリ Jingle | coins or keys
コツ Click | footsteps on a hard floor
ヒタ Pat | quiet bare footsteps
ズル Slide | slipping, dragging
ザザ Rustle | rustling, a rush
モゾ Wriggle | fidgeting
ゴシ Scrub | rubbing hard
フキ Wipe | wiping
スリ Rub | rubbing
ナデ Pat | patting a head
ポンポン Pat pat | a light pat
ビュー Whoosh | a strong wind
ビュオ Whoosh | a gust
サワ Rustle | a breeze in the leaves
ソヨ Breeze | a gentle breeze
シーン Silence | dead silence
シン Hush | silence
ミンミン Chirr | cicadas
チュン Tweet | a sparrow
ピヨ Cheep | a chick
ホー Hoo | an owl, or a sigh of wonder
ケロ Ribbit | a frog, or acting unbothered
ゲロ Croak | a frog
ワン Woof | a dog
モー Moo | a cow
メー Baa | a goat or a sheep
ヒヒーン Neigh | a horse
ウー Grrr | a growl, or a siren
チュー Squeak | a mouse, or a kiss
イ Eek | a squeak of fear or effort
ン Hm | a hum
オワ Whoa | a startled cry
ドワ Whoa | a cry of surprise, a blast
ウガー Raaargh | a frustrated roar
ムキー Grrr | fuming
キー Screech | a screech, a shriek of anger
ゼエ Huff | panting
ゼイ Wheeze | panting
ハフ Huff | puffing, eating something hot
ホ Phew | relief
ホウ Ohh | a sigh of admiration
ヌヌ Grr | frustration
グヌヌ Grrr | gritting one's teeth
シク Sob | quiet sobbing
メソ Sniff | whimpering
エーン Waaah | crying
ワーン Waaah | wailing
ウエーン Waaah | bawling
ウエエ Bleh | disgust, or a sob
クシュン Achoo | a small sneeze
ヘックション Achoo | a big sneeze
クー Zzz | sleeping, or a coo
スー Zzz | quiet breathing in sleep
スピー Zzz | snoring softly
スヤ Zzz | sleeping peacefully
グガー Snore | loud snoring
ムニャ Mumble | talking in one's sleep
パク Chomp | a quick bite
モグ Munch | chewing
ムシャ Munch | eating greedily
ボリ Crunch | crunching
ポリ Crunch | nibbling, scratching
ペロ Lick | a lick
ペコリ Bow | a quick bow
ハム Nom | a bite
アム Nom | a bite
アーン Say ah | feeding someone, a mouth opened wide
カプ Nibble | a little bite
ズキ Throb | a sharp twinge of pain
ズキン Throb | a stab of pain
ヒリ Sting | a smarting pain
ジン Tingle | a tingling, being moved
ジーン Touched | deeply moved, a ringing ache
クラ Dizzy | feeling dizzy
タラ Drip | a drop of sweat
ダラ Drip | dripping, sloppy
ジワ Well up | tears welling, seeping
ツー Trickle | a tear or a drop running down
ゾゾ Shiver | chills
ガーン Shock | a crushing shock
ズーン Gloom | heavy gloom
ドヨーン Gloom | a dark mood
ポツン Alone | all alone
シュン Deflated | crestfallen
ショボン Sad | downcast
パンパカパーン Ta-da | a fanfare
チャンチャン Ta-da | the end
キラーン Twinkle | a gleam
ピカーン Flash | a flash of light or of an idea
ビシ Snap | a sharp pose or point
ヌウ Loom | looming up
ニュ Squish | something poking out
ニュル Slither | sliding out slimily
ヒョコ Peek | popping into view
ヒョッコリ Pop | turning up unexpectedly
ソー Tiptoe | quietly, carefully
ツツツ Glide | sliding smoothly
ピーポー Wee-oo | a siren
ファン Whirr | a fan, a siren
ピピー Tweet | a whistle
パタン Flap | a light thud, a door shutting
ドタン Thud | a heavy fall
ドテン Thud | falling over
コテン Flop | toppling over
ペタン Flop | sitting down flat
ポテ Flop | a soft fall
ボト Plop | something dropping
ドサリ Thud | a heavy thing falling
ファサ Swish | hair or cloth falling softly
フサ Fluff | bushy
ヒラ Flutter | fluttering
ハラ Flutter | falling lightly
ヒラリ Flutter | dodging lightly
ハラリ Flutter | falling softly
ユサ Sway | swaying heavily
ブチン Snap | snapping, losing one's temper
ガヤ Chatter | a noisy crowd
ワイ Chatter | a lively crowd
ズボ Shlup | sinking in, pulling out
スポン Pop | popping out
ボロン Strum | a guitar
ポロン Plink | a string plucked
ピロン Bloop | a notification
ペラ Flip | turning a page
ベラ Blab | chattering, a page flipped
パラリ Flip | a page falling open
ズラ Line up | lined up
ゾロ Troop | coming in a crowd
ゾロリ Troop | in a line
ギョロ Goggle | eyes rolling, glaring
ドギャン Kaboom | a dramatic blast
バギャ Krak | a smashing blow
グワ Whoosh | surging forward
ゴワ Stiff | coarse, stiff
ボワ Fwoom | a burst of flame or aura
ポワ Glow | a soft glow, blushing
ホワ Ahh | a warm, gentle feeling
ヌク Warm | snug and warm
ホカ Warm | steaming warm
ジメ Damp | damp, gloomy
ムシ Muggy | humid, or ignoring someone
スッキリ Ahh | refreshed
ハキ Crisp | clear and brisk
シャン Straight | standing up straight, a ring
ピョイ Hop | a light hop
ニョキ Sprout | sticking up
モク Puff | smoke billowing
プー Toot | a horn, a pout
ブス Stab | a stab
グサ Stab | a stab, a hurtful word
ズブ Squelch | sinking in
ジュル Slurp | slurping, drooling
ジュルリ Slurp | drooling
コロリ Plop | falling over easily, won over easily
ドロン Poof | vanishing in smoke
ポワン Dreamy | a dreamy glow
ホワン Ahh | a warm daze
フワン Float | drifting softly
ムワ Waft | a stuffy waft
モワ Waft | steam or smoke rising
ウギャ Yaagh | a scream
ウギャー Yaaargh | a shriek
ギャン Yelp | a yelp
キャン Yelp | a dog's yelp
キャイン Yipe | a dog yelping in pain
ワオーン Awooo | a howl
アオーン Awooo | a howl
トリャ Hyah | a battle cry
テヤ Hyah | a battle cry
デヤ Hyah | a battle cry
ソリャ Hup | a cry of effort
ドリャ Hyaah | a battle cry
ドキン Ba-dump | the heart jumping
ムグ Mmph | a muffled sound, a mouth full
クン Sniff | sniffing
モソ Munch | eating listlessly, rustling
ゴン Bonk | a hard knock on the head
バラ Scatter | things scattering
ジャリ Crunch | grit or gravel underfoot
ストン Thump | dropping lightly into place
ギギ Creak | a grinding creak
ノソ Lumber | moving slowly and heavily
ゴソ Rustle | rummaging
プチ Snap | a small snap, a temper snapping
ヒック Hic | a hiccup
セイ Hah | a cry of effort
ポツ Drip | a single drop
ゴシャ Crunch | a crushing blow
"""


def long_form(text: str) -> str:
    """*text* as `skeleton` folds it but with its lengthening kept, as one long mark (ガァーン, ガアーン: ガーン; ザァァ:
    ザー), and its repeats kept (ドキドキ); "" when it is no kana. ガン and ガーン are one skeleton and two sounds (a
    clang, a shock), as ワン and ワーン are (a bark, a wail)."""
    kana = kana_form(text)
    if not kana:
        return ""
    kept: list[str] = []
    for ch in kana:
        if ch == "ー":
            if kept and kept[-1] != "ー":
                kept.append("ー")
            continue
        if ch in MARKS or ch == "ッ":
            continue
        ch = SMALL_VOWELS.get(ch, ch)
        before = kept[-1][-1] if kept else ""
        if ch in "アイウエオ" and before and (before == "ー" or VOWEL_OF.get(before) == ch):
            if before != "ー":
                kept.append("ー")  # (a vowel that lengthens the sound before it)
            continue
        kept.append(ch)
    return "".join(kept)


def _renderings() -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for line in RENDERINGS_TEXT.strip().splitlines():
        base, rest = line.split(" ", 1)
        english, meaning = (part.strip() for part in rest.split("|", 1))
        out.setdefault(long_form(base), (english, meaning))
    return out


RENDERINGS = _renderings()  # the `long_form` of a base form -> (English rendering, meaning)


def rendering(text: str) -> tuple[str, str] | None:
    """(the English rendering, its meaning) of the sound word *text* when `RENDERINGS_TEXT` gives its base form one:
    its `long_form` is that base form's, or is once its repeats are said once (ドキドキッ: ドキ); a voicing of a base
    form is another sound (ガン is not カン). None for any other text."""
    if not candidate(text):
        return None
    form = long_form(text)
    return RENDERINGS.get(form) or RENDERINGS.get("".join(_once(_morae(form))))


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
