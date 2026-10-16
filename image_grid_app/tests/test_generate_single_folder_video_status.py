from pathlib import Path

from PIL import Image

from app.routes import jobs


def _create_image(path: Path) -> None:
    Image.new("RGB", (120, 120), color="white").save(path, format="PNG")


def test_generate_single_folder_reports_video_output_path_when_created(
    tmp_path: Path,
    monkeypatch,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()

    for index in range(12):
        _create_image(input_dir / f"img_{index:03}.png")

    expected_video_path = str((output_dir / "preview.mp4").resolve())
    monkeypatch.setattr("app.routes.jobs.build_preview_video", lambda **_: expected_video_path)

    result = jobs._generate_for_single_folder(
        folder_path=str(input_dir),
        output_path=str(output_dir),
        page_width=3000,
        page_height=3000,
        margin=60,
        gap=30,
        export_format="PNG",
        create_video=True,
        video_duration_seconds=15,
        video_transition="none",
        video_filename="preview.mp4",
    )

    assert result.video_created is True
    assert result.video_file == expected_video_path
    assert f"Preview video saved to: {expected_video_path}" in result.message


def test_generate_single_folder_reports_video_failure_with_expected_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()

    for index in range(12):
        _create_image(input_dir / f"img_{index:03}.png")

    monkeypatch.setattr(
        "app.routes.jobs.build_preview_video",
        lambda **_: (_ for _ in ()).throw(RuntimeError("ffmpeg unavailable")),
    )

    result = jobs._generate_for_single_folder(
        folder_path=str(input_dir),
        output_path=str(output_dir),
        page_width=3000,
        page_height=3000,
        margin=60,
        gap=30,
        export_format="PNG",
        create_video=True,
        video_duration_seconds=15,
        video_transition="none",
        video_filename="preview.mp4",
    )

    expected_video_path = str((output_dir / "preview.mp4").resolve())
    assert result.video_created is False
    assert result.video_file is None
    assert f"Expected output path: {expected_video_path}" in result.message
    # The cause is reported as it happened, not as a guess about ffmpeg's install.
    assert "(ffmpeg unavailable)" in result.message
