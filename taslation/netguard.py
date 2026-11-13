"""Process-wide network guard for TASlation.

The whole point of TASlation is that nothing leaves the machine. The pipeline
code never calls out, but it sits on top of large third-party libraries (model
loaders, HTTP clients) that *could* phone home. This module makes such a call
fail loudly instead of leaking silently:

* ``socket.getaddrinfo`` / ``gethostbyname`` / ``gethostbyaddr`` refuse to
  resolve any host that is not a loopback name or address, so not even a DNS
  lookup can leak a hostname.
* ``socket.socket.connect`` / ``connect_ex`` / ``sendto`` refuse any
  destination that is not loopback **and** on an allowed port (the local
  Ollama port, 11434 by default).
* A CPython audit hook (``sys.addaudithook``) repeats the same checks at the C
  level, so code that bypasses the Python ``socket`` wrapper is caught too.
* Offline environment variables are set for Hugging Face / transformers so
  model loading never consults the Hub, and proxy variables are cleared so a
  system proxy can never see the local Ollama traffic.

Files, pipes and the GUI are untouched. Every runtime entry point (GUI and
CLI) installs the guard before importing anything heavy. ``setup_models.py``
is the only script that intentionally does *not* install it.
"""

from __future__ import annotations

import ipaddress
import os
import socket
import sys
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

DEFAULT_ALLOWED_PORTS = frozenset({11434})

LOOPBACK_NAMES = frozenset(
    {"localhost", "127.0.0.1", "::1", "0:0:0:0:0:0:0:1", "ip6-localhost", "ip6-loopback"}
)

# Environment that keeps third-party libraries from reaching out on their own.
OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
    "DISABLE_TELEMETRY": "1",
    "DO_NOT_TRACK": "1",
    # Never route anything through a proxy. The guard would refuse the proxy
    # connection anyway, but this keeps the Ollama request path simple.
    "NO_PROXY": "*",
    "no_proxy": "*",
}
PROXY_ENV = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "FTP_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "ftp_proxy",
)


class NetworkBlocked(RuntimeError):
    """Raised when something in the process tries to reach a non-local destination."""


@dataclass
class GuardState:
    allowed_ports: frozenset[int]
    installed: bool = False
    audit_hook_installed: bool = False
    blocked: list[str] = field(default_factory=list)
    allowed: list[str] = field(default_factory=list)
    record_allowed: bool = False


_state: GuardState | None = None
_lock = threading.RLock()
_originals: dict[str, Any] = {}


def is_loopback_host(host: Any) -> bool:
    """True if *host* can only ever refer to this machine."""
    if host is None:
        return True  # wildcard bind / unspecified host; never a remote destination
    if isinstance(host, (bytes, bytearray)):
        try:
            host = bytes(host).decode("ascii", "replace")
        except Exception:
            return False
    if not isinstance(host, str):
        return False
    h = host.strip().lower().rstrip(".")
    if h == "":
        return True
    if h in LOOPBACK_NAMES:
        return True
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    h = h.split("%", 1)[0]  # strip IPv6 scope id
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def _port_of(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = bytes(value).decode("ascii", "replace")
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _describe(address: Any) -> str:
    try:
        if isinstance(address, (tuple, list)) and len(address) >= 2:
            return f"{address[0]}:{address[1]}"
    except Exception:
        pass
    return repr(address)


def _current_state() -> GuardState:
    st = _state
    if st is None:  # pragma: no cover - patches never outlive the state
        raise NetworkBlocked("network guard state missing")
    return st


def check_endpoint(address: Any, what: str) -> None:
    """Allow loopback destinations on allowed ports, refuse everything else."""
    st = _current_state()
    if isinstance(address, (str, bytes, bytearray)):
        return  # AF_UNIX path: local by definition
    host: Any = None
    port: Any = None
    try:
        host, port = address[0], address[1]
    except Exception:
        _block(st, what, _describe(address))
    p = _port_of(port)
    if not is_loopback_host(host) or p is None or p not in st.allowed_ports:
        _block(st, what, _describe(address))
    if st.record_allowed:
        st.allowed.append(f"{what} -> {_describe(address)}")


def check_host(host: Any, port: Any, what: str) -> None:
    """Allow name resolution only for loopback names (and only allowed ports, if given)."""
    st = _current_state()
    if not is_loopback_host(host):
        _block(st, what, f"{host!r}")
    p = _port_of(port)
    if p is not None and p not in st.allowed_ports:
        _block(st, what, f"{host!r}:{p}")
    if st.record_allowed:
        st.allowed.append(f"{what} -> {host!r}:{port!r}")


def _block(st: GuardState, what: str, target: str) -> None:
    ports = ",".join(str(p) for p in sorted(st.allowed_ports))
    msg = f"TASlation network guard blocked {what} to {target} (only loopback:{ports} is allowed)"
    st.blocked.append(msg)
    raise NetworkBlocked(msg)


# --- Python-level patches -------------------------------------------------

def _patch_socket_method(name: str, address_index: int | None) -> None:
    orig = getattr(socket.socket, name)
    _originals[f"socket.{name}"] = orig

    def wrapper(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if address_index is None:
            address = args[-1] if args else kwargs.get("address")
        else:
            address = args[address_index] if len(args) > address_index else kwargs.get("address")
        check_endpoint(address, f"socket.{name}")
        return orig(self, *args, **kwargs)

    wrapper.__name__ = name
    wrapper.__qualname__ = f"socket.{name}"
    wrapper.__wrapped__ = orig  # type: ignore[attr-defined]
    setattr(socket.socket, name, wrapper)


def _make_resolver_wrapper(fn: Callable[..., Any], label: str) -> Callable[..., Any]:
    def wrapper(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        check_host(name, None, label)
        return fn(name, *args, **kwargs)

    wrapper.__name__ = label
    wrapper.__wrapped__ = fn  # type: ignore[attr-defined]
    return wrapper


def _patch_resolvers() -> None:
    orig_gai = socket.getaddrinfo
    _originals["getaddrinfo"] = orig_gai

    def getaddrinfo(host, port, *args, **kwargs):  # type: ignore[no-untyped-def]
        check_host(host, port, "getaddrinfo")
        return orig_gai(host, port, *args, **kwargs)

    getaddrinfo.__wrapped__ = orig_gai  # type: ignore[attr-defined]
    socket.getaddrinfo = getaddrinfo  # type: ignore[assignment]

    for fname in ("gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
        orig = getattr(socket, fname)
        _originals[fname] = orig
        setattr(socket, fname, _make_resolver_wrapper(orig, fname))


# --- C-level backstop -----------------------------------------------------

def _audit_hook(event: str, args: tuple[Any, ...]) -> None:
    st = _state
    if st is None or not st.installed:
        return
    try:
        if event in ("socket.connect", "socket.sendto", "socket.sendmsg"):
            check_endpoint(args[1], event)
        elif event == "socket.getaddrinfo":
            check_host(args[0], args[1] if len(args) > 1 else None, event)
        elif event in ("socket.gethostbyname", "socket.gethostbyaddr"):
            check_host(args[0], None, event)
    except NetworkBlocked:
        raise
    except Exception:
        # Never let a bookkeeping error inside the hook mask the real call;
        # the Python-level patches still apply.
        return


# --- public API -----------------------------------------------------------

def install(allowed_ports: int | frozenset[int] | set[int] | None = None, *, audit_hook: bool = True) -> GuardState:
    """Install the guard. Safe to call more than once; later calls update the allowed ports."""
    global _state
    ports = DEFAULT_ALLOWED_PORTS
    if isinstance(allowed_ports, int):
        ports = frozenset({allowed_ports})
    elif allowed_ports:
        ports = frozenset(int(p) for p in allowed_ports)
    with _lock:
        for k, v in OFFLINE_ENV.items():
            os.environ[k] = v
        for k in PROXY_ENV:
            os.environ.pop(k, None)
        if _state is None:
            _state = GuardState(allowed_ports=ports)
        else:
            _state.allowed_ports = ports
        if not _state.installed:
            _patch_socket_method("connect", 0)
            _patch_socket_method("connect_ex", 0)
            _patch_socket_method("sendto", None)
            _patch_resolvers()
            _state.installed = True
        if audit_hook and not _state.audit_hook_installed:
            sys.addaudithook(_audit_hook)
            _state.audit_hook_installed = True
        return _state


def uninstall() -> None:
    """Remove the Python-level patches (tests only). An installed audit hook cannot be removed."""
    with _lock:
        st = _state
        if st is None or not st.installed:
            return
        for name in ("connect", "connect_ex", "sendto"):
            setattr(socket.socket, name, _originals.pop(f"socket.{name}"))
        socket.getaddrinfo = _originals.pop("getaddrinfo")  # type: ignore[assignment]
        for fname in ("gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
            setattr(socket, fname, _originals.pop(fname))
        st.installed = False  # also turns the audit hook inert


def state() -> GuardState | None:
    return _state


def is_installed() -> bool:
    return _state is not None and _state.installed


def record_allowed(enabled: bool = True) -> None:
    """Also keep a list of *allowed* network calls (used by the ``audit`` command)."""
    st = _current_state()
    st.record_allowed = enabled
    if enabled:
        st.allowed.clear()


def describe() -> str:
    st = _state
    if st is None or not st.installed:
        return "Network guard: OFF"
    ports = ",".join(str(p) for p in sorted(st.allowed_ports))
    return f"Network guard: ON (loopback:{ports} only; {len(st.blocked)} attempt(s) blocked)"
