"""The live view's frame helpers (`taslation.frames`): two frames' thumbnails told apart, and a soft picture told
from a sharp one by its fine detail."""
from __future__ import annotations

from PIL import ImageFilter
from test_follow import _page

from taslation.frames import crispness, frames_differ, thumbnail


def test_frames_differ(sample_page, sample_page2):
    a, b = thumbnail(sample_page), thumbnail(sample_page2)
    assert not frames_differ(a, a)
    assert frames_differ(a, b)
    assert frames_differ(None, a)


def test_crispness_tells_soft_from_sharp_across_pages():
    sharp = [crispness(_page(seed)) for seed in (1, 2, 3)]
    soft = [crispness(_page(seed, soft=2)) for seed in (1, 2, 3)] + [
        crispness(_page(4).filter(ImageFilter.GaussianBlur(1.0)))]
    assert min(sharp) > 1.5 * max(soft)

