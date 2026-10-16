from pathlib import Path

from PIL import Image

from app.services.grid_composer import compose_image_grids


def _create_image(path: Path) -> None:
    Image.new("RGB", (120, 120), color="white").save(path, format="PNG")


def test_compose_image_grids_generates_clean_pages_without_overlay(tmp_path: Path) -> None:
    image_paths: list[str] = []
    for index in range(12):
        image_path = tmp_path / f"image_{index:03}.png"
        _create_image(image_path)
        image_paths.append(str(image_path))

    pages, summary = compose_image_grids(
        image_paths,
        page_width=1200,
        page_height=900,
        margin=20,
        gap=10,
    )

    assert summary.pages_generated == 1
    assert len(pages) == 1

    generated_page = pages[0]
    assert generated_page.size == (1200, 900)

    bottom_right_region = generated_page.crop((1100, 820, 1200, 900))
    assert bottom_right_region.getcolors() == [(bottom_right_region.width * bottom_right_region.height, (255, 255, 255))]
