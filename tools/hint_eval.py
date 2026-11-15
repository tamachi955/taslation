"""Measure whether PLaMo 3 Translate follows a translator's hint, a kind or a room put in its PFML3 ``context`` block.

The region editor's "hint for the model" (a pun, who is addressed), the kind of text and the room a bubble has reach
the chat translator as facts of its bubbles; PLaMo's prompt has no field for them, only the reference ``context``
(`taslation.translate.plamo`). This tries them there, on lines written for this test (no book is involved), each
with a hint that settles what the Japanese leaves open (who did it, a he or a she, one or many, how a name is read,
what a title means here, how politely, to whom) and a pattern a translation that follows the hint matches:

* the hint as one line of ``context`` in four ways (``bare``: the hint alone; ``plain``: "Note: ..."; ``about``:
  "About this line: ..."; ``note``: "Translator's note on the line: ..."), in English, once in Japanese, and the
  ``bare`` and ``note`` ways after a made-up series sheet; against the prompt without a hint. ``bare`` is the way the
  app gives PLaMo a hint (`PlamoTranslator._context`), "bare, after a sheet" the way with a series sheet;
* hints that should change nothing, to see that a hint does no harm (no hint text in the answer, the same words);
* the kind ("Kind of line: shout", "... sound effect (sfx)") and the room ("Room: the translation must fit in N
  characters", N = 60 % of the answer without it).

Every request is a raw PFML3 prompt (`plamo.pfml_prompt`) to the local Ollama through the app's translator
(`make_translator`, the app's options), seeds 1 to ``--seeds``; nothing but 127.0.0.1 is contacted (`netguard`). The
answers are kept in ``--out`` (JSON) so that a run broken off goes on from there. Measured on 2026-11-15:
docs/OFFLINE_VERIFICATION.md, "A translator's hint and PLaMo".

usage: python tools/hint_eval.py [--seeds 3] [--out hint_eval.json] [--show]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from taslation import netguard  # noqa: E402
from taslation.annotations import Glossary  # noqa: E402
from taslation.config import Settings  # noqa: E402
from taslation.translate.models import PLAMO, make_translator  # noqa: E402
from taslation.translate.plamo import pfml_prompt  # noqa: E402

# (Japanese, the hint in English, the hint in Japanese, a translation that follows the hint, what the hint settles)
CASES = [
    ("昨日、一人で行ったらしいよ", "The one who went alone is a woman.", "一人で行ったのは女性。", r"\b[Ss]he\b", "subject"),
    ("あいつ、まだ怒ってる", "あいつ is a girl.", "あいつは女の子。", r"\b[Ss]he\b|\bher\b", "gender"),
    ("昨日、先生を見かけた。元気そうだった", "The teacher is a woman.", "先生は女性。", r"\b[Ss]he\b|\bher\b", "gender"),
    ("隣の席の子、もう帰ったの？", "The child is a boy.", "その子は男の子。", r"\b[Hh]e\b|\bhim\b|\bhis\b|\bboy\b", "gender"),
    ("ずっと待ってたんだって", "It is his sister who waited.", "待っていたのは彼の妹。", r"sister", "subject"),
    ("来月、結婚するんだ", "The speaker's brother is the one getting married.", "結婚するのは話し手の兄。",
     r"brother", "subject"),
    ("もう食べた？", "Asked of a group of friends.", "友達のグループに聞いている。",
     r"you guys|you all|everyone|y'all|all of you|\bguys\b", "addressee"),
    ("猫にエサをあげといて", "There are three cats.", "猫は三匹いる。", r"\bcats\b", "number"),
    ("りんご、買ってきたよ", "Several apples.", "りんごは何個もある。", r"apples", "number"),
    ("友達が来るんだ", "Two friends are coming.", "来るのは友達二人。", r"friends|\btwo\b", "number"),
    ("子供が泣いてる", "Many children are crying.", "泣いているのは大勢の子供。", r"children|kids", "number"),
    ("光、こっちに来て", "光 is a girl's name, read Hikari.", "光は女の子の名前で、読みはひかり。", r"Hikari", "name"),
    ("翼はどこ？", "翼 is a boy's name, read Tsubasa.", "翼は男の子の名前で、読みはつばさ。", r"Tsubasa", "name"),
    ("司がそう言ってた", "司 is a name, read Tsukasa.", "司は人名で、読みはつかさ。", r"Tsukasa", "name"),
    ("明日、葵と会う", "葵 is a name, read Aoi.", "葵は人名で、読みはあおい。", r"Aoi", "name"),
    ("海に会いたい", "海 is a boy's name, read Kai.", "海は男の子の名前で、読みはかい。", r"\bKai\b", "name"),
    ("誠は優しいね", "誠 is a name, read Makoto.", "誠は人名で、読みはまこと。", r"Makoto", "name"),
    ("これ、使ってもいい？", "Said very politely to the company president.", "社長にとても丁寧に言っている。",
     r"[Mm]ay I|[Ww]ould it be|[Ss]ir\b|ma'am|[Pp]ermission|[Mm]ight I", "formality"),
    ("手伝ってくれる？", "Said humbly to the speaker's boss.", "上司にへりくだって頼んでいる。",
     r"[Ww]ould you|[Cc]ould you|[Ss]ir\b|ma'am|[Pp]lease|[Mm]ight", "formality"),
    ("会長が呼んでるよ", "会長 here is the student council president.", "会長は生徒会長のこと。", r"[Pp]resident",
     "term"),
    ("監督、遅いな", "監督 is the coach of the baseball team.", "監督は野球部の監督。", r"[Cc]oach", "term"),
    ("部長に怒られた", "部長 is the captain of the club.", "部長は部活の部長。", r"[Cc]aptain|club president|club leader",
     "term"),
    ("やった！", "The speaker means: I did it!", "「やり遂げた」という意味。", r"did it|made it|pulled it off", "meaning"),
    ("いいよ", "A refusal: no, thanks.", "断っている。", r"\b[Nn]o\b|[Nn]ope|I'm good|I'll pass|don't need|[Nn]ot ",
     "meaning"),
    ("大丈夫です", "A polite refusal of an offer.", "申し出を丁寧に断っている。", r"\b[Nn]o\b|[Tt]hank|[Nn]ot ",
     "meaning"),
    ("静かにしなさい", "Said to a whole class of pupils.", "クラスの生徒全員に言っている。",
     r"everyone|[Cc]lass|all of you|you all|kids|children|guys|everybody", "addressee"),
]
NEUTRAL = [  # hints that say something true but should leave the words as they are
    ("今日はいい天気だね", "Said cheerfully."), ("早く帰ろうよ", "Said while walking home."),
    ("この本、面白かった", "The book is a novel."), ("ちょっと待ってて", "Said on the phone."),
    ("また明日ね", "Said at the school gate."), ("お腹すいた", "Said in a whiny voice."),
    ("それ、本当？", "Surprised."), ("なんでもないよ", "She is hiding something."),
    ("ありがとう、助かった", "Said to a classmate."), ("ここ、どこだろう", "Lost in a forest."),
]
SHOUT = ["待て", "逃げろ", "やめて", "危ない", "助けて", "うるさい", "離せ", "来るな", "行くぞ", "ふざけるな"]
SFX = ["ドキドキ", "ゴゴゴ", "ザーッ", "シーン", "バタン", "ガシャン", "ゴクリ", "ニコッ", "ドン", "キラキラ"]
LONG = ["そんなこと、今さら言われても困るんだけど", "明日の朝までにこの書類を全部片付けなきゃいけないんだ",
        "あの時ちゃんと謝っておけばよかったって、ずっと後悔してる", "せっかく作ったんだから、少しくらい食べてくれてもいいじゃない",
        "まさかこんなところで君に会えるなんて思ってもみなかったよ", "どうして誰も本当のことを教えてくれなかったの",
        "雨が止むまで、もう少しここで待っていようか", "みんなが帰ったあとで、こっそり練習してたんだ",
        "約束の時間はとっくに過ぎてるのに、まだ来ないなんて", "今度の休みには、絶対に海へ連れて行ってあげるからね"]
SHEET = {  # made up: a sheet as a reader might keep one, about none of the lines above
    "entries": [{"term": "魔導書", "rendering": "grimoire"}],
    "characters": [{"name": "穂杉季和", "rendering": "Hosugi Nowa", "gender": "female", "age": "17"},
                   {"name": "樫戸朔", "rendering": "Kashido Saku", "gender": "male"}],
    "style": {"honorifics": "keep", "tone": "casual"},
}
LABELS = {"bare": "{}", "plain": "Note: {}", "about": "About this line: {}",
          "note": "Translator's note on the line: {}"}
# hint conditions: name -> (the label, the hint's language, the sheet before it)
HINTED = {"bare": ("bare", "en", False), "plain": ("plain", "en", False), "about": ("about", "en", False),
          "note": ("note", "en", False), "note, Japanese hint": ("note", "ja", False),
          "note, after a sheet": ("note", "en", True), "bare, after a sheet": ("bare", "en", True)}


def context(*parts: str) -> str:
    """The ``context`` block as `PlamoTranslator._context` joins its parts."""
    return "\n\n".join(p for p in parts if p)


def words(text: str) -> set[str]:
    """The words of *text* of three letters or more, in lower case: what a hint could leave in an answer ("on" in
    "Hold on" is no word of "Said on the phone")."""
    return {w for w in re.findall(r"[a-z']{3,}", text.lower())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--out", type=Path, default=Path("hint_eval.json"))
    ap.add_argument("--show", action="store_true", help="print every answer")
    args = ap.parse_args(argv)
    netguard.install()
    s = Settings()
    s.target_language = "English"
    sheet = Glossary(Path("eval.json"), "eval", "English")
    sheet.apply_json(SHEET)
    premises = sheet.format()
    got: dict[str, str] = json.loads(args.out.read_text("utf-8")) if args.out.exists() else {}
    seeds = list(range(1, args.seeds + 1))
    started, asked = time.monotonic(), 0
    for seed in seeds:
        tr = make_translator(s, PLAMO, seed=seed)
        if not tr.ping():
            print(f"Ollama is not running at {s.ollama_url}")
            return 2

        def ask(key: str, ja: str, ctx: str) -> str:
            nonlocal asked
            key = f"{key}|{seed}|{ja}"
            if key not in got:
                got[key] = " ".join(tr._generate(pfml_prompt(ja, "en", ctx), max(128, 4 * len(ja) + 64), 0).split())
                asked += 1
            return got[key]

        for ja, hint_en, hint_ja, _rx, _what in CASES:
            ask("none", ja, "")
            ask("sheet", ja, premises)
            for name, (label, language, with_sheet) in HINTED.items():
                hint = LABELS[label].format(hint_en if language == "en" else hint_ja)
                ask(name, ja, context(premises if with_sheet else "", hint))
        for ja, hint in NEUTRAL:
            ask("none", ja, "")
            for label in ("bare", "plain", "note"):
                ask(f"neutral {label}", ja, LABELS[label].format(hint))
        for ja in SHOUT:
            ask("none", ja, "")
            ask("shout", ja, "Kind of line: shout")
        for ja in SFX:
            ask("none", ja, "")
            ask("sfx", ja, "Kind of line: sound effect (sfx)")
        for ja in LONG:
            room = max(12, int(len(ask("none", ja, "")) * 0.6))
            got[f"room n|{seed}|{ja}"] = str(room)
            ask("room", ja, f"Room: the translation must fit in {room} characters.")
        args.out.write_text(json.dumps(got, ensure_ascii=False, indent=1), "utf-8")
    print(f"model {PLAMO.ollama_name}; {asked} requests in {time.monotonic() - started:.0f} s; seeds {seeds}")

    def a(key: str, seed: int, ja: str) -> str:
        return got[f"{key}|{seed}|{ja}"]

    n = len(seeds) * len(CASES)
    for name, base in (("none", ""), ("sheet", ""), *((h, "sheet" if HINTED[h][2] else "none") for h in HINTED)):
        followed = sum(bool(re.search(rx, a(name, s_, ja))) for s_ in seeds for ja, _h, _j, rx, _w in CASES)
        line = f"hint {name:20s} followed {followed:2d}/{n}"
        if base:
            missed = [(s_, ja, rx) for s_ in seeds for ja, _h, _j, rx, _w in CASES
                      if not re.search(rx, a(base, s_, ja))]
            mended = sum(bool(re.search(rx, a(name, s_, ja))) for s_, ja, rx in missed)
            spoilt = sum(bool(re.search(rx, a(base, s_, ja))) and not re.search(rx, a(name, s_, ja))
                         for s_ in seeds for ja, _h, _j, rx, _w in CASES)
            by: dict[str, list[int]] = {}
            for s_ in seeds:
                for ja, _h, _j, rx, what in CASES:
                    row = by.setdefault(what, [0, 0])
                    row[0] += bool(re.search(rx, a(name, s_, ja)))
                    row[1] += 1
            line += f"; of the {len(missed)} missed without it {mended} mended, {spoilt} spoilt; " + ", ".join(
                f"{what} {k}/{t}" for what, (k, t) in by.items())
        print(line)
    for label in ("bare", "plain", "note"):
        same = sum(a(f"neutral {label}", s_, ja).rstrip(".!?") == a("none", s_, ja).rstrip(".!?")
                   for s_ in seeds for ja, _h in NEUTRAL)
        leaked = sum(bool(words(hint) & (words(a(f"neutral {label}", s_, ja)) - words(a("none", s_, ja))))
                     for s_ in seeds for ja, hint in NEUTRAL)
        print(f"neutral hint {label:6s} same words {same}/{len(seeds) * len(NEUTRAL)}, "
              f"a word of the hint that the answer without it has not {leaked}")
    bang = {c: sum(a(c, s_, ja).endswith("!") or a(c, s_, ja).isupper() for s_ in seeds for ja in SHOUT)
            for c in ("none", "shout")}
    print(f"shout: an exclamation mark or capitals {bang['shout']}/{len(seeds) * len(SHOUT)} (without the kind "
          f"{bang['none']})")
    changed = sum(a("sfx", s_, ja) != a("none", s_, ja) for s_ in seeds for ja in SFX)
    print(f"sfx: answers changed by the kind {changed}/{len(seeds) * len(SFX)}")
    fits = {c: sum(len(a(c, s_, ja)) <= int(got[f"room n|{s_}|{ja}"]) for s_ in seeds for ja in LONG)
            for c in ("none", "room")}
    print(f"room: within it {fits['room']}/{len(seeds) * len(LONG)} (without it {fits['none']})")
    if args.show:
        for key, text in got.items():
            if not key.startswith("room n|"):
                print(f"  {key}: {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
