"""The `pasteup` command: serve the app locally."""

from __future__ import annotations

import argparse
import sys

from pasteup import __version__

LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="pasteup",
        description="Turn a folder of clip art into listing images. Serves the app in your browser.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="address to listen on (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="port to listen on (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="restart on code changes, for development")
    parser.add_argument("--version", action="version", version=f"pasteup {__version__}")
    args = parser.parse_args(argv)

    if args.host not in LOCAL_HOSTS:
        print(
            f"Warning: listening on {args.host} lets other machines reach an app that reads and "
            "writes your files, with no login. See SECURITY.md before doing this.",
            file=sys.stderr,
        )

    # Imported here so `pasteup --help` and `--version` stay instant.
    import uvicorn

    uvicorn.run("pasteup.main:app", host=args.host, port=args.port, reload=args.reload)
