"""The install check's translation (.github/workflows/install-check.yml): `taslation translate` run by the installed
program on a synthetic test page from tests/fixtures (drawn by tools/make_sample_page.py: invented lines, no real
book), with its result read as counts only, so that the public log shows no text of the page.

    <the installed .venv's python> translate-page.py PAGE.png --out COUNTS.json

The .json beside the page says how many bubbles it has. Exit code 0 when the command ended with 0 and no error, all
bubbles but one at most were read as Japanese (the tests with the real OCR ask the same) and at least one of them was
translated; else 1, and 2 without counts when this python is not that of an installed TASlation's .venv (the
program then runs in the folder of that .venv). The counts go to COUNTS.json for the job summary.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

TIMEOUT_S = 25 * 60  # without a GPU the translation model loads and translates on the runner's CPU cores
JAPANESE = ("translated", "untranslated")  # the statuses of a region read as Japanese (`taslation.pipeline`)


def main() -> int:
    ap = argparse.ArgumentParser(description="taslation translate on a test page, counts only")
    ap.add_argument("page", type=Path)
    ap.add_argument("--out", type=Path, required=True, help="where the counts go (JSON)")
    args = ap.parse_args()
    page = args.page.resolve()
    bubbles = len(json.loads(page.with_suffix(".json").read_text("utf-8"))["bubbles"])
    # The installed program: `python -m taslation` takes the package from the folder it runs in, and the folder of
    # the .venv this runs from is the install folder.
    install_dir = Path(sys.prefix).parent
    if sys.prefix == sys.base_prefix or not (install_dir / "taslation" / "__main__.py").is_file():
        print(f"not run by the python of an installed TASlation's .venv: {sys.executable}")
        return 2
    command = [sys.executable, "-m", "taslation", "translate", str(page), "--json"]
    counts: dict = {"page": page.name, "bubbles": bubbles}
    started = time.monotonic()
    try:
        run = subprocess.run(command, capture_output=True, cwd=install_dir,
                             env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        counts.update(exit_code=None, seconds=round(time.monotonic() - started, 1), error=f"no result in {TIMEOUT_S} s")
        return _end(args.out, counts, ok=False)
    counts.update(exit_code=run.returncode, seconds=round(time.monotonic() - started, 1))
    print(f"taslation translate {args.page.name}: exit code {run.returncode} after {counts['seconds']} s")
    try:
        result = json.loads(run.stdout.decode("utf-8"))
    except ValueError:
        result = None
    if not isinstance(result, dict):
        counts["error"] = "no result (the end of what the command said is below)"
        # what it said on stderr: notes and errors, the legal notice it shows once; never the page's text
        for line in run.stderr.decode("utf-8", "replace").splitlines()[-25:]:
            print("  | " + line)
        return _end(args.out, counts, ok=False)
    regions = result.get("regions") or []
    read = [r for r in regions if r.get("status") in JAPANESE and r.get("source_text")]
    translated = [r for r in read if r.get("status") == "translated" and r.get("translated_text")]
    counts.update(
        regions=len(regions), read=len(read), translated=len(translated),
        from_cache=sum(1 for r in regions if r.get("from_cache")),
        statuses=dict(sorted(Counter(r.get("status", "?") for r in regions).items())),
        timings={k: round(float(v), 2) for k, v in (result.get("timings") or {}).items()},
        error=str(result.get("error") or "")[:300])
    print(f"  bubbles on the page: {bubbles}; regions found: {len(regions)}; read as Japanese: {len(read)}; "
          f"translated: {len(translated)}")
    print("  regions by status: " + ", ".join(f"{k} {v}" for k, v in counts["statuses"].items()))
    print("  stages: " + ", ".join(f"{k} {v:.2f} s" for k, v in counts["timings"].items()))
    if counts["error"]:
        print(f"  error: {counts['error']}")
    ok = run.returncode == 0 and not counts["error"] and len(read) >= bubbles - 1 and len(translated) >= 1
    if ok and len(translated) < len(read):
        print(f"::warning title=Translation::{len(read) - len(translated)} of the {len(read)} lines read were not "
              "translated")
    return _end(args.out, counts, ok=ok)


def _end(out: Path, counts: dict, ok: bool) -> int:
    counts["ok"] = ok
    out.write_text(json.dumps(counts, indent=1), "utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
