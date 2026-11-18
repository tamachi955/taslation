"""The version is written in two places and told in the changelog (docs/DEVELOPMENT.md, "Releases"): they agree, and
the developer's check before a push knows when it has to go up."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import taslation

ROOT = Path(__file__).resolve().parent.parent


def _tool():
    spec = importlib.util.spec_from_file_location("version_check", ROOT / "tools" / "version_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_two_places_agree_and_the_version_is_three_numbers():
    tool = _tool()
    assert re.fullmatch(r"\d+\.\d+\.\d+", taslation.__version__)
    assert tool.project_version(ROOT) == taslation.__version__
    # the line update.cmd and the installer read from a copy: a literal in pyproject.toml, never worked out at build
    assert re.search(r'(?m)^version = "%s"$' % re.escape(taslation.__version__), (ROOT / "pyproject.toml").read_text("utf-8"))


def test_the_changelogs_top_entry_is_this_version_with_its_date():
    tool = _tool()
    entries = tool.changelog_entries((ROOT / "CHANGELOG.md").read_text("utf-8"))
    assert entries[0][0] == taslation.__version__
    assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) for _version, date in entries)
    numbers = [tool.parse(version) for version, _date in entries]
    assert numbers == sorted(numbers, reverse=True) and len(set(numbers)) == len(numbers)  # newest first, none twice


def test_what_a_person_installs_is_told_from_what_only_a_developer_meets():
    tool = _tool()
    assert tool.installed("taslation/pipeline.py") and tool.installed("install.ps1") and tool.installed("pyproject.toml")
    assert tool.installed("README.md") and tool.installed("docs/MANUAL.ja.md")
    for path in ("tests/test_version.py", "tools/version_check.py", "docs/DEVELOPMENT.md", "docs/ARCHITECTURE.md",
                 ".github/workflows/install-check.yml", "docs/media/demo.gif", ".gitattributes", "CHANGELOG.md"):
        assert not tool.installed(path)


def test_the_check_wants_a_higher_version_only_when_an_installed_file_changed():
    tool = _tool()
    log = "# Changelog\n\n## 0.2.1 - 2026-11-19\n\n* x\n\n## 0.2.0 - 2026-11-18\n"
    before = log.replace("## 0.2.1 - 2026-11-19\n\n* x\n\n", "")
    assert tool.verdict("0.2.0", "0.2.0", ["tools/x.py", "tests/test_x.py"], before) == []
    problems = tool.verdict("0.2.0", "0.2.0", ["taslation/pipeline.py"], before)
    assert len(problems) == 1 and "taslation/pipeline.py" in problems[0]
    assert tool.verdict("0.2.1", "0.2.0", ["taslation/pipeline.py"], log) == []
    assert tool.verdict("0.2.1", "0.2.0", ["taslation/pipeline.py"], log.replace("0.2.1", "0.2.2")) != []  # no entry
    assert tool.verdict("0.1.9", "0.2.0", [], log) != []  # never back
    assert tool.verdict("0.2.0", None, ["taslation/pipeline.py"], log.replace("## 0.2.1 - 2026-11-19\n\n* x\n\n", "")) == []
