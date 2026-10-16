"""`pasteup --shortcut`: a launcher that starts Pasteup with a double-click.

The launcher runs this installation's Python by its full path, so it works
without a terminal or a PATH set up for `pasteup`. Run the command again after
moving or reinstalling Pasteup somewhere else.
"""

from __future__ import annotations

import os
import shlex
import sys
from importlib.resources import files
from pathlib import Path

NOTE = "Starts Pasteup. Made by `pasteup --shortcut`; run that again if Pasteup moves."


def create_shortcut(platform: str | None = None) -> str:
    """Write a launcher for this platform and return a sentence saying where it is."""
    platform = platform or sys.platform

    if platform == "darwin":
        # Double-clicking a .command file runs it in Terminal.
        path = _existing_dir(Path.home() / "Desktop") / "Pasteup.command"
        _write(path, f"#!/bin/sh\n# {NOTE}\nexec {shlex.quote(sys.executable)} -m pasteup\n", executable=True)
        return f"Made {path}. Double-click it to start Pasteup."

    if platform == "win32":
        path = _windows_desktop() / "Pasteup.bat"
        python = sys.executable.replace("%", "%%")
        # chcp 65001 makes cmd read the rest as UTF-8, for a path with accents in
        # it; the pause keeps an error on screen instead of closing the window.
        script = (
            f'@echo off\r\nchcp 65001 >nul\r\nrem {NOTE}\r\n"{python}" -m pasteup\r\nif errorlevel 1 pause\r\n'
        )
        _write(path, script)
        return f"Made {path}. Double-click it to start Pasteup."

    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    path = data_home / "applications" / "pasteup.desktop"
    _write(path, _desktop_entry(), executable=True)
    return f"Added Pasteup to your applications menu ({path})."


def _desktop_entry() -> str:
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Name=Pasteup",
        "Comment=Turn a folder of clip art into listing images",
        f"Exec={_desktop_exec_argument(sys.executable)} -m pasteup",
        "Terminal=true",
        "Categories=Graphics;",
    ]
    icon = Path(str(files("pasteup") / "static" / "favicon.svg"))
    if icon.is_file():
        lines.append(f"Icon={icon}")
    return "\n".join(lines) + "\n"


def _desktop_exec_argument(value: str) -> str:
    """Quote one Exec argument as the desktop entry specification requires."""
    for reserved in ("\\", '"', "`", "$"):
        value = value.replace(reserved, "\\" + reserved)
    # "%" starts a field code, and the value as a whole escapes backslashes again.
    return f'"{value}"'.replace("%", "%%").replace("\\", "\\\\")


def _windows_desktop() -> Path:
    # The Desktop folder can be moved, most often into OneDrive; the registry
    # says where it is now.
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        ) as key:
            desktop = Path(os.path.expandvars(winreg.QueryValueEx(key, "Desktop")[0]))
        if desktop.is_dir():
            return desktop
    except (ImportError, OSError):
        pass
    return _existing_dir(Path.home() / "Desktop")


def _existing_dir(preferred: Path) -> Path:
    return preferred if preferred.is_dir() else Path.home()


def _write(path: Path, content: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="" keeps the line endings written above, CRLF included.
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(content)
    if executable:
        path.chmod(0o755)
