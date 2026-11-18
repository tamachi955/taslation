"""No two translations of a page are lettered over each other: where the rooms of two regions overlap, the shared
part goes to the region whose own lettering is nearer (`render.rooms.share_rooms`), whatever the regions' boxes do.
Bubbles fused into one white area are cut between their texts even where the straight line between the junction's
notches clips one of them, fragments of one block of small print are one region, and a region found inside a
larger region's box keeps its own."""
from __future__ import annotations

import cv2
import numpy as np
import pytest
from PIL import Image

from taslation.detect import BubbleDetector, TextBlockDetector
from taslation.detect.bubbles import DetectorConfig
from taslation.regions import ERASED, TextRegion
from taslation.render.rooms import in_own_room, room_mask, share_rooms

SIZE = 24  # glyph size of the lettering drawn


# ------------------------------------------------------------------ helpers
def _region(box, text_box, status="translated", mask=None, text="A line of the translation.", **kw) -> TextRegion:
    x0, y0, x1, y1 = box
    if mask is None:
        mask = np.full((y1 - y0, x1 - x0), 255, np.uint8)
    return TextRegion(x0, y0, x1, y1, mask, text_box, status=status, translated_text=text,
                      source_text="こんにちは", **kw)


def _page_mask(r: TextRegion, shape, mask=None) -> np.ndarray:
    out = np.zeros(shape[:2], bool)
    out[r.y0:r.y1, r.x0:r.x1] = (r.mask if mask is None else mask) > 0
    return out


def _meet(a, b) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


class _Ink:
    """The box of the lettering each call of the pipeline's `letter_text` draws (the pixels it changes)."""

    def __init__(self, monkeypatch):
        import taslation.pipeline as pipeline_module

        self.boxes: list[tuple[str, tuple[int, int, int, int]]] = []
        original = pipeline_module.letter_text

        def letter_text(image, region, text, *args, **kwargs):
            if image is None:
                return original(image, region, text, *args, **kwargs)
            before = np.asarray(image).copy()
            done = original(image, region, text, *args, **kwargs)
            ys, xs = np.nonzero(np.any(np.asarray(image) != before, axis=2))
            if xs.size:
                self.boxes.append((text, (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)))
            return done

        monkeypatch.setattr(pipeline_module, "letter_text", letter_text)

    def overlaps(self) -> list[tuple[str, str]]:
        return [(a, b) for i, (a, ba) in enumerate(self.boxes) for b, bb in self.boxes[i + 1:] if _meet(ba, bb)]


def _letter(img: Image.Image, columns) -> np.ndarray:
    from test_joined_bubbles import _letter as letter  # skips the test when no Japanese font is installed

    return letter(img, columns)


def _page(**shapes):
    from test_joined_bubbles import _page as page

    return page(**shapes)


# ------------------------------------------------------------------ sharing the rooms out
def test_overlapping_rooms_are_shared_between_the_texts():
    """Two regions whose boxes and masks overlap (a model's boxes of two fused bubbles): each keeps what is nearer
    its own lettering, the shared part is cut between them, and nothing of the two masks is lost."""
    a = _region((100, 100, 300, 400), (150, 150, 200, 250))
    b = _region((200, 200, 400, 500), (300, 330, 350, 450))
    assert share_rooms([a, b]) >= 1
    shape = (600, 600)
    ra, rb = _page_mask(a, shape, room_mask(a)), _page_mask(b, shape, room_mask(b))
    assert not (ra & rb).any()  # the rooms do not overlap ...
    assert ((ra | rb) == (_page_mask(a, shape) | _page_mask(b, shape))).all()  # ... and share all of it out
    assert ra[150:250, 150:200].all() and rb[330:450, 300:350].all()  # each keeps the room round its own lettering
    assert a.bbox == (100, 100, 300, 400) and b.bbox == (200, 200, 400, 500)  # the boxes are left as they are
    assert (a.mask == 255).all() and (b.mask == 255).all()  # and so are the masks (the erase is the region's own)


def test_a_region_alone_or_beside_no_text_keeps_its_room():
    a = _region((100, 100, 300, 400), (150, 150, 200, 250))
    empty = _region((200, 200, 400, 500), (300, 330, 350, 450), status="ocr-empty")
    assert share_rooms([a, empty]) == 0
    assert a.ceded is None and room_mask(a) is a.mask and in_own_room(a) is a


def test_regions_that_stay_beside_are_counted_but_not_changed():
    """*among*: regions of the page lettered elsewhere (or whose Japanese stays) keep their part, untouched."""
    a = _region((100, 100, 300, 400), (150, 150, 200, 250))
    other = _region((200, 200, 400, 500), (300, 330, 350, 450), status="untranslated")
    share_rooms([a], among=[other])
    assert a.ceded is not None and other.ceded is None
    assert not room_mask(a)[330 - 100:400 - 100, 300 - 100:].any()  # what is nearer the other's lettering is given up


def test_the_part_given_up_is_the_same_object_while_nothing_changes():
    """Shared out again with nothing changed, a region gives up the very same object (a draft's kept measure, keyed
    by identity, stays kept)."""
    a = _region((100, 100, 300, 400), (150, 150, 200, 250))
    b = _region((200, 200, 400, 500), (300, 330, 350, 450))
    share_rooms([a, b])
    first = a.ceded
    share_rooms([a, b])
    assert a.ceded is first
    erased_only = _region((200, 200, 400, 500), (300, 330, 350, 450), status=ERASED)
    share_rooms([a, erased_only])  # an "erase only" region keeps the room round the lettering it erases too
    assert a.ceded is not None


def test_a_small_caption_inside_a_large_box_keeps_its_room():
    """A two-character caption whose box lies inside a large region's box: the caption keeps its own room, the large
    region gives it up."""
    big = _region((100, 100, 500, 600), (200, 200, 400, 500))
    small = _region((420, 120, 470, 220), (430, 130, 460, 210))
    share_rooms([big, small])
    assert small.ceded is None and big.ceded is not None
    assert not room_mask(big)[130 - 100:210 - 100, 430 - 100:460 - 100].any()


def test_lettered_regions_never_overlap_on_the_page(settings, monkeypatch):
    """The invariant on the page: whatever the regions' boxes and masks, the lettering of no two regions overlaps (the
    boxes of what each lettering drew), on the page as rendered, on a page lettered again and on a page from the
    cache's lettering (`translated_page` shares out its copies alike)."""
    from taslation.pipeline import Pipeline

    ink = _Ink(monkeypatch)
    p = Pipeline(settings, ocr=None, translator=None)
    page = np.full((700, 700, 3), 255, np.uint8)
    texts = ["Where are you going so early in the morning?", "Nowhere you would ever want to follow me, really."]
    regions = [_region((100, 100, 420, 460), (180, 160, 240, 300), text=texts[0]),
               _region((220, 220, 560, 600), (360, 380, 420, 540), text=texts[1])]
    p._render(page.copy(), regions)
    assert len(ink.boxes) == 2 and ink.overlaps() == []
    ink.boxes.clear()
    p._render(page.copy(), regions, recap=False)  # lettered again (an edit of another region)
    assert len(ink.boxes) == 2 and ink.overlaps() == []
    ink.boxes.clear()
    p._render(page.copy(), regions[:1], among=regions[1:])  # the other one's Japanese or lettering stays beside
    assert len(ink.boxes) == 1 and not _meet(ink.boxes[0][1], regions[1].letter_box or regions[1].text_box)


def test_the_room_hint_is_that_of_the_regions_own_part(settings, monkeypatch):
    """The characters of room the translator is told of are measured in the part of the room the region keeps."""
    import taslation.pipeline as pipeline_module
    from taslation.pipeline import Pipeline
    from taslation.translate import DictTranslator

    measured: list[np.ndarray] = []
    original = pipeline_module.translation_room

    def translation_room(mask, *args, **kwargs):
        measured.append(np.asarray(mask).copy())
        return original(mask, *args, **kwargs)

    monkeypatch.setattr(pipeline_module, "translation_room", translation_room)
    p = Pipeline(settings, ocr=None, translator=DictTranslator({"こんにちは": "Hello there."}))
    a = _region((100, 100, 300, 300), (150, 150, 190, 250), status="untranslated", text="")
    b = _region((140, 100, 340, 300), (250, 150, 290, 250), status="untranslated", text="")
    p.share_rooms([a, b], (700, 700))
    assert a.ceded is not None and b.ceded is not None
    assert p._translate_regions([a, b], lambda _m: None) == ""
    assert len(measured) == 2
    assert np.array_equal(measured[0], room_mask(a)) and np.array_equal(measured[1], room_mask(b))
    assert (measured[0] > 0).sum() < (a.mask > 0).sum()


# ------------------------------------------------------------------ fused bubbles, cut between the texts
def _fused_offset():
    """Two upright bubbles fused wide, the left one lower: the right text's last column runs down past the
    junction's upper notch, so the straight line between the notches clips it."""
    img, _ = _page(ellipses=[(260, 100, 520, 460), (100, 260, 360, 620)])
    return _letter(img, [("こんにちはありが", 312, 175), ("ありがとう", 344, 175), ("大丈夫だよ", 166, 330),
                         ("まだまだ", 198, 350)])


def test_bubbles_fused_with_offset_texts_become_two_regions():
    rgb = _fused_offset()
    regions = sorted(BubbleDetector(DetectorConfig()).detect(rgb), key=lambda r: r.x0)
    assert len(regions) == 2, [r.bbox for r in regions]
    a, b = regions
    assert a.kind == b.kind == "bubble"
    assert a.text_box[2] < 300 and b.text_box[0] > 300  # each holds its own text only
    assert not (_page_mask(a, rgb.shape) & _page_mask(b, rgb.shape)).any()
    assert BubbleDetector(DetectorConfig(split_lobes=False)).detect(rgb) == []  # read whole: the old miss


class _SizedOcr:
    """Reads a short exclamation from a small crop and a long line from any other (the pipeline shows the OCR crops
    only, in an order of its own)."""

    def __init__(self, short: str, long: str):
        self.short, self.long = short, long

    def read(self, image: Image.Image) -> str:
        return self.short if image.width * image.height < 9000 else self.long


LONG_JA = "こんにちはありがとう大丈夫"


def test_bubbles_fused_with_offset_texts_are_lettered_apart(settings, monkeypatch):
    from taslation.pipeline import Pipeline
    from taslation.translate import DictTranslator

    ink = _Ink(monkeypatch)
    rgb = _fused_offset()
    tr = DictTranslator({LONG_JA: "Hello there, and thank you so much! It's fine."})
    res = Pipeline(settings, ocr=_SizedOcr("あっ", LONG_JA), translator=tr).process(Image.fromarray(rgb),
                                                                                  use_cache=False)
    assert len(res.translated) == 2, [(r.bbox, r.status) for r in res.regions]
    assert len(ink.boxes) == 2 and ink.overlaps() == []
    a, b = sorted(res.translated, key=lambda r: r.x0)
    assert b.order < a.order  # right to left: the upper right bubble first


def test_a_chain_of_three_fused_bubbles_becomes_three_regions():
    img, _ = _page(ellipses=[(560, 60, 760, 380), (420, 300, 620, 620), (280, 540, 480, 860)])
    rgb = _letter(img, [("こんにちは", 648, 110), ("ありがとう", 508, 350), ("大丈夫だよ", 368, 590)])
    regions = BubbleDetector().detect(rgb)
    assert len(regions) == 3, [r.bbox for r in regions]
    masks = [_page_mask(r, rgb.shape) for r in regions]
    assert not any((masks[i] & masks[j]).any() for i in range(3) for j in range(i + 1, 3))


def test_a_tall_bubble_with_two_paragraphs_stays_one_region():
    """One tall oval, its text in two groups of columns with a pause between them: one bubble, one text."""
    img, _ = _page(ellipses=[(250, 100, 520, 760)])
    rgb = _letter(img, [("こんにちは", 410, 170), ("ありがとう", 378, 170), ("大丈夫だよ", 346, 390),
                        ("まだまだよ", 314, 390)])
    regions = BubbleDetector().detect(rgb)
    assert len(regions) == 1, [r.bbox for r in regions]


def test_a_stepped_caption_with_one_text_stays_one_region():
    """A caption box of two offset rectangles (a step), one text set across the step at its own column spacing:
    the step's two corners are deep notches, but the columns on either side are one text's."""
    img, _ = _page(rects=[(400, 100, 600, 320), (260, 260, 460, 520)])
    rgb = _letter(img, [("こんにちは", 470, 130), ("ありがとう", 440, 150), ("大丈夫だよ", 410, 170),
                        ("まだまだ", 380, 280)])
    regions = BubbleDetector().detect(rgb)
    assert len(regions) == 1, [r.bbox for r in regions]


# ------------------------------------------------------------------ fragments of one block of small print
def _draw_rows(rgb: np.ndarray, rows, size: int) -> np.ndarray:
    from pathlib import Path

    from PIL import ImageDraw, ImageFont

    fonts = [r"C:\Windows\Fonts\YuGothB.ttc", r"C:\Windows\Fonts\meiryob.ttc",
             "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]
    path = next((p for p in fonts if Path(p).is_file()), None)
    if path is None:
        pytest.skip("no Japanese font available")
    pil = Image.fromarray(rgb)
    draw = ImageDraw.Draw(pil)
    font = ImageFont.truetype(path, size)
    for text, x, y in rows:
        draw.text((x, y), text, font=font, fill=(0, 0, 0))
    return np.asarray(pil).copy()


def test_columns_broken_at_a_long_mark_are_one_block():
    """Small print in columns set a glyph apart, each broken by a long mark that is no glyph-sized piece (a bar):
    one block of text, not a fragment per piece of column."""
    from test_detect import _draw_vertical

    rgb = np.full((700, 600, 3), 255, np.uint8)
    size = 16
    pitch = int(size * 1.1)
    for x in (400, 370, 340):  # columns a glyph apart
        rgb = _draw_vertical(rgb, "今日はいい天気", x, 100, size)
        bar_y = 100 + 7 * pitch + 2
        cv2.rectangle(rgb, (x + 7, bar_y), (x + 9, bar_y + size - 2), (0, 0, 0), -1)  # the long mark
        rgb = _draw_vertical(rgb, "大丈夫だよまだ", x, 100 + 8 * pitch, size)
    blocks = TextBlockDetector().detect(rgb)
    assert len(blocks) == 1, [b.text_box for b in blocks]
    tb = blocks[0].text_box
    assert tb[0] <= 342 and tb[2] >= 414 and tb[1] <= 103 and tb[3] >= 100 + 14 * pitch


def test_a_row_broken_at_a_dash_is_one_block():
    rgb = np.full((300, 900, 3), 255, np.uint8)
    rgb = _draw_rows(rgb, [("今日はいい天気", 100, 100)], 18)
    cv2.rectangle(rgb, (100 + 7 * 18 + 3, 108), (100 + 7 * 18 + 3 + 16, 111), (0, 0, 0), -1)  # a long dash
    rgb = _draw_rows(rgb, [("大丈夫だよまだ", 100 + 8 * 18 + 4, 100)], 18)
    blocks = TextBlockDetector().detect(rgb)
    assert len(blocks) == 1, [b.text_box for b in blocks]


def test_a_paragraph_of_three_rows_is_one_block():
    rgb = np.full((300, 900, 3), 255, np.uint8)
    rgb = _draw_rows(rgb, [("今日はいい天気だね大丈夫だよ", 100, 100), ("まだ終わってないどこへ行くの", 100, 128),
                           ("ありがとうこんにちは", 100, 156)], 18)
    blocks = TextBlockDetector().detect(rgb)
    assert len(blocks) == 1, [b.text_box for b in blocks]


def test_two_texts_with_an_outline_between_are_not_joined():
    """Two columns of small print a glyph apart with a line drawn between them (the outline of two boxes): two texts."""
    from test_detect import _draw_vertical

    rgb = np.full((600, 600, 3), 255, np.uint8)
    rgb = _draw_vertical(rgb, "今日はいい天気だね", 400, 100, 16)
    rgb = _draw_vertical(rgb, "大丈夫だよまだまだ", 362, 100, 16)
    cv2.line(rgb, (388, 60), (388, 320), (0, 0, 0), 2)
    blocks = TextBlockDetector().detect(rgb)
    assert len(blocks) == 2, [b.text_box for b in blocks]


def test_a_list_stays_a_line_per_entry():
    """Rows set as far apart as a list's (a table of contents) are separate texts, joined no more than before."""
    rgb = np.full((400, 900, 3), 255, np.uint8)
    rgb = _draw_rows(rgb, [("今日はいい天気", 100, 100), ("大丈夫だよまだ", 100, 150), ("ありがとうね", 100, 200)], 18)
    assert len(TextBlockDetector().detect(rgb)) == 3


# ------------------------------------------------------------------ a caption beside a larger region
def test_a_small_caption_beside_a_balloon_is_read_and_lettered_on_its_own(settings, monkeypatch):
    from taslation.pipeline import Pipeline
    from taslation.translate import DictTranslator

    from test_joined_bubbles import _shapes

    ink = _Ink(monkeypatch)
    img, draw = _page(ellipses=[(200, 150, 600, 650)])
    _shapes(draw, rects=[(560, 120, 620, 220)])
    rgb = _letter(img, [("こんにちは", 430, 260), ("ありがとう", 395, 260), ("大丈夫", 340, 300), ("あっ", 578, 130)])
    tr = DictTranslator({"あっ": "Ah!", LONG_JA: "Hello there, thank you, it's fine."})
    res = Pipeline(settings, ocr=_SizedOcr("あっ", LONG_JA), translator=tr).process(Image.fromarray(rgb),
                                                                                  use_cache=False)
    assert len(res.translated) == 2, [(r.bbox, r.status) for r in res.regions]
    caption = min(res.translated, key=lambda r: r.width * r.height)
    assert caption.x0 >= 555 and caption.x1 <= 625  # the caption's own region
    japanese = np.zeros(rgb.shape[:2], bool)
    japanese[125:180, 575:610] = cv2.cvtColor(rgb[125:180, 575:610], cv2.COLOR_RGB2GRAY) < 140
    assert (_page_mask(caption, rgb.shape) | ~japanese).all()  # its lettering is in its erase
    assert len(ink.boxes) == 2 and ink.overlaps() == []
    assert not _meet(next(b for t, b in ink.boxes if t != "Ah!"), caption.bbox)  # the balloon's set beside it
