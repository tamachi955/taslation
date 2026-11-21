"""The README's introduction tool (tools/intro_video.py) without a window, a model or a manga page: the scenes'
table (ids, order, what this checkout has, texts that fit a 960x540 frame, headers on one line), the scenes picked and
numbered as the GIF is made, every card line and step following sentences that still stand word for word in README.md,
docs/MANUAL.md or docs/THIRD_PARTY.md (or marked as the tool's own words), the cards' facts against the code's
constants and with nothing that compares or boasts, the version on the
title card and the credit on every frame with a page, the 5 MB limit, a GIF of made-up frames and one of a recording
(deleted once the GIF is written), no page text in a recording's facts, and the guard that refuses another
program's window."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import demo_video as dv  # noqa: E402
import intro_video as iv  # noqa: E402
import promo_video as pv  # noqa: E402

ORDER = ("viewer", "next_page", "original", "turned_past", "language", "sheet", "edit", "region", "undo", "add_region",
         "full_screen", "whole_book")


def quick(**kw) -> iv.Options:
    """Options for a small, quick GIF."""
    values = {"fps": 4.0, "title_s": 0.5, "card_s": 0.5}
    values.update(kw)
    return iv.Options(**values)


def small_sample(ids=("viewer", "next_page"), seconds: float = 1.0, fps: float = 3.0) -> iv.MemorySource:
    return iv.sample_source(list(ids), seconds=seconds, fps=fps)


# ---------------------------------------------------------------------------------------------------- the scenes
def test_the_scenes_ids_are_unique_and_in_the_order_of_the_introduction():
    assert iv.SCENE_IDS == ORDER
    assert len(set(iv.SCENE_IDS)) == len(iv.SCENE_IDS)
    for scene in iv.SCENES:
        assert scene.title and scene.description and scene.budget_s > 0
        assert not any(ch.isdigit() for ch in scene.title)  # (numbers are given as the GIF is made)
        assert scene.role in ("reader", "translator")


def test_every_step_fits_the_left_column_at_960x540():
    facts = iv.code_facts()
    layout = iv.Layout(iv.SIZE)
    for scene in iv.SCENES:
        title, description = iv.step_texts(scene, facts)
        assert "{" not in title + description, scene.id
        (tsize, tlines), (dsize, dlines) = layout.step(title, description)
        assert len(tlines) <= 2 and len(dlines) <= 5, scene.id
        assert tsize >= layout.title_px[1] and dsize >= layout.desc_px[1]
    for header, width in ((iv.LEFT_HEADER, layout.col), (iv.RIGHT_HEADER, layout.right[2] - layout.right[0])):
        size, label, note = layout.header(header, width)
        assert layout.header_fits(header, width), header  # (one line: a bold label and a lighter note)
        assert size >= layout.header_px[1] and label and note and f"{label}{iv.HEADER_SEP}{note}" == header
    assert layout.header(iv.LEFT_HEADER, 200)[0] < layout.header(iv.LEFT_HEADER, 400)[0]  # (smaller where narrower)
    assert not layout.header_fits(iv.LEFT_HEADER, 100)
    assert len(layout.cap_lines()[1]) == 1


def test_the_page_turn_is_named_on_the_fly_translation_with_no_timing_figures():
    title, description = iv.step_texts(iv.scene_of("next_page"), iv.code_facts())
    assert title == "On-the-fly translation"
    assert description.startswith("When you turn a page, its bubbles are replaced by their translations there and "
                                  "then, in reading order.")
    assert description.endswith(" Press the page key in TASlation; it is passed on to your viewer.")
    assert not any(ch.isdigit() for ch in description) and "second" not in description


# ---------------------------------------------------------------------------------------------------- what follows what
def flat(text: str) -> str:
    return " ".join(text.split())


def every_line(present_only: bool = False):
    """(where, follows, own) of each card line and each step's description (only the steps this checkout can show
    with *present_only*: a step whose feature is not here has no sentence in this checkout's documents yet)."""
    for kind, (_heading, lines) in iv.CARDS.items():
        for line in lines:
            yield f"card {kind}: {line.text[:50]}", line.follows, line.own
    for scene in iv.SCENES:
        if scene.present() or not present_only:
            yield f"step {scene.id}", scene.follows, scene.own


def test_every_card_line_and_step_follows_a_document_or_is_marked_the_tools_own():
    for where, follows, own in every_line():
        assert follows or own.strip(), where
        assert all(isinstance(cite, iv.Cite) and cite.doc in iv.DOCS and cite.quote.strip() for cite in follows), where
    owns = {where for where, _follows, own in every_line() if own}
    assert owns == {"card title: Recorded with version {version}", "step language"}


def documents() -> dict[str, str]:
    return {doc: flat((ROOT / doc).read_text(encoding="utf-8")) for doc in iv.DOCS}


def stale_lines(facts: dict, docs: dict[str, str]) -> list[str]:
    """The lines with a quote that does not stand in its document, once *facts* are put in."""
    stale = []
    for where, follows, _own in every_line(present_only=True):
        for cite in follows:
            quote = iv.filled(cite.quote, facts)
            assert quote is not None, (where, cite.quote)  # (a fact the code does not have)
            if flat(quote) not in docs[cite.doc]:
                stale.append(f"{where}: {cite.doc} no longer says {quote!r}")
    return stale


def test_every_quote_still_stands_in_its_document_word_for_word():
    stale = stale_lines(iv.code_facts(), documents())
    assert not stale, "\n".join(stale)


def test_a_changed_sentence_or_a_changed_figure_makes_its_line_stale():
    facts, docs = iv.code_facts(), documents()
    changed = dict(docs, **{iv.README: docs[iv.README].replace("| Network | Used only when installing and updating |",
                                                               "| Network | Used only while installing |")})
    assert [s.split(":")[0] for s in stale_lines(facts, changed)] == ["card privacy"]
    assert stale_lines(facts, changed)[0].startswith("card privacy: The network is used only when installing")
    assert "no longer says '| Network | Used only when installing and updating |'" in stale_lines(facts, changed)[0]
    other = dict(facts, plamo_gb="9.9")  # (the code's figure no longer what the README says)
    assert {s.split(":")[0] for s in stale_lines(other, docs)} == {"card models"}


def test_a_scene_is_present_only_where_this_checkout_has_what_it_shows(monkeypatch):
    here = {row["id"]: row["present"] for row in iv.scene_rows()}
    assert here["turned_past"] == ((ROOT / "taslation" / "backlog.py").is_file()
                                   and (ROOT / "taslation" / "ui" / "side.py").is_file())
    assert all(present for scene_id, present in here.items() if scene_id != "turned_past")
    absent = {"taslation.backlog", "taslation.ui.dialogs.batch"}
    monkeypatch.setattr(iv, "has_module", lambda name: name not in absent)
    rows = {row["id"]: row["present"] for row in iv.scene_rows()}
    assert rows["turned_past"] is False and rows["whole_book"] is False
    assert rows["viewer"] is True and rows["undo"] is True
    picked = [s.id for s in iv.pick_scenes(None)]
    assert "turned_past" not in picked and "whole_book" not in picked and len(picked) == len(ORDER) - 2
    with pytest.raises(SystemExit, match="not in this checkout"):
        iv.pick_scenes("viewer,whole_book")


def test_scenes_are_picked_in_the_tables_order_and_an_unknown_one_ends_the_run():
    assert [s.id for s in iv.pick_scenes("undo, viewer,language")] == ["viewer", "language", "undo"]
    assert [s.id for s in iv.pick_scenes("")] == [s for s in ORDER if iv.scene_of(s).present()]
    with pytest.raises(SystemExit, match="no such scene: nope"):
        iv.pick_scenes("viewer,nope")


def test_the_scenes_are_numbered_as_the_gif_is_made():
    source = small_sample(("viewer", "language", "undo"))
    numbers = [(p.id, p.number) for p in iv.plan(source, quick()) if p.kind == "scene"]
    assert numbers == [("viewer", 1), ("language", 2), ("undo", 3)]
    numbers = [(p.id, p.number) for p in iv.plan(source, quick(scenes=["language", "undo"])) if p.kind == "scene"]
    assert numbers == [("language", 1), ("undo", 2)]
    source.meta["scenes"][1]["failed"] = "timed out: the page in Spanish"  # (a failed scene is left out)
    numbers = [(p.id, p.number) for p in iv.plan(source, quick()) if p.kind == "scene"]
    assert numbers == [("viewer", 1), ("undo", 2)]
    kinds = [p.id for p in iv.plan(source, quick())]
    assert kinds[0] == "title" and kinds[-4:] == list(iv.CARD_ORDER)


def test_a_wait_for_the_models_is_shown_faster_and_a_still_wait_is_cut():
    entry = {"id": "viewer", "t0": 0.0, "t1": 30_000.0, "fast": [[2000.0, 28_000.0]], "failed": ""}
    changes = [float(t) for t in range(0, 30_001, 500)]
    segments, factor = iv.scene_segments(entry, changes, budget_ms=10_000, longest_ms=1200)
    assert factor == pytest.approx(26_000 / (10_000 - 4000), abs=0.05)  # R / (budget - S)
    shown = sum((b - a) / f for a, b, f, _fast in segments)
    assert shown == pytest.approx(10_000, rel=0.02)
    assert all(f == 1.0 for a, b, f, fast in segments if not fast)
    segments, factor = iv.scene_segments(entry, changes, budget_ms=1000, longest_ms=1200)
    assert factor == iv.MAX_SPEED  # (never faster than that)
    still = {"id": "undo", "t0": 0.0, "t1": 10_000.0, "fast": [], "failed": ""}
    segments, factor = iv.scene_segments(still, [1000.0, 9000.0], budget_ms=4000, longest_ms=1200)
    assert factor == 1.0
    assert sum(b - a for a, b, _f, _fast in segments) == pytest.approx(1000 + 1200 + 1000)  # 8 s still: 1.2 s left


# ---------------------------------------------------------------------------------------------------- the cards
def test_the_figures_are_the_codes_own():
    import taslation
    from taslation import jurisdictions
    from taslation.config import LAMA_MODEL, OCR_MODELS
    from taslation.i18n import UI_LANGUAGES
    from taslation.translate.models import PLAMO, QWEN, model_for_language
    from taslation.ui.constants import LANGUAGES

    facts = iv.code_facts()
    assert facts["version"] == taslation.__version__
    assert facts["languages"] == len(LANGUAGES) and facts["ui_languages"] == len(UI_LANGUAGES)
    assert facts["ocr_models"] == len(OCR_MODELS) and facts["ocr_word"] == iv.NUMBER_WORDS[len(OCR_MODELS)]
    assert facts["countries"] == len(jurisdictions.JURISDICTIONS)
    assert (facts["plamo"], facts["plamo_gb"]) == (PLAMO.display_name, f"{PLAMO.size_gb:g}")
    assert (facts["qwen"], facts["qwen_gb"]) == (QWEN.display_name, f"{QWEN.size_gb:g}")
    assert facts["lama_licence"] == LAMA_MODEL.licence
    by_qwen = [lang for lang in LANGUAGES if model_for_language(lang) is QWEN]
    assert facts["qwen_languages"] == iv.and_list(by_qwen) and all(lang in facts["qwen_languages"] for lang in by_qwen)


def test_the_cards_say_the_figures_of_the_code():
    facts = iv.code_facts()
    text = {kind: " ".join(t for t, _ in iv.card_lines(kind, facts)[1]) for kind in iv.CARDS}
    assert f"{facts['languages']} languages to translate into, and {facts['ui_languages']} languages" in text["models"]
    assert f"{facts['plamo']} by Preferred Networks" in text["models"] and f"about {facts['plamo_gb']} GB" in text["models"]
    assert f"use {facts['qwen']} (Apache-2.0), about {facts['qwen_gb']} GB" in text["models"]
    assert f"({facts['lama_licence']})" in text["models"]
    assert f"The weights of the {facts['ocr_word']} OCR models are under CC BY-NC-SA 4.0" in text["models"]
    assert f"read by {facts['ocr_word']} OCR models" in text["how"]
    assert f"what {facts['countries']} countries allow" in text["before"]
    assert pv.PROJECT in text["before"]
    assert [style for _t, style in iv.card_lines("how", facts)[1]].count("step") == 5
    assert iv.card_lines("how", facts)[0] == "How a page is translated"
    assert iv.card_lines("models", facts)[0] == "The models"
    assert iv.card_lines("before", facts)[0] == "Before you use it"


def test_a_line_whose_fact_is_missing_is_left_out():
    heading, lines = iv.card_lines("models", {"ocr_word": "three"})
    assert heading == "The models"
    assert [t for t, _ in lines][0].startswith("The weights of the three OCR models")
    assert not any("{" in t for t, _ in lines)


def test_nothing_on_a_card_or_a_step_compares_or_boasts():
    facts = iv.code_facts()
    texts = [t for kind in iv.CARDS for t in [iv.card_lines(kind, facts)[0]] + [x for x, _ in iv.card_lines(kind, facts)[1]]]
    texts += [x for scene in iv.SCENES for x in iv.step_texts(scene, facts)]
    texts += [iv.LEFT_HEADER, iv.RIGHT_HEADER, iv.CAP_PRESSED, iv.CAP_PASSED_ONCE, iv.CAP_PASSED, *iv.HOW_CAPTIONS]
    words = ("chrF", "twice", "faster", "benchmark", " AI", "AI ", "artificial", "%", "better", "compared", " than ",
             "fastest", "best")
    for text in texts:
        for word in words:
            assert word.lower() not in f" {text} ".lower(), (word, text)


def test_the_title_card_shows_the_version_small():
    import taslation

    lines = iv.card_lines("title", iv.code_facts())[1]
    assert (f"Recorded with version {taslation.__version__}", "small") in lines
    assert lines[0] == ("TASlation", "title")


def test_every_frame_with_a_page_carries_the_credit_with_modified():
    facts = iv.code_facts()
    assert pv.CREDIT == "Sample pages: OpenMantra dataset (Mantra Inc., CC BY-NC 4.0), modified"
    source = small_sample(("viewer",))
    part = next(p for p in iv.plan(source, quick()) if p.kind == "scene")
    for kind in ("scene", *iv.CARDS):
        texts = iv.frame_texts(kind, facts, part if kind == "scene" else None)
        assert (pv.CREDIT in texts) == iv.has_page(kind), kind
    assert iv.has_page("scene") and iv.has_page("how")
    assert not any(iv.has_page(kind) for kind in ("title", "models", "privacy", "before"))


def test_the_cards_fit_above_the_foot():
    painter = iv.Painter(small_sample(("viewer",)), quick())
    for kind in iv.CARDS:
        image = painter.card(kind)
        assert image.size == iv.SIZE
        assert painter.bottoms[kind] <= iv.SIZE[1] - 50, kind


# ---------------------------------------------------------------------------------------------------- the GIF
def test_a_gif_of_made_up_frames(tmp_path):
    out = tmp_path / "sample.gif"
    report = iv.render(small_sample(), out, quick(frames_png=tmp_path / "png"))
    with Image.open(out) as gif:
        assert gif.size == iv.SIZE and gif.n_frames >= 2
    assert report["bytes"] == out.stat().st_size and report["bytes"] <= iv.GIF_LIMIT
    assert [p["id"] for p in report["parts"]] == ["title", "viewer", "next_page", *iv.CARD_ORDER]
    assert sum(p["bytes"] for p in report["parts"]) <= report["bytes"]
    assert report["largest"] and report["largest"][0]["bytes"] >= report["largest"][-1]["bytes"]
    pngs = sorted(p.name for p in (tmp_path / "png").iterdir())
    assert "00_title.png" in pngs and "01_viewer_0.png" in pngs
    assert not (tmp_path / "sample.part.gif").exists()


def test_a_gif_over_the_limit_is_refused_and_says_which_scenes_take_the_most(tmp_path):
    out = tmp_path / "big.gif"
    with pytest.raises(iv.TooLarge) as refused:
        iv.render(small_sample(), out, quick(limit=1000))
    report = refused.value.report
    assert report["over_by"] == report["bytes"] - 1000 > 0
    assert report["largest"] and {"id", "bytes"} <= set(report["largest"][0])
    assert not out.exists() and not (tmp_path / "big.part.gif").exists()
    report = iv.render(small_sample(), out, quick(limit=1000, allow_large=True))
    assert out.exists() and report["over_by"] > 0
    assert iv.GIF_LIMIT == 5_000_000


def test_the_gifs_images_are_read_back_with_their_times_and_bytes(tmp_path):
    frames = [Image.new("RGB", (20, 10), colour) for colour in ((200, 0, 0), (0, 200, 0), (0, 0, 200))]
    path = tmp_path / "three.gif"
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=[100, 250, 400], loop=0)
    data = path.read_bytes()
    found = iv.gif_frames(data)
    assert [delay for delay, _size in found] == [100, 250, 400]
    assert sum(size for _delay, size in found) < len(data)


def test_a_frame_stores_only_what_changed_and_reads_back_whole(tmp_path):
    palette = Image.new("RGB", (4, 1))
    for x, colour in enumerate(((10, 10, 10), (200, 30, 30), (30, 200, 30), (240, 240, 240))):
        palette.putpixel((x, 0), colour)
    palette = palette.quantize(colors=4)
    base = Image.new("RGB", (60, 40), (240, 240, 240))
    frames = [base.copy() for _ in range(3)]
    frames[1].paste((200, 30, 30), (5, 5, 15, 15))  # (a bubble lettered)
    frames[2].paste((200, 30, 30), (5, 5, 15, 15))
    frames[2].paste((30, 200, 30), (40, 25, 50, 35))  # (the pointer elsewhere)
    paletted = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    stored = list(iv.changes_only(iter(paletted)))
    assert np.array_equal(np.asarray(stored[0]), np.asarray(paletted[0]))
    assert (np.asarray(stored[2]) != iv.TRANSPARENT).sum() == 100  # (the 10x10 that changed, nothing else)
    path = tmp_path / "changes.gif"
    stored[0].save(path, save_all=True, append_images=stored[1:], duration=[100, 100, 100], loop=0, optimize=False,
                   disposal=1, transparency=iv.TRANSPARENT)
    with Image.open(path) as gif:
        for k, expected in enumerate(frames):
            gif.seek(k)
            assert np.array_equal(np.asarray(gif.convert("RGB")), np.asarray(expected)), k


def test_a_name_on_the_page_is_two_to_four_kanji_and_a_capitalised_rendering():
    assert iv.name_like("山田\n太郎", "Taro Yamada.") == ("山田太郎", "Taro Yamada")
    assert iv.name_like("山田", "Yamada") == ("山田", "Yamada")
    assert iv.name_like("やまだ", "Yamada") is None  # (kana: not taken for a name)
    assert iv.name_like("山田太郎", "he is taro") is None
    assert iv.name_like("山", "Mountain") is None
    assert iv.name_like("山田太郎", "Taro Yamada, I said") is None


def test_the_series_sheets_file_line_is_left_empty_in_the_recording_process(monkeypatch):
    from taslation.ui.dialogs import glossary

    monkeypatch.setattr(glossary, "break_lines", lambda text, *a, **k: text)
    assert iv.blank_file_lines() == {"series_sheet_file_line": 1}
    assert glossary.break_lines("File: C:\\somewhere\\sheet.json", 60, None) == ""
    assert glossary.break_lines("Facts the model is told", 60, None) == "Facts the model is told"


def write_recording(path: Path, source: iv.MemorySource) -> None:
    """*source* as the record leaves a recording: its pictures in a ZIP, its facts in meta.json."""
    writer = pv.RecordingWriter(path)
    for t, name in source.frames:
        writer.add(t, source.image(name))
    for _t, _index, name in source.pics:
        buffer = io.BytesIO()
        source.image(name).save(buffer, format="JPEG")
        with writer.lock:
            writer.zip.writestr(name, buffer.getvalue())
    meta = {k: v for k, v in source.meta.items() if k != "frames"}
    iv.check_no_text(meta)
    writer.finish(meta)


def test_a_recording_is_made_into_a_gif_and_then_deleted(tmp_path, capsys):
    recording = tmp_path / "intro.zip"
    write_recording(recording, small_sample())
    out = tmp_path / "intro.gif"
    assert iv.main(["render", str(recording), "--out", str(out), "--fps", "4", "--title-seconds", "0.5",
                    "--card-seconds", "0.5"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["recording_deleted"] is True and not recording.exists()
    with Image.open(out) as gif:
        assert gif.size == iv.SIZE
    assert [p["number"] for p in report["parts"] if p["number"]] == [1, 2]


def test_a_recording_is_kept_when_asked_or_when_the_gif_is_refused(tmp_path, capsys, monkeypatch):
    recording = tmp_path / "intro.zip"
    write_recording(recording, small_sample())
    out = tmp_path / "intro.gif"
    args = ["render", str(recording), "--out", str(out), "--fps", "4", "--title-seconds", "0.5", "--card-seconds", "0.5"]
    assert iv.main([*args, "--keep-recording"]) == 0 and recording.exists()
    capsys.readouterr()
    monkeypatch.setattr(iv, "GIF_LIMIT", 1000)
    out.unlink()
    assert iv.main(args) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["refused"] and report["over_by"] > 0
    assert recording.exists() and not out.exists()


def test_the_help_says_the_recording_is_scratch_and_deleted(capsys):
    with pytest.raises(SystemExit):
        iv.parse(["record", "--help"])
    text = " ".join(capsys.readouterr().out.split())
    assert "scratch folder" in text and "deletes it once the GIF is written" in text


# ---------------------------------------------------------------------------------------------------- no text kept
def test_a_recordings_facts_hold_no_page_text():
    iv.check_no_text(small_sample().meta)
    for bad in ({"text": "a line"}, {"regions": [{"translated_text": "x"}]}, {"keys": [{"key": "Left", "lines": []}]},
                {"what": "こんにちは"}, {"why": "x" * (iv.LONGEST_VALUE + 1)}):
        with pytest.raises(ValueError):
            iv.check_no_text(bad)
    iv.check_no_text({"keys": [{"t": 1.0, "key": "Left", "passed_on": True}], "regions": [{"what": "added",
                                                                                          "box": [1, 2, 3, 4]}]})


# ---------------------------------------------------------------------------------------------------- the guard
def test_the_guard_table_opens_the_posted_key_to_the_stand_in_alone():
    table = iv.guard_table()
    assert table["post_key"][0] == "viewer"
    for name in ("press_key", "press_briefly", "post_click", "capture_screen_rect"):
        assert table[name][0] == "never", name
    for name in ("capture_window", "enlarge_window", "move_window", "raise_window"):
        assert table[name][0] == "ours", name
    assert set(table) == set(dv.GUARDED)


@pytest.mark.skipif(sys.platform != "win32", reason="the guard asks Windows whose a window is")
def test_the_guard_refuses_another_programs_window():
    stand_in, foreign = 0x7654320, 0x1234560  # (handles of no window: nothing is sent anywhere)
    guard = dv.Guard(stand_in)
    called: list[tuple] = []
    table = iv.guard_table()
    allow, target = table["post_key"]
    post_key = guard.wrap("post_key", lambda *a, **k: called.append(a), allow, target)
    with pytest.raises(dv.Refused):
        post_key(foreign, "Left")
    assert called == [] and guard.refused == ["post_key"]
    post_key(stand_in, "Left")
    assert called == [(stand_in, "Left")] and guard.used == {"post_key": 1}
    allow, target = table["press_briefly"]
    press = guard.wrap("press_briefly", lambda *a, **k: called.append(a), allow, target)
    with pytest.raises(dv.Refused):
        press(stand_in, "Left")  # (no key is ever pressed for real, not even in the stand-in)
    assert len(called) == 1


def test_the_owners_ollama_and_the_other_tools_ports_are_refused():
    for port in (11434, 11435, 11436, 11437):
        with pytest.raises(SystemExit):
            iv.check_port(port)
    assert iv.check_port(iv.DEFAULT_PORT) == 11438
    with pytest.raises(SystemExit):
        iv.check_port(80)


def test_record_list_prints_the_scenes_and_starts_nothing(capsys):
    assert iv.main(["record", "--list"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert [row["id"] for row in rows] == list(ORDER)
    assert all(set(row) == {"id", "title", "present"} for row in rows)


def test_files_go_to_scratch_and_where_git_ignores_them(tmp_path):
    with pytest.raises(SystemExit):
        pv.check_scratch_path(ROOT / "intro.zip")
    with pytest.raises(SystemExit):
        iv.main(["render", "--sample", "--out", str(ROOT / "docs" / "media" / "intro-test.gif")])
    assert not (ROOT / "docs" / "media" / "intro-test.gif").exists()
    with pytest.raises(SystemExit):
        iv.main(["render", "--sample", "--out", str(tmp_path / "intro.png")])
