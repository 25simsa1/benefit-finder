"""Tests for the desktop launcher helpers.

These cover the pieces that run before uvicorn takes over. The server
loop itself is exercised by the web app's own tests, so here we only
check free-port selection and the browser-open-when-ready gate, both
without binding a real server.
"""
from __future__ import annotations

import socket

from benefit_finder import desktop


def test_free_port_is_usable():
    port = desktop._free_port("127.0.0.1")
    assert 1 <= port <= 65535
    # The port the OS handed back must actually be bindable.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", port))


def test_port_is_open_detects_a_live_listener():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert desktop._port_is_open("127.0.0.1", port) is True


def test_port_is_open_false_when_nothing_listening():
    port = desktop._free_port("127.0.0.1")  # unbound, so nothing is listening
    assert desktop._port_is_open("127.0.0.1", port) is False


def test_open_browser_when_ready_opens_once_server_is_up(monkeypatch):
    opened = []
    monkeypatch.setattr(desktop.webbrowser, "open", lambda url: opened.append(url))

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        desktop._open_browser_when_ready("http://x", "127.0.0.1", port, timeout=2.0)

    assert opened == ["http://x"]
