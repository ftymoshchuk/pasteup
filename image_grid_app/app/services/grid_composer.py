"""Service for composing 4x3 image grids."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Sequence

from PIL import Image, UnidentifiedImageError

from mullion import (
    DEFAULT_TOLERANCE,
    BackgroundCleanMode,
    clean_background,
    flatten_onto,
    open_path,
)

GRID_COLUMNS = 4
GRID_ROWS = 3
CELLS_PER_PAGE = GRID_COLUMNS * GRID_ROWS
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ComposeSummary:
    """Summary of a grid composition run."""

    total_input_files: int
    total_images_placed: int
    total_images_skipped: int
    pages_generated: int
    skipped_files: list[str]
    total_images_dropped: int = 0
    background_cleaned: int = 0

    @property
    def user_message(self) -> str:
        """Human-friendly summary for API/UI responses."""
        parts = [
            f"Generated {self.pages_generated} page(s) with "
            f"{self.total_images_placed} image(s)."
        ]
        if self.total_images_skipped:
            parts.append(f"Skipped {self.total_images_skipped} unreadable file(s).")
        if self.background_cleaned:
            parts.append(f"Cleaned the background on {self.background_cleaned} image(s).")
        if self.total_images_dropped:
            # This used to happen silently, which read as images going missing.
            parts.append(
                f"Left out {self.total_images_dropped} trailing image(s) that did not "
                f"fill a complete {GRID_COLUMNS}x{GRID_ROWS} page — enable "
                f"'include partial page' to render them."
            )
        return " ".join(parts)


def _create_canvas(page_width: float, page_height: float) -> Image.Image:
    """Create a white page canvas from user settings."""
    canvas_width = int(round(page_width))
    canvas_height = int(round(page_height))
    if canvas_width <= 0 or canvas_height <= 0:
        raise ValueError("Page width and height must be greater than zero.")
    return Image.new("RGB", (canvas_width, canvas_height), color="white")


def _compute_cell_geometry(
    page_width: float,
    page_height: float,
    margin: float,
    gap: float,
) -> tuple[float, float]:
    """Compute cell geometry for a fixed 4x3 grid."""
    cell_width = (page_width - 2 * margin - (GRID_COLUMNS - 1) * gap) / GRID_COLUMNS
    cell_height = (page_height - 2 * margin - (GRID_ROWS - 1) * gap) / GRID_ROWS
    if cell_width <= 0 or cell_height <= 0:
        raise ValueError(
            "Computed cell size is invalid. "
            "Adjust page size, margin, or gap values."
        )
    return cell_width, cell_height


def _load_image_rgb(image_path: str) -> Image.Image:
    """Load an image as RGB, raising on unreadable/corrupt content.

    Delegates to :mod:`mullion` so transparent PNGs land on
    white rather than black, and EXIF-rotated photos land upright. See that
    module for why a bare ``convert("RGB")`` is wrong here.
    """
    return open_path(image_path)


def compose_image_grids(
    image_paths: Sequence[str],
    page_width: float,
    page_height: float,
    margin: float,
    gap: float,
    *,
    background_clean_mode: BackgroundCleanMode | str = BackgroundCleanMode.OFF,
    background_tolerance: int = DEFAULT_TOLERANCE,
    background_feather: int = 1,
    include_partial_page: bool = False,
) -> tuple[list[Image.Image], ComposeSummary]:
    """Compose input images into one or more white 4x3 grid pages.

    Images are proportionally resized to fit in each cell without distortion, then
    centered in their assigned cell. Unreadable image files are skipped and logged.

    Trailing images that do not complete a full 12-cell page are left out unless
    ``include_partial_page`` is set, in which case the final page is rendered
    with its unused cells left white. Either way the count is reported on the
    summary rather than being dropped silently.

    ``background_clean_mode`` runs each tile through
    :func:`mullion.clean_background` before it is
    placed, so an off-white source background blends into the page instead of
    reading as a faint rectangle around the tile.
    """
    cell_width, cell_height = _compute_cell_geometry(page_width, page_height, margin, gap)

    normalized_clean_mode = BackgroundCleanMode(str(background_clean_mode))

    pages: list[Image.Image] = []
    skipped_files: list[str] = []
    placed_count = 0
    cleaned_count = 0

    current_page = _create_canvas(page_width, page_height)
    slot_index = 0

    for image_path in image_paths:
        try:
            image = _load_image_rgb(image_path)
        except (FileNotFoundError, PermissionError, OSError, UnidentifiedImageError, ValueError) as exc:
            skipped_files.append(image_path)
            logger.warning("Skipping unreadable image '%s': %s", image_path, exc)
            continue

        if normalized_clean_mode is not BackgroundCleanMode.OFF:
            image, clean_result = clean_background(
                image,
                mode=normalized_clean_mode,
                tolerance=background_tolerance,
                feather=background_feather,
            )
            if clean_result.cleaned:
                cleaned_count += 1
            # A transparent-mode result still has to land on the opaque page.
            if image.mode != "RGB":
                image = flatten_onto(image)

        row = slot_index // GRID_COLUMNS
        col = slot_index % GRID_COLUMNS

        cell_x = margin + col * (cell_width + gap)
        cell_y = margin + row * (cell_height + gap)

        scale = min(cell_width / image.width, cell_height / image.height)
        resized_width = max(1, int(round(image.width * scale)))
        resized_height = max(1, int(round(image.height * scale)))

        resized_image = image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)

        paste_x = int(round(cell_x + (cell_width - resized_width) / 2))
        paste_y = int(round(cell_y + (cell_height - resized_height) / 2))
        current_page.paste(resized_image, (paste_x, paste_y))

        placed_count += 1
        slot_index += 1

        if slot_index == CELLS_PER_PAGE:
            pages.append(current_page)
            current_page = _create_canvas(page_width, page_height)
            slot_index = 0

    dropped_count = 0
    if slot_index > 0:
        if include_partial_page:
            # Unused cells keep the canvas white, which is what the README has
            # always described.
            pages.append(current_page)
        else:
            placed_count -= slot_index
            dropped_count = slot_index

    summary = ComposeSummary(
        total_input_files=len(image_paths),
        total_images_placed=max(0, placed_count),
        total_images_skipped=len(skipped_files),
        pages_generated=len(pages),
        skipped_files=[Path(path).name for path in skipped_files],
        total_images_dropped=dropped_count,
        background_cleaned=cleaned_count,
    )

    return pages, summary
