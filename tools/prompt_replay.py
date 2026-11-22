"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: how much of every translation request the server can take from the
request before it, on the OpenMantra pages (``fetch_openmantra.py``), counted without a model.

The PLaMo translator's server keeps the tokens of the last request it computed, its prompt and the answer it wrote,
and reuses them for the next request as far as that one begins with them (`translate.base`, "earlier pairs that only
grow"). This tool runs the gold Japanese of the pages through the app's own translating path, as
``openmantra_eval.py`` does in its official arm: page by page (`Pipeline._translate_regions`, what a reader runs;
``--mode page``, the only one, is still taken).
The model's call is a stand-in (`Recorder`) that answers every line with the professional English of OpenMantra
(``--answers gold``), so that nothing needs Ollama, or the real model through the server (``--answers live``: Ollama's
own counters of every request are read then, and set beside the counts; nothing else changes). For every request it
says how far its prompt extends the previous request's prompt and answer, and when it does not, why (the first
element that differs):

* ``first of book``: the first request (of a series: every series is a book of its own);
* ``context block``: the ``context`` element differs (the Japanese that follows a line, a speaker, a hint);
* ``history cut``: the earlier pairs no longer begin with the same pair (`GrowingContext` cut them back, or the prompt
  was cut to fit);
* ``glossary``: the request before carried a ``glossary``, which sits between its earlier pairs and its line, and its
  pair comes back without it;
* ``joined run``: the request before asked a run of bubbles as one text; its pairs come back one by one;
* ``answer changed``: the earlier pair holds another translation than the answer the server wrote (respelt, set
  differently, its spaces made one);
* ``line not kept``: the line asked before is not the next earlier pair (its answer was not used, or another came);
* ``pair changed``: an earlier pair inside the history differs (a line filled by asking again, put in its place);
* ``re-ask``, ``romanised``, ``aside``: a request beside the main ones (`ask_for_missing`, `ask_again_romanised`,
  `PlamoTranslator.translate_aside`), with a history of its own; and ``after re-ask`` (and so on): a main request that
  would have extended the main request before it, had the request beside it not come in between;
* ``warm`` (``--warm``): a step of the warming the window does while the reader reads
  (`Pipeline.warm_soon`, `PlamoTranslator.warm_prefix`), done here after every page; it is never one of the main
  requests, and ``main_prompts`` says whether those are the very same with it and without it (their number and a
  digest of their prompts in their order; with ``--answers gold`` they must be).

Tokens are reckoned as the translator reckons them (`plamo.tokens_about`, high); two estimates are given of what the
server computes: ``tail`` (it keeps the common beginning and computes the rest) and ``whole`` (a prompt that
differs anywhere is computed from its start). With ``--answers live`` the server's own durations show which of the
two it does (``prompt_eval_count`` is the whole prompt either way): measured on 2026-11-20 (docs/OFFLINE_VERIFICATION.md,
"What a PLaMo request costs the server"), the tail for a prompt that parts from the last one within its last few
pairs, the whole for one that parts further back or in its ``context``.

Prints counts and token estimates only; ``--out`` writes the same numbers as JSON. No text of a page is written or
printed anywhere: the prompts and answers stay in memory, the last two at a time.

    python tools/prompt_replay.py                                  # every series, gold answers
    python tools/prompt_replay.py --series balloon_dream
    python tools/prompt_replay.py --answers live --pages 4 --seed 1 --url http://127.0.0.1:11435 --out live.json
    python tools/prompt_replay.py --warm                           # the warming between pages: the same prompts?
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import openmantra  # noqa: E402
import openmantra_eval as ev  # noqa: E402
from taslation import netguard  # noqa: E402
from taslation.config import Settings  # noqa: E402
from taslation.translate import plamo as pl  # noqa: E402

SIDE_KINDS = ("re-ask", "romanised", "aside", "warm")


# ------------------------------------------------------------------------------------------- a prompt's parts
@dataclass
class Shape:
    """A PFML3 prompt (`plamo.pfml_prompt`) in its parts, with where each begins: the ``context``, the earlier pairs,
    the ``glossary`` and the line."""

    prompt: str
    context: str = ""
    pairs: list[tuple[str, str]] = field(default_factory=list)
    glossary: str = ""
    source: str = ""
    # (start, end, part) of every element of the prompt, part: "head", "context", ("pair", j), "glossary", "line"
    spans: list[tuple[int, int, Any]] = field(default_factory=list)


def _msg(element: str) -> str:
    return element.split(pl.MSG, 1)[1] if pl.MSG in element else ""


def shape_of(prompt: str) -> Shape:
    """*prompt* taken apart (see `Shape`)."""
    s = Shape(prompt)
    elements = prompt.split(pl.TAG)
    at = len(elements[0])
    parts: list[tuple[int, int, str]] = []
    for e in elements[1:]:
        start = at
        at += len(pl.TAG) + len(e)
        parts.append((start, at, e))
    i = 0
    if parts and parts[0][2].startswith("dataset"):
        s.spans.append((0, parts[0][1], "head"))
        i = 1
    if i < len(parts) and parts[i][2].startswith("context"):
        s.context = _msg(parts[i][2])
        s.spans.append((parts[i][0], parts[i][1], "context"))
        i += 1
    rest = parts[i:]
    line_at = len(rest) - 2  # the line: its input and the output left open
    k = 0
    while k < line_at:
        a, b, e = rest[k]
        if e.startswith("input") and k + 1 < line_at and rest[k + 1][2].startswith("output"):
            s.pairs.append((_msg(e), _msg(rest[k + 1][2])))
            s.spans.append((a, rest[k + 1][1], ("pair", len(s.pairs) - 1)))
            k += 2
        elif e.startswith("glossary"):
            s.glossary = e
            s.spans.append((a, b, "glossary"))
            k += 1
        else:
            k += 1
    if line_at >= 0:
        s.source = _msg(rest[line_at][2])
        s.spans.append((rest[line_at][0], len(prompt), "line"))
    return s


def part_at(shape: Shape, pos: int) -> Any:
    """The part of *shape*'s prompt the character *pos* is in ("answer" past its end)."""
    for a, b, part in shape.spans:
        if a <= pos < b:
            return part
    return "answer"


def common(a: str, b: str) -> int:
    """The length of the common beginning of *a* and *b*."""
    n = min(len(a), len(b))
    lo = 0
    step = 1024
    while lo < n:  # (in blocks, then character by character)
        hi = min(n, lo + step)
        if a[lo:hi] == b[lo:hi]:
            lo = hi
            continue
        while lo < hi and a[lo] == b[lo]:
            lo += 1
        return lo
    return lo


# ------------------------------------------------------------------------------------------ what was asked
@dataclass
class Asked:
    """One request: its kind, its prompt (in its parts), what the server wrote, where its line is, and what the
    context element was made of; with ``--answers live`` the server's counters."""

    kind: str
    shape: Shape
    answer: str  # the raw answer, as the server wrote it
    page: tuple[str, int] | None
    ctx: dict[str, Any]
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def state(self) -> str:
        """What the server holds after it: the prompt, then the answer."""
        return self.shape.prompt + self.answer


class Recorder(pl.PlamoTranslator):
    """The PLaMo translator whose model call is recorded (`on_request`), and answered by *answer* (a stand-in: no
    server) or, with *answer* None, by the server itself."""

    def __init__(self, answer: Callable[[str], str] | None, on_request: Callable[[Asked], None],
                 page_of: Callable[[str], tuple[str, int] | None], **kwargs: Any):
        super().__init__(**kwargs)
        self.answer = answer
        self.on_request = on_request
        self.page_of = page_of
        self.side = threading.local()
        self._ctx = threading.local()

    def _context(self, notes: str, speaker: str = "", following: Any = (), hint: str = "") -> str:
        self._ctx.args = {"speaker": bool(speaker), "following": len([t for t in following if str(t).strip()]),
                          "hint": bool(hint)}
        return super()._context(notes, speaker, following, hint)

    def translate_aside(self, *args: Any, **kwargs: Any) -> str:
        self.side.kind = "aside"
        try:
            return super().translate_aside(*args, **kwargs)
        finally:
            self.side.kind = None

    def _generate(self, prompt: str, max_tokens: int, offset: int = 0, cancel: Any = None, on_slow: Any = None) -> str:
        shape = shape_of(prompt)
        side = getattr(self.side, "kind", None)
        kind = side or ("joined" if "\n" in shape.source else "line")
        ctx = dict(getattr(self._ctx, "args", {}) or {})
        self._ctx.args = {}
        first = shape.source.split("\n")[0]
        if self.answer is not None:
            raw = self.answer(shape.source)
            self.on_request(Asked(kind, shape, raw, self.page_of(first), ctx))
            if hasattr(self, "_wrote"):
                self._wrote.text = pl.clean(raw)  # (as `PlamoTranslator._generate` keeps it)
            if hasattr(self, "_held_now"):
                self._held_now(prompt + raw, prompt)  # (what the server would hold: what a warming looks at)
            return "\n".join(" ".join(line.split()) for line in pl.clean(raw).splitlines() if line.strip())
        seen: dict[str, Any] = {}
        request, stream = self._request, self._stream

        def req(path: str, payload: Any = None, timeout: Any = None) -> Any:
            data = request(path, payload, timeout)
            if path == "/api/generate" and payload and payload.get("prompt"):
                seen["raw"] = str(data.get("response") or "")
                seen["data"] = data
            return data

        def strm(path: str, payload: Any, on_text: Any, *a: Any, **k: Any) -> Any:
            data = stream(path, payload, on_text, *a, **k)
            if path == "/api/generate" and payload and payload.get("prompt"):
                seen["raw"] = str((data.get("message") or {}).get("content") or "")
                seen["data"] = data
            return data

        self._request, self._stream = req, strm  # type: ignore[method-assign]
        try:
            got = super()._generate(prompt, max_tokens, offset, cancel, on_slow)
        finally:
            del self._request, self._stream
        stats = {k: (seen.get("data") or {}).get(k) for k in ("prompt_eval_count", "prompt_eval_duration",
                                                              "eval_count", "eval_duration", "total_duration")}
        self.on_request(Asked(kind, shape, str(seen.get("raw", "")), self.page_of(first), ctx, stats))
        return got

    def gpu_share(self, model: Any = None) -> Any:
        return 1.0 if self.answer is not None else super().gpu_share(model)  # (a stand-in: the model "on the GPU")

    def _warm_step(self, prompt: str) -> dict[str, Any]:
        """A step of the warming (`PlamoTranslator.warm_prefix`) recorded as a ``warm`` request: answered by nobody
        with a stand-in (the server would hold its prompt), else sent as the app sends it."""
        if self.answer is not None:
            self._held_now(prompt)
            self.on_request(Asked("warm", shape_of(prompt), "", None, {}))
            return {"ms": 0.0, "prompt_n": None}
        got = super()._warm_step(prompt)
        stats = {"prompt_eval_count": got.get("prompt_n"), "prompt_eval_duration": (got.get("prompt_ms") or 0) * 1e6,
                 "eval_count": got.get("answer_n"), "eval_duration": None, "total_duration": None}
        self.on_request(Asked("warm", shape_of(prompt), "", None, {}, stats))
        return got


CURRENT: list[Recorder] = []  # the recorder of the run under way


def _beside(module: Any, name: str, kind: str) -> None:
    """*module*'s function *name* (`ask_for_missing`, `ask_again_romanised`) marks the requests it makes as *kind*."""
    fn = getattr(module, name)
    if getattr(fn, "_replay", False):
        return

    def marked(*args: Any, **kwargs: Any) -> Any:
        rec = CURRENT[-1] if CURRENT else None
        before = getattr(rec.side, "kind", None) if rec is not None else None
        if rec is not None:
            rec.side.kind = kind
        try:
            return fn(*args, **kwargs)
        finally:
            if rec is not None:
                rec.side.kind = before

    marked._replay = True  # type: ignore[attr-defined]
    setattr(module, name, marked)


# ------------------------------------------------------------------------------------------- why it breaks
def _shifted(cur: list[tuple[str, str]], prev: list[tuple[str, str]]) -> bool:
    """Whether *cur* begins with a later part of *prev* (the pairs cut back, the oldest left out)."""
    return any(cur[:len(prev) - s] == prev[s:] for s in range(1, len(prev)))


def why(cur: Asked, prev: Asked) -> tuple[str, str]:
    """(reason, detail) of the first part where *cur*'s prompt leaves what the server holds after *prev*; ("extends",
    "") when it holds all of it."""
    state = prev.state
    p = common(cur.shape.prompt, state)
    if p >= len(state):
        return "extends", ""
    where = part_at(cur.shape, p)
    held = part_at(prev.shape, p)
    if where == "context" or held == "context":
        what = [k for k in ("following", "speaker", "hint") if cur.ctx.get(k) or prev.ctx.get(k)]
        return "context block", "+".join(what) or "premises"
    cp, pp = cur.shape.pairs, prev.shape.pairs
    j = where[1] if isinstance(where, tuple) else len(cp)
    if j < len(pp) or cp[:len(pp)] != pp:
        if cp[:1] != pp[:1]:  # (the earlier pairs begin otherwise: cut back, or another history altogether)
            return "history cut", "cut back" if _shifted(cp, pp) else "other pairs"
        if j < len(pp) and j < len(cp) and cp[j][0] == pp[j][0]:
            return "pair changed", "translation"
        return "pair changed", "inserted or left out"
    # the pairs of the request before all there: what follows them in its prompt is its glossary and its line
    if prev.shape.glossary:
        return "glossary", ""
    if "\n" in prev.shape.source:
        return "joined run", ""
    if len(cp) <= len(pp):
        return "line not kept", "no new pair"
    src, dst = cp[len(pp)]
    if src != prev.shape.source:
        return "line not kept", "another line"
    answer = pl.clean(prev.answer)
    if dst != answer:
        same = " ".join(dst.split()) == " ".join(answer.split())
        return "answer changed", "spaces" if same else "words"
    return "answer changed", "raw answer"  # (the raw answer's own spaces, which the earlier pair leaves out)


# ------------------------------------------------------------------------------------------- the tally
@dataclass
class Row:
    kind: str
    reason: str
    detail: str
    first_of_page: bool
    tokens: int  # the whole prompt, reckoned high
    new_tail: int  # what the server computes, if it keeps the common beginning
    new_whole: int  # what it computes, if a prompt that differs anywhere is computed from its start
    stats: dict[str, Any]


class Tally:
    """Every request of a run as a `Row`: the request before it kept, and the last main request (for ``after ...``)."""

    def __init__(self) -> None:
        self.rows: list[Row] = []
        self.prev: Asked | None = None
        self.prev_main: Asked | None = None
        self.last_page: tuple[str, int] | None = None
        self.book: str | None = None
        self.lock = threading.Lock()
        self.main_n = 0  # the main requests (no warming step), and a digest of their prompts in their order
        self.main_digest = hashlib.sha256()

    def new_book(self, name: str) -> None:
        """A series begins: its first request is the first of a book (the server holds another book's prompt)."""
        self.book = name
        self.prev = self.prev_main = None
        self.last_page = None

    def add(self, a: Asked) -> None:
        with self.lock:
            prev = self.prev
            main = a.kind not in SIDE_KINDS
            first_of_page = main and a.page is not None and a.page != self.last_page
            tokens = pl.tokens_about(a.shape.prompt)
            if prev is None:
                reason, detail, p = "first of book", "", 0
            else:
                p = common(a.shape.prompt, prev.state)
                reason, detail = why(a, prev)
                if reason != "extends" and a.kind in SIDE_KINDS:
                    detail = reason if not detail else f"{reason}: {detail}"
                    reason = a.kind
                elif (reason != "extends" and main and prev.kind in SIDE_KINDS and self.prev_main is not None
                      and why(a, self.prev_main)[0] == "extends"):
                    reason, detail = f"after {prev.kind}", ""
            extends = prev is not None and p >= len(prev.state)
            new_tail = pl.tokens_about(a.shape.prompt[p:]) if prev is not None else tokens
            new_whole = new_tail if extends else tokens
            self.rows.append(Row(a.kind, reason, detail, first_of_page, tokens, new_tail, new_whole, dict(a.stats)))
            if a.kind != "warm":
                self.main_n += 1
                self.main_digest.update(a.shape.prompt.encode("utf-8") + b"\0")
            self.prev = a
            if main:
                self.prev_main = a
                if a.page is not None:
                    self.last_page = a.page


def summarise(rows: list[Row]) -> dict[str, Any]:
    """The numbers of a run: requests by kind, the reasons with their counts and token estimates, the server's own
    counters by reason when there are any."""
    out: dict[str, Any] = {"requests": len(rows), "kinds": dict(Counter(r.kind for r in rows)),
                           "first_of_page": sum(r.first_of_page for r in rows),
                           "tokens": sum(r.tokens for r in rows), "new_tail": sum(r.new_tail for r in rows),
                           "new_whole": sum(r.new_whole for r in rows)}
    by: dict[str, dict[str, Any]] = defaultdict(lambda: {"requests": 0, "first_of_page": 0, "tokens": 0,
                                                         "new_tail": 0, "new_whole": 0, "details": Counter()})
    for r in rows:
        b = by[r.reason]
        b["requests"] += 1
        b["first_of_page"] += int(r.first_of_page)
        b["tokens"] += r.tokens
        b["new_tail"] += r.new_tail
        b["new_whole"] += r.new_whole
        if r.detail:
            b["details"][r.detail] += 1
    live = [r for r in rows if r.stats.get("prompt_eval_count") is not None]
    if live:
        server: dict[str, Any] = defaultdict(lambda: {"requests": 0, "prompt_eval_count": 0, "prompt_ms": 0.0,
                                                      "eval_count": 0, "eval_ms": 0.0, "new_tail": 0, "new_whole": 0,
                                                      "tokens": 0})
        for r in live:
            s = server[r.reason]
            s["requests"] += 1
            s["prompt_eval_count"] += int(r.stats.get("prompt_eval_count") or 0)
            s["prompt_ms"] += (r.stats.get("prompt_eval_duration") or 0) / 1e6
            s["eval_count"] += int(r.stats.get("eval_count") or 0)
            s["eval_ms"] += (r.stats.get("eval_duration") or 0) / 1e6
            s["new_tail"] += r.new_tail
            s["new_whole"] += r.new_whole
            s["tokens"] += r.tokens
        for s in server.values():
            s["prompt_ms"] = round(s["prompt_ms"], 1)
            s["eval_ms"] = round(s["eval_ms"], 1)
        out["server"] = dict(server)
        # the first request of each page (none beside it): what a turn's first line waits for the prompt
        firsts = sorted((r.stats.get("prompt_eval_duration") or 0) / 1e6 for r in live
                        if r.first_of_page and r.kind not in SIDE_KINDS)
        if firsts:
            out["first_of_page_prompt_ms"] = {"n": len(firsts), "sum": round(sum(firsts)),
                                              "median": round(firsts[len(firsts) // 2], 1), "max": round(firsts[-1]),
                                              "over_500": sum(1 for v in firsts if v > 500),
                                              "slowest": [round(v) for v in firsts[-8:]]}
        out["server_rows"] = [{"reason": r.reason, "kind": r.kind, "first_of_page": r.first_of_page,
                               "tokens": r.tokens, "new_tail": r.new_tail,
                               "new_whole": r.new_whole, **{k: r.stats.get(k) for k in
                                                            ("prompt_eval_count", "prompt_eval_duration",
                                                             "eval_count", "eval_duration", "total_duration")}}
                              for r in live]
    out["reasons"] = {k: {**v, "details": dict(v["details"])} for k, v in sorted(by.items(), key=lambda kv: -kv[1]["requests"])}
    return out


def report(name: str, s: dict[str, Any]) -> str:
    lines = [f"{name}: {s['requests']} requests ({', '.join(f'{k} {v}' for k, v in sorted(s['kinds'].items()))}), "
             f"{s['first_of_page']} first of a page; prompt tokens {s['tokens']:,} in all, the server computes "
             f"{s['new_tail']:,} keeping the common beginning, {s['new_whole']:,} computing a prompt that differs "
             f"anywhere from its start (reckoned high)"]
    lines.append(f"  {'reason':<18}{'requests':>9}{'1st/page':>9}{'tokens':>10}{'new tail':>10}{'new whole':>10}  details")
    for reason, v in s["reasons"].items():
        det = ", ".join(f"{k} {n}" for k, n in sorted(v["details"].items(), key=lambda kv: -kv[1]))
        lines.append(f"  {reason:<18}{v['requests']:>9}{v['first_of_page']:>9}{v['tokens']:>10,}{v['new_tail']:>10,}"
                     f"{v['new_whole']:>10,}  {det}")
    if "server" in s:
        lines.append(f"  server's counters: {'reason':<16}{'requests':>9}{'prompt n':>10}{'ms':>10}{'ms/req':>8}"
                     f"{'tail est':>10}{'whole est':>10}{'gen n':>8}{'gen ms':>9}")
        for reason, v in sorted(s["server"].items(), key=lambda kv: -kv[1]["requests"]):
            lines.append(f"  {'':<19}{reason:<16}{v['requests']:>9}{v['prompt_eval_count']:>10,}{v['prompt_ms']:>10,.0f}"
                         f"{v['prompt_ms'] / max(1, v['requests']):>8.0f}{v['new_tail']:>10,}{v['new_whole']:>10,}"
                         f"{v['eval_count']:>8,}{v['eval_ms']:>9,.0f}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------- the runs
def run_pages(settings: Settings, groups: dict[str, list[openmantra.Page]], answers: str, url: str,
              seed: int | None, lines_most: int, sheets: dict[str, Any] | None = None,
              warm: bool = False) -> dict[str, Any]:
    """Every series page by page (`openmantra_eval.translate_series_page`) with a `Recorder`; the tally's summary.
    *warm*: after every page, the warming the window does while the reader reads (`Pipeline.warm_soon`, waited for)."""
    import taslation.pipeline as pipe_mod

    gold: dict[str, str] = {}
    where: dict[str, tuple[str, int]] = {}
    for pages in groups.values():
        for page in pages:
            for b in page.bubbles:
                ja = ev.ja_line(b)
                if ja:
                    gold.setdefault(ja, " ".join(b.en.split()))
                    where.setdefault(ja, (page.series, page.index))
    tally = Tally()

    def stand_in(source: str) -> str:
        return "\n".join(gold.get(" ".join(line.split()), "") for line in source.split("\n"))

    _beside(pipe_mod, "ask_for_missing", "re-ask")
    _beside(pipe_mod, "ask_again_romanised", "romanised")
    rec = Recorder(stand_in if answers == "gold" else None, tally.add, where.get, url=url, seed=seed,
                   target_language=settings.target_language)
    CURRENT.append(rec)
    if answers == "live":
        ev._keep_stats(rec)
    extra: dict[str, Any] = {}
    if warm:
        def warmed(pipeline: Any) -> None:
            if pipeline.warm_soon() and pipeline._warm_thread is not None:
                pipeline._warm_thread.join()

        extra["between"] = warmed
    stats = ev._Stats()
    t0 = time.monotonic()
    done = 0
    for name, pages in groups.items():
        if lines_most and done >= lines_most:
            break
        tally.new_book(name)
        rec._asked.clear()  # (each series drawn as a book of its own)
        geos = [[None] * len(p.bubbles) for p in pages]
        ev.translate_series_page(settings, rec, name, pages, geos, stats, lambda _m: None, None,
                                 (sheets or {}).get(name), **extra)
        done += sum(1 for p in pages for b in p.bubbles if ev.ja_line(b))
    out = summarise(tally.rows)
    out["main_prompts"] = {"requests": tally.main_n, "digest": tally.main_digest.hexdigest()[:16]}
    out["seconds"] = round(time.monotonic() - t0, 1)
    out["lines"] = done
    out["requests_failed"] = stats.requests_failed
    out["pages_incomplete"] = stats.left_incomplete
    if answers == "live":
        try:
            rec.release_now()
        except Exception:  # noqa: BLE001 - the model let go as far as the server lets it
            pass
    return out


def main(argv: list[str] | None = None) -> int:
    netguard.install()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=openmantra.DEFAULT_ROOT, help="the dataset folder")
    ap.add_argument("--series", action="append", help="only this series (repeatable)")
    ap.add_argument("--pages", type=int, default=0, help="only the first N pages of every series")
    ap.add_argument("--mode", choices=("page",), default="page",
                    help="page: page by page, as reading translates (the only one)")
    ap.add_argument("--answers", choices=("gold", "live"), default="gold",
                    help="gold: the professional English, no server (default); live: the model through the server")
    ap.add_argument("--url", default="http://127.0.0.1:11434", help="the Ollama server (--answers live)")
    ap.add_argument("--seed", type=int, help="the sampling seed (--answers live)")
    ap.add_argument("--lines", type=int, default=0, help="stop after the series that reach about N lines")
    ap.add_argument("--glossary", type=Path, help="a series sheet per series, as openmantra_eval.py takes it")
    ap.add_argument("--out", type=Path, help="the numbers as JSON")
    ap.add_argument("--warm", action="store_true", help="the warming between pages (`Pipeline.warm_soon`)")
    ap.add_argument("--start-ollama", type=int, metavar="PORT",
                    help="--answers live from the Ollama TASlation's own starter starts on this spare port, stopped at "
                         "the end (as `openmantra_eval.py --start-ollama`); --url is left out")
    args = ap.parse_args(argv)
    pages = openmantra.load(args.root, args.series)
    groups = openmantra.by_series(pages)
    if args.pages:
        groups = {k: v[:args.pages] for k, v in groups.items()}
    s = Settings()
    s.ollama_url = args.url
    s.validate()  # (loopback only)
    if args.start_ollama:
        ev.start_own_ollama(s, args.start_ollama)  # (its port the only one besides: `netguard`)
        args.url = s.ollama_url
        try:
            return _run(args, s, groups)
        finally:
            from taslation import ollama_start

            ollama_start.finish_all()  # (the server it started stopped)
    netguard.install(allowed_ports={s.ollama_port})
    return _run(args, s, groups)


def _run(args: argparse.Namespace, s: Settings, groups: dict[str, list[openmantra.Page]]) -> int:
    sheets = ev.load_glossary(args.glossary, s.target_language)
    results: dict[str, Any] = {"tool": "prompt_replay", "answers": args.answers, "warm": args.warm,
                               "series": list(groups),
                               "pages": sum(len(v) for v in groups.values()), "sheets": sorted(sheets), "modes": {}}
    got = run_pages(s, groups, args.answers, args.url, args.seed, args.lines, sheets, warm=args.warm)
    results["modes"]["page"] = got  # (the place of the numbers as before, when a second mode stood beside it)
    print(report("page mode", got), flush=True)
    print(f"  main requests {got['main_prompts']['requests']}, their prompts' digest "
          f"{got['main_prompts']['digest']}", flush=True)
    if got.get("first_of_page_prompt_ms"):
        print(f"  a page's first request, the server's prompt time (ms): {got['first_of_page_prompt_ms']}", flush=True)
    print(f"  ({got['lines']} lines, {got['seconds']} s, {got['requests_failed']} requests failed, "
          f"{got['pages_incomplete']} pages incomplete)\n", flush=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(results, indent=1), encoding="utf-8")
        print(f"results: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
