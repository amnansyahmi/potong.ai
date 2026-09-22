import os
import subprocess
from pathlib import Path
from typing import Any


def _timestamp(seconds: float) -> str:
    value = max(0.0, seconds)
    total_ms = int(round(value * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def write_srt(
    segments: list[dict[str, Any]],
    clip_start: float,
    clip_end: float,
    destination: Path,
) -> None:
    rows: list[str] = []
    index = 1

    for segment in segments:
        segment_start = float(segment["start"])
        segment_end = float(segment["end"])
        start = max(segment_start, clip_start)
        end = min(segment_end, clip_end)

        if end <= clip_start or start >= clip_end or end <= start:
            continue

        rows.extend([
            str(index),
            f"{_timestamp(start - clip_start)} --> {_timestamp(end - clip_start)}",
            str(segment["text"]).strip(),
            "",
        ])
        index += 1

    destination.write_text("\n".join(rows), encoding="utf-8")


def _filter_path(path: Path) -> str:
    value = str(path.resolve()).replace("\\", "/")
    value = value.replace(":", "\\:")
    value = value.replace("'", "\\'")
    return value


CAPTION_STYLES = {
    "clean": (
        "FontName=Arial,FontSize=22,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=0,Alignment=2,MarginV=115"
    ),
    "bold": (
        "FontName=Arial,FontSize=26,Bold=1,PrimaryColour=&H0000E7FF,"
        "OutlineColour=&H00000000,BorderStyle=1,Outline=4,Shadow=0,Alignment=2,MarginV=130"
    ),
    "minimal": (
        "FontName=Arial,FontSize=18,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=3,BackColour=&H90000000,Outline=0,Shadow=0,Alignment=2,MarginV=96"
    ),
}


def _ffmpeg_binary() -> str:
    configured = os.getenv("FFMPEG_BINARY", "").strip()
    if configured:
        return configured
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def render_clip(
    source: Path,
    destination: Path,
    subtitle_file: Path,
    start: float,
    end: float,
    caption_style: str = "clean",
) -> None:
    duration = max(0.1, end - start)
    subtitle_path = _filter_path(subtitle_file)
    subtitle_style = CAPTION_STYLES.get(caption_style, CAPTION_STYLES["clean"])
    video_filter = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        f"subtitles='{subtitle_path}':"
        f"force_style='{subtitle_style}'"
    )

    base_command = [
        _ffmpeg_binary(), "-y", "-ss", f"{start:.3f}", "-i", str(source), "-t", f"{duration:.3f}",
    ]
    encoding = [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(destination),
    ]
    command = [
        *base_command,
        "-vf", video_filter, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(destination),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        # imageio-ffmpeg builds do not always include libass. Keep the MP4 job
        # useful by rendering the vertical crop and returning the SRT separately.
        crop_only = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
        fallback = [*base_command, "-vf", crop_only, *encoding]
        retry = subprocess.run(fallback, capture_output=True, text=True)
        if retry.returncode != 0:
            message = retry.stderr[-3000:] if retry.stderr else "FFmpeg failed."
            raise RuntimeError(message)
