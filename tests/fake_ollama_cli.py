"""A fake ``ollama`` command line for the install tests: ``list``, ``create NAME -f MODELFILE``, ``pull NAME`` and
``rm NAME`` on the models in a JSON file (``FAKE_OLLAMA_STATE``), every call written down there too. The file can
make it fail: ``"down": true`` (no server), ``"fail": ["create"]`` (that command ends with exit code 1),
``"slow": ["pull"]`` (that command takes a while, saying how far it got). `make` puts it in a folder as ollama.cmd."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def _state() -> tuple[Path, dict]:
    path = Path(os.environ["FAKE_OLLAMA_STATE"])
    data = json.loads(path.read_text("utf-8")) if path.is_file() else {}
    data.setdefault("models", [])
    data.setdefault("calls", [])
    data.setdefault("created", {})
    return path, data


def main(args: list[str]) -> int:
    path, data = _state()
    data["calls"].append(args)
    path.write_text(json.dumps(data), "utf-8")
    if data.get("down"):
        print("Error: could not connect to ollama app, is it running?")
        return 1
    command = args[0] if args else ""
    if command in data.get("slow", []):
        for step in range(1, 30):
            print(f"pulling 4f2b: {step}%", flush=True)
            time.sleep(0.1)
    if command in data.get("fail", []):
        print(f"Error: {command} failed")
        return 1
    if command == "list":
        print("NAME    ID    SIZE    MODIFIED")
        for name in data["models"]:
            print(f"{name}    abc123    1.8 GB    now")
        return 0
    if command == "create":
        name, modelfile = args[1], Path(args[args.index("-f") + 1])
        text = modelfile.read_text("utf-8")
        source = next(line.split(None, 1)[1] for line in text.splitlines() if line.startswith("FROM "))
        if not (modelfile.parent / source).is_file():
            print(f"Error: no such file {source}")
            return 1
        print("copying file sha256:2c28 100%")
        data["created"][name] = text
        data["models"].append(name + ":latest")
    elif command == "pull":
        print("pulling manifest")
        print("pulling 4f2b: 50%")
        print("pulling 4f2b: 100%")
        data["models"].append(args[1])
    elif command == "rm":
        name = args[1]
        kept = [m for m in data["models"] if m not in (name, name + ":latest")]
        if len(kept) == len(data["models"]):
            print(f"Error: model '{name}' not found")
            return 1
        data["models"] = kept
        print(f"deleted '{name}'")
    path.write_text(json.dumps(data), "utf-8")
    return 0


def make(folder: Path, state: Path, models: list[str] | None = None, **extra) -> Path:
    """ollama.cmd in *folder*, running this file on *state* (which starts with *models* and *extra*)."""
    folder.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"models": list(models or []), **extra}), "utf-8")
    exe = folder / "ollama.cmd"
    exe.write_text(f'@echo off\r\n"{sys.executable}" "{Path(__file__).resolve()}" %*\r\n', encoding="ascii")
    return exe


def read(state: Path) -> dict:
    return json.loads(state.read_text("utf-8"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
