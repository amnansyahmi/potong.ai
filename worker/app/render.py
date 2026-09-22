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


def render_clip(source: Path, destination: Path, subtitle_file: Path, start: float, end: float) -> None:
    duration = max(0.1, end - start)
    subtitle_path = _filter_path(subtitle_file)
    video_filter = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        f"subtitles='{subtitle_path}':"
        "force_style='FontName=Arial,FontSize=22,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=0,Alignment=2,MarginV=115'"
    )

    command = [
        "ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", str(source), "-t", f"{duration:.3f}",
        "-vf", video_filter, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(destination),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        message = completed.stderr[-3000:] if completed.stderr else "FFmpeg failed."
        raise RuntimeError(message)
