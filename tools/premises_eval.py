"""Measure what the reader-made premises do for the local model: the same lines translated with and without them.

The lines in ``premises_eval_set.json`` were written for this test (no book
is involved) and each carries the facts a translator would record (speaker,
kind, continuation) plus the checks a correct translation passes: the right
renderings of names and terms, the right pronoun for a character whose
gender only the sheet knows, honorifics kept, a split sentence left open, a
rough speaker not made polite. Everything runs on the local Ollama server, through the app's translator
(`taslation.translate.models.make_translator`: with ``--model`` left out, the one English is translated with, PLaMo 3
Translate 2B, which takes the sheet as its glossary; ``--model qwen3.5:4b`` for the chat translator).

With --long-sheet N the sheet gets made-up entries in front until it has N, so that the premises block's limits cut
the real ones (characters at half the block, terms at a third), and the lines go page by page (--page-size): the
block alone is scored against the block with the entries each request's lines name after its bubbles.

usage: python tools/premises_eval.py [--runs 2] [--set tools/premises_eval_set.json] [--model NAME]
       python tools/premises_eval.py --long-sheet 200 [--page-size 8] [--runs 2]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from taslation import netguard  # noqa: E402
from taslation.annotations import Glossary, Premises  # noqa: E402
from taslation.config import Settings  # noqa: E402
from taslation.terms import cut_entries, required_renderings  # noqa: E402
from taslation.translate.models import make_translator, wanted_name  # noqa: E402


def passes(check: list[str], text: str) -> bool:
    kind, value = check[0], (check[1] if len(check) > 1 else "")
    if kind == "has":
        return value in text
    if kind == "lacks":
        return value not in text
    if kind == "noword":
        return re.search(r"(?i)\b" + re.escape(value) + r"\b", text) is None
    if kind == "regex":
        return re.search(value, text) is not None
    if kind == "no_end_punct":
        return not text.rstrip().endswith((".", "!", "?", "。", "！", "？"))
    raise ValueError(f"unknown check {kind}")


def score(items: list[dict], outputs: list[str]) -> tuple[int, int, list[str]]:
    passed = total = 0
    failures: list[str] = []
    for item, out in zip(items, outputs):
        for check in item["checks"]:
            total += 1
            if passes(check, out):
                passed += 1
            else:
                failures.append(f"#{item['id']} {check[0]} {check[1] if len(check) > 1 else ''}: {out!r}")
    return passed, total, failures


def long_sheet(sheet: dict, total: int) -> dict:
    """*sheet* with made-up characters and terms in front of its own, half each, *total* entries in all, and without
    the style rules that spell out a rendering (they are never cut, and would tell the model what the test cuts)."""
    own = len(sheet.get("characters", [])) + len(sheet.get("entries", []))
    fill = max(0, total - own)
    made_up = [{"name": f"架空人物{n:03d}", "rendering": f"Filler Name {n}", "role": "a bystander in the test sheet"}
               for n in range(fill // 2)]
    terms = [{"term": f"架空用語{n:03d}", "rendering": f"Filler Term {n}"} for n in range(fill - fill // 2)]
    names = [c["rendering"] for c in sheet.get("characters", [])] + [e["rendering"] for e in sheet.get("entries", [])]
    style = dict(sheet.get("style", {}))
    style["rules"] = [rule for rule in style.get("rules", []) if not any(name in rule for name in names)]
    return {**sheet, "characters": made_up + sheet.get("characters", []), "entries": terms + sheet.get("entries", []),
            "style": style}


def run_pages(tr: Any, items: list[dict], meta: list[dict], notes: str, page_size: int) -> dict:
    """Every page of *items* translated with *notes*: the checks passed, of how many, and the failures."""
    outputs: list[str] = []
    for start in range(0, len(items), page_size):
        page = items[start:start + page_size]
        outputs.extend(tr.translate_page([item["ja"] for item in page], notes=notes, meta=meta[start:start + page_size]))
    passed, total, failures = score(items, outputs)
    return {"passed": passed, "total": total, "failures": failures}


def long_sheet_eval(tr: Any, data: dict, items: list[dict], meta: list[dict], args: argparse.Namespace) -> int:
    padded = long_sheet(data["sheet"], args.long_sheet)
    sheet = Glossary(Path("eval.json"), padded.get("series", "eval"), padded.get("language", "English"))
    sheet.apply_json(padded)
    block = sheet.format()
    wanted = {r for item, m in zip(items, meta) for r in required_renderings(sheet, item["ja"], m.get("speaker", ""))}
    shown = sum(1 for r in wanted if r in block)
    pages = [range(k, min(k + args.page_size, len(items))) for k in range(0, len(items), args.page_size)]
    added = [cut_entries(sheet, block, [items[k]["ja"] for k in page], [meta[k].get("speaker", "") for k in page])
             for page in pages]
    print(f"sheet of {len(sheet.characters) + len(sheet.entries)} entries, block {len(block)} chars; {shown} of "
          f"{len(wanted)} required renderings in the block; {len(pages)} pages, entries after the bubbles per page "
          f"{[len(a) for a in added]}, {max(sum(len(x) + 1 for x in a) for a in added)} chars at most")
    results: dict[str, list[dict]] = {"block alone": [], "with cut entries": []}
    for run in range(args.runs):
        for label, notes in (("block alone", str(block)), ("with cut entries", Premises(block, sheet))):
            t0 = time.monotonic()
            r = run_pages(tr, items, meta, notes, args.page_size)
            results[label].append(r)
            print(f"run {run + 1} {label:17s}: {r['passed']}/{r['total']} checks passed  [{time.monotonic() - t0:.0f}s]")
    print()
    for label, runs in results.items():
        mean = sum(r["passed"] for r in runs) / len(runs)
        print(f"{label:17s}: mean {mean:.1f} of {runs[0]['total']} checks")
        if args.show:
            for line in runs[-1]["failures"]:
                print("  " + line)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--set", type=Path, default=ROOT / "tools" / "premises_eval_set.json")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--model")
    ap.add_argument("--num-ctx", type=int, default=0, help="the chat translator's context (PLaMo has its own)")
    ap.add_argument("--show", action="store_true", help="print every translation")
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--long-sheet", type=int, default=0, metavar="N",
                    help="pad the sheet to N entries with the real ones last; block alone against cut entries added")
    ap.add_argument("--page-size", type=int, default=8, help="lines per request with --long-sheet")
    args = ap.parse_args(argv)
    netguard.install()
    data = json.loads(args.set.read_text(encoding="utf-8"))
    items = data["items"]
    sheet = Glossary(Path("eval.json"), data["sheet"].get("series", "eval"), data["sheet"].get("language", "English"))
    sheet.apply_json(data["sheet"])
    premises = Premises(sheet.format(), sheet)  # as the pipeline gives it: the text, and the sheet behind it
    meta = [{k: item[k] for k in ("speaker", "kind", "continues") if item.get(k)} for item in items]
    texts = [item["ja"] for item in items]
    s = Settings()
    s.target_language = "English"
    if args.temperature is not None:
        s.ollama_temperature = args.temperature
    if args.num_ctx:
        s.ollama_num_ctx = args.num_ctx
    tr = make_translator(s, args.model or wanted_name(s.ollama_model, s.target_language))
    if not tr.ping():
        print(f"Ollama is not running at {s.ollama_url}")
        return 2
    print(f"model {tr.model}; {len(items)} lines, {sum(len(i['checks']) for i in items)} checks, {args.runs} run(s) each")
    if args.long_sheet:
        return long_sheet_eval(tr, data, items, meta, args)
    results: dict[str, list[tuple[int, int]]] = {"without premises": [], "with premises": []}
    last_failures: dict[str, list[str]] = {}
    for run in range(args.runs):
        for label, kwargs in (("without premises", {}), ("with premises", {"notes": premises, "meta": meta})):
            t0 = time.monotonic()
            outputs = tr.translate_page(texts, **kwargs)
            passed, total, failures = score(items, outputs)
            results[label].append((passed, total))
            last_failures[label] = failures
            print(f"run {run + 1} {label:17s}: {passed}/{total} checks passed  [{time.monotonic() - t0:.0f}s]")
            if args.show:
                for item, out in zip(items, outputs):
                    print(f"    #{item['id']:2d} {out}")
    print()
    for label, runs in results.items():
        mean = sum(p for p, _t in runs) / len(runs)
        print(f"{label:17s}: mean {mean:.1f} of {runs[0][1]} checks ({100 * mean / runs[0][1]:.0f}%)")
    for label, failures in last_failures.items():
        if failures:
            print(f"\nlast run, {label}, failed checks:")
            for line in failures:
                print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
