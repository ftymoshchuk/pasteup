from pathlib import Path

import pytest
from PIL import Image
from fastapi import HTTPException
from pydantic import ValidationError

from app.models.schemas import CoverCollageGenerationRequest
from app.routes import jobs
from app.routes.jobs import generate_cover_collage_job


def _create_image(path: Path, color: tuple[int, int, int]) -> None:
    Image.new("RGB", (320, 480), color=color).save(path, format="PNG")


@pytest.mark.parametrize(
    ("export_format", "collage_template", "expected_name", "expected_total_images"),
    [
        ("PNG", "feature-spread", "cover_collage_001.png", 6),
        ("JPG", "center-stage", "cover_collage_001.jpg", 7),
    ],
)
def test_generate_cover_collage_collects_images_recursively_from_bundle_folders(
    tmp_path: Path,
    export_format: str,
    collage_template: str,
    expected_name: str,
    expected_total_images: int,
) -> None:
    parent = tmp_path / "---Listing Images---"
    parent.mkdir()

    first_bundle = parent / "00001. Bundle One"
    first_bundle.mkdir()
    _create_image(first_bundle / "one.png", (255, 0, 0))
    _create_image(first_bundle / "two.png", (0, 255, 0))

    second_bundle = parent / "00002. Bundle Two"
    second_bundle.mkdir()
    _create_image(second_bundle / "three.png", (0, 0, 255))

    output_dir = parent / "---Created---"

    payload = CoverCollageGenerationRequest(
        folder_path=str(parent),
        output_path=str(output_dir),
        page_width=1200,
        page_height=1200,
        format=export_format,
        collage_template=collage_template,
    )

    result = generate_cover_collage_job(payload)

    assert result.success is True
    assert result.total_images == expected_total_images
    assert result.pages_generated == 1
    assert len(result.output_files) == 1
    assert output_dir.joinpath(expected_name).exists()
    assert result.output_files == [str(output_dir / expected_name)]
    assert payload.collage_template == collage_template


@pytest.mark.parametrize("export_format", ["PNG", "JPG"])
def test_generate_cover_collage_uses_separate_numbering_from_standard_pages(
    tmp_path: Path,
    export_format: str,
) -> None:
    parent = tmp_path / "input"
    parent.mkdir()
    _create_image(parent / "one.png", (255, 0, 0))
    _create_image(parent / "two.png", (0, 255, 0))

    output_dir = tmp_path / "output"
    standard_extension = "png" if export_format == "PNG" else "jpg"
    standard_page = output_dir / f"page_001.{standard_extension}"
    output_dir.mkdir()
    standard_page.write_bytes(b"existing page export")

    payload = CoverCollageGenerationRequest(
        folder_path=str(parent),
        output_path=str(output_dir),
        page_width=1200,
        page_height=1200,
        format=export_format,
        collage_template="randomized-grid",
    )

    result = generate_cover_collage_job(payload)

    expected_cover = output_dir / f"cover_collage_001.{standard_extension}"
    assert result.output_files == [str(expected_cover)]
    assert all("page_001" not in Path(output_file).name for output_file in result.output_files)
    assert expected_cover.exists()
    assert standard_page.read_bytes() == b"existing page export"


def test_cover_collage_generation_request_accepts_optional_image_fit_mode() -> None:
    payload = CoverCollageGenerationRequest(
        folder_path="/tmp/input",
        output_path="/tmp/output",
        page_width=1200,
        page_height=1200,
        format="jpg",
        collage_template="randomized-grid",
        image_fit="contain",
    )

    assert payload.format == "JPG"
    assert payload.collage_template == "randomized-grid"
    assert payload.image_fit == "contain"


def test_cover_collage_generation_request_normalizes_selected_cover_images() -> None:
    payload = CoverCollageGenerationRequest.model_validate(
        {
            "folder_path": "/tmp/input",
            "output_path": "/tmp/output",
            "page_width": 1200,
            "page_height": 1200,
            "format": "png",
            "selected_cover_images": [" cover001.jpg ", "cover001.jpg", "cover002.png", " "],
        }
    )

    assert payload.selected_cover_images == ["cover001.jpg", "cover002.png"]


def test_cover_collage_generation_request_accepts_omitted_selected_cover_images() -> None:
    payload = CoverCollageGenerationRequest.model_validate(
        {
            "folder_path": "/tmp/input",
            "output_path": "/tmp/output",
            "page_width": 1200,
            "page_height": 1200,
            "format": "png",
        }
    )

    assert payload.selected_cover_images is None


@pytest.mark.parametrize(
    "invalid_value",
    [
        "cover001.jpg",
        123,
        ["cover001.jpg", 456],
    ],
)
def test_cover_collage_generation_request_rejects_invalid_selected_cover_images(
    invalid_value: object,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        CoverCollageGenerationRequest.model_validate(
            {
                "folder_path": "/tmp/input",
                "output_path": "/tmp/output",
                "page_width": 1200,
                "page_height": 1200,
                "format": "png",
                "selected_cover_images": invalid_value,
            }
        )

    assert "selected_cover_images" in str(exc_info.value)


def test_generate_cover_collage_uses_only_selected_images(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    parent = tmp_path / "input"
    nested = parent / "nested"
    nested.mkdir(parents=True)
    _create_image(parent / "one.png", (255, 0, 0))
    _create_image(parent / "two.png", (0, 255, 0))
    _create_image(nested / "three.png", (0, 0, 255))

    output_dir = tmp_path / "output"
    payload = CoverCollageGenerationRequest(
        folder_path=str(parent),
        output_path=str(output_dir),
        page_width=1200,
        page_height=1200,
        format="PNG",
        collage_template="randomized-grid",
        selected_cover_images=["three.png", "one.png"],
    )

    captured_image_paths: list[str] = []

    def _fake_compose_cover_collage(image_paths: list[str], **_: object):
        captured_image_paths.extend(image_paths)

        class _Summary:
            total_images_placed = len(image_paths)
            user_message = f"Generated 1 cover collage with {len(image_paths)} image(s)."

        return [object()], _Summary()

    monkeypatch.setattr(jobs, "compose_cover_collage", _fake_compose_cover_collage)
    monkeypatch.setattr(jobs, "export_pages", lambda *args, **kwargs: [str(output_dir / "cover_collage_001.png")])

    result = generate_cover_collage_job(payload)

    assert result.success is True
    assert result.total_images == 2
    assert result.output_files == [str(output_dir / "cover_collage_001.png")]
    assert captured_image_paths == [str(parent / "one.png"), str(nested / "three.png")]


def test_generate_cover_collage_rejects_empty_manual_selection_matches(tmp_path: Path) -> None:
    parent = tmp_path / "input"
    parent.mkdir()
    _create_image(parent / "one.png", (255, 0, 0))

    output_dir = tmp_path / "output"
    payload = CoverCollageGenerationRequest(
        folder_path=str(parent),
        output_path=str(output_dir),
        page_width=1200,
        page_height=1200,
        format="PNG",
        selected_cover_images=["missing.png"],
    )

    with pytest.raises(HTTPException) as exc_info:
        generate_cover_collage_job(payload)

    assert "Cover collage include list did not match any supported images" in str(exc_info.value)
