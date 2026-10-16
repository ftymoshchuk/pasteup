"""Service for scanning image folders."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
DEFAULT_SAMPLE_SIZE = 5
IMAGES_PER_PAGE_ESTIMATE = 12
# Batch scanning and validation must reject generated-output folders so the UI only
# offers real source bundles. Keep this list here alongside the discovery helpers to
# avoid reintroducing output directories such as `---Created---` into batch selection.
EXCLUDED_GENERATED_FOLDER_NAMES = frozenset({"---Created---"})


def scan_folder(folder_path: str, sample_size: int = DEFAULT_SAMPLE_SIZE) -> dict[str, object]:
    """Scan a folder for supported image files.

    The scan is non-recursive and only inspects files directly inside
    ``folder_path``.
    """
    normalized_sample_size = max(0, sample_size)

    # A blank path would otherwise resolve to the server's working directory and
    # scan that instead.
    if isinstance(folder_path, str) and not folder_path.strip():
        return _build_response(
            valid=False,
            image_count=0,
            sample_files=[],
            estimated_pages=0,
            available_subfolders=[],
            message="Enter a folder path to scan.",
        )

    try:
        folder = resolve_folder_path(folder_path)
    except (TypeError, ValueError):
        return _build_response(
            valid=False,
            image_count=0,
            sample_files=[],
            estimated_pages=0,
            available_subfolders=[],
            message="Invalid folder path.",
        )

    if not folder.exists():
        return _build_response(
            valid=False,
            image_count=0,
            sample_files=[],
            estimated_pages=0,
            available_subfolders=[],
            message=f"Folder not found: {folder}. Check the path for typos.",
        )

    if not folder.is_dir():
        return _build_response(
            valid=False,
            image_count=0,
            sample_files=[],
            estimated_pages=0,
            available_subfolders=[],
            message=f"Path is not a folder: {folder}",
        )

    image_names = [path.name for path in list_supported_image_paths(folder)]

    image_count = len(image_names)
    sample_files = image_names[:normalized_sample_size]

    if image_count == 0:
        available_subfolders = list_child_folder_paths(folder)
        if available_subfolders:
            return _build_response(
                valid=False,
                image_count=0,
                sample_files=[],
                estimated_pages=0,
                available_subfolders=available_subfolders,
                message=(
                    "No supported image files were found at the top level, "
                    "but direct subfolders are available to scan."
                ),
            )

        return _build_response(
            valid=False,
            image_count=0,
            sample_files=[],
            estimated_pages=0,
            available_subfolders=[],
            message="No supported image files found (.jpg, .jpeg, .png, .webp).",
        )

    estimated_pages = image_count // IMAGES_PER_PAGE_ESTIMATE
    return _build_response(
        valid=True,
        image_count=image_count,
        sample_files=sample_files,
        estimated_pages=estimated_pages,
        available_subfolders=[],
        message=f"Found {image_count} supported image file(s).",
    )


def _build_response(
    *,
    valid: bool,
    image_count: int,
    sample_files: list[str],
    estimated_pages: int,
    available_subfolders: list[dict[str, str]],
    message: str,
) -> dict[str, object]:
    return {
        "valid": valid,
        "image_count": image_count,
        "sample_files": sample_files,
        "estimated_pages": estimated_pages,
        "available_subfolders": available_subfolders,
        "message": message,
    }


def resolve_folder_path(folder_path: str) -> Path:
    return Path(folder_path).expanduser().resolve(strict=False)


def list_supported_image_paths(folder: Path, *, recursive: bool = False) -> list[Path]:
    iterator: Iterable[Path]
    if recursive:
        iterator = (item for item in folder.rglob("*") if item.is_file())
    else:
        iterator = folder.iterdir()

    return sorted(
        [
            item
            for item in iterator
            if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS
        ],
        key=lambda path: (path.name.lower(), path.name, str(path)),
    )


def is_generated_output_folder(folder: Path) -> bool:
    return folder.name in EXCLUDED_GENERATED_FOLDER_NAMES


def list_child_folder_paths(folder: Path) -> list[dict[str, str]]:
    return [
        {"display_name": path.name, "full_path": str(path)}
        for path in sorted(
            (
                item.resolve(strict=False)
                for item in folder.iterdir()
                if item.is_dir() and not is_generated_output_folder(item)
            ),
            key=lambda path: (path.name.lower(), path.name, str(path)),
        )
    ]
