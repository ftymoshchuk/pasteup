"""The `pasteup` command: start the app and open it in the browser."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

from pasteup import __version__

LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
WILDCARD_HOSTS = {"0.0.0.0": "127.0.0.1", "::": "::1"}
DEFAULT_PORT = 8000
# Ports tried after the default when another program holds it.
FALLBACK_PORTS = 10
BROWSER_WAIT_SECONDS = 20

# Asking the local server must not go through a proxy set in the environment.
_local_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="pasteup",
        description="Turn a folder of clip art into listing images. Starts the app and opens it in your browser.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="address to listen on (default: 127.0.0.1)")
    parser.add_argument(
        "--port", type=_port_number, help=f"port to listen on (default: {DEFAULT_PORT}, or the next free one)"
    )
    parser.add_argument("--no-browser", action="store_true", help="don't open the app in a browser")
    parser.add_argument(
        "--shortcut", action="store_true", help="put a Pasteup launcher on your desktop, then exit"
    )
    parser.add_argument("--reload", action="store_true", help="restart on code changes, for development")
    parser.add_argument("--version", action="version", version=f"pasteup {__version__}")
    args = parser.parse_args(argv)

    if args.shortcut:
        from pasteup.shortcut import create_shortcut

        print(create_shortcut())
        return

    if args.host not in LOCAL_HOSTS:
        print(
            f"Warning: listening on {args.host} lets other machines reach an app that reads and "
            "writes your files, with no login. See SECURITY.md before doing this.",
            file=sys.stderr,
        )

    visit_host = WILDCARD_HOSTS.get(args.host, args.host)
    open_browser = not args.no_browser and _can_open_browser(visit_host)
    port, state = _choose_port(visit_host, args.port)
    url = _base_url(visit_host, port)

    if state == "pasteup":
        print(f"Pasteup is already running at {url}")
        if open_browser:
            webbrowser.open(url)
        return

    if port != (args.port or DEFAULT_PORT):
        print(f"Port {DEFAULT_PORT} is taken by another program, so Pasteup is using {port}.")
    print(f"Pasteup is running at {url}")
    if open_browser:
        print("Opening it in your browser...")
        _open_when_ready(url)
    else:
        print("Open that address in your browser.")
    print("Keep this window open while you use Pasteup; press Ctrl+C to stop it.")
    if shutil.which("ffmpeg") is None:
        print(
            "Note: preview videos need ffmpeg (https://ffmpeg.org), which isn't installed. "
            "Everything else works."
        )
    sys.stdout.flush()

    # Imported here so `pasteup --help` and `--version` stay instant.
    import uvicorn

    uvicorn.run(
        "pasteup.main:app",
        host=args.host,
        port=port,
        reload=args.reload,
        # Errors only, unless developing: request logs mean nothing to a user.
        log_level="info" if args.reload else "warning",
    )
    print("Pasteup has stopped.")


def _port_number(value: str) -> int:
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("must be between 1 and 65535")
    return port


def _choose_port(host: str, requested_port: int | None) -> tuple[int, str]:
    """Return the port to use, and "pasteup" when Pasteup already runs there."""
    if requested_port is not None:
        state = _probe(host, requested_port)
        if state == "busy":
            sys.exit(f"Port {requested_port} is in use by another program. Choose a different one with --port.")
        return requested_port, state

    for port in range(DEFAULT_PORT, DEFAULT_PORT + FALLBACK_PORTS + 1):
        state = _probe(host, port)
        if state != "busy":
            return port, state
    sys.exit(
        f"Ports {DEFAULT_PORT} to {DEFAULT_PORT + FALLBACK_PORTS} are all in use by other programs. "
        "Choose a free one with --port."
    )


def _probe(host: str, port: int) -> str:
    """Say whether a port is "free", has Pasteup on it ("pasteup") or another program ("busy")."""
    try:
        with socket.create_connection((host, port), timeout=0.5):
            pass
    except OSError:
        return "free"
    return "pasteup" if _answers_as_pasteup(_base_url(host, port)) else "busy"


def _answers_as_pasteup(url: str) -> bool:
    try:
        with _local_opener.open(f"{url}api/jobs/health", timeout=2) as response:
            return json.load(response).get("app") == "pasteup"
    except (OSError, ValueError, AttributeError):
        return False


def _open_when_ready(url: str) -> None:
    """Open the browser once the server answers, without holding up its start."""
    threading.Thread(target=_wait_then_open, args=(url,), daemon=True).start()


def _wait_then_open(url: str, timeout: float = BROWSER_WAIT_SECONDS) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _answers_as_pasteup(url):
            webbrowser.open(url)
            return
        time.sleep(0.25)


def _can_open_browser(host: str) -> bool:
    # A browser on this machine can reach only a server listening on it.
    if host not in LOCAL_HOSTS:
        return False
    if os.environ.get("BROWSER"):
        return True
    # Without a display, Python falls back to text browsers such as lynx, which
    # would take over this terminal.
    if sys.platform.startswith(("linux", "freebsd", "openbsd", "netbsd")):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True


def _base_url(host: str, port: int) -> str:
    return f"http://[{host}]:{port}/" if ":" in host else f"http://{host}:{port}/"
