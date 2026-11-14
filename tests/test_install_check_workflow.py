""".github/workflows/install-check.yml, the install check on a fresh Windows runner, and its helpers: what it may do
(started by hand only, read-only rights), where the licences are agreed (one step, install.ps1's exact sentences, the
owner's agreement written beside them), that the installed program runs in the install folder, and that the lines it
looks for are the scripts' own. Nothing here runs the workflow; GitHub's ZIP has no .github, so a copy unpacked from
it skips these.
"""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "install-check.yml"
HELPERS = ROOT / ".github" / "install-check"

pytestmark = pytest.mark.skipif(not WORKFLOW.is_file(), reason="no .github here (GitHub's ZIP leaves it out)")


def _workflow() -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(WORKFLOW.read_text("utf-8"))


def _steps() -> list[dict]:
    return _workflow()["jobs"]["install-check"]["steps"]


def _step(name_part: str) -> tuple[int, dict]:
    found = [(i, s) for i, s in enumerate(_steps()) if name_part in s.get("name", "")]
    assert len(found) == 1, name_part
    return found[0]


def _install_ps1(name: str) -> str:
    m = re.search(r"^\$" + name + r" = '([^']+)'", (ROOT / "install.ps1").read_text("ascii"), re.M)
    assert m, name
    return m.group(1)


def test_it_is_started_by_hand_or_weekly_and_may_only_read_the_repository():
    wf = _workflow()
    on = wf.get("on", wf.get(True))  # (YAML 1.1 reads the key `on` as true)
    assert sorted(on) == ["schedule", "workflow_dispatch"]  # never a push or a pull request: it downloads 5 GB
    assert on["schedule"] == [{"cron": "0 22 * * 0"}]  # once a week
    assert "if (-not $hide) { $hide = 'true' }" in (ROOT / ".github/workflows/install-check.yml").read_text("utf-8")
    assert wf["permissions"] == {"contents": "read"}
    assert list(wf["jobs"]) == ["install-check"]
    job = wf["jobs"]["install-check"]
    assert job["runs-on"] == "windows-2025"  # (the image with winget)
    assert 30 <= job["timeout-minutes"] <= 120
    assert job["defaults"]["run"]["shell"] == "pwsh"
    text = WORKFLOW.read_text("utf-8")
    assert "secrets." not in text and "pull_request" not in text
    checkout = _steps()[0]
    assert checkout["uses"].startswith("actions/checkout@") and checkout["with"]["persist-credentials"] is False
    # actions of GitHub's own only
    assert all(s["uses"].split("/")[0] == "actions" for s in _steps() if "uses" in s)


def test_the_licences_are_agreed_in_the_install_step_only_with_install_ps1s_exact_sentences():
    ocr, plamo = _install_ps1("OcrConsentVar"), _install_ps1("PlamoConsentVar")
    assert (ocr, plamo) == ("TASLATION_AGREE_OCR_LICENCE", "TASLATION_AGREE_PLAMO_LICENCE")
    wf = _workflow()
    assert "env" not in wf and "env" not in wf["jobs"]["install-check"]  # (no other step has them)
    with_consent = [s for s in _steps() if ocr in (s.get("env") or {}) or plamo in (s.get("env") or {})]
    _i, install = _step("(install.cmd -Yes)")
    assert with_consent == [install]
    assert install["env"][ocr] == _install_ps1("OcrConsentText") == "I agree to CC BY-NC-SA 4.0"
    assert install["env"][plamo] == _install_ps1("PlamoConsentText") == "I agree to the PLaMo Community License"
    assert re.search(r"^\s*& \.\\install\.cmd -Yes 2>&1 \|", install["run"], re.M)
    assert install["working-directory"] == "${{ env.INSTALL_DIR }}"
    # whose agreement it is, for what use, and which licences, right above the sentences
    text = WORKFLOW.read_text("utf-8")
    above = text[:text.index(f"{ocr}: ")]
    above = above[above.rindex("env:"):]
    assert "The repository owner has read the two licences below and agrees to them" in above
    assert "non-commercial" in above
    assert "https://creativecommons.org/licenses/by-nc-sa/4.0/" in above
    assert "https://plamo.preferredai.jp/info/plamo-community-license-en" in above


def test_the_installed_program_runs_in_the_install_folder():
    # `python -m taslation` takes the package from the folder it runs in: never the checkout's
    for step in _steps():
        run = step.get("run", "")
        if "$VenvPy" in run or "uninstall.cmd" in run:
            assert ("Set-Location -LiteralPath $InstallDir" in run
                    or step.get("working-directory") == "${{ env.INSTALL_DIR }}"), step["name"]
    helper = (HELPERS / "translate-page.py").read_text("utf-8")
    assert "cwd=install_dir" in helper and "sys.prefix == sys.base_prefix" in helper


def test_the_steps_run_in_an_order_that_shows_whose_setting_the_server_has():
    # the prompt cache is looked at before anything of TASlation starts Ollama (it would pass the setting itself),
    # and the uninstall comes last
    order = [_step(n)[0] for n in ("(install.cmd -Yes)", "Check what the installer made", "taslation doctor",
                                   "prompt cache", "Translate a synthetic test page", "-DryRun", "uninstall.cmd -Yes",
                                   "Job summary", "Keep the console output")]
    assert order == sorted(order)
    for name in ("Job summary", "Keep the console output"):
        assert _step(name)[1]["if"] == "${{ always() }}"
    upload = _step("Keep the console output")[1]
    assert upload["uses"].startswith("actions/upload-artifact@")
    assert upload["with"]["path"] == "${{ runner.temp }}/install-check/"


def test_the_helpers_it_names_are_there_and_parse():
    text = WORKFLOW.read_text("utf-8")
    named = set(re.findall(r"\.github[/\\]install-check[/\\](\w[\w-]*\.\w+)", text))
    assert named == {"checks.ps1", "translate-page.py"}
    for name in named:
        assert (HELPERS / name).is_file(), name
    for path in (WORKFLOW, *HELPERS.iterdir()):
        assert all(b < 128 for b in path.read_bytes()), path.name
    ast.parse((HELPERS / "translate-page.py").read_text("utf-8"))


@pytest.mark.skipif(not shutil.which("pwsh"), reason="PowerShell 7 (the runner's shell) is not installed")
def test_every_step_and_checks_ps1_parse_in_powershell_7(tmp_path):
    scripts = [HELPERS / "checks.ps1"]
    for i, step in enumerate(_steps()):
        if "run" in step:
            scripts.append(tmp_path / f"step{i:02d}.ps1")
            scripts[-1].write_text(step["run"], "utf-8")
    command = "; ".join(
        f"$t = $null; $e = $null; $null = [System.Management.Automation.Language.Parser]::ParseFile('{p}', [ref]$t, "
        f"[ref]$e); foreach ($x in $e) {{ '{p.name}: ' + $x.Message }}" for p in scripts)
    r = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True, text=True,
                       timeout=120, stdin=subprocess.DEVNULL)
    assert r.returncode == 0 and r.stdout.strip() == "", r.stdout + r.stderr


def test_the_lines_it_looks_for_are_the_scripts_own():
    install = (ROOT / "install.ps1").read_text("ascii")
    for line in ("Write-Host (T 'TASlation is installed.')", 'Write-Host "$($script:Warnings.Count) warning(s):"',
                 "Write-Ok \"Python $($basePython.Version) installed\"", "Write-Ok \"Python $($basePython.Version) found\"",
                 "Write-Ok 'Ollama installed'", "Write-Ok 'Ollama found'", "Write-Info \"$question -> $($Offered.Name) ($why)\"",
                 "Write-Ok (T 'Ollama started, with its app')",
                 "Write-Ok (T 'Ollama started, as ollama serve in a hidden window (it runs until you sign out)')",
                 "is agreed to through {2}, by whoever set that variable.", "'[{0}/{1}] {2}'",
                 "$lnk.Arguments = '-m taslation gui'", "$CacheRamMarker = Join-Path $Root '.cache-ram-by-install'"):
        assert line in install, line
    uninstall = (ROOT / "uninstall.ps1").read_text("ascii")
    for line in ('"  dry run, would: $Text"', "Remove-Target 'the virtual environment' $Venv",
                 "Remove-Target 'the OCR model and fonts' $Models", '"delete $What ($Path, $size)"',
                 '"delete the Start-menu shortcut $ShortcutPath"', '"ollama rm $name"', '"clear $Name for this user"'):
        assert line in uninstall, line
    workflow = WORKFLOW.read_text("utf-8")
    model = re.search(r"^\$TranslatorModel = '([^']+)'", (HELPERS / "checks.ps1").read_text("ascii"), re.M).group(1)
    assert model in (ROOT / "setup_models.py").read_text("utf-8")
    assert "'Result: ready'" in workflow and 'print("Result:", "ready"' in (ROOT / "taslation" / "cli.py").read_text("utf-8")


def test_github_zip_leaves_the_checks_out():
    rules = (ROOT / ".gitattributes").read_text(encoding="ascii").splitlines()
    assert ".github export-ignore" in rules and ".github/** export-ignore" in rules
    if shutil.which("git") and (ROOT / ".git").exists():
        r = subprocess.run(["git", "check-attr", "export-ignore", "--", ".github/workflows/install-check.yml",
                            ".github/install-check/checks.ps1"], cwd=ROOT, capture_output=True, text=True, timeout=30)
        assert r.returncode == 0 and r.stdout.count(": export-ignore: set") == 2, r.stdout
    # and an update from a clone never copies them
    assert re.search(r"^\$KeptNames = @\([^)]*'\.github'", (ROOT / "update.ps1").read_text("ascii"), re.M)
