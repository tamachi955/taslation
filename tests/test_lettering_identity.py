"""Lettering comes out pixel for pixel as it did before the size emphasis was added (`TextRegion.large`), for every
bubble without an emphasis: sample pages lettered by the pipeline (`Pipeline._render`: the erase, the page's caps,
the rooms of bubbles that overlap) and sample bubbles lettered by the typesetter (`letter_text`: stacked, slanted,
turned, formatted, in capitals, outlined, in shaped and other scripts), their pixels' digests against goldens made
from the code before the emphasis (`tests/data/lettering_identity.json`). The goldens hold on the fonts they were
made with: on a computer whose font files differ (another system, another version of a font) the cases are skipped.

``python tests/test_lettering_identity.py --write`` writes the goldens anew (only ever from code known to letter as
before)."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from taslation.regions import TextRegion  # noqa: E402

GOLDEN = Path(__file__).with_name("fixtures") / "lettering_identity.json"

ENGLISH = [
    "Why on earth did you weld the hatch shut, Pyo?! That really hurt, you know! I was stuck in there for hours.",
    "Huh?!",
    "What are you doing here at this hour?",
    "We split up at the river. You take the bridge, and I'll go round by the mill. Meet me at the old gate.",
    "Don't you *dare* touch that.",
    "First line.\nSecond paragraph here, a little longer.",
    "I wonder if she knew all along...",
    "GET BACK!!",
    "BOOM",
    "Fine.",
]


def _ellipse(w: int, h: int) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    inside = ((xx + 0.5 - w / 2) / (w / 2)) ** 2 + ((yy + 0.5 - h / 2) / (h / 2)) ** 2 <= 1.0
    return (inside * 255).astype(np.uint8)


def _region(x0: int, y0: int, mask: np.ndarray, text: str, kind: str = "bubble", tag: str = "",
            text_box: tuple[int, int, int, int] | None = None, glyph: float = 0.0) -> TextRegion:
    h, w = mask.shape
    tb = text_box or (x0 + w // 4, y0 + h // 4, x0 + 3 * w // 4, y0 + 3 * h // 4)
    r = TextRegion(x0, y0, x0 + w, y0 + h, mask, tb, kind=kind, source_text="x", translated_text=text,
                   status="translated", tag=tag, glyph=glyph)
    return r


def _page() -> tuple[np.ndarray, list[TextRegion]]:
    """A page of bubbles drawn on white, part of it under a tone (lines a drawing would give), and its regions."""
    w, h = 1000, 1400
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for x in range(560, 1000, 6):  # a tone on the right of the lower half
        d.line([(x, 900), (x - 300, 1400)], fill=(120, 120, 120), width=2)
    regions: list[TextRegion] = []

    def bubble(x0: int, y0: int, bw: int, bh: int, text: str, kind: str = "bubble", tag: str = "",
               fill: tuple[int, int, int] = (255, 255, 255), outline: tuple[int, int, int] = (0, 0, 0)) -> TextRegion:
        d.ellipse([x0 - 3, y0 - 3, x0 + bw + 2, y0 + bh + 2], fill=fill, outline=outline, width=3)
        r = _region(x0, y0, _ellipse(bw, bh), text, kind, tag)
        regions.append(r)
        return r

    bubble(40, 40, 260, 340, ENGLISH[0])
    bubble(340, 60, 120, 90, ENGLISH[1])
    bubble(500, 40, 90, 300, ENGLISH[2])
    # two bubbles joined at a neck: one region, one mask
    joined = np.zeros((260, 420), np.uint8)
    joined[:, :230] |= _ellipse(230, 260)
    joined[30:230, 200:420] |= _ellipse(220, 200)
    d.ellipse([637, 37, 870, 300], outline=(0, 0, 0), width=3)
    d.ellipse([837, 67, 1000, 270], outline=(0, 0, 0), width=3)
    img.paste((255, 255, 255), (640, 40), Image.fromarray(joined))
    regions.append(_region(640, 40, joined, ENGLISH[3]))
    # two bubbles whose boxes overlap: their rooms are shared out (`render.rooms`)
    bubble(60, 460, 240, 200, ENGLISH[4])
    bubble(250, 560, 220, 180, ENGLISH[5], tag="thought")
    bubble(560, 420, 300, 220, ENGLISH[6], kind="dark-bubble", fill=(0, 0, 0), outline=(255, 255, 255))
    bubble(80, 860, 260, 160, ENGLISH[7], tag="shout")
    # lettering on the tone, no bubble: text on the page
    mask = np.full((160, 300), 255, np.uint8)
    r = _region(620, 1060, mask, ENGLISH[8], kind="text", text_box=(660, 1100, 880, 1180))
    r.letter_box = (660, 1100, 880, 1180)
    regions.append(r)
    bubble(380, 1150, 110, 80, ENGLISH[9])
    for n, r in enumerate(regions):
        r.order = n
    return np.asarray(img).copy(), regions


def _pipeline(state_dir: Path) -> Any:
    from taslation.config import Settings
    from taslation.pipeline import Pipeline

    s = Settings(state_dir=state_dir)
    s.art_erase = "off"
    s.target_language = "English"
    s.validate()
    return Pipeline(s, ocr=None, translator=None, cache=None)


def _digest(image: Image.Image | np.ndarray) -> str:
    arr = np.asarray(image.convert("RGB") if isinstance(image, Image.Image) else image, dtype=np.uint8)
    return hashlib.sha256(arr.tobytes() + repr(arr.shape).encode()).hexdigest()


def _bubble_cases() -> list[tuple[str, dict[str, Any]]]:
    """The typesetter's cases: (name, the arguments of `letter_text` but the image and the font)."""
    jp = "こんにちは、元気ですか？今日はいい天気ですね。"
    return [
        ("plain", {"text": ENGLISH[0], "mask": (220, 300)}),
        ("short", {"text": ENGLISH[1], "mask": (110, 80)}),
        ("narrow", {"text": ENGLISH[2], "mask": (70, 260)}),
        ("stressed", {"text": ENGLISH[4], "mask": (200, 160)}),
        ("paragraphs", {"text": ENGLISH[5], "mask": (220, 200)}),
        ("capitals", {"text": ENGLISH[3], "mask": (240, 260), "uppercase": True}),
        ("outlined", {"text": ENGLISH[6], "mask": (240, 200), "outline": True}),
        ("coloured", {"text": ENGLISH[6], "mask": (240, 200), "color": (200, 20, 20), "outline": True,
                      "outline_color": (255, 255, 0)}),
        ("formatted", {"text": ENGLISH[3], "mask": (240, 260), "fmt": ("left", "top", 16, 1.3, None)}),
        ("formatted-fixed-over", {"text": ENGLISH[0], "mask": (120, 100), "fmt": ("right", "bottom", 20, 0.0, None)}),
        ("slanted", {"text": ENGLISH[3], "mask": (240, 260), "angle": 12.0}),
        ("turned-down", {"text": ENGLISH[2], "mask": (120, 300), "direction": "down"}),
        ("stacked-jp", {"text": jp, "mask": (200, 260), "direction": "stacked", "language": "Japanese"}),
        ("stacked-latin", {"text": "HELLO", "mask": (60, 300), "direction": "stacked"}),
        ("horizontal-jp", {"text": jp, "mask": (220, 220), "language": "Japanese"}),
        ("chinese", {"text": "你今天怎么这么晚才回来？我们都等了你很久了。", "mask": (220, 220),
                     "language": "Chinese (Simplified)"}),
        ("korean", {"text": "오늘 왜 이렇게 늦게 왔어? 우리 모두 오래 기다렸어.", "mask": (220, 220), "language": "Korean"}),
        ("thai", {"text": "วันนี้ทำไมกลับบ้านช้าจัง พวกเรารอเธอนานมากเลยนะ", "mask": (220, 220), "language": "Thai"}),
        ("hindi", {"text": "तुम आज इतनी देर से क्यों आए? हम सब बहुत देर से इंतज़ार कर रहे थे।", "mask": (220, 240),
                   "language": "Hindi"}),
        ("russian", {"text": "Почему ты сегодня так поздно вернулся? Мы все тебя долго ждали.", "mask": (220, 240),
                     "language": "Russian"}),
        ("text-on-page", {"text": ENGLISH[8], "mask": (300, 160), "kind": "text", "outline": True}),
        ("dark", {"text": ENGLISH[6], "mask": (240, 200), "kind": "dark-bubble", "background": (0, 0, 0)}),
    ]


def _letter_case(spec: dict[str, Any], draw: bool) -> tuple[str, int, list[str], str, str]:
    """One typesetter case lettered (or only measured, without *draw*): its digest, size, flags, the layout that
    won and the font file it used."""
    from taslation.render import find_font, letter_text
    from taslation.render.typeset import TextFormat

    w, h = spec["mask"]
    mask = _ellipse(w, h) if spec.get("kind", "bubble") != "text" else np.full((h, w), 255, np.uint8)
    x0, y0 = 30, 40
    region = _region(x0, y0, mask, spec["text"], spec.get("kind", "bubble"))
    region.angle = spec.get("angle", 0.0)
    language = spec.get("language", "English")
    font = find_font("", None, spec["text"], language).path
    background = spec.get("background", (255, 255, 255))
    image = Image.new("RGB", (w + 60, h + 80), background) if draw else None
    fmt = TextFormat(*spec["fmt"]) if "fmt" in spec else None
    done = letter_text(image, region, spec["text"], font, 9, 64, 1.12, spec.get("uppercase", False), background,
                       False, language, spec.get("outline"), fmt, direction=spec.get("direction", ""),
                       color=spec.get("color"), outline_color=spec.get("outline_color"))
    return (_digest(image) if image is not None else ""), int(done.size), list(done.flags), done.won, font or ""


def _page_case(state_dir: Path) -> tuple[str, list[int], list[list[str]], list[str]]:
    """The sample page lettered by the pipeline (its settings' state folder *state_dir*): its digest, each region's
    size and flags, the fonts used."""
    pipe = _pipeline(state_dir)
    out, regions = _page()
    pipe._render(out, regions)
    fonts = sorted({pipe.lettering_for(r.translated_text, r.tag).path or "" for r in regions}
                   | {getattr(pipe.lettering_for(r.translated_text, r.tag), name) or ""
                      for r in regions for name in ("italic_path", "bold_path", "bold_italic_path")})
    return _digest(out), [int(r.font_size) for r in regions], [list(r.letter_flags) for r in regions], fonts


def _file_digest(path: str) -> str:
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if path and p.is_file() else ""


def _fonts_of(paths: list[str]) -> dict[str, str]:
    """The font files used, as their file names (never a folder of this computer's) and their contents' digests."""
    return {Path(f).name: _file_digest(f) for f in sorted(set(paths)) if f}


def build(state_dir: Path) -> dict[str, Any]:
    """Every case lettered as the code in place letters it."""
    cases: dict[str, Any] = {}
    digest, sizes, flags, used = _page_case(state_dir)
    cases["page"] = {"digest": digest, "sizes": sizes, "flags": flags, "fonts": _fonts_of(used)}
    for name, spec in _bubble_cases():
        for draw in (True, False):
            d, size, fl, won, font = _letter_case(spec, draw)
            cases[name + ("" if draw else ":measured")] = {"digest": d, "size": size, "flags": fl, "won": won,
                                                           "fonts": _fonts_of([font])}
    return {"cases": cases}


def _golden() -> dict[str, Any]:
    if not GOLDEN.is_file():
        pytest.skip("no goldens")
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def _same_fonts(want: dict[str, str], used: list[str]) -> None:
    """Skips unless the fonts used now are the very files the golden was made with."""
    if _fonts_of(used) != want:
        pytest.skip("this computer's fonts are not those the goldens were made with")


def test_the_sample_page_letters_as_before(tmp_path):
    want = _golden()["cases"]["page"]
    digest, sizes, flags, used = _page_case(tmp_path)
    _same_fonts(want["fonts"], used)
    assert sizes == want["sizes"]
    assert flags == want["flags"]
    assert digest == want["digest"]


@pytest.mark.parametrize("name", [name for name, _spec in _bubble_cases()])
def test_a_bubble_letters_as_before(name):
    golden = _golden()
    spec = dict(_bubble_cases())[name]
    for draw in (True, False):
        want = golden["cases"][name + ("" if draw else ":measured")]
        digest, size, flags, won, font = _letter_case(spec, draw)
        _same_fonts(want["fonts"], [font])
        assert (size, flags, won) == (want["size"], want["flags"], want["won"])
        assert digest == want["digest"]


if __name__ == "__main__":
    if "--write" not in sys.argv[1:]:
        raise SystemExit("usage: python tests/test_lettering_identity.py --write")
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        golden = build(Path(folder))
    GOLDEN.write_text(json.dumps(golden, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"written: {GOLDEN}")
