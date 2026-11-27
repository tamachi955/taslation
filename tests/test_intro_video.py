"""The README's introduction tool (tools/intro_video.py) without a window, a model or a manga page: the scenes'
table (ids, order, what this checkout has, texts that fit the frame), the scenes picked and numbered as the GIF is
made, every card line and step following sentences of docs/MANUAL.md that still stand word for word (or marked as the
tool's own words; nothing quotes the README), nothing that compares or boasts, the version on the title card and the
credit on every frame with a page, the panes and the right pane's foot outlined in their scenes, the 5 MB limit and
the fit to the size of the GIF it replaces, a GIF of made-up frames and one of a recording (deleted once the GIF is
written), no page text in a recording's facts; and of ``record``: what it refuses before anything starts (no clean
place for the stand-in among the other programs' windows too), the stand-in run it asks for (its own scenario, the
stand-in sharp at once on its monitor, a port of its own for the translator, TASlation starting editing and asking
for the viewer), the screen's windows looked at while it runs (another program's window on the stand-in, the
foreground come to ours from another program's: the take given up), what could take the foreground acting only
while one of ours has it, messages posted to TASlation's own windows only, the check of each frame (another
program's window or pixels: refused, and enough of them in a row stop the run; the chooser's frames on the window
checks alone), where TASlation's own windows draw, and the scenes acted on made-up objects: the viewer chooser, and
the scenes after it on a made-up TASlation answering the messages posted to it."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import intro_video as iv  # noqa: E402
import promo_video as pv  # noqa: E402

ORDER = ("chooser", "reader", "turn", "panes", "foot", "language", "original", "edit")


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
    edited = dict(docs, **{iv.MANUAL: docs[iv.MANUAL].replace("switches editing off, and unchecked again, on",
                                                              "switches editing off")})
    assert [s.split(":")[0] for s in stale_lines(facts, edited)] == ["step reader"]
    clicked = dict(docs, **{iv.MANUAL: docs[iv.MANUAL].replace("A double click opens the region editor beside it.",
                                                               "A click opens the region editor beside it.")})
    assert [s.split(":")[0] for s in stale_lines(facts, clicked)] == ["step edit"]


def test_a_scene_is_present_only_where_this_checkout_has_what_it_shows(monkeypatch):
    assert all(scene.present() for scene in iv.SCENES)
    assert (ROOT / "taslation" / "panes.py").is_file() and (ROOT / "taslation" / "ui" / "see_edit.py").is_file()
    assert (ROOT / "taslation" / "ui" / "see_menu.py").is_file()
    monkeypatch.setattr(iv, "has_module", lambda name: name != "taslation.ui.see_edit")
    assert iv.scene_of("edit").present() is False and iv.scene_of("reader").present() is False
    assert iv.scene_of("panes").present() is True and iv.scene_of("chooser").present() is True
    made_up = [entry["id"] for entry in iv.sample_source(seconds=0.5, fps=2.0).meta["scenes"]]
    assert made_up == ["chooser", "turn", "panes", "foot", "language", "original"]  # (what this checkout has)
    monkeypatch.setattr(iv, "has_module", lambda name: name != "taslation.ui.see_menu")
    assert iv.scene_of("chooser").present() is False and iv.scene_of("edit").present() is True


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


def test_the_right_panes_foot_is_outlined_in_its_own_scene():
    source = small_sample(("panes", "foot"), seconds=2.0, fps=4.0)
    opts = quick()
    painter = iv.Painter(source, opts)
    parts = {p.id: p for p in iv.plan(source, opts) if p.kind == "scene"}
    key = painter.state(parts["foot"], parts["foot"].ms / 2)
    assert len(key[4]) == 1  # (the foot alone: not the panes)
    x0, y0, x1, y1 = key[4][0]
    panes = painter.state(parts["panes"], parts["panes"].ms / 2)[4]
    right = panes[1]
    assert right[0] <= x0 and x1 <= right[2] and right[1] < y0 and y1 <= right[3] + 1  # (the lower part of the right)
    image = painter.draw(parts["foot"], key)
    assert np.abs(np.asarray(image)[y0 - 4, (x0 + x1) // 2].astype(int) - iv.AMBER).max() <= 40
    source.meta["foot"] = [[source.meta["foot"][0][0], -1, -1, -1, -1]]  # (no foot on show)
    source.index()
    assert iv.Painter(source, opts).state(parts["foot"], parts["foot"].ms / 2)[4] == ()


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


def test_the_gif_is_fitted_to_the_size_of_the_one_it_replaces(tmp_path, capsys, monkeypatch):
    assert iv.AIM_BYTES == 654_681 <= iv.GIF_LIMIT  # (the README's recording before this one)
    assert iv.FIT_LADDER[0] == (iv.STILL_FPS, iv.COLOURS, iv.RENDER_FPS)
    assert all(a[0] >= b[0] and a[1] >= b[1] and a[2] >= b[2] for a, b in zip(iv.FIT_LADDER, iv.FIT_LADDER[1:]))
    out = tmp_path / "fit.gif"
    report = iv.fit_render(small_sample(("turn",)), out, quick(), aim=10 ** 8)
    first = dict(zip(("still_fps", "colours", "fps"), iv.FIT_LADDER[0]))
    assert report["fit"]["chose"] == first and len(report["fit"]["tried"]) == 1
    assert report["fps"] == iv.RENDER_FPS and out.stat().st_size == report["bytes"] <= 10 ** 8
    out.unlink()
    with pytest.raises(iv.TooLarge) as refused:
        iv.fit_render(small_sample(("turn",)), out, quick(), aim=500)  # (none of the settings keeps it so small)
    fit = refused.value.report["fit"]
    assert fit["chose"] is None and [(t["still_fps"], t["colours"], t["fps"]) for t in fit["tried"]] == \
        list(iv.FIT_LADDER)
    assert all(t["bytes"] > 500 for t in fit["tried"]) and not out.exists()
    assert not (tmp_path / "fit.part.gif").exists()
    made_up = iv.sample_source
    monkeypatch.setattr(iv, "sample_source", lambda: made_up(["turn"], seconds=1.0, fps=3.0))  # (one short scene)
    assert iv.main(["render", "--sample", "--out", str(out), "--title-seconds", "0.5", "--card-seconds", "0.5",
                    "--fit", "500"]) == 1
    said = json.loads(capsys.readouterr().out)
    assert said["refused"] is not None and said["fit"]["aim"] == 500 and not out.exists()
    assert iv.parse(["render", "--sample", "--out", "x.gif", "--fit"]).fit == iv.AIM_BYTES
    assert iv.parse(["render", "--sample", "--out", "x.gif"]).fit is None


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


def test_record_refuses_where_another_programs_window_lies_on_the_stand_ins_place(tmp_path, monkeypatch):
    started = []
    monkeypatch.setitem(sys.modules, "standin_e2e", None)  # (an import of the stand-in run would fail loudly)
    monkeypatch.setitem(sys.modules, "demo_video", None)
    monkeypatch.setattr(iv, "Run", lambda *a, **k: started.append(a))
    monkeypatch.setattr(iv, "monitor_areas", lambda: [((0, 0, 1920, 1040), True), ((1920, 0, 3840, 1040), False)])
    shown = [iv.Shown(7, 4242, (3420 + iv.PLACE_MARGIN - 2, 100, 3600, 300))]  # (within the margin of its right side)
    monkeypatch.setattr(iv, "windows_now", lambda: list(shown))
    with pytest.raises(SystemExit) as refused:
        iv.main(record_args(tmp_path))
    assert "no clean place" in str(refused.value) and "monitor 2" in str(refused.value)
    assert "nothing was started" in str(refused.value)
    with pytest.raises(SystemExit) as missing:
        iv.main(record_args(tmp_path, "--standin-monitor", "3"))
    assert "no monitor 3" in str(missing.value)
    assert not started and not (tmp_path / "intro.zip").exists() and not (tmp_path / "intro-run").exists()
    shown[:] = [iv.Shown(7, 4242, (3420 + iv.PLACE_MARGIN, 100, 3600, 300)),  # (past the margin)
                iv.Shown(8, os.getpid(), (1920, 0, 2500, 500)),  # (ours)
                iv.Shown(9, 4243, (0, 0, 3840, 1080), desktop=True)]  # (the desktop's own)
    assert iv.clean_place(iv.parse(record_args(tmp_path))) == (1920, 0, 3420, 900)


def test_the_stand_ins_place_is_the_top_left_of_its_monitors_work_area():
    areas = [((0, 0, 1920, 1040), True), ((1920, 0, 3840, 1040), False)]
    assert iv.planned_place("1500x900", 2, areas) == (1920, 0, 3420, 900)
    assert iv.planned_place("2500x1200", 1, areas) == (0, 0, 1920, 1040)  # (no larger than its work area)
    with pytest.raises(SystemExit):
        iv.planned_place("1500x900", 0, areas)
    assert iv.STANDIN_MONITOR == 2 and iv.parse(["record", "--out", "x.zip"]).standin_monitor == 2


def test_only_the_windows_of_other_programs_that_meet_a_place_are_found():
    me = os.getpid()
    shown = [iv.Shown(1, me, (0, 0, 100, 100)), iv.Shown(2, 4242, (90, 90, 200, 200)),
             iv.Shown(3, 4242, (100, 0, 200, 50)), iv.Shown(4, 4243, (0, 0, 3000, 2000), desktop=True)]
    found = iv.foreign_windows([(0, 0, 100, 100)], {me}, shown)
    assert [w.hwnd for w in found] == [2]  # (ours, one only touching its edge, the desktop's own: left out)
    assert iv.foreign_windows([(0, 0, 100, 100)], {me, 4242}, shown) == []
    assert [w.hwnd for w in iv.foreign_windows([(0, 0, 100, 100), (150, 10, 160, 20)], {me}, shown)] == [2, 3]


def test_the_stand_in_run_it_asks_for():
    args = iv.parse(["record", "--out", "x.zip"])
    assert args.start_ollama == iv.RECORD_PORT == 11435 and args.fps == iv.RECORD_FPS
    argv = iv.e2e_argv(args, Path("work"))
    assert argv[-2:] == ["--editing", "--chooser"]  # (TASlation starting editing, and asking for the viewer)
    pairs = dict(zip(argv[:-2:2], argv[1:-2:2]))
    assert pairs["--scenario"] == iv.SCENARIO and pairs["--soft-first"] == "off"
    assert pairs["--start-ollama"] == "11435" and pairs["--out"] == "work"
    assert pairs["--standin-size"] == iv.STANDIN_SIZE and pairs["--first"] == str(iv.FIRST_PAGE)
    assert pairs["--standin-monitor"] == str(iv.STANDIN_MONITOR) == "2"
    assert "--see-edit" not in argv and "--see-truth" not in argv and "--see-pane-shot" not in argv
    assert "11434" not in argv


def test_the_e2e_run_places_its_stand_in_where_the_tool_looked():
    import standin_e2e as e2e

    parsed = e2e.parse(iv.e2e_argv(iv.parse(["record", "--out", "x.zip"]), Path("work")))
    assert parsed.standin_monitor == iv.STANDIN_MONITOR and parsed.standin_size == iv.STANDIN_SIZE
    assert parsed.chooser is True and parsed.editing is True and parsed.soft_first == "off"


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


STANDIN = (100, 70, 1600, 1000)  # (the stand-in's window on the made-up screen)


def screen_of(monkeypatch, shown: list, front: list, locks: list | None = None) -> None:
    """A made-up screen for `Run.check_screen`: its windows *shown*, the process in front *front[0]*."""
    monkeypatch.setattr(iv, "windows_now", lambda: list(shown))
    monkeypatch.setattr(iv, "frame_rect", lambda hwnd: STANDIN)
    monkeypatch.setattr(iv, "front_pid", lambda: front[0])
    monkeypatch.setattr(iv, "lock_foreground", lambda on: (locks.append(on) if locks is not None else None) or True)


def test_the_take_is_given_up_when_another_programs_window_meets_the_stand_in(tmp_path, monkeypatch):
    me = os.getpid()
    shown = [iv.Shown(1, me, (500, 300, 900, 500)), iv.Shown(2, 777, STANDIN),  # (the chooser; the stand-in)
             iv.Shown(3, 4242, (1600, 0, 1900, 500)),  # (another program's beside it: only touching)
             iv.Shown(4, 4243, (0, 0, 3840, 1080), desktop=True)]
    locks: list = []
    screen_of(monkeypatch, shown, [4242], locks)
    run = iv.Run(tmp_path / "r.zip")
    try:
        assert run.check_screen() == []  # (no watch yet: nothing looked at)
        run.watch, run.browser = SimpleNamespace(hwnd=5), SimpleNamespace(tree=[777])
        assert run.pids() == {me, 777}
        assert run.check_screen() == shown and run.checks == 1 and locks == [True] and not run.failed
        assert run.check_screen() == shown and locks == [True]  # (the lock asked for again every LOCK_EVERY_S)
        run.begin("panes")
        shown.append(iv.Shown(5, 4242, (1590, 900, 1700, 1100)))  # (it comes over a corner, above or below)
        assert run.check_screen() is None
        assert run.failed == iv.FOREIGN and run.foreign == 1 and run.foreign_where == [[1590, 900, 1700, 1100]]
        assert run.scenes[0]["failed"] == iv.FOREIGN and run.scenes[0]["t1"] is not None
    finally:
        run.writer.abandon()


def test_the_take_is_given_up_when_the_foreground_comes_to_ours_from_another_programs(tmp_path, monkeypatch):
    me = os.getpid()
    front = [4242]
    screen_of(monkeypatch, [iv.Shown(2, 777, STANDIN)], front)
    run = iv.Run(tmp_path / "r.zip")
    try:
        run.watch, run.browser = SimpleNamespace(hwnd=5), SimpleNamespace(tree=[777])
        assert run.check_screen() is not None and run.front == 4242
        front[0] = 4243  # (from one program's to another's: not ours)
        assert run.check_screen() is not None
        run.front = me
        front[0] = 4242  # (from ours to another program's: the person's click elsewhere)
        assert run.check_screen() is not None
        run.begin("edit")
        front[0] = 777  # (to the stand-in's, from another program's)
        assert run.check_screen() is None
        assert run.failed == iv.TAKEN and run.fronts_taken == 1 and run.scenes[0]["failed"] == iv.TAKEN
        meta = run.meta({"version": "9.9.9"})
        assert meta["check"]["fronts_taken"] == 1 and meta["check"]["windows_looked_at"] == 4
        iv.check_no_text(meta)
    finally:
        run.writer.abandon()


def test_what_could_take_the_foreground_acts_only_while_one_of_ours_has_it():
    import tkinter

    from taslation.capture import windows
    from taslation.ui import see_menu

    me = os.getpid()
    front = [4242]
    guard = iv.ForegroundGuard(lambda: {me}, front=lambda: front[0])
    calls = []
    given = guard.wrap(lambda *a: calls.append(a) or True, "give_foreground")
    assert given(1) is False and not calls and guard.refused == {"give_foreground": 1}
    front[0] = me
    assert given(2) is True and calls == [(2,)]
    assert iv.ForegroundGuard(lambda: {me}, front=lambda: 1 // 0).allowed() is False  # (not known: not allowed)
    originals = (windows.give_foreground, see_menu._front, tkinter.Misc.focus_force)
    front[0] = 4242
    guard.install()
    try:
        assert windows.give_foreground.__wrapped__ is originals[0]
        assert see_menu._front.__wrapped__ is originals[1] and tkinter.Misc.focus_force.__wrapped__ is originals[2]
        assert windows.give_foreground(123) is False and see_menu._front(123) is False
        assert tkinter.Misc.focus_force(None) is None
        assert guard.refused == {"give_foreground": 2, "menu_front": 1, "focus_force": 1}
    finally:
        guard.undo()
    assert (windows.give_foreground, see_menu._front, tkinter.Misc.focus_force) == originals


def test_the_choosers_frames_are_kept_on_the_window_checks_alone(tmp_path, monkeypatch):
    import standin_seethrough as ss

    from taslation.capture import windows

    shown = [iv.Shown(1, os.getpid(), (500, 300, 900, 500))]  # (the viewer chooser over the stand-in: ours)
    screen_of(monkeypatch, shown, [4242])
    monkeypatch.setattr(windows, "_client_box", lambda hwnd: (100, 100, 1500, 900))
    copies = []
    monkeypatch.setattr(ss, "screen_copy", lambda x, y, w, h: copies.append((x, y, w, h)) or np.zeros((h, w, 3),
                                                                                                         np.uint8))
    run = iv.Run(tmp_path / "r.zip")
    try:
        run.watch = SimpleNamespace(hwnd=5, over=lambda: None, fake_point=(700, 400))
        run.grab()
        e = iv.EDGE
        assert copies == [(100 + e, 100, 1500 - 2 * e, 900 - e)]
        assert run.kept == 1 and run.client == [1500 - 2 * e, 900 - e] and run.checks == 2  # (before and after)
        assert run.pointer[-1][1:] == [700 - 100 - e, 400 - 100, 0] and run.panes == [] and run.foot == []
        shown.append(iv.Shown(2, 4242, (1590, 0, 1700, 200)))  # (another program's window meets the stand-in's)
        run.grab()
        assert run.kept == 1 and run.failed == iv.FOREIGN and len(copies) == 1
    finally:
        run.writer.abandon()


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


def test_the_programs_other_windows_are_left_out_of_the_check_but_not_the_letterings_own():
    over = SimpleNamespace(hwnd=10)
    mine = {10: (100, 100, 1500, 900), 20: (500, 300, 900, 500), 30: (1400, 200, 1700, 260)}
    p = iv.OWN_PAD
    assert iv.window_masks(mine, over, 100, 100) == [(400 - p, 200 - p, 800 + p, 400 + p),
                                                     (1300 - p, 100 - p, 1600 + p, 160 + p)]


def test_messages_are_posted_to_the_programs_own_windows_only(monkeypatch):
    sent = []
    monkeypatch.setattr(iv, "_user32", lambda: SimpleNamespace(PostMessageW=lambda *a: sent.append(a)))
    monkeypatch.setattr(iv, "window_pid", lambda hwnd: os.getpid() if hwnd == 10 else 4242)
    iv.post(10, 0x0201, 1, 5, 7)
    assert sent == [(10, 0x0201, 1, 7 << 16 | 5)]
    for hwnd in (0, 20):  # (none, another program's)
        with pytest.raises(iv.SceneFailed):
            iv.post_raw(hwnd, iv.WM_CLOSE, 0, 0)
    assert len(sent) == 1


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


def drive(program, run, world=None) -> dict[str, bool]:
    """*program* (`chooser_program`, `scenes_program`) acted to its end without sleeping, on the made-up *world*'s
    clock: a wait's seconds counted on it, a wait for something asked again every TICK_S of it until it holds (past
    its limit: timed out), the world told where the tool's pointer is at each step. Whether each wait for something
    held at once."""
    world = world if world is not None else SimpleNamespace(clock=0.0, tick=lambda point: None)
    asked: dict[str, bool] = {}
    for got in program:
        if isinstance(got, (int, float)):
            world.clock += float(got)
            world.tick(run.watch.fake_point)
            continue
        until, limit, what = got
        waited = 0.0
        while not until():
            waited += iv.TICK_S
            world.clock += iv.TICK_S
            world.tick(run.watch.fake_point)
            if waited > limit:
                raise iv.SceneFailed(f"timed out: {what}")
        asked.setdefault(what, waited == 0.0)
    return asked


class Widget:
    def __init__(self, rect):
        self.rect = rect

    def winfo_rootx(self):
        return self.rect[0]

    def winfo_rooty(self):
        return self.rect[1]

    def winfo_width(self):
        return self.rect[2] - self.rect[0]

    def winfo_height(self):
        return self.rect[3] - self.rect[1]


class FakeChooser(Widget):
    """The parts of `ui.see_menu.ViewerDialog` the chooser's scene uses."""

    def __init__(self, app, listed, at, rect=(500, 300, 900, 500)):
        from taslation.capture import taskbar_title

        super().__init__(rect)
        self.app, self.windows, self.picked = app, listed, None
        dialog = self

        class Box(Widget):
            def current(self, i=None):
                if i is None:
                    return self.at
                self.at = i

            def get(self):
                return taskbar_title(dialog.windows[self.at])

        self.box = Box((rect[0] + 20, rect[1] + 40, rect[2] - 20, rect[1] + 70))
        self.box.at = at
        self.ok_button = Widget((rect[2] - 120, rect[3] - 40, rect[2] - 20, rect[3] - 10))
        self.ok_button.instate = lambda states: False

    def _picked(self):
        self.picked = self.box.current()

    def ok(self):
        self.app.selected, self.app._see_chooser = self.windows[self.picked], None


def chooser_world(monkeypatch, tmp_path, title="Stand-in reader t1a2b3c4d5", at=1, rect=(500, 300, 900, 500)):
    from taslation.capture import windows

    monkeypatch.setattr(windows, "_client_box", lambda hwnd: (100, 100, 1500, 900))
    listed = [windows.WindowInfo(3, "A made-up window", "MadeUp", 300, (0, 0, 400, 300)),
              windows.WindowInfo(5, title, windows.BROWSER_CLASSES[0], 500, STANDIN)]
    app = SimpleNamespace(selected=None)
    app._see_chooser = FakeChooser(app, listed, at, rect)
    director = SimpleNamespace(app=app, browser=SimpleNamespace(hwnd=5), notes=SimpleNamespace(top=30, dpr=1.25),
                               band_px=40, chooser_rows=[])
    run = iv.Run(tmp_path / "chooser.zip")
    run.watch = SimpleNamespace(fake_point=None)
    return director, run


def test_the_viewer_chooser_is_answered_through_its_own_object_with_the_stand_in_preselected(tmp_path, monkeypatch):
    director, run = chooser_world(monkeypatch, tmp_path)
    app, dialog = director.app, director.app._see_chooser
    try:
        asked = drive(iv.chooser_program(director, run, dialog), run)
        assert asked == {"the stand-in listed in the viewer chooser": True, "the stand-in chosen as the viewer": True}
        assert app.selected.hwnd == 5 and app._see_chooser is None and dialog.picked == 1
        assert [s["id"] for s in run.scenes] == ["chooser"] and run.scenes[0]["t1"] is not None
        row = director.chooser_rows[0]
        assert row["preselected_standin"] is True and row["answered_t"] is not None and row["activated"] is False
        assert run.crop_top == 30 + 50 and not run.on.is_set() and run.watch.fake_point is None and not run.down
    finally:
        run.writer.abandon()
    for kw, why in (({"at": 0}, "the stand-in is not preselected in the viewer chooser"),
                    ({"rect": (50, 50, 400, 300)}, "the viewer chooser is not over the stand-in"),
                    ({"title": "Stand-in reader t1a2b3c4d5 - " + a_browser_name()},
                     "the viewer chooser names the stand-in's browser")):
        director, run = chooser_world(monkeypatch, tmp_path, **kw)
        try:
            with pytest.raises(iv.SceneFailed) as failed:
                drive(iv.chooser_program(director, run, director.app._see_chooser), run)
            assert str(failed.value) == why and director.app.selected is None and not run.on.is_set()
        finally:
            run.writer.abandon()


def a_browser_name() -> str:
    from taslation.capture import windows

    return windows.BROWSER_NAMES[0].title()


LEFT_HITS = (("translate", (10, 10, 90, 30)), ("auto", (10, 40, 90, 60)), ("language", (10, 70, 90, 90)),
             ("lettering", (10, 100, 90, 120)), ("indicators", (10, 130, 90, 150)), ("edit", (10, 160, 90, 180)))
FOOT_ROWS = ((0, 480, 250, 500), (0, 500, 250, 520), (0, 520, 250, 540))


class World:
    """A made-up TASlation over a made-up stand-in as the scenes after the chooser see them: the messages posted to
    its windows (`post_raw`) answered at once, the hover's delay counted on the scenes' own clock."""

    ORIGIN, SIZE = (1000, 500), (800, 600)
    LEFT, RIGHT = (740, 520, 990, 1080), (1810, 520, 2060, 1080)
    PATCHES = ((120, 120, 280, 180), (420, 90, 500, 150), (600, 400, 700, 460))
    BOXES = ((100, 100, 300, 200), (400, 80, 520, 160))
    OVER, PANES, EDITOR, MENU = 10, {"left": 11, "right": 12}, 99, 77

    def __init__(self, hover_delay=1.2):
        self.clock, self.hover_delay = 0.0, hover_delay
        self.reader = False  # (TASlation starts editing)
        self.language, self.serial = "English", 1
        self.boxes = list(self.BOXES)
        self.chosen = self.entry = self.pressed = self.moved = self.last_down = self.hover = self.bare = None
        self.editor = self.menu = 0
        self.events = [{"ev": "hold", "id": 1}]
        self.posted: list[tuple[int, int]] = []

    def tick(self, point):
        o = self.ORIGIN
        at = None if point is None else next(
            (i for i, b in enumerate(self.PATCHES)
             if o[0] + b[0] <= point[0] < o[0] + b[2] and o[1] + b[1] <= point[1] < o[1] + b[3]), None)
        if at is None:
            self.hover = self.bare = None
        elif self.hover is None or self.hover[0] != at:
            self.hover, self.bare = (at, self.clock), None
        elif self.clock - self.hover[1] >= self.hover_delay:
            self.bare = at  # (its original shown, the bubble's block in the right pane)

    def turn(self, _director, n):
        assert n == 1
        self.serial += 1
        self.events.append({"ev": "draw", "why": "next"})

    def marks(self):
        from taslation import seethrough as st

        if self.reader:
            return None
        plates = tuple((np.zeros((14, 20, 4), np.uint8), (b[0] + 4, b[1] + 4)) for b in self.boxes)
        return st.Marks(key=self.serial, boxes=tuple(self.boxes), plates=plates,
                        chosen=() if self.chosen is None else (self.chosen,), locked=bool(self.editor))

    def post(self, hwnd, message, _wparam, lparam):
        import standin_seethrough as ss

        self.posted.append((hwnd, message))
        point = (lparam & 0xFFFF, (lparam >> 16) & 0xFFFF)
        if hwnd in self.PANES.values():
            if message == ss.WM_LBUTTONUP and hwnd == self.PANES["left"]:
                name = next((n for n, b in LEFT_HITS if b[0] <= point[0] < b[2] and b[1] <= point[1] < b[3]), "")
                self.entry = None  # (a pane's click gives a place entry up first)
                if name == "edit":
                    self.reader, self.chosen = not self.reader, None
                elif name == "language":
                    self.menu = self.MENU
            return
        if hwnd == self.OVER:
            if message == ss.WM_LBUTTONDOWN:
                twice = self.last_down == (point, self.clock)  # (a second press at once where the first was)
                self.last_down, self.pressed, self.moved = (point, self.clock), point, None
                if twice and self.chosen is not None:
                    self.editor = self.EDITOR
            elif message == ss.WM_MOUSEMOVE:
                self.moved = point
            elif message == ss.WM_LBUTTONUP:
                self.release(point)
            return
        if hwnd == self.EDITOR and message == iv.WM_CLOSE:
            self.editor = 0
            return
        raise AssertionError(f"a message for a window the scenes never post to: {hwnd}")

    def release(self, point):
        from taslation import seethrough as st

        press, self.pressed = self.pressed, None
        if self.editor or press is None:
            return
        if self.moved is not None and max(abs(self.moved[0] - press[0]), abs(self.moved[1] - press[1])) > 4:
            dx, dy = point[0] - press[0], point[1] - press[1]
            i = next(i for i, b in enumerate(self.boxes) if b[0] <= press[0] < b[2] and b[1] <= press[1] < b[3])
            b = self.boxes[i]
            self.boxes[i] = (b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy)
            return
        grip = st.edit_grip(self.marks(), point, st.GRIP_PX)
        if grip is None:
            self.chosen, self.entry = None, None  # (the page's empty ground)
        elif grip[1] == st.PLATE:
            self.entry = SimpleNamespace(closed=False)
        else:
            self.chosen, self.entry = grip[0], None


class WorldOver:
    """The see-through window of the made-up world (the parts the scenes read)."""

    def __init__(self, world):
        self.world = world
        self._lock = threading.Lock()
        self.hwnd, self.panes = World.OVER, dict(World.PANES)
        self._last_look = (0, 0, 0, 0, 0, World.ORIGIN, World.SIZE)
        self._press, self._left_out, self._dpi, self._ghost = None, frozenset(), 96, None
        self._hover_delay = world.hover_delay

    @property
    def _store(self):
        return SimpleNamespace(sets=[FakeSet(self.world.serial, World.PATCHES)])

    @property
    def _edit_takes(self):
        return not self.world.reader

    @property
    def _marks_live(self):
        return self.world.marks()

    def shown(self):
        w = self.world
        return w.serial, tuple(i for i in range(len(World.PATCHES)) if i != w.bare), World.ORIGIN, World.SIZE

    def pane_shown(self, side):
        return {"left": World.LEFT, "right": World.RIGHT}.get(side)


class WorldApp:
    """TASlation's window object of the made-up world (the parts the scenes read)."""

    def __init__(self, world):
        from taslation import panes as pn

        self.world = world
        left = pn.Picture(np.zeros((560, 250, 4), np.uint8), LEFT_HITS)
        column = pn.Picture(np.zeros((560, 250, 4), np.uint8), (), FOOT_ROWS)
        self._see_pane_memo = {"left": (1, left, World.LEFT), "right": (2, column, World.RIGHT),
                               "bubble": (3, column, World.RIGHT)}
        self.role_var = SimpleNamespace(get=lambda: "reader" if world.reader else "translator")
        self.lang_var = SimpleNamespace(get=lambda: world.language)
        self.selected = object()

    @property
    def _chosen_region(self):
        w = self.world
        return None if w.chosen is None else SimpleNamespace(bbox=w.boxes[w.chosen])

    @property
    def _see_place_entry(self):
        return self.world.entry

    @property
    def _see_right_used(self):
        return "bubble" if self.world.bare is not None else "right"


def scenes_world(monkeypatch, tmp_path, world):
    over = WorldOver(world)
    monkeypatch.setattr(iv, "post_raw", world.post)
    monkeypatch.setattr(iv, "menu_window", lambda: world.menu)
    monkeypatch.setattr(iv, "end_menu", lambda: setattr(world, "menu", 0))
    monkeypatch.setattr(iv, "release_hold", world.turn)
    monkeypatch.setattr(iv, "double_click_s", lambda: 0.5)
    director = SimpleNamespace(app=WorldApp(world), events=world.events, idle=lambda: True, control={"go": 0},
                               standin_dir=tmp_path, notes=SimpleNamespace(top=30, dpr=1.0), band_px=40)
    run = iv.Run(tmp_path / "scenes.zip")
    run.watch = SimpleNamespace(over=lambda: over, fake_point=None, _editor_window=lambda: world.editor)
    return director, run


def test_the_scenes_after_the_chooser_on_a_made_up_taslation(tmp_path, monkeypatch):
    world = World()
    director, run = scenes_world(monkeypatch, tmp_path, world)
    try:
        asked = drive(iv.scenes_program(director, run), run, world)
        assert [s["id"] for s in run.scenes] == list(ORDER[1:]) and all(s["t1"] is not None for s in run.scenes)
        assert all(asked.values()), asked  # (each thing waited for there at once: the rests long enough)
        assert asked["the original under the pointer"] is True  # (the hover's delay rested past, 1.2 s here)
        assert {"Reader mode", "the list of languages closed", "the box selected, its handles", "the region editor",
                "the region editor closed", "the place entry", "the place entry given up"} <= set(asked)
        assert world.reader is False and world.language == "English" and world.menu == 0 and world.editor == 0
        assert world.boxes == list(World.BOXES) and world.entry is None and world.serial == 2  # (dragged and back)
        assert {hwnd for hwnd, _m in world.posted} == {World.OVER, World.PANES["left"], World.EDITOR}
        assert (World.EDITOR, iv.WM_CLOSE) in world.posted
        assert run.crop_top == 70 and not run.on.is_set() and run.watch.fake_point is None and not run.down
        assert run.drag_box is None
    finally:
        run.writer.abandon()


def test_a_scene_fails_where_the_made_up_taslation_does_not_do_what_it_shows(tmp_path, monkeypatch):
    world = World()
    director, run = scenes_world(monkeypatch, tmp_path, world)
    monkeypatch.setattr(iv, "end_menu", lambda: (setattr(world, "menu", 0), setattr(world, "language", "French")))
    try:
        with pytest.raises(iv.SceneFailed) as failed:
            drive(iv.scenes_program(director, run), run, world)
        assert str(failed.value) == "the target language changed"
    finally:
        run.writer.abandon()
    world = World()
    director, run = scenes_world(monkeypatch, tmp_path, world)
    director.app._see_pane_memo["right"] = (2, None, World.RIGHT)  # (no right pane's picture: no foot)
    try:
        with pytest.raises(iv.SceneFailed) as failed:
            drive(iv.scenes_program(director, run), run, world)
        assert str(failed.value) == "the right pane shows no foot"
        assert [s["id"] for s in run.scenes] == ["reader", "turn", "panes", "foot"]
    finally:
        run.writer.abandon()


def test_the_foot_is_the_columns_on_show():
    world = World()
    app, over = WorldApp(world), WorldOver(world)
    right = World.RIGHT
    assert iv.foot_box(app, over) == (right[0], right[1] + 480, right[0] + 250, right[1] + 540)
    world.bare = 0  # (a bubble's block in the right pane: its column's foot)
    app._see_pane_memo["right"] = (2, None, None)
    assert iv.foot_box(app, over) == (right[0], right[1] + 480, right[0] + 250, right[1] + 540)
    assert iv.foot_box(None, over) is None and iv.foot_box(app, None) is None
    over.pane_shown = lambda side: None
    assert iv.foot_box(app, over) is None


def test_the_plate_and_the_ground_the_edit_scene_clicks():
    from taslation import seethrough as st

    world = World()
    over = WorldOver(world)
    assert iv.index_near(over, (101, 99, 300, 201)) == 0 and iv.index_near(over, (0, 0, 9, 9)) is None
    plate = iv.plate_point(over, 0)
    assert plate == (114, 111) and st.edit_grip(world.marks(), plate, st.GRIP_PX) == (0, st.PLATE)
    assert iv.plate_point(over, 5) is None
    ground = iv.ground_point(over)
    assert ground is not None and st.edit_grip(world.marks(), ground, st.GRIP_PX) is None
    world.boxes = [(0, 0, 800, 600)]  # (no empty ground)
    assert iv.ground_point(over) is None
    app = WorldApp(world)
    world.chosen = 0
    assert iv.selected(app, over, 0, (0, 0, 800, 600)) and not iv.selected(app, over, 0, (0, 0, 10, 10))
    assert iv.place_entry(app) is None
    world.entry = SimpleNamespace(closed=False)
    assert iv.place_entry(app) is world.entry
    world.entry.closed = True
    assert iv.place_entry(app) is None


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
