from pathlib import Path

from app.models.schemas import ScanRequest
from app.routes.jobs import scan_folder_job


def test_scan_folder_valid_directory_under_12_images_returns_zero_estimated_pages(tmp_path: Path) -> None:
    """A valid directory with fewer than 12 images should estimate zero full pages."""
    (tmp_path / "one.jpg").write_bytes(b"fake-jpg")
    (tmp_path / "two.png").write_bytes(b"fake-png")

    payload = ScanRequest(folder_path=str(tmp_path))
    response = scan_folder_job(payload)
    data = response.model_dump()

    assert data["valid"] is True
    assert data["image_count"] == 2
    assert data["estimated_pages"] == 0
    assert data["available_subfolders"] == []
    assert isinstance(data["estimated_pages"], int)
    assert list(data.keys()).count("estimated_pages") == 1


def test_scan_folder_accepts_tilde_expansion(tmp_path: Path, monkeypatch) -> None:
    """The scan job should accept a home-relative path and expand '~' correctly."""
    fake_home = tmp_path / "fake_home"
    photos_dir = fake_home / "photos"
    photos_dir.mkdir(parents=True)
    (photos_dir / "sample.webp").write_bytes(b"fake-webp")

    monkeypatch.setenv("HOME", str(fake_home))

    payload = ScanRequest(folder_path="~/photos")
    response = scan_folder_job(payload)
    data = response.model_dump()

    assert data["valid"] is True
    assert data["image_count"] == 1
    assert data["estimated_pages"] == 0
    assert data["available_subfolders"] == []


def test_scan_folder_invalid_path_returns_controlled_non_exception_payload() -> None:
    """Typo-like invalid paths should return a controlled payload instead of blowing up."""
    payload = ScanRequest(folder_path="~/Downalods/not-a-real-folder")

    response = scan_folder_job(payload)
    data = response.model_dump()

    assert data["valid"] is False
    assert data["estimated_pages"] == 0
    assert data["available_subfolders"] == []
    assert "Folder not found" in data["message"]


def test_scan_folder_blank_path_does_not_scan_the_working_directory(tmp_path: Path, monkeypatch) -> None:
    """A blank path resolves to the server's cwd; the scan must refuse it instead."""
    (tmp_path / "cwd_image.png").write_bytes(b"fake-png")
    monkeypatch.chdir(tmp_path)

    response = scan_folder_job(ScanRequest(folder_path="   "))
    data = response.model_dump()

    assert data["valid"] is False
    assert data["image_count"] == 0
    assert data["message"] == "Enter a folder path to scan."


def test_scan_folder_estimates_only_full_pages(tmp_path: Path) -> None:
    for index in range(13):
        (tmp_path / f"image_{index:02}.png").write_bytes(b"fake-png")

    payload = ScanRequest(folder_path=str(tmp_path))
    response = scan_folder_job(payload)
    data = response.model_dump()

    assert data["valid"] is True
    assert data["image_count"] == 13
    assert data["estimated_pages"] == 1
    assert data["available_subfolders"] == []


def test_scan_folder_returns_available_subfolders_when_top_level_has_no_images(tmp_path: Path) -> None:
    first_bundle = tmp_path / "Bundle A"
    second_bundle = tmp_path / "bundle-b"
    first_bundle.mkdir()
    second_bundle.mkdir()
    (first_bundle / "image_01.jpg").write_bytes(b"fake-jpg")

    payload = ScanRequest(folder_path=str(tmp_path))
    response = scan_folder_job(payload)
    data = response.model_dump()

    assert data["valid"] is False
    assert data["image_count"] == 0
    assert data["estimated_pages"] == 0
    assert data["sample_files"] == []
    assert data["available_subfolders"] == [
        {"display_name": first_bundle.name, "full_path": str(first_bundle.resolve())},
        {"display_name": second_bundle.name, "full_path": str(second_bundle.resolve())},
    ]
    assert "top level" in data["message"]
    assert "subfolders" in data["message"]



def test_scan_folder_excludes_generated_output_subfolders_from_available_choices(tmp_path: Path) -> None:
    source_bundle = tmp_path / "Bundle A"
    source_bundle.mkdir()
    (source_bundle / "image_01.jpg").write_bytes(b"fake-jpg")

    generated_output = tmp_path / "---Created---"
    generated_output.mkdir()
    (generated_output / "page_001.png").write_bytes(b"fake-png")

    payload = ScanRequest(folder_path=str(tmp_path))
    response = scan_folder_job(payload)
    data = response.model_dump()

    assert data["valid"] is False
    assert data["available_subfolders"] == [
        {"display_name": source_bundle.name, "full_path": str(source_bundle.resolve())}
    ]

def test_scan_folder_empty_folder_has_no_images_and_no_subfolders(tmp_path: Path) -> None:
    payload = ScanRequest(folder_path=str(tmp_path))
    response = scan_folder_job(payload)
    data = response.model_dump()

    assert data["valid"] is False
    assert data["image_count"] == 0
    assert data["available_subfolders"] == []
    assert data["message"] == "No supported image files found (.jpg, .jpeg, .png, .webp)."
