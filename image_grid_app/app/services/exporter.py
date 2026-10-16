"""Service for exporting generated outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Sequence

from PIL import Image

from mullion import DEFAULT_DPI, validate_dpi


ExportFormat = Literal["PNG", "JPG"]
PathMode = Literal["relative", "absolute"]


def _next_available_index(
    output_dir: Path,
    prefix: str,
    extension: str,
    start_index: int = 1,
) -> int:
    """Find the next available sequential page index for conflict-safe exports."""
    index = start_index
    while (output_dir / f"{prefix}_{index:03d}.{extension}").exists():
        index += 1
    return index


def _save_image(
    page: Image.Image,
    destination: Path,
    export_format: ExportFormat,
    *,
    dpi: int = DEFAULT_DPI,
) -> None:
    """Save a single page with format-aware options.

    ``dpi`` is written into the file's metadata (a ``pHYs`` chunk for PNG, a
    JFIF density for JPEG). Without it a 3000x4000 export carries no resolution
    at all, so print software falls back to 72 DPI and reads the page as
    41.7x55.6in instead of 10x13.3in — the same pixels, described as a poster.
    """
    resolution = (dpi, dpi)

    if export_format == "PNG":
        page.save(
            destination,
            format="PNG",
            optimize=True,
            compress_level=6,
            dpi=resolution,
        )
        return

    # JPEG does not support alpha channels.
    page.convert("RGB").save(
        destination,
        format="JPEG",
        quality=95,
        optimize=True,
        subsampling=0,
        dpi=resolution,
    )


def export_pages(
    pages: Sequence[Image.Image],
    output_dir: str | Path,
    export_format: ExportFormat,
    *,
    path_mode: PathMode = "relative",
    filename_prefix: str = "page",
    dpi: int = DEFAULT_DPI,
) -> list[str]:
    """Export composed pages with sequential names and conflict-safe behavior.

    Filenames are generated as `<prefix>_001.<ext>`, `<prefix>_002.<ext>`, etc.
    The default prefix keeps standard exports as `page_001.<ext>`, `page_002.<ext>`, etc.
    If files already exist, numbering continues from the next available index
    rather than overwriting existing files.

    ``dpi`` is stamped into every exported file so the page reports its intended
    physical size to print software rather than defaulting to 72 DPI.
    """
    target_dir = Path(output_dir).expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)

    normalized_format = export_format.upper()
    if normalized_format not in {"PNG", "JPG"}:
        raise ValueError("Unsupported export format. Use 'PNG' or 'JPG'.")
    if not filename_prefix:
        raise ValueError("filename_prefix must be a non-empty string.")
    resolved_dpi = validate_dpi(dpi)

    extension = "png" if normalized_format == "PNG" else "jpg"
    current_index = _next_available_index(target_dir, filename_prefix, extension)

    saved_paths: list[str] = []
    for page in pages:
        output_path = target_dir / f"{filename_prefix}_{current_index:03d}.{extension}"
        _save_image(page, output_path, normalized_format, dpi=resolved_dpi)

        if path_mode == "absolute":
            saved_paths.append(str(output_path.resolve()))
        elif path_mode == "relative":
            saved_paths.append(str(output_path))
        else:
            raise ValueError("Unsupported path_mode. Use 'relative' or 'absolute'.")

        current_index += 1

    return saved_paths
