"""Upscaling: every image of a bundle made bigger, saved as PNG and as JPG.

Lanczos resampling makes an image bigger without blocks or jagged edges, but
it can't add detail the image doesn't have, so at 4x clip art comes out soft.
Pillow premultiplies alpha as it resamples, so a cutout's edge doesn't pick
up a dark fringe from the transparent pixels around it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from PIL import Image

from mullion import flatten_onto, open_path, validate_dpi

logger = logging.getLogger(__name__)

UPSCALE_FACTORS = (2, 3, 4)
# Made inside the bundle's output folder, with a folder per format inside it.
UPSCALED_FOLDER_NAME = "Upscaled"
# As for pages (MAX_PAGE_MEGAPIXELS in routes/jobs.py): an image is held in
# memory several times over while it is resampled and saved, and a 3000 px
# image at 4x is already 144 MP.
MAX_UPSCALED_MEGAPIXELS = 100
# Files sharing a name, as art.png and art.jpg often do, would be saved over
# each other, so one gives both formats: lossless and maybe transparent first.
_SOURCE_PREFERENCE = {".png": 0, ".webp": 1, ".jpg": 2, ".jpeg": 2}


class _TooLarge(Exception):
    pass


@dataclass
class UpscaleSummary:
    scale: int
    output_dir: Path
    upscaled: list[str] = field(default_factory=list)
    output_files: list[str] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)
    too_large: list[str] = field(default_factory=list)
    same_name: list[str] = field(default_factory=list)

    @property
    def png_dir(self) -> Path:
        return self.output_dir / "PNG"

    @property
    def jpg_dir(self) -> Path:
        return self.output_dir / "JPG"

    @property
    def user_message(self) -> str:
        parts = [f"Upscaled {len(self.upscaled)} image(s) {self.scale}x, each saved as PNG and JPG."]
        if self.unreadable:
            parts.append(f"Skipped {len(self.unreadable)} unreadable file(s).")
        if self.too_large:
            parts.append(
                f"Left out {len(self.too_large)} image(s) that would pass {MAX_UPSCALED_MEGAPIXELS} MP "
                f"at {self.scale}x: {', '.join(self.too_large)}."
            )
        if self.same_name:
            parts.append(
                f"Left out {len(self.same_name)} file(s) named like an image in another format, "
                f"which gave both formats: {', '.join(self.same_name)}."
            )
        return " ".join(parts)


def upscale_images(image_paths: Sequence[Path], output_dir: Path, *, scale: int, dpi: int) -> UpscaleSummary:
    """Upscale each image ``scale`` times into ``output_dir``/PNG and /JPG.

    A file keeps its name, so upscaling again replaces what the last run made.
    The PNG keeps any transparency; the JPG is flattened onto white.
    """
    if scale not in UPSCALE_FACTORS:
        raise ValueError(f"Scale must be one of {', '.join(map(str, UPSCALE_FACTORS))}.")
    resolved_dpi = validate_dpi(dpi)

    summary = UpscaleSummary(scale=scale, output_dir=output_dir)
    sources, summary.same_name = _one_file_per_name(image_paths)
    for path in sources:
        try:
            upscaled = _upscale(path, scale)
        except _TooLarge:
            summary.too_large.append(path.name)
            continue
        except (OSError, ValueError) as exc:
            summary.unreadable.append(path.name)
            logger.warning("Skipping unreadable image '%s': %s", path, exc)
            continue

        summary.output_files.extend(_save_both_formats(upscaled, summary, path.stem, resolved_dpi))
        summary.upscaled.append(path.name)
    return summary


def _one_file_per_name(image_paths: Sequence[Path]) -> tuple[list[Path], list[str]]:
    """The files to upscale, and the names of those left out for sharing a name.

    Names are compared ignoring case, as Mac and Windows file systems do.
    """
    chosen: dict[str, Path] = {}
    for path in image_paths:
        current = chosen.get(path.stem.casefold())
        if current is None or _preference(path) < _preference(current):
            chosen[path.stem.casefold()] = path

    kept = set(chosen.values())
    return [path for path in image_paths if path in kept], [path.name for path in image_paths if path not in kept]


def _preference(path: Path) -> int:
    return _SOURCE_PREFERENCE.get(path.suffix.lower(), len(_SOURCE_PREFERENCE))


def _upscale(path: Path, scale: int) -> Image.Image:
    # The size is read from the header first, so an image too big to upscale
    # is never decoded at all.
    try:
        with Image.open(path) as probe:
            width, height = probe.size
    except Image.DecompressionBombError as exc:
        raise _TooLarge from exc
    if width * height * scale * scale > MAX_UPSCALED_MEGAPIXELS * 1_000_000:
        raise _TooLarge

    # Upright, with any transparency kept as RGBA.
    image = open_path(path, keep_alpha=True)
    if image.getchannel("A").getextrema() == (255, 255):
        # Opaque after all: without an alpha channel the PNG is smaller.
        image = image.convert("RGB")
    return image.resize((image.width * scale, image.height * scale), Image.Resampling.LANCZOS)


def _save_both_formats(image: Image.Image, summary: UpscaleSummary, stem: str, dpi: int) -> list[str]:
    summary.png_dir.mkdir(parents=True, exist_ok=True)
    summary.jpg_dir.mkdir(parents=True, exist_ok=True)
    png_path = summary.png_dir / f"{stem}.png"
    jpg_path = summary.jpg_dir / f"{stem}.jpg"

    # Not optimize=True, as the exporter's pages are: on a 4x upscale it
    # tripled the time for a file no smaller.
    image.save(png_path, format="PNG", compress_level=6, dpi=(dpi, dpi))
    # JPEG has no transparency; the same settings as exported pages.
    jpg_image = image if image.mode == "RGB" else flatten_onto(image)
    jpg_image.save(jpg_path, format="JPEG", quality=95, optimize=True, subsampling=0, dpi=(dpi, dpi))
    return [str(png_path), str(jpg_path)]
