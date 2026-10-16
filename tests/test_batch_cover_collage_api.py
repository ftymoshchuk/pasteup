from pathlib import Path

import pytest
from PIL import Image
from fastapi import HTTPException

from pasteup.models.schemas import BatchCoverCollageGenerationRequest
from pasteup.routes.jobs import generate_cover_collage_batch_job


def _create_image(path: Path, color: tuple[int, int, int]) -> None:
    Image.new("RGB", (320, 480), color=color).save(path, format="PNG")


def test_generate_cover_collage_batch_builds_one_collage_per_selected_folder(tmp_path: Path) -> None:
    parent = tmp_path / "---Listing Images---"
    parent.mkdir()

    first_bundle = parent / "00001. Bundle One"
    first_bundle.mkdir()
    _create_image(first_bundle / "one.png", (255, 0, 0))
    _create_image(first_bundle / "two.png", (0, 255, 0))

    second_bundle = parent / "00002. Bundle Two"
    second_bundle.mkdir()
    _create_image(second_bundle / "three.png", (0, 0, 255))
    _create_image(second_bundle / "four.png", (255, 255, 0))

    created_root = parent / "---Created---"
    created_root.mkdir()

    payload = BatchCoverCollageGenerationRequest(
        parent_folder_path=str(parent),
        created_output_root_path=str(created_root),
        selected_subfolders=[str(first_bundle), str(second_bundle)],
        page_width=1200,
        page_height=1200,
        format="png",
        collage_template="randomized-grid",
        image_fit="contain",
    )

    result = generate_cover_collage_batch_job(payload)

    assert result.success is True
    assert result.processed_folders == 2
    assert result.selected_folders == 2
    assert result.total_detected_folders == 2
    assert result.generated_folders == 2
    assert result.created_output_root_path == str(created_root)
    assert result.message == (
        "Detected 2 eligible folder(s) under the parent. "
        "Processed 2 selected folder(s). "
        "Generated cover collages for 2 folder(s)."
    )
    assert [bundle.folder_name for bundle in result.bundle_results] == [
        first_bundle.name,
        second_bundle.name,
    ]
    assert all(bundle.success for bundle in result.bundle_results)
    assert all(bundle.pages_generated == 1 for bundle in result.bundle_results)
    assert all(bundle.output_files for bundle in result.bundle_results)
    assert result.bundle_results[0].output_path == str(created_root / first_bundle.name)
    assert result.bundle_results[0].output_files == [
        str(created_root / first_bundle.name / "cover_collage_001.png")
    ]
    assert result.bundle_results[1].output_path == str(created_root / second_bundle.name)
    assert result.bundle_results[1].output_files == [
        str(created_root / second_bundle.name / "cover_collage_001.png")
    ]
    assert (created_root / first_bundle.name / "cover_collage_001.png").exists()
    assert (created_root / second_bundle.name / "cover_collage_001.png").exists()


def test_generate_cover_collage_batch_uses_child_output_folder_and_preserves_standard_pages(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "---Listing Images---"
    parent.mkdir()

    bundle = parent / "00001. Bundle One"
    bundle.mkdir()
    _create_image(bundle / "one.png", (255, 0, 0))
    _create_image(bundle / "two.png", (0, 255, 0))

    created_root = parent / "---Created---"
    bundle_output = created_root / bundle.name
    bundle_output.mkdir(parents=True)
    standard_page = bundle_output / "page_001.png"
    standard_page.write_bytes(b"existing standard page export")

    payload = BatchCoverCollageGenerationRequest(
        parent_folder_path=str(parent),
        created_output_root_path=str(created_root),
        selected_subfolders=[str(bundle)],
        page_width=1200,
        page_height=1200,
        format="png",
        collage_template="randomized-grid",
        image_fit="contain",
    )

    result = generate_cover_collage_batch_job(payload)

    assert result.bundle_results[0].output_path == str(bundle_output)
    assert result.bundle_results[0].output_files == [str(bundle_output / "cover_collage_001.png")]
    assert (bundle_output / "cover_collage_001.png").exists()
    assert standard_page.read_bytes() == b"existing standard page export"


@pytest.mark.parametrize("field_name", ["created_output_root_path", "output_root_path"])
def test_batch_cover_collage_request_accepts_output_root_alias(field_name: str) -> None:
    payload = BatchCoverCollageGenerationRequest.model_validate(
        {
            "parent_folder_path": "/tmp/input",
            field_name: "/tmp/output",
            "selected_subfolder_paths": [" /tmp/input/a ", "/tmp/input/a", "/tmp/input/b"],
            "page_width": 1200,
            "page_height": 1600,
            "format": "jpg",
            "collage_template": "feature-spread",
            "image_fit": "contain",
        }
    )

    assert payload.created_output_root_path == "/tmp/output"
    assert payload.selected_subfolders == ["/tmp/input/a", "/tmp/input/b"]
    assert payload.format == "JPG"


def test_generate_cover_collage_batch_rejects_selected_folder_outside_parent(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / "inside").mkdir()

    outside = tmp_path / "outside"
    outside.mkdir()
    _create_image(outside / "one.png", (255, 0, 0))

    payload = BatchCoverCollageGenerationRequest(
        parent_folder_path=str(parent),
        created_output_root_path=str(parent / "output"),
        selected_subfolders=[str(outside)],
        page_width=1200,
        page_height=1200,
        format="PNG",
    )

    with pytest.raises(HTTPException) as exc_info:
        generate_cover_collage_batch_job(payload)

    assert exc_info.value.status_code == 400
    assert "not inside the scanned parent folder" in str(exc_info.value.detail)
