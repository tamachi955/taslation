"""Font lookup for the rendered translation, by script.

The script a translation is written in is detected from the text itself
(Latin/Greek/Cyrillic, Japanese, Chinese, Korean, Thai, Arabic, Hebrew,
Devanagari, Bengali). For each script we prefer a font in ``<models>/fonts``
(``setup_models.py --fonts`` downloads the OFL-licensed Noto Sans family and
``--font`` the Comic Neue lettering font), then a system font that covers the
script, then Pillow's built-in font.

A series sheet may suggest a lettering font by family name (``find_font``'s
*suggested*). The name is looked up among the installed fonts on each reader's
computer, by the names written in the font files themselves (``resolve_font``),
and the font is used where it has glyphs for the text (``covers``); where it is
not installed, or lacks the glyphs, the automatic choice above applies.
"""

from __future__ import annotations

import functools
import os
import re
import struct
import sys
import unicodedata
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import ImageFont

FontT = ImageFont.FreeTypeFont | ImageFont.ImageFont

# Unicode ranges per script (inclusive). Han characters are resolved with the
# language hint and the presence of kana / hangul.
_RANGES: list[tuple[str, int, int]] = [
    ("kana", 0x3040, 0x30FF),
    ("han", 0x3400, 0x4DBF),
    ("han", 0x4E00, 0x9FFF),
    ("han", 0xF900, 0xFAFF),
    ("hangul", 0x1100, 0x11FF),
    ("hangul", 0x3130, 0x318F),
    ("hangul", 0xAC00, 0xD7AF),
    ("thai", 0x0E00, 0x0E7F),
    ("arabic", 0x0600, 0x06FF),
    ("arabic", 0x0750, 0x077F),
    ("arabic", 0x08A0, 0x08FF),
    ("arabic", 0xFB50, 0xFDFF),
    ("arabic", 0xFE70, 0xFEFF),
    ("hebrew", 0x0590, 0x05FF),
    ("devanagari", 0x0900, 0x097F),
    ("bengali", 0x0980, 0x09FF),
    ("cyrillic", 0x0400, 0x04FF),
    ("greek", 0x0370, 0x03FF),
]

RTL_SCRIPTS = frozenset({"arabic", "hebrew"})
NO_SPACE_SCRIPTS = frozenset({"jp", "sc", "tc", "thai"})

# Files that setup_models.py --fonts puts into <models>/fonts (google/fonts, OFL-1.1).
NOTO_FONTS: dict[str, str] = {
    "lgc": "NotoSans[wdth,wght].ttf",
    "sc": "NotoSansSC[wght].ttf",
    "tc": "NotoSansTC[wght].ttf",
    "jp": "NotoSansJP[wght].ttf",
    "kr": "NotoSansKR[wght].ttf",
    "thai": "NotoSansThai[wdth,wght].ttf",
    "arabic": "NotoSansArabic[wdth,wght].ttf",
    "hebrew": "NotoSansHebrew[wdth,wght].ttf",
    "devanagari": "NotoSansDevanagari[wdth,wght].ttf",
    "bengali": "NotoSansBengali[wdth,wght].ttf",
}
COMIC_FONT = "ComicNeue-Bold.ttf"

_WINDOWS: dict[str, list[str]] = {
    "lgc": ["comicbd.ttf", "arialbd.ttf", "segoeuib.ttf", "verdanab.ttf", "arial.ttf"],
    "symbols": ["seguisym.ttf", "segoeuib.ttf", "msgothic.ttc"],
    "latin_wide": ["segoeuib.ttf", "arialbd.ttf", "arial.ttf"],
    "sc": ["msyhbd.ttc", "msyh.ttc", "simhei.ttf", "simsun.ttc"],
    "tc": ["msjhbd.ttc", "msjh.ttc", "mingliu.ttc"],
    "jp": ["YuGothB.ttc", "meiryob.ttc", "msgothic.ttc"],
    "kr": ["malgunbd.ttf", "malgun.ttf", "gulim.ttc"],
    "thai": ["LeelUIb.ttf", "leelawui.ttf", "tahomabd.ttf"],
    "arabic": ["segoeuib.ttf", "arialbd.ttf", "tahomabd.ttf"],
    "hebrew": ["segoeuib.ttf", "arialbd.ttf", "tahomabd.ttf"],
    "devanagari": ["NirmalaB.ttf", "Nirmala.ttf", "Nirmala.ttc", "mangal.ttf"],
    "bengali": ["NirmalaB.ttf", "Nirmala.ttf", "Nirmala.ttc", "vrinda.ttf"],
}
_MAC: dict[str, list[str]] = {
    "lgc": ["/Library/Fonts/Arial Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc"],
    "symbols": ["/System/Library/Fonts/Apple Symbols.ttf", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"],
    "sc": ["/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Medium.ttc"],
    "tc": ["/System/Library/Fonts/PingFang.ttc"],
    "jp": ["/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc"],
    "kr": ["/System/Library/Fonts/AppleSDGothicNeo.ttc"],
    "thai": ["/System/Library/Fonts/Thonburi.ttc", "/System/Library/Fonts/Supplemental/Ayuthaya.ttf"],
    "arabic": ["/System/Library/Fonts/GeezaPro.ttc", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"],
    "hebrew": ["/System/Library/Fonts/Supplemental/Arial Hebrew.ttc", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"],
    "devanagari": ["/System/Library/Fonts/Supplemental/DevanagariMT.ttc", "/System/Library/Fonts/Supplemental/Kohinoor.ttc"],
    "bengali": ["/System/Library/Fonts/Supplemental/Bangla MN.ttc", "/System/Library/Fonts/Supplemental/Kohinoor Bangla.ttc"],
}
_LINUX: dict[str, list[str]] = {
    "lgc": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"],
    "symbols": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/noto/NotoSansSymbols2-Regular.ttf"],
    "sc": ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"],
    "tc": ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"],
    "jp": ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"],
    "kr": ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"],
    "thai": ["/usr/share/fonts/truetype/noto/NotoSansThai-Bold.ttf", "/usr/share/fonts/truetype/tlwg/Garuda-Bold.ttf"],
    "arabic": ["/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "hebrew": ["/usr/share/fonts/truetype/noto/NotoSansHebrew-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "devanagari": ["/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf", "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf"],
    "bengali": ["/usr/share/fonts/truetype/noto/NotoSansBengali-Bold.ttf", "/usr/share/fonts/truetype/lohit-bengali/Lohit-Bengali.ttf"],
}

TRADITIONAL_HINTS = ("traditional", "繁體", "繁体", "taiwan", "hong kong", "zh-tw", "zh-hk", "zh-hant")


def script_of(text: str, language: str = "") -> str:
    """Dominant script of *text*: lgc (Latin/Greek/Cyrillic), jp, sc, tc, kr, thai, arabic, hebrew, devanagari, bengali."""
    counts: dict[str, int] = {}
    for ch in text:
        cp = ord(ch)
        if cp < 0x0370:
            continue  # ASCII / Latin-1 / Latin Extended: all fonts cover these
        for name, lo, hi in _RANGES:
            if lo <= cp <= hi:
                counts[name] = counts.get(name, 0) + 1
                break
    if not counts:
        return "lgc"
    if counts.get("kana"):
        return "jp"
    if counts.get("hangul"):
        return "kr"
    if counts.get("han"):
        return "tc" if any(h in language.lower() for h in TRADITIONAL_HINTS) else "sc"
    best = max((n for n in counts if n not in ("cyrillic", "greek")), key=lambda n: counts[n], default=None)
    return best or "lgc"


_SIGNS = "symbols"  # the system fonts' list for signs no script's font has


def _needs_wide_latin(text: str) -> bool:
    """True when the text has characters outside Latin-1 / Latin Extended-A: the stand-in for a font's own cmap
    when that cannot be read (`can_draw`)."""
    return any(ord(ch) > 0x017F for ch in text)


@dataclass(frozen=True)
class FontSpec:
    path: str | None
    bold_variation: bool = False  # variable font: select the bold instance

    def __bool__(self) -> bool:
        return self.path is not None


def _system_candidates(script: str) -> list[Path]:
    if sys.platform == "win32":
        fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        names = _WINDOWS.get(script, _WINDOWS["lgc"])
        return [fonts / n for n in names]
    if sys.platform == "darwin":
        return [Path(p) for p in _MAC.get(script, _MAC["lgc"])]
    return [Path(p) for p in _LINUX.get(script, _LINUX["lgc"])]


def find_font(preferred: str = "", fonts_dir: Path | None = None, text: str = "", language: str = "",
              suggested: str | Sequence[str] = "") -> FontSpec:
    """Pick a font file for *text* (or for Latin text when no text is given).

    *suggested* is the family name of the font the series sheet asks for (or several, the first that works wins):
    it is used when it is installed on this computer and has glyphs for *text*; otherwise *preferred* (the
    reader's own font file), then the automatic choice per script. A script's font has no signs that lie outside
    the scripts (a heart, a star, an arrow a reply kept from the page): a text it lacks glyphs for goes to the first
    system font of `_SIGNS` that has them all.
    """
    for name in ([suggested] if isinstance(suggested, str) else suggested):
        if not name:
            continue
        spec = resolve_font(name, fonts_dir)
        if spec and (not text or can_draw(spec.path, text)):
            return spec
    if preferred:
        p = Path(preferred).expanduser()
        if p.is_file():
            return FontSpec(str(p), "[" in p.name)
    spec = _by_script(fonts_dir, text, language)
    if spec and text and not can_draw(spec.path, text) and _coverage(spec.path) is not None:
        for cand in _system_candidates(_SIGNS):
            if cand.is_file() and can_draw(str(cand), text):
                return FontSpec(str(cand))
    return spec


def _draws_latin(path: str, text: str) -> bool:
    """Whether the Latin lettering font at *path* can set *text*: its cmap decides (`can_draw`), and only for a font
    whose cmap cannot be read does the old test stand in (nothing past Latin Extended-A)."""
    if _coverage(path) is None:
        return not _needs_wide_latin(text)
    return can_draw(path, text)


def _by_script(fonts_dir: Path | None, text: str, language: str) -> FontSpec:
    """The automatic choice for *text*: the fonts folder's for its script, else the system's. Latin, Greek and
    Cyrillic text is set in the comic lettering font wherever that font can draw all of it (`can_draw`: by its cmap,
    a letter it lacks composed from the base letter and a mark it has), else in Noto Sans."""
    script = script_of(text, language) if text else "lgc"
    fonts_dir = Path(fonts_dir) if fonts_dir else None
    if fonts_dir and fonts_dir.is_dir():
        if script == "lgc":
            comic = fonts_dir / COMIC_FONT
            if comic.is_file() and (not text or _draws_latin(str(comic), text)):
                return FontSpec(str(comic))
        noto = fonts_dir / NOTO_FONTS[script]
        if noto.is_file():
            return FontSpec(str(noto), True)
        if script == "lgc":  # any other font the user dropped in
            files = sorted(f for f in fonts_dir.glob("*.[to]tf") if "Noto" not in f.name)
            bold = [f for f in files if "bold" in f.name.lower()]
            if bold or files:
                return FontSpec(str((bold or files)[0]))
    if script == "lgc" and text:  # the system's: the first lettering font that can draw it, then the wide ones
        wide = _system_candidates("latin_wide") if sys.platform == "win32" else []
        for cand in [*_system_candidates("lgc"), *wide]:
            if cand.is_file() and _draws_latin(str(cand), text):
                return FontSpec(str(cand))
    system_script = "latin_wide" if (script == "lgc" and _needs_wide_latin(text) and sys.platform == "win32") else script
    for cand in _system_candidates(system_script):
        if cand.is_file():
            return FontSpec(str(cand))
    return FontSpec(None)


@functools.lru_cache(maxsize=512)
def load_font(path: str | None, size: int, bold_variation: bool = False, weight: int = 700) -> FontT:
    """The font at *path* (a face of a collection as "path#index") at *size*; with *bold_variation*, a variable
    font is set to *weight* (a static font is loaded as it is)."""
    size = max(1, int(size))
    if path:
        file, index = split_face(path)
        try:
            font = ImageFont.truetype(file, size, index=index)
            if bold_variation:
                try:
                    axes = font.get_variation_axes()
                    values = [weight if a.get("name") in (b"Weight", "Weight") else int(a.get("default", 100)) for a in axes]
                    font.set_variation_by_axes(values)
                except Exception:
                    pass
            return font
        except OSError:
            pass
    try:
        return ImageFont.load_default(size)  # Pillow >= 10.1 ships a scalable default
    except TypeError:  # pragma: no cover - very old Pillow
        return ImageFont.load_default()


# --- fonts by name -------------------------------------------------------------------------------
# A suggested font is a family name ("Comic Neue", "Wild Words"), never a path: paths differ between computers.
# The installed fonts are indexed by the names in their own 'name' tables (family, subfamily, full name), the
# index is kept per directory until the directory changes, and a face of a collection (.ttc) is addressed as
# "<path>#<index>" so that the one path string the typesetter carries around still names it.

FONT_SUFFIXES = (".ttf", ".otf", ".ttc")
MAX_FONT_FILES = 4000
_BOLD_WORDS = ("bold", "black", "heavy", "extrabold", "semibold", "demibold")
_SLANT_WORDS = ("italic", "oblique")


@dataclass(frozen=True)
class FontFace:
    path: str  # the file, with "#<index>" for a face of a collection other than the first
    family: str
    subfamily: str
    full: str
    variable: bool = False  # a variable font: its bold instance is selected when it is loaded

    @property
    def file(self) -> str:
        return split_face(self.path)[0]


def split_face(path: str) -> tuple[str, int]:
    """("file", face index) from a font path that may end in "#<index>" (a face of a .ttc collection)."""
    base, sep, idx = path.rpartition("#")
    if sep and base and idx.isdigit():
        return base, int(idx)
    return path, 0


def _system_font_dirs() -> list[Path]:
    if sys.platform == "win32":
        dirs = [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"]
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")  # fonts installed for one user
        return dirs
    if sys.platform == "darwin":
        return [Path("/System/Library/Fonts"), Path("/System/Library/Fonts/Supplemental"), Path("/Library/Fonts"),
                Path.home() / "Library" / "Fonts"]
    return [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts",
            Path.home() / ".local" / "share" / "fonts"]


def _read_at(f, offset: int, length: int) -> bytes:
    f.seek(offset)
    return f.read(length)


def _face_offsets(f) -> list[int]:
    head = _read_at(f, 0, 12)
    if len(head) < 12:
        return []
    if head[:4] == b"ttcf":
        n = struct.unpack_from(">I", head, 8)[0]
        if n > 64:
            return []
        return list(struct.unpack(f">{n}I", _read_at(f, 12, 4 * n)))
    if head[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
        return []
    return [0]


def _tables(f, offset: int) -> dict[bytes, tuple[int, int]]:
    """tag -> (offset, length) of the font whose table directory starts at *offset*."""
    head = _read_at(f, offset, 12)
    if len(head) < 12:
        return {}
    num = struct.unpack_from(">H", head, 4)[0]
    if num > 64:
        return {}
    raw = _read_at(f, offset + 12, 16 * num)
    tables: dict[bytes, tuple[int, int]] = {}
    for i in range(len(raw) // 16):
        tag, _check, off, length = struct.unpack_from(">4sIII", raw, 16 * i)
        tables[tag] = (off, length)
    return tables


def _names(raw: bytes) -> dict[int, str]:
    """nameID -> string from a 'name' table (English preferred, Unicode or Mac Roman records only)."""
    if len(raw) < 6:
        return {}
    _fmt, count, str_off = struct.unpack_from(">HHH", raw, 0)
    out: dict[int, str] = {}
    english: dict[int, bool] = {}
    for i in range(min(count, 512)):
        pos = 6 + 12 * i
        if pos + 12 > len(raw):
            break
        pid, eid, lid, nid, ln, so = struct.unpack_from(">HHHHHH", raw, pos)
        if nid not in (1, 2, 4, 16, 17):
            continue
        chunk = raw[str_off + so:str_off + so + ln]
        if len(chunk) < ln:
            continue
        if pid in (0, 3):
            try:
                text = chunk.decode("utf-16-be")
            except UnicodeDecodeError:
                continue
            is_english = pid == 0 or lid == 0x409
        elif pid == 1 and eid == 0:
            text = chunk.decode("mac_roman", "replace")
            is_english = lid == 0
        else:
            continue
        text = text.strip("\x00").strip()
        if text and (nid not in out or (is_english and not english[nid])):
            out[nid], english[nid] = text, is_english
    return out


def _faces_of_file(path: Path) -> list[FontFace]:
    faces: list[FontFace] = []
    try:
        with open(path, "rb") as f:
            for index, offset in enumerate(_face_offsets(f)):
                tables = _tables(f, offset)
                if b"name" not in tables:
                    continue
                off, length = tables[b"name"]
                names = _names(_read_at(f, off, min(length, 1 << 20)))
                family = names.get(16) or names.get(1) or ""
                if not family:
                    continue
                sub = names.get(17) or names.get(2) or ""
                faces.append(FontFace(str(path) + (f"#{index}" if index else ""), family, sub,
                                      names.get(4) or f"{family} {sub}".strip(), b"fvar" in tables))
    except (OSError, struct.error, ValueError):
        return []
    return faces


@functools.lru_cache(maxsize=16)
def _faces_in(directory: str, _stamp: int) -> tuple[FontFace, ...]:
    root = Path(directory)
    files = sorted(p for p in root.rglob("*") if p.suffix.lower() in FONT_SUFFIXES and p.is_file())[:MAX_FONT_FILES]
    faces: list[FontFace] = []
    for p in files:
        faces.extend(_faces_of_file(p))
    return tuple(faces)


def font_faces(fonts_dir: Path | None = None) -> list[FontFace]:
    """Every installed font face, the ones in *fonts_dir* first, then the system's."""
    out: list[FontFace] = []
    dirs = ([Path(fonts_dir)] if fonts_dir else []) + _system_font_dirs()
    for d in dirs:
        try:
            stamp = d.stat().st_mtime_ns if d.is_dir() else -1
        except OSError:
            continue
        if stamp >= 0:
            out.extend(_faces_in(str(d), stamp))
    return out


def font_families(fonts_dir: Path | None = None) -> list[str]:
    """The family names of every installed font face (those in *fonts_dir* and the system's), each once, in
    alphabetical order: what a reader may choose a region's font from. Names the system hides (a leading dot)
    are left out."""
    seen: dict[str, str] = {}
    for face in font_faces(fonts_dir):
        name = face.family.strip()
        if name and not name.startswith(".") and _key(name) not in seen:
            seen[_key(name)] = name
    return sorted(seen.values(), key=str.casefold)


def _key(name: str) -> str:
    return re.sub(r"[\s\-_,.]+", "", name).casefold()


def _weight_rank(face: FontFace) -> int:
    """0 for a bold face (or a variable font, whose bold instance is selected), 1 for a regular one, 2 for a
    slanted or light one: the lettering is set bold by habit."""
    low = f"{face.subfamily} {Path(face.file).stem}".lower()
    if any(w in low for w in _SLANT_WORDS):
        return 2
    if face.variable or any(w in low for w in _BOLD_WORDS):
        return 0
    return 1 if face.subfamily.lower() in ("", "regular", "normal", "book", "medium") or "regular" in low else 2


def resolve_font(name: str, fonts_dir: Path | None = None) -> FontSpec:
    """The installed font for a family name (a full name such as "Comic Neue Bold" also works; so does the stem
    of a file in *fonts_dir*), the bold face preferred; an empty FontSpec when no such font is installed."""
    want = _key(name)
    if not want:
        return FontSpec(None)
    given = Path(name).expanduser()
    if given.suffix.lower() in FONT_SUFFIXES and given.is_file():  # a file path works too, on this computer
        return FontSpec(str(given), "[" in given.name)
    best: tuple[int, int, int] | None = None
    best_face: FontFace | None = None
    for order, face in enumerate(font_faces(fonts_dir)):
        fam, full, fstem = _key(face.family), _key(face.full), _key(Path(face.file).stem)
        if want == fam:
            rank = 1  # the family: its bold face below
        elif want == full and full != fam:
            rank = 0  # a face named in full ("Comic Neue Bold")
        elif fstem.startswith(want) and len(fstem) - len(want) <= 12:  # a file called "ComicNeue-Bold.ttf"
            rank = 2
        else:
            continue
        score = (rank, _weight_rank(face), order)
        if best is None or score < best:
            best, best_face = score, face
    if best_face is None:
        return FontSpec(None)
    return FontSpec(best_face.path, best_face.variable)


def face_of(path: str) -> FontFace | None:
    """The names of the font at *path* (with "#<index>" for a face of a collection), or None."""
    file, index = split_face(path)
    faces = _faces_of_file(Path(file))
    return faces[index] if index < len(faces) else None


def _cmap_ranges_format4(raw: bytes, off: int) -> list[tuple[int, int]]:
    seg_x2 = struct.unpack_from(">H", raw, off + 6)[0]
    n = seg_x2 // 2
    ends = struct.unpack_from(f">{n}H", raw, off + 14)
    starts = struct.unpack_from(f">{n}H", raw, off + 16 + seg_x2)
    deltas = struct.unpack_from(f">{n}h", raw, off + 16 + 2 * seg_x2)
    ro_pos = off + 16 + 3 * seg_x2
    range_offsets = struct.unpack_from(f">{n}H", raw, ro_pos)
    out: list[tuple[int, int]] = []
    for i in range(n):
        start, end = starts[i], ends[i]
        if start > end or start == 0xFFFF:
            continue
        if range_offsets[i] == 0:
            if (start + deltas[i]) & 0xFFFF or end > start:  # glyph 0 only for a one-code segment mapping to .notdef
                out.append((start, end))
            continue
        run_start = None
        for c in range(start, min(end, 0xFFFE) + 1):
            gpos = ro_pos + 2 * i + range_offsets[i] + 2 * (c - start)
            glyph = struct.unpack_from(">H", raw, gpos)[0] if gpos + 2 <= len(raw) else 0
            if glyph:
                if run_start is None:
                    run_start = c
            elif run_start is not None:
                out.append((run_start, c - 1))
                run_start = None
        if run_start is not None:
            out.append((run_start, min(end, 0xFFFE)))
    return out


def _cmap_ranges_format12(raw: bytes, off: int) -> list[tuple[int, int]]:
    n = struct.unpack_from(">I", raw, off + 12)[0]
    out: list[tuple[int, int]] = []
    for i in range(min(n, 100000)):
        start, end, _glyph = struct.unpack_from(">III", raw, off + 16 + 12 * i)
        if start <= end:
            out.append((start, end))
    return out


@functools.lru_cache(maxsize=64)
def _coverage(path: str) -> tuple[tuple[int, ...], tuple[int, ...]] | None:
    """(range starts, range ends) of the code points the font at *path* has glyphs for; None when unreadable."""
    file, index = split_face(path)
    try:
        with open(file, "rb") as f:
            offsets = _face_offsets(f)
            if index >= len(offsets):
                return None
            tables = _tables(f, offsets[index])
            if b"cmap" not in tables:
                return None
            off, length = tables[b"cmap"]
            raw = _read_at(f, off, min(length, 1 << 24))
        _version, n = struct.unpack_from(">HH", raw, 0)
        best: tuple[int, int, int] | None = None  # (score, subtable offset, format)
        for i in range(min(n, 32)):
            pid, eid, sub = struct.unpack_from(">HHI", raw, 4 + 8 * i)
            if sub + 4 > len(raw):
                continue
            fmt = struct.unpack_from(">H", raw, sub)[0]
            if fmt not in (4, 12):
                continue
            score = (3 if fmt == 12 else 1) + (1 if pid in (0, 3) else 0)
            if best is None or score > best[0]:
                best = (score, sub, fmt)
        if best is None:
            return None
        ranges = _cmap_ranges_format12(raw, best[1]) if best[2] == 12 else _cmap_ranges_format4(raw, best[1])
    except (OSError, struct.error, ValueError):
        return None
    ranges.sort()
    merged: list[list[int]] = []
    for lo, hi in ranges:
        if merged and lo <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return tuple(m[0] for m in merged), tuple(m[1] for m in merged)


def _has(cov: tuple[tuple[int, ...], tuple[int, ...]], ch: str) -> bool:
    """Whether the coverage *cov* has a glyph for *ch*; a space or a control character needs none."""
    cp = ord(ch)
    if ch.isspace() or cp < 0x20 or 0xFE00 <= cp <= 0xFE0F or cp == 0x200D or cp == 0x00AD:
        return True
    i = bisect_right(cov[0], cp) - 1
    return i >= 0 and cp <= cov[1][i]


def covers(path: str | None, text: str) -> bool:
    """True when the font at *path* has a glyph for every character of *text* that is not a space or a control
    character (an unreadable font counts as covering nothing)."""
    cov = _coverage(path) if path else None
    return cov is not None and all(_has(cov, ch) for ch in text)


# --- letters a font lacks, drawn from the ones it has ------------------------------------------------
# Pillow lays text out without a shaping engine here, so a letter the font lacks is not composed for us the way
# HarfBuzz composes it (a precomposed letter missing from the cmap is drawn as its canonical decomposition when the
# font has those glyphs). `_cluster_form` does that much: a lowercase letter is drawn as its base letter and the
# combining marks, whose glyphs sit at the height of a small letter with no advance of their own (Comic Neue's
# U+0304 over o and u, measured on renders); i and j drop their dot under a mark above (the soft-dotted rule,
# U+0131 and U+0237). Over a capital the same marks run into the letter (the case forms of the marks are reached
# only through the font's shaping tables), so a capital is drawn precomposed or, for the macron alone, without the
# mark: the long vowels of Hepburn names, which English editions of manga mostly print without macrons. The text
# kept is never changed; only what is drawn.
_DOTLESS = {"i": "ı", "j": "ȷ"}
_ABOVE = 230  # the canonical combining class of the marks set above a letter
_FOLDED_ON_CAPITALS = frozenset("̄")  # COMBINING MACRON


def _clusters(text: str) -> list[str]:
    """*text* in clusters: a character and the combining marks that follow it."""
    out: list[str] = []
    for ch in text:
        if out and unicodedata.combining(ch):
            out[-1] += ch
        else:
            out.append(ch)
    return out


def _cluster_form(cov: tuple[tuple[int, ...], tuple[int, ...]], cluster: str) -> str | None:
    """How a font of coverage *cov* draws one *cluster* (a character and its combining marks): as it is, as its
    precomposed letter, as the base letter and its marks (a lowercase base only), or a capital without its macron;
    None when it cannot."""
    base = cluster[0]
    capital = base.isupper() and len(cluster) > 1
    if not capital and all(_has(cov, ch) for ch in cluster):
        return cluster
    composed = unicodedata.normalize("NFC", cluster)
    if len(composed) == 1 and _has(cov, composed):
        return composed
    parts = unicodedata.normalize("NFD", composed)
    base, marks = parts[0], parts[1:]
    if not marks or not _has(cov, base):
        return None
    if not base.isupper():
        if not all(_has(cov, m) for m in marks):
            return None
        dotless = _DOTLESS.get(base)
        if dotless and _has(cov, dotless) and any(unicodedata.combining(m) == _ABOVE for m in marks):
            base = dotless
        return base + marks
    rest = "".join(m for m in marks if m not in _FOLDED_ON_CAPITALS)
    if not rest:
        return base
    again = unicodedata.normalize("NFC", base + rest)
    return again if len(again) == 1 and _has(cov, again) else None


def can_draw(path: str | None, text: str) -> bool:
    """True when the font at *path* can draw every character of *text*: it has the glyph (`covers`), or the glyphs
    `_cluster_form` draws the letter from (a lowercase letter composed from its base and a mark, a capital without a
    macron). An unreadable font draws nothing."""
    cov = _coverage(path) if path else None
    if cov is None:
        return False
    if all(_has(cov, ch) for ch in text) and not _capital_marks(text):
        return True
    return all(_cluster_form(cov, c) is not None for c in _clusters(text))


def _capital_marks(text: str) -> bool:
    """Whether a combining mark follows a capital somewhere in *text* (drawn as it is, it would run into it)."""
    return any(unicodedata.combining(ch) and i and text[i - 1].isupper() for i, ch in enumerate(text))


def drawable(path: str | None, text: str) -> str:
    """*text* as the font at *path* can draw it: a letter it lacks drawn from the glyphs it has (`_cluster_form`),
    and without the characters it has no glyph for at all, since a box in their place tells the reader nothing. As it
    is when the font cannot be read, and when the font has every glyph."""
    cov = _coverage(path) if path else None
    if cov is None:
        return text
    if all(_has(cov, ch) for ch in text) and not _capital_marks(text):
        return text
    out: list[str] = []
    for cluster in _clusters(text):
        form = _cluster_form(cov, cluster)
        out.append(form if form is not None else "".join(ch for ch in cluster if _has(cov, ch)))
    return "".join(out)
