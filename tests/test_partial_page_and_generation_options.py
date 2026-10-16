"""Trailing images, and the options reaching the endpoints.

``compose_image_grids`` used to discard the final incomplete page *and* subtract
those images from its own placed count, so 20 images produced one page and eight
images vanished with nothing said about them. The default is unchanged — the
count is now reported, and rendering the partial page is opt-in.
"""

from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from pasteup.main import app
from pasteup.services.grid_composer import CELLS_PER_PAGE, compose_image_grids

client = TestClient(app)


def _seed_images(folder: Path, count: int, *, colour=(20, 60, 200)) -> list[str]:
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for index in range(count):
        path = folder / f"img_{index:03}.png"
        Image.new("RGB", (120, 120), colour).save(path)
        paths.append(str(path))
    return paths


def test_trailing_images_are_reported_rather_than_dropped_silently(tmp_path: Path) -> None:
    paths = _seed_images(tmp_path, CELLS_PER_PAGE + 8)

    pages, summary = compose_image_grids(paths, page_width=1200, page_height=900, margin=20, gap=10)

    assert len(pages) == 1
    assert summary.total_images_placed == CELLS_PER_PAGE
    assert summary.total_images_dropped == 8
    assert "8 trailing image(s)" in summary.user_message


def test_include_partial_page_renders_the_remainder(tmp_path: Path) -> None:
    paths = _seed_images(tmp_path, CELLS_PER_PAGE + 8)

    pages, summary = compose_image_grids(
        paths, page_width=1200, page_height=900, margin=20, gap=10, include_partial_page=True
    )

    assert len(pages) == 2
    assert summary.total_images_placed == CELLS_PER_PAGE + 8
    assert summary.total_images_dropped == 0
    assert "trailing" not in summary.user_message


def test_a_partial_page_leaves_its_unused_cells_white(tmp_path: Path) -> None:
    paths = _seed_images(tmp_path, CELLS_PER_PAGE + 1)

    pages, _ = compose_image_grids(
        paths, page_width=1200, page_height=900, margin=20, gap=10, include_partial_page=True
    )

    # Bottom-right of the second page holds no image.
    corner = pages[1].crop((1100, 820, 1200, 900))
    assert corner.getcolors() == [(corner.width * corner.height, (255, 255, 255))]


def test_an_exact_multiple_reports_nothing_dropped(tmp_path: Path) -> None:
    paths = _seed_images(tmp_path, CELLS_PER_PAGE * 2)

    _, summary = compose_image_grids(paths, page_width=1200, page_height=900, margin=20, gap=10)

    assert summary.total_images_dropped == 0
    assert "trailing" not in summary.user_message


def test_generate_endpoint_accepts_inches_and_reports_geometry(tmp_path: Path) -> None:
    source = tmp_path / "in"
    _seed_images(source, CELLS_PER_PAGE)

    response = client.post(
        "/api/jobs/generate",
        json={
            "folder_path": str(source),
            "output_path": str(tmp_path / "out"),
            "page_width": 10,
            "page_height": 8,
            "page_unit": "in",
            "dpi": 300,
            "gap": 30,
            "margin": 60,
            "format": "PNG",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["page_geometry"] == "3000x2400px (10.00x8.00in at 300 DPI)"

    with Image.open(body["output_files"][0]) as page:
        assert page.size == (3000, 2400)
        assert round(page.info["dpi"][0]) == 300


def test_generate_endpoint_cleans_backgrounds_when_asked(tmp_path: Path) -> None:
    source = tmp_path / "in"
    # Off-white tiles: the background the cleaner exists for.
    _seed_images(source, CELLS_PER_PAGE, colour=(248, 248, 246))

    response = client.post(
        "/api/jobs/generate",
        json={
            "folder_path": str(source),
            "output_path": str(tmp_path / "out"),
            "page_width": 1200,
            "page_height": 900,
            "gap": 10,
            "margin": 20,
            "format": "PNG",
            "background_clean_mode": "flatten",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["backgrounds_cleaned"] == CELLS_PER_PAGE
    assert "Cleaned the background" in body["message"]


def test_generate_endpoint_reports_dropped_images(tmp_path: Path) -> None:
    source = tmp_path / "in"
    _seed_images(source, CELLS_PER_PAGE + 3)

    response = client.post(
        "/api/jobs/generate",
        json={
            "folder_path": str(source),
            "output_path": str(tmp_path / "out"),
            "page_width": 1200,
            "page_height": 900,
            "gap": 10,
            "margin": 20,
            "format": "PNG",
        },
    )

    assert response.json()["images_dropped"] == 3


def test_generate_endpoint_include_partial_page_reaches_the_composer(tmp_path: Path) -> None:
    """The batcher truncates to whole pages, so the flag has to bypass it."""
    source = tmp_path / "in"
    _seed_images(source, CELLS_PER_PAGE + 3)

    response = client.post(
        "/api/jobs/generate",
        json={
            "folder_path": str(source),
            "output_path": str(tmp_path / "out"),
            "page_width": 1200,
            "page_height": 900,
            "gap": 10,
            "margin": 20,
            "format": "PNG",
            "include_partial_page": True,
        },
    )

    body = response.json()
    assert body["pages_generated"] == 2
    assert body["total_images"] == CELLS_PER_PAGE + 3
    assert body["images_dropped"] == 0


def test_an_invalid_dpi_is_rejected_by_the_endpoint(tmp_path: Path) -> None:
    source = tmp_path / "in"
    _seed_images(source, 1)

    response = client.post(
        "/api/jobs/generate",
        json={
            "folder_path": str(source),
            "output_path": str(tmp_path / "out"),
            "page_width": 1200,
            "page_height": 900,
            "gap": 10,
            "margin": 20,
            "format": "PNG",
            "dpi": 0,
        },
    )

    assert response.status_code == 422


def test_cover_collage_endpoint_carries_dpi(tmp_path: Path) -> None:
    source = tmp_path / "in"
    _seed_images(source, 6)

    response = client.post(
        "/api/jobs/generate-cover-collage",
        json={
            "folder_path": str(source),
            "output_path": str(tmp_path / "out"),
            "page_width": 4,
            "page_height": 4,
            "page_unit": "in",
            "dpi": 300,
            "format": "PNG",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["page_geometry"] == "1200x1200px (4.00x4.00in at 300 DPI)"
    with Image.open(body["output_files"][0]) as collage:
        assert collage.size == (1200, 1200)
        assert round(collage.info["dpi"][0]) == 300


def test_a_margin_wider_than_the_page_is_a_client_error(tmp_path: Path) -> None:
    """It used to escape as a bare 500, which the UI could not even parse."""
    source = tmp_path / "in"
    _seed_images(source, CELLS_PER_PAGE)

    response = client.post(
        "/api/jobs/generate",
        json={
            "folder_path": str(source),
            "output_path": str(tmp_path / "out"),
            "page_width": 3000,
            "page_height": 3000,
            "gap": 30,
            "margin": 1600,
            "format": "PNG",
        },
    )

    assert response.status_code == 400
    assert "Adjust page size, margin, or gap" in response.json()["message"]
    assert not (tmp_path / "out").exists()
