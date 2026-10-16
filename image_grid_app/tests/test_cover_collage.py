from pathlib import Path
import random

import pytest
from PIL import Image

from app.services.cover_collage import (
    COVER_COLLAGE_TEMPLATE_OPTIONS,
    CoverCollageFittingMode,
    CoverCollageTemplate,
    _build_tile_image_assignments,
    _resolve_layout_template,
    _resize_to_contain,
    compose_cover_collage,
)

WHITE = (255, 255, 255)
PAGE_SIZE = (900, 1200)
TEMPLATE_EXPECTATIONS = {
    CoverCollageTemplate.RANDOMIZED_GRID: {
        "slot_count": 9,
        "geometry": [
            (0, 0, 300, 400, "grid"),
            (300, 0, 300, 400, "grid"),
            (600, 0, 300, 400, "grid"),
            (0, 400, 300, 400, "grid"),
            (300, 400, 300, 400, "grid"),
            (600, 400, 300, 400, "grid"),
            (0, 800, 300, 400, "grid"),
            (300, 800, 300, 400, "grid"),
            (600, 800, 300, 400, "grid"),
        ],
        "centers": [
            (150, 200),
            (450, 200),
            (750, 200),
            (150, 600),
            (450, 600),
            (750, 600),
            (150, 1000),
            (450, 1000),
            (750, 1000),
        ],
    },
    CoverCollageTemplate.FEATURE_SPREAD: {
        "slot_count": 6,
        "geometry": [
            (0, 0, 450, 800, "feature"),
            (450, 0, 450, 800, "feature"),
            (0, 800, 225, 400, "bottom"),
            (225, 800, 225, 400, "bottom"),
            (450, 800, 225, 400, "bottom"),
            (675, 800, 225, 400, "bottom"),
        ],
        "centers": [
            (225, 400),
            (675, 400),
            (112, 1000),
            (337, 1000),
            (562, 1000),
            (787, 1000),
        ],
    },
    CoverCollageTemplate.CENTER_STAGE: {
        "slot_count": 7,
        "geometry": [
            (225, 0, 450, 1200, "feature"),
            (0, 0, 225, 400, "side"),
            (0, 400, 225, 400, "side"),
            (0, 800, 225, 400, "side"),
            (675, 0, 225, 400, "side"),
            (675, 400, 225, 400, "side"),
            (675, 800, 225, 400, "side"),
        ],
        "centers": [
            (450, 600),
            (112, 200),
            (112, 600),
            (112, 1000),
            (787, 200),
            (787, 600),
            (787, 1000),
        ],
    },
}


def _create_image(path: Path, color: tuple[int, int, int], size: tuple[int, int] = (400, 500)) -> None:
    Image.new("RGB", size, color=color).save(path)


def _assert_no_white_canvas_on_tile_boundaries(image: Image.Image) -> None:
    colors = image.getcolors(maxcolors=image.width * image.height)
    assert colors is not None
    assert any(color == WHITE for _, color in colors) is False


def _assert_feature_tiles_are_fully_populated(image: Image.Image) -> None:
    feature_tiles = TEMPLATE_EXPECTATIONS[CoverCollageTemplate.FEATURE_SPREAD]["geometry"][:2]

    for x, y, width, height, _ in feature_tiles:
        tile_image = image.crop((x, y, x + width, y + height))
        assert _find_non_background_bounds(tile_image) == (0, 0, tile_image.width - 1, tile_image.height - 1)


def test_compose_cover_collage_populates_tile_boundaries_with_nine_valid_images(tmp_path: Path) -> None:
    rng_seed = 7
    image_paths: list[str] = []
    colors = [
        (255, 0, 0),
        (0, 255, 0),
        (0, 0, 255),
        (255, 255, 0),
        (255, 0, 255),
        (0, 255, 255),
        (255, 128, 0),
        (128, 0, 255),
        (0, 128, 255),
    ]

    for index, color in enumerate(colors, start=1):
        image_path = tmp_path / f"image_{index:02d}.png"
        _create_image(image_path, color=color, size=(250 + index * 19, 260 + index * 23))
        image_paths.append(str(image_path))

    pages, summary = compose_cover_collage(image_paths, *PAGE_SIZE, rng=random.Random(rng_seed))

    assert len(pages) == 1
    assert pages[0].size == PAGE_SIZE
    assert summary.output_created is True
    assert summary.total_images_placed == 9
    assert summary.total_images_skipped == 0
    _assert_no_white_canvas_on_tile_boundaries(pages[0])


def test_compose_cover_collage_reuses_fewer_than_nine_images_without_white_boundaries(tmp_path: Path) -> None:
    rng_seed = 11
    image_paths: list[str] = []
    for index, color in enumerate([(255, 64, 64), (64, 255, 64), (64, 64, 255)], start=1):
        image_path = tmp_path / f"small_set_{index:02d}.png"
        _create_image(image_path, color=color, size=(220 + index * 31, 200 + index * 17))
        image_paths.append(str(image_path))

    pages, summary = compose_cover_collage(image_paths, *PAGE_SIZE, rng=random.Random(rng_seed))

    assert len(pages) == 1
    assert summary.total_images_placed == 9
    assert summary.total_images_skipped == 0
    _assert_no_white_canvas_on_tile_boundaries(pages[0])


def test_compose_cover_collage_skips_unreadable_images_without_leaving_white_tiles(tmp_path: Path) -> None:
    rng_seed = 19
    valid_paths: list[str] = []
    for index, color in enumerate(
        [(255, 32, 32), (32, 255, 32), (32, 32, 255), (255, 160, 32)],
        start=1,
    ):
        image_path = tmp_path / f"valid_{index:02d}.png"
        _create_image(image_path, color=color, size=(280 + index * 13, 240 + index * 29))
        valid_paths.append(str(image_path))

    unreadable_path = tmp_path / "broken.png"
    unreadable_path.write_text("not an image")

    pages, summary = compose_cover_collage(valid_paths + [str(unreadable_path)], *PAGE_SIZE, rng=random.Random(rng_seed))

    assert len(pages) == 1
    assert summary.total_images_placed == 9
    assert summary.total_images_skipped == 1
    assert summary.skipped_files == [unreadable_path.name]
    _assert_no_white_canvas_on_tile_boundaries(pages[0])


def test_build_tile_image_assignments_seeded_rng_produces_stable_randomized_subset(tmp_path: Path) -> None:
    image_paths: list[str] = []
    for index, color in enumerate(
        [(10, 20, 30), (40, 50, 60), (70, 80, 90), (100, 110, 120), (130, 140, 150)],
        start=1,
    ):
        image_path = tmp_path / f"stable_subset_{index:02d}.png"
        _create_image(image_path, color=color)
        image_paths.append(str(image_path))

    assignments, skipped_files = _build_tile_image_assignments(image_paths, slot_count=3, rng=random.Random(3))

    assert skipped_files == []
    assert len(assignments) == 3
    assert assignments == [
        image_paths[1],
        image_paths[4],
        image_paths[3],
    ]


def test_build_tile_image_assignments_undersized_sets_do_not_cycle_input_order(tmp_path: Path) -> None:
    image_paths: list[str] = []
    for index, color in enumerate([(10, 20, 30), (40, 50, 60), (70, 80, 90)], start=1):
        image_path = tmp_path / f"undersized_{index:02d}.png"
        _create_image(image_path, color=color)
        image_paths.append(str(image_path))

    assignments, skipped_files = _build_tile_image_assignments(image_paths, slot_count=5, rng=random.Random(3))

    assert skipped_files == []
    assert len(assignments) == 5
    assert assignments != [image_paths[0], image_paths[1], image_paths[2], image_paths[0], image_paths[1]]
    assert all(current != previous for previous, current in zip(assignments, assignments[1:]))


def test_build_tile_image_assignments_avoids_adjacent_filename_runs_when_alternatives_exist(
    tmp_path: Path,
) -> None:
    image_paths: list[str] = []
    for name, color in (
        ("sequence_021.png", (10, 20, 30)),
        ("sequence_022.png", (40, 50, 60)),
        ("sequence_023.png", (70, 80, 90)),
        ("sequence_040.png", (100, 110, 120)),
    ):
        image_path = tmp_path / name
        _create_image(image_path, color=color)
        image_paths.append(str(image_path))

    assignments, skipped_files = _build_tile_image_assignments(image_paths, slot_count=7, rng=random.Random(8))

    assert skipped_files == []
    assert len(assignments) == 7

    suffixes = [int(Path(path).stem.rsplit("_", maxsplit=1)[-1]) for path in assignments]
    for previous_path, current_path, previous_suffix, current_suffix in zip(
        assignments,
        assignments[1:],
        suffixes,
        suffixes[1:],
    ):
        assert current_path != previous_path
        assert abs(current_suffix - previous_suffix) != 1


def test_cover_collage_template_options_stay_in_registry_order() -> None:
    assert COVER_COLLAGE_TEMPLATE_OPTIONS == (
        ("randomized-grid", "randomized_grid", "Randomized grid"),
        ("feature-spread", "feature_spread", "Feature spread"),
        ("center-stage", "center_stage", "Center stage"),
    )


@pytest.mark.parametrize(
    ("template", "expected_slot_count", "expected_geometry"),
    [
        (template, expectation["slot_count"], expectation["geometry"])
        for template, expectation in TEMPLATE_EXPECTATIONS.items()
    ],
)
def test_cover_collage_templates_report_expected_slot_counts_and_geometry(
    template: CoverCollageTemplate,
    expected_slot_count: int,
    expected_geometry: list[tuple[int, int, int, int, str]],
) -> None:
    layout = _resolve_layout_template(*PAGE_SIZE, template)

    assert layout.name == template.value.replace("-", "_")
    assert layout.slot_count == expected_slot_count
    assert [(tile.x, tile.y, tile.width, tile.height, tile.role) for tile in layout.tiles] == expected_geometry


def test_feature_spread_template_inherits_request_level_fitting_mode_for_all_slots() -> None:
    layout = _resolve_layout_template(*PAGE_SIZE, CoverCollageTemplate.FEATURE_SPREAD)

    assert [tile.fitting_mode for tile in layout.tiles] == [None, None, None, None, None, None]


@pytest.mark.parametrize(
    "template",
    [
        CoverCollageTemplate.RANDOMIZED_GRID,
        CoverCollageTemplate.FEATURE_SPREAD,
        CoverCollageTemplate.CENTER_STAGE,
    ],
)
def test_compose_cover_collage_uses_deterministic_template_placement_order(
    tmp_path: Path,
    template: CoverCollageTemplate,
) -> None:
    colors = [
        (230, 10, 10),
        (10, 230, 10),
        (10, 10, 230),
        (220, 220, 10),
        (220, 10, 220),
        (10, 220, 220),
        (180, 120, 10),
        (120, 10, 180),
        (10, 120, 180),
    ]
    image_paths: list[str] = []
    for index, color in enumerate(colors, start=1):
        image_path = tmp_path / f"ordered_{template.value}_{index:02d}.png"
        _create_image(image_path, color=color, size=(300 + index * 7, 420 + index * 9))
        image_paths.append(str(image_path))

    pages, summary = compose_cover_collage(
        image_paths,
        *PAGE_SIZE,
        rng=random.Random(17),
        template=template,
    )

    layout_expectation = TEMPLATE_EXPECTATIONS[template]
    expected_assignments, skipped_files = _build_tile_image_assignments(
        image_paths,
        slot_count=layout_expectation["slot_count"],
        rng=random.Random(17),
    )

    assert len(pages) == 1
    assert skipped_files == []
    assert summary.total_images_placed == layout_expectation["slot_count"]
    for sample_point, assigned_path in zip(layout_expectation["centers"], expected_assignments):
        expected_color = Image.open(assigned_path).convert("RGB").getpixel((0, 0))
        assert pages[0].getpixel(sample_point) == expected_color


@pytest.mark.parametrize(
    ("template", "tile_index", "crop_box"),
    [
        (CoverCollageTemplate.FEATURE_SPREAD, 0, (0, 0, 450, 800)),
        (CoverCollageTemplate.FEATURE_SPREAD, 1, (450, 0, 900, 800)),
    ],
)
def test_compose_cover_collage_feature_tiles_use_request_level_cover_mode(
    tmp_path: Path,
    template: CoverCollageTemplate,
    tile_index: int,
    crop_box: tuple[int, int, int, int],
) -> None:
    image_path = tmp_path / f"feature_{tile_index}.png"
    _create_image(image_path, color=(12, 34, 200), size=(120, 600))

    pages, summary = compose_cover_collage(
        [str(image_path)],
        *PAGE_SIZE,
        rng=random.Random(5),
        template=template,
        fitting_mode=CoverCollageFittingMode.COVER,
    )

    assert len(pages) == 1
    assert summary.total_images_placed == TEMPLATE_EXPECTATIONS[template]["slot_count"]
    tile_image = pages[0].crop(crop_box)
    assert tile_image.getbbox() == (0, 0, tile_image.width, tile_image.height)


def test_compose_cover_collage_feature_spread_populates_feature_tiles_without_white_letterboxing(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "feature_spread_cover.png"
    _create_image(image_path, color=(12, 34, 200), size=(120, 600))

    pages, summary = compose_cover_collage(
        [str(image_path)],
        *PAGE_SIZE,
        rng=random.Random(5),
        template=CoverCollageTemplate.FEATURE_SPREAD,
    )

    assert len(pages) == 1
    assert summary.total_images_placed == TEMPLATE_EXPECTATIONS[CoverCollageTemplate.FEATURE_SPREAD]["slot_count"]
    _assert_feature_tiles_are_fully_populated(pages[0])


@pytest.mark.parametrize(
    ("template", "tile_index", "crop_box", "expected_bounds"),
    [
        (CoverCollageTemplate.FEATURE_SPREAD, 0, (0, 0, 450, 800), (145, 0, 304, 799)),
        (CoverCollageTemplate.FEATURE_SPREAD, 1, (450, 0, 900, 800), (145, 0, 304, 799)),
    ],
)
def test_compose_cover_collage_feature_tiles_still_honor_explicit_contain_mode(
    tmp_path: Path,
    template: CoverCollageTemplate,
    tile_index: int,
    crop_box: tuple[int, int, int, int],
    expected_bounds: tuple[int, int, int, int],
) -> None:
    image_path = tmp_path / f"feature_{tile_index}.png"
    _create_image(image_path, color=(12, 34, 200), size=(120, 600))

    pages, summary = compose_cover_collage(
        [str(image_path)],
        *PAGE_SIZE,
        rng=random.Random(5),
        template=template,
        fitting_mode=CoverCollageFittingMode.CONTAIN,
    )

    assert len(pages) == 1
    assert summary.total_images_placed == TEMPLATE_EXPECTATIONS[template]["slot_count"]
    tile_image = pages[0].crop(crop_box)
    assert _find_non_background_bounds(tile_image) == expected_bounds


def _find_non_background_bounds(
    image: Image.Image,
    background_color: tuple[int, int, int] = WHITE,
) -> tuple[int, int, int, int]:
    xs: list[int] = []
    ys: list[int] = []
    for y in range(image.height):
        for x in range(image.width):
            if image.getpixel((x, y)) != background_color:
                xs.append(x)
                ys.append(y)

    assert xs and ys
    return min(xs), min(ys), max(xs), max(ys)


def test_resize_to_contain_preserves_full_image_bounds() -> None:
    image = Image.new("RGB", (120, 600), color=(12, 34, 200))

    resized = _resize_to_contain(image, 300, 200, background_color=(0, 0, 0))

    assert resized.size == (300, 200)
    bounds = _find_non_background_bounds(resized, background_color=(0, 0, 0))
    assert bounds == (130, 0, 169, 199)


def test_compose_cover_collage_contain_mode_renders_full_page(tmp_path: Path) -> None:
    image_path = tmp_path / "portrait.png"
    _create_image(image_path, color=(12, 34, 200), size=(120, 600))

    pages, summary = compose_cover_collage(
        [str(image_path)],
        *PAGE_SIZE,
        rng=random.Random(5),
        fitting_mode=CoverCollageFittingMode.CONTAIN,
    )

    assert len(pages) == 1
    assert pages[0].size == PAGE_SIZE
    assert summary.output_created is True
    assert summary.total_images_placed == 9
    assert summary.total_images_skipped == 0

    colors = pages[0].getcolors(maxcolors=pages[0].width * pages[0].height)
    assert colors is not None
    color_counts = dict(colors)
    assert color_counts.get(WHITE, 0) < pages[0].width * pages[0].height
    assert any(color != WHITE for color in color_counts)
