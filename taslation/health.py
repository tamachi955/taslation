"""Quick checks of what translating needs: Ollama running, the translation model installed, the OCR model on disk.

Meant to run when the window starts, every few seconds while a problem stands, and before a whole-book batch
(`taslation.batch.preflight`). They only ever talk to the configured Ollama on this computer (a URL whose host
is not a loopback address counts as "not running", and nothing is sent to it), with one short GET request at
most, and they are quick when Ollama is not running: on Windows a refused connection takes about 2 s to be
reported (the system tries twice more before it gives up), so every address gets a single connection attempt
with a short timeout (`CONNECT_TIMEOUT`) instead; a server on this computer accepts at once.

`check` says what is wrong as `taslation.messages.Message` objects:

* ``health.ocr_missing`` {path}: the OCR model is not in its folder (install.cmd fetches it);
* ``health.ollama_down`` {url}: nothing answers at the Ollama URL;
* with ``ollama_model = "auto"`` (the default: the target language chooses the model, `taslation.translate.models`):
  ``translator.model_missing`` {model, name, language}: the model the language needs is not installed and nothing
  can stand in for it; ``translator.other_model`` {model, name, language, used}: PLaMo is not installed and Qwen
  translates meanwhile (a notice). ``model`` is the Ollama name of the model to install, ``name`` the one the reader
  knows;
* ``health.model_missing`` {model}: Ollama runs but has no model at all (install.cmd fetches the default one);
* ``health.other_model`` {wanted, used}: Ollama lacks the default model and the window would use ``used`` (the first
  one Ollama lists) instead (a default model asked for by name);
* ``health.chosen_model_missing`` {model, command}, ``health.chosen_other_model`` {wanted, used, command}: the same for
  a model other than the default, set by hand in a settings file: install.cmd does not help, ``command`` does
  (``ollama pull``). Only this person ever reads of a command.
"""

from __future__ import annotations

import http.client
import json
import socket
import ssl
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import Settings
from .messages import Message
from .netguard import is_loopback_host
from .ocr.charspot import check_model_dir

CONNECT_TIMEOUT = 0.5  # seconds for one connection attempt: a local server accepts at once
MAX_BODY = 1 << 20  # what is read of an answer at most
PULL_COMMAND = "ollama pull {model}"  # how a model is installed (see the README)


def pull_command(model: str) -> str:
    """The command that installs *model* in Ollama."""
    return PULL_COMMAND.format(model=model)


def is_default_model(model: str) -> bool:
    """Whether *model* is one install.cmd installs: the default of the settings (``"auto"``) or one of the models the
    target language chooses from (`taslation.translate.models.MODELS`)."""
    from .translate.models import by_ollama_name  # (the translate package imports this module)

    return model == Settings.ollama_model or by_ollama_name(model) is not None


def _endpoint(url: str) -> tuple[str, str, int, str] | None:
    """(scheme, host, port, path prefix) of a loopback http(s) URL; None for any other."""
    try:
        parsed = urlparse(url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.hostname or not is_loopback_host(parsed.hostname):
        return None
    return parsed.scheme, parsed.hostname, port, parsed.path.rstrip("/")


def _addresses(host: str, port: int) -> list[tuple[Any, ...]]:
    """Where *host* is, IPv4 first (Ollama listens on 127.0.0.1 unless told otherwise)."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return []
    return sorted(infos, key=lambda info: 0 if info[0] == socket.AF_INET else 1)


def _connect(host: str, port: int, deadline: float) -> socket.socket | None:
    """A connected socket, trying each address once with a short timeout, until *deadline*; None when nothing
    accepts."""
    for family, kind, proto, _name, address in _addresses(host, port):
        left = deadline - time.monotonic()
        if left <= 0:
            break
        sock = socket.socket(family, kind, proto)
        sock.settimeout(min(CONNECT_TIMEOUT, left))
        try:
            sock.connect(address)
            return sock
        except OSError:
            sock.close()
    return None


class _Quick(http.client.HTTPConnection):
    """An HTTP connection that connects as `_connect` does and gives up at *deadline*."""

    def __init__(self, host: str, port: int, deadline: float, tls: bool = False):
        super().__init__(host, port, timeout=max(0.05, deadline - time.monotonic()))
        self._deadline = deadline
        self._tls = tls

    def connect(self) -> None:
        sock = _connect(self.host, self.port, self._deadline)
        if sock is None:
            raise ConnectionRefusedError("nothing accepts the connection")
        sock.settimeout(max(0.05, self._deadline - time.monotonic()))
        if self._tls:
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)
        self.sock = sock


def get(url: str, path: str, timeout: float = 1.0) -> tuple[int, bytes] | None:
    """GET *path* of the Ollama at *url*: (status, body), or None when nothing answers within *timeout* seconds
    (or the URL is not a loopback one)."""
    endpoint = _endpoint(url)
    if endpoint is None:
        return None
    scheme, host, port, prefix = endpoint
    conn = _Quick(host, port, time.monotonic() + max(0.05, timeout), tls=scheme == "https")
    try:
        conn.request("GET", prefix + path, headers={"Accept": "application/json", "Connection": "close"})
        resp = conn.getresponse()
        return resp.status, resp.read(MAX_BODY)
    except (OSError, http.client.HTTPException):
        return None
    finally:
        conn.close()


def ollama_running(url: str, timeout: float = 1.0) -> bool:
    """Whether Ollama answers at *url*."""
    answer = get(url, "/api/version", timeout)
    return answer is not None and answer[0] == 200


def installed_models(url: str, timeout: float = 1.0) -> list[str] | None:
    """The models Ollama at *url* has (`/api/tags`), in its order; None when it does not answer as Ollama does."""
    answer = get(url, "/api/tags", timeout)
    if answer is None or answer[0] != 200:
        return None
    try:
        data = json.loads(answer[1].decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, list):
        return None
    return [str(m.get("name")) for m in models if isinstance(m, dict) and m.get("name")]


def has_model(models: list[str], wanted: str) -> bool:
    """Whether *wanted* is among *models*: by its full name, or a name without a tag by any of its tags (as
    `OllamaTranslator.has_model` decides)."""
    if wanted in models:
        return True
    return ":" not in wanted and any(m.split(":", 1)[0] == wanted for m in models)


def model_installed(url: str, model: str, timeout: float = 1.0) -> bool:
    """Whether Ollama at *url* runs and has *model*."""
    models = installed_models(url, timeout)
    return models is not None and has_model(models, model)


def ocr_available(model_dir: str | Path | None = None) -> bool:
    """Whether the OCR model's files are in *model_dir* (the test `taslation.ocr.charspot` makes before loading; by
    default the folder of the default settings, ``Settings().ocr_model_dir``)."""
    if model_dir is None:
        model_dir = Settings().ocr_model_dir
    return not check_model_dir(Path(model_dir))


def check_ocr(model_dir: str | Path) -> list[Message]:
    """``health.ocr_missing`` when the OCR model that reads alone (charspot) is not in *model_dir*; empty when it is.
    The two other readers missing is no problem: `Readers` goes on without them and ``ocr.one_reader`` says so."""
    if ocr_available(model_dir):
        return []
    return [Message("health.ocr_missing", path=str(model_dir))]


def page_models_missing(settings: Any) -> bool:
    """Whether the layout model or an inpainting model the settings ask for on this computer is not here (`ArtEraser`,
    `LayoutModel`): pages are read and erased the classical way then. No problem, and never a banner: a line says so.
    The inpainting is asked for as `artwork.runs_here` says (art_erase "auto", the default, only where torch has a
    CUDA GPU): a computer without one is told nothing about models it would not use."""
    from .detect import layout
    from .render import artwork

    wants_erase = settings.erase_mode == "fill" and artwork.runs_here(settings.art_erase)
    wants_layout = settings.detect_model == "on" or (settings.detect_model == "auto" and wants_erase)
    return ((wants_erase and not artwork.available(settings.models_dir, settings.art_erase))
            or (wants_layout and not layout.available(settings.models_dir)))


def check_ollama(url: str, model: str, timeout: float = 1.0, known: Any = None, language: str = "") -> list[Message]:
    """What stands in the way of translating with *model* at *url*: Ollama not running, the model not installed
    (with another one to use instead, or none at all; the messages for the default model send the reader to
    install.cmd, those for another one give the command); empty when all is well. *known*: the
    `taslation.translate.models.TranslatorModel` the target language *language* chose (a translator's
    ``auto_model``): missing, it is ``translator.model_missing``, since no other model stands in for a translator
    already made for it."""
    models = installed_models(url, timeout)
    if models is None:
        return [Message("health.ollama_down", url=url)]
    if has_model(models, model):
        return []
    if known is not None:
        from .translate.models import missing_message

        return [missing_message(known, language)]
    default = is_default_model(model)
    if models:
        if default:
            return [Message("health.other_model", wanted=model, used=models[0])]
        return [Message("health.chosen_other_model", wanted=model, used=models[0], command=pull_command(model))]
    if default:
        return [Message("health.model_missing", model=model)]
    return [Message("health.chosen_model_missing", model=model, command=pull_command(model))]


def check_translation_model(url: str, setting: str, language: str, timeout: float = 1.0) -> list[Message]:
    """What stands in the way of translating into *language* with the setting ``ollama_model`` *setting*: for
    ``"auto"``, Ollama not running, or what `taslation.translate.models.choose` says of the models it has
    (``translator.model_missing``, ``translator.other_model``); for a model set by hand, `check_ollama`."""
    from .translate.models import choose, is_auto

    if not is_auto(setting):
        return check_ollama(url, str(setting).strip(), timeout)
    models = installed_models(url, timeout)
    if models is None:
        return [Message("health.ollama_down", url=url)]
    problem = choose(setting, language, models).problem
    return [problem] if problem is not None else []


def check(settings: Any, model: str | None = None, url: str | None = None, timeout: float = 1.0,
          language: str | None = None) -> list[Message]:
    """Everything translating new pages needs, in the order the pipeline needs it: the OCR model, then Ollama
    and the model (*model* and *url*, by default the settings' ``ollama_model`` and ``ollama_url``; with
    ``"auto"``, the model the target language - *language*, by default the settings' - needs:
    `check_translation_model`). Empty when all is well; at most one second or so when Ollama is not running."""
    problems = check_ocr(settings.ocr_model_dir)
    url = url or settings.ollama_url
    if model:
        problems += check_ollama(url, model, timeout)
    else:
        problems += check_translation_model(url, settings.ollama_model, language or settings.target_language, timeout)
    return problems
