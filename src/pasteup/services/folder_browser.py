"""Listing folders for the folder browser in the UI.

A page cannot learn the path of a folder picked with the browser's own file
chooser, and Pasteup needs paths: it reads the images where they are and writes
its results next to them. So the page browses the disk through these listings.
"""

from __future__ import annotations

import os
import stat
import string
import sys
from collections.abc import Iterator
from pathlib import Path

from pasteup.services.folder_scanner import SUPPORTED_EXTENSIONS, is_generated_output_folder

# Offered as shortcuts when the home folder has them.
STANDARD_FOLDER_NAMES = ("Desktop", "Documents", "Downloads", "Pictures")

_ON_WINDOWS = os.name == "nt"
# Windows hides its own folders (AppData, $Recycle.Bin, System Volume
# Information) with these attributes rather than a leading dot.
_HIDDEN_ATTRIBUTES = stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM


def browse_folder(folder_path: str = "") -> dict[str, object]:
    """List the folders inside ``folder_path`` and count its images.

    A blank path starts at the home folder. A folder that cannot be listed
    gives way to the nearest one above it that can, with a message saying why,
    so the browser always has somewhere to show.
    """
    home = _home_folder()
    requested = folder_path.strip() if isinstance(folder_path, str) else ""
    target = _absolute_path(requested) if requested else home

    message = ""
    shown, folder_names, image_count = target, [], 0
    for candidate in _folders_to_try(target, home):
        try:
            folder_names, image_count = _read_folder(candidate)
        except (OSError, ValueError) as exc:
            message = message or _describe_unreadable_folder(target, exc)
            continue
        shown = candidate
        break

    parent = shown.parent
    return {
        "path": str(shown),
        "parent_path": str(parent) if parent != shown else None,
        "breadcrumbs": [_link(folder) for folder in (*reversed(shown.parents), shown)],
        "folders": [{"name": name, "path": str(shown / name)} for name in folder_names],
        "image_count": image_count,
        "places": list_places(home),
        "message": message,
    }


def list_places(home: Path) -> list[dict[str, str]]:
    """Shortcuts: home, its standard folders, and on Windows each drive."""
    places = [{"name": "Home", "path": str(home)}]
    places.extend(_link(home / name) for name in STANDARD_FOLDER_NAMES if os.path.isdir(home / name))
    places.extend(_link(Path(root)) for root in _drive_roots())
    return places


def _link(folder: Path) -> dict[str, str]:
    # A root has no name of its own: show it as "/" or "C:\".
    return {"name": folder.name or str(folder), "path": str(folder)}


def _read_folder(folder: Path) -> tuple[list[str], int]:
    """The visible folders inside ``folder``, and how many images it holds.

    Images are counted as the scan counts them, as supported files directly
    inside, so the number shown matches what the scan then finds.
    """
    folder_names: list[str] = []
    image_count = 0
    with os.scandir(folder) as entries:
        for entry in entries:
            try:
                if entry.is_dir():
                    if not _is_hidden(entry) and not is_generated_output_folder(Path(entry.name)):
                        folder_names.append(entry.name)
                elif entry.is_file() and Path(entry.name).suffix.lower() in SUPPORTED_EXTENSIONS:
                    image_count += 1
            except OSError:
                continue
    return sorted(folder_names, key=lambda name: (name.lower(), name)), image_count


def _is_hidden(entry: os.DirEntry) -> bool:
    if entry.name.startswith("."):
        return True
    if not _ON_WINDOWS:
        return False
    # Not following links, so a hidden junction such as "Documents and
    # Settings" is judged by itself rather than by the folder it points to.
    return bool(entry.stat(follow_symlinks=False).st_file_attributes & _HIDDEN_ATTRIBUTES)


def _folders_to_try(target: Path, home: Path) -> Iterator[Path]:
    """``target``, then each folder above it, then home."""
    yield target
    yield from target.parents
    if home != target and home not in target.parents:
        yield home


def _describe_unreadable_folder(folder: Path, exc: Exception) -> str:
    if isinstance(exc, (FileNotFoundError, NotADirectoryError)):
        return f"There's no folder at {folder}, so this is the nearest one that exists."
    if isinstance(exc, PermissionError):
        message = f"Pasteup isn't allowed to open {folder}."
        if sys.platform == "darwin":
            message += (
                " To let it, turn on access for your terminal app under System Settings ›"
                " Privacy & Security › Files and Folders."
            )
        return message
    reason = getattr(exc, "strerror", None) or str(exc)
    return f"Couldn't open {folder} ({reason})."


def _absolute_path(folder_path: str) -> Path:
    # Not resolved: a link such as ~/Dropbox stays where the user found it
    # rather than jumping to wherever it points.
    return Path(os.path.abspath(os.path.expanduser(folder_path)))


def _home_folder() -> Path:
    try:
        return Path.home()
    except (RuntimeError, KeyError):
        return Path(Path.cwd().anchor)


def _drive_roots() -> list[str]:
    """Each drive's root on Windows, since nothing above C:\\ leads to D:\\."""
    if not _ON_WINDOWS:
        return []
    try:
        if hasattr(os, "listdrives"):  # Python 3.12+
            return sorted(os.listdrives())
        import ctypes

        present = ctypes.windll.kernel32.GetLogicalDrives()
    except (OSError, AttributeError):
        return []
    return [f"{letter}:\\" for index, letter in enumerate(string.ascii_uppercase) if present >> index & 1]
