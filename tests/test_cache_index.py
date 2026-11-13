"""The cache's fingerprint index (`cache._PageIndex`): `BookCache._place` finds the same page through it as the scan
it replaced, copied here as the oracle, on random fingerprints, drifted ones, clusters of pages a few bits apart,
other distances, odd fingerprints, removals and pages placed twice; and a merge compares a fingerprint with the few
pages that share a chunk of it instead of with every page (5,000 pages into 5,000 took some 25 seconds)."""
from __future__ import annotations

import itertools
import random
from pathlib import Path

import pytest

from taslation import cache as cache_module
from taslation.cache import INDEXED_WITHIN, BookCache, CachedPage
from taslation.fingerprint import FINGERPRINT_BITS, hamming

FLIPS = [0, 1, 2, 3, 4, 5, 5, 6, 6, 6, 7, 7, 8, 9, 12, 40]  # bits a page drifts by: most near the replace distance


def oracle_place(pages: list[CachedPage], page: CachedPage, replace_within: int = 6) -> None:
    """`BookCache._place` as it was before the index (commit 012aba8): the first page in the list within
    *replace_within* bits is replaced and its sequence number kept, else the page goes last, with the next number
    when it has none or one another page has."""
    for i, existing in enumerate(pages):
        if hamming(existing.fingerprint, page.fingerprint) <= replace_within:
            page.seq = existing.seq
            pages[i] = page
            return
    if page.seq < 0 or any(p.seq == page.seq for p in pages):
        page.seq = max((p.seq for p in pages), default=-1) + 1
    pages.append(page)


def oracle_remove(pages: list[CachedPage], fingerprint: str, replace_within: int = 6) -> list[CachedPage]:
    """`BookCache.remove` as it was (and is): every page within *replace_within* bits goes."""
    return [p for p in pages if hamming(p.fingerprint, fingerprint) > replace_within]


def _random(rng: random.Random) -> str:
    return format(rng.getrandbits(FINGERPRINT_BITS), "080x")


def _near(fingerprint: str, bits: int, rng: random.Random) -> str:
    """*fingerprint* with *bits* bits flipped: the same page captured again."""
    value = int(fingerprint, 16)
    for bit in rng.sample(range(FINGERPRINT_BITS), bits):
        value ^= 1 << bit
    return format(value, "080x")


def _odd(fingerprint: str, rng: random.Random) -> str:
    """A fingerprint no pipeline makes but `hamming` reads: upper case (indexed all the same), a prefix, a space, an
    underscore, a short one (compared every time)."""
    return rng.choice([fingerprint.upper(), "0x" + fingerprint[2:], " " + fingerprint[1:],
                       fingerprint[:40] + "_" + fingerprint[41:], fingerprint[:20]])


def _state(pages: list[CachedPage]) -> list[tuple[float, str, int]]:
    return [(p.aspect, p.fingerprint, p.seq) for p in pages]  # the aspect is each page's own tag


def _check_index(cache: BookCache) -> None:
    """The index the places kept in step is the one the list gives afresh (`_PageIndex`)."""
    index = cache._index
    if index is None or not index.current(cache.pages):
        return  # made anew at the next place
    fresh = cache_module._PageIndex(cache.pages)
    assert [{key: sorted(at) for key, at in chunk.items()} for chunk in index.chunks] == \
        [{key: sorted(at) for key, at in chunk.items()} for chunk in fresh.chunks]
    assert (index.keys, index.ids, index.odd, index.members, index.top) == \
        (fresh.keys, fresh.ids, fresh.odd, fresh.members, fresh.top)
    assert {seq: n for seq, n in index.seqs.items() if n} == fresh.seqs


def _run(seed: int, steps: int) -> None:
    rng = random.Random(seed)
    cache = BookCache(Path("index.json"), "b", "m")
    oracle: list[CachedPage] = []
    tags = itertools.count()

    def twins(fingerprint: str, seq: int) -> tuple[CachedPage, CachedPage]:
        """The same page for each side (the oracle changes the numbers of its own pages)."""
        tag = float(next(tags))
        return CachedPage(fingerprint, tag, [], seq=seq), CachedPage(fingerprint, tag, [], seq=seq)

    # a file's worth of pages as a load gives them: near duplicates side by side, sequence numbers that repeat
    centres = [_random(rng) for _ in range(40)]
    known = list(centres)
    for _ in range(300):
        fingerprint = _near(rng.choice(centres), rng.randint(0, 6), rng) if rng.random() < 0.5 else _random(rng)
        known.append(fingerprint)
        mine, theirs = twins(fingerprint, rng.randint(0, 250))
        cache.pages.append(mine)
        oracle.append(theirs)
    for step in range(steps):
        if step % 50 == 0:
            _check_index(cache)
        roll, within = rng.random(), INDEXED_WITHIN
        seq = rng.choice([-1, -1, -1, -7, rng.randint(0, 2 * len(oracle) + 1)])
        if roll < 0.30:  # a page captured again, its fingerprint drifted
            fingerprint = _near(rng.choice(known), rng.choice(FLIPS), rng)
        elif roll < 0.42:  # a page near several in a cluster: the first in the list wins
            fingerprint = _near(rng.choice(centres), rng.randint(0, 9), rng)
        elif roll < 0.62:  # a new page
            fingerprint = _random(rng)
        elif roll < 0.72:  # another distance: every page is compared, and the index follows the change
            fingerprint = _near(rng.choice(known), rng.choice(FLIPS), rng)
            within = rng.choice([0, 3, 5, 7, 12])
        elif roll < 0.78:
            fingerprint = _odd(_near(rng.choice(known), rng.choice(FLIPS), rng), rng)
        elif roll < 0.84 and oracle:  # a page that is in the list already, placed again
            at = rng.randrange(len(oracle))
            within = rng.choice([INDEXED_WITHIN, INDEXED_WITHIN, 9])
            cache.add(cache.pages[at], within)
            oracle_place(oracle, oracle[at], within)
            assert _state(cache.pages) == _state(oracle)
            continue
        elif roll < 0.90:  # forgotten pages
            fingerprint = _near(rng.choice(known), rng.randint(0, 9), rng)
            within = rng.choice([INDEXED_WITHIN, INDEXED_WITHIN, 2, 9])
            gone = len(oracle)
            oracle[:] = oracle_remove(oracle, fingerprint, within)
            assert cache.remove(fingerprint, within) == gone - len(oracle)
            assert _state(cache.pages) == _state(oracle)
            continue
        elif roll < 0.92:  # another list with the same pages (what a reload puts in place)
            cache.pages = list(cache.pages)
            continue
        else:
            fingerprint = _near(rng.choice(centres), rng.choice(FLIPS), rng)
        if len(fingerprint) == 80 and fingerprint.isalnum():
            known.append(fingerprint.lower())
        mine, theirs = twins(fingerprint, seq)
        assert cache.add(mine, within) is mine
        oracle_place(oracle, theirs, within)
        assert _state(cache.pages) == _state(oracle)
    _check_index(cache)
    assert cache.next_seq == max((p.seq for p in oracle), default=-1) + 1
    assert [p.to_json() for p in cache.pages] == [p.to_json() for p in oracle]


@pytest.mark.parametrize("seed", [1, 2])
def test_the_index_places_every_page_where_the_scan_did(seed):
    _run(seed, 1500)


def test_pages_within_the_distance_of_each_other_the_first_in_the_list_is_replaced():
    """Two pages a file holds within six bits of each other (written so by an earlier version, or by hand), and a
    page near both: the first in the list is replaced, as the scan did, not the nearest."""
    rng = random.Random(3)
    first = _random(rng)
    second = _near(first, 6, rng)
    cache = BookCache(Path("index.json"), "b", "m")
    cache.pages.extend([CachedPage(first, 0.7, [], seq=0), CachedPage(second, 0.7, [], seq=1)])
    page = cache.add(CachedPage(second, 0.7, [], seq=-1))  # 0 bits from the second page, 6 from the first
    assert cache.pages[0] is page and page.seq == 0 and cache.pages[1].fingerprint == second


def test_a_page_placed_again_while_in_the_list():
    """A page that is in the list already, placed again where an earlier page is within reach: the scan gave it that
    page's number and place, so it stood twice in the list and its own number was gone. The index counts numbers,
    so such a place goes without it: the next page keeps the number nobody has any more, as with the scan."""
    rng = random.Random(4)
    first = _random(rng)
    second, third, fourth = _near(first, 3, rng), _random(rng), _random(rng)
    cache = BookCache(Path("index.json"), "b", "m")
    oracle: list[CachedPage] = []
    for pages in (cache.pages, oracle):
        pages.extend([CachedPage(first, 0.0, [], seq=0), CachedPage(second, 1.0, [], seq=1)])
    cache.add(CachedPage(third, 2.0, [], seq=-1))  # the index is made
    oracle_place(oracle, CachedPage(third, 2.0, [], seq=-1))
    cache.add(cache.pages[1])  # the second page again: it takes the place and the number of the first, 3 bits off
    oracle_place(oracle, oracle[1])
    assert cache.pages[0] is cache.pages[1] and _state(cache.pages) == _state(oracle)
    cache.add(CachedPage(fourth, 3.0, [], seq=1))  # no page has the number 1 any more: the new one keeps it
    oracle_place(oracle, CachedPage(fourth, 3.0, [], seq=1))
    assert _state(cache.pages) == _state(oracle) and cache.pages[3].seq == 1
    _check_index(cache)


def test_a_merge_compares_a_few_fingerprints_per_page_not_every_page(monkeypatch):
    """The scan compared each page brought with every page there until one was near: millions of comparisons for
    thousands of pages. Through the index a page is compared with those that share a chunk of its fingerprint: the
    page it replaces, and next to never another one."""
    rng = random.Random(5)
    cache = BookCache(Path("index.json"), "b", "m")
    there = [_random(rng) for _ in range(2000)]
    for fingerprint in there:
        cache.add(CachedPage(fingerprint, 0.7, [], seq=-1))
    again = [_near(fingerprint, rng.randint(0, INDEXED_WITHIN), rng) for fingerprint in rng.sample(there, 1000)]
    new = [_random(rng) for _ in range(1000)]
    compared: list[int] = []

    def counted(a: str, b: str) -> int:
        compared.append(1)
        return hamming(a, b)

    monkeypatch.setattr(cache_module, "hamming", counted)
    for fingerprint in again + new:
        cache.add(CachedPage(fingerprint, 0.7, [], seq=-1))
    assert len(cache) == 3000 and sorted(p.seq for p in cache.pages) == list(range(3000))
    assert len(compared) <= 1100  # the scan: some 3.5 million
    probe = _near(cache.pages[2500].fingerprint, 8, rng)  # another distance: every page in turn, as before
    first = next(i for i, p in enumerate(cache.pages) if hamming(p.fingerprint, probe) <= 10)
    compared.clear()
    cache.add(CachedPage(probe, 0.7, [], seq=-1), replace_within=10)
    assert len(compared) == first + 1 and cache.pages[first].fingerprint == probe
