"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: the name consistency helper (`taslation.name_variants`) on OpenMantra.

Per series of OpenMantra (``~/.taslation/datasets/openmantra``, CC BY-NC 4.0, fetched by ``fetch_openmantra.py``),
the gold Japanese lines with a translation are handed to `find_variants` as a whole-book run hands its lines over:

* by default: the professional English. A translation kept consistent by its editor: what the helper
  offers here is mostly what it should not offer.
* ``--translate``: the app's translator (as ``openmantra_eval.py --mode book --geometry gold`` translates: the
  whole-book batch's own translation pass), the run whose inconsistencies the helper is for.

It prints counts: the names found before an honorific, the names offered (rendered in more than one way) and their
renderings, per series. ``--show`` also prints, to this console only, each name offered with its renderings and
their counts, for a developer's judgement of whether the offer is right; nothing of it is written anywhere.
``--keep FILE`` writes the model's lines to FILE (outside the repository: a scratch folder) so that the helper can
be tuned without translating again (``--lines FILE`` reads them back); delete it afterwards.

``--inject`` measures the helper where a translation is known to be inconsistent: in every series, each name found
before an honorific whose lines have one rendering (a capitalised word on 60 % of them or more, romaji-like for a
name in kanji) gets a second spelling of it (``Tsubasa`` -> ``Tubasa``, ``Ichikawa`` -> ``Ichigawa``, ``Lena`` ->
``Rena``) on every other line of the series that has it, as a translator that spells a name two ways does; it counts
the names given one, the ones offered with exactly the two spellings, the ones offered otherwise, and the offers of a
name not given one (each a wrong offer). ``--shuffle N`` runs the helper N times per series on its translations
shuffled among its lines (all of them, half, a quarter): where it offers nothing on the lines as they are, every
offer on them shuffled is a wrong one.

    python tools/names_eval.py                        # the professional English, counts only
    python tools/names_eval.py --translate --keep %TEMP%/om_lines.json
    python tools/names_eval.py --lines %TEMP%/om_lines.json --show
    python tools/names_eval.py --lines %TEMP%/om_lines.json --inject
    python tools/names_eval.py --lines %TEMP%/om_lines.json --shuffle 20

Nothing goes over the network but the local Ollama server (the socket guard is installed first)."""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import openmantra  # noqa: E402
from taslation import netguard  # noqa: E402
from taslation.config import Settings  # noqa: E402
from taslation.name_variants import (NOT_RENDERINGS, RunLine, _capitalised, _honorific_names, _key,  # noqa: E402
                                     _words, find_variants, romaji_like, unify_text)
from taslation.terms import fold_kana  # noqa: E402


def gold_lines(pages: list[openmantra.Page]) -> list[RunLine]:
    from openmantra_eval import ja_line

    return [RunLine(ja_line(b), " ".join(b.en.split()), (p.index, i)) for p in pages for i, b in enumerate(p.bubbles)
            if ja_line(b) and b.en.strip()]


def model_lines(settings: Settings, translator: Any, series: str, pages: list[openmantra.Page]) -> list[RunLine]:
    from openmantra_eval import _Stats, ja_line, translate_series_book

    geos = [[None] * len(p.bubbles) for p in pages]
    outs = translate_series_book(settings, translator, series, pages, geos, _Stats(), lambda m: print(m, flush=True))
    return [RunLine(ja_line(b), out[i][0], (p.index, i)) for p, out in zip(pages, outs)
            for i, b in enumerate(p.bubbles) if i in out and ja_line(b)]


def honorific_names(lines: list[RunLine]) -> int:
    from taslation.name_variants import NAME_MIN_HONORIFIC, _honorific_names

    seen: dict[str, set[int]] = {}
    for i, line in enumerate(lines):
        for name in _honorific_names(line.source):
            seen.setdefault(fold_kana(name), set()).add(i)
    return sum(1 for at in seen.values() if len(at) >= NAME_MIN_HONORIFIC)


# second spellings of a name in romaji, the first that applies: what a translation gives one name on another page
SECOND_SPELLINGS = (("kawa", "gawa"), ("shi", "si"), ("tsu", "tu"), ("chi", "ti"), ("ji", "zi"), ("l", "r"),
                    ("r", "l"), ("ou", "o"), ("o", "ou"), ("e", "ee"))


def second_spelling(word: str) -> str | None:
    low = word.lower()
    for a, b in SECOND_SPELLINGS:
        if a in low:
            new = low.replace(a, b, 1)
            return new[0].upper() + new[1:]
    return None


def inject(lines: list[RunLine]) -> tuple[list[RunLine], dict[str, set[str]]]:
    """*lines* with a second spelling of each name's rendering on every other line of the name (see ``--inject``),
    and per name (folded) the two spellings (keys)."""
    from taslation.name_variants import NAME_MIN_HONORIFIC

    at_honorific: dict[str, set[int]] = {}
    for i, line in enumerate(lines):
        for name in _honorific_names(line.source):
            at_honorific.setdefault(fold_kana(name), set()).add(i)
    out = list(lines)
    given: dict[str, set[str]] = {}
    for key, at in at_honorific.items():
        if len(at) < NAME_MIN_HONORIFIC:
            continue
        mine = [i for i, line in enumerate(lines) if key in fold_kana(line.source)]
        words: dict[str, int] = {}
        for i in mine:
            for k in {_key(w) for w, _s, _e in _words(lines[i].text) if _capitalised(w)}:
                words[k] = words.get(k, 0) + 1
        kanji = not any("ぁ" <= ch <= "ゟ" for ch in key)
        fit = [k for k, n in words.items() if n >= 0.6 * len(mine) and k not in NOT_RENDERINGS and len(k) >= 2
               and (romaji_like(k) or not kanji)]
        if len(fit) != 1:
            continue  # no one rendering (or two words on every line): nothing known to put a second spelling of
        rendering = fit[0]
        other = second_spelling(rendering)
        if other is None or any(_key(w) == _key(other) for line in lines for w, _s, _e in _words(line.text)):
            continue
        with_it = [i for i in range(len(lines)) if rendering in {_key(w) for w, _s, _e in _words(lines[i].text)}]
        for i in with_it[1::2]:
            spelled = next(w for w, _s, _e in _words(out[i].text) if _key(w) == rendering)
            out[i] = out[i]._replace(text=unify_text(out[i].text, [spelled], other))
        given[key] = {rendering, _key(other)}
    return out, given


def shuffled_offers(lines: list[RunLine], runs: int, seed: int = 7) -> tuple[int, int]:
    """How many names the helper offers on *lines* with their translations shuffled among them (all, half, a
    quarter of the lines; *runs* times each): (runs made, offers). On lines it offers nothing for as they are, every
    offer is a wrong one."""
    rng = random.Random(seed)
    made = offers = 0
    for share in (1.0, 0.5, 0.25):
        for _ in range(runs):
            texts = [line.text for line in lines]
            picked = [i for i in range(len(texts)) if rng.random() < share]
            moved = [texts[i] for i in picked]
            rng.shuffle(moved)
            for i, text in zip(picked, moved):
                texts[i] = text
            offers += len(find_variants([line._replace(text=t) for line, t in zip(lines, texts)]))
            made += 1
    return made, offers


def main(argv: list[str] | None = None) -> int:
    netguard.install()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=openmantra.DEFAULT_ROOT)
    ap.add_argument("--series", action="append")
    ap.add_argument("--translate", action="store_true", help="the app's translator's lines, not the professional ones")
    ap.add_argument("--keep", type=Path, help="write the model's lines here (a scratch file outside the repository)")
    ap.add_argument("--lines", type=Path, help="read the model's lines from a file --keep wrote")
    ap.add_argument("--show", action="store_true", help="print each name offered and its renderings (this console only)")
    ap.add_argument("--inject", action="store_true", help="a second spelling of each name on every other line of it")
    ap.add_argument("--shuffle", type=int, default=0, metavar="N", help="N runs per series and share, lines shuffled")
    args = ap.parse_args(argv)
    groups = openmantra.by_series(openmantra.load(args.root, args.series))
    per_series: dict[str, list[RunLine]] = {}
    if args.lines:
        kept = json.loads(args.lines.read_text(encoding="utf-8"))
        per_series = {name: [RunLine(s, t, tuple(w)) for s, t, w in rows] for name, rows in kept.items()}
    elif args.translate:
        from taslation import health
        from taslation.translate.models import choose, make_translator

        s = Settings()
        model = choose(s.ollama_model, s.target_language, health.installed_models(s.ollama_url)).name
        translator = make_translator(s, model)
        if not translator.ping():
            raise SystemExit(f"Ollama is not running at {s.ollama_url}")
        print(f"translating with {model}", flush=True)
        t0 = time.monotonic()
        for name, pages in groups.items():
            per_series[name] = model_lines(s, translator, name, pages)
        print(f"translated in {time.monotonic() - t0:.0f} s", flush=True)
        if args.keep:
            args.keep.write_text(json.dumps({k: [list(r) for r in v] for k, v in per_series.items()},
                                            ensure_ascii=False), encoding="utf-8")
    else:
        per_series = {name: gold_lines(pages) for name, pages in groups.items()}
    total = offered = renderings = 0
    injected = exact = other = wrong = 0
    shuffled = shuffled_wrong = 0
    for name, lines in per_series.items():
        if args.shuffle:  # (on the lines as they are: a second spelling put in would still be found)
            made, offers = shuffled_offers(lines, args.shuffle)
            shuffled, shuffled_wrong = shuffled + made, shuffled_wrong + offers
        given: dict[str, set[str]] = {}
        if args.inject:
            lines, given = inject(lines)
        variants = find_variants(lines)
        if args.inject:
            injected += len(given)
            for v in variants:
                key, spellings = fold_kana(v.source), {_key(s) for s, _at in v.renderings}
                if key not in given:
                    wrong += 1
                elif spellings == given[key]:
                    exact += 1
                else:
                    other += 1
        names = honorific_names(lines)
        total += names
        offered += len(variants)
        renderings += sum(len(v.renderings) for v in variants)
        print(f"{name}: {len(lines)} lines, {names} names before an honorific, {len(variants)} offered "
              f"({sum(len(v.renderings) for v in variants)} renderings, "
              f"{sum(v.to_change(v.renderings[0][0]) for v in variants)} lines to change to the main one)")
        if args.show:
            for v in variants:
                print("   ", v.source, " / ".join(f"{s} ({n})" for s, n in v.counts()), f"[{len(v.lines)} lines]")
    print(f"all: {sum(len(v) for v in per_series.values())} lines, {total} names, {offered} offered, "
          f"{renderings} renderings")
    if args.inject:
        print(f"given a second spelling: {injected} names; offered with exactly the two: {exact}, offered otherwise: "
              f"{other}, offered without one given: {wrong}")
    if args.shuffle:
        print(f"translations shuffled among the lines: {shuffled} runs, {shuffled_wrong} offers (each a wrong one)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
