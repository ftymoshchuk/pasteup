"""Service for generating a full-page cover collage with seeded random placement."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import logging
from pathlib import Path
import random
import re
from typing import Sequence

from PIL import Image, UnidentifiedImageError

from mullion import (
    DEFAULT_TOLERANCE,
    BackgroundCleanMode,
    clean_background,
    flatten_onto,
    open_path,
)

logger = logging.getLogger(__name__)

BACKGROUND_COLOR = (255, 255, 255)


class CoverCollageFittingMode(StrEnum):
    COVER = "cover"
    CONTAIN = "contain"


class CoverCollageTemplate(StrEnum):
    RANDOMIZED_GRID = "randomized-grid"
    FEATURE_SPREAD = "feature-spread"
    CENTER_STAGE = "center-stage"


@dataclass(frozen=True, slots=True)
class CoverCollageTile:
    x: int
    y: int
    width: int
    height: int
    role: str = "default"
    fitting_mode: CoverCollageFittingMode | None = None


@dataclass(frozen=True, slots=True)
class CoverCollageLayoutTemplate:
    name: str
    tiles: list[CoverCollageTile]

    @property
    def slot_count(self) -> int:
        return len(self.tiles)


@dataclass(frozen=True, slots=True)
class CoverCollageTileRect:
    x: float
    y: float
    width: float
    height: float
    role: str = "default"
    fitting_mode: CoverCollageFittingMode | None = None


@dataclass(frozen=True, slots=True)
class CoverCollageTemplateDefinition:
    name: str
    display_name: str
    tiles: tuple[CoverCollageTileRect, ...]
    default_fitting_mode: CoverCollageFittingMode | None = None

    @property
    def slot_count(self) -> int:
        return len(self.tiles)


@dataclass(slots=True)
class CoverCollageSummary:
    total_input_files: int
    total_images_placed: int
    total_images_skipped: int
    output_created: bool
    skipped_files: list[str]
    background_cleaned: int = 0

    @property
    def user_message(self) -> str:
        parts = [f"Generated 1 cover collage with {self.total_images_placed} image(s)."]
        if self.total_images_skipped:
            parts.append(f"Skipped {self.total_images_skipped} unreadable file(s).")
        if self.background_cleaned:
            parts.append(f"Cleaned the background on {self.background_cleaned} image(s).")
        return " ".join(parts)


def _load_image_rgb(image_path: str) -> Image.Image:
    return open_path(image_path)


def _resize_to_cover(image: Image.Image, width: int, height: int) -> Image.Image:
    scale = max(width / image.width, height / image.height)
    resized = image.resize(
        (max(1, int(round(image.width * scale))), max(1, int(round(image.height * scale)))),
        Image.Resampling.LANCZOS,
    )

    left = max(0, (resized.width - width) // 2)
    top = max(0, (resized.height - height) // 2)
    return resized.crop((left, top, left + width, top + height))


def _resize_to_contain(
    image: Image.Image,
    width: int,
    height: int,
    background_color: tuple[int, int, int],
) -> Image.Image:
    scale = min(width / image.width, height / image.height)
    resized = image.resize(
        (max(1, int(round(image.width * scale))), max(1, int(round(image.height * scale)))),
        Image.Resampling.LANCZOS,
    )

    canvas = Image.new("RGB", (width, height), color=background_color)
    left = max(0, (width - resized.width) // 2)
    top = max(0, (height - resized.height) // 2)
    canvas.paste(resized, (left, top))
    return canvas


def _fit_tile_image(
    image: Image.Image,
    width: int,
    height: int,
    fitting_mode: CoverCollageFittingMode,
    background_color: tuple[int, int, int],
) -> Image.Image:
    if fitting_mode == CoverCollageFittingMode.CONTAIN:
        return _resize_to_contain(image, width, height, background_color)
    return _resize_to_cover(image, width, height)


def _build_feature_spread_tile_rects() -> tuple[CoverCollageTileRect, ...]:
    """Return feature spread geometry separately from placement for easy future gap tuning."""
    column_width = 1 / 4
    row_height = 1 / 3

    return (
        CoverCollageTileRect(
            0 * column_width,
            0 * row_height,
            2 * column_width,
            2 * row_height,
            role="feature",
        ),
        CoverCollageTileRect(
            2 * column_width,
            0 * row_height,
            2 * column_width,
            2 * row_height,
            role="feature",
        ),
        CoverCollageTileRect(0 * column_width, 2 * row_height, 1 * column_width, 1 * row_height, role="bottom"),
        CoverCollageTileRect(1 * column_width, 2 * row_height, 1 * column_width, 1 * row_height, role="bottom"),
        CoverCollageTileRect(2 * column_width, 2 * row_height, 1 * column_width, 1 * row_height, role="bottom"),
        CoverCollageTileRect(3 * column_width, 2 * row_height, 1 * column_width, 1 * row_height, role="bottom"),
    )


# Keep enum values, internal names, and display labels together so the API and UI can expose
# the same template identifiers without drifting. Templates should only set tile-level
# fitting overrides when they intentionally need behavior that differs from the request-level
# `image_fit`; feature-spread now inherits the collage default so its large tiles do not
# silently reintroduce letterboxing.
TEMPLATE_REGISTRY: dict[CoverCollageTemplate, CoverCollageTemplateDefinition] = {
    CoverCollageTemplate.RANDOMIZED_GRID: CoverCollageTemplateDefinition(
        name="randomized_grid",
        display_name="Randomized grid",
        tiles=(
            CoverCollageTileRect(0.0, 0.0, 1 / 3, 1 / 3, role="grid"),
            CoverCollageTileRect(1 / 3, 0.0, 1 / 3, 1 / 3, role="grid"),
            CoverCollageTileRect(2 / 3, 0.0, 1 / 3, 1 / 3, role="grid"),
            CoverCollageTileRect(0.0, 1 / 3, 1 / 3, 1 / 3, role="grid"),
            CoverCollageTileRect(1 / 3, 1 / 3, 1 / 3, 1 / 3, role="grid"),
            CoverCollageTileRect(2 / 3, 1 / 3, 1 / 3, 1 / 3, role="grid"),
            CoverCollageTileRect(0.0, 2 / 3, 1 / 3, 1 / 3, role="grid"),
            CoverCollageTileRect(1 / 3, 2 / 3, 1 / 3, 1 / 3, role="grid"),
            CoverCollageTileRect(2 / 3, 2 / 3, 1 / 3, 1 / 3, role="grid"),
        ),
    ),
    CoverCollageTemplate.FEATURE_SPREAD: CoverCollageTemplateDefinition(
        name="feature_spread",
        display_name="Feature spread",
        tiles=_build_feature_spread_tile_rects(),
    ),
    CoverCollageTemplate.CENTER_STAGE: CoverCollageTemplateDefinition(
        name="center_stage",
        display_name="Center stage",
        tiles=(
            CoverCollageTileRect(1 / 4, 0.0, 2 / 4, 1.0, role="feature"),
            CoverCollageTileRect(0.0, 0.0, 1 / 4, 1 / 3, role="side"),
            CoverCollageTileRect(0.0, 1 / 3, 1 / 4, 1 / 3, role="side"),
            CoverCollageTileRect(0.0, 2 / 3, 1 / 4, 1 / 3, role="side"),
            CoverCollageTileRect(3 / 4, 0.0, 1 / 4, 1 / 3, role="side"),
            CoverCollageTileRect(3 / 4, 1 / 3, 1 / 4, 1 / 3, role="side"),
            CoverCollageTileRect(3 / 4, 2 / 3, 1 / 4, 1 / 3, role="side"),
        ),
    ),
}

COVER_COLLAGE_TEMPLATE_OPTIONS: tuple[tuple[str, str, str], ...] = tuple(
    (template.value, definition.name, definition.display_name)
    for template, definition in TEMPLATE_REGISTRY.items()
)


def _resolve_layout_template(
    page_width: int,
    page_height: int,
    template: CoverCollageTemplate,
) -> CoverCollageLayoutTemplate:
    definition = TEMPLATE_REGISTRY[template]
    tiles: list[CoverCollageTile] = []
    for tile_rect in definition.tiles:
        left = int(round(page_width * tile_rect.x))
        top = int(round(page_height * tile_rect.y))
        right = int(round(page_width * (tile_rect.x + tile_rect.width)))
        bottom = int(round(page_height * (tile_rect.y + tile_rect.height)))
        tiles.append(
            CoverCollageTile(
                x=left,
                y=top,
                width=max(1, min(page_width, right) - left),
                height=max(1, min(page_height, bottom) - top),
                role=tile_rect.role,
                fitting_mode=tile_rect.fitting_mode or definition.default_fitting_mode,
            )
        )

    return CoverCollageLayoutTemplate(name=definition.name, tiles=tiles)


def _build_tile_image_assignments(
    image_paths: Sequence[str],
    slot_count: int,
    rng: random.Random,
) -> tuple[list[str], list[str]]:
    readable_paths: list[str] = []
    skipped_files: list[str] = []

    for image_path in image_paths:
        try:
            with Image.open(image_path) as source_image:
                source_image.verify()
        except (FileNotFoundError, PermissionError, OSError, UnidentifiedImageError, ValueError) as exc:
            skipped_files.append(image_path)
            logger.warning("Skipping unreadable image '%s': %s", image_path, exc)
            continue

        readable_paths.append(image_path)

    if not readable_paths:
        return [], skipped_files

    if len(readable_paths) >= slot_count:
        assignments = rng.sample(readable_paths, k=slot_count)
        rng.shuffle(assignments)
        return assignments, skipped_files

    suffix_by_path = {path: _parse_trailing_numeric_token(path) for path in readable_paths}
    assignments = []
    previous_path: str | None = None
    for _ in range(slot_count):
        assignments.append(_choose_next_assignment(readable_paths, assignments, previous_path, suffix_by_path, rng))
        previous_path = assignments[-1]

    return assignments, skipped_files


def _parse_trailing_numeric_token(image_path: str) -> int | None:
    match = re.search(r"(\d+)$", Path(image_path).stem)
    if match is None:
        return None
    return int(match.group(1))


def _is_adjacent_sequence(previous_path: str | None, candidate_path: str, suffix_by_path: dict[str, int | None]) -> bool:
    if previous_path is None:
        return False

    previous_suffix = suffix_by_path.get(previous_path)
    candidate_suffix = suffix_by_path.get(candidate_path)
    if previous_suffix is None or candidate_suffix is None:
        return False
    return abs(candidate_suffix - previous_suffix) == 1


def _choose_next_assignment(
    readable_paths: Sequence[str],
    assignments: Sequence[str],
    previous_path: str | None,
    suffix_by_path: dict[str, int | None],
    rng: random.Random,
) -> str:
    if not assignments:
        return rng.choice(list(readable_paths))

    non_repeating = [path for path in readable_paths if path != previous_path]
    non_adjacent = [path for path in non_repeating if not _is_adjacent_sequence(previous_path, path, suffix_by_path)]

    candidate_pool = non_adjacent or non_repeating or list(readable_paths)
    return rng.choice(candidate_pool)


def compose_cover_collage(
    image_paths: Sequence[str],
    page_width: float,
    page_height: float,
    rng: random.Random | None = None,
    fitting_mode: CoverCollageFittingMode | str = CoverCollageFittingMode.COVER,
    template: CoverCollageTemplate | str = CoverCollageTemplate.RANDOMIZED_GRID,
    *,
    background_clean_mode: BackgroundCleanMode | str = BackgroundCleanMode.OFF,
    background_tolerance: int = DEFAULT_TOLERANCE,
    background_feather: int = 1,
) -> tuple[list[Image.Image], CoverCollageSummary]:
    canvas_width = int(round(page_width))
    canvas_height = int(round(page_height))
    if canvas_width <= 0 or canvas_height <= 0:
        raise ValueError("Page width and height must be greater than zero.")

    fitting_mode = CoverCollageFittingMode(fitting_mode)
    template = CoverCollageTemplate(template)
    rng = rng or random.Random()
    layout_template = _resolve_layout_template(canvas_width, canvas_height, template)
    selected_paths, skipped_files = _build_tile_image_assignments(image_paths, layout_template.slot_count, rng)

    normalized_clean_mode = BackgroundCleanMode(str(background_clean_mode))
    collage = Image.new("RGB", (canvas_width, canvas_height), color=BACKGROUND_COLOR)

    placed_count = 0
    cleaned_count = 0

    for tile, image_path in zip(layout_template.tiles, selected_paths):
        image = _load_image_rgb(image_path)
        if normalized_clean_mode is not BackgroundCleanMode.OFF:
            image, clean_result = clean_background(
                image,
                mode=normalized_clean_mode,
                tolerance=background_tolerance,
                feather=background_feather,
                matte=BACKGROUND_COLOR,
            )
            if clean_result.cleaned:
                cleaned_count += 1
            if image.mode != "RGB":
                image = flatten_onto(image, BACKGROUND_COLOR)
        tile_fitting_mode = tile.fitting_mode or fitting_mode
        collage.paste(
            _fit_tile_image(image, tile.width, tile.height, tile_fitting_mode, BACKGROUND_COLOR),
            (tile.x, tile.y),
        )
        placed_count += 1

    summary = CoverCollageSummary(
        total_input_files=len(image_paths),
        total_images_placed=placed_count,
        total_images_skipped=len(skipped_files),
        output_created=placed_count > 0,
        skipped_files=[Path(path).name for path in skipped_files],
        background_cleaned=cleaned_count,
    )

    pages = [collage] if placed_count > 0 else []
    return pages, summary
