"""Guards for a tool that reads and writes local paths with no authentication.

Each test pins one way a single request could reach beyond what the user asked
for: writing outside the output folder, allocating an unbounded page, or being
driven by a web page through a re-pointed domain.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from pasteup.main import app
from pasteup.models.schemas import GenerationRequest
from pasteup.routes.jobs import MAX_PAGE_MEGAPIXELS, _OutputOptions
from pasteup.services.video_exporter import build_preview_video

client = TestClient(app)


def _request(**overrides) -> dict:
    payload = {
        "folder_path": "/unused",
        "output_path": "/unused",
        "page_width": 1000,
        "page_height": 800,
        "gap": 10,
        "margin": 10,
        "format": "PNG",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "filename",
    ["/tmp/preview.mp4", "../preview.mp4", "nested/preview.mp4", "..\\preview.mp4", "..", "", "preview.mov"],
)
def test_video_filename_must_be_a_plain_mp4_name(filename: str) -> None:
    with pytest.raises(ValidationError, match="video_filename"):
        GenerationRequest(**_request(video_filename=filename))


def test_a_plain_video_filename_is_accepted() -> None:
    request = GenerationRequest(**_request(video_filename="  Bundle Preview.MP4 "))
    assert request.video_filename == "Bundle Preview.MP4"


def test_generate_refuses_a_video_path_outside_the_output_folder(tmp_path: Path) -> None:
    source = tmp_path / "in"
    source.mkdir()
    for index in range(12):
        Image.new("RGB", (40, 30), (index * 20, 90, 140)).save(source / f"img_{index:02}.png")
    precious = tmp_path / "elsewhere" / "notes.mp4"
    precious.parent.mkdir()
    precious.write_text("keep me")

    response = client.post(
        "/api/jobs/generate",
        json=_request(
            folder_path=str(source),
            output_path=str(tmp_path / "out"),
            create_video=True,
            video_filename=str(precious),
        ),
    )

    assert response.status_code == 422
    assert precious.read_text() == "keep me"
    assert not (tmp_path / "out").exists()


def test_exporter_refuses_a_filename_that_leaves_the_output_folder(tmp_path: Path) -> None:
    page = tmp_path / "page_001.png"
    Image.new("RGB", (20, 20), "white").save(page)

    with pytest.raises(ValueError, match="plain file name"):
        build_preview_video([str(page)], tmp_path / "out", 3.0, "none", "../escape.mp4")


def test_page_size_is_capped_before_anything_is_allocated() -> None:
    side = 10_000  # 100 MP exactly: allowed
    assert _OutputOptions().geometry(page_width=side, page_height=side).width_px == side

    with pytest.raises(ValueError, match=f"limit is {MAX_PAGE_MEGAPIXELS} MP"):
        _OutputOptions().geometry(page_width=side + 1, page_height=side)


def test_page_size_cap_applies_after_unit_conversion() -> None:
    """40x40in at 1200 DPI is a modest-looking request for 2,304 MP."""
    options = _OutputOptions(page_unit="in", dpi=1200)

    with pytest.raises(ValueError, match="48000x48000px"):
        options.geometry(page_width=40, page_height=40)


def test_non_finite_page_size_is_rejected() -> None:
    with pytest.raises(ValueError, match="finite"):
        _OutputOptions().geometry(page_width=float("inf"), page_height=100)


def test_generate_reports_an_oversized_page_as_a_client_error(tmp_path: Path) -> None:
    response = client.post(
        "/api/jobs/generate",
        json=_request(folder_path=str(tmp_path), output_path=str(tmp_path / "out"), page_width=200_000, page_height=200_000),
    )

    assert response.status_code == 400
    assert f"the limit is {MAX_PAGE_MEGAPIXELS} MP" in response.json()["message"]
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("base_url", ["http://localhost:8000", "http://127.0.0.1:8000", "http://[::1]:8000"])
def test_local_host_names_are_answered(base_url: str) -> None:
    assert TestClient(app, base_url=base_url).get("/api/jobs/health").status_code == 200


def test_requests_for_another_host_are_refused() -> None:
    """What a DNS-rebinding page's requests look like when they reach the app."""
    rebinding_client = TestClient(app, base_url="http://attacker.example:8000")

    assert rebinding_client.get("/").status_code == 400
    assert rebinding_client.post("/api/jobs/scan-folder", json={"folder_path": "/"}).status_code == 400
    assert rebinding_client.post("/api/jobs/browse-folder", json={"folder_path": "/"}).status_code == 400
