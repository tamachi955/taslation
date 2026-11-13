"""Page units (`fingerprint.analyze`) on real captures of a reader, kept on the developer's machine in
``~/.taslation/dev-snapshots`` (tools/dev_snapshots.py): never shipped, never copied - the tests read the files in
place and skip unless TASLATION_REALDATA=1 and the files are there. Nothing of a page is printed: the assertions
compare boxes, counts and shares of pixels.

* ``2026-10-31-cloud-reader-spread-dark-right-page.png``: a browser-based viewer's spread whose right page is black
  panels in its lower half; the ``.json`` beside it records the capture areas it was read in and the page boxes
  expected. Its right page unit used to stop at the upper panels, and the bubbles below were never read.
* ``<book>/``: the screens of a volume walked by the tool, with the fingerprints analyze gave them then (one
  volume walked in October so far). Its page panel re-fitted into viewports of other sizes stands for the viewer's
  window resized (`_refit`); the book is recognised there by its pages (`bookid.recognise`), never by the pages of
  another screen or of the spread above.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from taslation import fingerprint as fp
from taslation.bookid import page_groups, recognise
from taslation.cache import CachedBubble, CachedPage, CacheIdentity, CacheStore
from taslation.pipeline import Pipeline, _units_before
from taslation.config import Settings
from taslation.detect.page_area import find_page_area, page_area_margins

SNAPSHOTS = Path(Settings().state_dir) / "dev-snapshots"
SPREAD = SNAPSHOTS / "2026-10-31-cloud-reader-spread-dark-right-page.png"
WANTED = os.environ.get("TASLATION_REALDATA") == "1"
VOLUMES = sorted(p.parent for p in SNAPSHOTS.glob("*/manifest.json")) if WANTED and SNAPSHOTS.is_dir() else []
spread_frame = pytest.mark.skipif(not (WANTED and SPREAD.is_file() and SPREAD.with_suffix(".json").is_file()),
                                  reason="the dark-page spread is not in dev-snapshots, or TASLATION_REALDATA is not 1")
volume_frames = pytest.mark.skipif(not VOLUMES,
                                   reason="no walked volume in dev-snapshots, or TASLATION_REALDATA is not 1")


def _rgb(path: Path) -> np.ndarray:
    with Image.open(path) as img:
        return np.asarray(img.convert("RGB"))


def _near(box, expected, tol: int = 12) -> bool:
    return max(abs(a - b) for a, b in zip(box, expected)) <= tol


@spread_frame
def test_a_spread_with_a_dark_right_page_gives_both_pages_whole_in_both_capture_areas():
    """Two units in the window's page panel and in the reader's hand-set area, the right one down to the page's
    foot (its unit stopped at y=623, under the upper panels, and the bubbles below were never read), the left one
    from the page's left edge (in the hand-set area it began at x=497, past the page's first panel, too narrow a
    blob for a capture that wide): the same two units, fingerprints and all, in both, as the ``.json`` records them.

    The frame was saved with the reader's header and page slider shown over the pages (the pointer was over the
    viewer), so the ``.json`` records the capture areas as the window's panel and the hand-set area cut to the rows
    between the bars (``find_page_area`` on this frame leaves them out, which is checked too), and the boxes in them.
    """
    meta = json.loads(SPREAD.with_suffix(".json").read_text(encoding="utf-8"))
    want = meta["expected"]
    rgb = _rgb(SPREAD)
    height, width = rgb.shape[:2]
    areas = [tuple(m) for m in want["capture_areas"]]
    shown = page_area_margins(find_page_area(rgb), (width, height))
    assert all(m[1] == shown[1] and m[3] == shown[3] for m in areas), (areas, shown)
    expected, tol = (want["right_page_box"], want["left_page_box"]), want["tolerance_px"]
    found = []
    for margins in areas:
        units = fp.analyze(rgb, margins)
        assert len(units) == want["units"] == 2, (margins, [u.box for u in units])
        assert all(_near(u.box, e, tol) for u, e in zip(units, expected)), (margins, [u.box for u in units])
        found.append([u.fingerprint for u in units])
    assert want["same_fingerprints_in_both_areas"] and found[0] == found[1]
    times = []
    for margins in areas * 3:
        start = time.perf_counter()
        fp.analyze(rgb, margins)
        times.append(time.perf_counter() - start)
    assert min(times) < 0.030, times


@volume_frames
def test_every_screen_of_a_walked_volume_keeps_its_pages_whole():
    """Every screen of every walked volume, in the area it was captured in and in the page panel the window joins
    from its screens: at most two units, none only where the panel holds no ink, never fewer than analyze gave
    then, each within the panel; and the panel's grey ink (the art, not the paper or the black at the viewer's own
    level) left outside every unit is at most 15 % on any screen and over 5 % on at most three. On the October
    volume (101 screens), before the page's blobs in line with its large ones were taken in, 12 screens (13 in the
    hand-set area) left more than 5 % out, the worst 87 %; now one does (10.6 %: the black foot of a page, at the
    viewer's own level)."""
    for volume in VOLUMES:
        _volume_keeps_its_pages_whole(volume)


def _volume_keeps_its_pages_whole(volume: Path) -> None:
    manifest = json.loads((volume / "manifest.json").read_text(encoding="utf-8"))
    frames = [(entry, _rgb(volume / entry["file"])) for entry in manifest["screens"]]
    hand = tuple(manifest["margins"])
    boxes = [box for _entry, rgb in frames if (box := find_page_area(rgb)) is not None]
    joined = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    height, width = frames[0][1].shape[:2]
    panel = page_area_margins(joined, (width, height))
    times = []
    for margins in (hand, panel):
        left_out = []
        for entry, rgb in frames:
            start = time.perf_counter()
            units = fp.analyze(rgb, margins)
            times.append(time.perf_counter() - start)
            where = f"screen {entry['screen']}, margins {margins}"
            assert len(units) <= 2 and len(units) >= len(entry["fingerprints"]), (where, [u.box for u in units])
            x0, y0, x1, y1 = joined
            gray = rgb[y0:y1, x0:x1].mean(axis=2)
            if not units:
                assert not (gray < 120).any(), where
                continue
            grey = (gray > 24) & (gray < 120)
            total = int(grey.sum())
            for u in units:
                assert x0 - 2 <= u.box[0] and y0 - 2 <= u.box[1] and u.box[2] <= x1 + 2 and u.box[3] <= y1 + 2, where
                grey[max(0, u.box[1] - y0):u.box[3] - y0, max(0, u.box[0] - x0):u.box[2] - x0] = False
            left_out.append(int(grey.sum()) / total if total else 0.0)
        assert max(left_out) <= 0.15 and sum(share > 0.05 for share in left_out) <= 3, (margins, sorted(left_out)[-5:])
    assert float(np.median(times)) < 0.030


# ------------------------------------------------------------------ the book recognised after a resize
class _Store:
    """A store of caches as recognising a book reads it (`CacheStore.identities`), without files: one cache per
    book, of (fingerprint, aspect) pages; nothing of a page's text."""

    def __init__(self, books: dict[str, list[tuple[str, float]]]):
        self.books = books

    def identities(self) -> list[CacheIdentity]:
        return [CacheIdentity(f"{book}.json", book, "English", tuple(pages), {}) for book, pages in self.books.items()]


def _refit(rgb: np.ndarray, panel: fp.Box, sx: float, sy: float) -> np.ndarray:
    """The capture *rgb* as the viewer shows it in a window *sx* times as wide and *sy* times as tall below the
    browser's bars: the page panel *panel* fitted into it with its aspect kept (as a viewer re-fits its pages),
    centred on the viewer's black background; the browser's bars stretched across the new width."""
    h, w = rgb.shape[:2]
    x0, y0, x1, y1 = panel
    width, below = int(round(w * sx)), int(round((h - y0) * sy))
    scale = min(below / (y1 - y0), width / (x1 - x0))
    tw, th = int(round((x1 - x0) * scale)), int(round((y1 - y0) * scale))
    page = cv2.resize(rgb[y0:y1, x0:x1], (tw, th), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    out = np.zeros((y0 + max(below, th), max(width, tw), 3), np.uint8)
    out[:y0] = cv2.resize(rgb[:y0], (out.shape[1], y0), interpolation=cv2.INTER_NEAREST)
    left, top = (out.shape[1] - tw) // 2, y0 + (out.shape[0] - y0 - th) // 2
    out[top:top + th, left:left + tw] = page
    return out


def _other_pages() -> list[tuple[str, float]]:
    """The pages of the dark-page spread (another book's), as a cache would hold them; [] when it is not there."""
    if not SPREAD.is_file() or not SPREAD.with_suffix(".json").is_file():
        return []
    meta = json.loads(SPREAD.with_suffix(".json").read_text(encoding="utf-8"))
    areas = [tuple(m) for m in meta["expected"]["capture_areas"]]
    return [probe for group in page_groups(_rgb(SPREAD), areas) for probe in group]


@volume_frames
def test_a_walked_volume_is_recognised_after_the_viewers_window_is_resized():
    """Every third screen of a walked volume re-fitted into four other window sizes (0.8 to 1.25 times as wide and
    as tall): recognised as the volume by a cache of its pages as analyze gives them now, in the area the screens
    were captured in, but for at most 2 % of the frames; never with the screen's own pages left out of the cache
    (then every match would be another page, of the volume or of the spread's book). On the October volume, all 101
    screens at 24 sizes (0.8, 0.9, 1.0, 1.1, 1.25 in each axis): a page lands a median 1 bit from its cached self
    (p95 8, p99 45: its unit moved by some pixels), the volume is recognised in 99.6 % of the 2,400 frames (99.4 %
    by a page within 6 bits alone), with its own pages left out in none."""
    other = _other_pages()
    for volume in VOLUMES:
        manifest = json.loads((volume / "manifest.json").read_text(encoding="utf-8"))
        hand = tuple(manifest["margins"])
        screens = [(entry["screen"], _rgb(volume / entry["file"])) for entry in manifest["screens"]]
        boxes = [box for _screen, rgb in screens if (box := find_page_area(rgb)) is not None]
        panel = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
        cached = {screen: [(u.fingerprint, u.aspect) for u in fp.analyze(rgb, hand)] for screen, rgb in screens}
        frames = missed = 0
        for screen, rgb in screens[::3]:
            if not cached[screen]:
                continue
            for sx, sy in ((0.8, 0.8), (1.25, 1.25), (1.1, 0.9), (0.9, 1.1)):
                groups = page_groups(_refit(rgb, panel, sx, sy), hand)
                frames += 1
                found = recognise(_Store({"Volume": [p for pages in cached.values() for p in pages], "Other": other}),
                                  groups, "English")
                missed += [r.book for r in found[:1]] != ["Volume"]
                rest = [p for s, pages in cached.items() if s != screen for p in pages]
                assert recognise(_Store({"Volume": rest, "Other": other}), groups, "English") == [], (screen, sx, sy)
        assert frames >= 30 and missed <= 0.02 * frames, (volume.name, missed, frames)


@volume_frames
def test_a_cache_walked_before_the_unit_grew_is_recognised():
    """The fingerprints the walk recorded (before 2026-10-31, when the paper on a dark viewer began to grow through
    a page's black panels) are what analyze gives without growing it, every one; and with them as the cache every
    screen is recognised at distance 0, though analyze now gives some pages another fingerprint (19 of the October
    volume's 198 pages more than 6 bits away, 17 more than the 36 bits a cache lookup allows)."""
    for volume in VOLUMES:
        manifest = json.loads((volume / "manifest.json").read_text(encoding="utf-8"))
        hand = tuple(manifest["margins"])
        walked = [(entry, _rgb(volume / entry["file"])) for entry in manifest["screens"]]
        store = _Store({"Volume": [(f, 0.0) for entry, _rgb_ in walked for f in entry["fingerprints"]]})
        moved = 0
        for entry, rgb in walked:
            assert [u.fingerprint for u in fp.analyze(rgb, hand, grow=False)] == entry["fingerprints"], entry["screen"]
            now = [u.fingerprint for u in fp.analyze(rgb, hand)]
            moved += sum(min(fp.hamming(n, f) for n in now) > 6 for f in entry["fingerprints"])
            if entry["fingerprints"]:
                found = recognise(store, rgb, "English", margins=hand)
                assert [(r.book, r.distance) for r in found] == [("Volume", 0)], entry["screen"]
        assert moved > 0  # what the units as found before are looked for for


@volume_frames
def test_a_cache_walked_before_the_unit_grew_keeps_hitting_in_the_pipeline(tmp_path):
    """The walk's fingerprints (kept before the unit grew) as a cache of stand-in bubbles: the pipeline's lookup finds
    every page the walk kept (198 of today's 199 units on the October volume), the 17 whose unit grew through black
    panels by the units as found before (`Pipeline._lookup_before`), which re-keys them under today's units; with a
    screen's own pages left out, nothing is found that way (another page would have been re-keyed)."""
    for volume in VOLUMES:
        manifest = json.loads((volume / "manifest.json").read_text(encoding="utf-8"))
        hand = tuple(manifest["margins"])
        walked = [(entry, _rgb(volume / entry["file"])) for entry in manifest["screens"]]
        settings = Settings(state_dir=tmp_path / volume.name)
        cache = CacheStore(settings.cache_dir).open("Volume", "m")
        for entry, _frame in walked:
            for fingerprint in entry["fingerprints"]:
                cache.add(CachedPage(fingerprint=fingerprint, aspect=0.0, seq=-1,
                                     bubbles=[CachedBubble(box=(0.2, 0.2, 0.4, 0.3), text="x")]))
        cache.save()
        pipeline = Pipeline(settings, cache=cache)
        units = hits = rekeyed = 0
        for entry, rgb in walked:
            for unit in fp.analyze(rgb, hand):
                units += 1
                direct = cache.lookup(unit.fingerprint, unit.aspect, settings.fingerprint_max_distance)
                hit = pipeline._lookup(unit, _units_before(rgb, hand))
                hits += hit is not None
                rekeyed += hit is not None and direct is None
                if hit is not None and direct is None:
                    assert hit[0].fingerprint == unit.fingerprint and hit[1] == 0, entry["screen"]
        kept = sum(len(entry["fingerprints"]) for entry, _frame in walked)  # a screen has a unit more today
        assert hits >= kept and rekeyed > 0, (hits, units, kept, rekeyed)

        for entry, rgb in walked[::4]:  # another page is never re-keyed in its place
            rest = CacheStore(tmp_path / "rest" / str(entry["screen"])).open("Volume", "m")
            for other, _frame in walked:
                if other["screen"] != entry["screen"]:
                    for fingerprint in other["fingerprints"]:
                        rest.add(CachedPage(fingerprint=fingerprint, aspect=0.0, seq=-1, bubbles=[]))
            missing = Pipeline(settings, cache=rest)
            before = _units_before(rgb, hand)
            for unit in fp.analyze(rgb, hand):
                assert missing._lookup_before(unit, before()) is None, entry["screen"]
