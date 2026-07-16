"""Desktop launcher for the benefit-finder web app.

This is what the double-click app runs. It starts the local web server on
a free port, opens the default browser at the tool, and keeps running
until the app is quit. No terminal and no arguments needed, so a
non-technical user just double-clicks and the tool opens in their browser.

Wired to the `benefit-finder-app` console script.
"""
from __future__ import annotations

import socket
import threading
import time
import webbrowser


def _free_port(host: str) -> int:
    """Ask the OS for an unused port so a stale server never blocks launch."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def _port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


def _open_browser_when_ready(url: str, host: str, port: int, timeout: float = 15.0) -> None:
    """Wait for the server to accept connections, then open the browser once."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_is_open(host, port):
            webbrowser.open(url)
            return
        time.sleep(0.1)
    # If the server never came up we still try, so the user sees something.
    webbrowser.open(url)


def main() -> int:
    host = "127.0.0.1"

    try:
        import uvicorn
    except ModuleNotFoundError:
        print(
            "The desktop app is missing its web dependencies. Rebuild it "
            "with the 'web' extra installed."
        )
        return 1

    from benefit_finder.web.app import app

    port = _free_port(host)
    url = f"http://{host}:{port}/"

    print("Benefit Finder is running. It should open in your web browser.", flush=True)
    print(f"If it does not, open this address yourself: {url}", flush=True)
    print("To quit Benefit Finder, close this window.", flush=True)

    threading.Thread(
        target=_open_browser_when_ready,
        args=(url, host, port),
        daemon=True,
    ).start()

    # Pass the app object directly (not an import string) so this works
    # inside a frozen PyInstaller bundle where reload is never used.
    uvicorn.run(app, host=host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
