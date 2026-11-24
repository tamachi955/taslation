"""The README's introduction tool (tools/intro_video.py) without a window, a model or a manga page: the scenes'
table (ids, order, what this checkout has, texts that fit the frame), the scenes picked and numbered as the GIF is
made, every card line and step following sentences of docs/MANUAL.md that still stand word for word (or marked as the
tool's own words; nothing quotes the README), nothing that compares or boasts, the version on the title card and the
credit on every frame with a page, the 5 MB limit, a GIF of made-up frames and one of a recording (deleted once the GIF
is written), no page text in a recording's facts; and of ``record``: what it refuses before anything starts, the
stand-in run it asks for (its own scenario, the stand-in sharp at once, a port of its own for the translator), the
check of each frame (another program's window or pixels: refused, and enough of them in a row stop the run), where
TASlation's own windows draw, and the scenes' loop on made-up objects."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import intro_video as iv  # noqa: E402
import promo_video as pv  # noqa: E402

ORDER = ("turn", "panes", "original", "edit")


def quick(**kw) -> iv.Options:
    """Options for a small, quick GIF."""
    values = {"fps": 4.0, "title_s": 0.5, "card_s": 0.5}
    values.update(kw)
    return iv.Options(**values)


def small_sample(ids=("turn", "panes"), seconds: float = 1.0, fps: float = 3.0) -> iv.MemorySource:
    return iv.sample_source(list(ids), seconds=seconds, fps=fps)


# ---------------------------------------------------------------------------------------------------- the scenes
def test_the_scenes_ids_are_unique_and_in_the_order_of_the_introduction():
    assert iv.SCENE_IDS == ORDER
    assert len(set(iv.SCENE_IDS)) == len(iv.SCENE_IDS)
    for scene in iv.SCENES:
        assert scene.title and scene.description and scene.budget_s > 0
        assert not any(ch.isdigit() for ch in scene.title)  # (numbers are given as the GIF is made)
    assert [s.id for s in iv.SCENES if not s.cut] == ["turn"]  # (the page's turn shown as it was)


def test_every_step_fits_under_the_picture():
    facts = iv.code_facts()
    layout = iv.Layout(iv.SIZE)
    for scene in iv.SCENES:
        title, description = iv.step_texts(scene, facts)
        assert "{" not in title + description, scene.id
        assert layout.step_fits(title, description), scene.id
        (tsize, _tlines), (dsize, _dlines) = layout.step(title, description)
        assert tsize >= layout.title_px[1] and dsize >= layout.desc_px[1]
    assert layout.picture[3] < layout.step_box[1] and layout.step_box[3] <= iv.SIZE[1] - layout.foot


def test_the_page_turn_is_named_real_time_translation_with_no_timing_figures():
    title, description = iv.step_texts(iv.scene_of("turn"), iv.code_facts())
    assert title == "Real-time translation"
    assert "in reading order" in description and "as soon as its translation is ready" in description
    assert not any(ch.isdigit() for ch in description) and "second" not in description


# ---------------------------------------------------------------------------------------------------- what follows what
def flat(text: str) -> str:
    return " ".join(text.split())


def every_line(present_only: bool = False):
    """(where, follows, own) of each card line and each step's description (only the steps this checkout can show
    with *present_only*)."""
    for kind, (_heading, lines) in iv.CARDS.items():
        for line in lines:
            yield f"card {kind}: {line.text[:50]}", line.follows, line.own
    for scene in iv.SCENES:
        if scene.present() or not present_only:
            yield f"step {scene.id}", scene.follows, scene.own


def test_every_card_line_and_step_follows_the_manual_or_is_marked_the_tools_own():
    assert iv.DOCS == ("docs/MANUAL.md",)  # (nothing quotes the README: it is rewritten on its own)
    for where, follows, own in every_line():
        assert follows or own.strip(), where
        assert all(isinstance(cite, iv.Cite) and cite.doc in iv.DOCS and cite.quote.strip() for cite in follows), where
    owns = {where for where, _follows, own in every_line() if own}
    assert owns == {"card title: TASlation", "card title: Recorded with version {version}",
                    f"card points: {pv.PROJECT}"}


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


def test_a_changed_sentence_makes_its_line_stale():
    facts, docs = iv.code_facts(), documents()
    changed = dict(docs, **{iv.MANUAL: docs[iv.MANUAL].replace("There is no account to make and no limit",
                                                               "There is no account to make and a limit")})
    stale = stale_lines(facts, changed)
    assert [s.split(":")[0] for s in stale] == ["card points"]
    assert "no longer says 'There is no account to make and no limit on the pages it translates.'" in stale[0]
    edited = dict(docs, **{iv.MANUAL: docs[iv.MANUAL].replace("turns editing on and off", "turns editing on")})
    assert [s.split(":")[0] for s in stale_lines(facts, edited)] == ["step edit"]


def test_a_scene_is_present_only_where_this_checkout_has_what_it_shows(monkeypatch):
    assert all(scene.present() for scene in iv.SCENES)
    assert (ROOT / "taslation" / "panes.py").is_file() and (ROOT / "taslation" / "ui" / "see_edit.py").is_file()
    monkeypatch.setattr(iv, "has_module", lambda name: name != "taslation.ui.see_edit")
    assert iv.scene_of("edit").present() is False and iv.scene_of("panes").present() is True
    made_up = [entry["id"] for entry in iv.sample_source(seconds=0.5, fps=2.0).meta["scenes"]]
    assert made_up == ["turn", "panes", "original"]  # (the sample: what this checkout has)


def test_the_scenes_are_numbered_as_the_gif_is_made():
    source = small_sample(("turn", "panes", "edit"))
    numbers = [(p.id, p.number) for p in iv.plan(source, quick()) if p.kind == "scene"]
    assert numbers == [("turn", 1), ("panes", 2), ("edit", 3)]
    numbers = [(p.id, p.number) for p in iv.plan(source, quick(scenes=["panes", "edit"])) if p.kind == "scene"]
    assert numbers == [("panes", 1), ("edit", 2)]
    source.meta["scenes"][1]["failed"] = "timed out: the original under the pointer"  # (a failed scene: left out)
    numbers = [(p.id, p.number) for p in iv.plan(source, quick()) if p.kind == "scene"]
    assert numbers == [("turn", 1), ("edit", 2)]
    kinds = [p.id for p in iv.plan(source, quick())]
    assert kinds[0] == "title" and kinds[-len(iv.CARD_ORDER):] == list(iv.CARD_ORDER)


def test_a_wait_is_shown_faster_and_a_still_wait_is_cut():
    entry = {"id": "edit", "t0": 0.0, "t1": 30_000.0, "fast": [[2000.0, 28_000.0]], "failed": ""}
    changes = [float(t) for t in range(0, 30_001, 500)]
    segments, factor = iv.scene_segments(entry, changes, budget_ms=10_000, longest_ms=1200)
    assert factor == pytest.approx(26_000 / (10_000 - 4000), abs=0.05)  # R / (budget - S)
    shown = sum((b - a) / f for a, b, f, _fast in segments)
    assert shown == pytest.approx(10_000, rel=0.02)
    assert all(f == 1.0 for a, b, f, fast in segments if not fast)
    segments, factor = iv.scene_segments(entry, changes, budget_ms=1000, longest_ms=1200)
    assert factor == iv.MAX_SPEED  # (never faster than that)
    still = {"id": "edit", "t0": 0.0, "t1": 10_000.0, "fast": [], "failed": ""}
    segments, factor = iv.scene_segments(still, [1000.0, 9000.0], budget_ms=4000, longest_ms=1200)
    assert factor == 1.0
    assert sum(b - a for a, b, _f, _fast in segments) == pytest.approx(1000 + 1200 + 1000)  # 8 s still: 1.2 s left
    segments, _factor = iv.scene_segments(still, [1000.0, 9000.0], budget_ms=4000, longest_ms=float("inf"))
    assert sum(b - a for a, b, _f, _fast in segments) == pytest.approx(10_000)  # (the turn: shown as it was)


def test_the_page_turn_is_not_cut_and_the_others_are():
    source = small_sample(("turn", "edit"), seconds=4.0, fps=1.0)
    for entry in source.meta["scenes"]:
        entry["t1"] += 9000.0  # (nine seconds with nothing changing at each scene's end)
    parts = {p.id: p for p in iv.plan(source, quick()) if p.kind == "scene"}
    real = {e["id"]: e["t1"] - e["t0"] for e in source.meta["scenes"]}
    assert parts["turn"].ms == pytest.approx(real["turn"])
    assert parts["edit"].ms < real["edit"] - 7000


# ---------------------------------------------------------------------------------------------------- the cards
def test_the_version_is_the_codes_own():
    import taslation

    assert iv.code_facts()["version"] == taslation.__version__


def test_the_cards():
    facts = iv.code_facts()
    assert iv.card_lines("points", facts)[0] == "On your own computer"
    lines = [t for t, _ in iv.card_lines("points", facts)[1]]
    assert lines[0] == "There is no account to make and no limit on the pages it translates."
    assert any("presses no key and sends no click to the viewer" in t for t in lines)
    assert pv.PROJECT in lines
    assert iv.card_lines("title", facts)[0] == ""


def test_a_line_whose_fact_is_missing_is_left_out():
    heading, lines = iv.card_lines("title", {})
    assert heading == "" and [t for t, _ in lines][0] == "TASlation"
    assert not any("{" in t or "Recorded" in t for t, _ in lines)


def test_nothing_on_a_card_or_a_step_compares_or_boasts():
    facts = iv.code_facts()
    texts = [t for kind in iv.CARDS for t in [iv.card_lines(kind, facts)[0]] + [x for x, _ in iv.card_lines(kind, facts)[1]]]
    texts += [x for scene in iv.SCENES for x in iv.step_texts(scene, facts)]
    words = ("chrF", "twice", "faster", "benchmark", " AI", "AI ", "artificial", "%", "better", "compared", " than ",
             "fastest", "best", "instant", "free", "piracy", "pirate")
    for text in texts:
        for word in words:
            assert word.lower() not in f" {text} ".lower(), (word, text)


def test_the_title_card_shows_the_version_small():
    import taslation

    lines = iv.card_lines("title", iv.code_facts())[1]
    assert (f"Recorded with version {taslation.__version__}", "small") in lines
    assert lines[0] == ("TASlation", "title") and lines[1] == ("Real-time translation", "lead")


def test_every_frame_with_a_page_carries_the_credit_with_modified():
    facts = iv.code_facts()
    assert pv.CREDIT == "Sample pages: OpenMantra dataset (Mantra Inc., CC BY-NC 4.0), modified"
    source = small_sample(("turn",))
    part = next(p for p in iv.plan(source, quick()) if p.kind == "scene")
    for kind in ("scene", *iv.CARDS):
        texts = iv.frame_texts(kind, facts, part if kind == "scene" else None)
        assert (pv.CREDIT in texts) == iv.has_page(kind), kind
    assert iv.has_page("scene") and not any(iv.has_page(kind) for kind in iv.CARDS)


def test_the_cards_fit_above_the_foot():
    painter = iv.Painter(small_sample(("turn",)), quick())
    for kind in iv.CARDS:
        image = painter.card(kind)
        assert image.size == iv.SIZE
        assert painter.bottoms[kind] <= iv.SIZE[1] - 50, kind


def test_a_scene_frame_draws_the_picture_the_pointer_and_the_panes_outlined():
    source = small_sample(("panes",), seconds=2.0, fps=4.0)
    opts = quick()
    painter = iv.Painter(source, opts)
    part = next(p for p in iv.plan(source, opts) if p.kind == "scene")
    key = painter.state(part, part.ms / 2)
    assert key[0] == "scene" and key[1] == 1 and key[2] is not None
    assert key[3] is not None  # (the tool's pointer)
    assert len(key[4]) == 2  # (both panes outlined in their scene)
    placed = painter.place(key[2])
    assert placed[1] >= painter.layout.picture[1] and placed[1] + placed[3] <= painter.layout.picture[3]
    image = painter.draw(part, key)
    assert image.size == iv.SIZE
    x0, y0, x1, _y1 = key[4][0]
    assert np.abs(np.asarray(image)[y0 - 4, (x0 + x1) // 2].astype(int) - iv.AMBER).max() <= 40  # (its outline)
    other = small_sample(("turn",))
    turn = next(p for p in iv.plan(other, opts) if p.kind == "scene")
    assert iv.Painter(other, opts).state(turn, 10.0)[4] == ()  # (outlined in that scene only)


# ---------------------------------------------------------------------------------------------------- the GIF
def test_a_gif_of_made_up_frames(tmp_path):
    out = tmp_path / "sample.gif"
    report = iv.render(small_sample(), out, quick(frames_png=tmp_path / "png"))
    with Image.open(out) as gif:
        assert gif.size == iv.SIZE and gif.n_frames >= 2
    assert report["bytes"] == out.stat().st_size and report["bytes"] <= iv.GIF_LIMIT
    assert [p["id"] for p in report["parts"]] == ["title", "turn", "panes", *iv.CARD_ORDER]
    assert sum(p["bytes"] for p in report["parts"]) <= report["bytes"]
    assert report["largest"] and report["largest"][0]["bytes"] >= report["largest"][-1]["bytes"]
    pngs = sorted(p.name for p in (tmp_path / "png").iterdir())
    assert "00_title.png" in pngs and "01_turn_0.png" in pngs
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


def test_the_palette_keeps_the_boxes_colours_and_leaves_the_transparent_index_free():
    page = Image.new("RGB", (480, 270), (250, 250, 250))
    for x in range(0, 480, 4):  # (greys of a page: many of them, as the screentones give)
        page.paste((x // 2, x // 2, x // 2), (x, 0, x + 4, 200))
    page.paste((255, 212, 0), (100, 220, 106, 226))  # (a box's handle: a few pixels)
    page.paste((40, 160, 70), (200, 210, 330, 212))  # (a region's thin green frame)
    for colours in (255, 64):
        palette = iv.palette_of([page], colours)
        assert len(palette.getpalette()) // 3 <= colours
        mapped = page.quantize(palette=palette, dither=Image.Dither.NONE)
        assert int(np.asarray(mapped).max()) < iv.TRANSPARENT
        back = np.asarray(mapped.convert("RGB")).astype(int)
        for (x, y), colour in (((102, 222), (255, 212, 0)), ((250, 211), (40, 160, 70))):
            assert np.abs(back[y, x] - colour).max() <= 24, (colours, colour, back[y, x])


def scene_frame(picture: str, pointer=None, ms: float = 100.0, part: int = 1) -> list:
    return [part, ("scene", 1, picture, pointer, (), None), ms]


def test_frames_where_only_the_screens_picture_changes_are_held_to_the_still_rate():
    merged = [scene_frame(f"w{k}") for k in range(10)]  # (a second of lettering: the picture alone changes)
    kept = iv.thinned([list(m) for m in merged], 4.0)
    assert [m[1][2] for m in kept] == ["w0", "w3", "w6", "w9"]  # (one each 250 ms or so, and the last)
    assert sum(m[2] for m in kept) == 1000.0  # (the same time shown)
    moving = [scene_frame(f"w{k}", pointer=(k, k, False)) for k in range(10)]  # (the pointer gliding: every frame)
    assert len(iv.thinned([list(m) for m in moving], 4.0)) == 10
    assert iv.thinned([list(m) for m in merged], None) == merged
    other = merged[:3] + [scene_frame("w3", part=2)] + [scene_frame(f"w{k}", part=2) for k in range(4, 6)]
    assert [m[0] for m in iv.thinned([list(m) for m in other], 4.0)][:2] == [1, 1]  # (a part's last frame kept)
    assert any(m[0] == 2 and m[1][2] == "w3" for m in iv.thinned([list(m) for m in other], 4.0))


def write_recording(path: Path, source: iv.MemorySource) -> None:
    """*source* as the record leaves a recording: its pictures in a ZIP, its facts in meta.json."""
    writer = pv.RecordingWriter(path)
    for t, name in source.frames:
        writer.add(t, source.image(name))
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


def test_a_recording_of_the_programs_own_window_is_not_rendered(tmp_path):
    recording = tmp_path / "old.zip"
    source = small_sample(("turn",))
    source.meta["intro_format"] = "intro-1"
    write_recording(recording, source)
    with pytest.raises(SystemExit):
        iv.main(["render", str(recording), "--out", str(tmp_path / "old.gif")])


def test_the_help_says_the_recording_is_scratch_and_deleted(capsys):
    with pytest.raises(SystemExit):
        iv.parse(["render", "--help"])
    text = " ".join(capsys.readouterr().out.split())
    assert "scratch folder" in text and "deleted once the GIF is written" in text


# ---------------------------------------------------------------------------------------------------- record
def record_args(tmp_path, *more: str) -> list[str]:
    return ["record", "--out", str(tmp_path / "intro.zip"), *more]


def test_record_refuses_before_anything_starts(tmp_path, monkeypatch):
    started = []
    monkeypatch.setitem(sys.modules, "standin_e2e", None)  # (an import of the stand-in run would fail loudly)
    monkeypatch.setattr(iv, "Run", lambda *a, **k: started.append(a))
    with pytest.raises(SystemExit) as port:
        iv.main(record_args(tmp_path, "--start-ollama", "11434"))
    assert "usual port" in str(port.value)
    with pytest.raises(SystemExit):
        iv.main(["record", "--out", str(ROOT / "intro.zip")])  # (never into a repository)
    with pytest.raises(SystemExit):
        iv.main(["record", "--out", str(tmp_path / "intro.gif")])
    (tmp_path / "intro.zip").write_bytes(b"")
    with pytest.raises(SystemExit):
        iv.main(record_args(tmp_path))  # (one there already)
    (tmp_path / "intro.zip").unlink()
    (tmp_path / "intro-run").mkdir()
    with pytest.raises(SystemExit):
        iv.main(record_args(tmp_path))  # (a run's folder from before)
    assert not started and not (tmp_path / "intro.zip").exists()


def test_the_stand_in_run_it_asks_for():
    args = iv.parse(["record", "--out", "x.zip"])
    assert args.start_ollama == iv.RECORD_PORT == 11435 and args.fps == iv.RECORD_FPS
    argv = iv.e2e_argv(args, Path("work"))
    pairs = dict(zip(argv[::2], argv[1::2]))
    assert pairs["--scenario"] == iv.SCENARIO and pairs["--soft-first"] == "off"
    assert pairs["--start-ollama"] == "11435" and pairs["--out"] == "work"
    assert pairs["--standin-size"] == iv.STANDIN_SIZE and pairs["--first"] == str(iv.FIRST_PAGE)
    assert "--see-edit" not in argv and "--see-truth" not in argv and "--see-pane-shot" not in argv
    assert "11434" not in argv


def test_its_scenario_holds_until_the_first_scene_turns_once_and_holds_to_the_end(monkeypatch):
    import standin_e2e as e2e

    monkeypatch.setitem(e2e.SCENARIOS, iv.SCENARIO, ("the README's introduction", list(iv.SCRIPT)))
    monkeypatch.setattr(e2e, "NAMED_ONLY", (*e2e.NAMED_ONLY, iv.SCENARIO))
    assert e2e.wanted(iv.SCENARIO) == [iv.SCENARIO] and iv.SCENARIO not in e2e.wanted("all")
    segments, steps = e2e.build_plan([iv.SCENARIO], e2e.pages_needed([iv.SCENARIO]))
    assert [s.name for s in segments] == [iv.SCENARIO] and segments[0].screens == [(2, True)]
    assert [s.op for s in steps] == list("gmhnhe")


def test_a_frame_is_refused_for_a_window_over_the_stand_in_or_another_programs_pixels():
    assert iv.verdict(0, 0) == ""
    assert iv.verdict(1, 0) == "a window over the stand-in"
    assert iv.verdict(0, -1) == "no frame of the stand-in's to tell it by"
    assert iv.verdict(0, 3) == "another program's pixels"


def test_refused_frames_in_a_row_stop_the_run(tmp_path):
    run = iv.Run(tmp_path / "r.zip")
    try:
        for _ in range(iv.REFUSED_IN_A_ROW - 1):
            run.refuse("another program's pixels")
        assert not run.failed
        run.in_a_row = 0  # (a frame kept in between)
        for _ in range(iv.REFUSED_IN_A_ROW - 1):
            run.refuse("a window over the stand-in")
        assert not run.failed
        run.begin("turn")
        run.refuse("a window over the stand-in")
        assert run.failed.startswith("a window over the stand-in: ")
        assert run.scenes[0]["failed"] == run.failed and run.scenes[0]["t1"] is not None
        assert run.refused == {"another program's pixels": iv.REFUSED_IN_A_ROW - 1,
                               "a window over the stand-in": iv.REFUSED_IN_A_ROW}
    finally:
        run.writer.abandon()
    assert not (tmp_path / "r.zip").exists()


class FakeSet:
    def __init__(self, serial, boxes, final=True):
        self.serial, self.final = serial, final
        self.patches = [type("P", (), {"box": b})() for b in boxes]


class FakeOver:
    """The parts of the see-through window the tool reads (`capture.seethrough.SeeThrough`)."""

    def __init__(self, sets, shown, panes, marks=None, takes=False):
        import threading

        self._lock = threading.Lock()
        self._store = type("S", (), {"sets": sets})()
        self._shown = shown
        self._panes = panes
        self._marks_live, self._edit_takes = marks, takes
        self._last_look = None if shown is None else (0, 0, 0, 0, 0, shown[2], shown[3])
        self._ghost = None
        self._dpi = 96
        self._left_out = frozenset()
        self._press = None

    def shown(self):
        return self._shown

    def pane_shown(self, side):
        return self._panes.get(side)


def test_where_the_programs_own_windows_draw_is_left_out_of_the_check(tmp_path):
    from taslation import seethrough as st

    sets = [FakeSet(1, [(10, 10, 50, 30)]), FakeSet(2, [(100, 100, 140, 120), (60, 60, 70, 70)]),
            FakeSet(3, [(300, 300, 310, 310)])]
    over = FakeOver(sets, (2, (0, 1), (1000, 500), (800, 600)), {"left": (910, 520, 990, 700)})
    run = iv.Run(tmp_path / "r.zip")
    try:
        masks = iv.own_masks(over, 900, 480, run)
        p = iv.PATCH_PAD
        assert (100 + 100 - p, 100 + 20 - p, 140 + 100 + p, 120 + 20 + p) in masks  # (the set shown, at its origin)
        assert (10 + 100 - p, 10 + 20 - p, 50 + 100 + p, 30 + 20 + p) not in masks  # (not shown at either frame)
        assert not any(m[0] == 300 + 100 - p for m in masks)
        assert (10 - 2, 40 - 2, 90 + 2, 220 + 2) in masks  # (the left pane, its box in the copy's px)
        assert len(masks) == 3 and run.serials == (2,)
        over._shown = (1, (0,), (1000, 500), (800, 600))  # (the next page's set: the one before still left out)
        masks = iv.own_masks(over, 900, 480, run)
        assert run.serials == (1, 2) and len(masks) == 4
        assert (10 + 100 - p, 10 + 20 - p, 50 + 100 + p, 30 + 20 + p) in masks
        marks = st.Marks(key=1, boxes=((200, 200, 260, 240),),
                         plates=((np.zeros((12, 20, 4), np.uint8), (190, 180)),))
        over._marks_live, over._edit_takes = marks, True
        run.drag_box = (200, 200, 320, 270)
        masks = iv.own_masks(over, 900, 480, run)
        e = iv.EDIT_PAD
        assert (200 + 100 - e, 200 + 20 - e, 260 + 100 + e, 240 + 20 + e) in masks
        assert (200 + 100 - e, 200 + 20 - e, 320 + 100 + e, 270 + 20 + e) in masks  # (the drag's sweep)
        assert (190 + 100 - p, 180 + 20 - p, 210 + 100 + p, 192 + 20 + p) in masks  # (a number plate)
    finally:
        run.writer.abandon()


def test_the_bubble_and_the_box_the_scenes_pick():
    sets = [FakeSet(5, [(0, 0, 40, 40), (100, 100, 300, 200), (500, 0, 560, 60)])]
    over = FakeOver(sets, (5, (0, 1, 2), (1000, 500), (800, 600)), {})
    assert iv.biggest_patch(over, ()) == (5, 1, (1200, 650))
    assert iv.biggest_patch(over, [(1150, 600, 1250, 700)]) == (5, 2, (1530, 530))  # (not one under a pane)
    sets[0].final = False
    assert iv.biggest_patch(over, ()) is None  # (a page filling in)
    from taslation import seethrough as st

    over._marks_live = st.Marks(key=1, boxes=((10, 10, 30, 30), (100, 100, 300, 200), (700, 500, 790, 590),
                                               (150, 130, 250, 170)))
    assert iv.drag_box_pick(over) is None  # (each middle in the other box, too small, or no room for the drag)
    over._marks_live = st.Marks(key=1, boxes=((10, 10, 30, 30), (100, 100, 300, 200), (700, 500, 790, 590)))
    assert iv.drag_box_pick(over) == (1, (100, 100, 300, 200))  # (the small one too small, the last no room)
    assert iv.box_near(over, (101, 99, 300, 201)) == (100, 100, 300, 200) and iv.box_near(over, (0, 0, 9, 9)) is None


def test_the_tools_pointer_glides_and_moves_nothing_else():
    run = argparse.Namespace(watch=argparse.Namespace(fake_point=(0, 0)))
    waits = list(iv.glide(run, (100, 50), 0.4))
    assert waits and all(w == iv.TICK_S for w in waits)
    assert run.watch.fake_point == (100, 50)
    run.watch.fake_point = None
    list(iv.glide(run, (7, 8), 0.1))
    assert run.watch.fake_point == (7, 8)  # (it appears where it goes when it was nowhere)


class FakeDirector:
    """standin_e2e's Director as the tool's subclass uses it (the loop calls `step` every tick)."""

    def __init__(self, *a, **k):
        self.over, self.released, self.phase = False, {}, "prepare"
        self.stopped, self.finished = None, False

    def step(self):
        self.released[iv.SCENARIO] = {}
        self.phase = "running"

    def stop(self, why):
        self.over, self.stopped = True, why

    def finish(self):
        self.finished = True
        self.stop("done")


def run_loop(director, seconds: float = 5.0) -> None:
    end = time.monotonic() + seconds
    while not director.over and time.monotonic() < end:
        director.step()
        time.sleep(0.001)


def test_the_scenes_are_acted_on_the_runs_loop(tmp_path, monkeypatch):
    done = []

    def program(_director, run):
        yield 0.01
        yield (lambda: True, 1.0, "something at once")
        run.begin("turn")
        done.append("turn")
        run.end("turn")

    monkeypatch.setattr(iv, "scenes_program", program)
    monkeypatch.setattr(iv, "RUN", iv.Run(tmp_path / "r.zip"))
    try:
        director = iv.director_class(argparse.Namespace(Director=FakeDirector))()
        assert iv.RUN.director is director
        run_loop(director)
        assert director.finished and director.stopped == "done" and done == ["turn"]
        assert not iv.RUN.failed and iv.RUN.scenes[0]["t1"] is not None and not iv.RUN.on.is_set()
    finally:
        iv.RUN.writer.abandon()


def test_a_scene_that_waits_too_long_or_lacks_what_it_needs_stops_the_run(tmp_path, monkeypatch):
    def slow(_director, run):
        run.begin("original")
        yield (lambda: False, 0.05, "the original under the pointer")

    def lacking(_director, _run):
        yield 0.0
        raise iv.SceneFailed("no box the drag can move")

    for program, why in ((slow, "timed out: the original under the pointer"), (lacking, "no box the drag can move")):
        monkeypatch.setattr(iv, "scenes_program", program)
        monkeypatch.setattr(iv, "RUN", iv.Run(tmp_path / f"{program.__name__}.zip"))
        try:
            director = iv.director_class(argparse.Namespace(Director=FakeDirector))()
            run_loop(director)
            assert director.stopped == why and not director.finished and iv.RUN.failed == why
            assert all(s["failed"] == why for s in iv.RUN.scenes)
        finally:
            iv.RUN.writer.abandon()


def test_the_watch_leaves_its_own_pointer_and_clicks_to_the_scenes():
    class FakeWatch:
        def __init__(self):
            self.started = self.closed = False

        def _click_lettering(self):
            raise AssertionError("never: the scenes click the panes")

        def _hover_safe(self):
            raise AssertionError("never: the scenes move the tool's pointer")

        def _edit_safe(self):
            raise AssertionError("never")

        def start(self):
            self.started = True

        def close(self):
            self.closed = True

    watch = iv.watch_class(argparse.Namespace(SeeWatch=FakeWatch))()
    watch._click_lettering()
    watch._hover_safe()
    watch._edit_safe()
    assert watch.pane_click and watch.hover and watch.edit_result
    watch.start()
    watch.close()
    assert watch.started and watch.closed


# ---------------------------------------------------------------------------------------------------- no text kept
def test_a_recordings_facts_hold_no_page_text(tmp_path):
    iv.check_no_text(small_sample().meta)
    run = iv.Run(tmp_path / "r.zip")
    try:
        run.begin("turn")
        run.end("turn")
        run.pointer.append([1.0, 10, 20, 0])
        run.panes.append([1.0, 0, 0, 10, 10, -1, -1, -1, -1])
        run.refused["a window over the stand-in"] += 1
        iv.check_no_text(run.meta({"version": "9.9.9"}))
    finally:
        run.writer.abandon()
    for bad in ({"text": "a line"}, {"regions": [{"translated_text": "x"}]}, {"keys": [{"key": "Left", "lines": []}]},
                {"what": "こんにちは"}, {"why": "x" * (iv.LONGEST_VALUE + 1)}):
        with pytest.raises(ValueError):
            iv.check_no_text(bad)


def test_files_go_to_scratch_and_where_git_ignores_them(tmp_path):
    with pytest.raises(SystemExit):
        pv.check_scratch_path(ROOT / "intro.zip")
    with pytest.raises(SystemExit):
        iv.main(["render", "--sample", "--out", str(ROOT / "docs" / "media" / "intro-test.gif")])
    assert not (ROOT / "docs" / "media" / "intro-test.gif").exists()
    with pytest.raises(SystemExit):
        iv.main(["render", "--sample", "--out", str(tmp_path / "intro.png")])


def test_the_readmes_gif_is_small_enough_for_every_visitor():
    gif = ROOT / "docs" / "media" / "taslation-intro.gif"
    if not gif.is_file():
        pytest.skip("no GIF in this checkout")
    assert gif.stat().st_size <= iv.GIF_LIMIT
    with Image.open(gif) as image:
        assert image.format == "GIF" and image.size == iv.SIZE and image.n_frames > 10
