""".github/workflows/gpu-checks.yml, the GPU computer's checks on GitHub's runners, and its helpers: what it may do (a
push to ci/... or main, or a start by hand, read-only rights, bounded jobs and times, at most 20 jobs at once with
tests.yml's), that the caches are made on main only and read elsewhere, that the stand-in's jobs run every scenario
once and the benchmark's every title, that Ollama comes from its pinned release, checked, where TASlation looks for
it, where PLaMo's licence is agreed (one step, install.ps1's exact sentence, the owner's agreement beside it), that no
cache and no artifact holds the dataset or a picture, and what its summaries and verdicts make of the tools' reports.
Nothing here runs the workflow, Ollama or a model; GitHub's ZIP has no .github, so a copy unpacked from it skips these.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "gpu-checks.yml"
TESTS = ROOT / ".github" / "workflows" / "tests.yml"
HELPERS = ROOT / ".github" / "gpu-checks"
ON_MAIN = "github.ref == 'refs/heads/main'"

pytestmark = pytest.mark.skipif(not WORKFLOW.is_file(), reason="no .github here (GitHub's ZIP leaves it out)")

sys.path.insert(0, str(ROOT / "tools"))

needs_pwsh = pytest.mark.skipif(not shutil.which("pwsh"), reason="PowerShell 7 (the runner's shell) is not installed")


def _load(path: Path) -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(path.read_text("utf-8"))


def _workflow() -> dict:
    return _load(WORKFLOW)


def _on(wf: dict) -> dict:
    return wf.get("on", wf.get(True))  # (YAML 1.1 reads the key `on` as true)


def _summarise():
    spec = importlib.util.spec_from_file_location("gpu_checks_summarise", HELPERS / "summarise.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _steps(job: str, wf: dict | None = None) -> list[dict]:
    return (wf or _workflow())["jobs"][job]["steps"]


def _step(job: str, name_part: str, wf: dict | None = None) -> dict:
    found = [s for s in _steps(job, wf) if name_part in s.get("name", "")]
    assert len(found) == 1, (job, name_part)
    return found[0]


def _install_ps1(name: str) -> str:
    m = re.search(r"^\$" + name + r" = '([^']+)'", (ROOT / "install.ps1").read_text("ascii"), re.M)
    assert m, name
    return m.group(1)


def _groups() -> dict[str, dict[str, str]]:
    """The stand-in's groups: name -> {scenarios, role, size}."""
    return json.loads(_workflow()["env"]["STANDIN_GROUPS"])


def test_it_runs_for_a_ci_branch_main_or_by_hand_with_read_only_rights_and_bounded_jobs():
    wf = _workflow()
    on = _on(wf)
    assert sorted(on) == ["push", "workflow_dispatch"]
    assert on["push"] == {"branches": ["ci/**", "main"]}
    assert wf["permissions"] == {"contents": "read"}
    assert wf["concurrency"]["cancel-in-progress"] is True
    text = WORKFLOW.read_text("utf-8")
    assert "secrets." not in text and "pull_request" not in text and "schedule" not in text
    jobs = wf["jobs"]
    assert list(jobs) == ["prepare", "standin", "benchmark", "summary"]
    for name, job in jobs.items():
        assert job["runs-on"] == "windows-2025", name
        assert 1 <= job["timeout-minutes"] <= 60, name
        assert job["defaults"]["run"]["shell"] == "pwsh", name
        for step in job["steps"]:
            assert step.get("timeout-minutes", 0) < job["timeout-minutes"], (name, step.get("name"))
            if "uses" in step:  # actions of GitHub's own only
                assert step["uses"].split("/")[0] == "actions", step["uses"]
            if step.get("uses", "").startswith("actions/checkout@"):  # (nothing here pushes: no token stays)
                assert step["with"]["persist-credentials"] is False
        assert job.get("permissions", {"contents": "read"}) in ({"contents": "read"},
                                                                {"contents": "read", "actions": "read"}), name
    assert jobs["summary"]["permissions"] == {"contents": "read", "actions": "read"}
    # the matrices come from the job "prepare" (a part of them by hand), each job with a time limit
    assert jobs["standin"]["strategy"]["matrix"] == {"include": "${{ fromJSON(needs.prepare.outputs.standin_matrix) }}"}
    assert jobs["benchmark"]["strategy"]["matrix"] == {"title": "${{ fromJSON(needs.prepare.outputs.titles) }}"}
    assert jobs["standin"]["if"] == "needs.prepare.outputs.standin == 'true'"  # (an empty matrix is no job)
    assert jobs["benchmark"]["if"] == "needs.prepare.outputs.benchmark == 'true'"
    assert jobs["standin"]["needs"] == jobs["benchmark"]["needs"] == "prepare"
    assert jobs["summary"]["needs"] == ["prepare", "standin", "benchmark"]
    assert "needs.prepare.result == 'success'" in jobs["summary"]["if"]
    # at most 20 jobs at once (GitHub's limit for the account) with tests.yml's, which the same push starts
    parallel = [jobs[name]["strategy"]["max-parallel"] for name in ("standin", "benchmark")]
    assert all(jobs[name]["strategy"]["fail-fast"] is False for name in ("standin", "benchmark"))
    assert parallel == [min(len(_groups()), 7), 5]
    shards = _load(TESTS)["jobs"]["suite"]["strategy"]["matrix"]["shard"]
    assert len(shards) == int(_load(TESTS)["env"]["SHARDS"]) == 8
    assert sum(parallel) + len(shards) <= 20
    # an input reaches a script only through the environment, and is checked there
    inputs = on["workflow_dispatch"]["inputs"]
    assert len(inputs) == 10 and text.count("${{ inputs.") == len(inputs)
    for name, spec in inputs.items():
        if name == "checks":  # (a push to main runs no check: the caches alone)
            assert f"${{{{ inputs.checks || ({ON_MAIN} && 'none') || 'both' }}}}" in text
        else:
            assert f"${{{{ inputs.{name} || '{spec['default']}' }}}}" in text, name
    for job in jobs:
        for step in _steps(job, wf):
            assert "inputs." not in step.get("run", ""), step.get("name")


def test_ollama_comes_from_its_pinned_release_checked_and_unpacked_where_taslation_looks(tmp_path, monkeypatch):
    wf = _workflow()
    pinned = wf["env"]["OLLAMA_PINNED"]
    assert pinned == "v0.40.17" == _on(wf)["workflow_dispatch"]["inputs"]["ollama_version"]["default"]
    assert wf["env"]["OLLAMA_VERSION"] == f"${{{{ inputs.ollama_version || '{pinned}' }}}}"
    assert re.fullmatch(r"[0-9a-f]{64}", wf["env"]["OLLAMA_PINNED_ZIP_SHA256"])
    download = _step("prepare", "Download Ollama's files", wf)
    assert "$env:OLLAMA_PINNED_ZIP_SHA256" in download["run"] and "-eq $env:OLLAMA_PINNED" in download["run"]
    assert "Install-OllamaFiles $release $pinned" in download["run"]
    helpers = (HELPERS / "helpers.ps1").read_text("ascii")
    # the release's standalone zip, checked against every SHA-256 there is for it (one at least) and its size
    assert "$OllamaZip = 'ollama-windows-amd64.zip'" in helpers
    for words in ("$wanted = [ordered]@{ pinned = $Pinned; github = $Release.digest }", "$wanted['sha256sum.txt']",
                  "does not match the SHA-256 of $name", "no SHA-256 to check", "is not the size the release gives",
                  "holds no ollama.exe at its top"):
        assert words in helpers, words
    body = helpers[helpers.index("function Install-OllamaFiles"):]
    assert body.index("no SHA-256 to check") < body.index("ExtractToDirectory")  # (nothing unpacked unchecked)
    # no installer, nothing started: only Ollama's own processes stopped (its program folder)
    assert "Start-Process" not in helpers and "OllamaSetup" not in helpers
    assert "$OllamaHome.TrimEnd('\\') + '\\'" in helpers
    assert "$OllamaHome = Join-Path $env:LOCALAPPDATA 'Programs\\Ollama'" in helpers
    # ... where TASlation's starter and the translator's install look for ollama.exe
    paths = {s["with"]["path"] for job in wf["jobs"] for s in _steps(job, wf)
             if s.get("uses", "").startswith("actions/cache") and "program_key" in s["with"]["key"]}
    assert paths == {"~/AppData/Local/Programs/Ollama"}
    from taslation import ollama_start, translator_install

    exe = tmp_path / "Programs" / "Ollama" / "ollama.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert ollama_start.find_ollama() == [str(exe), "serve"]
    assert translator_install.find_ollama() == str(exe)


def test_the_caches_are_made_on_main_only_and_read_elsewhere():
    wf = _workflow()
    caches = [(job, s) for job in wf["jobs"] for s in _steps(job, wf) if s.get("uses", "").startswith("actions/cache")]
    assert all(s["uses"] in ("actions/cache/restore@v5", "actions/cache/save@v5") for _, s in caches)
    saves = [s for job, s in caches if s["uses"].startswith("actions/cache/save")]
    assert sorted(s["with"]["key"].split(".")[-1].rstrip(" }") for s in saves) == [
        "models_key", "pip_key", "program_key", "store_key"]
    assert all(job == "prepare" for job, s in caches if s["uses"].startswith("actions/cache/save"))
    for step in saves:
        assert step["if"].startswith(ON_MAIN + " && "), step["name"]
    # what makes a cache runs on main only (a ci branch never downloads Ollama, the models or PLaMo for one)
    for name in ("Download Ollama's files", "Ollama's files from the cache", "Python 3.13", "pip's downloads from",
                 "Install the packages", "Download the models", "Import the translation model"):
        assert _step("prepare", name, wf)["if"].startswith(ON_MAIN + " && "), name
    # one path for each key, everywhere (a cache is found only under the paths it was kept with)
    paths: dict[str, set[str]] = {}
    for _, s in caches:
        paths.setdefault(s["with"]["key"].split(".")[-1].rstrip(" }"), set()).add(s["with"]["path"])
    assert paths == {"program_key": {"~/AppData/Local/Programs/Ollama"}, "store_key": {"~/.ollama/models"},
                     "models_key": {"models"}, "pip_key": {"~/AppData/Local/pip/Cache"}}
    # the jobs restore them, the three that are needed or nothing
    for job in ("standin", "benchmark"):
        restores = {s["with"]["key"]: s for j, s in caches if j == job}
        assert sorted(restores) == sorted(f"${{{{ needs.prepare.outputs.{k} }}}}"
                                          for k in ("program_key", "store_key", "models_key", "pip_key"))
        for key, s in restores.items():
            assert s["with"].get("fail-on-cache-miss") is (None if "pip_key" in key else True), key
        assert restores["${{ needs.prepare.outputs.pip_key }}"]["with"]["restore-keys"] == "pip-Windows-py3.13-"
        for s in _steps(job, wf):
            assert "Install-OllamaFiles" not in s.get("run", "") and "setup_models.py" not in s.get("run", "")
    # no step saves on its own (setup-python's pip cache saves for the branch it runs on)
    for job in wf["jobs"]:
        for s in _steps(job, wf):
            if s.get("uses", "").startswith("actions/setup-python"):
                assert set(s["with"]) == {"python-version"}, (job, s["name"])
    lookups = [s for s in _steps("prepare", wf) if (s.get("with") or {}).get("lookup-only") is True]
    assert len(lookups) == 4
    gate = _step("prepare", "The caches a run on main makes", wf)["run"]
    assert "::error title=Caches::" in gate and "Run this workflow on main first" in gate
    plan = _step("prepare", "Which checks", wf)
    assert 'pip_key = "pip-Windows-py3.13-$env:PIP_HASH"' in plan["run"]
    assert 'models_key = "models-$env:MODELS_HASH"' in plan["run"]
    assert plan["env"]["MODELS_HASH"] == "${{ hashFiles('setup_models.py') }}"
    assert plan["env"]["PIP_HASH"] == "${{ hashFiles('pyproject.toml') }}"


def test_tests_yml_runs_for_every_ci_branch_and_reads_mains_caches_only():
    tests = _load(TESTS)
    assert _on(tests)["push"]["branches"] == ["ci/**"]
    steps = tests["jobs"]["suite"]["steps"]
    uses = [s["uses"] for s in steps if "uses" in s]
    assert not any(u.startswith(("actions/cache@", "actions/cache/save")) for u in uses), uses
    assert all(set(s["with"]) == {"python-version"} for s in steps if s.get("uses", "").startswith("actions/setup-python"))
    restored = {s["with"]["path"]: s["with"] for s in steps if s.get("uses", "").startswith("actions/cache/restore")}
    assert restored["models"]["key"] == "models-${{ hashFiles('setup_models.py') }}"
    pip = restored["~/AppData/Local/pip/Cache"]
    # (runner.os is "Windows": the key the job "prepare" of gpu-checks.yml keeps them under)
    assert pip["key"] == "pip-${{ runner.os }}-py3.13-${{ hashFiles('pyproject.toml') }}"
    assert pip["restore-keys"] == "pip-${{ runner.os }}-py3.13-"
    assert any("setup_models.py --models-dir models" in s.get("run", "") for s in steps)  # (else downloaded)
    # the packages gpu-checks.yml's prepare installs on main are these (pip's downloads kept there serve both)
    install = next(s["run"] for s in steps if s.get("name", "").startswith("Install the packages"))
    prepare = _step("prepare", "Install the packages")["run"]
    for line in ("pip install torch --index-url https://download.pytorch.org/whl/cpu", 'pip install -e ".[backup,dev]"'):
        assert line in install and line in prepare, line


def test_the_stand_in_jobs_run_every_scenario_once_and_the_benchmark_every_title():
    import standin_e2e

    groups = _groups()
    covered, editing = [], []
    for group, spec in groups.items():
        assert sorted(spec) == ["role", "scenarios", "size"], group
        assert spec["role"] in ("reader", "editing"), group
        names = standin_e2e.wanted(spec["scenarios"])
        # (the group says what the tool runs, a pair comes along, and an editing group says so)
        assert group == "-".join(names) + ("-editing" if spec["role"] == "editing" else ""), group
        (editing if spec["role"] == "editing" else covered).extend(names)
    # every scenario of "all" once, and scenario k's three paces (never in "all") once; of those by their names only,
    # the ones a runner's one monitor can show: another tab (tab0 needs a start of its own), the window resized, the
    # page slid, a start behind another window - all of them in Reader mode, and one group again in editing
    by_name = [*standin_e2e.TAB_STEPS_ASKED, *standin_e2e.R_STEPS, "s", "h"]
    assert sorted(covered) == sorted([*standin_e2e.ORDER, *standin_e2e.K_ASKED, *by_name])
    assert len(covered) == len(set(covered))
    assert editing and set(editing) <= set(covered) and sum(s["role"] == "editing" for s in groups.values()) == 1
    assert not set(covered) & set(standin_e2e.M_STEPS)  # (a second monitor: none on a runner)
    behind = "if (($env:SCENARIOS -split ',') -contains 'h') { $arguments += @('--start-behind', 'cover') }"
    assert behind in _step("standin", "Run: tools/standin_e2e.py")["run"]
    # the groups whose criteria look at the side panes: a stand-in with room for them beside a spread (the tool's own
    # size leaves none), within the runner's screen less its taskbar; the others at the tool's size
    display = [int(v) for v in _workflow()["env"]["DISPLAY_SIZE"].split("||")[-1].strip(" '}").split("x")]
    panes = {*standin_e2e.TAB_STEPS_ASKED, *standin_e2e.R_STEPS, "s", "h"}
    for group, spec in groups.items():
        names = set(standin_e2e.wanted(spec["scenarios"]))
        if names & panes:
            w, h = (int(v) for v in spec["size"].split("x"))
            assert w > standin_e2e.STANDIN_SIZE[0] + 400 and w <= display[0] and h <= display[1] - 60, group
        else:
            assert spec["size"] == "", group
    run = _step("standin", "Run: tools/standin_e2e.py")
    assert run["env"]["ROLE"] == "${{ matrix.role }}" and run["env"]["STANDIN_SIZE"] == "${{ matrix.size }}"
    for line in ("if ($env:ROLE -eq 'editing') { $arguments += @('--editing') }",
                 "if ($env:STANDIN_SIZE) { $arguments += @('--standin-size', $env:STANDIN_SIZE) }"):
        assert line in run["run"], line
    assert standin_e2e.parse(["--editing", "--standin-size", "1900x1000"]).editing
    verdict = _step("standin", "The verdict")
    assert verdict["env"]["ROLE"] == "${{ matrix.role }}" and "--role $env:ROLE" in verdict["run"]
    # e turns back to the pages d translated: never alone, never without d
    assert any(standin_e2e.wanted(s["scenarios"])[:2] == ["d", "e"] for s in groups.values())
    choice = _on(_workflow())["workflow_dispatch"]["inputs"]["groups"]["description"]
    assert ",".join(groups) in choice
    run = _step("standin", "Run: tools/standin_e2e.py")
    for flag in ("'--start-ollama', $env:OLLAMA_PORT", "'--seed', '1'", "'--timeout', $env:SCENARIO_TIMEOUT",
                 "'--cancel-soft-ms', $env:CANCEL_SOFT_MS", "'--scenario', $env:SCENARIOS",
                 "if ($env:WAIT_DONE -ne '0') { $arguments += @('--wait-done', $env:WAIT_DONE) }"):
        assert flag in run["run"], flag
    assert "'--canned'" not in run["run"] and run["env"]["SCENARIOS"] == "${{ matrix.scenarios }}"
    bench = _step("benchmark", "Run: tools/openmantra_eval.py")["run"]
    for flag in ("'--series', $env:SERIES", "'--seed', '1'", "'--start-ollama', $env:OLLAMA_PORT",
                 "'--detect-model', $env:DETECT_MODEL"):
        assert flag in bench, flag
    assert "--dump" not in bench and "--scan" not in bench and "--geometry-scan" not in bench  # (text, masks)
    assert _workflow()["env"]["OLLAMA_PORT"] not in ("11434", "")
    # each job's verdict is its exit code: the summary's --check
    for job, words in (("standin", "summarise.py standin"), ("benchmark", "summarise.py bench")):
        verdict = _step(job, "The verdict")
        assert verdict["if"] == "always()" and words in verdict["run"] and "--check" in verdict["run"]
        assert "exit $code" in verdict["run"]
    assert "--timeout $env:SCENARIO_TIMEOUT" in _step("standin", "The verdict")["run"]


def test_scenario_k_runs_once_in_a_short_form_its_rests_never_held():
    import standin_e2e

    groups = {g: s["scenarios"] for g, s in _groups().items()}
    with_k = [g for g, s in groups.items() if "k" in s.split(",")]
    assert len(with_k) == 1 and with_k[0].split("-")[-3:] == ["k5", "k1", "k2"], with_k
    run = _step("standin", "Run: tools/standin_e2e.py")["run"]
    short = "if (($env:SCENARIOS -split ',') -contains 'k') { $arguments += @('--k-turns', '6', '--k-read', '3') }"
    assert short in run and run.index("$arguments = @(") < run.index(short) < run.index("& $env:PY @arguments")
    args, tools = standin_e2e.parse(["--scenario", groups[with_k[0]], "--k-turns", "6", "--k-read", "3"]), \
        standin_e2e.parse([])
    assert (args.k_turns, args.k_read, args.k_read_ms) == (6, 3, standin_e2e.K_READ_MS)
    assert args.k_turns < tools.k_turns and tools.k_read == 0  # (the tool's own form: 20, and all of them read back)
    # (--wait-done holds no rest of k: its rests are its pace; each pace waits for the backlog to empty instead)
    assert not set(standin_e2e.K_PACES) & set(standin_e2e.HOLD_SCENARIOS)

    def scripted_s(turns: int, read: int) -> float:
        names = standin_e2e.wanted(groups[with_k[0]])
        segments, _ = standin_e2e.build_plan(names, 200, 0, 700, 90.0, {"turns": turns, "read": read or turns})
        waits = [s for seg in segments if seg.name in standin_e2e.K_PACES for s in seg.steps if s.startswith("w")]
        return sum(int(s[1:].split("-")[0]) for s in waits) / 1000

    # the stand-in's own waits in k: under two minutes for the three paces, against near ten in the tool's form
    assert scripted_s(6, 3) == 117.0 and scripted_s(20, 0) == 574.0


def _run_step(job: str, name_part: str, env: dict[str, str], tmp_path: Path) -> tuple[int, str, dict[str, str]]:
    """A step's script run in PowerShell 7 with the helpers it would dot-source stood in for (nothing is looked up,
    downloaded or started): its exit code, its output and what it wrote to GITHUB_OUTPUT."""
    import os

    stubs = ("function Resolve-OllamaRelease([string]$Asked) { return [ordered]@{ tag = $(if ($Asked -eq 'latest') "
             "{ 'v9.9.9' } else { $Asked }) } }\nfunction Set-Fact($Name, $Value) { }\n"
             "function Get-MachineFacts { return @{} }\n")
    script = _step(job, name_part)["run"].replace(". .github/gpu-checks/helpers.ps1\n", stubs)
    assert "helpers.ps1" not in script
    path = tmp_path / "step.ps1"
    path.write_text(script, "utf-8")
    output = tmp_path / "output.txt"
    output.write_text("", "utf-8")
    full = {**os.environ, **{k: v for k, v in _workflow()["env"].items() if "${{" not in str(v)},
            "GITHUB_OUTPUT": str(output), **env}
    r = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-File", str(path)], capture_output=True, text=True,
                       timeout=120, stdin=subprocess.DEVNULL, env=full)
    outputs = dict(line.split("=", 1) for line in output.read_text("utf-8").splitlines() if "=" in line)
    return r.returncode, r.stdout + r.stderr, outputs


@needs_pwsh
def test_the_plan_gives_the_jobs_asked_for(tmp_path):
    base = {"CHECKS": "both", "WANTED_GROUPS": "all", "WANTED_TITLES": "all", "OLLAMA_VERSION": "v0.40.17",
            "MODELS_HASH": "m" * 64, "TRANSLATOR_HASH": "t" * 64, "PIP_HASH": "p" * 64}
    code, said, out = _run_step("prepare", "Which checks", base, tmp_path)
    assert code == 0, said
    assert json.loads(out["standin_matrix"]) == [{"group": g, **s} for g, s in _groups().items()]
    assert json.loads(out["titles"]) == [1, 2, 3, 4, 5]
    assert (out["standin"], out["benchmark"]) == ("true", "true")
    assert out["program_key"] == "ollama-program-v0.40.17-windows-amd64"
    assert out["store_key"] == "ollama-store-v0.40.17-" + "t" * 16
    assert (out["models_key"], out["pip_key"]) == ("models-" + "m" * 64, "pip-Windows-py3.13-" + "p" * 64)
    code, said, out = _run_step("prepare", "Which checks", {**base, "CHECKS": "stand-in", "WANTED_GROUPS": "d-e-x-f2",
                                                            "WANTED_TITLES": "3"}, tmp_path)
    assert code == 0, said
    assert json.loads(out["standin_matrix"]) == [{"group": "d-e-x-f2", "scenarios": "d,e,x,f2", "role": "reader",
                                                  "size": ""}]  # (an array of one)
    assert (out["standin"], out["benchmark"], json.loads(out["titles"])) == ("true", "false", [3])
    code, said, out = _run_step("prepare", "Which checks", {**base, "CHECKS": "benchmark", "WANTED_TITLES": "5, 1,1",
                                                            "OLLAMA_VERSION": "latest"}, tmp_path)
    assert code == 0, said
    assert (out["standin"], out["benchmark"], json.loads(out["titles"])) == ("false", "true", [1, 5])
    assert out["program_key"] == "ollama-program-v9.9.9-windows-amd64"
    code, said, out = _run_step("prepare", "Which checks", {**base, "CHECKS": "none"}, tmp_path)
    assert code == 0 and (out["standin"], out["benchmark"]) == ("false", "false"), said
    for wrong in ({"CHECKS": "all"}, {"WANTED_GROUPS": "c-a-b,q"}, {"WANTED_TITLES": "6"}, {"WANTED_TITLES": "1;2"}):
        code, said, out = _run_step("prepare", "Which checks", {**base, **wrong}, tmp_path)
        assert code != 0 and not out, wrong


@needs_pwsh
def test_a_ci_branch_without_mains_caches_stops_at_once_and_says_what_to_run(tmp_path):
    found = {"PROGRAM": "true", "STORE": "true", "MODELS": "true", "PIP": "true"}
    ci = {"GITHUB_REF": "refs/heads/ci/some-work", "CHECKS": "both"}
    assert _run_step("prepare", "The caches a run on main makes", {**found, **ci}, tmp_path)[0] == 0
    code, said, _ = _run_step("prepare", "The caches a run on main makes", {**found, **ci, "STORE": ""}, tmp_path)
    assert code == 1 and "::error title=Caches::not in main's caches: store." in said
    code, said, _ = _run_step("prepare", "The caches a run on main makes", {**found, **ci, "PIP": "false"}, tmp_path)
    assert code == 0 and "::notice title=Caches::" in said  # (pip's downloads: only slower)
    nothing = {k: "" for k in found}
    assert _run_step("prepare", "The caches a run on main makes",
                     {**nothing, "GITHUB_REF": "refs/heads/main", "CHECKS": "both"}, tmp_path)[0] == 0
    assert _run_step("prepare", "The caches a run on main makes", {**nothing, **ci, "CHECKS": "none"}, tmp_path)[0] == 0


def test_plamos_licence_is_agreed_in_the_import_step_only_with_install_ps1s_exact_sentence():
    plamo = _install_ps1("PlamoConsentVar")
    assert plamo == "TASLATION_AGREE_PLAMO_LICENCE"
    wf = _workflow()
    assert plamo not in wf["env"] and all(plamo not in (job.get("env") or {}) for job in wf["jobs"].values())
    with_consent = [s for job in wf["jobs"] for s in _steps(job, wf) if plamo in (s.get("env") or {})]
    step = _step("prepare", "Import the translation model", wf)
    assert with_consent == [step]
    assert step["env"][plamo] == _install_ps1("PlamoConsentText") == "I agree to the PLaMo Community License"
    assert "--plamo-agreed TASLATION_AGREE_PLAMO_LICENCE" in step["run"]
    assert "-cne 'I agree to the PLaMo Community License'" in step["run"]
    # only on main, and only when the store is not kept already
    assert step["if"] == f"{ON_MAIN} && steps.store.outputs.cache-hit != 'true'"
    assert "TASLATION_AGREE_OCR_LICENCE" not in WORKFLOW.read_text("utf-8")  # (the models as tests.yml: --agreed)
    text = WORKFLOW.read_text("utf-8")
    above = text[:text.index(f"{plamo}: ")]
    above = above[above.rindex("env:"):]
    assert "The repository owner has read the licence below and agrees to it" in above
    assert "non-commercial" in above and "https://plamo.preferredai.jp/info/plamo-community-license-en" in above


def test_no_cache_and_no_artifact_holds_the_dataset_or_a_picture():
    forbidden = ("dataset", "openmantra", "shots", ".png", ".jpg", ".taslation", "taslation-state", "plamo-download")
    kept: list[str] = []
    wf = _workflow()
    for job in wf["jobs"]:
        for step in _steps(job, wf):
            uses = step.get("uses", "")
            if uses.startswith(("actions/cache", "actions/upload-artifact")):
                kept += [p.strip() for p in str(step["with"]["path"]).splitlines() if p.strip()]
    assert kept and all(not any(f in p.lower() for f in forbidden) for p in kept), kept
    caches = {s["with"]["path"] for job in wf["jobs"] for s in _steps(job, wf)
              if s.get("uses", "").startswith("actions/cache")}
    assert caches == {"~/AppData/Local/Programs/Ollama", "~/.ollama/models", "models", "~/AppData/Local/pip/Cache"}
    # the artifacts are named files (numbers only), never a folder that could hold the tool's pictures
    for job in ("standin", "benchmark"):
        upload = _step(job, "Keep the numbers", wf)
        paths = [p.strip() for p in upload["with"]["path"].splitlines() if p.strip()]
        assert all(re.search(r"/(summary\.json|summary\.md|facts\.json|console\.txt|report\.json|results\.json)$", p)
                   for p in paths), paths
        assert upload["if"] == "always()"
    assert _step("prepare", "Keep the facts", wf)["with"]["path"].endswith("/gpu-checks/facts.json")
    # the dataset comes from its publisher in each job that reads it
    for job in ("standin", "benchmark"):
        assert sum("tools/fetch_openmantra.py" in s.get("run", "") for s in _steps(job, wf)) == 1
    assert "fetch_openmantra" not in json.dumps(wf["jobs"]["prepare"])


def test_the_helpers_it_names_are_there_ascii_and_parse():
    text = WORKFLOW.read_text("utf-8")
    named = set(re.findall(r"\.github[/\\]gpu-checks[/\\](\w[\w-]*\.\w+)", text))
    assert named == {"helpers.ps1", "summarise.py", "benchmark-expected.json"}
    assert all((HELPERS / name).is_file() for name in named)
    for path in (WORKFLOW, TESTS, *HELPERS.iterdir()):
        if path.is_file():
            assert all(b < 128 for b in path.read_bytes()), path.name
    helpers = (HELPERS / "helpers.ps1").read_text("ascii")
    used = set(re.findall(r"\b((?:Get|Set|Resolve|Save|Install|Stop)-[A-Z]\w+)\b", text))
    for name in used - {"Set-Content", "Get-Content", "Get-ChildItem", "Get-Item", "Set-Location"}:
        assert f"function {name}" in helpers, name
    assert "trial" not in text.lower() and "trial" not in helpers.lower()


@needs_pwsh
def test_every_step_and_the_helpers_parse_in_powershell_7(tmp_path):
    scripts = [HELPERS / "helpers.ps1"]
    for workflow in (_workflow(), _load(TESTS)):
        for job in workflow["jobs"]:
            for i, step in enumerate(_steps(job, workflow)):
                if "run" in step:  # (an expression is put in by GitHub before PowerShell reads the script)
                    scripts.append(tmp_path / f"{len(scripts):02d}-{job}{i:02d}.ps1")
                    scripts[-1].write_text(re.sub(r"\$\{\{[^}]*\}\}", "0", step["run"]), "utf-8")
    command = "; ".join(
        f"$t = $null; $e = $null; $null = [System.Management.Automation.Language.Parser]::ParseFile('{p}', [ref]$t, "
        f"[ref]$e); foreach ($x in $e) {{ '{p.name}: ' + $x.Message }}" for p in scripts)
    r = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True,
                       encoding="utf-8", errors="replace", timeout=120, stdin=subprocess.DEVNULL)
    assert r.returncode == 0 and r.stdout.strip() == "", r.stdout + r.stderr


def test_the_summary_reads_the_tools_own_lines():
    s = _summarise()
    import standin_e2e

    assert (s.REST_MS, s.STALE_MS) == (standin_e2e.REST_MS, standin_e2e.STALE_MS)
    assert (s.K_PACES, s.K_STAYED_MS) == (tuple(standin_e2e.K_PACES), standin_e2e.K_STAYED_MS)
    source = (ROOT / "tools" / "standin_e2e.py").read_text("utf-8")
    assert 'print(f"run stopped: {why}", file=sys.stderr, flush=True)' in source
    # scenario k's fields as the tool writes them (`k_block`, `told_states`, `wasted_requests`, the request list)
    for words in ('"frames_held_after_read_most":', '"bytes_at_end":', '"left_working":', '"read_back_caught_no_new_read":',
                  '"why": why, "frame": r["frame"], "gate": r["gate"]', 'return "dropped"', '"side": getattr(',
                  '"scenario_k": k_facts', '"request_list": request_list'):
        assert words in source, words
    for why in s.LEFT_FAULTS:  # (standin_e2e.left_why's words)
        assert f'"{why}"' in source, why
    assert s.console_facts("x\nrun stopped: the stand-in browser ended\n")["stopped"] == "the stand-in browser ended"
    ev = (ROOT / "tools" / "openmantra_eval.py").read_text("utf-8")
    assert "f\"  {page.series} p{page.index}: gold {row['gold']}, candidates" in ev
    assert ('log(f"  {series}: page {done}/{len(pages)} translated, {lines} lines so far, '
            '{time.monotonic() - t0:.0f} s")') in ev
    console = ("OCR model loaded in 3.1 s\n"
               "  some_title p1: gold 9, candidates 12 (9 matched), read as text 10 (9 matched)  [4.5 s]\n"
               "  some_title p2: gold 3, candidates 4 (3 matched)  [2.0 s]\n"
               "run 1/1, official arm, seed 1\n  some_title: page 1/8 translated, 9 lines so far, 70 s\n"
               "  some_title: page 2/8 translated, 12 lines so far, 300 s\n")
    progress = s.bench_progress(console)
    assert progress == {"pages_read": 2, "detection_ocr_s": 6.5,
                        "translation": {"pages_done": 2, "pages": 8, "lines": 12, "seconds": 300,
                                        "seconds_all_at_this_pace": 1200}}
    assert s.bench(None, console, {}, "3")["verdict"] == "no results"


def _report(**run) -> dict:
    turns = [
        {"n": 0, "segment": "c", "t_s": 2.0, "rest_ms": 1200, "finished_ms": None, "page": 0, "spread": True,
         "why": "first"},
        {"n": 1, "segment": "c", "t_s": 9.0, "rest_ms": 8000, "finished_ms": 7000, "at_rest": "translated",
         "at_rest_from": "sharp", "page": 2, "spread": True, "why": "next", "requests": 3},
        {"n": 2, "segment": "a", "t_s": 20.0, "rest_ms": 7000, "finished_ms": 9000, "at_rest": "untranslated",
         "page": 4, "spread": True, "why": "next", "requests": 2},
        {"n": 3, "segment": "a", "t_s": 27.0, "rest_ms": 7000, "finished_ms": 5000, "at_rest": "translated",
         "at_rest_from": "sharp", "page": 6, "spread": True, "why": "next", "requests": 4},
        {"n": 4, "segment": "x", "t_s": 40.0, "rest_ms": 5000, "finished_ms": 4000, "at_rest": "translated",
         "at_rest_from": "sharp", "page": 8, "spread": True, "why": "jump", "requests": 1},
    ]
    segments = [
        {"segment": "c", "turns": 2, "rested": 1, "translated_at_rest": 1, "finished_ms_median": 7000,
         "finished_ms_max": 7000, "stale": 0, "not_following": 0, "jobs": 2, "requests": 4, "wasted_requests": 1},
        {"segment": "a", "turns": 2, "rested": 2, "translated_at_rest": 1, "finished_ms_median": 7000,
         "finished_ms_max": 9000, "stale": 1, "not_following": 2, "jobs": 3, "requests": 9, "wasted_requests": 0},
        {"segment": "x", "turns": 1, "rested": 1, "translated_at_rest": 1, "stale": 0, "not_following": 0},
    ]
    base = {"failed": "", "seconds": 300.0, "ready_s": 5.0, "captures": {"sharp": 400, "soft": 30, "black": 4},
            "capture_route": {"route": "Windows.Graphics.Capture", "looks": {"frames": 420, "none": 3},
                              "used": "Windows.Graphics.Capture"},
            "released": {"c": {"waited_s": 1.0, "timed_out": False}, "a": {"waited_s": 20.0, "timed_out": False}},
            "segments": segments, "turns": turns, "guard": {"refused": [], "only_the_stand_in_chosen": True},
            "jobs": {"started": 5, "on": {"sharp": 5}, "kept_from_unsettled_frames": [],
                     "on_black_spinner_unknown_shown": 0,
                     "soft_frames_at_end": {"left_in_the_cache": 0, "left": []}},
            "cancels": {"page_still_on_show": [], "by_segment": {"a": 1},
                        "list": [{"t_s": 21.0, "page_on_show": False}]},
            "cancel_in_flight": {"soft_ms": 700, "requests_on_soft": 0, "cancelled_in_flight": 0},
            "wasted_requests": {"count": 1, "by_segment": {"x": 1}}, "errors": {"hooks": {}},
            "requests": {"total": 13},
            "incidents": {"stale_overlays": [{"from_s": 22.0, "seen_ms": 420}]},
            "ocr": {"placements": [{"engines": ["cpu"], "t": 1.0}]}}
    base.update(run)
    return {"scenarios": ["c", "a", "x"], "translator": "real (the server TASlation starts)", "browser": "chrome",
            "pages": "dataset", "run": base,
            "cleanup": {"log": {"lines": {}, "exception_types": {}}, "state_deleted": True,
                        "cache_pages_incomplete": 2},
            "server_started": {"setup": {"full_window": True, "cache_ram": "256"}, "stopped": True}}


def _failed(out: dict) -> list[str]:
    return [c["criterion"] for c in out["failed"]]


def test_a_stand_in_run_passes_on_its_criteria_of_correctness_with_its_slowness_beside_them(tmp_path):
    s = _summarise()
    facts = {"run": {"exit_code": 0, "seconds": 320.5}, "screen": {"after": "1920x1080 at 32 bit, 60 Hz"}}
    out = s.standin(_report(), "", facts, "c", 600)
    assert out["verdict"] == "pass" and out["failed"] == [] and out["criteria"] >= 20, _failed(out)
    assert out["run"] == "works" and out["exit_code"] == 0 and out["ocr_devices"] == ["cpu"]
    assert out["meaning"]["c"] == "holds: 1 of 2 turns came before the window was ready"
    assert out["meaning"]["a"] == "partly: 1 of 2 rested turns translated at rest"
    assert out["meaning"]["x"].startswith("lost: no request on the soft frame, within --cancel-soft-ms (700 ms)")
    # what depends on the computer's speed: reported, never a failure
    assert out["speed"] == {"rested turns not finished within their rest": 1,
                            "rested turns not translated at rest": 1,
                            "spells the window did not follow the stand-in (over 1 s)": 2,
                            "lettering of a page left on show over 1 s, until the window captured the new one": 1,
                            "jobs cancelled as the reader turned away": 1,
                            "pages left half done in the cache at the end": 2}
    a = next(r for r in out["segments"] if r["scenario"] == "a")
    assert a["finished_within_rest"] == 1 and a["rest_ms_median"] == 7000
    md = s.standin_md(out)
    assert "### Stand-in c: PASS" in md and "| a | 2 | 2 (7000) | 1 | 1 | - |" in md
    assert f"* correctness: {out['criteria']} of {out['criteria']} criteria hold" in md
    assert "* speed (reported, never a failure): " in md
    # the command writes both files and exits 1 only with --check on a failure
    report = tmp_path / "report.json"
    report.write_text(json.dumps(_report()), encoding="utf-8")
    (tmp_path / "facts.json").write_text(json.dumps(facts), encoding="utf-8-sig")  # (PowerShell may write a BOM)
    args = ["standin", str(report), "--facts", str(tmp_path / "facts.json"), "--group", "c", "--out",
            str(tmp_path / "out"), "--timeout", "600"]
    assert s.main([*args, "--check"]) == 0
    assert json.loads((tmp_path / "out" / "summary.json").read_text("utf-8"))["run_step_s"] == 320.5
    report.write_text(json.dumps(_report(captures={"black": 9})), encoding="utf-8")
    assert s.main(args) == 0 and s.main([*args, "--check"]) == 1
    assert s.main(["standin", str(tmp_path / "none.json"), "--group", "c", "--out", str(tmp_path / "o2"),
                   "--check"]) == 1


def test_a_stand_in_run_fails_on_a_fault_and_only_on_one():
    s = _summarise()
    fails = {
        "the window captured the stand-in's frames": {"captures": {"black": 9}},
        "the guard refused no call": {"failed": "a call was refused: capture_screen_rect",
                                      "guard": {"refused": ["capture_screen_rect"], "only_the_stand_in_chosen": True}},
        "no request sent for nothing (outside scenario x, whose point they are)":
            {"wasted_requests": {"count": 3, "by_segment": {"a": 2, "x": 1}}},
        "no lettering of a page the stand-in had left on show over 1 s after the window captured the new one":
            {"incidents": {"stale_overlays": [{"from_s": 22.0, "seen_ms": 1500}]}},
        "no rested page left unfinished with the window at rest (--wait-done)":
            {"waits": {"holds": [{"segment": "a", "page": 4, "why": "idle", "waited_ms": 3000}]}},
        "nothing left in the cache from a frame that was not the sharp one where the sharp frame came in time to "
        "take it back": {"jobs": {"on_black_spinner_unknown_shown": 0, "kept_from_unsettled_frames": [],
                                  "soft_frames_at_end": {"left_in_the_cache": 1, "left": [
                                      {"t_s": 21.0, "page": 4, "why": "put back, yet left"}]}}},
        "no job cancelled while its page was on show": {"cancels": {"page_still_on_show": [{"t_s": 21.0}]}},
        f"a request cancelled in flight ended within {s.RAN_ON_MS} ms of its job's cancel":
            {"cancel_in_flight": {"soft_ms": 700, "requests_on_soft": 2, "cancelled_in_flight": 2,
                                  "ran_on_after_cancel_ms": {"max": 6000}}},
        "a page translated at rest came back without a request": {"turns": [
            *_report()["run"]["turns"][:4],
            {"n": 4, "segment": "x", "t_s": 40.0, "rest_ms": 5000, "page": 2, "spread": True, "why": "previous",
             "requests": 2, "at_rest": "translated", "at_rest_from": "sharp"}]},
    }
    for criterion, run in fails.items():
        out = s.standin(_report(**run), "", {}, "c", 600)
        assert out["verdict"] == "fail" and criterion in _failed(out), (criterion, _failed(out))
    assert s.standin(_report(captures={"black": 9}), "", {}, "c")["run"] == "no frames"
    # the window not at rest within --timeout is a hang (no scenario is released early since 2.0.0: no mode to wait for)
    hung = s.standin(_report(released={"a": {"waited_s": 600.2, "timed_out": True}}), "", {}, "c", 600)
    assert hung["verdict"] == "fail" and any(c.startswith("the window came to rest") for c in _failed(hung))
    assert not any("mode" in key for key in hung["speed"])
    report = _report()
    report["server_started"] = None  # (no server of its own: the canned translator, or one already running)
    assert s.standin(report, "", {}, "c", 600)["verdict"] == "pass"
    report = _report()
    report["server_started"]["stopped"] = False
    assert "the Ollama TASlation started was stopped at the end" in _failed(s.standin(report, "", {}, "c"))
    report = _report()
    report["cleanup"]["log"]["exception_types"] = {"RuntimeError": 1}
    assert "no traceback, error or exception in the window's log" in _failed(s.standin(report, "", {}, "c"))
    # what is speed stays speed: a hold at its cap, a sharp frame too late, lettering left until the next capture
    fine = {"waits": {"cap_s": 90, "holds": [{"segment": "a", "page": 4, "why": "cap", "waited_ms": 90000},
                                             {"segment": "a", "page": 6, "why": "finished", "waited_ms": 3000}]},
            "jobs": {"on_black_spinner_unknown_shown": 0, "kept_from_unsettled_frames": [5],
                     "soft_frames_at_end": {"left_in_the_cache": 1, "left": [
                         {"t_s": 21.0, "page": 4, "why": "later than the open time"}]}}}
    out = s.standin(_report(**fine), "", {}, "c", 600)
    assert out["verdict"] == "pass", _failed(out)
    assert out["speed"]["holds of --wait-done that reached their cap"] == 1
    assert out["speed"]["left in the cache from a frame not the sharp one, its sharp frame too late to take it "
                        "back (by why)"] == {"later than the open time": 1}
    assert out["segments"][1]["holds_by_why"] == {"cap": 1, "finished": 1}
    # x's soft frames kept until the window asked (--wait-done): what it keeps of them is the design's
    kept = {"waits": {"cap_s": 90, "holds": [], "keeps": [{"segment": "x", "why": "asked", "asked_ms": 1800}]},
            "jobs": {"on_black_spinner_unknown_shown": 0, "kept_from_unsettled_frames": [],
                     "soft_frames_at_end": {"left_in_the_cache": 1, "left": [
                         {"t_s": 41.0, "page": 8, "why": "put back, yet left"}]}}}
    assert s.standin(_report(**kept), "", {}, "c", 600)["verdict"] == "pass"
    assert "its soft frames kept until the window asked (1 of 1)" in s.standin(_report(**kept), "", {}, "c")[
        "meaning"]["x"]
    del kept["waits"]
    assert s.standin(_report(**kept), "", {}, "c", 600)["verdict"] == "fail"  # (without --wait-done it is judged)
    gone = s.standin(None, "Traceback (most recent call last):\n  x\nOSError: boom\n", {}, "c")
    assert gone["verdict"] == "no report" and gone["console"]["exception_types"] == {"OSError": 1}
    assert _failed(gone) == ["the tool wrote its report"]


def test_the_tab_resize_slide_and_behind_scenarios_fail_on_what_their_rule_forbids_and_only_on_it():
    s = _summarise()

    def failed(judge, run: dict, names: list[str]) -> tuple[list[str], int]:
        found: list[tuple[str, bool]] = []
        judge(run, names, lambda _scenario, criterion, ok, seen=None: found.append((criterion, bool(ok))))
        return [c for c, ok in found if not ok], len(found)

    # another tab shown: nothing read, asked, stored or learnt of it, no lettering or mouse over it a second after its
    # title came, the right pane's line; the book's tab followed into its own window (its page areas its own there)
    switch = {"segment": "tab1", "kind": "switch", "lettering_over_the_other_tab_last_ms": 40,
              "mouse_over_the_other_tab_last_ms": None, "memory_titles_added": 0, "book_changed": False,
              "page_areas_changed": False, "right_pane_line_shown": True}
    out = {**switch, "segment": "tab6", "kind": "out", "followed_the_book_s_window_ms": 500, "page_areas_changed": True,
           "right_pane_line_shown": False}

    def tabs(*spells: dict, **more) -> dict:
        return {"tabs": {"spells": list(spells), "jobs_on_the_other_tab": {"made": 0, "requests": 0, "stored": 0},
                         "memory_holds_an_other_tab_title": False, "chosen_by_the_other_tab_s_title": False, **more}}

    assert failed(s._tab_correctness, tabs(switch, out), ["tab1", "tab6"]) == ([], 11)
    assert failed(s._tab_correctness, tabs(switch), ["c"]) == ([], 0)  # (no tab scenario: nothing judged)
    faults = {
        "no page job made on a frame of the other tab, nothing asked or stored for it":
            tabs(switch, jobs_on_the_other_tab={"made": 1, "requests": 0, "stored": 0}),
        "nothing of the other tab's title learnt in the viewer's memory, the window never chosen by it":
            tabs(switch, memory_holds_an_other_tab_title=True),
        f"no lettering and no mouse taken over the other tab's page {s.TAB_AFTER_TITLE_MS} ms after its title came":
            tabs({**switch, "mouse_over_the_other_tab_last_ms": 1200}),
        "nothing learnt and the book's name kept while the other tab showed (and its page areas, the tab back in the "
        "same window)": tabs({**switch, "page_areas_changed": True}),
        "the right pane said in one line that the window shows another tab":
            tabs({**switch, "right_pane_line_shown": False}),
        "the window followed the book's tab into its own window":
            tabs(switch, {**out, "followed_the_book_s_window_ms": None}),
        "the stand-in showed another tab": tabs(out),
        "the tool told the spells away from the book's tab": {"tabs": {"failed": "KeyError"}},
    }
    for criterion, run in faults.items():
        bad, _n = failed(s._tab_correctness, run, ["tab1", "tab6"] if "tab6" in str(run) else ["tab1"])
        assert bad == [criterion], (criterion, bad)
    assert s.meanings({"scenarios": ["tab1"], "run": {"tabs": {"spells": [{**switch, "away_ms": 6000,
                                                                          "back_to_lettered_ms": 280}]}}})[
        "tab1"].startswith("holds: another tab shown [6000] ms")

    # the window resized: no job or request while the button was held, no side pane outside the window, each pane back
    # at rest (or hidden for want of room)
    panes = {"left": {"outside_the_viewer_looks": 0, "at_end": "shown"},
             "right": {"outside_the_viewer_looks": 0, "at_end": "hidden: no room"}}
    drag = {"button": True, "jobs_started_while_pressed": 0, "requests_while_pressed": 0, "panes": panes}

    def resized(r1: dict, r5: dict | None = None, step: dict | None = None) -> dict:
        return {"monitors": {"places": [{"segment": "r1", "step": step or {}, "resize": r1},
                                        {"segment": "r5", "step": {}, "resize": r5 or {
                                            **drag, "button": False, "jobs_started_while_pressed": 2}}]}}

    assert failed(s._resize_correctness, resized(drag), ["r1", "r5"]) == ([], 8)
    for criterion, run in {
        "no page job started and nothing asked while the button was held":
            resized({**drag, "requests_while_pressed": 1}),
        "no side pane outside the viewer's window": resized(drag, {**drag, "button": False, "panes": {
            **panes, "left": {"outside_the_viewer_looks": 2, "at_end": "shown"}}}),
        "each side pane back at rest (or hidden for want of room beside the page)": resized({**drag, "panes": {
            **panes, "right": {"outside_the_viewer_looks": 0, "at_end": "hidden: sizing"}}}),
        "the step was done to the stand-in's window": resized(drag, step={"refused": "no such place"}),
    }.items():
        assert failed(s._resize_correctness, run, ["r1", "r5"])[0] == [criterion], criterion

    # the page slid with the pointer: no side pane hidden (but by the window's closing at the end of the run)
    def slid(*spells: list) -> dict:
        rows = [{"dir": "r", "hidden_spells_ms_from_press": []},
                {"dir": "l", "hidden_spells_ms_from_press": list(spells)}]
        return {"see_through": {"slides": {"slides": rows, "error": None}}}

    assert failed(s._slide_correctness, slid(["left", 13085, None, "closed"]), ["s"]) == ([], 2)
    assert failed(s._slide_correctness, slid(["right", 300, 900, "turn"]), ["s"])[0] == [
        "no side pane hidden on a slide (from its press until 10 s after its release)"]
    assert failed(s._slide_correctness, {"see_through": {}}, ["s"])[0] == ["the tool told the slides"]

    # a start behind another window: both panes on the screen once the stand-in is back in sight, and there they stay
    behind = {"behind": {"behind": {"made": True, "ended_t": 8171}, "panes_back_ms": 278, "panes_stayed": True}}
    assert failed(s._behind_correctness, behind, ["h"]) == ([], 3)
    assert failed(s._behind_correctness, {"behind": {**behind["behind"], "panes_stayed": False}}, ["h"])[0] == [
        "the side panes stayed on the screen"]
    assert failed(s._behind_correctness, {}, ["h"]) == (
        ["the stand-in was out of sight at the start and back in sight"], 1)


def test_a_group_s_role_is_judged_and_a_pane_s_criteria_say_why_it_was_hidden(tmp_path):
    s = _summarise()
    criterion = "the window was in {}, as the group says"
    # the role the group states: kept for the book, and the window's alone from its ready on (before the book's role
    # is known the window starts in the settings' own)
    reading = {"modes": {"columns": ["t_s", "role"], "rows": [[0.1, "translator"], [0.4, "reader"]]}}
    report = {**_report(**reading), "role_kept": "reader"}
    assert s.standin(report, "", {}, "c", 600, "reader")["verdict"] == "pass"
    assert criterion.format("Reader mode") not in _failed(s.standin(report, "", {}, "c", 600))  # (no role: none)
    assert _failed(s.standin(report, "", {}, "c-editing", 600, "editing")) == [criterion.format("editing")]
    later = {"modes": {"rows": [[0.1, "translator"], [0.4, "reader"], [30.0, "translator"]]}}
    assert _failed(s.standin({**_report(**later), "role_kept": "reader"}, "", {}, "c", 600, "reader")) == [
        criterion.format("Reader mode")]
    editing = {**_report(modes={"rows": [[0.1, "translator"]]}), "role_kept": "translator"}
    out = s.standin(editing, "", {}, "c-a-b-editing", 600, "editing")
    assert out["verdict"] == "pass" and out["role"] == "editing" and "; in editing" in s.standin_md(out)
    report_file = tmp_path / "report.json"
    report_file.write_text(json.dumps(editing), encoding="utf-8")
    assert s.main(["standin", str(report_file), "--group", "c-a-b-editing", "--role", "editing", "--out",
                   str(tmp_path / "out"), "--timeout", "600", "--check"]) == 0
    assert s.main(["standin", str(report_file), "--group", "c-a-b", "--role", "reader", "--out",
                   str(tmp_path / "out"), "--timeout", "600", "--check"]) == 1
    # e: a turn back lettered with nothing asked holds, from the cache or from the lines the window kept
    turns = [{"n": 5, "segment": "e", "t_s": 50.0, "page": 2, "spread": True, "why": "previous", "requests": 0,
              "cached": False, "first_lettered_ms": 300},
             {"n": 6, "segment": "e", "t_s": 55.0, "page": 0, "spread": True, "why": "previous", "requests": 2,
              "cached": False, "first_lettered_ms": 4000}]
    meaning = s.meanings({"scenarios": ["e"], "run": {"turns": turns}})["e"]
    assert meaning.startswith("holds: 1 of 2 turns back lettered with nothing asked"), meaning
    assert s.meanings({"scenarios": ["e"], "run": {"turns": turns[1:]}})["e"].startswith("lost: none of 1")
    # a side pane's criteria say why it was hidden (`standin_seethrough.SeeWatch.pane_report`'s hidden_why)
    whys = {"left": {"no room": 60}, "right": {"no room": 58, "covered": 2}}
    seen: dict[str, object] = {}
    run = {"see_through": {"panes": {"hidden_why": whys}, "slides": {"slides": [
        {"dir": "l", "hidden_spells_ms_from_press": [["left", None, None, "before"]]}], "error": None}},
        "behind": {"behind": {"made": True, "ended_t": 8171}, "panes_back_ms": None, "panes_stayed": False},
        "tabs": {"spells": [{"segment": "tab1", "kind": "switch", "right_pane_line_shown": False}],
                 "jobs_on_the_other_tab": {}}}

    def note(_scenario, criterion_, ok, seen_=None):
        if not ok:
            seen[criterion_] = seen_

    s._slide_correctness(run, ["s"], note)
    s._behind_correctness(run, ["h"], note)
    s._tab_correctness(run, ["tab1"], note)
    assert seen["no side pane hidden on a slide (from its press until 10 s after its release)"]["hidden_why"] == whys
    assert seen["both side panes on the screen once the stand-in was back in sight"]["hidden_why"] == whys
    assert seen["the right pane said in one line that the window shows another tab"] == {
        "shown": False, "right_pane_hidden": whys["right"]}
    # ... as the tool counts them, a look at a time (the hooks' why first, then the window's own)
    source = (ROOT / "tools" / "standin_seethrough.py").read_text("utf-8")
    assert '"hidden_why":' in source and "standin_monitors.watch_pane_whys(self)" in source


def test_lines_taken_back_are_reported_and_fail_a_run_only_when_something_of_them_stayed():
    s = _summarise()
    source = (ROOT / "tools" / "standin_e2e.py").read_text("utf-8")
    for key in ("final_from_taken_back", "early_left_at_close", "early_left_at_result", *s.STREAMED_KEYS):
        assert f'"{key}"' in source, key  # (the tool's `streamed_lines` writes them)
    assert '"streamed_lines": streamed' in source
    streamed = {"units": 6, "lines_sent_early": 20, "lines_stood": 18, "lines_taken_back": 2,
                "units_first_line_taken_back": 1, "units_any_taken_back": 2, "requests_taken_back": 2,
                "withdrawn_on_show_ms": {"n": 1, "median": 240, "max": 240},
                "final_from_taken_back": 0, "early_left_at_close": 0, "early_left_at_result": 0}
    criterion = ("nothing of a line taken back once its page was read stayed in the page's lines (and so in the "
                 "cache) or on show when the page was finished")
    out = s.standin(_report(streamed_lines=streamed), "", {}, "c", 600)
    assert out["verdict"] == "pass", _failed(out)
    assert out["streamed_lines"]["lines_taken_back"] == 2 and "final_from_taken_back" not in out["streamed_lines"]
    md = s.standin_md(out)
    assert "* lines sent as they were read (reported): 20 in 6 units, 18 stood, 2 taken back (a unit's first line " \
           "in 1), 2 requests thrown away; a taken-back lettering on show ms median/max 240/240" in md
    for key in ("final_from_taken_back", "early_left_at_close", "early_left_at_result"):
        out = s.standin(_report(streamed_lines={**streamed, key: 1}), "", {}, "c", 600)
        assert out["verdict"] == "fail" and _failed(out) == [criterion], (key, _failed(out))
    out = s.standin(_report(), "", {}, "c", 600)  # (a run without the stream: neither judged nor reported)
    assert out["streamed_lines"] is None and criterion not in [c["criterion"] for c in out["failed"]]


def test_the_backlog_s_work_computed_low_is_reported_and_any_other_request_computed_low_fails_a_run():
    s = _summarise()
    source = (ROOT / "tools" / "standin_e2e.py").read_text("utf-8")
    for key in (*s.PRIORITY_KEYS, "other_requests_low"):
        assert f'"{key}"' in source, key  # (the tool's `priority_report` writes them)
    assert '"server_priority": priority_report(notes, rel)' in source
    priority = {"lowered": 3, "not_lowered": 0, "set_back": 3, "processes_set_back": 6, "low_ms": 9100,
                "backlog_requests": 29, "backlog_requests_low": 29, "other_requests_low": []}
    criterion = "no request but the backlog's was computed while the server was lowered for the backlog's work"
    out = s.standin(_report(server_priority=priority), "", {}, "c", 600)
    assert out["verdict"] == "pass", _failed(out)
    assert out["server_priority"]["backlog_requests_low"] == 29 and "other_requests_low" not in out["server_priority"]
    assert ("* the backlog's work computed low (reported): 29 of 29 backlog requests; the server lowered 3 times "
            "(0 not), set back 3, low 9100 ms in all") in s.standin_md(out)
    seen = [{"t_s": 300.4, "side": None, "job": 13}]
    out = s.standin(_report(server_priority={**priority, "other_requests_low": seen}), "", {}, "c", 600)
    assert out["verdict"] == "fail" and _failed(out) == [criterion]
    out = s.standin(_report(), "", {}, "c", 600)  # (a tool before it: neither judged nor reported)
    assert out["server_priority"] is None and criterion not in [c["criterion"] for c in out["failed"]]


def test_a_job_that_gave_its_page_over_to_a_new_size_is_no_cancel_with_its_page_on_show():
    s = _summarise()
    # a change of the stand-in's size on a runner, as a tool before `resized_away` reported it: the job on the old
    # size's frame cancelled 2.3 s after the size changed, 1.3 s after the window's first capture of the new size
    cancel = {"id": 9, "t_s": 79.33, "segment": "f2", "frame": "sharp", "gate_end": "confirmed", "page_on_show": True,
              "resize_within_1s": False}
    run = {"cancels": {"page_still_on_show": [cancel], "list": [cancel]},
           "job_list": [{"id": 9, "t_s": 70.91, "size": [1904, 1072]}, {"id": 10, "t_s": 79.44, "size": [1904, 1024]}],
           "resizes": [{"from_s": 77.06, "size_before": [1904, 1072], "size_after": [1904, 1024],
                        "first_capture_ms": 934}]}
    criterion = "no job cancelled while its page was on show"
    assert s.standin(_report(**run), "", {}, "d-e-x-f2", 600)["verdict"] == "pass"
    for other in ({"resizes": []},  # no change of size
                  {"resizes": [{**run["resizes"][0], "first_capture_ms": 3000}]},  # the new size captured after it
                  {"resizes": [{**run["resizes"][0], "from_s": 60.0}]},  # a change before the job began
                  {"resizes": [{**run["resizes"][0], "size_before": [1904, 1024]}]},  # not from the job's size
                  {"cancels": {"page_still_on_show": [{**cancel, "resized_away": False}]}}):  # the tool's own word
        out = s.standin(_report(**{**run, **other}), "", {}, "d-e-x-f2", 600)
        assert out["verdict"] == "fail" and criterion in _failed(out), other
        assert next(c for c in out["failed"] if c["criterion"] == criterion)["seen"] == [79.33]


def _k_report(**run) -> dict:
    """`_report` with scenario k's three paces after it: each a turn to a fresh page, two pages flipped past and two
    read back, as the tool tells them; at 1 s a page two requests of a page job asked before its frame was confirmed
    and dropped as the page was flipped past (the window's design), at 2 s both pages caught and read back from what
    the backlog read."""
    report = _report()
    turns = list(report["run"]["turns"])
    t = 60.0
    for name in ("k5", "k1", "k2"):
        for why, rest in (("jump", 8000), ("next", 1000), ("next", 1000), ("jump", 8000), ("next", 8000)):
            turns.append({"n": len(turns), "segment": name, "t_s": t, "rest_ms": rest, "finished_ms": 3000,
                          "at_rest": "translated", "at_rest_from": "sharp", "page": 20 + len(turns), "spread": False,
                          "why": why, "requests": 1})
            t += rest / 1000
    pace = {"flips": 2, "stayed": 0, "caught": 0, "done_on_show": 0, "agree": 2, "read_back": 2,
            "read_back_caught": 0, "read_back_caught_no_new_read": 0, "drain_s": 0.0, "background_requests": 0,
            "first_lettered_read_back": {"n": 2, "median": 2100, "p90": 3000, "max": 3000}, "peak_mb": 0.0,
            "frames_held_after_read_most": 0, "bytes_at_end": 0}
    paces = {"k5": {**pace, "pace_ms": 500},
             "k1": {**pace, "pace_ms": 1000, "stayed": 1, "caught": 1, "read_back_caught": 1,
                    "read_back_caught_no_new_read": 1, "drain_s": 4.1, "background_requests": 6, "peak_mb": 2.4},
             "k2": {**pace, "pace_ms": 2000, "stayed": 2, "caught": 2, "read_back_caught": 2,
                    "read_back_caught_no_new_read": 2, "drain_s": 31.5, "background_requests": 14, "peak_mb": 5.0,
                    "first_lettered_read_back": {"n": 2, "median": 160, "p90": 470, "max": 470}}}
    dropped = [{"t_s": 77.2 + d, "segment": "k1", "job": 40, "why": "dropped", "frame": "sharp", "gate": "pending"}
               for d in (0.0, 0.1)]
    base = {"turns": turns, "released": {**report["run"]["released"], "end": {"waited_s": 35.0, "timed_out": False}},
            "scenario_k": {"paces": paces, "told": {"left_working": [], "done_told_working_again": 0}},
            "wasted_requests": {"count": 3, "by_segment": {"x": 1, "k1": 2},
                                "list": [{"t_s": 41.0, "segment": "x", "why": "soft", "gate": "none"}, *dropped]},
            "request_list": {"columns": ["t_s", "job", "side", "wasted"],
                             "rows": [[77.2, 40, None, "dropped"], [100.5, None, "backlog", None]]}}
    base.update(run)
    report["run"].update(base)
    report["scenarios"] = [*report["scenarios"], "k5", "k1", "k2"]
    return report


def test_scenario_k_is_judged_on_what_the_pages_turned_past_guarantee_and_its_figures_are_reported():
    s = _summarise()
    out = s.standin(_k_report(), "", {}, "k5-k1-k2", 600)
    assert out["verdict"] == "pass", _failed(out)
    k_criteria = [c for c in s.correctness(_k_report(), 600) if c["scenario"] in ("k5", "k1", "k2")]
    assert len(k_criteria) == 3 * 5 + 2  # (each pace: drawn, last page, told, requests, frames; at the end: two more)
    assert out["meaning"]["k5"].startswith("holds: 0 of 2 pages flipped past caught")
    assert out["meaning"]["k2"] == ("holds: 2 of 2 pages flipped past caught and 0 finished on show, 2 stayed 800 ms; "
                                    "2 of 2 caught pages read back begun with no new read")
    lost = _k_report(scenario_k={"paces": {**_k_report()["run"]["scenario_k"]["paces"], "k2": {
        **_k_report()["run"]["scenario_k"]["paces"]["k2"], "caught": 0, "agree": 0, "read_back_caught": 0,
        "read_back_caught_no_new_read": 0}}, "told": {"left_working": []}})
    assert s.standin(lost, "", {}, "k", 600)["meaning"]["k2"].startswith("lost: 0 of 2")  # (a meaning, no failure)
    assert s.standin(lost, "", {}, "k", 600)["verdict"] == "pass"
    figures = out["scenario_k"]
    assert figures["k2"]["drain_s"] == 31.5 and figures["k1"]["background_requests"] == 6
    md = s.standin_md(out)
    assert "Scenario k (reported, never a failure):" in md
    assert "| k2 (2000 ms) | 2 (2) | 2, 0 | 2 (2, 2) | 160/470 | 31.5 | 14 | 5.0 |" in md
    # the faults, each failing its own criterion and no other
    requests = ("every request sent for nothing was a page job's asked before its frame was confirmed and dropped as "
                "the page was flipped past (none on a frame that was not the sharp one, none of the backlog's)")
    base = _k_report()["run"]
    faults = {
        requests: [
            {"wasted_requests": {**base["wasted_requests"], "list": [
                *base["wasted_requests"]["list"], {"t_s": 66.0, "segment": "k5", "why": "soft", "gate": "pending"}]}},
            {"wasted_requests": {**base["wasted_requests"], "list": [
                *base["wasted_requests"]["list"][:2], {**base["wasted_requests"]["list"][2], "gate": "confirmed"}]}},
            {"request_list": {**base["request_list"], "rows": [*base["request_list"]["rows"],
                                                               [101.0, None, "backlog", "dropped"]]}},
            {"wasted_requests": {"count": 3, "by_segment": {"x": 1, "k1": 2}}}],  # (counts only: none told apart)
        "the backlog held no frame after it was read": [
            {"scenario_k": {**base["scenario_k"], "paces": {**base["scenario_k"]["paces"], "k1": {
                **base["scenario_k"]["paces"]["k1"], "frames_held_after_read_most": 1}}}}],
        "the backlog held nothing at the end of the run, the window at rest (0 bytes)": [
            {"scenario_k": {**base["scenario_k"], "paces": {**base["scenario_k"]["paces"], "k2": {
                **base["scenario_k"]["paces"]["k2"], "bytes_at_end": 2_400_000}}}}],
        "no screen was left told at work at the end of the run, the window at rest": [
            {"scenario_k": {**base["scenario_k"], "told": {"left_working": ["31:translate"]}}}],
        "the tool told the pace (its pages flipped past and read back)": [
            {"scenario_k": {**base["scenario_k"], "paces": {
                k: v for k, v in base["scenario_k"]["paces"].items() if k != "k1"}}}],
    }
    for criterion, runs in faults.items():
        for run in runs:
            got = _failed(s.standin(_k_report(**run), "", {}, "k", 600))
            assert got == [criterion], (criterion, got)
    # the window not at rest at the end: the hang fails, what the backlog held then is not judged
    hung = _k_report(released={**base["released"], "end": {"waited_s": 600.4, "timed_out": True}},
                     scenario_k={**base["scenario_k"], "told": {"left_working": ["31:translate"]}})
    got = _failed(s.standin(hung, "", {}, "k", 600))
    assert len(got) == 1 and got[0].startswith("the window came to rest before every scenario"), got
    # outside k a request sent for nothing still fails
    assert ("no request sent for nothing (outside scenario x, whose point they are)" in _failed(s.standin(
        _k_report(wasted_requests={"count": 1, "by_segment": {"a": 1}, "list": []}), "", {}, "k", 600)))


def _results(f1: float = 0.9705, cer: float = 0.0325, chrf: float = 38.01, pages: int = 54,
             series: str = "rasetugari", **more) -> dict:
    return {"tool": "openmantra_eval", "dataset": {"series": [series], "pages": pages},
            "settings": {"detect_model": "on"},
            "summary": {"all": {"f1": f1, "ocr_gold": {"corpus": cer}, "translation": {"chrf": chrf, "lines": 7}}},
            "translation": {"ollama": "0.40.17", "run_results": [{"speed": {"eval_tok_per_s": 7.5}}], **more},
            "seconds": {"detection_ocr": 100.0, "translation": 900.0, "total": 1000.0}}


def test_the_expected_benchmark_figures_are_the_runners_own_per_title():
    expected = json.loads((HELPERS / "benchmark-expected.json").read_text("utf-8"))
    titles = expected["titles"]
    assert sorted(titles) == ["1", "2", "3", "4", "5"] and expected["detect_model"] == "on"
    assert sum(t["pages"] for t in titles.values()) == expected["pooled"]["pages"]
    for part in ("title", "pooled"):
        assert sorted(expected["tolerance"][part]) == ["cer", "chrf", "f1"]
    for t in (*titles.values(), expected["pooled"]):
        assert 0 < t["f1"] <= 1 and 0 <= t["cer"] < 1 and 0 < t["chrf"] < 100
    runs = expected["measured"]["runs"]
    assert len(runs) == len(set(runs)) >= 2 and "runners" in expected["measured"]["note"]
    # the spread seen so far: each run's figures in the order of the runs, the first run's the expected ones, and
    # each within its tolerance (tightened only once more runs show the spread)
    for part, figures in (*(("title", t) for t in titles.values()), ("pooled", expected["pooled"])):
        tolerance = expected["tolerance"][part]
        assert sorted(figures["seen"]) == ["cer", "chrf", "f1"]
        for name, seen in figures["seen"].items():
            assert len(seen) == len(runs) and seen[0] == figures[name]
            assert all(abs(v - figures[name]) <= tolerance[name] + 1e-9 for v in seen), (part, name, seen)


def test_a_benchmark_title_fails_when_a_score_leaves_its_tolerance(tmp_path):
    s = _summarise()
    expected = json.loads((HELPERS / "benchmark-expected.json").read_text("utf-8"))
    out = s.bench(_results(), "", {}, "5", expected)
    assert out["verdict"] == "pass" and out["expected"]["compared"] and out["expected"]["ok"]
    near = s.bench(_results(f1=0.9705 - 0.009, cer=0.0325 + 0.004, chrf=38.01 + 1.9), "", {}, "5", expected)
    assert near["verdict"] == "pass"
    low = s.bench(_results(chrf=35.0), "", {}, "5", expected)
    assert low["verdict"] == "fail" and not low["expected"]["scores"]["chrf"]["ok"]
    assert "chrf 35.0 vs 38.01 (+-2.0) OUTSIDE" in s.bench_md(low)
    assert s.bench(_results(cer=0.05), "", {}, "5", expected)["verdict"] == "fail"
    # a run of fewer pages (--pages), another title or another detect_model is not compared
    short = s.bench(_results(pages=10, chrf=20.0), "", {}, "5", expected)
    assert short["verdict"] == "pass" and not short["expected"]["compared"]
    assert not s.bench(_results(series="another", chrf=20.0), "", {}, "5", expected)["expected"]["compared"]
    # a translation that did not complete fails whatever the scores
    assert s.bench(_results(error="boom"), "", {}, "5", expected)["verdict"] == "fail"
    path = tmp_path / "results.json"
    path.write_text(json.dumps(_results(chrf=35.0)), encoding="utf-8")
    args = ["bench", str(path), "--title", "5", "--out", str(tmp_path / "out")]
    assert s.main(args) == 0 and s.main([*args, "--check"]) == 1
    path.write_text(json.dumps(_results()), encoding="utf-8")
    assert s.main([*args, "--check"]) == 0


def test_the_run_table_has_each_jobs_minutes_both_verdicts_the_pooled_row_and_the_caches(tmp_path, capsys):
    s = _summarise()
    one = tmp_path / "artifacts" / "standin-c"
    one.mkdir(parents=True)
    (one / "summary.json").write_text(json.dumps(s.standin(_report(), "", {}, "c", 600)), encoding="utf-8")
    bad = tmp_path / "artifacts" / "standin-d"
    bad.mkdir(parents=True)
    (bad / "summary.json").write_text(json.dumps(s.standin(_report(captures={"black": 9}), "", {}, "d")), "utf-8")
    expected = json.loads((HELPERS / "benchmark-expected.json").read_text("utf-8"))
    two = tmp_path / "artifacts" / "benchmark-5"
    two.mkdir(parents=True)
    (two / "summary.json").write_text(json.dumps(s.bench(_results(), "", {}, "5", expected)), encoding="utf-8")
    prepare = tmp_path / "artifacts" / "prepare"
    prepare.mkdir(parents=True)
    (prepare / "facts.json").write_text(json.dumps({"ollama_tag": "v0.40.17", "found": {
        "program": True, "store": True, "models": True, "pip": False}}), encoding="utf-8-sig")
    jobs = tmp_path / "jobs.jsonl"
    job = {"name": "Stand-in c", "conclusion": "success", "created_at": "2026-11-22T10:00:00Z",
           "started_at": "2026-11-22T10:00:30Z", "completed_at": "2026-11-22T10:20:30Z",
           "steps": [{"name": "Set up: the packages", "conclusion": "success", "started_at": "2026-11-22T10:01:00Z",
                      "completed_at": "2026-11-22T10:04:00Z"},
                     {"name": "Run: tools/standin_e2e.py --scenario c", "conclusion": "success",
                      "started_at": "2026-11-22T10:08:30Z", "completed_at": "2026-11-22T10:19:30Z"}]}
    jobs.write_text(json.dumps(job) + "\n" + json.dumps({"name": "Summary", "steps": []}) + "\nnot json\n", "utf-8")
    caches = tmp_path / "caches.jsonl"
    caches.write_text("\n".join(json.dumps(c) for c in (
        {"key": "models-ab", "ref": "refs/heads/main", "size_in_bytes": 1_100_000_000},
        {"key": "ollama-store-v0.40.17-cd", "ref": "refs/heads/main", "size_in_bytes": 1_810_000_000},
        {"key": "ollama-program-v0.40.17-windows-amd64", "ref": "refs/heads/main", "size_in_bytes": 1_600_000_000})),
        "utf-8")
    merged = tmp_path / "merged.json"
    pooled = expected["pooled"]
    assert pooled["chrf"] == 41.2
    merged.write_text(json.dumps({**_results(f1=pooled["f1"], cer=pooled["cer"], chrf=39.7, pages=pooled["pages"]),
                                  "dataset": {"series": ["a", "b", "c", "d", "e"], "pages": pooled["pages"]}}), "utf-8")
    assert s.main(["table", str(tmp_path / "artifacts"), "--jobs", str(jobs), "--caches", str(caches),
                   "--merged", str(merged), "--out", str(tmp_path / "summary.md")]) == 0
    text = (tmp_path / "summary.md").read_text("utf-8")
    assert text == capsys.readouterr().out
    assert text.startswith("# GPU checks on runners\n")
    assert "| Stand-in c | success | 0:30 | 8:00 | 11:00 | 1:00 | 20:00 | the packages 180 |" in text
    assert "Summary |" not in text
    assert "Ollama v0.40.17; main's caches found: program, store, models, missing: pip; none made by this run." in text
    assert "4.51 GB in 3 caches, of the 10 GB" in text and "ollama-program 1.6 GB (1)" in text
    assert "| c | PASS | 0 | works | Windows.Graphics.Capture | 400/30/4, 0, 0 |" in text
    assert "| d | FAIL | 1 | no frames |" in text
    assert "Failed criteria:\n* d:\n  * all: the window captured the stand-in's frames" in text
    assert "| 5 rasetugari | PASS | 54 | 100.0 | 900.0 | 1000.0 | 0.9705 | 0.0325 | 38.01 | 7.5 |" in text
    rows = [line for line in text.splitlines() if line.startswith("| all, pooled (5 titles) |")]
    assert len(rows) == 1 and "chrf 39.7 vs 41.2 (+-1.0) OUTSIDE" in rows[0] and "f1 0.9719 vs 0.9719" in rows[0]
    # the summary job's warning finds that row
    step = _step("summary", "The run's tables")["run"]
    pattern = re.search(r"-Pattern '([^']+)'", step).group(1)
    assert re.search(pattern, rows[0]) and not re.search(pattern, text.replace("OUTSIDE", "x"), re.M)


def test_the_stand_in_tool_says_which_capture_gave_its_frames(monkeypatch, capsys):
    import standin_e2e
    from taslation.capture import wgc

    monkeypatch.setattr(wgc, "route", lambda: "Windows.Graphics.Capture")
    notes = standin_e2e.Notes(31, 1.0)
    assert standin_e2e.capture_route(notes)["used"] == "none"
    notes.compositor["none"] += 3
    assert standin_e2e.capture_route(notes) == {"route": "Windows.Graphics.Capture", "looks": {"none": 3},
                                                "used": "PrintWindow"}
    notes.compositor["frames"] += 40
    assert standin_e2e.capture_route(notes)["used"] == wgc.ROUTE
    report = {"translator": "canned", "browser": "chrome", "pages": "synthetic",
              "run": {"seconds": 1.0, "failed": "the stand-in browser ended", "captures": {"sharp": 2},
                      "capture_route": standin_e2e.capture_route(notes)}}
    standin_e2e.print_table(report, Path("report.json"))
    assert "capture: Windows.Graphics.Capture (looks {'none': 3, 'frames': 40}" in capsys.readouterr().out
