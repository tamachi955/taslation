"""The install check's look at the server TASlation starts (.github/workflows/install-check.yml): Ollama started by the
installed program's own starter (`taslation.ollama_start.OllamaStarter`, as the window and the commands start it),
the translation model loaded into it, the server held while the workflow reads its processes' environment, and then
given back to the product, which stops it (`ollama_start.finish_all`, as a command does at its end).

    <the installed .venv's python> hold-ollama.py --model NAME --state STATE.json --release RELEASE

What it found goes to STATE.json in two steps: once the model is loaded (``"held": true``: the workflow then reads
the processes, and makes the file RELEASE when it is done), and once the product has had its end (``"finish"``: the
lines it said, and whether Ollama still answers). It waits for RELEASE for at most `HOLD_S` seconds. Exit code 0 when
the product started the server itself (nothing answered before), owned it, loaded the model in it and stopped it at
the end; else 1, and 2 when this python is not that of an installed TASlation's .venv. Names and numbers only: no text
of a book is anywhere near this.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

HOLD_S = 15 * 60  # how long the server is held for the workflow at most
LOAD_TIMEOUT_S = 10 * 60  # the model loads on the runner's CPU


def main() -> int:
    ap = argparse.ArgumentParser(description="Ollama started, held and stopped by the installed TASlation")
    ap.add_argument("--model", required=True, help="the translation model to load")
    ap.add_argument("--state", type=Path, required=True, help="where what was found goes (JSON)")
    ap.add_argument("--release", type=Path, required=True, help="the file whose appearance ends the hold")
    args = ap.parse_args()
    install_dir = Path(sys.prefix).parent
    if sys.prefix == sys.base_prefix or not (install_dir / "taslation" / "__main__.py").is_file():
        print(f"not run by the python of an installed TASlation's .venv: {sys.executable}")
        return 2
    sys.path.insert(0, str(install_dir))  # (the installed program; the workflow also runs this in its folder)
    from taslation import health, ollama_start
    from taslation.config import Settings

    settings = Settings.load()
    url = settings.ollama_url
    state: dict = {"url": url, "answered_before": health.ollama_running(url)}
    began = time.monotonic()
    starter = ollama_start.OllamaStarter(url, state_dir=settings.state_dir, own=ollama_start.own_models(settings))
    failed = starter.start()
    state.update(start_s=round(time.monotonic() - began, 1), failure=failed.code if failed is not None else None,
                 owned=ollama_start.owns_server())
    record = ollama_start.record_path(settings.state_dir)
    try:
        data = json.loads(record.read_text("utf-8"))
        state["record"] = {k: data.get(k) for k in ("pid", "exe", "started", "url")}
        state["record"]["users"] = len(data.get("users") or [])
    except (OSError, ValueError, AttributeError):
        state["record"] = None
    if failed is None:
        began = time.monotonic()
        body = json.dumps({"model": args.model, "keep_alive": "15m"}).encode()
        request = urllib.request.Request(f"{url}/api/generate", body, {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=LOAD_TIMEOUT_S) as answer:
                answer.read()
            state["load_s"] = round(time.monotonic() - began, 1)
            state["loaded"] = health.loaded_models(url, 5.0) or []
        except OSError as e:
            state["load_error"] = f"{type(e).__name__}: {e}"[:300]
    state["held"] = True
    _write(args.state, state)
    print("held: " + json.dumps(state), flush=True)
    deadline = time.monotonic() + HOLD_S
    while not args.release.exists() and time.monotonic() < deadline:
        time.sleep(0.5)
    state["released"] = args.release.exists()
    began = time.monotonic()
    state["finish"] = ollama_start.finish_all()
    state["finish_s"] = round(time.monotonic() - began, 1)
    state["answers_after"] = health.ollama_running(url)
    state["record_after"] = record.is_file()
    _write(args.state, state)
    print("finished: " + json.dumps({k: state[k] for k in ("finish", "finish_s", "answers_after", "record_after")}))
    ok = (not state["answered_before"] and failed is None and state["owned"] and "load_s" in state
          and state["finish"] == [ollama_start.STOPPED] and not state["answers_after"] and not state["record_after"])
    return 0 if ok else 1


def _write(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=1), "utf-8")


if __name__ == "__main__":
    sys.exit(main())
