from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import urllib.request

import pytest

from taslation import netguard


@pytest.fixture
def guard():
    st = netguard.install(audit_hook=False)
    try:
        yield st
    finally:
        netguard.uninstall()


def free_server() -> tuple[socket.socket, int]:
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    return srv, srv.getsockname()[1]


def test_blocks_dns_before_any_packet(guard):
    with pytest.raises(netguard.NetworkBlocked):
        socket.getaddrinfo("example.com", 80)
    with pytest.raises(netguard.NetworkBlocked):
        socket.gethostbyname("example.com")
    assert any("example.com" in b for b in guard.blocked)


def test_blocks_direct_ip_connect(guard):
    s = socket.socket()
    try:
        with pytest.raises(netguard.NetworkBlocked):
            s.connect(("1.1.1.1", 80))
        with pytest.raises(netguard.NetworkBlocked):
            s.connect_ex(("8.8.8.8", 53))
    finally:
        s.close()


def test_blocks_udp_sendto(guard):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        with pytest.raises(netguard.NetworkBlocked):
            s.sendto(b"x", ("1.1.1.1", 53))
    finally:
        s.close()


def test_blocks_loopback_on_other_ports(guard):
    srv, port = free_server()
    try:
        s = socket.socket()
        with pytest.raises(netguard.NetworkBlocked):
            s.connect(("127.0.0.1", port))
        s.close()
    finally:
        srv.close()


def test_allows_loopback_on_allowed_port():
    srv, port = free_server()
    netguard.install(allowed_ports={port}, audit_hook=False)
    try:
        accepted = []

        def accept():
            conn, _ = srv.accept()
            accepted.append(conn)

        t = threading.Thread(target=accept, daemon=True)
        t.start()
        c = socket.create_connection(("localhost", port), timeout=3)
        t.join(3)
        c.close()
        assert accepted
        assert socket.getaddrinfo("127.0.0.1", port)
    finally:
        for c in accepted:
            c.close()
        srv.close()
        netguard.uninstall()


def test_urllib_cannot_leave_the_machine(guard):
    with pytest.raises(netguard.NetworkBlocked):
        urllib.request.urlopen("http://example.com/", timeout=2)


def test_offline_environment_is_set(guard):
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
    assert os.environ["HF_HUB_DISABLE_TELEMETRY"] == "1"
    assert "HTTP_PROXY" not in os.environ and "HTTPS_PROXY" not in os.environ


def test_describe_and_uninstall():
    netguard.install(audit_hook=False)
    assert "ON" in netguard.describe()
    netguard.uninstall()
    assert not netguard.is_installed()
    # plain resolution works again for loopback at least
    assert socket.getaddrinfo("127.0.0.1", 80)


def test_is_loopback_host():
    assert netguard.is_loopback_host("localhost")
    assert netguard.is_loopback_host("127.0.0.1")
    assert netguard.is_loopback_host("127.5.5.5")
    assert netguard.is_loopback_host("::1")
    assert netguard.is_loopback_host(b"localhost")
    assert netguard.is_loopback_host(None)
    assert not netguard.is_loopback_host("example.com")
    assert not netguard.is_loopback_host("10.0.0.1")
    assert not netguard.is_loopback_host("localhost.example.com")


def test_no_test_reaches_ollama_s_usual_port_and_none_leaves_the_guard_on():
    """tests/conftest.py refuses a connection to this computer's port 11434 - the person's own server there - as on a
    computer where nothing listens on it, and notes it (the test that tried fails); and puts the guard back as it was
    after each test (a guard left on blocked a later test's fake server on its own port on the runners, by their
    order). Its hook is asked here as Python asks it, never with a real connection."""
    import conftest

    before = len(conftest._usual_port_tried)
    for host in ("127.0.0.1", "localhost", "::1"):
        with pytest.raises(ConnectionRefusedError):
            conftest._usual_port_refused("socket.connect", (None, (host, conftest.USUAL_PORT)))
    assert conftest._usual_port_tried[before:] == ["127.0.0.1:11434", "localhost:11434", "::1:11434"]
    del conftest._usual_port_tried[before:]  # (this test's own: not a test that tried)
    for event, args in (("socket.connect", (None, ("127.0.0.1", 11435))), ("socket.connect", (None, r"\\.\pipe\x")),
                        ("socket.getaddrinfo", ("127.0.0.1", 11434, 0, 0, 0, 0))):
        conftest._usual_port_refused(event, args)  # (another port, a pipe, a name looked up: let through)
    assert len(conftest._usual_port_tried) == before
    was = conftest._guard_now()
    assert was == (False, netguard.state().allowed_ports if netguard.state() else None)
    netguard.install(allowed_ports={9}, audit_hook=False)  # (left on by "a test")
    conftest._guard_back(was)
    assert not netguard.is_installed()
    netguard.install(allowed_ports={9}, audit_hook=False)  # (on before "a test" that turned it off)
    on = conftest._guard_now()
    netguard.uninstall()
    conftest._guard_back(on)
    assert netguard.is_installed() and netguard.state().allowed_ports == frozenset({9})
    netguard.uninstall()


def test_no_test_runs_this_computer_s_own_ollama_command(tmp_path, monkeypatch):
    """tests/conftest.py refuses to start the ollama command installed on this computer (as a process of its own it
    would talk to the person's own server on the usual port, which the socket hook does not see), however it is named
    to ``subprocess.Popen``, and notes it; a fake command elsewhere is let through. Asked as Python asks it, with a
    stand-in for the installed one: no process is started."""
    import conftest

    exe = tmp_path / "Programs" / "Ollama" / "ollama.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    monkeypatch.setattr(conftest, "INSTALLED_OLLAMA", frozenset({conftest._program_key(exe)}))
    before = len(conftest._installed_ollama_run)
    for executable, argv in ((None, [str(exe), "serve"]), (str(exe), ["ollama", "rm", "m"]), (None, f'"{exe}" pull m'),
                             (None, [exe, "list"]), (None, f'"{exe}" ps'.encode())):
        with pytest.raises(PermissionError):
            conftest._installed_ollama_refused("subprocess.Popen", (executable, argv, None, None))
    assert len(conftest._installed_ollama_run) == before + 5
    del conftest._installed_ollama_run[before:]  # (this test's own: not a test that ran it)
    fake = tmp_path / "fake" / "ollama.cmd"
    for executable, argv in ((None, [str(fake), "serve"]), (None, [sys.executable, "-c", "pass"]), (None, []),
                             (None, ""), (None, "ollama-that-is-nowhere list")):
        conftest._installed_ollama_refused("subprocess.Popen", (executable, argv, None, None))
    conftest._installed_ollama_refused("socket.connect", (None, ("127.0.0.1", 11435)))
    assert len(conftest._installed_ollama_run) == before


def test_audit_hook_blocks_raw_socket_module():
    """The C-level backstop catches code that bypasses the Python socket wrapper."""
    code = (
        "import taslation.netguard as n, _socket, sys\n"
        "n.install()\n"
        "s = _socket.socket()\n"
        "try:\n"
        "    s.connect(('1.1.1.1', 80))\n"
        "except Exception as e:\n"
        "    print('CAUGHT', type(e).__name__, e)\n"
        "    sys.exit(7)\n"
        "print('NOT BLOCKED')\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 7, proc.stdout + proc.stderr
    assert "network guard blocked" in proc.stdout
