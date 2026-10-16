from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from pasteup.main import app
from pasteup.services import upscaler

client = TestClient(app)

RED = (220, 40, 40)


def _photo(path: Path, size: tuple[int, int] = (40, 30)) -> None:
    Image.new("RGB", size, (90, 160, 220)).save(path)


def _cutout(path: Path) -> None:
    """A red square on a transparent page: clip art as it is usually sold."""
    image = Image.new("RGBA", (50, 40), (0, 0, 0, 0))
    image.paste(RED + (255,), (10, 10, 40, 30))
    image.save(path)


def _upscale(folder: Path, output: Path, **overrides) -> dict:
    response = client.post(
        "/api/jobs/upscale-images",
        json={"folder_path": str(folder), "output_path": str(output), "scale": 2, "dpi": 300, **overrides},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_each_image_is_upscaled_into_a_png_and_a_jpg_folder(tmp_path: Path) -> None:
    source = tmp_path / "bundle"
    source.mkdir()
    _photo(source / "photo.jpg")
    _cutout(source / "cutout.png")
    output = tmp_path / "---Created---" / "bundle"

    result = _upscale(source, output, scale=3)

    upscaled = output / "Upscaled"
    assert result["success"] is True
    assert result["total_images"] == 2
    assert result["output_path"] == str(upscaled)
    assert result["png_folder"] == str(upscaled / "PNG")
    assert result["jpg_folder"] == str(upscaled / "JPG")
    assert sorted(result["output_files"]) == sorted(
        str(upscaled / folder / f"{name}.{folder.lower()}")
        for name in ("cutout", "photo")
        for folder in ("PNG", "JPG")
    )
    for path in map(Path, result["output_files"]):
        with Image.open(path) as image:
            assert image.size == ((150, 120) if path.stem == "cutout" else (120, 90))
            assert round(image.info["dpi"][0]) == 300


def test_the_png_keeps_transparency_without_a_dark_fringe_and_the_jpg_goes_on_white(tmp_path: Path) -> None:
    source = tmp_path / "bundle"
    source.mkdir()
    _cutout(source / "cutout.png")

    _upscale(source, tmp_path / "out", scale=4)

    with Image.open(tmp_path / "out" / "Upscaled" / "PNG" / "cutout.png") as png:
        assert png.mode == "RGBA"
        assert png.getpixel((0, 0))[3] == 0
        # Resampled without premultiplying, the square's edge would blend
        # towards the black of the transparent pixels around it (red ~130).
        reds, alphas = png.getchannel("R").tobytes(), png.getchannel("A").tobytes()
        edge_reds = [red for red, alpha in zip(reds, alphas) if 128 <= alpha < 255]
        assert edge_reds and min(edge_reds) > 200
    with Image.open(tmp_path / "out" / "Upscaled" / "JPG" / "cutout.jpg") as jpg:
        assert jpg.mode == "RGB"
        assert jpg.getpixel((0, 0)) == (255, 255, 255)


def test_an_opaque_image_makes_a_png_without_an_alpha_channel(tmp_path: Path) -> None:
    source = tmp_path / "bundle"
    source.mkdir()
    _photo(source / "photo.png")

    _upscale(source, tmp_path / "out")

    with Image.open(tmp_path / "out" / "Upscaled" / "PNG" / "photo.png") as png:
        assert png.mode == "RGB"


def test_a_phone_photo_is_upscaled_upright(tmp_path: Path) -> None:
    source = tmp_path / "bundle"
    source.mkdir()
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90 degrees to display.
    Image.new("RGB", (40, 30), "white").save(source / "phone.jpg", exif=exif)

    _upscale(source, tmp_path / "out")

    with Image.open(tmp_path / "out" / "Upscaled" / "JPG" / "phone.jpg") as jpg:
        assert jpg.size == (60, 80)


def test_one_image_of_a_name_gives_both_formats(tmp_path: Path) -> None:
    """art.png and art.jpg would be saved over each other; the PNG is used."""
    source = tmp_path / "bundle"
    source.mkdir()
    _cutout(source / "art.png")
    _photo(source / "Art.jpg")

    result = _upscale(source, tmp_path / "out")

    assert result["total_images"] == 1
    assert result["same_name_files"] == ["Art.jpg"]
    with Image.open(tmp_path / "out" / "Upscaled" / "PNG" / "art.png") as png:
        assert png.mode == "RGBA"
    assert "Art.jpg" in result["message"]


def test_an_image_too_big_to_upscale_is_left_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upscaler, "MAX_UPSCALED_MEGAPIXELS", 0.01)  # 10,000 pixels
    source = tmp_path / "bundle"
    source.mkdir()
    _photo(source / "small.png", (40, 30))  # 80 x 60 at 2x: 4,800 pixels
    _photo(source / "big.png", (60, 60))  # 120 x 120 at 2x: 14,400 pixels

    result = _upscale(source, tmp_path / "out")

    assert result["total_images"] == 1
    assert result["too_large_files"] == ["big.png"]
    assert not (tmp_path / "out" / "Upscaled" / "PNG" / "big.png").exists()


def test_an_image_too_big_even_to_open_is_left_out_before_it_is_decoded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Pillow refuses to open an image over twice this many pixels.
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1_000)
    source = tmp_path / "bundle"
    source.mkdir()
    _photo(source / "huge.png", (60, 60))

    result = _upscale(source, tmp_path / "out")

    assert result["success"] is False
    assert result["too_large_files"] == ["huge.png"]
    assert result["output_files"] == []


def test_an_unreadable_file_is_skipped(tmp_path: Path) -> None:
    source = tmp_path / "bundle"
    source.mkdir()
    _photo(source / "good.png")
    (source / "broken.png").write_bytes(b"not an image")

    result = _upscale(source, tmp_path / "out")

    assert result["total_images"] == 1
    assert result["images_skipped"] == 1


def test_upscaling_again_replaces_what_the_last_run_made(tmp_path: Path) -> None:
    source = tmp_path / "bundle"
    source.mkdir()
    _photo(source / "photo.png")

    _upscale(source, tmp_path / "out", scale=2)
    _upscale(source, tmp_path / "out", scale=4)

    png_folder = tmp_path / "out" / "Upscaled" / "PNG"
    assert [path.name for path in png_folder.iterdir()] == ["photo.png"]
    with Image.open(png_folder / "photo.png") as png:
        assert png.size == (160, 120)


@pytest.mark.parametrize("scale", [1, 5, 2.5])
def test_the_scale_must_be_2_3_or_4(tmp_path: Path, scale: float) -> None:
    response = client.post(
        "/api/jobs/upscale-images",
        json={"folder_path": str(tmp_path), "output_path": str(tmp_path / "out"), "scale": scale},
    )

    assert response.status_code == 422
    assert not (tmp_path / "out").exists()


def test_a_folder_without_images_is_refused(tmp_path: Path) -> None:
    response = client.post(
        "/api/jobs/upscale-images",
        json={"folder_path": str(tmp_path), "output_path": str(tmp_path / "out")},
    )

    assert response.status_code == 400
    assert "No supported image files" in response.json()["detail"]


def test_many_bundles_are_each_upscaled_into_their_own_folder(tmp_path: Path) -> None:
    parent = tmp_path / "clip-art"
    for bundle, count in (("bundle-a", 2), ("bundle-b", 1), ("empty", 0)):
        (parent / bundle).mkdir(parents=True)
        for index in range(count):
            _photo(parent / bundle / f"art_{index}.png")
    (parent / "bundle-b" / "broken.png").write_bytes(b"not an image")
    created_root = parent / "---Created---"

    response = client.post(
        "/api/jobs/upscale-images-batch",
        json={
            "parent_folder_path": str(parent),
            "created_output_root_path": str(created_root),
            "selected_subfolders": [str(parent / name) for name in ("bundle-a", "bundle-b", "empty")],
            "scale": 3,
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["scale"] == 3
    assert result["generated_folders"] == 2
    assert [(r["folder_name"], r["success"], r["total_images"]) for r in result["bundle_results"]] == [
        ("bundle-a", True, 2),
        ("bundle-b", True, 1),
        ("empty", False, 0),
    ]
    # What a bundle couldn't use is reported per bundle, as for one bundle.
    assert result["bundle_results"][1]["images_skipped"] == 1
    assert (created_root / "bundle-a" / "Upscaled" / "JPG" / "art_1.jpg").exists()
    assert (created_root / "bundle-b" / "Upscaled" / "PNG" / "art_0.png").exists()


def test_many_bundles_refuses_a_folder_outside_the_parent(tmp_path: Path) -> None:
    parent = tmp_path / "clip-art"
    (parent / "bundle").mkdir(parents=True)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    _photo(outside / "art.png")

    response = client.post(
        "/api/jobs/upscale-images-batch",
        json={
            "parent_folder_path": str(parent),
            "created_output_root_path": str(parent / "---Created---"),
            "selected_subfolders": [str(outside)],
        },
    )

    assert response.status_code == 400
    assert not (parent / "---Created---").exists()
