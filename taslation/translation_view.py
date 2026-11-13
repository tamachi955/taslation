"""What the window shows while a whole-book run translates: the page whose lines the model is answering, from the run's
page images in memory (`pageimages.PageImages`), each line lettered in its bubble as the model answers it, the lines
still to come outlined on the page as it was captured, and the view moving on with the requests.

`TranslationView` is told what the run's translation does, on the run's own thread, and only notes it there (a lock
and a list), so that the translation never waits for a picture:

* `request` (units): a request to the model starts with these page units: the view goes to the page of the first;
* `line` (unit, index, Japanese, text, speaker): the model answered a line (``on_item``: PLaMo line by line, Ollama as
  its reply streams). Spelt as the series sheet spells (*spell*, the batch's `_spelt_right`, no model request) and
  lettered when it is a real translation; the view goes to its page when it is on another;
* `stored` (unit, texts): the unit's lines are stored (`Pipeline.commit_unit`): the page starts again from the cache's
  picture of it (`Pipeline.page_picture`), so that the provisional lines give way to the stored ones;
* `ended` (seq): the page's translation is over (`page_stage` translate done or failed): no line of it is waited for,
  and a line of it never stored (its request failed) goes: the page is the cache's picture.

A thread of its own, at a lower priority, letters (`pipeline.PageDraft`: only the lines not lettered yet, the erase
taken from the run's erase ahead) and tells the window ``translation_page`` {seq, frame, image, waiting}: *frame* the
page as it was captured (Show original), *image* the page with what is lettered so far (a picture of its own each
time), *waiting* the boxes of its lines not answered yet; *image* None when no image of the page is held any more
(the memory cap made room: the window shows what it showed before). Told when the view comes to a page and after
every change, at most every `GAP_S`, the changes meanwhile together; a page the view leaves is told once more first, as
it is then. The view goes where the run's requests and answers go, never back by itself. Once nothing of a page is
left provisional its picture is the cache's (`Pipeline.page_picture`), exactly: the cache is read under the run's lock
(*storing*), the lettering done without it. Nothing here is stored or written anywhere, nothing is logged: the
pictures go from memory to the window's memory, and `close` ends the thread (the end of the translation: what was
told before is shown first; Stop: at once), what was provisional with it."""

from __future__ import annotations

import threading
import time
from contextlib import nullcontext
from typing import Any, Callable, ContextManager, Sequence

from .pageimages import PageImages
from .pipeline import PageDraft, ScannedUnit
from .render import balance_marks

GAP_S = 0.2  # s: the window is told at most this often (`batch.LINE_SAID_S`, as the band's line count)
JOIN_S = 5.0  # s: `close` waits this long for a picture being lettered


class TranslationView:
    """See the module's docstring. *show*(kind, data) is the window's (the batch's ``show``); *seq_of* gives the page
    (its run number) of a unit; *spell*(japanese, text, speaker) the text as the series sheet spells it; *storing* a
    lock the run holds while it stores, which the view holds only while it takes what the cache holds for a page (not
    while it letters: `PageDraft.restart`); *priority* is called first on the view's thread (the batch's
    `lower_priority`)."""

    def __init__(self, pipeline: Any, images: PageImages, show: Callable[[str, dict[str, Any]], None],
                 units: Sequence[ScannedUnit], seq_of: Callable[[ScannedUnit], int],
                 spell: Callable[[str, str, str], str] | None = None, storing: ContextManager[Any] | None = None,
                 priority: Callable[[], Any] | None = None, gap_s: float | None = None):
        self.pipeline, self.images, self.show = pipeline, images, show
        self.seq_of = seq_of
        self.spell = spell
        self.storing = storing if storing is not None else nullcontext()
        self.priority = priority
        self.gap_s = GAP_S if gap_s is None else gap_s
        self.pages: dict[int, list[ScannedUnit]] = {}  # seq -> its units to translate, in the book's order
        for unit in units:
            seq = seq_of(unit)
            if seq > 0:
                self.pages.setdefault(seq, []).append(unit)
        self._jobs: list[tuple[Any, ...]] = []
        self._cond = threading.Condition()
        self._closed = False
        self._dropped = False  # closed at Stop: nothing more is shown
        # what the run has told, kept on the view's thread: the lines answered and not stored, by unit (id), the lines
        # stored, the pages over
        self._said: dict[int, dict[int, str]] = {}
        self._kept: dict[int, set[int]] = {}
        self._over: set[int] = set()
        self.seq = 0  # the page on show (0: none yet)
        self.draft: PageDraft | None = None
        self.told = 0  # pictures told to the window
        self.lettered_s = 0.0  # seconds spent lettering and telling (for the measurement)
        self.thread = threading.Thread(target=self._loop, name="batch-translation-view", daemon=True)
        self.thread.start()

    # ------------------------------------------------------------------ told by the run (its thread)
    def request(self, units: Sequence[ScannedUnit]) -> None:
        self._put(("request", tuple(units)))

    def line(self, unit: ScannedUnit, index: int, japanese: str, text: str, speaker: str = "") -> None:
        self._put(("line", unit, index, japanese, text, speaker))

    def stored(self, unit: ScannedUnit, texts: dict[int, str]) -> None:
        self._put(("stored", unit, dict(texts)))

    def ended(self, seq: int) -> None:
        self._put(("ended", seq))

    def close(self, finish: bool = True) -> None:
        """The translation is over: what was told before is shown (*finish*: the last page as stored), then the
        thread ends, what was provisional with it; nothing is told after. Stopped (*finish* False): it ends at once."""
        with self._cond:
            self._closed = True
            if not finish:
                self._jobs, self._dropped = [], True
            self._cond.notify_all()
        if threading.current_thread() is not self.thread:
            self.thread.join(JOIN_S)

    def _put(self, job: tuple[Any, ...]) -> None:
        with self._cond:
            if not self._closed:
                self._jobs.append(job)
                self._cond.notify_all()

    # ------------------------------------------------------------------ the view's thread
    def _loop(self) -> None:
        if self.priority is not None:
            self.priority()
        due = 0.0  # when the window may be told next
        dirty = False  # the page on show changed since the window was last told
        while True:
            with self._cond:
                while not self._jobs and not self._closed:
                    if dirty and time.monotonic() >= due:
                        break
                    self._cond.wait(max(0.0, due - time.monotonic()) if dirty else None)
                last = self._closed  # closed: what is noted is shown at once, and that is all
                if last and (self._dropped or not (self._jobs or dirty)):
                    return
                jobs, self._jobs = self._jobs, []
            began = time.monotonic()
            try:
                dirty = self._apply(jobs, dirty)
                if dirty and (last or time.monotonic() >= due):
                    self._tell()
                    dirty = False
                    due = time.monotonic() + self.gap_s
            except Exception:  # noqa: BLE001 - a picture that cannot be made costs only the picture: the band goes on
                dirty = False
            self.lettered_s += time.monotonic() - began
            if last:
                return

    def _apply(self, jobs: list[tuple[Any, ...]], dirty: bool = False) -> bool:
        """What the run told, in its order: the lines noted, the page on show changed, the new lines lettered; a page
        left for another is told first as it is then (its last lines, or as stored), once. True when the window has
        something new to be told (*dirty*: it had before)."""
        changed, letter = dirty, False

        def go(seq: int) -> None:
            nonlocal changed, letter
            if self.draft is not None and self.seq:
                if letter:
                    changed = self.draft.letter(self._lines(self.seq)) or changed
                if changed:
                    self._tell()
            self._go(seq)
            changed, letter = True, True

        for job in jobs:
            kind = job[0]
            if kind == "request":
                first = next((self.seq_of(u) for u in job[1] if self.seq_of(u) in self.pages), 0)
                if first and first != self.seq:
                    go(first)
            elif kind == "line":
                _kind, unit, index, japanese, text, speaker = job
                seq = self.seq_of(unit)
                text = self._usable(japanese, text, speaker)
                if seq not in self.pages or not text:
                    continue
                if seq != self.seq:
                    go(seq)
                self._said.setdefault(id(unit), {})[index] = text
                letter = True
            elif kind == "stored":
                # every line answered so far gives way to what is stored (a line asked for again after this comes
                # after this, in the run's order): the page is the cache's again
                _kind, unit, texts = job
                self._said.pop(id(unit), None)
                self._kept.setdefault(id(unit), set()).update(i for i, t in texts.items() if (t or "").strip())
                if self.seq_of(unit) == self.seq and self.draft is not None:
                    self.draft.restart()
                    changed, letter = True, True
            elif kind == "ended":
                # (a line of a request that failed and was never stored goes too: the page is the cache's)
                seq = job[1]
                self._over.add(seq)
                left = [u for u in self.pages.get(seq, []) if self._said.pop(id(u), None)]
                if seq == self.seq and self.draft is not None:
                    if left:
                        self.draft.restart()
                        letter = True
                    changed = True
        if letter and self.draft is not None:
            changed = self.draft.letter(self._lines(self.seq)) or changed
        return changed

    def _usable(self, japanese: str, text: str, speaker: str) -> str:
        """*text* as it is lettered: spelt as the series sheet spells, its emphasis marks paired; "" when it is no real
        translation of *japanese* (a line copied, nothing): such a line stays outlined."""
        text = (text or "").strip()
        if self.spell is not None and text:
            text = self.spell(japanese, text, speaker)
        text = balance_marks(text).strip()
        return text if text and self.pipeline.real_translation(japanese, text) else ""

    def _go(self, seq: int) -> None:
        """The page *seq* on show from now on, as the cache letters it, its lines answered so far lettered after."""
        self.seq = seq
        self.draft = PageDraft(self.pipeline, self.images, seq, self.storing)

    def _lines(self, seq: int) -> list[tuple[ScannedUnit, dict[int, str]]]:
        return [(u, self._said[id(u)]) for u in self.pages.get(seq, []) if self._said.get(id(u))]

    def waiting(self, seq: int) -> list[tuple[int, int, int, int]]:
        """The boxes of the lines of page *seq* neither answered nor stored, while its translation is not over."""
        if seq in self._over:
            return []
        out = []
        for unit in self.pages.get(seq, []):
            said, kept = self._said.get(id(unit), {}), self._kept.get(id(unit), set())
            out += [tuple(r.bbox) for i, r in enumerate(unit.japanese()) if i not in said and i not in kept]
        return out  # type: ignore[return-value]

    def _tell(self) -> None:
        """The window told the page on show as it is now (not after a `close` at Stop)."""
        draft = self.draft
        if draft is None or not self.seq:
            return
        image = draft.image()
        data: dict[str, Any] = {"seq": self.seq, "frame": draft.frame if image is not None else None, "image": image,
                                "waiting": self.waiting(self.seq) if image is not None else []}
        with self._cond:
            if self._dropped:
                return
        self.show("translation_page", data)
        self.told += 1


__all__ = ["GAP_S", "TranslationView"]
