from __future__ import annotations

import numpy as np
from helpers import EN_TEXTS, JA_TEXTS
from PIL import Image

from taslation.detect import BubbleDetector, is_dark
from taslation.pipeline import Pipeline
from taslation.render.erase import bubble_background, erase_region
from taslation.translate import DictTranslator


def _dark_bubble_page():
    """A white page with one black bubble holding white lettering (plus a normal white bubble)."""
    from test_detect import _draw_vertical

    img = np.full((900, 1200, 3), 255, np.uint8)
    yy, xx = np.mgrid[0:900, 0:1200]
    # black bubble (light lettering)
    inside = ((xx - 300) / 130.0) ** 2 + ((yy - 400) / 180.0) ** 2 <= 1.0
    img[inside] = 20
    img = _draw_vertical(img, "死ねぇぇ！", 282, 270, 30, color=(240, 240, 240))
    # white bubble (dark lettering) on a gray panel
    img[150:750, 650:1150] = 190
    inside2 = ((xx - 900) / 130.0) ** 2 + ((yy - 450) / 180.0) ** 2 <= 1.0
    border2 = ((xx - 900) / 134.0) ** 2 + ((yy - 450) / 184.0) ** 2 <= 1.0
    img[border2] = 0
    img[inside2] = 255
    img = _draw_vertical(img, "大丈夫だよ", 882, 320, 30)
    return img


def test_dark_bubble_is_found_by_the_inverted_pass():
    img = _dark_bubble_page()
    det = BubbleDetector()
    light = det.detect(img)
    dark = det.detect(img, inverted=True)
    assert len(light) == 1 and light[0].kind == "bubble" and light[0].x0 > 700, [r.bbox for r in light]
    assert len(dark) == 1 and dark[0].kind == "dark-bubble" and dark[0].x1 < 500, [r.bbox for r in dark]
    assert is_dark(dark[0]) and not is_dark(light[0])
    bg = bubble_background(img[dark[0].y0:dark[0].y1, dark[0].x0:dark[0].x1], dark[0].mask, dark=True)
    assert max(bg) < 40
    work = img.copy()
    erase_region(work, dark[0], dark=True)
    assert work[dark[0].y0:dark[0].y1, dark[0].x0:dark[0].x1][dark[0].mask > 0].max() < 40  # lettering gone


class RecordingOcr:
    def __init__(self):
        self.means = []
        self.i = 0

    def read(self, image):
        self.means.append(float(np.asarray(image.convert("L")).mean()))
        self.i += 1
        return JA_TEXTS[self.i % len(JA_TEXTS)]


def test_pipeline_reads_dark_bubbles_inverted_and_letters_them_in_white(settings):
    img = _dark_bubble_page()
    ocr = RecordingOcr()
    tr = DictTranslator(EN_TEXTS)
    res = Pipeline(settings, ocr=ocr, translator=tr).process(Image.fromarray(img), use_cache=False)
    assert len(res.translated) == 2
    assert sorted(is_dark(r) for r in res.translated) == [False, True]
    assert all(m > 128 for m in ocr.means)  # every crop handed to the OCR was dark-on-light
    out = np.asarray(res.image)
    dark = next(r for r in res.translated if is_dark(r))
    region = out[dark.y0:dark.y1, dark.x0:dark.x1][dark.mask > 0]
    assert region.max() > 200 and np.median(region) < 40  # white text on the dark bubble
