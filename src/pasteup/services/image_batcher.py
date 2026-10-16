"""Service for grouping images into page-sized batches."""

from __future__ import annotations


IMAGES_PER_PAGE = 12


def build_image_batches(image_paths: list[str]) -> list[list[str]]:
    """Split image paths into ordered full-page batches using a fixed 4x3 layout."""
    full_page_count = len(image_paths) // IMAGES_PER_PAGE
    return [
        image_paths[index : index + IMAGES_PER_PAGE]
        for index in range(0, full_page_count * IMAGES_PER_PAGE, IMAGES_PER_PAGE)
    ]


def estimate_page_count(image_count: int) -> int:
    """Return the number of full 4x3 pages that can be generated."""
    normalized_count = max(0, image_count)
    return normalized_count // IMAGES_PER_PAGE
