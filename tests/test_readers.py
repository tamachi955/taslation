"""The three OCR readers: the rule that takes their word, how the pipeline asks them, an install with charspot alone.
The last tests read with the real models, and are skipped until setup_models.py has run."""
from __future__ import annotations

import logging
import threading
from pathlib import Path

import numpy as np
import pytest
from conftest import ocr_installed
from helpers import FakeOcr
from PIL import Image

from taslation import netguard
from taslation.config import OCR_MODELS, OCR_SECOND_READERS, Settings
from taslation.messages import Cancelled, Message
from taslation.ocr import Readers
from taslation.ocr import readers as R
from taslation.ocr.charspot import CharspotChar, CharspotReading, confidence
from taslation.ocr.readers import agree, distance, edits, medoid, missing_readers, normal, split
from taslation.pipeline import SPLIT_CONFIDENCE, Pipeline
from taslation.regions import TextRegion
from taslation.review import OCR_UNSURE, flags_for

LONG = "今日はとてもいい天気ですね"


def never() -> str:
    raise AssertionError("the third reader was asked")


def test_two_that_agree_are_taken_without_the_third():
    assert agree("そうだ", "そうだ", never) == ("そうだ", False)


def test_they_agree_as_normalised_text_and_charspot_s_spelling_stands():
    assert agree("そう…", "そ う...", never) == ("そう…", False)


def test_otherwise_the_reading_nearest_the_other_two_stands():
    assert agree("今日はいい天気", "今日はいい天気だ", lambda: "今日はいい天気だ") == ("今日はいい天気だ", False)
    assert agree("今日はいい天気だ", "昨日はいい天気だ", lambda: "今日はいい天気だ") == ("今日はいい天気だ", False)
    assert agree("あああああ", "今日はいい天気", lambda: "今日はいい天気だ")[0] in ("今日はいい天気", "今日はいい天気だ")


def test_a_tie_goes_to_charspot_then_nar():
    assert medoid(["abcd", "abce", "abcf"]) == "abcd"
    assert medoid(["zzzz", "abce", "abcd"]) == "abce"


def test_edit_distance():
    assert edits("", "abc") == 3 and edits("kitten", "sitting") == 3 and distance("", "") == 0 and distance("ab", "cd") == 1


def test_normal_folds_what_is_written_differently():
    assert normal("ＡＢ　c…～") == "ABc...~"


def test_three_different_lines_are_a_split_and_a_small_difference_is_not():
    assert not split([LONG, LONG + "よ", LONG[:-1] + "な"])
    assert split(["今日はとてもいい天気", "昨夜はかなりひどい雨", "明朝も少しだけ寒い朝"])
    assert not split(["今日はとてもいい天気", "今日はとてもいい天気", "全然違う読みです"])
    assert agree("今日はとてもいい天気", "昨夜はかなりひどい雨", lambda: "明朝も少しだけ寒い朝")[1]


def test_the_confidence_is_mean_heat_times_mean_classifier_probability():
    box = (0.0, 0.0, 10.0, 10.0)
    chars = [CharspotChar("あ", box, 0.9, 1.0), CharspotChar("い", box, 0.7, 0.5)]
    assert confidence(chars) == pytest.approx(0.8 * 0.75)
    assert confidence([]) == 0.0


# ---------------------------------------------------------------- the pipeline's questions


def reading(text: str, size: float = 18.0, score: float = 0.9) -> CharspotReading:
    chars = tuple(CharspotChar(c, (0.0, 0.0, size, size), score) for c in text)
    return CharspotReading(text, chars, score)


class Engine:
    """Charspot's reading per region, told by the crop's first pixel, and what the others make of it."""

    def __init__(self, charspot: list[CharspotReading], settled: list[str | None]):
        self.charspot, self.settled = charspot, settled
        self.asked: list[int] = []

    @staticmethod
    def index(image: Image.Image) -> int:
        return image.convert("RGB").getpixel((5, 5))[0] - 1

    def read_chars(self, image: Image.Image) -> CharspotReading:
        return self.charspot[self.index(image)]

    def settle(self, image: Image.Image, read: CharspotReading) -> CharspotReading:
        i = self.index(image)
        self.asked.append(i)
        text = self.settled[i]
        return CharspotReading(text if text is not None else read.text, read.chars, read.score, split=text is not None)


def page(n: int, kind: str = "bubble") -> tuple[np.ndarray, list[TextRegion]]:
    rgb = np.full((60 * n + 20, 200, 3), 255, np.uint8)
    regions = []
    for i in range(n):
        y0 = 10 + 60 * i
        rgb[y0:y0 + 50, 10:190] = (i + 1, 200, 200)
        regions.append(TextRegion(10, y0, 190, y0 + 50, np.full((50, 180), 255, np.uint8), (10, y0, 190, y0 + 50), kind=kind))
    return rgb, regions


def run(engine: Engine, kind: str = "bubble", cancel: threading.Event | None = None) -> list[TextRegion]:
    rgb, regions = page(len(engine.charspot), kind)
    Pipeline(Settings(), ocr=engine, translator=None)._ocr_regions(rgb, regions, lambda _m: None, cancel=cancel)
    return regions


def test_the_others_are_asked_only_about_what_passed_charspot_s_gate():
    engine = Engine([reading("今日はいい天気"), reading("明日は雨だろう", score=0.5)], ["今日はいい天気だ", None])
    regions = run(engine)
    assert engine.asked == [0]
    assert regions[0].source_text == "今日はいい天気だ" and [r.status for r in regions] == ["untranslated", "low-confidence"]
    assert regions[1].source_text == "明日は雨だろう"


def test_a_settled_text_keeps_charspot_s_score_and_is_judged_again():
    engine = Engine([reading("今日はいい天気", score=0.92), reading("明日は雨だろう")], [None, "!!!!!!"])
    regions = run(engine)
    assert regions[0].ocr_confidence == pytest.approx(0.92)
    assert regions[1].status == "not-japanese"


def test_a_region_the_reader_added_is_read_by_all_of_them_whatever_charspot_thought():
    engine = Engine([CharspotReading(), reading("あ", 200, 0.1)], ["そうだね", "違うよ"])
    regions = run(engine, kind="manual")
    assert engine.asked == [0, 1]
    assert [r.source_text for r in regions] == ["そうだね", "違うよ"] and [r.status for r in regions] == ["untranslated"] * 2


def test_readers_that_split_flag_the_line_through_the_confidence():
    engine = Engine([reading("今日はいい天気", score=0.95), reading("明日は雨だろう", score=0.95)], ["昨夜はひどい雨", None])
    engine.settle = lambda image, read: CharspotReading(read.text, read.chars, read.score, split=Engine.index(image) == 0)
    regions = run(engine)
    assert regions[0].ocr_split and regions[0].ocr_confidence == SPLIT_CONFIDENCE < OCR_UNSURE
    assert not regions[1].ocr_split and regions[1].ocr_confidence == pytest.approx(0.95)
    assert flags_for("今日はいい天気", "Nice day.", 14, Settings(), confidence=regions[0].ocr_confidence) == ["ocr"]


def test_the_same_crop_is_not_asked_twice():
    engine = Engine([reading("今日はいい天気")], [None])
    rgb, regions = page(1)
    pipeline = Pipeline(Settings(), ocr=engine, translator=None)
    pipeline._ocr_regions(rgb, regions, lambda _m: None)
    pipeline._ocr_regions(rgb, regions, lambda _m: None)
    assert engine.asked == [0]


def test_stop_ends_the_reading_between_regions():
    cancel = threading.Event()
    engine = Engine([reading("今日はいい天気"), reading("明日は雨だろう"), reading("明後日も雨だ")], [None, None, None])
    real = engine.settle

    def then_stop(image, read):
        cancel.set()
        return real(image, read)

    engine.settle = then_stop
    with pytest.raises(Cancelled):
        run(engine, cancel=cancel)
    assert engine.asked == [0]


def test_an_engine_without_others_reads_alone(sample_page, settings):
    res = Pipeline(settings, ocr=FakeOcr(), translator=None).process(sample_page, translate=False, use_cache=False)
    assert res.regions


# ---------------------------------------------------------------- short lines all three read


class Unanimous(Engine):
    """`Engine` that also says whether the others read charspot's text (per region), and what it was asked."""

    def __init__(self, charspot: list[CharspotReading], same: list[bool]):
        super().__init__(charspot, [None] * len(charspot))
        self.same = same
        self.asked_all: list[tuple[int, str]] = []

    @staticmethod
    def index(image: Image.Image) -> int:
        red = image.convert("RGB").getpixel((5, 5))[0]
        return red - 1 if red < 128 else 254 - red  # a dark region's crop is turned dark-on-light

    def unanimous(self, image: Image.Image, text: str) -> bool:
        i = self.index(image)
        self.asked_all.append((i, text))
        return self.same[i]


def small_bubbles(n: int, kind: str = "bubble", pieces: int = 2) -> tuple[np.ndarray, list[TextRegion]]:
    """*n* regions as small as a bubble cut down to a word's lettering (under ``min_short_bubble``)."""
    rgb = np.full((60 * n + 20, 100, 3), 255, np.uint8)
    regions = []
    for i in range(n):
        y0 = 10 + 60 * i
        rgb[y0:y0 + 44, 10:54] = (i + 1, 200, 200)
        regions.append(TextRegion(10, y0, 54, y0 + 44, np.full((44, 44), 255, np.uint8), (10, y0, 54, y0 + 44),
                                  kind=kind, pieces=pieces))
    return rgb, regions


def read_small(engine: Unanimous, kind: str = "bubble", pieces: int = 2) -> list[TextRegion]:
    rgb, regions = small_bubbles(len(engine.charspot), kind, pieces)
    Pipeline(Settings(), ocr=engine, translator=None)._ocr_regions(rgb, regions, lambda _m: None)
    return regions


def test_one_character_in_a_bubble_is_a_line_when_all_three_read_it():
    """Charspot's gate wants two characters: a bubble's one-character line passes when nar and CPT read it too."""
    engine = Unanimous([reading("よ", score=0.99), reading("嘘", score=0.99)], [True, False])
    regions = read_small(engine)
    assert engine.asked_all == [(0, "よ"), (1, "嘘")]
    assert [r.status for r in regions] == ["untranslated", "ocr-noise"]
    assert regions[0].source_text == "よ" and regions[0].ocr_confidence == pytest.approx(0.99)


def test_a_short_line_charspot_is_less_sure_of_needs_all_three():
    engine = Unanimous([reading("ねえ", score=0.92), reading("ねえ", score=0.92), reading("ねえ", score=0.89)],
                       [True, False, True])
    regions = read_small(engine)
    assert [r.status for r in regions] == ["untranslated", "ocr-noise", "ocr-noise"]
    assert [i for i, _ in engine.asked_all] == [0, 1]  # under the unanimous bar nobody is asked


def test_a_short_line_charspot_carries_alone_is_not_asked_about():
    engine = Unanimous([reading("ねえ", score=0.97)], [False])
    regions = read_small(engine)
    assert regions[0].status == "untranslated" and engine.asked_all == []


@pytest.mark.parametrize("text", ["ドン", "っ", "ー", "〜あ", "まさか"])
def test_what_is_no_short_line_is_not_asked_about(text):
    """Katakana (pieces of sound effects), a small kana or a mark at the start, three characters."""
    engine = Unanimous([reading(text, score=0.99)], [True])
    read_small(engine)
    assert engine.asked_all == []


@pytest.mark.parametrize("kind", ["text", "text-dark"])
def test_lettering_without_an_outline_has_no_short_lines_whatever_the_readers_say(kind):
    engine = Unanimous([reading("よ", score=0.99), reading("ねえ", score=0.92)], [True, True])
    regions = read_small(engine, kind)
    assert engine.asked_all == [] and [r.status for r in regions] == ["ocr-noise"] * 2


def test_a_face_read_as_one_character_stays_noise_whatever_the_readers_say():
    engine = Unanimous([reading("よ", score=0.99)], [True])
    regions = read_small(engine, pieces=4)
    assert engine.asked_all == [] and regions[0].status == "ocr-noise"


def test_a_piece_of_another_region_s_lettering_is_no_short_line_whatever_the_readers_say():
    """A small white area cut down to two characters of a longer line's lettering: all three read them alike."""
    engine = Unanimous([reading("よ", score=0.99), reading("よ", score=0.99)], [True, True])
    rgb, regions = small_bubbles(2)
    column = TextRegion(0, 0, 100, 140, np.full((140, 100), 255, np.uint8), (5, 5, 95, 135), kind="text", pieces=9)
    Pipeline(Settings(), ocr=engine, translator=None)._ocr_regions(rgb, regions[:1], lambda _m: None, read=[column])
    assert engine.asked_all == [] and regions[0].status == "ocr-noise"
    away = TextRegion(0, 0, 100, 60, np.full((60, 100), 255, np.uint8), (60, 5, 95, 50), kind="text", pieces=9)
    Pipeline(Settings(), ocr=engine, translator=None)._ocr_regions(rgb, regions[:1], lambda _m: None, read=[away])
    assert engine.asked_all == [(0, "よ")] and regions[0].status == "untranslated"  # (beside it: a line)
    twin = TextRegion(8, 8, 56, 56, np.full((48, 48), 255, np.uint8), (12, 12, 56, 56), kind="bubble", pieces=2)
    engine.asked_all.clear()
    Pipeline(Settings(), ocr=engine, translator=None)._ocr_regions(rgb, regions[:1], lambda _m: None, read=[twin])
    assert regions[0].status == "untranslated"  # the other detector's region of the same lettering: still a line


def test_the_others_are_asked_once_about_the_same_crop():
    engine = Unanimous([reading("よ", score=0.99)], [True])
    rgb, regions = small_bubbles(1)
    pipeline = Pipeline(Settings(), ocr=engine, translator=None)
    pipeline._ocr_regions(rgb, regions, lambda _m: None)
    pipeline._ocr_regions(rgb, regions, lambda _m: None)
    assert engine.asked_all == [(0, "よ")] and regions[0].status == "untranslated"


class _Reads:
    def __init__(self, text: str):
        self.text = text

    def read(self, image: Image.Image) -> str:
        return self.text


def bare_readers(nar: str | None, cpt: str | None) -> Readers:
    readers = object.__new__(Readers)
    readers._nar = None if nar is None else _Reads(nar)
    readers._cpt = None if cpt is None else _Reads(cpt)
    return readers


def test_unanimous_compares_as_readings_are_compared():
    image = Image.new("RGB", (8, 8))
    assert bare_readers("よ…", "よ...").unanimous(image, "よ…")
    assert not bare_readers("よ", "ょ").unanimous(image, "よ")
    assert not bare_readers("嘘", "嘘").unanimous(image, "")
    assert not bare_readers(None, None).unanimous(image, "よ")  # charspot alone: never unanimous


# ---------------------------------------------------------------- what is installed


def install(models: Path, *which) -> None:
    for model in which:
        folder = models / model.dirname
        folder.mkdir(parents=True)
        for name in model.required:
            (folder / name).write_text("{}")


def stub_charspot(monkeypatch) -> list[tuple]:
    made: list[tuple] = []
    monkeypatch.setattr(R, "CharspotEngine", lambda path, threads=0: made.append((Path(path).name, threads)) or object())
    return made


def test_without_the_others_charspot_reads_alone_with_one_quiet_line(tmp_path, monkeypatch, caplog):
    install(tmp_path, OCR_MODELS[0])
    made = stub_charspot(monkeypatch)
    with caplog.at_level(logging.INFO, logger=R.__name__):
        readers = Readers(tmp_path, 3)
    assert made == [(OCR_MODELS[0].dirname, 3)] and readers.missing == [m.dirname for m in OCR_SECOND_READERS]
    assert len(caplog.records) == 1 and caplog.records[0].levelno == logging.INFO
    read = reading("そうだ")
    assert readers.settle(Image.new("RGB", (8, 8)), read) is read


@pytest.mark.parametrize("left", OCR_SECOND_READERS, ids=lambda m: m.dirname)
def test_one_of_the_others_is_not_enough(tmp_path, monkeypatch, left):
    install(tmp_path, OCR_MODELS[0], left)
    stub_charspot(monkeypatch)
    assert len(Readers(tmp_path).missing) == 1


def test_missing_readers_looks_at_each_required_file(tmp_path):
    install(tmp_path, *OCR_SECOND_READERS)
    assert missing_readers(tmp_path) == []
    (tmp_path / OCR_SECOND_READERS[1].dirname / "model.safetensors").unlink()
    assert missing_readers(tmp_path) == [OCR_SECOND_READERS[1].dirname]


def test_a_window_with_one_reader_says_so_in_a_line_of_its_own_message():
    assert Message("ocr.one_reader") == "The Japanese reader is running in its basic form. Double-click install.cmd to read better."


# ---------------------------------------------------------------- the real models

def all_three() -> bool:
    return ocr_installed() and not missing_readers(Settings().models_dir)


real = pytest.mark.skipif(not all_three(), reason="OCR models not downloaded (run setup_models.py)")


@real
def test_real_readers_read_the_sample_bubbles_on_the_cpu(sample_page, sample_truth, settings):
    import difflib

    import torch

    st = netguard.install()
    blocked = len(st.blocked)
    engine = Readers(settings.models_dir, 2)
    assert not engine.missing and torch.get_num_threads() == 2
    good = 0
    for t in sample_truth:
        x0, y0, x1, y1 = t["text_box"]
        crop = sample_page.crop((x0 - 12, y0 - 12, x1 + 12, y1 + 12))
        first = engine.read_chars(crop)
        settled = engine.settle(crop, first)
        assert (settled.chars, settled.score) == (first.chars, first.score)
        good += difflib.SequenceMatcher(None, settled.text, t["text"]).ratio() >= 0.6
    assert good >= len(sample_truth) - 1 and len(st.blocked) == blocked


@real
def test_real_second_readers_read_a_small_crop_without_harm(settings):
    engine = Readers(settings.models_dir)
    crop = Image.new("RGB", (3, 2), "white")
    assert isinstance(engine._nar.read(crop), str) and isinstance(engine._cpt.read(crop), str)
