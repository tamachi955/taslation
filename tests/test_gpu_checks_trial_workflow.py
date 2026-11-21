""".github/workflows/gpu-checks-trial.yml, the trial of the GPU computer's checks on GitHub's runners, and its helpers:
what it may do (a push to ci/trial-... or a start by hand, read-only rights, bounded jobs and times), that the stand-in's
jobs run every scenario once and the benchmark's every title, where PLaMo's licence is agreed (one step, install.ps1's
exact sentence, the owner's agreement beside it), that no cache and no artifact holds the dataset or a picture, and
what its summaries make of the tools' reports. Nothing here runs the workflow; GitHub's ZIP has no .github, so a copy
unpacked from it skips these.
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
WORKFLOW = ROOT / ".github" / "workflows" / "gpu-checks-trial.yml"
HELPERS = ROOT / ".github" / "gpu-checks-trial"

pytestmark = pytest.mark.skipif(not WORKFLOW.is_file(), reason="no .github here (GitHub's ZIP leaves it out)")

sys.path.insert(0, str(ROOT / "tools"))


def _workflow() -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(WORKFLOW.read_text("utf-8"))


def _summarise():
    spec = importlib.util.spec_from_file_location("gpu_checks_trial_summarise", HELPERS / "summarise.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _steps(job: str) -> list[dict]:
    return _workflow()["jobs"][job]["steps"]


def _step(job: str, name_part: str) -> dict:
    found = [s for s in _steps(job) if name_part in s.get("name", "")]
    assert len(found) == 1, (job, name_part)
    return found[0]


def _install_ps1(name: str) -> str:
    m = re.search(r"^\$" + name + r" = '([^']+)'", (ROOT / "install.ps1").read_text("ascii"), re.M)
    assert m, name
    return m.group(1)


def test_it_runs_for_a_trial_branch_or_by_hand_with_read_only_rights_and_bounded_jobs():
    wf = _workflow()
    on = wf.get("on", wf.get(True))  # (YAML 1.1 reads the key `on` as true)
    assert sorted(on) == ["push", "workflow_dispatch"]
    assert on["push"] == {"branches": ["ci/trial-**"]}
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
    # at most 16 jobs at once (GitHub's limit for the account is 20), each with a time limit
    matrices = [jobs[name]["strategy"] for name in ("standin", "benchmark")]
    counts = [len(m["matrix"].get("include") or m["matrix"].get("title")) for m in matrices]
    assert counts == [11, 5] and sum(counts) <= 20
    assert [m["max-parallel"] for m in matrices] == counts and all(m["fail-fast"] is False for m in matrices)
    assert jobs["standin"]["needs"] == jobs["benchmark"]["needs"] == "prepare"
    assert jobs["summary"]["needs"] == ["prepare", "standin", "benchmark"]
    # an input reaches a script only through the environment, and is checked there
    inputs = on["workflow_dispatch"]["inputs"]
    assert text.count("${{ inputs.") == len(inputs) == 7
    assert all(f"${{{{ inputs.{name} || '{spec['default']}' }}}}" in text for name, spec in inputs.items())
    for job in ("prepare", "standin", "benchmark", "summary"):
        for step in _steps(job):
            assert "inputs." not in step.get("run", ""), step.get("name")


def test_tests_yml_leaves_the_trial_branches_out():
    yaml = pytest.importorskip("yaml")
    tests = yaml.safe_load((ROOT / ".github" / "workflows" / "tests.yml").read_text("utf-8"))
    assert tests[True]["push"]["branches"] == ["ci/**", "!ci/trial-**"]


def test_the_stand_in_jobs_run_every_scenario_once_and_the_benchmark_every_title():
    import standin_e2e

    groups = _workflow()["jobs"]["standin"]["strategy"]["matrix"]["include"]
    covered = []
    for g in groups:
        names = standin_e2e.wanted(g["scenarios"])
        assert g["group"] == "-".join(names), g  # (the group says what the tool runs: a pair comes along)
        covered += names
    assert sorted(covered) == sorted(standin_e2e.ORDER) and len(covered) == len(set(covered))
    # e turns back to the pages d translated: never alone, never without d
    assert ["d", "e"] in [standin_e2e.wanted(g["scenarios"]) for g in groups]
    run = _step("standin", "Run: tools/standin_e2e.py")
    for flag in ("'--start-ollama', $env:OLLAMA_PORT", "'--seed', '1'", "'--timeout', $env:SCENARIO_TIMEOUT",
                 "'--cancel-soft-ms', $env:CANCEL_SOFT_MS", "'--scenario', $env:SCENARIOS"):
        assert flag in run["run"], flag
    assert "'--canned'" not in run["run"] and run["env"]["SCENARIOS"] == "${{ matrix.scenarios }}"
    assert _workflow()["jobs"]["benchmark"]["strategy"]["matrix"]["title"] == [1, 2, 3, 4, 5]
    bench = _step("benchmark", "Run: tools/openmantra_eval.py")["run"]
    for flag in ("'--series', $env:SERIES", "'--seed', '1'", "'--start-ollama', $env:OLLAMA_PORT",
                 "'--detect-model', $env:DETECT_MODEL"):
        assert flag in bench, flag
    assert "--dump" not in bench and "--scan" not in bench and "--geometry-scan" not in bench  # (text, masks)
    assert _workflow()["env"]["OLLAMA_PORT"] not in ("11434", "")


def test_plamos_licence_is_agreed_in_the_import_step_only_with_install_ps1s_exact_sentence():
    plamo = _install_ps1("PlamoConsentVar")
    assert plamo == "TASLATION_AGREE_PLAMO_LICENCE"
    wf = _workflow()
    assert plamo not in wf["env"] and all(plamo not in (job.get("env") or {}) for job in wf["jobs"].values())
    with_consent = [s for job in wf["jobs"] for s in _steps(job) if plamo in (s.get("env") or {})]
    step = _step("prepare", "Import the translation model")
    assert with_consent == [step]
    assert step["env"][plamo] == _install_ps1("PlamoConsentText") == "I agree to the PLaMo Community License"
    assert "--plamo-agreed TASLATION_AGREE_PLAMO_LICENCE" in step["run"]
    assert "-cne 'I agree to the PLaMo Community License'" in step["run"]
    assert step["if"] == "steps.store.outputs.cache-hit != 'true'"  # (only when the store is not kept already)
    assert "TASLATION_AGREE_OCR_LICENCE" not in WORKFLOW.read_text("utf-8")  # (the models as tests.yml: --agreed)
    text = WORKFLOW.read_text("utf-8")
    above = text[:text.index(f"{plamo}: ")]
    above = above[above.rindex("env:"):]
    assert "The repository owner has read the licence below and agrees to it" in above
    assert "non-commercial" in above and "https://plamo.preferredai.jp/info/plamo-community-license-en" in above


def test_no_cache_and_no_artifact_holds_the_dataset_or_a_picture():
    forbidden = ("dataset", "openmantra", "shots", ".png", ".jpg", ".taslation", "taslation-state", "plamo-download")
    kept: list[str] = []
    for job in _workflow()["jobs"]:
        for step in _steps(job):
            uses = step.get("uses", "")
            if uses.startswith(("actions/cache", "actions/upload-artifact")):
                kept += [p.strip() for p in str(step["with"]["path"]).splitlines() if p.strip()]
    assert kept and all(not any(f in p.lower() for f in forbidden) for p in kept), kept
    caches = {p for job in _workflow()["jobs"] for s in _steps(job) if s.get("uses", "").startswith("actions/cache")
              for p in [s["with"]["path"]]}
    assert caches == {"${{ runner.temp }}/ollama-setup", "~/.ollama/models", "models"}
    # the artifacts are named files (numbers only), never a folder that could hold the tool's pictures
    for job in ("standin", "benchmark"):
        upload = _step(job, "Keep the numbers")
        paths = [p.strip() for p in upload["with"]["path"].splitlines() if p.strip()]
        assert all(re.search(r"/(summary\.json|summary\.md|facts\.json|console\.txt|report\.json|results\.json)$", p)
                   for p in paths), paths
        assert upload["if"] == "always()"
    # the dataset comes from its publisher in each job that reads it
    for job in ("standin", "benchmark"):
        assert sum("tools/fetch_openmantra.py" in s.get("run", "") for s in _steps(job)) == 1
    assert "fetch_openmantra" not in json.dumps(_workflow()["jobs"]["prepare"])
    # the models are kept as tests.yml keeps them
    tests = (ROOT / ".github" / "workflows" / "tests.yml").read_text("utf-8")
    assert "key: models-${{ hashFiles('setup_models.py') }}" in tests
    assert 'models_key = "models-$env:MODELS_HASH"' in WORKFLOW.read_text("utf-8")
    assert _step("prepare", "Which checks")["env"]["MODELS_HASH"] == "${{ hashFiles('setup_models.py') }}"


def test_the_helpers_it_names_are_there_ascii_and_parse():
    text = WORKFLOW.read_text("utf-8")
    named = set(re.findall(r"\.github[/\\]gpu-checks-trial[/\\](\w[\w-]*\.\w+)", text))
    assert named == {"helpers.ps1", "summarise.py"}
    for path in (WORKFLOW, *HELPERS.iterdir()):
        if path.is_file():
            assert all(b < 128 for b in path.read_bytes()), path.name
    helpers = (HELPERS / "helpers.ps1").read_text("ascii")
    used = set(re.findall(r"\b((?:Get|Set|Resolve|Save|Install|Stop)-[A-Z]\w+)\b", text))
    for name in used - {"Set-Content", "Get-Content", "Get-ChildItem", "Get-Item", "Set-Location"}:
        assert f"function {name}" in helpers, name
    # the helpers start nothing and stop only Ollama's own processes (its program folder)
    assert "Start-Process" in helpers and helpers.count("Start-Process") == 1  # (Ollama's installer)
    assert "function Get-OllamaProcesses" in helpers and "$OllamaHome.TrimEnd('\\') + '\\'" in helpers


@pytest.mark.skipif(not shutil.which("pwsh"), reason="PowerShell 7 (the runner's shell) is not installed")
def test_every_step_and_the_helpers_parse_in_powershell_7(tmp_path):
    scripts = [HELPERS / "helpers.ps1"]
    for job in _workflow()["jobs"]:
        for i, step in enumerate(_steps(job)):
            if "run" in step:
                scripts.append(tmp_path / f"{job}{i:02d}.ps1")
                scripts[-1].write_text(step["run"], "utf-8")
    command = "; ".join(
        f"$t = $null; $e = $null; $null = [System.Management.Automation.Language.Parser]::ParseFile('{p}', [ref]$t, "
        f"[ref]$e); foreach ($x in $e) {{ '{p.name}: ' + $x.Message }}" for p in scripts)
    r = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True, text=True,
                       timeout=120, stdin=subprocess.DEVNULL)
    assert r.returncode == 0 and r.stdout.strip() == "", r.stdout + r.stderr


def test_the_summary_reads_the_tools_own_lines():
    s = _summarise()
    import standin_e2e

    assert s.REST_MS == standin_e2e.REST_MS
    source = (ROOT / "tools" / "standin_e2e.py").read_text("utf-8")
    assert 'print(f"run stopped: {why}", file=sys.stderr, flush=True)' in source
    assert s.console_facts("x\nrun stopped: the stand-in browser ended\n")["stopped"] == "the stand-in browser ended"
    ev = (ROOT / "tools" / "openmantra_eval.py").read_text("utf-8")
    assert "f\"  {page.series} p{page.index}: gold {row['gold']}, candidates" in ev
    assert "log(f\"  {series}: run {params['chunk']}/{params['chunks']}, {params['bubbles']} lines so far, " in ev
    console = ("OCR model loaded in 3.1 s\n"
               "  some_title p1: gold 9, candidates 12 (9 matched), read as text 10 (9 matched)  [4.5 s]\n"
               "  some_title p2: gold 3, candidates 4 (3 matched)  [2.0 s]\n"
               "run 1/1, official arm, seed 1\n  some_title: run 2/8, 61 lines so far, 300 s\n")
    progress = s.bench_progress(console)
    assert progress == {"pages_read": 2, "detection_ocr_s": 6.5,
                        "translation": {"runs_done": 2, "runs": 8, "lines": 61, "seconds": 300,
                                        "seconds_all_at_this_pace": 1200}}
    assert s.bench(None, console, {}, "3")["verdict"] == "no results"


def _report(**run) -> dict:
    turns = [
        {"n": 0, "segment": "c", "t_s": 2.0, "rest_ms": 1200, "finished_ms": None},
        {"n": 1, "segment": "c", "t_s": 9.0, "rest_ms": 8000, "finished_ms": 7000, "at_rest": "translated"},
        {"n": 2, "segment": "a", "t_s": 20.0, "rest_ms": 7000, "finished_ms": 9000, "at_rest": "untranslated"},
        {"n": 3, "segment": "a", "t_s": 27.0, "rest_ms": 7000, "finished_ms": 5000, "at_rest": "translated"},
        {"n": 4, "segment": "x", "t_s": 40.0, "rest_ms": 5000, "finished_ms": 4000, "at_rest": "translated"},
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
            "released": {"c": {"waited_s": 1.0, "timed_out": False}, "a": {"waited_s": 600.2, "timed_out": True}},
            "segments": segments, "turns": turns, "guard": {"refused": [], "only_the_stand_in_chosen": True},
            "jobs": {"started": 5, "on": {"sharp": 5}, "kept_from_unsettled_frames": [],
                     "on_black_spinner_unknown_shown": 0},
            "cancels": {"page_still_on_show": [], "by_segment": {"a": 1}},
            "cancel_in_flight": {"soft_ms": 700, "requests_on_soft": 0, "cancelled_in_flight": 0},
            "wasted_requests": {"count": 1}, "errors": {"hooks": {}}, "requests": {"total": 13},
            "ocr": {"placements": [{"engines": ["cpu"], "t": 1.0}]}}
    base.update(run)
    return {"scenarios": ["c", "a", "x"], "translator": "real (the server TASlation starts)", "browser": "chrome",
            "pages": "dataset", "run": base,
            "cleanup": {"log": {"lines": {}, "exception_types": {}}, "state_deleted": True},
            "server_started": {"setup": {"full_window": True, "cache_ram": "256"}, "stopped": True}}


def test_a_stand_in_run_is_told_from_its_report_with_faults_apart_from_slowness(tmp_path):
    s = _summarise()
    facts = {"run": {"exit_code": 0, "seconds": 320.5}, "screen": {"after": "1920x1080 at 32 bit, 60 Hz"}}
    out = s.standin(_report(), "", facts, "c")
    assert out["verdict"] == "works" and out["exit_code"] == 0 and out["ocr_devices"] == ["cpu"]
    assert out["meaning"]["c"] == "holds: 1 of 2 turns came before the window was ready"
    assert out["meaning"]["a"] == "partly: 1 of 2 rested turns translated at rest"
    assert out["meaning"]["x"].startswith("lost: no request on the soft frame within --cancel-soft-ms (700 ms)")
    assert out["faults"] == {"overlays left on a page the stand-in had left": 1}
    assert out["slowness"] == {"scenarios released by --timeout, not at rest": ["a"],
                               "rested turns not finished within their rest": 1,
                               "rested turns not translated at rest": 1,
                               "spells the window did not follow the stand-in (over 1 s)": 2,
                               "requests sent for nothing": 1}
    a = next(r for r in out["segments"] if r["scenario"] == "a")
    assert a["finished_within_rest"] == 1 and a["rest_ms_median"] == 7000
    md = s.standin_md(out)
    assert "### Stand-in c: works" in md and "| a | 2 | 2 (7000) | 1 | 1 |" in md
    assert s.standin(_report(captures={"black": 9}), "", {}, "c")["verdict"] == "no frames"
    refused = s.standin(_report(failed="a call was refused: capture_screen_rect",
                                guard={"refused": ["capture_screen_rect"], "only_the_stand_in_chosen": True}),
                        "", {}, "c")
    assert refused["verdict"] == "stopped" and refused["why"] == "a call was refused: capture_screen_rect"
    assert refused["faults"]["calls refused by the guard"] == ["capture_screen_rect"]
    gone = s.standin(None, "Traceback (most recent call last):\n  x\nOSError: boom\n", facts, "c")
    assert gone["verdict"] == "no report" and gone["console"]["exception_types"] == {"OSError": 1}
    # the command writes both files
    report = tmp_path / "report.json"
    report.write_text(json.dumps(_report()), encoding="utf-8")
    (tmp_path / "facts.json").write_text(json.dumps(facts), encoding="utf-8-sig")  # (PowerShell may write a BOM)
    assert s.main(["standin", str(report), "--facts", str(tmp_path / "facts.json"), "--group", "c",
                   "--out", str(tmp_path / "out")]) == 0
    assert json.loads((tmp_path / "out" / "summary.json").read_text("utf-8"))["run_step_s"] == 320.5


def test_the_run_table_has_each_jobs_minutes_both_checks_and_the_caches(tmp_path, capsys):
    s = _summarise()
    one = tmp_path / "artifacts" / "standin-c"
    one.mkdir(parents=True)
    (one / "summary.json").write_text(json.dumps(s.standin(_report(), "", {}, "c")), encoding="utf-8")
    two = tmp_path / "artifacts" / "benchmark-1"
    two.mkdir(parents=True)
    results = {"tool": "openmantra_eval", "dataset": {"series": ["t1"], "pages": 2}, "settings": {"detect_model": "on"},
               "summary": {"all": {"f1": 0.9, "ocr_gold": {"corpus": 0.03}, "translation": {"chrf": 30.5, "lines": 7}}},
               "translation": {"ollama": "0.40.16", "run_results": [{"speed": {"eval_tok_per_s": 7.5}}]},
               "seconds": {"detection_ocr": 100.0, "translation": 900.0, "total": 1000.0}}
    (two / "summary.json").write_text(json.dumps(s.bench(results, "", {}, "1")), encoding="utf-8")
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
        {"key": "models-ab", "ref": "refs/heads/ci/trial-1", "size_in_bytes": 1_100_000_000},
        {"key": "ollama-store-v0.40.16-cd", "ref": "refs/heads/ci/trial-1", "size_in_bytes": 1_810_000_000},
        {"key": "setup-python-Windows-pip-ef", "ref": "refs/heads/ci/tests-1", "size_in_bytes": 400_000_000})),
        "utf-8")
    assert s.main(["table", str(tmp_path / "artifacts"), "--jobs", str(jobs), "--caches", str(caches),
                   "--out", str(tmp_path / "summary.md")]) == 0
    text = (tmp_path / "summary.md").read_text("utf-8")
    assert text == capsys.readouterr().out
    assert "| Stand-in c | success | 0:30 | 8:00 | 11:00 | 1:00 | 20:00 | the packages 180 |" in text
    assert "Summary |" not in text
    assert "3.31 GB in 3 caches, of the 10 GB" in text and "ollama-store 1.81 GB (1)" in text
    assert "| c | works | Windows.Graphics.Capture | 400/30/4, 0, 0 |" in text
    assert "| 1 t1 | complete | 2 | 100.0 | 900.0 | 1000.0 | 0.9 | 0.03 | 30.5 | 7.5 |" in text


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
