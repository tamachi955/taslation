"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: what PLaMo 3 Translate makes of a line's kind, of a standing line
saying the text is a manga's lettering, and of a sound word's meaning or rendering, on lines written for the test
(no book is involved).

Every request is a raw PFML3 prompt (`plamo.pfml_prompt`) through the app's translator (`make_translator`, the app's
options), seeds 1 to ``--seeds``, without earlier pairs; the parts tried go into its ``context`` block as the app puts
the premises and a hint there (`PlamoTranslator._context`):

* ``lines``: made-up lines of each kind - a line spoken in a bubble (with interjections, a stutter, a word drawn out,
  a line that trails off, a sentence split over two bubbles, a name with an honorific), a thought, narration in a
  box, a shout, a sound effect drawn on the art, a sign in the scenery - each under four prompts: nothing (the app's
  prompt before this), the standing line (``standing``), the line's kind (``kind``), both (``both``). Sound effects and
  signs are scored against the renderings written for them here (`SFX`, `SIGNS`); the other kinds are printed changed
  against the prompt without either, for a person to judge better, the same or worse.
* ``words``: every base form of the program's sound-word list (`taslation.soundwords.BASES`, lettered as a page
  letters it: `lettered`) under nothing, the kind, and both, into each ``--language``; each answer sorted as empty,
  the Japanese copied, its romanisation (`romanised`), or a word of the target language, which a person judges.
* ``position``: the words lettered, after ten made-up earlier pairs (`HISTORIES`), with nothing, with the standing
  line and the kind at the front of the prompt (where the premises and a hint go), and with both in a second
  ``context`` element after the pairs (`late_prompt`: the prompt then shares its beginning with the lines before it).
* ``renderings``: the words `taslation.soundwords.RENDERINGS_TEXT` gives a rendering, after ten made-up earlier pairs
  in the target language (`HISTORIES`), with nothing (``none``), with the standing line and the kind, the meaning
  after the kind (``meaning``), with the English rendering there (``english``, the default beside English), or with
  no ``context`` and the English rendering as the word's glossary entry (``glossary``, the default for English).
* ``chat``: every third base form, lettered, through the chat translator (`OllamaTranslator.translate_page`),
  ``CHAT_BATCH`` words a request as one page's bubbles, without facts and with the kind "sfx" in each one's facts.

The answers are kept in ``--out`` (JSON) so that a run broken off goes on from there. ``--start-ollama PORT``: the
server TASlation's own starter starts on that loopback port (`openmantra_eval.start_own_ollama`), stopped at the end;
nothing but 127.0.0.1 is contacted (`netguard`). Measured on 2026-11-28: docs/OFFLINE_VERIFICATION.md, "Sound effects,
the kind of a line and PLaMo".

usage: python tools/sfx_eval.py lines [--seeds 3] [--out sfx_eval.json] [--show] [--start-ollama 11435]
       python tools/sfx_eval.py words --language English --language French [--out ...] [--show]
       python tools/sfx_eval.py position|renderings|chat [--language ...] [--conditions a,b] [--out ...]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from taslation import netguard, soundwords  # noqa: E402
from taslation.config import Settings  # noqa: E402
from taslation.translate.base import TranslationError  # noqa: E402
from taslation.translate.models import PLAMO, make_translator, plamo_code  # noqa: E402
from taslation.translate.plamo import MSG, TAG, pfml_prompt  # noqa: E402

STANDING = "The lettering of a manga page: short lines."
KIND_LINES = {"speech": "A line spoken in a speech bubble.", "thought": "A character's thought.",
              "narration": "Narration in a caption box.", "shout": "A line shouted aloud.",
              "sfx": "A sound effect drawn on the art.",
              "sign": "Text written in the scenery (a sign or a label), not spoken."}
CONDITIONS = ("none", "standing", "kind", "both")

# (Japanese, kind); the lines of a kind are made up for the test
SPEECH = ["え？", "うん、わかった", "そ、そんなこと言ってない！", "すごーい！", "田中先輩、おはようございます", "美咲ちゃん、待ってよ",
          "だって、あの時は…", "それで、結局", "誰も来なかったんだ", "はあ？何それ", "ちょ、ちょっと待って", "やったー！"]
THOUGHT = ["どうしよう…", "あいつ、何を考えてるんだ", "まさか、気づかれた？", "早く帰りたい", "この人、どこかで…", "落ち着け、私"]
NARRATION = ["その日、町に初雪が降った", "三年後――", "そして、夏休みが始まった", "翌朝", "彼女はまだ知らなかった",
             "これは、ある小さな村の物語"]
SHOUT = ["待てー！", "危ない！", "ふざけるな！", "逃げろ！！", "やめろぉぉ！"]
# a sound effect and what an English rendering of it may say (a pattern, case ignored)
SFX = {"ドキドキ": r"thump|throb|ba-?dump|pound|heart|thud", "ガシャン": r"crash|smash|clang|clatter|shatter",
       "ゴクリ": r"gulp|swallow", "ザーッ": r"rain|pour|patter|hiss|whoosh|shh|splash",
       "シーン": r"silen|quiet|still|hush|\.\.\.|…", "バタン": r"slam|bang|thud|wham|thump",
       "ニコッ": r"smil|grin", "ドン": r"boom|bang|thud|thump|bam|whump|wham",
       "キラキラ": r"sparkl|glitter|twinkl|shin|glint|gleam",
       "ゴゴゴ": r"rumbl|menac|loom|ominous", "パチパチ": r"clap|crackl|applau|blink", "コンコン": r"knock",
       "ガラッ": r"slid|rattl|clatter|open|swish", "ピンポーン": r"ding|doorbell|chime|bell",
       "ブルブル": r"shiver|trembl|shak|quiver|brr", "ワクワク": r"excit|thrill|eager", "ジーッ": r"star|gaz|buzz|whir",
       "ペコリ": r"bow", "ズキズキ": r"throb|ache|pain|sting|pulse", "フワフワ": r"fluff|float|soft|drift",
       "スヤスヤ": r"sleep|z{2,}|snor|slumber", "ポロポロ": r"tear|drip|crumbl|trickl|fall|drop",
       "ザワザワ": r"murmur|chatter|buzz|rustl|commotion|stir|whisper", "ガタガタ": r"rattl|shak|clatter|trembl|jolt"}
SIGNS = {"立入禁止": r"no (entry|trespass|admittance)|keep out|do not enter|off.?limits|restricted",
         "本日休業": r"closed", "出口": r"exit|way out", "職員室": r"staff|teachers|faculty",
         "営業中": r"open", "非常口": r"emergency|exit", "2年A組": r"2-?A|class|year", "駐車禁止": r"no parking|parking"}
LINES = ([(ja, "speech") for ja in SPEECH] + [(ja, "thought") for ja in THOUGHT]
         + [(ja, "narration") for ja in NARRATION] + [(ja, "shout") for ja in SHOUT]
         + [(ja, "sfx") for ja in SFX] + [(ja, "sign") for ja in SIGNS])
PATTERNS = {**SFX, **SIGNS}
# earlier pairs made up for the test, the lines before a sound word as a page's would be (``position``)
HISTORY = [("おはよう", "Good morning."), ("今日も暑いね", "It's hot again today."), ("宿題やった？", "Did you do the homework?"),
           ("まだ半分しか", "Only half of it."), ("図書館に行こうか", "Shall we go to the library?"),
           ("うん、そうしよう", "Yeah, let's."), ("あれ、鍵がない", "Huh? My key's gone."),
           ("ポケットの中は？", "What about your pocket?"), ("あった！", "Found it!"), ("よかった", "Thank goodness.")]
# ... and in the other target languages measured (``renderings``), by PLaMo's code
HISTORIES = {"en": HISTORY, "fr": list(zip((ja for ja, _en in HISTORY), (
    "Bonjour.", "Il fait encore chaud aujourd'hui.", "Tu as fait tes devoirs ?", "Seulement la moitié.",
    "On va à la bibliothèque ?", "Oui, allons-y.", "Hein ? Ma clé a disparu.", "Et dans ta poche ?", "Je l'ai !",
    "Ouf, tant mieux."))), "zh-hans": list(zip((ja for ja, _en in HISTORY), (
        "早上好。", "今天也好热啊。", "作业做了吗？", "才做了一半。", "我们去图书馆吧？", "嗯，就这么办。", "咦，钥匙不见了。",
        "口袋里呢？", "找到了！", "太好了。")))}
CHAT_BATCH = 20  # words a request of the chat translator (``chat``), as one page's bubbles


def context(condition: str, kind: str, extra: str = "") -> str:
    """The ``context`` block of a line of *kind* under *condition*, joined as `PlamoTranslator._context` joins its
    parts: the standing line first, then the line's own (the kind, then *extra*: a meaning)."""
    parts = [STANDING if condition in ("standing", "both") else "",
             KIND_LINES.get(kind, "") if condition in ("kind", "both") else "", extra]
    return "\n\n".join(p for p in parts if p)


def lettered(base: str) -> str:
    """A base form of the list as a page letters it: one or two sounds with a small tsu after them (ドキッ, ザッ), a
    base that ends long or on ン, or has three sounds or more, as it is."""
    if base[-1] in "ンーッ" or len(soundwords._morae(base)) >= 3:
        return base
    return base + "ッ"


def _letters(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", text.lower()) if "a" <= ch <= "z")


def _key(latin: str) -> str:
    return re.sub(r"(.)\1+", r"\1", latin.replace("h", ""))


def romanised(ja: str, answer: str) -> bool:
    """Whether *answer* is the romanisation of the sound word *ja* (loosely: no h, no letter twice, 0.75 alike or
    more), of the form as lettered or of its skeleton."""
    import jaconv

    ans = _key(_letters(answer))
    if not ans:
        return False
    for form in (ja, soundwords.skeleton(ja)):
        kana = "".join(ch for ch in form if ch not in soundwords.MARKS)
        src = _key(_letters(jaconv.kana2alphabet(jaconv.kata2hira(kana)).replace("xtsu", "")))
        if src and (src in ans or SequenceMatcher(None, ans, src).ratio() >= 0.75):
            return True
    return False


def sort_answer(ja: str, answer: str) -> str:
    """"empty", "copied" (kana in it), "romaji" (`romanised`) or "word"."""
    if not answer.strip():
        return "empty"
    if any("぀" <= ch <= "ヿ" for ch in answer):
        return "copied"
    return "romaji" if romanised(ja, answer) else "word"


def _start(s: Settings, port: int | None) -> bool:
    if not port:
        netguard.install()
        return False
    import openmantra_eval

    openmantra_eval.start_own_ollama(s, port)
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("mode", choices=("lines", "words", "position", "renderings", "chat"))
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--language", action="append", help="target language (words, renderings; default English)")
    ap.add_argument("--conditions", default="", help="the conditions to ask, comma-separated (default: the mode's)")
    ap.add_argument("--out", type=Path, default=Path("sfx_eval.json"))
    ap.add_argument("--show", action="store_true", help="print the answers (made-up text only)")
    ap.add_argument("--start-ollama", type=int, metavar="PORT")
    args = ap.parse_args(argv)
    s = Settings()
    started = _start(s, args.start_ollama)
    try:
        return _run(args, s)
    finally:
        if started:
            from taslation import ollama_start

            ollama_start.finish_all()


def _run(args: argparse.Namespace, s: Settings) -> int:
    got: dict[str, str] = json.loads(args.out.read_text("utf-8")) if args.out.exists() else {}
    seeds = list(range(1, args.seeds + 1))
    languages = args.language or ["English"]
    t0, asked = time.monotonic(), 0
    tokens = {"prompt": 0, "answer": 0}

    def ask(tr, key: str, ja: str, ctx: str, glossary=(), history=()) -> str:
        nonlocal asked
        if key not in got:
            prompt = pfml_prompt(ja, plamo_code(tr.target_language) or "en", ctx, history, glossary)
            try:
                answer = tr._generate(prompt, max(128, 4 * len(ja) + 64), 0)
            except TranslationError:  # (a server that failed once: asked once more, the answers so far kept)
                args.out.write_text(json.dumps(got, ensure_ascii=False, indent=1), "utf-8")
                answer = tr._generate(prompt, max(128, 4 * len(ja) + 64), 0)
            got[key] = " ".join(answer.split())
            asked += 1
            tokens["prompt"] += int(tr.last_stats.get("prompt_eval_count") or 0)
            tokens["answer"] += int(tr.last_stats.get("eval_count") or 0)
        return got[key]

    if args.mode == "lines":
        conditions = args.conditions.split(",") if args.conditions else list(CONDITIONS)
        s.target_language = "English"
        for seed in seeds:
            tr = make_translator(s, PLAMO, seed=seed)
            if not tr.ping():
                print(f"Ollama is not running at {s.ollama_url}")
                return 2
            for ja, kind in LINES:
                for c in conditions:
                    ask(tr, f"lines|{c}|en|{seed}|{ja}", ja, context(c, kind))
            args.out.write_text(json.dumps(got, ensure_ascii=False, indent=1), "utf-8")
        print(f"{asked} requests in {time.monotonic() - t0:.0f} s, prompt tokens {tokens['prompt']}, answer tokens "
              f"{tokens['answer']}")
        report_lines(got, seeds, conditions, args.show)
        return 0
    bases = list(dict.fromkeys(soundwords.BASES.split()))
    if args.mode == "chat":  # the chat translator (Qwen), every third base form, CHAT_BATCH words a request
        from taslation.translate.models import QWEN

        conditions = args.conditions.split(",") if args.conditions else ["none", "kind"]
        sample = bases[::3]
        for language in languages:
            s.target_language = language
            tr = make_translator(s, QWEN, seed=1)
            for c in conditions:
                words = [lettered(b) for b in sample]
                for k in range(0, len(words), CHAT_BATCH):
                    batch = words[k:k + CHAT_BATCH]
                    if all(f"chat|{c}|{language}|1|{ja}" in got for ja in batch):
                        continue
                    meta = [{"kind": "sfx"} if c == "kind" else {} for _ in batch]
                    out = tr.translate_page(batch, meta=meta)
                    asked += 1
                    for ja, a in zip(batch, out):
                        got[f"chat|{c}|{language}|1|{ja}"] = " ".join(str(a or "").split())
                    args.out.write_text(json.dumps(got, ensure_ascii=False, indent=1), "utf-8")
            for c in conditions:
                counts: dict[str, int] = {}
                for b in sample:
                    sort = sort_answer(lettered(b), got.get(f"chat|{c}|{language}|1|{lettered(b)}", ""))
                    counts[sort] = counts.get(sort, 0) + 1
                print(f"chat {language} {c:5s} " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
                      + f" (of {len(sample)})")
        print(f"{asked} requests in {time.monotonic() - t0:.0f} s")
        return 0
    if args.mode == "position":
        conditions = args.conditions.split(",") if args.conditions else ["none", "front", "after"]
        s.target_language = languages[0]
        code = plamo_code(languages[0])
        tr = make_translator(s, PLAMO, seed=1)
        for n, base in enumerate(bases):
            ja = lettered(base)
            if n % 50 == 49:
                args.out.write_text(json.dumps(got, ensure_ascii=False, indent=1), "utf-8")
            for c in conditions:
                key = f"position|{c}|{code}|1|{ja}"
                if key in got:
                    continue
                history = HISTORIES.get(code, HISTORY)
                if c == "after":
                    prompt = late_prompt(ja, code, "", history, context("both", "sfx"))
                else:
                    prompt = pfml_prompt(ja, code, context("both", "sfx") if c == "front" else "", history)
                got[key] = " ".join(tr._generate(prompt, max(128, 4 * len(ja) + 64), 0).split())
                asked += 1
                tokens["prompt"] += int(tr.last_stats.get("prompt_eval_count") or 0)
        args.out.write_text(json.dumps(got, ensure_ascii=False, indent=1), "utf-8")
        for c in conditions:
            counts: dict[str, int] = {}
            for base in bases:
                ja = lettered(base)
                sort = sort_answer(ja, got[f"position|{c}|{code}|1|{ja}"])
                counts[sort] = counts.get(sort, 0) + 1
            print(f"{code} {c:6s} " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
        print(f"{asked} requests in {time.monotonic() - t0:.0f} s")
        return 0
    if args.mode == "words":
        conditions = args.conditions.split(",") if args.conditions else ["none", "kind", "both"]
        for language in languages:
            s.target_language = language
            code = plamo_code(language)
            tr = make_translator(s, PLAMO, seed=1)
            for base in bases:
                ja = lettered(base)
                for c in conditions:
                    ask(tr, f"words|{c}|{code}|1|{ja}", ja, context(c, "sfx"))
            args.out.write_text(json.dumps(got, ensure_ascii=False, indent=1), "utf-8")
            report_words(got, bases, code, conditions, args.show)
        print(f"{asked} requests in {time.monotonic() - t0:.0f} s, prompt tokens {tokens['prompt']}")
        return 0
    meanings = renderings_of()
    for language in languages:
        s.target_language = language
        code = plamo_code(language)
        conditions = (args.conditions.split(",") if args.conditions
                      else ["none", "meaning", "glossary" if code == "en" else "english"])
        tr = make_translator(s, PLAMO, seed=1)
        for n, (base, (english, meaning)) in enumerate(meanings.items()):
            ja = lettered(base)
            if n % 50 == 49:
                args.out.write_text(json.dumps(got, ensure_ascii=False, indent=1), "utf-8")
            for c in conditions:
                ask(tr, f"renderings|{c}|{code}|1|{ja}", ja, *rendering_prompt(c, english, meaning, ja),
                    history=HISTORIES.get(code, ()))
        args.out.write_text(json.dumps(got, ensure_ascii=False, indent=1), "utf-8")
        if args.show:
            for base, (english, meaning) in meanings.items():
                ja = lettered(base)
                print(f"{code} {ja} [{english}] | " + " | ".join(
                    got[f"renderings|{c}|{code}|1|{ja}"] for c in conditions))
    print(f"{asked} requests in {time.monotonic() - t0:.0f} s")
    return 0


def late_prompt(source: str, target: str, front: str, history, late: str, glossary=()) -> str:
    """`pfml_prompt` with a second ``context`` element, *late*, after the earlier pairs (before the glossary and the
    line): what a prompt that carries a line's own part there and *front* alone at its beginning looks like."""
    head = pfml_prompt("", target, front, history)
    cut = head.rindex(TAG + "input")  # (the empty line's input element: the line goes after the late element)
    tail = pfml_prompt(source, target, "", (), glossary)
    tail = tail[tail.index(TAG + "glossary") if glossary else tail.index(TAG + "input"):]
    return head[:cut] + TAG + "context" + MSG + late + tail


def renderings_of() -> dict[str, tuple[str, str]]:
    """The base forms `soundwords.RENDERINGS_TEXT` gives a rendering, each with (English rendering, meaning)."""
    out = {}
    for line in soundwords.RENDERINGS_TEXT.strip().splitlines():
        base, rest = line.split(" ", 1)
        english, meaning = (part.strip() for part in rest.split("|", 1))
        out[base] = (english, meaning)
    return out


def rendering_prompt(condition: str, english: str, meaning: str, ja: str) -> tuple[str, list[tuple[str, str]]]:
    """The ``context`` and the glossary of a sound word under a renderings *condition*: ``none`` (neither), ``both``
    (the standing line and the kind), ``meaning`` (both, the meaning after the kind), ``english`` (the same with the
    English rendering), ``glossary`` (no ``context``, the English rendering as the word's glossary entry)."""
    sfx = KIND_LINES["sfx"].rstrip(".")
    if condition == "none":
        return "", []
    if condition == "meaning":
        return "\n\n".join((STANDING, f"{sfx}: {meaning}.")), []
    if condition == "english":
        return "\n\n".join((STANDING, f"{sfx}: {english} in English.")), []
    if condition == "glossary":
        return "", [(ja, english)]
    return context("both", "sfx"), []


def report_lines(got: dict[str, str], seeds: list[int], conditions: list[str], show: bool) -> None:
    """Per kind: for sound effects and signs the answers that say what the renderings written for them say, for the
    others the answers that differ from the prompt without either (words, case and a final full stop compared)."""
    def same(a: str, b: str) -> bool:
        return a.rstrip(".!?…").strip().lower() == b.rstrip(".!?…").strip().lower()

    kinds = list(dict.fromkeys(k for _ja, k in LINES))
    for kind in kinds:
        rows = [ja for ja, k in LINES if k == kind]
        line = f"{kind:10s} ({len(rows) * len(seeds)} answers a prompt):"
        for c in conditions:
            answers = [(ja, got[f"lines|{c}|en|{s_}|{ja}"]) for s_ in seeds for ja in rows]
            if kind in ("sfx", "sign"):
                ok = sum(bool(re.search(PATTERNS[ja], a, re.I)) for ja, a in answers)
                roman = sum(romanised(ja, a) for ja, a in answers) if kind == "sfx" else 0
                line += f"  {c}: right {ok}" + (f", romaji {roman}" if kind == "sfx" else "")
            elif c != "none":
                changed = sum(not same(a, got[f"lines|none|en|{s_}|{ja}"])
                              for s_ in seeds for ja, a in [(j, got[f"lines|{c}|en|{s_}|{j}"]) for j in rows])
                line += f"  {c}: changed {changed}"
        print(line)
    if show:
        for ja, kind in LINES:
            for s_ in seeds:
                answers = [got[f"lines|{c}|en|{s_}|{ja}"] for c in conditions]
                if kind in ("sfx", "sign") or len({a.rstrip('.!?').lower() for a in answers}) > 1:
                    print(f"  {kind} {s_} {ja}: " + " | ".join(f"{c}: {a}" for c, a in zip(conditions, answers)))


def report_words(got: dict[str, str], bases: list[str], code: str, conditions: list[str], show: bool) -> None:
    """The words' answers into *code* sorted (`sort_answer`), per condition; with *show* every answer."""
    for c in conditions:
        counts: dict[str, int] = {}
        for base in bases:
            ja = lettered(base)
            sort = sort_answer(ja, got[f"words|{c}|{code}|1|{ja}"])
            counts[sort] = counts.get(sort, 0) + 1
        print(f"{code} {c:8s} " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) + f" (of {len(bases)})")
    if show:
        for base in bases:
            ja = lettered(base)
            print(f"{code} {ja} | " + " | ".join(
                f"{got[f'words|{c}|{code}|1|{ja}']} [{sort_answer(ja, got[f'words|{c}|{code}|1|{ja}'])[0]}]"
                for c in conditions))


if __name__ == "__main__":
    raise SystemExit(main())
