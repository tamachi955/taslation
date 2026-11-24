"""The promotional video tool (tools/promo_video.py) without a window, a model or a manga page: made-up recordings
of drawn rectangles and text, the pages' times taken from the window's page events, the video at real speed (a long
pause cut and said, a page's time never), two sides started together, the cards, the credit on every frame, the
H.264 MP4 read back from its boxes, the GIF made smaller until it fits, and where files may go; recordings from the
start (the page on show timed from the window's appearance, a turn made at ready), the start's quiet stretch shown
faster with the clocks in real seconds and the speed said on every such frame."""

from __future__ import annotations

import struct
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import promo_video as pv  # noqa: E402
import standin_e2e  # noqa: E402
import standin_viewer as sv  # noqa: E402

SMALL = (200, 250)


def made_up(tmp_path: Path, name: str, pages, pauses=2000.0, fps: float = 10.0) -> pv.Recording:
    return pv.Recording(pv.made_up(tmp_path / f"{name}.zip", name, pages, pauses, size=SMALL, fps=fps))


def no_cards(**kw) -> pv.Options:
    return pv.Options(title_ms=0, end_ms=0, **kw)


# ---------------------------------------------------------------------------------------------------- the pages' times
def test_page_times_from_the_windows_page_events():
    turns = [{"k": 1, "t": 1000.0, "screen": [1, 0]}, {"k": 2, "t": 9000.0, "screen": [2, 0]},
             {"k": 3, "t": 20000.0, "screen": [3, 0]}]
    displays = [
        {"t": 1050, "screen": [0, 0], "kind": "translated", "lettered": 5},  # the page before, drawn after the turn
        {"t": 1100, "screen": [1, 0], "kind": "live", "lettered": 0},
        {"t": 2000, "screen": [1, 0], "kind": "filling", "lettered": 1},
        {"t": 3000, "screen": [1, 0], "kind": "filling", "lettered": 2},
        {"t": 3500, "screen": [1, 0], "kind": "filling", "lettered": 3},
        {"t": 3600, "screen": [1, 0], "kind": "translated", "lettered": 3},
        {"t": 9100, "screen": [2, 0], "kind": "live", "lettered": 0},  # page 2: no text at all
        {"t": 9800, "screen": [2, 0], "kind": "translated", "lettered": 0},
        {"t": 20100, "screen": [3, 0], "kind": "filling", "lettered": 1},  # page 3: never finished
    ]
    results = [{"t": 3610, "screen": [1, 0], "bubbles": 3}, {"t": 9810, "screen": [2, 0], "bubbles": 0}]
    p1, p2, p3 = pv.page_times(turns, displays, results, end=30000.0)
    assert (p1["first_ms"], p1["page_ms"], p1["result_ms"], p1["bubbles"], p1["finished"]) == (1000, 2500, 2610, 3,
                                                                                              True)
    assert p1["until"] == 9000.0
    assert (p2["first_ms"], p2["page_ms"], p2["bubbles"]) == (None, 810, 0)  # nothing to letter: the page done
    assert (p3["first_ms"], p3["page_ms"], p3["finished"], p3["until"]) == (100, None, False, 30000.0)


def test_pictures_without_a_readable_code_count_from_the_viewers_own_picture():
    turns = [{"k": 1, "t": 1000.0, "screen": [1, 0]}]
    displays = [{"t": 1050, "screen": None, "kind": "translated", "lettered": 5},  # the page before: left out
                {"t": 1100, "screen": None, "kind": "live", "lettered": 0},
                {"t": 1900, "screen": None, "kind": "filling", "lettered": 1},
                {"t": 2400, "screen": None, "kind": "filling", "lettered": 2}]
    (page,) = pv.page_times(turns, displays, [{"t": 2500, "screen": None, "bubbles": 2}], end=5000.0)
    assert (page["first_ms"], page["page_ms"], page["bubbles"]) == (900, 1400, 2)


def test_the_bubbles_lettered_as_the_page_showed_them(tmp_path):
    rec = made_up(tmp_path, "a", [(3000, 4)])
    page = rec.pages[0]
    a = page["t"]
    assert page["page_ms"] == 3000 and page["bubbles"] == 4 and page["first_ms"] == 3000 * 0.45
    assert rec.lettered(0, a + 100) == 0
    assert rec.lettered(0, a + 1360) == 1
    assert rec.lettered(0, a + 2990) == 3
    assert rec.lettered(0, a + 3001) == 4 and rec.lettered(0, a + 9000) == 4
    rec.close()


def test_a_recording_keeps_a_picture_the_same_as_the_last_once(tmp_path):
    writer = pv.RecordingWriter(tmp_path / "r.zip")
    red, blue = Image.new("RGB", (40, 30), (200, 0, 0)), Image.new("RGB", (40, 30), (0, 0, 200))
    assert writer.add(1000.0, red) and not writer.add(1066.0, red.copy()) and writer.add(1133.0, blue)
    writer.finish({"turns": [], "displays": [], "results": [], "end_t": 1200.0})
    rec = pv.Recording(tmp_path / "r.zip")
    assert len(rec.frames) == 3 and len({name for _t, name in rec.frames}) == 2 and rec.size == (40, 30)
    assert rec.picture(rec.at(1100.0)).getpixel((0, 0)) == pytest.approx((200, 0, 0), abs=3)
    assert rec.picture(rec.at(1133.0)).getpixel((0, 0)) == pytest.approx((0, 0, 200), abs=3)
    assert rec.at(0.0) == rec.frames[0][1]  # before the first: the first
    rec.close()


# ---------------------------------------------------------------------------------------------------- the video
def test_one_recording_at_real_speed(tmp_path):
    rec = made_up(tmp_path, "a", [(3400, 6), (2900, 5), (4100, 8)])
    video = pv.Video([rec], no_cards(), fps=30)
    pages = [s for s in video.segments if s.kind == "page"]
    assert [s.body for s in pages] == [3400, 2900, 4100]
    assert pages[0].lead == 0  # the page before the first is the start-up's
    for seg, start in zip(video.segments, video.starts):
        page = rec.pages[seg.index]
        for u in (0.0, 500.0, seg.body - 1, seg.body, seg.body + 300):
            side = pv.side_state(rec, seg.index, u)
            assert side.source_t == pytest.approx(page["t"] + u)  # one ms of the video is one ms of the run
        assert pv.side_state(rec, seg.index, seg.body - 1).watch == "running"
        stopped = pv.side_state(rec, seg.index, seg.body + 200)
        assert stopped.watch == "stopped" and stopped.watch_ms == page["page_ms"] and stopped.lettered == page["bubbles"]
    # the pauses (2 s after a page finished, as the record's pace) shown as they were
    for a, b in zip(pages, pages[1:]):
        real = rec.pages[b.index]["t"] - (rec.pages[a.index]["t"] + a.body)
        assert a.tail + b.lead == pytest.approx(real) and a.cut_after is None and b.cut_before is None
    assert {video.facts(i).note for i in range(len(video))} <= {pv.NOTE_REAL, ""}
    rec.close()


def test_a_long_pause_is_shortened_and_the_caption_says_so(tmp_path):
    rec = made_up(tmp_path, "a", [(3000, 4), (2500, 3), (2800, 5)], pauses=[2000, 6000, 2000])
    video = pv.Video([rec], no_cards(max_pause_ms=2500), fps=30)
    p1, p2, p3 = (s for s in video.segments if s.kind == "page")
    assert p1.cut_after is None
    real = rec.pages[2]["t"] - rec.pages[1]["stop_t"]
    assert p2.cut_after == (pytest.approx(real), 2500) and p3.cut_before == p2.cut_after
    assert p2.tail + p3.lead == pytest.approx(2500)
    assert p2.body == 2500 and p3.body == 2800  # never the pages' own time
    said = {video.facts(i).note for i in range(len(video))}
    assert f"{pv.NOTE_REAL}. Pause between pages shortened from {real / 1000:.1f} s to 2.5 s" in said
    start = video.starts[video.segments.index(p2)]
    assert video.facts(int((start + p2.lead + 1000) * 30 / 1000)).note == pv.NOTE_REAL  # not while the page runs
    rec.close()


def test_two_sides_start_each_page_together_and_the_faster_stops_first(tmp_path):
    slow = made_up(tmp_path, "slow", [(3400, 6), (2900, 5), (4100, 8)])
    fast = made_up(tmp_path, "fast", [(2300, 6), (2000, 5), (2700, 8)])
    video = pv.Video([slow, fast], no_cards(), labels=["A", "B"], fps=30)
    for seg, start in zip(video.segments, video.starts):
        turn = int(round((start + seg.lead) * 30 / 1000)) + 1  # the first frame after the turn
        facts = video.facts(turn)
        assert [s.watch for s in facts.sides] == ["running", "running"]
        assert facts.sides[0].watch_ms == pytest.approx(facts.sides[1].watch_ms)  # the same moment on both
        assert seg.body == max(pv.page_span(slow, seg.index), pv.page_span(fast, seg.index))
        stops = {}
        for i in range(turn, int((start + seg.ms) * 30 / 1000)):
            for s, side in enumerate(video.facts(i).sides):
                if side.watch == "stopped":
                    stops.setdefault(s, i)
        assert stops[1] < stops[0]  # the faster side's stopwatch stops first
        for s, rec in enumerate((slow, fast)):
            page = rec.pages[seg.index]
            assert video.facts(stops[s]).sides[s].watch_ms == page["page_ms"]
            # a side that waits never shows what it showed after its own next turn
            assert all(video.facts(i).sides[s].source_t < page["until"]
                       for i in range(turn, int((start + seg.ms) * 30 / 1000)))
    assert all(f.note in (pv.NOTE_SIDES, "") for f in map(video.facts, range(len(video))))
    slow.close()
    fast.close()


def test_a_stretch_of_the_pages(tmp_path):
    rec = made_up(tmp_path, "a", [(3000, 4), (2500, 3), (2800, 5), (2600, 2)])
    video = pv.Video([rec], no_cards(pages=(2, 3), lead_ms=400))
    pages = [s for s in video.segments if s.kind == "page"]
    assert [(s.number, s.index) for s in pages] == [(1, 1), (2, 2)]
    assert pages[0].lead == 400  # the page before is one of the run's: a lead as any page's
    assert video.facts(len(video) - 1).of == 2
    for bad in ((0, 2), (3, 2), (2, 9)):
        with pytest.raises(SystemExit):
            pv.Video([rec], no_cards(pages=bad))
    rec.close()


def test_a_page_never_finished_says_so(tmp_path):
    rec = made_up(tmp_path, "a", [(3000, 4), (2500, 3)])
    rec.pages[1].update(page_ms=None, stop_t=None, finished=False)
    span = pv.page_span(rec, 1)
    assert span == rec.pages[1]["until"] - rec.pages[1]["t"]
    assert pv.side_state(rec, 1, span - 1).watch == "running"
    assert pv.side_state(rec, 1, span + 10).watch == "unfinished"
    rec.close()


def test_the_cards(tmp_path):
    rec = made_up(tmp_path, "a", [(2000, 3)])
    lines = ["Translation 2x faster", "Measured on a made-up computer", pv.PROJECT]
    video = pv.Video([rec], pv.Options(title_ms=2500, end_ms=4500), "Title\\nsecond line", lines)
    assert [s.kind for s in video.segments] == ["title", "page", "end"]
    assert video.segments[0].ms == 2500 and video.segments[-1].ms == 4500
    assert video.facts(0).kind == "title" and video.facts(len(video) - 1).kind == "end"
    title = video.image(video.facts(0))
    assert title.size == video.layout.size
    with pytest.raises(SystemExit):
        pv.Video([rec], pv.Options(), "T", ["1", "2", "3", "4", "5"])
    assert [s.kind for s in pv.Video([rec], no_cards()).segments] == ["page"]
    rec.close()


def test_an_end_line_too_long_is_set_smaller_before_it_is_wrapped():
    short, long = "Short", "A line of the end card that is much too long to stand at the card's own size"
    assert pv.fitting_size([short], 34, 24, 600) == 34
    size = pv.fitting_size([short, long], 34, 10, 1000)
    assert size < 34 and pv.text_width(long, pv.font(size)) <= 1000 < pv.text_width(long, pv.font(size + 1))
    assert pv.fitting_size([long], 34, 24, 200) == 24  # (no smaller than that: wrapped instead)


def test_every_frame_carries_the_credit(tmp_path):
    a = made_up(tmp_path, "a", [(2000, 3), (1500, 2)], pauses=[2000, 5000])
    b = made_up(tmp_path, "b", [(1500, 3), (1200, 2)])
    for recs in ([a], [a, b]):
        video = pv.Video(recs, pv.Options(title_ms=1000, end_ms=1000), "Title", ["one line"], fps=10)
        layout = video.layout
        w, h = layout.size
        assert w % 2 == 0 and h % 2 == 0 and w <= 1280
        reference = Image.new("RGB", layout.size)
        reference.paste(layout.caption(""), (0, h - layout.caption_h))
        box = layout.credit_box()
        credit = reference.crop(box)
        assert len(credit.getcolors(1 << 16) or ()) > 2  # (letters there)
        for i in range(len(video)):
            assert video.image(video.facts(i)).crop(box).tobytes() == credit.tobytes(), i
    a.close()
    b.close()


def test_the_video_is_at_most_1280_wide_and_never_enlarges(tmp_path):
    big = pv.Recording(pv.made_up(tmp_path / "big.zip", "big", [(1000, 1)], size=(900, 1000), fps=5))
    small = pv.Recording(pv.made_up(tmp_path / "small.zip", "small", [(1000, 1)], size=(500, 600), fps=5))
    assert pv.Video([big], no_cards()).layout.size[0] == 900
    two = pv.Video([big, big], no_cards()).layout
    assert two.size[0] <= 1280 and two.column == 634
    assert pv.Video([big, small], no_cards()).layout.column == 500  # the narrower side's width, not enlarged
    big.close()
    small.close()


# ---------------------------------------------------------------------------------------------------- MP4 and GIF
def box(kind: str, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), kind.encode("latin-1")) + payload


def made_up_mp4() -> tuple[bytes, list[bytes]]:
    """An MP4's boxes as an encoder that writes ``moov`` last leaves them: three samples of ten bytes in ``mdat``."""
    samples = [b"A" * 10, b"B" * 10, b"C" * 10]
    ftyp = box("ftyp", b"isom" + bytes(4) + b"isom")
    mdat = box("mdat", b"".join(samples))
    offsets = [len(ftyp) + 8 + 10 * k for k in range(3)]
    entry = bytes(6) + struct.pack(">H", 1) + bytes(16) + struct.pack(">HH", 320, 240) + bytes(50)
    avc1 = box("avc1", entry + box("avcC", bytes([1, 100, 0, 31, 0xFF, 0xE1, 0])))
    stbl = box("stbl", box("stsd", bytes(4) + struct.pack(">I", 1) + avc1)
               + box("stsz", bytes(4) + struct.pack(">II", 0, 3) + struct.pack(">III", 10, 10, 10))
               + box("stco", bytes(4) + struct.pack(">I", 3) + struct.pack(">III", *offsets)))
    mdia = box("mdia", box("mdhd", bytes(4) + struct.pack(">IIII", 0, 0, 1000, 3000) + bytes(4))
               + box("hdlr", bytes(8) + b"vide" + bytes(13)) + box("minf", stbl))
    return ftyp + mdat + box("moov", box("trak", mdia)), samples


def test_an_mp4_is_read_from_its_boxes_and_its_moov_put_first(tmp_path):
    data, samples = made_up_mp4()
    path = tmp_path / "v.mp4"
    path.write_bytes(data)
    facts = pv.mp4_facts(path)
    assert (facts["entry"], facts["profile"], facts["level"], facts["width"], facts["height"]) == ("avc1", "High", 3.1,
                                                                                                  320, 240)
    assert (facts["frames"], facts["seconds"], facts["moov_first"]) == (3, 3.0, False)
    assert pv.faststart(path) and not pv.faststart(path)
    moved = path.read_bytes()
    assert len(moved) == len(data) and pv.mp4_facts(path)["moov_first"]
    stco = pv.find_box(moved, ["moov", "trak", "mdia", "minf", "stbl", "stco"])
    offsets = struct.unpack(">III", moved[stco[1] + 8:stco[1] + 20])
    assert [moved[o:o + 10] for o in offsets] == samples  # the chunks found where they now are


def test_an_mp4_is_h264_read_back_frame_by_frame(tmp_path):
    if sys.platform != "win32":
        pytest.skip("Media Foundation is Windows'")
    rec = made_up(tmp_path, "a", [(1500, 2)], fps=10)
    video = pv.Video([rec], no_cards(), fps=10)
    try:
        facts = pv.write_mp4(video.frames(), tmp_path / "v.mp4", video.layout.size, 10, len(video))
    except pv.VideoError as e:
        if "did not open" in str(e):
            pytest.skip("no H.264 writer on this computer")
        raise
    assert facts["entry"] == "avc1" and facts["codec"] == "H.264" and facts["moov_first"]
    assert facts["frames"] == facts["read_back_frames"] == len(video)
    assert (facts["width"], facts["height"]) == video.layout.size
    assert facts["hardware_acceleration"] == 0  # (the software encoder: nothing on the GPU)
    assert not list(tmp_path.glob("*.part.*"))
    rec.close()


def test_no_mp4_gives_a_gif_and_says_why(tmp_path, monkeypatch):
    rec = made_up(tmp_path, "a", [(1200, 2)], fps=5)

    def refused(*_a, **_k):
        raise pv.VideoError("Media Foundation's H.264 writer did not open")

    monkeypatch.setattr(pv, "write_mp4", refused)
    report = pv.render([rec], tmp_path / "v.mp4", no_cards(), fps=10)
    assert report["mp4_failed"].startswith("Media Foundation") and report["result"]["format"] == "gif"
    assert Path(report["result"]["path"]) == tmp_path / "v.gif" and (tmp_path / "v.gif").is_file()
    assert not (tmp_path / "v.mp4").exists()
    rec.close()


def test_a_gif_is_made_smaller_until_it_fits(tmp_path):
    rec = made_up(tmp_path, "a", [(1500, 3), (1200, 2)], fps=5)

    def make(width, fps):
        return pv.Video([rec], no_cards(), fps=fps, max_width=int(width))

    steps = ((1.0, 10.0), (0.5, 10.0), (0.3, 5.0))
    whole = pv.write_gif(make, tmp_path / "a.gif", 10 ** 9, 200, steps)
    assert whole["tried"] == [{"width": 200, "fps": 10.0, "bytes": whole["bytes"]}]
    assert whole["seconds"] == pytest.approx(make(200, 10).ms / 1000, abs=0.1)
    smaller = pv.write_gif(make, tmp_path / "b.gif", whole["bytes"] - 1, 200, steps)
    assert len(smaller["tried"]) >= 2 and smaller["bytes"] <= whole["bytes"] - 1
    assert (tmp_path / "b.gif").stat().st_size == smaller["bytes"] and Image.open(tmp_path / "b.gif").n_frames > 1
    with pytest.raises(pv.VideoError):
        pv.write_gif(make, tmp_path / "c.gif", 100, 200, steps)
    assert not (tmp_path / "c.gif").exists() and not list(tmp_path.glob("*.part.*"))
    rec.close()


def test_gif_frame_times_add_up():
    for fps in (8.0, 10.0, 15.0, 30.0):
        times = pv.gif_durations(300, fps)
        assert all(t % 10 == 0 for t in times) and abs(sum(times) - 300 * 1000 / fps) <= 10


# ---------------------------------------------------------------------------------------------------- the record's parts
def test_where_files_go(tmp_path):
    with pytest.raises(SystemExit):
        pv.check_video_path(ROOT / "tools" / "promo.mp4")  # could be committed
    with pytest.raises(SystemExit):
        pv.check_video_path(pv.REAL_STATE / "promo.mp4")
    assert pv.check_video_path(tmp_path / "promo.mp4") == (tmp_path / "promo.mp4").resolve()
    for bad in (ROOT / "rec.zip", pv.REAL_STATE / "rec.zip"):
        with pytest.raises(SystemExit):
            pv.check_scratch_path(bad)
    assert pv.check_scratch_path(tmp_path / "rec.zip") == (tmp_path / "rec.zip").resolve()


def test_the_stand_ins_script_and_pages():
    assert pv.script_of(3) == "g1,n,g2,n,g3,n,e"
    assert [s.op for s in sv.parse_script(pv.script_of(2))] == ["g", "n", "g", "n", "e"]
    assert pv.pages_needed(6, "single") == 7 and pv.pages_needed(6, "spread") == 14


def overlap(a, b) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def test_the_windows_go_side_by_side():
    one = [((0, 0, 1920, 1040), True)]
    standin, own = pv.places(one, (760, 1000), (860, 1000))
    assert not overlap(standin, own) and own[0] + own[2] <= 1920 and standin[3] <= 1040 and own[3] <= 1040 - 80
    two = [((0, 0, 1920, 1040), True), ((1920, 0, 3840, 1040), False)]
    standin, own = pv.places(two, (760, 1000), (860, 1000))
    assert standin[0] < 1920 <= own[0] and (own[2], standin[2]) == (860, 760)
    narrow = [((0, 0, 1280, 720), True)]
    standin, own = pv.places(narrow, (760, 1000), (860, 1000))
    assert not overlap(standin, own) and own[0] + own[2] <= 1280


def test_the_translator_is_on_this_computer():
    assert pv.loopback("http://127.0.0.1:11435/") == "http://127.0.0.1:11435"
    for bad in ("http://192.168.1.2:11434", "https://127.0.0.1:11434", "http://127.0.0.1", "http://example.com:80"):
        with pytest.raises(SystemExit):
            pv.loopback(bad)


def test_settings_another_checkout_lacks_are_left_out():
    from dataclasses import dataclass

    @dataclass
    class Older:
        state_dir: str = ""
        ui_language: str = "en"

    made = pv.settings_for(Older, state_dir="x", ui_language="en", ollama_url="http://127.0.0.1:11434")
    assert made == Older("x", "en")
    assert pv.settings_for(Older, asked=["ui_language"], state_dir="x", ui_language="ja") == Older("x", "ja")
    with pytest.raises(SystemExit):  # (a setting asked for on the command line that the package lacks)
        pv.settings_for(Older, asked=["ollama_window_cache"], state_dir="x", ollama_window_cache="off")


def test_the_server_taslation_starts_is_on_a_spare_port():
    assert pv.started_url(11436) == "http://127.0.0.1:11436"
    for bad in (11434, 80, 0, 70000):  # (never the default port: the server there is the person's own)
        with pytest.raises(SystemExit):
            pv.started_url(bad)
    args = pv.parse(["record", "--out", "x.zip", "--start-ollama", "11436", "--ollama-window-cache", "off",
                     "--ocr-runs-on", "gpu"])
    assert (args.start_ollama, args.ollama_window_cache, args.ocr_runs_on) == (11436, "off", "gpu")
    plain = pv.parse(["record", "--out", "x.zip"])
    assert (plain.start_ollama, plain.ollama_window_cache, plain.ocr_runs_on) == (None, None, None)


def test_where_the_readers_read_while_the_pictures_were_taken():
    def at(t, *engines, device="gpu", why="setting"):
        return {"t": t, "device": device, "why": why, "engines": list(engines), "loading": False}

    records = [at(0, "cpu", "cpu", device="cpu", why="not_asked"), at(100, "cuda", "cuda"),
               at(900, "cpu", "cpu", device="cpu", why="released"), at(950, "cuda", "cuda")]
    held = pv.readers_during(records, 200, 800)  # (the one in force at the start, none after it)
    assert held == {"placements": [{"device": "gpu", "why": "setting", "engines": ["cuda", "cuda"]}], "all_gpu": True}
    late = pv.readers_during(records, 200, 1000)  # (the readers on the CPU for a while: not all on the GPU)
    assert not late["all_gpu"] and len(late["placements"]) == 2
    assert not pv.readers_during(records, 50, 80)["all_gpu"]  # (on the CPU at the start)
    assert pv.readers_during([], 0, 10) == {"placements": [], "all_gpu": False}
    assert pv.readers_during(records, None, None)["all_gpu"] is False


def test_what_the_starter_chose_is_kept():
    plan = {"gpu": ["translator", "readers", "lama", "layout"], "cpu": [], "short": 0, "why": "room"}
    started = {"setup": {"kv_cache": "q8_0", "full_window": False, "cache_ram": "0", "why": "setting"},
               "gpu_plan": plan, "loaded_at_close": None, "finish": [], "stopped": True}
    assert pv.server_summary(started) == {"full_window": False, "cache_ram_mib": "0", "kv_cache": "q8_0",
                                          "why": "setting", "gpu_plan": plan, "stopped": True,
                                          "loaded_at_close": None}
    assert pv.server_summary(None) is None


def coded(page: int, top: int = 31) -> Image.Image:
    """A frame of the stand-in's, its band carrying the screen's code (as tests/test_standin_viewer.py draws it)."""
    image = Image.new("RGB", (900, 700), (43, 43, 43))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, top, 900, top + 53), fill=(58, 61, 65))
    draw.rectangle((150, top + 80, 750, 660), fill=(240, 240, 240))
    for k, bit in enumerate(sv.cells_of(page, False, False, False)):
        x, y = sv.CODE_X + k * sv.CELL, top + sv.CODE_Y
        draw.rectangle((x, y, x + sv.CELL - 1, y + sv.CELL - 1), fill=(255, 255, 255) if bit else (0, 0, 0))
    return image


# ---------------------------------------------------------------------------------------------------- from the start
FPS = 10.0


def from_start(tmp_path: Path, name: str, mode: str, **kw) -> pv.Recording:
    return pv.Recording(pv.made_up_start(tmp_path / f"{name}.zip", name, mode, size=SMALL, fps=FPS, **kw))


def page_frames(video: pv.Video) -> list[pv.FrameFacts]:
    return [f for f in map(video.facts, range(len(video))) if f.kind == "page"]


def test_a_recording_from_the_start_is_timed_from_the_windows_appearance(tmp_path):
    rec = from_start(tmp_path, "a", "start", appear_ms=900, ready_ms=4800, first_ms=6000, page_ms=9000, bubbles=4)
    assert rec.mode == "start" and rec.from_start
    assert rec.appeared == pytest.approx(rec.meta["launch_t"] + 900, abs=1000 / FPS)  # its first picture drawn
    (page,) = rec.pages
    assert page["start"] and page["t"] == rec.appeared and page["screen"] == [0, 0]
    assert (page["first_ms"], page["page_ms"], page["bubbles"], page["finished"]) == (6000, 9000, 4, True)
    facts = pv.start_facts(rec)
    assert facts["ready_after_appeared_s"] == round((rec.ready_t - rec.appeared) / 1000, 2)
    assert (facts["first_bubble_after_appeared_s"], facts["last_bubble_after_appeared_s"]) == (6.0, 9.0)
    plain = made_up(tmp_path, "plain", [(2000, 3)])
    assert plain.mode == "turns" and not plain.from_start and pv.start_facts(plain) is None
    assert plain.appeared == plain.first  # (no appearance noted: its first picture)
    rec.close()
    plain.close()


def test_a_segments_real_time_through_a_stretch_shown_faster():
    seg = pv.Segment("page", pv.shown_ms(1000 + 6000 + 500, ((1000.0, 5000.0, 4.0),)), lead=1000, body=6000,
                     tail=500, speeds=((1000.0, 5000.0, 4.0),))
    assert seg.ms == 7500 - 3000  # (4 s shown in 1 s)
    assert [seg.u_at(v) for v in (0, 1000, 2000, 2500, 3000, 4000, 4500)] == [-1000, 0, 1000, 3000, 5000, 6000, 6500]
    assert [seg.factor_at(v) for v in (1999, 2000, 2999, 3000)] == [1.0, 4.0, 4.0, 1.0]
    plain = pv.Segment("page", 7500, lead=1000, body=6000, tail=500)
    assert all(plain.u_at(v) == v - 1000 and plain.factor_at(v) == 1.0 for v in (0, 1234, 7500))
    assert pv.sped(0, 999, 4) == () and pv.sped(0, 2000, 1) == () and pv.sped(0, 2000, 4) == ((0, 2000, 4.0),)


def test_the_starts_quiet_stretch_is_sped_up_and_the_clocks_show_real_seconds(tmp_path):
    slow = from_start(tmp_path, "slow", "start", ready_ms=4900, first_ms=8000, page_ms=11000)
    fast = from_start(tmp_path, "fast", "start", appear_ms=1000, ready_ms=4700, first_ms=6000, page_ms=8000)
    opts = no_cards(start_speed=4, start_head_ms=1000, real_before_ms=1500)
    video = pv.Video([slow, fast], opts, labels=["0.7.0", "0.8.0"], fps=FPS)
    (seg,) = video.segments
    assert seg.lead == 0 and seg.body == 11000 and seg.speeds == ((1000, 6000 - 1500, 4.0),)
    assert seg.ms == pytest.approx(11000 + seg.tail - 3500 * 0.75)
    frames = page_frames(video)
    sped = [f for f in frames if f.speed > 1]
    assert sped and all(f.speed == 4 and f.note == pv.sped_note(4) and "x4" in f.note for f in sped)
    assert all(f.note == pv.NOTE_START_SIDES for f in frames if f.speed == 1)
    steps = set()
    for a, b in zip(frames, frames[1:]):  # one frame of the video: 4 x 100 ms of the clocks while sped, else 100 ms
        if a.sides[0].watch == b.sides[0].watch == "running" and a.speed == b.speed:
            step = b.sides[0].watch_ms - a.sides[0].watch_ms
            assert step == pytest.approx(1000 / FPS * a.speed)
            steps.add(round(step))
    assert steps == {100, 400}
    for f in frames:  # both clocks from each window's appearance, the same real seconds on both
        if all(s.watch == "running" for s in f.sides):
            assert f.sides[0].watch_ms == pytest.approx(f.sides[1].watch_ms)
            assert f.sides[0].source_t - slow.appeared == pytest.approx(f.sides[1].source_t - fast.appeared)
    assert all(s.lettered == 0 and s.first_ms is None for f in sped for s in f.sides)  # no bubble while sped up
    last_sped = max(f.sides[1].watch_ms for f in sped)
    assert last_sped <= 6000 - 1500 + 1  # the real time before the first of the first bubbles shown as it was
    end = frames[-1]
    assert [s.watch for s in end.sides] == ["stopped", "stopped"]
    assert [s.watch_ms for s in end.sides] == [11000, 8000] and [s.first_ms for s in end.sides] == [8000, 6000]
    assert [s.ready for s in end.sides] == [True, True]
    assert end.sides[0].start_ms == pytest.approx(slow.ready_t - slow.appeared)  # the start's clock stops at ready
    summary = video.summary()
    assert summary["kind"] == "start" and summary["sped"] == [{"page": 1, "from_s": 1.0, "to_s": 4.5, "factor": 4.0,
                                                               "real_s": 3.5, "shown_s": 0.88}]
    slow.close()
    fast.close()


def test_a_start_shown_in_full(tmp_path):
    rec = from_start(tmp_path, "a", "start", first_ms=6000, page_ms=8000)
    video = pv.Video([rec], no_cards(start_speed=1), fps=FPS)
    (seg,) = video.segments
    assert seg.speeds == () and seg.ms == seg.lead + seg.body + seg.tail
    frames = page_frames(video)
    assert all(f.speed == 1 and f.note == pv.NOTE_START for f in frames)
    assert all(f.sides[0].watch_ms == pytest.approx(min(f.ms, 8000)) for f in frames)  # one ms shown is one ms
    rec.close()


def test_a_turn_at_ready_shows_each_window_from_its_appearance_and_times_the_turn(tmp_path):
    slow = from_start(tmp_path, "slow", "turn_at_ready", appear_ms=900, ready_ms=4900, first_ms=7000,
                      page_ms=11000, turn_ms=150)
    fast = from_start(tmp_path, "fast", "turn_at_ready", appear_ms=1000, ready_ms=4300, first_ms=2600,
                      page_ms=6600, turn_ms=150)
    video = pv.Video([slow, fast], no_cards(), labels=["0.7.0", "0.8.0"], fps=FPS)
    (seg,) = video.segments
    stretch = [r.pages[0]["t"] - r.appeared for r in (slow, fast)]
    assert seg.lead == max(stretch) and seg.body == 11000
    assert seg.speeds == ((-seg.lead + 1000, -1500, 4.0),)
    frames = page_frames(video)
    first = frames[0]
    assert first.sides[0].present and not first.sides[1].present  # (the side whose start was shorter: not there yet)
    assert first.sides[1].start_ms is None
    turn = next(f for f in frames if f.sides[0].watch == "running")
    assert turn.sides[1].watch == "running" and turn.sides[0].watch_ms == turn.sides[1].watch_ms  # one moment
    before = [f for f in frames if f.ms < turn.ms]
    assert all(s.watch == "ready" and s.watch_ms == 0 and s.lettered == 0 for f in before for s in f.sides)
    assert any(f.speed == 4 for f in before) and all(f.speed == 1 for f in frames if f.ms >= turn.ms)
    for s, rec in enumerate((slow, fast)):  # the first bubble on the turn's clock, from the moment it was lettered
        marked = [f for f in frames if f.sides[s].first_ms is not None]
        assert marked and marked[0].sides[s].first_ms == rec.pages[0]["first_ms"]
        assert marked[0].sides[s].watch_ms >= rec.pages[0]["first_ms"] and marked[0].sides[s].lettered >= 1
        assert all(f.sides[s].lettered == 0 for f in frames if f.ms < marked[0].ms)
        ready = next(f for f in frames if f.sides[s].ready)
        assert ready.sides[s].start_ms == pytest.approx(rec.ready_t - rec.appeared)
    assert [s.watch_ms for s in frames[-1].sides] == [11000, 6600]
    facts = pv.start_facts(fast)
    assert facts["turn_after_ready_s"] == 0.15 and facts["first_bubble_after_turn_s"] == 2.6
    assert facts["first_bubble_after_sharp_s"] == round((2600 - 260) / 1000, 2)
    slow.close()
    fast.close()


def test_two_recordings_of_other_kinds_are_not_put_side_by_side(tmp_path):
    rec = pv.Recording(pv.made_up(tmp_path / "turns.zip", "t", [(2000, 3), (1800, 2)], size=SMALL, fps=FPS))
    start = from_start(tmp_path, "s", "start")
    at_ready = from_start(tmp_path, "r", "turn_at_ready")
    for pair in ([rec, start], [start, at_ready]):
        with pytest.raises(SystemExit):
            pv.Video(pair, no_cards())
    rec.close()
    start.close()
    at_ready.close()


def test_every_frame_from_the_start_carries_the_credit_and_says_its_speed(tmp_path):
    a = from_start(tmp_path, "a", "turn_at_ready", first_ms=6000, page_ms=8000)
    b = from_start(tmp_path, "b", "turn_at_ready", appear_ms=1200, first_ms=2000, page_ms=4000)
    video = pv.Video([a, b], pv.Options(title_ms=500, end_ms=500), "Title", ["one line"], fps=5)
    layout = video.layout
    w, h = layout.size
    reference = Image.new("RGB", layout.size)
    reference.paste(layout.caption(""), (0, h - layout.caption_h))
    box = layout.credit_box()
    credit = reference.crop(box).tobytes()
    for i in range(len(video)):
        facts = video.facts(i)
        image = video.image(facts)
        assert image.crop(box).tobytes() == credit, i
        if facts.kind == "page" and facts.speed > 1:  # the badge on the picture, in amber
            corner = image.crop((0, layout.header_h, layout.column // 3, layout.header_h + layout.header_h))
            assert any(abs(r - pv.AMBER[0]) < 12 and abs(g - pv.AMBER[1]) < 12 and abs(bl - pv.AMBER[2]) < 12
                       for _n, (r, g, bl) in corner.getcolors(1 << 16))
    a.close()
    b.close()


def test_a_picture_of_another_size_during_the_start_keeps_the_scale(tmp_path):
    writer = pv.RecordingWriter(tmp_path / "r.zip")
    small, full = Image.new("RGB", (100, 120), (200, 0, 0)), Image.new("RGB", (200, 240), (0, 0, 200))
    writer.add(1000.0, small)
    writer.add(1100.0, full)
    writer.finish({"turns": [], "displays": [], "results": [], "end_t": 3000.0, "mode": "start", "appeared_t": 1000.0,
                   "ready_t": 1500.0, "picture": [200, 240], "start_screen": [0, 0]})
    rec = pv.Recording(tmp_path / "r.zip")
    video = pv.Video([rec], no_cards(), fps=FPS)
    pw, ph = video.layout.pictures[0]
    early = video.scaled(0, rec.at(1000.0))
    assert early.size == (pw, ph)
    assert early.getpixel((2, 2)) == pytest.approx((200, 0, 0), abs=8)  # at the window's own scale, top left ...
    assert early.getpixel((pw - 2, ph - 2)) == pv.BG  # ... not stretched over the whole picture
    rec.close()


def test_the_windows_appearance_is_its_first_picture_not_of_one_colour():
    assert pv.one_colour(Image.new("RGB", (40, 30), (0, 0, 0))) and pv.one_colour(Image.new("RGB", (1, 1)))
    drawn = Image.new("RGB", (40, 30), (240, 240, 240))
    ImageDraw.Draw(drawn).rectangle((5, 5, 10, 10), fill=(0, 0, 0))
    assert not pv.one_colour(drawn) and pv.one_colour(Image.new("L", (5, 5), 7))


def test_the_records_kinds_on_the_command_line():
    plain = pv.parse(["record", "--out", "x.zip"])
    assert pv.record_mode(plain) == "turns" and not plain.from_start and not plain.turn_at_ready
    assert pv.record_mode(pv.parse(["record", "--out", "x.zip", "--from-start", "--turns", "0"])) == "start"
    assert pv.record_mode(pv.parse(["record", "--out", "x.zip", "--turn-at-ready"])) == "turn_at_ready"
    with pytest.raises(SystemExit):  # (one or the other)
        pv.parse(["record", "--out", "x.zip", "--from-start", "--turn-at-ready"])
    pv.check_turns("start", 0)
    for mode, turns in (("turns", 0), ("turn_at_ready", 0), ("start", 41), ("turns", 41)):
        with pytest.raises(SystemExit):
            pv.check_turns(mode, turns)
    pv.check_turns("turn_at_ready", 1)
    assert pv.script_of(0) == "e" and [s.op for s in sv.parse_script(pv.script_of(1))] == ["g", "n", "e"]
    assert pv.pages_needed(0, "spread") == 2 and pv.pages_needed(1, "single") == 2
    ren = pv.parse(["render", "a.zip", "--out", "v.mp4", "--start-speed", "3", "--real-before", "2"])
    opts = pv.options_of(ren)
    assert (opts.start_speed, opts.start_head_ms, opts.real_before_ms) == (3.0, 1000.0, 2000.0)
    with pytest.raises(SystemExit):
        pv.options_of(pv.parse(["render", "a.zip", "--out", "v.mp4", "--start-speed", "0.5"]))


def test_an_older_packages_input_functions_are_refused():
    older = SimpleNamespace(click_screen=lambda x, y: None, bring_to_front=lambda hwnd: True)

    def target(args, kwargs):
        return None

    assert pv.older_guarded(older, {}, target) == {"click_screen": ("never", target),
                                                   "bring_to_front": ("never", target)}
    assert pv.older_guarded(older, {"click_screen": ("never", target)}, target) == {
        "bring_to_front": ("never", target)}  # (one the table names stays as it says)
    assert pv.older_guarded(SimpleNamespace(), {}, target) == {}  # (today's package has neither)
    one = SimpleNamespace(press_briefly=lambda hwnd, key: True, post_key=lambda hwnd, key: None,
                          enlarge_window=lambda hwnd: None)  # (a 1.x package's: keys refused, the stand-in enlarged)
    assert pv.older_guarded(one, {}, target) == {"press_briefly": ("never", target), "post_key": ("never", target),
                                                 "enlarge_window": ("ours", target)}


def test_the_probe_notes_the_windows_ready_and_acts_once_after_it():
    probe = pv.Probe(standin_e2e.Notes(31, 1.0))
    calls = []
    probe.on_ready = calls.append
    probe.ready("app", before=True)
    first = probe.ready_t
    assert first is not None and calls == []  # (noted as the handler begins; the act after it ran)
    probe.ready("app", before=False)
    probe.ready("app", before=True)
    probe.ready("app", before=False)
    assert calls == ["app"] and probe.ready_t == first


def test_the_probe_notes_what_the_page_showed_and_each_result_taken():
    notes = standin_e2e.Notes(31, 1.0)
    probe = pv.Probe(notes)
    frame = coded(4)
    result = SimpleNamespace(original=frame, translated=[1, 2, 3])
    app = SimpleNamespace(canvas=SimpleNamespace(_image=frame), _fill=None, last_result=result, _live=coded(5))
    probe.displayed(app)
    probe.result(app, {"result": result})
    probe.result(app, {"result": SimpleNamespace(original=frame, translated=[])})  # held back: not on the page
    (display,) = probe.displays()
    assert (display["screen"], display["kind"], display["lettered"]) == ([4, 0], "translated", 3)
    assert [(r["screen"], r["bubbles"]) for r in probe.results] == [([4, 0], 3)]
    probe.displayed(SimpleNamespace(canvas=SimpleNamespace(_image=frame), _fill=SimpleNamespace()))
    assert probe.errors  # (a window of another shape: noted, never raised into it)


def test_record_pictures_a_package_that_shows_its_own_window_and_holds_its_hot_keys_off_the_system():
    """(`record` pictures TASlation's own window: a package before 2.0.0 - no see-through mode, or one as a setting of
    its window -; this checkout's window is hidden, see-through mode its one mode, and is refused before anything runs)"""
    import dataclasses
    import importlib.util

    from taslation.config import Settings

    @dataclasses.dataclass
    class Older:
        see_through: bool = False

    assert pv.own_window_shown(Settings, importlib.util.find_spec("taslation.ui.seethrough") is not None) is False
    assert pv.own_window_shown(Older, True) and pv.own_window_shown(Settings, False)
    keys = pv.HotKeys()  # (an older package's global hot keys: never registered with Windows, no press ever comes)
    assert keys.register("F11", 0x7A) and keys.register("F5", 0x74) and keys.registered == {"F11", "F5"}
    keys.unregister("F5")
    assert keys.take() == [] and keys.registered == {"F11"}
    keys.close()
    assert keys.registered == frozenset()
