from pathlib import Path

from PIL import Image

from pasteup.models.schemas import BatchGenerationRequest, GenerationRequest
from pasteup.routes.jobs import generate_all_folders_job


def _create_image(path: Path) -> None:
    Image.new("RGB", (100, 120), color="white").save(path, format="PNG")


def test_generate_all_folders_builds_created_subfolders_and_exports_pages(tmp_path: Path) -> None:
    parent = tmp_path / "---Listing Images---"
    parent.mkdir()

    bundle_one = parent / "00001. Moths and Botanicals"
    bundle_one.mkdir()
    for index in range(12):
        _create_image(bundle_one / f"img_{index:03}.png")

    bundle_two = parent / "00002. Small Bundle"
    bundle_two.mkdir()
    for index in range(10):
        _create_image(bundle_two / f"img_{index:03}.png")

    created_root = parent / "---Created---"
    created_root.mkdir()

    payload = BatchGenerationRequest(
        parent_folder_path=str(parent),
        created_output_root_path=str(created_root),
        page_width=3000,
        page_height=3000,
        gap=30,
        margin=60,
        format="PNG",
    )

    result = generate_all_folders_job(payload)

    assert result.success is True
    assert result.created_output_root_path == str(created_root)
    assert result.processed_folders == 2
    assert result.selected_folders == 2
    assert result.total_detected_folders == 2
    assert result.generated_folders == 1
    assert result.message == (
        "Detected 2 eligible folder(s) under the parent. "
        "Processed 2 selected folder(s). "
        "Generated collage pages for 1 folder(s)."
    )

    first_output = created_root / "00001. Moths and Botanicals"
    second_output = created_root / "00002. Small Bundle"

    assert result.bundle_results[0].output_path == str(first_output)
    assert result.bundle_results[1].output_path == str(second_output)

    assert first_output.exists()
    assert (first_output / "page_001.png").exists()
    assert second_output.exists()
    assert not any(second_output.glob("*.png"))



def test_generate_all_folders_honors_selected_subfolders(tmp_path: Path) -> None:
    parent = tmp_path / "---Listing Images---"
    parent.mkdir()

    selected_bundle = parent / "00001. Selected Bundle"
    selected_bundle.mkdir()
    for index in range(12):
        _create_image(selected_bundle / f"img_{index:03}.png")

    skipped_bundle = parent / "00002. Skipped Bundle"
    skipped_bundle.mkdir()
    for index in range(12):
        _create_image(skipped_bundle / f"img_{index:03}.png")

    created_root = parent / "---Created---"
    created_root.mkdir()

    payload = BatchGenerationRequest(
        parent_folder_path=str(parent),
        created_output_root_path=str(created_root),
        selected_subfolders=[str(selected_bundle)],
        page_width=3000,
        page_height=3000,
        gap=30,
        margin=60,
        format="PNG",
    )

    result = generate_all_folders_job(payload)

    assert result.success is True
    assert result.processed_folders == 1
    assert result.selected_folders == 1
    assert result.total_detected_folders == 2
    assert result.generated_folders == 1
    assert result.message == (
        "Detected 2 eligible folder(s) under the parent. "
        "Processed 1 selected folder(s). "
        "Generated collage pages for 1 folder(s)."
    )
    assert [bundle.folder_name for bundle in result.bundle_results] == [selected_bundle.name]
    assert (created_root / selected_bundle.name / "page_001.png").exists()
    assert not (created_root / skipped_bundle.name).exists()


def test_batch_generation_request_accepts_legacy_selected_subfolder_paths_alias() -> None:
    payload = BatchGenerationRequest.model_validate(
        {
            "parent_folder_path": "/tmp/input",
            "created_output_root_path": "/tmp/output",
            "selected_subfolder_paths": [" /tmp/input/a ", "/tmp/input/a", "/tmp/input/b"],
            "page_width": 3000,
            "page_height": 4000,
            "gap": 30,
            "margin": 60,
            "format": "png",
        }
    )

    assert payload.selected_subfolders == ["/tmp/input/a", "/tmp/input/b"]
    assert payload.format == "PNG"


def test_generation_request_accepts_frontend_preview_video_field_aliases() -> None:
    payload = GenerationRequest.model_validate(
        {
            "folder_path": "/tmp/input",
            "output_path": "/tmp/output",
            "page_width": 3000,
            "page_height": 4000,
            "gap": 30,
            "margin": 60,
            "format": "png",
            "create_preview_video": True,
            "duration_seconds": 22,
            "transition": "crossfade",
        }
    )

    assert payload.create_video is True
    assert payload.video_duration_seconds == 22
    assert payload.video_transition == "crossfade"
    assert payload.format == "PNG"


def test_batch_generation_request_accepts_frontend_preview_video_field_aliases() -> None:
    payload = BatchGenerationRequest.model_validate(
        {
            "parent_folder_path": "/tmp/input",
            "created_output_root_path": "/tmp/output",
            "selected_subfolder_paths": ["/tmp/input/a"],
            "page_width": 3000,
            "page_height": 4000,
            "gap": 30,
            "margin": 60,
            "format": "png",
            "create_preview_video": True,
            "duration_seconds": 25,
            "transition": "flip",
        }
    )

    assert payload.create_video is True
    assert payload.video_duration_seconds == 25
    assert payload.video_transition == "flip"
    assert payload.selected_subfolders == ["/tmp/input/a"]


def test_generate_all_folders_excludes_generated_output_named_folders_from_detection(tmp_path: Path) -> None:
    parent = tmp_path / "---Listing Images---"
    parent.mkdir()

    selected_bundle = parent / "00001. Selected Bundle"
    selected_bundle.mkdir()
    for index in range(12):
        _create_image(selected_bundle / f"img_{index:03}.png")

    generated_like_folder = parent / "---Created---"
    generated_like_folder.mkdir()
    for index in range(12):
        _create_image(generated_like_folder / f"img_{index:03}.png")

    created_root = parent / "batch-output"

    payload = BatchGenerationRequest(
        parent_folder_path=str(parent),
        created_output_root_path=str(created_root),
        page_width=3000,
        page_height=3000,
        gap=30,
        margin=60,
        format="PNG",
    )

    result = generate_all_folders_job(payload)

    assert result.total_detected_folders == 1
    assert result.processed_folders == 1
    assert [bundle.folder_name for bundle in result.bundle_results] == [selected_bundle.name]
    assert not (created_root / generated_like_folder.name).exists()
