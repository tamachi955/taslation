"""DEVELOPER TOOL, NOT PART OF THE APPLICATION: fetch the OpenMantra dataset into ~/.taslation/datasets/openmantra.

OpenMantra is the evaluation set of "Towards Fully Automated Manga Translation" (Ryota Hinami, Shonosuke
Ishiwatari, Kazuhiko Yasuda, Yusuke Matsui; AAAI 2021), published by Mantra Inc.: five Japanese manga series, the
page images, and for every speech bubble a box with the Japanese text and professional English and Chinese
translations. It is licensed CC BY-NC 4.0 (its LICENSE.md); TASlation is MIT, so the data never enters this
repository and is never shipped. This script downloads the archive of the dataset's GitHub repository, checks it,
extracts it into a new, empty folder outside the repository and writes SOURCE.md beside the data: where it came
from, when, the archive's SHA-256, the licence and the citation the authors ask for.

    python tools/fetch_openmantra.py                         # into ~/.taslation/datasets/openmantra
    python tools/fetch_openmantra.py --target D:/data/openmantra
    python tools/fetch_openmantra.py --force                 # replace what an earlier run put there (only that)
    python tools/fetch_openmantra.py --check                 # counts of a copy already fetched (no network)

Standard library only, and it never imports the application: TASlation itself uses no network but the local Ollama
server, and this download is the one exception, made here at the developer's request. The downloaded files are
data: nothing in them is ever run, the JSON is read with the json module only, and only what TASlation needs is
extracted (annotation.json, LICENSE.md, README.md, images/). Only counts are printed, never the text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

URL = "https://github.com/mantra-inc/open-mantra-dataset/archive/refs/heads/main.zip"
DEFAULT_TARGET = Path.home() / ".taslation" / "datasets" / "openmantra"
SOURCE = "SOURCE.md"
MANIFEST = ".fetched_files.json"  # every file this script put in the target, so that --force removes only those
REQUIRED_FILES = ("annotation.json", "LICENSE.md", "README.md")
IMAGES = "images"
MAX_DOWNLOAD = 512 * 1024 * 1024  # the archive is about 35 MB; anything far larger is not what we asked for
MAX_UNPACKED = 1024 * 1024 * 1024
MAX_MEMBERS = 20000
TIMEOUT = 60.0
CHUNK = 1 << 16


class FetchError(RuntimeError):
    pass


# ------------------------------------------------------------------------------------------------- download
def download(url: str, dest: Path, limit: int = MAX_DOWNLOAD) -> tuple[str, int]:
    """Stream *url* into *dest*; (SHA-256 hex digest, bytes)."""
    req = urllib.request.Request(url, headers={"User-Agent": "taslation-fetch-openmantra"})
    digest = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp, open(dest, "wb") as out:
        while True:
            block = resp.read(CHUNK)
            if not block:
                break
            size += len(block)
            if size > limit:
                raise FetchError(f"the download is larger than {limit // (1024 * 1024)} MB: not the expected archive")
            digest.update(block)
            out.write(block)
    return digest.hexdigest(), size


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


# -------------------------------------------------------------------------------------------- the archive
def _parts(name: str) -> tuple[str, ...] | None:
    """The member name as safe path parts, or None for a name that could point outside the target."""
    if not name or name.startswith(("/", "\\")) or "\\" in name or ":" in name or "\x00" in name:
        return None
    parts = PurePosixPath(name).parts
    if any(p in ("", ".", "..") for p in parts):
        return None
    return parts


def check_archive(zf: zipfile.ZipFile) -> tuple[str, list[tuple[zipfile.ZipInfo, str]]]:
    """The archive's single top folder and the members to extract, as (member, path relative to the top folder):
    the required files and every file under images/. Raises FetchError when the archive is not what was expected."""
    infos = zf.infolist()
    if len(infos) > MAX_MEMBERS:
        raise FetchError(f"the archive holds {len(infos)} members: not the expected archive")
    tops: set[str] = set()
    for info in infos:
        parts = _parts(info.filename.rstrip("/"))
        if parts is None:
            raise FetchError("the archive holds a member with an unsafe name")
        tops.add(parts[0])
    if len(tops) != 1:
        raise FetchError(f"the archive has {len(tops)} top-level entries, not a single folder")
    top = tops.pop()
    wanted: list[tuple[zipfile.ZipInfo, str]] = []
    unpacked = 0
    for info in infos:
        if info.is_dir():
            continue
        parts = _parts(info.filename)
        assert parts is not None
        rel = parts[1:]
        if not rel:
            raise FetchError("the archive's top-level entry is a file, not a folder")
        if (len(rel) == 1 and rel[0] in REQUIRED_FILES) or (len(rel) > 1 and rel[0] == IMAGES):
            wanted.append((info, "/".join(rel)))
            unpacked += info.file_size
    have = {rel for _info, rel in wanted}
    missing = [f for f in REQUIRED_FILES if f not in have]
    if not any(rel.startswith(IMAGES + "/") for rel in have):
        missing.append(IMAGES + "/")
    if missing:
        raise FetchError(f"the archive's folder lacks {', '.join(missing)}")
    if unpacked > MAX_UNPACKED:
        raise FetchError(f"the archive would unpack to {unpacked} bytes: not the expected archive")
    return top, wanted


# --------------------------------------------------------------------------------------------- the target
def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def remove_previous(target: Path) -> int:
    """Delete the files an earlier run of this script put in *target* (its manifest says which) and the folders
    that leaves empty; anything else in *target* stays. Returns the number of files deleted."""
    manifest = target / MANIFEST
    if not manifest.is_file():
        return 0
    try:
        listed = json.loads(manifest.read_text(encoding="utf-8")).get("files", [])
    except (OSError, ValueError, AttributeError) as e:
        raise FetchError(f"cannot read {manifest}: {e}") from e
    removed = 0
    folders: set[Path] = set()
    for rel in listed:
        parts = _parts(str(rel))
        if parts is None:
            continue
        path = target.joinpath(*parts)
        if not _inside(path, target) or path.is_symlink() or not path.is_file():
            continue
        path.unlink()
        removed += 1
        parent = path.parent
        while parent != target and _inside(parent, target):
            folders.add(parent)
            parent = parent.parent
    for folder in sorted(folders, key=lambda p: len(p.parts), reverse=True):
        try:
            folder.rmdir()  # only when empty
        except OSError:
            pass
    if manifest.exists():
        manifest.unlink()
    return removed


def prepare_target(target: Path, force: bool) -> None:
    if target.exists() and not target.is_dir():
        raise FetchError(f"{target} exists and is not a folder")
    if target.is_dir() and any(target.iterdir()):
        if not force:
            raise FetchError(f"{target} exists and is not empty; use --force to replace what an earlier run of this "
                             "script put there (nothing else is touched)")
        removed = remove_previous(target)
        print(f"removed {removed} file(s) of an earlier fetch", flush=True)
    target.mkdir(parents=True, exist_ok=True)


def extract(zf: zipfile.ZipFile, members: list[tuple[zipfile.ZipInfo, str]], target: Path) -> int:
    """Write *members* under *target* (never over an existing file); returns the bytes written. The manifest is
    written first, so a run that fails half-way can still be cleaned up with --force."""
    rels = [rel for _info, rel in members]
    for rel in rels + [SOURCE, MANIFEST]:
        if (target / rel).exists():
            raise FetchError(f"{rel} already exists in the target and was not put there by this script")
    (target / MANIFEST).write_text(json.dumps({"files": rels + [SOURCE, MANIFEST]}, indent=1), encoding="utf-8")
    written = 0
    for info, rel in members:
        out = target.joinpath(*rel.split("/"))
        if not _inside(out, target):
            raise FetchError("a member would land outside the target")
        out.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(out, "xb") as dst:
            size = 0
            for block in iter(lambda: src.read(CHUNK), b""):
                size += len(block)
                if size > info.file_size:
                    raise FetchError("a member is larger than the archive says")
                dst.write(block)
        written += size
    return written


# ------------------------------------------------------------------------------------- licence and citation
def licence_name(text: str) -> str:
    """The licence LICENSE.md states, e.g. "Creative Commons Attribution-NonCommercial 4.0 International"."""
    m = re.search(r"(Creative\s+Commons\s+)?(Attribution(?:[-\s][A-Za-z]+)*\s+\d\.\d(?:\s+International)?)", text)
    if m:
        name = "Creative Commons " + re.sub(r"\s+", " ", m.group(2)).strip()
        short = {"Attribution-NonCommercial 4.0": "CC BY-NC 4.0", "Attribution-NonCommercial-ShareAlike 4.0": "CC BY-NC-SA 4.0",
                 "Attribution 4.0": "CC BY 4.0", "Attribution-ShareAlike 4.0": "CC BY-SA 4.0"}
        for key, abbr in short.items():
            if re.sub(r"\s+International$", "", m.group(2).strip()) == key:
                return f"{name} ({abbr})"
        return name
    for line in text.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:120]
    return "(LICENSE.md is empty)"


def bibtex(readme: str) -> str:
    """The first BibTeX entry in the README (from a fenced block, else from the running text), or ""."""
    for block in re.findall(r"```[^\n]*\n(.*?)```", readme, re.S):
        if re.search(r"@\w+\s*\{", block):
            return block.strip()
    m = re.search(r"@\w+\s*\{", readme)
    if not m:
        return ""
    depth, i = 0, m.end() - 1
    for i in range(m.end() - 1, len(readme)):
        if readme[i] == "{":
            depth += 1
        elif readme[i] == "}":
            depth -= 1
            if depth == 0:
                break
    return readme[m.start():i + 1].strip()


def write_source(target: Path, url: str, when: datetime, sha: str, size: int, top: str, files: int) -> str:
    licence = licence_name((target / "LICENSE.md").read_text(encoding="utf-8", errors="replace"))
    cite = bibtex((target / "README.md").read_text(encoding="utf-8", errors="replace"))
    lines = [
        "# OpenMantra: where this copy came from",
        "",
        "This folder was filled by TASlation's `tools/fetch_openmantra.py`. The dataset is not part of TASlation and",
        "is not covered by TASlation's MIT licence; it is used under its own licence, below.",
        "",
        "- Dataset: OpenMantra, the evaluation set of \"Towards Fully Automated Manga Translation\" (Ryota Hinami,",
        "  Shonosuke Ishiwatari, Kazuhiko Yasuda, Yusuke Matsui; AAAI 2021), published by Mantra Inc.",
        f"- Source: {url}",
        f"- Downloaded: {when.strftime('%Y-%m-%d %H:%M:%S')} UTC",
        f"- Archive: {size} bytes, SHA-256 `{sha}` (top folder `{top}/`)",
        f"- Extracted: {files} files (annotation.json, LICENSE.md, README.md and images/), unchanged",
        f"- Licence: {licence}. The licence text is `LICENSE.md` beside this file, copied from the archive as is.",
        "  Non-commercial use only; attribute the dataset, its authors and the licence wherever it is used.",
        "",
        "## Citation (BibTeX, copied from the dataset's README)",
        "",
        "```bibtex",
        cite or "(the dataset's README holds no BibTeX entry)",
        "```",
        "",
    ]
    (target / SOURCE).write_text("\n".join(lines), encoding="utf-8")
    return licence


# --------------------------------------------------------------------------------------------------- counts
def counts(target: Path) -> dict[str, int]:
    """Series, pages and bubbles in annotation.json; page images and bytes on disk."""
    data = json.loads((target / "annotation.json").read_text(encoding="utf-8"))
    books = data if isinstance(data, list) else []
    series = pages = bubbles = 0
    for book in books:
        if not isinstance(book, dict):
            continue
        series += 1
        for page in book.get("pages") or []:
            if isinstance(page, dict):
                pages += 1
                bubbles += len(page.get("text") or [])
    image_files = [p for p in (target / IMAGES).rglob("*") if p.is_file()]
    try:  # the files this script put there (results an evaluation wrote beside them are not the dataset)
        listed = json.loads((target / MANIFEST).read_text(encoding="utf-8")).get("files", [])
        files = [target / rel for rel in listed if _parts(str(rel)) is not None]
    except (OSError, ValueError, AttributeError):
        files = list(target.rglob("*"))
    data_bytes = sum(p.stat().st_size for p in files if p.is_file())
    return {"series": series, "pages": pages, "bubbles": bubbles, "images": len(image_files), "bytes": data_bytes}


def print_counts(c: dict[str, int]) -> None:
    print(f"series {c['series']}, pages {c['pages']}, bubbles {c['bubbles']}; {c['images']} page images, "
          f"{c['bytes']} bytes on disk ({c['bytes'] / (1024 * 1024):.1f} MB)", flush=True)


# ----------------------------------------------------------------------------------------------------- main
def fetch(target: Path, url: str = URL, force: bool = False) -> dict[str, int]:
    prepare_target(target, force)
    workdir = Path(tempfile.mkdtemp(prefix="openmantra-download-"))  # a new, empty folder of its own
    try:
        archive = workdir / "open-mantra-dataset.zip"
        print(f"downloading {url} ...", flush=True)
        when = datetime.now(timezone.utc)
        sha, size = download(url, archive)
        print(f"downloaded {size} bytes, SHA-256 {sha}", flush=True)
        if not zipfile.is_zipfile(archive):
            raise FetchError("the download is not a zip archive")
        with zipfile.ZipFile(archive) as zf:
            top, members = check_archive(zf)
            written = extract(zf, members, target)
        licence = write_source(target, url, when, sha, size, top, len(members))
        print(f"extracted {len(members)} files ({written} bytes) into {target}; licence: {licence}", flush=True)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    c = counts(target)
    c["archive_bytes"] = size
    return c


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--target", type=Path, default=DEFAULT_TARGET, help=f"folder to fill (default: {DEFAULT_TARGET})")
    ap.add_argument("--url", default=URL, help=argparse.SUPPRESS)
    ap.add_argument("--force", action="store_true",
                    help="the target is not empty: delete what an earlier run of this script put there, then fetch")
    ap.add_argument("--check", action="store_true", help="print the counts of a copy already fetched (no download)")
    args = ap.parse_args(argv)
    target = args.target.expanduser()
    try:
        if args.check:
            if not (target / "annotation.json").is_file():
                raise FetchError(f"no dataset at {target}: run this script without --check first")
            print_counts(counts(target))
            return 0
        print_counts(fetch(target, args.url, args.force))
    except (FetchError, OSError, zipfile.BadZipFile, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
