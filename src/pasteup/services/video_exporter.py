"""Service for building preview videos from exported page images."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image

VideoTransition = Literal["none", "crossfade", "flip"]

# A conventional frame rate, so players and upload pipelines handle the file.
# Slideshow timing is expressed as frame counts, not by slowing the rate down.
FRAME_RATE = 30
# A preview, not a print master: listing sites show video at about 1080p, and
# full print-size frames take several times longer to encode and can exceed
# what H.264 decoders accept. Smaller pages are never scaled up.
MAX_VIDEO_SIDE = 1920
# Transitions are short and fixed, and never take more than a third of a page's
# share of the video, so the pages fill it rather than the blends between them.
MAX_TRANSITION_SECONDS = 0.5
_XFADE_TRANSITIONS = {"crossfade": "fade", "flip": "squeezev"}


@dataclass(frozen=True, slots=True)
class _Timeline:
    total_frames: int
    # Frames each page's clip runs, including its overlap with the next page.
    clip_frames: int
    # The last clip also absorbs the rounding remainder, so the total is exact.
    last_clip_frames: int
    transition_frames: int


def build_preview_video(
    page_paths: list[str],
    output_dir: str | Path,
    duration_seconds: float,
    transition: str,
    filename: str,
) -> str:
    """Build an MP4 preview from exported page images.

    Args:
        page_paths: Paths to exported page image files.
        output_dir: Directory where the output MP4 should be written.
        duration_seconds: Desired total video duration.
        transition: Transition mode ("none", "crossfade", "flip").
        filename: Output MP4 filename.

    Returns:
        The absolute output path for the generated MP4.

    Raises:
        ValueError: If pages are empty, duration is invalid, paths are invalid,
            or transition mode is unsupported.
        RuntimeError: If ffmpeg is unavailable or video encoding fails.
    """
    validated_page_paths = _validate_page_paths(page_paths)
    # ffmpeg overwrites its output, so the video must not land outside output_dir.
    if filename in {"", ".", ".."} or Path(filename).name != filename:
        raise ValueError("filename must be a plain file name inside output_dir.")
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be greater than 0.")

    if transition not in {"none", "crossfade", "flip"}:
        raise ValueError("transition must be one of: 'none', 'crossfade', 'flip'.")

    ffmpeg_binary = shutil.which("ffmpeg")
    if ffmpeg_binary is None:
        raise RuntimeError("ffmpeg is required to export preview videos but was not found on PATH")

    target_dir = Path(output_dir).expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)
    output_path = target_dir / filename

    timeline = _plan_timeline(len(validated_page_paths), duration_seconds, transition)
    width, height = _video_frame_size(validated_page_paths[0])

    command = [ffmpeg_binary, "-y", "-hide_banner", "-loglevel", "error"]
    for index, page_path in enumerate(validated_page_paths):
        # One decoded frame a second is plenty for a still; the fps filter
        # repeats it, and trim cuts the clip to its exact frame count.
        clip_seconds = _clip_frames(timeline, index, len(validated_page_paths)) / FRAME_RATE
        command += ["-loop", "1", "-framerate", "1", "-t", f"{clip_seconds + 1:.6f}", "-i", str(page_path)]

    filter_graph, output_label = _build_filter_graph(
        timeline,
        page_count=len(validated_page_paths),
        xfade_transition=_XFADE_TRANSITIONS.get(transition),
        width=width,
        height=height,
    )
    command += [
        "-filter_complex",
        filter_graph,
        "-map",
        f"[{output_label}]",
        "-frames:v",
        str(timeline.total_frames),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FRAME_RATE),
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffmpeg failed to encode the preview video: {_first_error_line(exc.stderr)}") from exc
    except OSError as exc:
        raise RuntimeError(f"ffmpeg could not be started: {exc}") from exc

    return str(output_path.resolve())


def _validate_page_paths(page_paths: list[str]) -> list[Path]:
    if not page_paths:
        raise ValueError("page_paths cannot be empty.")

    validated_paths = sorted(Path(path).expanduser() for path in page_paths)
    missing_paths = [str(path) for path in validated_paths if not path.exists()]
    if missing_paths:
        raise ValueError(f"One or more page_paths do not exist: {', '.join(missing_paths)}")

    return validated_paths


def _plan_timeline(page_count: int, duration_seconds: float, transition: str) -> _Timeline:
    # Every page needs at least one frame, even if that runs past the duration.
    total_frames = max(page_count, round(duration_seconds * FRAME_RATE))

    transition_frames = 0
    if transition != "none" and page_count > 1:
        transition_frames = min(
            round(MAX_TRANSITION_SECONDS * FRAME_RATE),
            total_frames // (page_count * 3),
        )

    # Consecutive clips overlap by one transition, so together they cover more
    # frames than the video holds.
    covered_frames = total_frames + (page_count - 1) * transition_frames
    clip_frames = covered_frames // page_count
    return _Timeline(
        total_frames=total_frames,
        clip_frames=clip_frames,
        last_clip_frames=clip_frames + covered_frames % page_count,
        transition_frames=transition_frames,
    )


def _clip_frames(timeline: _Timeline, index: int, page_count: int) -> int:
    return timeline.last_clip_frames if index == page_count - 1 else timeline.clip_frames


def _video_frame_size(first_page: Path) -> tuple[int, int]:
    try:
        with Image.open(first_page) as page:
            width, height = page.size
    except OSError as exc:
        raise RuntimeError(f"Could not read page {first_page.name}: {exc}") from exc

    scale = min(1.0, MAX_VIDEO_SIDE / max(width, height))
    # yuv420p stores colour at half resolution, so libx264 refuses odd sizes.
    return max(2, int(width * scale) // 2 * 2), max(2, int(height * scale) // 2 * 2)


def _build_filter_graph(
    timeline: _Timeline,
    *,
    page_count: int,
    xfade_transition: str | None,
    width: int,
    height: int,
) -> tuple[str, str]:
    # Fit each page into the frame without distortion; pages from one run share
    # a size, so the padding only shows if a caller mixes sizes.
    fit = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=white"
    )
    parts = [
        (
            f"[{index}:v]{fit},setsar=1,format=yuv420p,fps={FRAME_RATE},"
            f"trim=end_frame={_clip_frames(timeline, index, page_count)},setpts=PTS-STARTPTS[p{index}]"
        )
        for index in range(page_count)
    ]

    if page_count == 1:
        return ";".join(parts), "p0"

    if xfade_transition is None or timeline.transition_frames == 0:
        clips = "".join(f"[p{index}]" for index in range(page_count))
        parts.append(f"{clips}concat=n={page_count}:v=1:a=0[video]")
        return ";".join(parts), "video"

    transition_seconds = timeline.transition_frames / FRAME_RATE
    current_label = "p0"
    for index in range(1, page_count):
        offset_seconds = index * (timeline.clip_frames - timeline.transition_frames) / FRAME_RATE
        output_label = f"x{index}"
        parts.append(
            f"[{current_label}][p{index}]xfade=transition={xfade_transition}:"
            f"duration={transition_seconds:.6f}:offset={offset_seconds:.6f}[{output_label}]"
        )
        current_label = output_label

    return ";".join(parts), current_label


def _first_error_line(stderr: str | None) -> str:
    """ffmpeg reports the specific failure first and generic wrappers after it."""
    for line in (stderr or "").splitlines():
        if line.strip():
            # Drop the memory address ffmpeg prints beside each component's name.
            return re.sub(r" @ 0x[0-9a-f]+", "", line.strip())
    return "no error output"
