"""DPI has to reach the exported file, or the page has no physical size.

A 3000x4000 export with no resolution metadata is read by print software at the
72 DPI fallback — 41.7x55.6in instead of the intended 10x13.3in. The pixels are
identical either way, which is why this went unnoticed.
"""

from pathlib import Path

import pytest
from PIL import Image

from app.services.exporter import export_pages


def _round_dpi(image: Image.Image) -> tuple[int, int]:
    """PNG stores resolution as integer pixels-per-metre, so 300 round-trips
    as 299.9994. Compare the rounded value rather than the raw float."""
    dpi = image.info.get("dpi")
    assert dpi is not None, "export carried no DPI metadata"
    return (round(dpi[0]), round(dpi[1]))


@pytest.mark.parametrize("export_format,extension", [("PNG", "png"), ("JPG", "jpg")])
def test_export_stamps_dpi(tmp_path: Path, export_format: str, extension: str) -> None:
    page = Image.new("RGB", (600, 800), "white")

    saved = export_pages([page], tmp_path, export_format, path_mode="absolute", dpi=300)

    assert saved[0].endswith(f".{extension}")
    with Image.open(saved[0]) as exported:
        assert _round_dpi(exported) == (300, 300)


def test_export_dpi_is_configurable(tmp_path: Path) -> None:
    saved = export_pages(
        [Image.new("RGB", (100, 100), "white")], tmp_path, "PNG", path_mode="absolute", dpi=150
    )
    with Image.open(saved[0]) as exported:
        assert _round_dpi(exported) == (150, 150)


def test_an_invalid_dpi_is_rejected_at_export(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        export_pages([Image.new("RGB", (10, 10))], tmp_path, "PNG", dpi=0)
