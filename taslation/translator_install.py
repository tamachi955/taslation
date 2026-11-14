"""The translator model a target language needs, installed one at a time ("exclusive"): PLaMo 3 Translate 2B by
default, Qwen3.5 4B for the two languages PLaMo does not cover (`translate.models.model_for_language`). When the
language changes so that the other one is needed, TASlation offers to download it and to remove the one no longer
needed, so that only one takes room on the disk.

What is here does not use the network. The download itself is `setup_models.py`'s, the one script of TASlation
that does: the window and the command line run it in a process of its own (`Installer`), read what it says on the
way (`progress_line`, `parse_progress`) and can stop it; it leaves nothing half done (a ``.part`` file, a GGUF, a
model Ollama did not finish importing are removed).

* PLaMo comes from Hugging Face as one GGUF file at a fixed revision (`PLAMO_FILE`, checked against `PLAMO_SHA256`),
  is imported into Ollama under `PLAMO.ollama_name` from a Modelfile beside it (`modelfile_text`), and the GGUF is
  then deleted: the copy in Ollama is the one used. Its licence, the PLaMo Community License, is agreed to first.
* Qwen3.5 4B is Ollama's own library model: ``ollama pull``.

`record_path` (``translator_models.json`` in the data folder) keeps what TASlation installed and the licences agreed
to, with when: a model is removed only when TASlation installed it, or after the person's own yes (default: keep) -
a model the person had before, such as their own qwen3.5:4b, is theirs. uninstall.ps1 reads the same file.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .atomic import write_atomic
from .health import has_model
from .translate.models import AUTO, PLAMO, QWEN, TranslatorModel, by_ollama_name, model_for_language, wanted_name

MODELS: tuple[TranslatorModel, ...] = (PLAMO, QWEN)

# PLaMo 3 Translate 2B, GGUF (Q4_K_M, the card's default), from this revision of the repository only (2026-11-09: the
# chat template in system messages, the licence as revised on November 9, 2026). The file of the revision pinned
# before, f2b4599d (sha256 2c288ecc...c4cc060787, 1,807,192,480 bytes), is refused by Hugging Face's storage since
# then; its tensors and every other metadata key are those of this file byte for byte, only the embedded chat template
# differs (10,560 bytes), and TASlation sends its prompts raw, without that template: a model imported from it stays
# as it is and translates the same (504 OpenMantra lines, 445 requests, the same answer to each, 2026-11-14).
PLAMO_REPO = "pfnet/plamo-3-translate-2b-GGUF"
PLAMO_REVISION = "4f672106b847200bfdc0f6af6c321cd94eba1aed"
PLAMO_FILE = "plamo-3-translate-2b-Q4_K_M.gguf"
PLAMO_SHA256 = "1ffd9073afcc70e35ccc942428aa2b73d7aa2b9ea779bf504b775369e0276c13"
PLAMO_BYTES = 1_807_203_040
PLAMO_DIRNAME = "plamo-3-translate-2b"  # its folder under the models folder: the Modelfile and the licence's texts
PLAMO_NUM_CTX = 16384  # the context the window's whole-book requests need (the card trained 32K)
PLAMO_STOPS = ("<|plamo:tag|>", "<|plamo:bos|>")  # where a translation ends (the card's Completions examples)
# the licence, in the two languages the repository has it in (path in the repository, sha256, file name kept): the
# texts at the pinned revision, "Established on February 25, 2025 / Revised on November 9, 2026"
PLAMO_LICENCE = "plamo-community-license"
PLAMO_LICENCE_REVISED = "November 9, 2026"  # the revision the summaries below describe (`PLAMO_TERMS`, the window's)
PLAMO_LICENCE_FILES = (
    ("LICENSE/en", "ca0c5e90f6de6799fc2d2d4f2b2647cc088444c19f286f689e525d4ad28f9ed6", "PLaMo-Community-License-en.txt"),
    ("LICENSE/ja", "7dd74339bbf9a39fe33e271a89657aacf06f452b082fcb1273fb792b8d6b7db2", "PLaMo-Community-License-ja.txt"),
)
PLAMO_LICENCE_URLS = ("https://plamo.preferredai.jp/info/plamo-community-license-en",
                      "https://plamo.preferredai.jp/info/plamo-community-license-ja")
# a GGUF on the disk and its copy in Ollama's folder, for a moment both (the GGUF is deleted after the import)
PLAMO_ROOM_GB = 2 * PLAMO_BYTES / 1e9 + 0.2
# the licence's article 4 (1) (ii), for whoever provides the model or a model made from it to others: in the window
# (About) and the README
CREDIT = "Built with PLaMo"
# what the person agrees to, in plain words, with the articles of the revised text (the console's; the window's is in
# its language, locales/features/translator_models.py; install.ps1 has its own copy)
PLAMO_TERMS = f"""TASlation translates with PLaMo 3 Translate 2B by Preferred Networks (PFN), about 1.8 GB, into every
language but Portuguese (Brazil) and Turkish. Its licence is the PLaMo Community License, as revised on
{PLAMO_LICENCE_REVISED}:
  * personal and other non-commercial use is free, with no registration;
    commercial use needs registering with PFN first (article 3);
  * you must be 18 or older (or of age where you live), or have a parent's or guardian's consent (article 2);
  * you are responsible for having the rights to what you put into it and to what comes out of it;
    the licence gives no rights to other people's works (article 9);
  * a translation made with it may be published without a note that it is PLaMo's output, but one
    published as all or a large part of a book or another long publication must say that PLaMo was
    used; when you give a translation to someone or make it public, you must tell them that models
    trained on it fall under this licence (article 5); TASlation asks you not to publish translations at all;
  * the model comes as is, without any warranty; how you use it is your responsibility (article 7).
The full licence, in English and in Japanese:
  {PLAMO_LICENCE_URLS[0]}
  {PLAMO_LICENCE_URLS[1]}"""

RECORD_FILE = "translator_models.json"
PROGRESS_PREFIX = "@taslation "  # a line of setup_models.py --progress: this, then one JSON object
CANCELLED = 3  # setup_models.py's exit code for an install that was stopped (nothing left behind)
NO_ROOM = 4  # ... for too little disk space (nothing downloaded)
# ... for a download the server refused or no longer has (HTTP `REFUSED_HTTP`): trying again does not help, a newer
# TASlation that names the current file does (install.ps1 says so, and the window)
REFUSED = 5
REFUSED_HTTP = frozenset({401, 403, 404, 410})
CANCEL_WAIT_S = 20.0  # how long a stopped install has to clean up before its process is ended


def plamo_url(name: str) -> str:
    """Where *name* of the PLaMo repository is, at the pinned revision."""
    return f"https://huggingface.co/{PLAMO_REPO}/resolve/{PLAMO_REVISION}/{name}"


def modelfile_text(gguf: str = PLAMO_FILE) -> str:
    """The Modelfile PLaMo is imported with: the GGUF beside it, the context and the two stop tokens. No template:
    the window sends PLaMo its prompts as they are (raw)."""
    lines = [f"FROM ./{gguf}", f"PARAMETER num_ctx {PLAMO_NUM_CTX}"]
    lines += [f'PARAMETER stop "{stop}"' for stop in PLAMO_STOPS]
    return "\n".join(lines) + "\n"


def shown_name(model: TranslatorModel) -> str:
    """The model's name as the person reads it ("PLaMo 3 Translate 2B")."""
    return str(getattr(model, "display_name", "") or getattr(model, "name", "") or model.ollama_name)


def size_text(gb: float) -> str:
    return f"{gb:.1f}"


def by_name(name: str) -> TranslatorModel | None:
    """The translator model Ollama knows under *name* (with or without ``:latest``)."""
    for model in MODELS:
        if has_model([name], model.ollama_name) or name == model.ollama_name:
            return model
    return None


# ---------------------------------------------------------------- the record


def record_path(state_dir: Path | str) -> Path:
    return Path(state_dir) / RECORD_FILE


def load_record(state_dir: Path | str) -> dict[str, Any]:
    """``{"installed": {name: {...}}, "agreed": {licence: {...}}}``; empty tables when there is no such file."""
    try:
        with open(record_path(state_dir), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    for key in ("installed", "agreed"):
        if not isinstance(data.get(key), dict):
            data[key] = {}
    return data


def _save_record(state_dir: Path | str, data: dict[str, Any]) -> None:
    path = record_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def mark_installed(state_dir: Path | str, model: TranslatorModel) -> None:
    """*model* was installed by TASlation (it may be removed again when no longer needed)."""
    data = load_record(state_dir)
    data["installed"][model.ollama_name] = {"when": _now(), "size_gb": model.size_gb}
    _save_record(state_dir, data)


def forget(state_dir: Path | str, name: str) -> None:
    data = load_record(state_dir)
    if data["installed"].pop(name, None) is not None:
        _save_record(state_dir, data)


def installed_by_taslation(state_dir: Path | str, name: str) -> bool:
    """Whether TASlation installed the model *name*: recorded so, or PLaMo, whose name only TASlation gives."""
    model = by_name(name)
    if model is not None and model.ollama_name == PLAMO.ollama_name:
        return True
    recorded = load_record(state_dir)["installed"]
    return name in recorded or (model is not None and model.ollama_name in recorded)


def record_agreement(state_dir: Path | str, where: str, licence: str = PLAMO_LICENCE) -> None:
    """The person agreed to *licence* (the texts pinned in `PLAMO_LICENCE_FILES`), in *where* ("install", "window",
    "console")."""
    data = load_record(state_dir)
    data["agreed"][licence] = {"when": _now(), "where": where, "revision": PLAMO_REVISION,
                               "texts": {path: sha for path, sha, _name in PLAMO_LICENCE_FILES}}
    _save_record(state_dir, data)


def has_agreed(state_dir: Path | str, licence: str = PLAMO_LICENCE) -> bool:
    """Whether the person agreed to these very texts of *licence* (a changed licence is asked about again)."""
    entry = load_record(state_dir)["agreed"].get(licence)
    if not isinstance(entry, dict):
        return False
    return entry.get("texts") == {path: sha for path, sha, _name in PLAMO_LICENCE_FILES}


# ---------------------------------------------------------------- what a language change needs


@dataclass(frozen=True)
class Switch:
    """What translating into *language* needs: *needed*, not installed; *unneeded*, the other translator model, when
    installed (None otherwise), and whether TASlation installed it (*ours*: removed with the yes to the offer; else
    the person is asked on its own, and keeping it is the default)."""

    language: str
    needed: TranslatorModel
    unneeded: TranslatorModel | None = None
    ours: bool = False
    unneeded_name: str = ""  # the name Ollama lists it under

    @property
    def freed_gb(self) -> float:
        return self.unneeded.size_gb if self.unneeded is not None else 0.0


def plan(language: str, installed: list[str] | None, state_dir: Path | str, setting: Any = AUTO) -> Switch | None:
    """The switch translating into *language* needs, given the models Ollama lists (*installed*) and the setting
    ``ollama_model`` (*setting*: ``"auto"`` lets the language choose, `translate.models.wanted_name`); None when the
    model it needs is there, when Ollama does not answer (*installed* None: nothing can be said then), or when the
    setting names a model of the person's own (theirs to install: TASlation offers only its two)."""
    if installed is None:
        return None
    needed = by_ollama_name(wanted_name(setting, language))
    if needed is None:
        return None
    if has_model(installed, needed.ollama_name):
        return None
    for model in MODELS:
        if model.ollama_name == needed.ollama_name:
            continue
        name = next((m for m in installed if has_model([m], model.ollama_name) or m == model.ollama_name), None)
        if name is not None:
            return Switch(language, needed, model, installed_by_taslation(state_dir, name), name)
    return Switch(language, needed)


# ---------------------------------------------------------------- Ollama's command line


def find_ollama() -> str | None:
    """ollama.exe: on the PATH, else where its installer puts it (a PATH winget changed is not this process's yet)."""
    found = shutil.which("ollama")
    if found:
        return found
    programs = os.environ.get("LOCALAPPDATA")
    if programs:
        exe = Path(programs) / "Programs" / "Ollama" / "ollama.exe"
        if exe.is_file():
            return str(exe)
    return None


def ollama_env(url: str | None = None) -> dict[str, str]:
    """The environment of an ollama command: the server at *url* (OLLAMA_HOST), no proxy for it."""
    env = dict(os.environ)
    if url:
        env["OLLAMA_HOST"] = url
    env["NO_PROXY"] = env["no_proxy"] = "*"
    return env


def _flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0  # no console of its own


def run_ollama(exe: str, args: list[str], url: str | None = None, timeout: float = 60.0) -> subprocess.CompletedProcess:
    return subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, env=ollama_env(url), stdin=subprocess.DEVNULL, creationflags=_flags())


def listed(exe: str, url: str | None = None) -> list[str] | None:
    """The models ``ollama list`` names; None when it fails (Ollama not running)."""
    try:
        r = run_ollama(exe, ["list"], url)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    lines = [line.split() for line in r.stdout.splitlines() if line.strip()]
    return [parts[0] for parts in lines[1:] if parts and parts[0] != "NAME"]


def remove_model(exe: str, name: str, state_dir: Path | str, url: str | None = None) -> bool:
    """``ollama rm name``; the record forgets it. Whether it went (or was not there)."""
    try:
        r = run_ollama(exe, ["rm", name], url)
    except (OSError, subprocess.SubprocessError):
        return False
    gone = r.returncode == 0
    if not gone:
        names = listed(exe, url)
        gone = names is not None and not has_model(names, name)
    if gone:
        forget(state_dir, name)
    return gone


_PERCENT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")


def percent_of(text: str) -> float | None:
    """The last percentage in a line of ollama's progress ("pulling 4f2b...: 45% ..."), as 0-1."""
    found = _PERCENT.findall(text)
    if not found:
        return None
    return max(0.0, min(1.0, float(found[-1]) / 100.0))


_SIZES = re.compile(r"(\d+(?:\.\d+)?)\s*((?:[KMGT]i?)?B)\s*/\s*(\d+(?:\.\d+)?)\s*((?:[KMGT]i?)?B)", re.IGNORECASE)
_MB = {"b": 1e-6, "kb": 1e-3, "kib": 1.024e-3, "mb": 1.0, "mib": 1.048576, "gb": 1e3, "gib": 1073.741824,
       "tb": 1e6, "tib": 1099511.627776}


def sizes_of(text: str) -> tuple[float, float] | None:
    """How much of how much, in MB, in a line of ollama's progress ("... 1.5 GB/3.3 GB ..."); None without it."""
    found = _SIZES.findall(text)
    if not found:
        return None
    done, done_unit, total, total_unit = found[-1]
    return float(done) * _MB[done_unit.lower()], float(total) * _MB[total_unit.lower()]


def progress_text(percent: int | None, done_mb: float | None = None, total_mb: float | None = None) -> str:
    """A download's progress for a person: "  45 %  (12.3 of 27.0 MB)", the percent or the MB alone when that is
    all there is to say."""
    parts = []
    if percent is not None:
        parts.append(f"{max(0, min(100, int(percent))):3d} %")
    if done_mb is not None and total_mb:
        parts.append(f"({done_mb:,.1f} of {total_mb:,.1f} MB)" if percent is not None else
                     f"{done_mb:,.1f} of {total_mb:,.1f} MB")
    elif done_mb is not None:
        parts.append(f"{done_mb:,.1f} MB")
    return "  " + "  ".join(parts)


def run_watched(command: list[str], cancel: threading.Event, on_output: Callable[[str], None],
                env: dict[str, str] | None = None) -> int | None:
    """*command* run with its output read as it comes (each piece between line ends and carriage returns, to
    *on_output*); ended at once when *cancel* is set. Its exit code, None when it was ended."""
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            env=env, creationflags=_flags())

    def read() -> None:
        assert proc.stdout is not None
        rest = b""
        while True:
            piece = proc.stdout.read1(4096) if hasattr(proc.stdout, "read1") else proc.stdout.read(4096)
            if not piece:
                break
            rest += piece
            parts = re.split(rb"[\r\n]+", rest)
            rest = parts.pop()
            for part in parts:
                if part.strip():
                    on_output(part.decode("utf-8", "replace"))
        if rest.strip():
            on_output(rest.decode("utf-8", "replace"))

    reader = threading.Thread(target=read, name="taslation-ollama-output", daemon=True)
    reader.start()
    while proc.poll() is None:
        if cancel.wait(0.2):
            proc.kill()
            proc.wait()
            reader.join(2.0)
            return None
    reader.join(2.0)
    return proc.returncode


# ---------------------------------------------------------------- leftovers


def plamo_dir(models_dir: Path | str) -> Path:
    return Path(models_dir) / PLAMO_DIRNAME


def remove_leftovers(models_dir: Path | str) -> list[Path]:
    """The GGUF and any ``.part`` of a download in PLaMo's folder, removed (its Modelfile and licence texts stay)."""
    gone: list[Path] = []
    folder = plamo_dir(models_dir)
    if not folder.is_dir():
        return gone
    for path in [*folder.glob("*.gguf"), *folder.glob("*.part")]:
        try:
            path.unlink()
            gone.append(path)
        except OSError:
            pass
    return gone


def free_gb(path: Path | str) -> float | None:
    """Free space on the disk of *path* (its nearest existing folder), in GB; None when it cannot be told."""
    p = Path(path)
    while not p.exists() and p.parent != p:
        p = p.parent
    try:
        return shutil.disk_usage(p).free / 1e9
    except OSError:
        return None


def ollama_models_dir() -> Path:
    return Path(os.environ.get("OLLAMA_MODELS") or Path.home() / ".ollama" / "models")


# ---------------------------------------------------------------- the progress lines


def progress_line(phase: str, done: float = 0, total: float = 0, **extra: Any) -> str:
    """One line of setup_models.py --progress: *phase* ("download", "check", "import", "pull", "remove", "done",
    "error", "cancelled"), how far (*done* of *total*; 0 of 0: no measure) and what else there is to say."""
    return PROGRESS_PREFIX + json.dumps({"phase": phase, "done": done, "total": total, **extra}, ensure_ascii=True)


def parse_progress(line: str) -> dict[str, Any] | None:
    if not line.startswith(PROGRESS_PREFIX):
        return None
    try:
        data = json.loads(line[len(PROGRESS_PREFIX):])
    except ValueError:
        return None
    return data if isinstance(data, dict) and isinstance(data.get("phase"), str) else None


# ---------------------------------------------------------------- the install, run by the window or the command line


@dataclass
class Outcome:
    """How an install ended: "done", "cancelled", "failed", "no_room" or "refused" (the server refused the file or no
    longer has it: `REFUSED`) (*detail*: what setup_models.py said last)."""

    state: str
    detail: str = ""


def setup_script() -> Path:
    from .config import REPO_DIR

    return REPO_DIR / "setup_models.py"


class Installer:
    """setup_models.py in a process of its own installing the translator model *language* needs (the person agreed
    to its licence before), each of its progress lines to *on_progress* (in the thread that calls `run`). `cancel`
    stops it from any thread: the script removes what it began, and if it does not end within CANCEL_WAIT_S, its
    process is ended and what it left is removed here (`remove_leftovers`; a model that came into Ollama meanwhile and
    was not there before is removed too)."""

    def __init__(self, language: str, models_dir: Path | str, state_dir: Path | str, url: str | None = None,
                 on_progress: Callable[[dict[str, Any]], None] | None = None, python: str | None = None,
                 script: Path | None = None, where: str = "window"):
        self.language = language
        self.models_dir = Path(models_dir)
        self.state_dir = Path(state_dir)
        self.url = url
        self.on_progress = on_progress or (lambda _data: None)
        self.python = python or _console_python()
        self.script = script or setup_script()
        self.where = where
        self._cancel = threading.Event()
        self._proc: subprocess.Popen | None = None
        self.last: dict[str, Any] = {}

    def command(self) -> list[str]:
        return [self.python, "-u", str(self.script), "--translator-for", self.language, "--plamo-agreed", self.where,
                "--progress", "--models-dir", str(self.models_dir)]

    def cancel(self) -> None:
        self._cancel.set()
        proc = self._proc
        if proc is not None and proc.poll() is None and proc.stdin is not None:
            try:
                proc.stdin.write("cancel\n")
                proc.stdin.flush()
            except (OSError, ValueError):
                pass

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def run(self) -> Outcome:
        if not Path(self.script).is_file():
            return Outcome("failed", "setup_models.py is not there")
        if self.url:  # Ollama's server first, started as TASlation starts it: an ``ollama`` command that finds none
            # would start Ollama's tray app instead, and with it Ollama's start with Windows
            from .ollama_start import OllamaStarter

            OllamaStarter(self.url, state_dir=self.state_dir).start()
        exe = find_ollama()
        before = listed(exe, self.url) if exe else None
        env = ollama_env(self.url)
        env["TASLATION_STATE_DIR"] = str(self.state_dir)
        env["PYTHONUTF8"] = "1"
        try:
            self._proc = subprocess.Popen(self.command(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                          stdin=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                          env=env, creationflags=_flags())
        except OSError as e:
            return Outcome("failed", str(e))
        if self._cancel.is_set():
            self.cancel()
        watchdog = threading.Thread(target=self._end_if_stuck, name="taslation-install-watchdog", daemon=True)
        watchdog.start()
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            data = parse_progress(line.rstrip("\n"))
            if data is not None:
                self.last = data
                self.on_progress(data)
        code = self._proc.wait()
        if code == 0 and not self._cancel.is_set():
            return Outcome("done")
        if self._cancel.is_set() or code == CANCELLED:
            self._clean(exe, before)
            return Outcome("cancelled")
        self._clean(exe, before)
        if code == NO_ROOM:
            return Outcome("no_room", str(self.last.get("text", "")))
        if code == REFUSED:
            return Outcome("refused", str(self.last.get("text", "")))
        return Outcome("failed", str(self.last.get("text", "")) or f"exit code {code}")

    def _end_if_stuck(self) -> None:
        self._cancel.wait()
        proc = self._proc
        if proc is None:
            return
        try:
            proc.wait(CANCEL_WAIT_S)
        except subprocess.TimeoutExpired:
            proc.kill()

    def _clean(self, exe: str | None, before: list[str] | None) -> None:
        """What a stopped or failed install may have left: the download, and the model if it came in just now."""
        remove_leftovers(self.models_dir)
        needed = model_for_language(self.language)
        if exe is None or before is None or has_model(before, needed.ollama_name):
            return
        now = listed(exe, self.url)
        if now is not None and has_model(now, needed.ollama_name):
            remove_model(exe, needed.ollama_name, self.state_dir, self.url)


def _console_python() -> str:
    """The Python to run setup_models.py with: this one, as python.exe rather than the window's pythonw.exe (whose
    output nobody could read)."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and (exe.parent / "python.exe").is_file():
        return str(exe.parent / "python.exe")
    return str(exe)
