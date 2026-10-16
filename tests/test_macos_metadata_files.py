"""A bundle on a drive a Mac has written to.

A drive that can't hold macOS's file metadata itself (exFAT, FAT32, some network
shares) gets it as a hidden "._name" file beside each file copied there, and
macOS adds hidden folders of its own (.Spotlight-V100, .Trashes, .fseventsd). A zip
made on a Mac carries the same "._" files in a __MACOSX folder, which appears
when the zip is unpacked anywhere else. None of it is clip art.
"""

from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from pasteup.main import app
from pasteup.services.folder_scanner import list_supported_image_paths

client = TestClient(app)

MACOS_FOLDERS = (".Spotlight-V100", ".Trashes", ".fseventsd", "__MACOSX")


def _image(path: Path) -> None:
    Image.new("RGB", (40, 30), (200, 80, 60)).save(path)


def _apple_double(path: Path) -> None:
    # What macOS writes: the AppleDouble magic number and version, then filler.
    path.write_bytes(b"\x00\x05\x16\x07\x00\x02\x00\x00Mac OS X        ".ljust(4096, b"\x00"))


def _bundle_copied_by_a_mac(folder: Path, image_count: int) -> Path:
    folder.mkdir(parents=True)
    for index in range(image_count):
        _image(folder / f"art_{index:02}.png")
        _apple_double(folder / f"._art_{index:02}.png")
    return folder


def test_the_scan_counts_only_the_images(tmp_path: Path) -> None:
    bundle = _bundle_copied_by_a_mac(tmp_path / "bundle", 12)

    data = client.post("/api/jobs/scan-folder", json={"folder_path": str(bundle)}).json()

    assert data["image_count"] == 12
    assert data["estimated_pages"] == 1
    assert data["sample_files"] == [f"art_{index:02}.png" for index in range(5)]


def test_sheets_do_not_report_the_metadata_as_unreadable_images(tmp_path: Path) -> None:
    bundle = _bundle_copied_by_a_mac(tmp_path / "bundle", 12)

    data = client.post(
        "/api/jobs/generate",
        json={
            "folder_path": str(bundle),
            "output_path": str(tmp_path / "out"),
            "page_width": 400,
            "page_height": 300,
            "gap": 4,
            "margin": 4,
            "format": "PNG",
        },
    ).json()

    assert data["pages_generated"] == 1
    assert data["total_images"] == 12
    assert data["images_skipped"] == 0


def test_a_cover_draws_on_no_hidden_file_or_folder(tmp_path: Path) -> None:
    """Covers look through every folder inside, where hidden ones hold copies."""
    bundle = _bundle_copied_by_a_mac(tmp_path / "bundle", 2)
    _bundle_copied_by_a_mac(bundle / "extras", 1)
    for name in (".thumbnails", "__MACOSX", "---Created---"):
        (bundle / name).mkdir()
        _image(bundle / name / "art_00.png")

    found = list_supported_image_paths(bundle, recursive=True)

    assert sorted(found) == [bundle / "art_00.png", bundle / "art_01.png", bundle / "extras" / "art_00.png"]


def test_macos_folders_are_not_offered_as_bundles(tmp_path: Path) -> None:
    parent = tmp_path / "drive"
    bundle = _bundle_copied_by_a_mac(parent / "bundle-01", 12)
    for name in MACOS_FOLDERS:
        (parent / name).mkdir()
    _apple_double(parent / "__MACOSX" / "._bundle-01")

    scan = client.post("/api/jobs/scan-folder", json={"folder_path": str(parent)}).json()
    assert scan["available_subfolders"] == [{"display_name": "bundle-01", "full_path": str(bundle)}]

    created_root = parent / "---Created---"
    sheets = client.post(
        "/api/jobs/generate-all-folders",
        json={
            "parent_folder_path": str(parent),
            "created_output_root_path": str(created_root),
            "page_width": 400,
            "page_height": 300,
            "gap": 4,
            "margin": 4,
            "format": "PNG",
        },
    ).json()
    assert sheets["total_detected_folders"] == 1
    assert [result["folder_name"] for result in sheets["bundle_results"]] == ["bundle-01"]

    picked_anyway = client.post(
        "/api/jobs/scan-selected-batch-folders",
        json={"parent_folder_path": str(parent), "selected_subfolders": [str(parent / "__MACOSX")]},
    )
    assert picked_anyway.status_code == 400


def test_the_folder_browser_counts_and_lists_as_the_scan_does(tmp_path: Path) -> None:
    parent = tmp_path / "drive"
    bundle = _bundle_copied_by_a_mac(parent / "bundle-01", 12)
    for name in MACOS_FOLDERS:
        (parent / name).mkdir()

    def browse(folder: Path) -> dict:
        return client.post("/api/jobs/browse-folder", json={"folder_path": str(folder)}).json()

    assert browse(bundle)["image_count"] == 12
    assert [folder["name"] for folder in browse(parent)["folders"]] == ["bundle-01"]
