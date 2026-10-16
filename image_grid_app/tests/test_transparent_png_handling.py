"""A transparent PNG must land on white, not black.

``Image.open(path).convert("RGB")`` drops the alpha channel and keeps whatever
RGB sits underneath it, which in almost every PNG writer is ``(0, 0, 0)``. The
page still renders and the export still succeeds, so nothing fails — the tile
simply arrives inside a black rectangle.

Loading is mullion's job and its own suite covers each shape transparency
arrives in. These tests make the same claims through this app's composer, so a
mullion upgrade that regressed them would still fail here.
"""

from pathlib import Path

import pytest
from PIL import Image, ImageChops

from app.services.grid_composer import compose_image_grids


def _cutout_rgba(size: int = 80) -> Image.Image:
    """An opaque red square on a fully transparent field."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    for y in range(size // 4, size - size // 4):
        for x in range(size // 4, size - size // 4):
            image.putpixel((x, y), (220, 40, 40, 255))
    return image


def test_composed_page_has_no_black_boxes(tmp_path: Path) -> None:
    """The end-to-end claim: a page of cutouts contains no black at all."""
    paths = []
    for index in range(12):
        path = tmp_path / f"cutout_{index:02}.png"
        _cutout_rgba().save(path)
        paths.append(str(path))

    pages, _ = compose_image_grids(paths, page_width=1200, page_height=900, margin=20, gap=10)

    colours = {colour for _, colour in pages[0].getcolors(maxcolors=1_000_000)}
    assert (0, 0, 0) not in colours


@pytest.mark.parametrize("orientation,expected_portrait", [(1, False), (6, True)])
def test_exif_orientation_is_applied(tmp_path: Path, orientation: int, expected_portrait: bool) -> None:
    """A phone photo stores portrait as landscape plus a rotation tag.

    Pillow does not apply that tag on open, so without ``exif_transpose`` the
    image is placed sideways — and because the cell fit preserves aspect ratio,
    it reads as merely small rather than obviously wrong.
    """
    path = tmp_path / f"photo_{orientation}.jpg"
    image = Image.new("RGB", (120, 60), (90, 120, 160))
    exif = image.getexif()
    exif[0x0112] = orientation
    image.save(path, exif=exif)

    pages, _ = compose_image_grids(
        [str(path)], page_width=1200, page_height=900, margin=0, gap=0, include_partial_page=True
    )

    # The photo lands in the first 300x300 cell; measure what was placed there.
    cell = pages[0].crop((0, 0, 300, 300))
    left, top, right, bottom = ImageChops.difference(cell, Image.new("RGB", cell.size, "white")).getbbox()
    assert (bottom - top > right - left) is expected_portrait
