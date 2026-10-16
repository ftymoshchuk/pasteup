import os
import stat
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from pasteup.main import app
from pasteup.services import folder_browser
from pasteup.services.folder_scanner import scan_folder

client = TestClient(app)


def _browse(folder_path: str) -> dict:
    response = client.post("/api/jobs/browse-folder", json={"folder_path": folder_path})
    assert response.status_code == 200
    return response.json()


def _names(links: list[dict]) -> list[str]:
    return [link["name"] for link in links]


def test_lists_the_folders_inside_and_counts_the_images(tmp_path: Path) -> None:
    for name in ("bundle-b", "Bundle A", "bundle-c", ".git", "---Created---"):
        (tmp_path / name).mkdir()
    for name in ("one.png", "two.JPG", "three.webp", "notes.txt"):
        (tmp_path / name).write_bytes(b"fake")

    listing = _browse(str(tmp_path))

    assert listing["path"] == str(tmp_path)
    # Hidden folders and Pasteup's own output folder are left out.
    assert listing["folders"] == [
        {"name": name, "path": str(tmp_path / name)} for name in ("Bundle A", "bundle-b", "bundle-c")
    ]
    assert listing["image_count"] == 3
    assert listing["image_count"] == scan_folder(str(tmp_path))["image_count"]
    assert listing["message"] == ""


def test_shows_the_way_up_from_the_top_of_the_drive(tmp_path: Path) -> None:
    folder = tmp_path / "clip-art" / "bundle-01"
    folder.mkdir(parents=True)

    listing = _browse(str(folder))

    assert listing["parent_path"] == str(folder.parent)
    assert listing["breadcrumbs"][0] == {"name": folder.anchor, "path": folder.anchor}
    assert listing["breadcrumbs"][-2:] == [
        {"name": "clip-art", "path": str(folder.parent)},
        {"name": "bundle-01", "path": str(folder)},
    ]
    assert len(listing["breadcrumbs"]) == len(folder.parts)


def test_the_top_of_the_drive_has_no_parent() -> None:
    root = Path.cwd().anchor

    listing = _browse(root)

    assert listing["path"] == root
    assert listing["parent_path"] is None
    assert listing["breadcrumbs"] == [{"name": root, "path": root}]


def test_a_blank_path_starts_at_home(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "Pictures").mkdir()

    listing = _browse("  ")

    assert listing["path"] == str(tmp_path)
    assert _names(listing["folders"]) == ["Pictures"]


def test_a_home_relative_path_is_expanded(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "Pictures" / "clip-art").mkdir(parents=True)

    assert _browse("~/Pictures")["path"] == str(tmp_path / "Pictures")


def test_a_missing_folder_shows_the_nearest_one_that_exists(tmp_path: Path) -> None:
    """A typo in the folder field opens the browser as close to it as it can."""
    (tmp_path / "clip-art").mkdir()
    typo = tmp_path / "clip-art" / "bundel-01" / "deeper"

    listing = _browse(str(typo))

    assert listing["path"] == str(tmp_path / "clip-art")
    assert listing["message"] == f"There's no folder at {typo}, so this is the nearest one that exists."


def test_a_file_shows_the_folder_it_is_in(tmp_path: Path) -> None:
    image = tmp_path / "one.png"
    image.write_bytes(b"fake")

    listing = _browse(str(image))

    assert listing["path"] == str(tmp_path)
    assert listing["image_count"] == 1
    assert "no folder at" in listing["message"]


def test_a_folder_it_may_not_open_gives_way_to_the_one_above(tmp_path: Path, monkeypatch) -> None:
    locked = tmp_path / "Desktop"
    locked.mkdir()
    real_scandir = os.scandir

    def scandir(path):
        if Path(path) == locked:
            raise PermissionError(1, "Operation not permitted", str(path))
        return real_scandir(path)

    monkeypatch.setattr(folder_browser.os, "scandir", scandir)

    listing = _browse(str(locked))

    assert listing["path"] == str(tmp_path)
    assert listing["message"].startswith(f"Pasteup isn't allowed to open {locked}.")


def test_a_linked_folder_keeps_the_path_it_was_opened_by(tmp_path: Path) -> None:
    """~/Dropbox stays ~/Dropbox, rather than jumping to where the link points."""
    target = tmp_path / "Library" / "CloudStorage" / "Dropbox"
    target.mkdir(parents=True)
    link = tmp_path / "Dropbox"
    link.symlink_to(target, target_is_directory=True)

    listing = _browse(str(link))

    assert listing["path"] == str(link)
    assert listing["breadcrumbs"][-1] == {"name": "Dropbox", "path": str(link)}


def test_places_are_home_and_the_standard_folders_it_has(tmp_path: Path, monkeypatch) -> None:
    for name in ("Pictures", "Desktop", "Music"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(folder_browser, "_drive_roots", lambda: ["C:\\", "D:\\"])

    places = folder_browser.list_places(tmp_path)

    assert places == [
        {"name": "Home", "path": str(tmp_path)},
        {"name": "Desktop", "path": str(tmp_path / "Desktop")},
        {"name": "Pictures", "path": str(tmp_path / "Pictures")},
        {"name": "C:\\", "path": "C:\\"},
        {"name": "D:\\", "path": "D:\\"},
    ]


def test_windows_hidden_and_system_folders_are_left_out(monkeypatch) -> None:
    monkeypatch.setattr(folder_browser, "_ON_WINDOWS", True)

    def entry(name: str, attributes: int = 0) -> SimpleNamespace:
        result = SimpleNamespace(st_file_attributes=attributes)
        return SimpleNamespace(name=name, stat=lambda follow_symlinks=True: result)

    assert folder_browser._is_hidden(entry("AppData", stat.FILE_ATTRIBUTE_HIDDEN))
    assert folder_browser._is_hidden(entry("$Recycle.Bin", stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM))
    assert folder_browser._is_hidden(entry(".cache"))
    assert not folder_browser._is_hidden(entry("Pictures", stat.FILE_ATTRIBUTE_DIRECTORY))
