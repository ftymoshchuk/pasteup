import json
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from pasteup.services import video_exporter
from pasteup.services.video_exporter import (
    FRAME_RATE,
    MAX_TRANSITION_SECONDS,
    MAX_VIDEO_SIDE,
    _plan_timeline,
    build_preview_video,
)

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are needed to encode and inspect a real video",
)


def _create_image(path: Path, color: str, size: tuple[int, int] = (100, 100)) -> None:
    Image.new("RGB", size, color=color).save(path, format="PNG")


def _pages(tmp_path: Path, count: int, size: tuple[int, int] = (64, 48)) -> list[str]:
    colors = ["red", "green", "blue", "orange", "purple", "teal"]
    paths = []
    for index in range(count):
        path = tmp_path / f"page_{index + 1:03d}.png"
        _create_image(path, colors[index % len(colors)], size)
        paths.append(str(path))
    return paths


def _probe(video: str) -> dict[str, object]:
    output = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_entries",
            "stream=width,height,r_frame_rate,nb_read_frames",
            "-of",
            "json",
            video,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(output)["streams"][0]


def test_build_preview_video_raises_for_empty_pages(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="page_paths cannot be empty"):
        build_preview_video([], tmp_path, 3.0, "none", "preview.mp4")


def test_build_preview_video_raises_for_invalid_duration(tmp_path: Path) -> None:
    image_path = tmp_path / "page_002.png"
    _create_image(image_path, "red")

    with pytest.raises(ValueError, match="duration_seconds must be greater than 0"):
        build_preview_video([str(image_path)], tmp_path, 0, "none", "preview.mp4")


def test_build_preview_video_sorts_paths_before_encoding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page_2 = tmp_path / "page_002.png"
    page_1 = tmp_path / "page_001.png"
    _create_image(page_1, "red")
    _create_image(page_2, "blue")

    monkeypatch.setattr("pasteup.services.video_exporter.shutil.which", lambda _: "/usr/bin/ffmpeg")

    captured: dict[str, list[str]] = {}

    def _fake_run(command: list[str], check: bool, capture_output: bool, text: bool) -> None:
        captured["command"] = command

    monkeypatch.setattr("pasteup.services.video_exporter.subprocess.run", _fake_run)

    output = build_preview_video(
        [str(page_2), str(page_1)],
        tmp_path,
        2.0,
        "crossfade",
        "preview.mp4",
    )

    assert output == str((tmp_path / "preview.mp4").resolve())
    assert captured["command"][0] == "/usr/bin/ffmpeg"
    inputs = [captured["command"][i + 1] for i, arg in enumerate(captured["command"]) if arg == "-i"]
    assert inputs == [str(page_1), str(page_2)]


@pytest.mark.parametrize("page_count", [1, 2, 3, 7, 10, 30])
@pytest.mark.parametrize("transition", ["none", "crossfade"])
def test_timeline_fills_exactly_the_requested_duration(page_count: int, transition: str) -> None:
    timeline = _plan_timeline(page_count, 15.0, transition)

    clips = [timeline.clip_frames] * (page_count - 1) + [timeline.last_clip_frames]
    assert sum(clips) - (page_count - 1) * timeline.transition_frames == 15 * FRAME_RATE


def test_pages_not_transitions_fill_the_video() -> None:
    """3 pages over 15 s used to show each page for 1.7 s and each fade for 5 s."""
    timeline = _plan_timeline(3, 15.0, "crossfade")

    assert timeline.transition_frames == round(MAX_TRANSITION_SECONDS * FRAME_RATE)
    page_only_frames = timeline.clip_frames - 2 * timeline.transition_frames
    assert page_only_frames > 8 * timeline.transition_frames


def test_transitions_shrink_when_pages_are_short() -> None:
    timeline = _plan_timeline(30, 15.0, "crossfade")

    slot_frames = 15 * FRAME_RATE / 30
    assert 0 < timeline.transition_frames <= slot_frames / 3


def test_every_page_gets_a_frame_even_when_the_duration_is_too_short() -> None:
    timeline = _plan_timeline(50, 1.0, "crossfade")

    assert timeline.transition_frames == 0
    assert timeline.clip_frames >= 1


@needs_ffmpeg
def test_odd_page_sizes_still_encode(tmp_path: Path) -> None:
    """libx264 refuses odd dimensions in yuv420p; this used to fail every time."""
    pages = _pages(tmp_path, 2, size=(101, 75))

    video = build_preview_video(pages, tmp_path / "out", 2.0, "crossfade", "preview.mp4")

    stream = _probe(video)
    assert (stream["width"], stream["height"]) == (100, 74)


@needs_ffmpeg
@pytest.mark.parametrize("transition", ["none", "crossfade", "flip"])
def test_video_runs_the_requested_duration_at_a_standard_frame_rate(tmp_path: Path, transition: str) -> None:
    pages = _pages(tmp_path, 3)

    video = build_preview_video(pages, tmp_path / "out", 3.0, transition, "preview.mp4")

    stream = _probe(video)
    assert stream["r_frame_rate"] == f"{FRAME_RATE}/1"
    assert int(stream["nb_read_frames"]) == 3 * FRAME_RATE


@needs_ffmpeg
def test_large_pages_are_scaled_down_for_the_preview(tmp_path: Path) -> None:
    pages = _pages(tmp_path, 1, size=(MAX_VIDEO_SIDE * 2, MAX_VIDEO_SIDE))

    video = build_preview_video(pages, tmp_path / "out", 1.0, "none", "preview.mp4")

    stream = _probe(video)
    assert (stream["width"], stream["height"]) == (MAX_VIDEO_SIDE, MAX_VIDEO_SIDE // 2)


@needs_ffmpeg
def test_encoding_failure_reports_ffmpegs_own_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The old message always blamed a missing ffmpeg, whatever had gone wrong."""
    monkeypatch.setitem(video_exporter._XFADE_TRANSITIONS, "crossfade", "no-such-transition")
    pages = _pages(tmp_path, 2)

    with pytest.raises(RuntimeError, match=r"ffmpeg failed to encode the preview video: \[Parsed_xfade_\d+\] \w+"):
        build_preview_video(pages, tmp_path / "out", 2.0, "crossfade", "preview.mp4")


def test_an_unreadable_page_is_reported_not_raised_raw(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pasteup.services.video_exporter.shutil.which", lambda _: "/usr/bin/ffmpeg")
    broken_page = tmp_path / "page_001.png"
    broken_page.write_bytes(b"not a png")

    with pytest.raises(RuntimeError, match="Could not read page page_001.png"):
        build_preview_video([str(broken_page)], tmp_path / "out", 1.0, "none", "preview.mp4")
