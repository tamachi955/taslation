"""Before a push: has the version gone up where it has to (docs/DEVELOPMENT.md, "Releases")?

    python tools/version_check.py

Compares the working tree with the newest version tag (``vX.Y.Z``) and fails (exit 1) when a file a person installs
differs from it while the version is the tag's, when the version is lower than the tag's, or when CHANGELOG.md has no
entry for the version at its top. Reads git and the files only; changes nothing and uses no network."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# What a person never installs or runs: a change there alone needs no new version.
DEVELOPER_ONLY = ("tests/", "tools/", ".github/", "docs/media/", "docs/research/", "docs/DEVELOPMENT.md",
                  "docs/ARCHITECTURE.md", "docs/OFFLINE_VERIFICATION.md", ".gitattributes", ".gitignore",
                  "CHANGELOG.md")


def parse(version: str) -> tuple[int, int, int]:
    """``X.Y.Z`` as numbers."""
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version.strip())
    if m is None:
        raise ValueError(f"not a version X.Y.Z: {version!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def project_version(root: Path) -> str:
    """The version pyproject.toml gives, as update.cmd reads it."""
    m = re.search(r'(?m)^\s*version\s*=\s*"([^"]+)"', (root / "pyproject.toml").read_text("utf-8"))
    if m is None:
        raise ValueError("pyproject.toml has no version")
    return m.group(1)


def changelog_entries(text: str) -> list[tuple[str, str]]:
    """The (version, date) of the changelog's entries, in its order."""
    return re.findall(r"(?m)^## (\d+\.\d+\.\d+) - (\S+)\s*$", text)


def installed(path: str) -> bool:
    """Whether *path* (as git names it) is a file a person installs, runs or reads with the program."""
    return not any(path == rule or (rule.endswith("/") and path.startswith(rule)) for rule in DEVELOPER_ONLY)


def verdict(version: str, tagged: str | None, changed: list[str], changelog: str) -> list[str]:
    """What is wrong, in words: *version* the tree's, *tagged* the newest tag's (None: no tag yet), *changed* the files
    that differ from the tag."""
    problems = []
    entries = changelog_entries(changelog)
    if not entries or entries[0][0] != version:
        problems.append(f"CHANGELOG.md has no entry for {version} at its top")
    if tagged is None:
        return problems
    if parse(version) < parse(tagged):
        problems.append(f"the version {version} is lower than the newest tag's, {tagged}")
    elif parse(version) == parse(tagged):
        files = [path for path in changed if installed(path)]
        if files:
            shown = ", ".join(files[:5]) + (f" and {len(files) - 5} more" if len(files) > 5 else "")
            problems.append(f"files a person installs differ from v{tagged} and the version is still {version}: {shown}")
    return problems


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True).stdout


def newest_tag() -> str | None:
    """The highest version among the tags ``vX.Y.Z``."""
    versions = [name[1:] for name in _git("tag", "--list", "v*").split() if re.fullmatch(r"v\d+\.\d+\.\d+", name)]
    return max(versions, key=parse) if versions else None


def main() -> int:
    version = project_version(ROOT)
    tagged = newest_tag()
    changed = _git("diff", "--name-only", f"v{tagged}").split("\n") if tagged else []
    changed += _git("ls-files", "--others", "--exclude-standard").split("\n") if tagged else []
    problems = verdict(version, tagged, [path for path in changed if path],
                       (ROOT / "CHANGELOG.md").read_text("utf-8"))
    for problem in problems:
        print(f"version check: {problem}")
    if not problems:
        print(f"version check: ok ({version}" + (f", newest tag v{tagged})" if tagged else ", no tag yet)"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
