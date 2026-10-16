from pathlib import Path

from PIL import Image
import pytest
from fastapi import HTTPException

from app.models.schemas import SelectedBatchFolderValidationRequest
from app.routes.jobs import scan_selected_batch_folders_job


def _create_image(path: Path) -> None:
    Image.new("RGB", (100, 120), color="white").save(path, format="PNG")


def test_selected_batch_folder_validation_reports_valid_and_skipped_folders(tmp_path: Path) -> None:
    parent = tmp_path / "---Listing Images---"
    parent.mkdir()

    valid_bundle = parent / "00001. Ready Bundle"
    valid_bundle.mkdir()
    for index in range(12):
        _create_image(valid_bundle / f"img_{index:03}.png")

    empty_bundle = parent / "00002. Empty Bundle"
    empty_bundle.mkdir()

    nested_only_bundle = parent / "00003. Nested Only Bundle"
    nested_only_bundle.mkdir()
    nested_child = nested_only_bundle / "child"
    nested_child.mkdir()
    _create_image(nested_child / "nested.png")

    payload = SelectedBatchFolderValidationRequest(
        parent_folder_path=str(parent),
        selected_subfolders=[str(valid_bundle), str(empty_bundle), str(nested_only_bundle)],
    )

    result = scan_selected_batch_folders_job(payload)

    assert result.parent_folder_path == str(parent)
    assert result.selected_folders == 3
    assert result.valid_selected_folders == 1
    assert result.invalid_selected_folders == 2
    assert [folder.display_name for folder in result.scanned_folders] == [valid_bundle.name]
    assert result.scanned_folders[0].image_count == 12
    assert [folder.display_name for folder in result.skipped_folders] == [empty_bundle.name, nested_only_bundle.name]
    assert result.skipped_folders[0].message == "No supported image files found (.jpg, .jpeg, .png, .webp)."
    assert result.skipped_folders[1].message == (
        "No supported image files were found at the top level, "
        "but direct subfolders are available to scan."
    )
    assert result.message == "Validated 1 of 3 selected folder(s). Skipped 2 folder(s)."



def test_selected_batch_folder_validation_request_accepts_legacy_alias() -> None:
    payload = SelectedBatchFolderValidationRequest.model_validate(
        {
            "parent_folder_path": "/tmp/input",
            "selected_subfolder_paths": [" /tmp/input/a ", "/tmp/input/a", "/tmp/input/b"],
        }
    )

    assert payload.selected_subfolders == ["/tmp/input/a", "/tmp/input/b"]



def test_selected_batch_folder_validation_rejects_unknown_folder(tmp_path: Path) -> None:
    parent = tmp_path / "---Listing Images---"
    parent.mkdir()

    valid_bundle = parent / "00001. Ready Bundle"
    valid_bundle.mkdir()
    for index in range(3):
        _create_image(valid_bundle / f"img_{index:03}.png")

    missing_bundle = parent / "00002. Missing Bundle"

    payload = SelectedBatchFolderValidationRequest(
        parent_folder_path=str(parent),
        selected_subfolders=[str(valid_bundle), str(missing_bundle)],
    )

    with pytest.raises(HTTPException) as exc_info:
        scan_selected_batch_folders_job(payload)

    assert exc_info.value.status_code == 400
    assert "does not exist or is not a directory" in str(exc_info.value.detail)


def test_selected_batch_folder_validation_rejects_generated_output_folder(tmp_path: Path) -> None:
    parent = tmp_path / "---Listing Images---"
    parent.mkdir()

    valid_bundle = parent / "00001. Ready Bundle"
    valid_bundle.mkdir()
    _create_image(valid_bundle / "img_000.png")

    generated_output = parent / "---Created---"
    generated_output.mkdir()
    _create_image(generated_output / "page_001.png")

    payload = SelectedBatchFolderValidationRequest(
        parent_folder_path=str(parent),
        selected_subfolders=[str(valid_bundle), str(generated_output)],
    )

    with pytest.raises(HTTPException) as exc_info:
        scan_selected_batch_folders_job(payload)

    assert exc_info.value.status_code == 400
    assert "generated-output directory" in str(exc_info.value.detail)
