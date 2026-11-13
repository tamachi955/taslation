"""The OpenMantra tools: the fetcher on a synthetic archive, the loader on a synthetic annotation, the IoU matcher,
the scores and their aggregation. With the dataset fetched (tools/fetch_openmantra.py) and TASLATION_REALDATA=1,
one real page is also run through detection and the OCR."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import fetch_openmantra  # noqa: E402
import openmantra  # noqa: E402
import openmantra_eval  # noqa: E402

from conftest import requires_ocr  # noqa: E402

LICENSE = "# Creative Commons Attribution-NonCommercial 4.0 International\n\nThe licence text.\n"
README = ("# OpenMantra dataset\n\n## Citation\n\n```\n@article{test_2021,\n    author={A and B},\n"
          "    title={A Title},\n    year={2021}\n}\n```\n")


def write_dataset(root: Path, en_image: bool = False) -> None:
    """A tiny dataset in the real file's format: two series, the Japanese page images (blank), one with an
    English page beside it; a bubble with a box of no size and a page whose image path leads outside."""
    root.mkdir(parents=True, exist_ok=True)
    data = [
        {"book_title": "series_a", "pages": [
            {"page_index": 2, "image_paths": {"ja": "images/series_a/ja/001.jpg"},
             "frame": [{"x": 0, "y": 0, "w": 100, "h": 150}],
             "text": [{"x": 50, "y": 10, "w": 20, "h": 60, "text_ja": "二ページ目", "text_en": "Page two", "text_zh": "第二页"}]},
            {"page_index": 1, "image_paths": {"ja": "images/series_a/ja/000.jpg"},
             "frame": [{"x": 0, "y": 0, "w": 100, "h": 70}, {"x": 0, "y": 80, "w": 100, "h": 70}],
             "text": [{"x": 70, "y": 10, "w": 20, "h": 50, "text_ja": "こんにちは", "text_en": "Hello", "text_zh": "你好"},
                      {"x": 10, "y": 90, "w": 0, "h": 40, "text_ja": "x", "text_en": "x", "text_zh": "x"},
                      {"x": 10, "y": 90, "w": 30, "h": 40, "text_ja": "", "text_en": "(sign)", "text_zh": ""}]},
        ]},
        {"book_title": "series_b", "pages": [
            {"page_index": 1, "image_paths": {"ja": "images/series_b/ja/000.jpg"}, "frame": [],
             "text": [{"x": 5, "y": 5, "w": 30, "h": 30, "text_ja": "はい", "text_en": "Yes", "text_zh": "是"}]},
            {"page_index": 2, "image_paths": {"ja": "../outside.jpg"}, "frame": [], "text": []},
        ]},
    ]
    (root / "annotation.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    for rel in ("images/series_a/ja/000.jpg", "images/series_a/ja/001.jpg", "images/series_b/ja/000.jpg"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (100, 150), "white").save(root / rel)
    if en_image:
        (root / "images/series_a/en").mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (100, 150), "white").save(root / "images/series_a/en/000.jpg")


# ---------------------------------------------------------------------------------------------------- loader
def test_loader_reads_the_annotation_format(tmp_path):
    root = tmp_path / "openmantra"
    write_dataset(root, en_image=True)
    pages = openmantra.load(root)
    assert [(p.series, p.index) for p in pages] == [("series_a", 1), ("series_a", 2), ("series_b", 1)]  # by page_index
    first = pages[0]
    assert first.image == root / "images/series_a/ja/000.jpg" and first.images["ja"] == first.image
    assert first.en_image == root / "images/series_a/en/000.jpg" and first.zh_image is None  # picked up beside ja
    assert pages[1].en_image is None
    assert [b.box for b in first.bubbles] == [(70, 10, 90, 60), (10, 90, 40, 130)]  # the box of no size is left out
    assert (first.bubbles[0].ja, first.bubbles[0].en, first.bubbles[0].zh) == ("こんにちは", "Hello", "你好")
    assert first.frames == [(0, 0, 100, 70), (0, 80, 100, 150)]
    assert first.open().size == (100, 150) and first.open("en").mode == "RGB"
    with pytest.raises(FileNotFoundError):
        first.open("zh")
    assert openmantra.series_names(pages) == ["series_a", "series_b"]
    assert [p.index for p in openmantra.by_series(pages)["series_a"]] == [1, 2]
    assert [p.series for p in openmantra.load(root, "series_b")] == ["series_b"]
    assert len(openmantra.load(root, ["series_a", "series_b"])) == 3
    with pytest.raises(FileNotFoundError):
        openmantra.load(tmp_path / "nothing")


# --------------------------------------------------------------------------------------------------- matcher
def test_matcher_pairs_one_to_one_largest_overlap_first():
    gold = [(0, 0, 10, 10), (20, 0, 30, 10), (100, 100, 110, 110)]
    regions = [(1, 0, 11, 10), (0, 0, 10, 10), (20, 0, 29, 10), (200, 200, 210, 210)]
    pairs = openmantra_eval.match(gold, regions)
    assert [(g, r) for g, r, _v in pairs] == [(0, 1), (1, 2)]  # the exact box wins over the shifted one; no double use
    assert pairs[0][2] == 1.0 and abs(pairs[1][2] - 0.9) < 1e-9
    assert openmantra_eval.match(gold, [(0, 0, 10, 4)]) == []  # IoU 0.4: under the threshold
    assert openmantra_eval.match(gold, [(0, 0, 10, 4)], threshold=0.4)[0][:2] == (0, 0)
    # a region as its bubble box and its lettering box: the better of the two counts
    bubble, lettering = (0, 0, 40, 40), (1, 1, 10, 10)
    assert openmantra_eval.match([(0, 0, 10, 10)], [(bubble, lettering)])[0][:2] == (0, 0)
    assert openmantra_eval.match([(0, 0, 40, 38)], [(bubble, lettering)])[0][:2] == (0, 0)
    assert openmantra_eval.match([], regions) == [] and openmantra_eval.match(gold, []) == []


def test_scores():
    assert openmantra_eval.chrf("Hello there", "hello there") == pytest.approx(100.0)
    assert openmantra_eval.chrf("", "hello") == 0.0 and openmantra_eval.chrf("hello", "") == 0.0
    assert 0 < openmantra_eval.chrf("Hello", "Hello there") < openmantra_eval.chrf("Hello ther", "Hello there") < 100
    assert openmantra_eval.prf(3, 4, 6) == {"precision": 0.75, "recall": 0.5, "f1": 0.6}
    assert openmantra_eval.prf(0, 0, 0) == {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    stats = openmantra_eval.cer_stats([(0.0, 4), (0.5, 2), (2.0, 2)])
    assert stats == {"n": 3, "mean": round(2.5 / 3, 4), "capped": 0.5, "corpus": 0.625, "right": 1, "wrong": 2}
    assert openmantra_eval.cer_stats([]) == {"n": 0}
    assert openmantra_eval.ja_line(openmantra.Bubble((0, 0, 1, 1), "こん にちは\nさん", "", "")) == "こんにちはさん"


# ----------------------------------------------------------------------------------------------- aggregation
def _row(series, gold, cands, cand_matched, found=None, matched=None, gold_ocr=None, matched_ocr=None, lines=None):
    row = {"series": series, "page": 1, "gold": gold, "candidates": cands, "candidates_matched": cand_matched}
    if found is not None:
        row.update(found=found, found_matched=matched, gold_ocr=gold_ocr or [], matched_ocr=matched_ocr or [])
    if lines is not None:
        row["lines"] = lines
    return row


def test_aggregation_per_series_and_overall():
    line = lambda c, flags=(): {"chrf": c, "real": c > 0, "flags": list(flags)}  # noqa: E731
    rows = [
        _row("a", 10, 20, 8, found=9, matched=7, gold_ocr=[(0.0, 5), (0.2, 5)], matched_ocr=[(0.1, 5)],
             lines=[line(50.0), line(30.0, ["small"]), line(0.0)]),
        _row("a", 5, 6, 5, found=5, matched=4, gold_ocr=[(1.0, 2)], matched_ocr=[], lines=[line(40.0, ["long", "small"])]),
        _row("b", 4, 3, 2, found=2, matched=2, gold_ocr=[], matched_ocr=[(0.5, 4)], lines=[]),
    ]
    summ = openmantra_eval.summarize(rows)
    assert list(summ["by_series"]) == ["a", "b"]
    a, b, everything = summ["by_series"]["a"], summ["by_series"]["b"], summ["all"]
    assert (a["pages"], a["gold"], a["found"], a["matched"]) == (2, 15, 14, 11)
    assert a["precision"] == round(11 / 14, 4) and a["recall"] == round(11 / 15, 4)
    assert a["f1"] == round(2 * (11 / 14) * (11 / 15) / (11 / 14 + 11 / 15), 4)
    assert a["candidate_recall"] == round(13 / 15, 4) and a["candidate_precision"] == round(13 / 26, 4)
    assert a["ocr_gold"]["n"] == 3 and a["ocr_gold"]["corpus"] == round(3.0 / 12, 4) and a["ocr_gold"]["wrong"] == 1
    assert a["ocr_matched"] == {"n": 1, "mean": 0.1, "capped": 0.1, "corpus": 0.1, "right": 1, "wrong": 0}
    assert b["ocr_gold"] == {"n": 0} and b["ocr_matched"]["n"] == 1
    t = a["translation"]
    assert (t["lines"], t["real"], t["chrf"], t["flagged"], t["flagged_share"]) == (4, 3, 30.0, 2, 0.5)
    assert t["by_reason"]["small"] == 2 and t["by_reason"]["long"] == 1 and t["by_reason"]["spelling"] == 0
    assert b["translation"]["lines"] == 0 and b["translation"]["chrf"] == 0.0
    assert (everything["pages"], everything["gold"], everything["found"], everything["matched"]) == (3, 19, 16, 13)
    assert everything["translation"]["lines"] == 4
    report = openmantra_eval.report(summ, 0.5)
    assert "Detection" in report and "OCR" in report and "Translation" in report and "all" in report


def test_aggregation_without_ocr_or_translation():
    summ = openmantra_eval.summarize([_row("a", 4, 5, 2), _row("a", 2, 0, 0)])
    s = summ["all"]
    assert s["candidate_recall"] == round(2 / 6, 4) and s["candidate_precision"] == round(2 / 5, 4)
    assert "found" not in s and "ocr_gold" not in s and "translation" not in s
    report = openmantra_eval.report(summ, 0.5)
    assert "no OCR" in report and "CER" not in report and "Translation" not in report


def test_recall_leaves_the_punctuation_only_gold_boxes_out():
    # 10 gold boxes, 2 of them "..." or "!?": 8 found right, one of them on a punctuation-only box
    row = _row("a", 10, 12, 8, found=9, matched=8)
    row.update(gold_worded=8, candidates_matched_worded=7, found_matched_worded=7)
    s = openmantra_eval.summarize([row])["all"]
    assert s["precision"] == round(8 / 9, 4)  # a region on a "..." box is found right
    assert s["recall"] == round(7 / 8, 4) and s["recall_all"] == round(8 / 10, 4)
    assert s["f1_all"] == openmantra_eval.prf(8, 9, 10)["f1"] and s["f1"] > s["f1_all"]
    assert s["candidate_recall"] == round(7 / 8, 4) and s["candidate_recall_all"] == round(8 / 10, 4)
    assert openmantra_eval.worded("こんにちは") and openmantra_eval.worded("１")
    assert not any(openmantra_eval.worded(t) for t in ("...", "!?", "ーー", "…！", "一"))


def test_the_kinds_of_gold_lines():
    is_open = openmantra_eval.ends_open
    assert is_open("私は") and is_open("それで…") and is_open("だから、") and is_open("行ったけど...")
    assert not is_open("行くぞ!!") and not is_open("待ってね") and not is_open("...") and not is_open("そうか。")
    roman = openmantra_eval.bare_romanisation
    assert roman("なに", "Nani?") and roman("えっ", "Eh!") and roman("ええ", "Ee...") and roman("ナニ", "nani")
    assert not roman("なに", "What?") and not roman("なにそれ", "nanisore") and not roman("何", "Nani")


def test_the_end_to_end_lines_are_strict_and_lenient():
    page = openmantra.Page("s", 1, Path("x.jpg"), bubbles=[
        openmantra.Bubble((0, 0, 10, 10), "こんにちは", "Hello", ""),
        openmantra.Bubble((20, 0, 30, 10), "はい", "Yes", ""),
        openmantra.Bubble((40, 0, 50, 10), "", "(sign)", "")])
    items = [{"text": "こんにちわ", "gold": 0, "geo": None}, {"text": "ゴゴゴ", "gold": None, "geo": None}]
    lines = openmantra_eval.score_e2e(page, items, {0: ("Hello", []), 1: ("Rumble", [])})
    assert [(ln["matched"], ln["chrf"]) for ln in lines] == [(True, 100.0), (False, 0.0)]  # the empty gold line: none
    summ = openmantra_eval.line_summary(lines)
    assert summ["strict"] == 50.0 and summ["lenient"] == 100.0 and summ["matched"] == 1
    rows = [{"series": "s", "e2e_lines": lines, "e2e_extra": 1}]
    rec = openmantra_eval.arm_record(rows, "e2e_lines")
    assert rec["series"]["s"]["chrf"] == 50.0 and rec["series_lenient"]["s"]["chrf"] == 100.0
    assert rec["extra_regions"] == 1


def test_names_are_scored_by_index_and_rendering():
    names = {"芦藤": [["Ashifuji"], ["Roto", "Ashito"]], "柚葉": [["Yuzuha"], []]}  # accents folded
    hits = openmantra_eval.name_hits
    assert hits("芦藤の奴が", "that ashifuji guy", "That guy Ashitō", names) == [[0, 2, 0]]
    assert hits("芦藤の奴が", "that ashifuji guy", "That guy Ashifuji", names) == [[0, 0, 1]]
    assert hits("芦藤の家", "my family", "The Ashifuji house", names) == []  # the reference does not name him
    assert hits("柚葉か", "yuzuha", "You Ye, huh?", names) == [[1, -1, 0]]
    lines = [{"names": [[0, 2, 0]]}, {"names": [[0, 2, 0]]}, {"names": [[0, 0, 1]]}, {"names": [[1, -1, 0]]}]
    summ = openmantra_eval.name_summary(lines, ["s"] * 4)
    assert summ["lines"] == 4 and summ["as_reference"] == 1 and summ["names"] == 2
    assert summ["consistent"] == round(2 / 3, 4) and summ["consistency_lines"] == 3  # a name of one line left out


# ---------------------------------------------------------------------------------------------------- fetcher
def make_archive(path: Path, top: str = "open-mantra-dataset-main", extra: dict[str, bytes] | None = None,
                 skip: tuple[str, ...] = ()) -> Path:
    files = {f"{top}/annotation.json": b"[]", f"{top}/LICENSE.md": LICENSE.encode(), f"{top}/README.md": README.encode(),
             f"{top}/images/s/ja/000.jpg": b"jpeg bytes", f"{top}/tools/run_me.py": b"print('never run')"}
    files.update(extra or {})
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{top}/", b"")
        for name, data in files.items():
            if not any(name.endswith(s) for s in skip):
                zf.writestr(name, data)
    return path


def test_fetch_extracts_what_is_needed_and_records_the_source(tmp_path):
    (tmp_path / "dl").mkdir()
    archive = make_archive(tmp_path / "dl" / "a.zip")
    target = tmp_path / "datasets" / "openmantra"
    counts = fetch_openmantra.fetch(target, archive.as_uri())
    assert counts["series"] == 0 and counts["images"] == 1 and counts["archive_bytes"] == archive.stat().st_size
    assert (target / "images/s/ja/000.jpg").read_bytes() == b"jpeg bytes"
    assert not (target / "tools").exists()  # only the data is extracted
    assert (target / "LICENSE.md").read_text(encoding="utf-8") == LICENSE  # copied as is
    source = (target / "SOURCE.md").read_text(encoding="utf-8")
    assert hashlib.sha256(archive.read_bytes()).hexdigest() in source and archive.as_uri() in source
    assert "Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)" in source
    assert "@article{test_2021," in source and "title={A Title}" in source
    # a second run refuses the folder that is not empty; --force replaces only what the first run put there
    with pytest.raises(fetch_openmantra.FetchError):
        fetch_openmantra.fetch(target, archive.as_uri())
    (target / "results").mkdir()
    (target / "results" / "mine.json").write_text("{}", encoding="utf-8")
    fetch_openmantra.fetch(target, archive.as_uri(), force=True)
    assert (target / "results" / "mine.json").exists() and (target / "SOURCE.md").exists()
    assert fetch_openmantra.remove_previous(target) == 6  # the archive's 4 files, SOURCE.md and the manifest
    assert sorted(p.name for p in target.iterdir()) == ["results"]


def test_fetch_refuses_an_archive_that_is_not_the_dataset(tmp_path):
    def check(path):
        with zipfile.ZipFile(path) as zf:
            return fetch_openmantra.check_archive(zf)

    top, members = check(make_archive(tmp_path / "ok.zip"))
    assert top == "open-mantra-dataset-main"
    assert sorted(rel for _i, rel in members) == ["LICENSE.md", "README.md", "annotation.json", "images/s/ja/000.jpg"]
    with pytest.raises(fetch_openmantra.FetchError, match="lacks annotation.json"):
        check(make_archive(tmp_path / "missing.zip", skip=("annotation.json",)))
    with pytest.raises(fetch_openmantra.FetchError, match="top-level"):
        check(make_archive(tmp_path / "two.zip", extra={"other/file.txt": b"x"}))
    with pytest.raises(fetch_openmantra.FetchError, match="unsafe"):
        check(make_archive(tmp_path / "slip.zip", extra={"open-mantra-dataset-main/../../evil.txt": b"x"}))
    target = tmp_path / "t"
    not_zip = tmp_path / "not.zip"
    not_zip.write_bytes(b"not a zip")
    with pytest.raises(fetch_openmantra.FetchError, match="not a zip"):
        fetch_openmantra.fetch(target, not_zip.as_uri())
    assert fetch_openmantra.licence_name("no heading here\n") == "no heading here"
    assert fetch_openmantra.bibtex("see @inproceedings{x, title={T {nested}}} and more") == "@inproceedings{x, title={T {nested}}}"
    assert fetch_openmantra.bibtex("nothing to cite") == ""


# -------------------------------------------------------------------------------------------------- real data
REAL = openmantra.DEFAULT_ROOT
real_data = pytest.mark.skipif(not (REAL / "annotation.json").is_file() or os.environ.get("TASLATION_REALDATA") != "1",
                               reason="the OpenMantra dataset is not fetched, or TASLATION_REALDATA is not 1")
REAL_PAGE = ("tojime_no_siora", 4)  # a page of dialogue in bubbles, ten gold boxes


@real_data
def test_real_data_loads():
    pages = openmantra.load(REAL)
    assert len(openmantra.series_names(pages)) == 5 and len(pages) == 214
    assert sum(len(p.bubbles) for p in pages) == 1592 and all(p.image.is_file() for p in pages)


@real_data
@requires_ocr
def test_real_page_detection_and_ocr():
    from taslation.config import Settings
    from taslation.ocr import CharspotEngine
    from taslation.pipeline import Pipeline

    page = next(p for p in openmantra.load(REAL, REAL_PAGE[0]) if p.index == REAL_PAGE[1])
    s = Settings()
    ocr = CharspotEngine(s.ocr_model_dir)
    row, _geo, _items = openmantra_eval.score_page(Pipeline(s, ocr=ocr, translator=None, cache=None), ocr, page,
                                                  page.open())
    assert row["found_matched"] >= row["gold"] / 2  # detection finds at least half of the gold boxes
    assert openmantra_eval.cer_stats(row["gold_ocr"])["corpus"] < 0.4  # the OCR on the gold boxes
