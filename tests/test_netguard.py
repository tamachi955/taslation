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
