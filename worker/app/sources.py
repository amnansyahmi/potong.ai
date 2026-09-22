import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


def validate_youtube_url(value: str) -> str:
    url = value.strip()
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    if parsed.scheme != "https" or hostname not in YOUTUBE_HOSTS:
        raise ValueError("Masukkan URL YouTube yang sah menggunakan https://.")

    if hostname == "youtu.be" and not parsed.path.strip("/"):
        raise ValueError("URL YouTube tidak mempunyai video ID.")

    return url


def _ydl_options(download: bool, destination: Path | None = None) -> dict[str, Any]:
    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 2,
    }

    if download:
        if destination is None:
            raise ValueError("Destination is required for downloads.")
        options.update({
            "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
            "merge_output_format": "mp4",
            "outtmpl": str(destination / "source.%(ext)s"),
        })
    else:
        options["skip_download"] = True

    return options


def _clean_info(info: dict[str, Any], url: str) -> dict[str, Any]:
    duration = int(info.get("duration") or 0)
    max_duration = int(os.getenv("MAX_SOURCE_DURATION_SECONDS", "14400"))
    if duration and duration > max_duration:
        raise ValueError(f"Video melebihi had {max_duration // 3600} jam untuk worker ini.")

    return {
        "url": url,
        "title": str(info.get("title") or "Video YouTube")[:240],
        "channel": str(info.get("channel") or info.get("uploader") or "")[:160],
        "thumbnail": str(info.get("thumbnail") or ""),
        "duration": duration,
        "webpage_url": str(info.get("webpage_url") or url),
    }


def inspect_youtube(url: str) -> dict[str, Any]:
    from yt_dlp import YoutubeDL

    safe_url = validate_youtube_url(url)
    with YoutubeDL(_ydl_options(download=False)) as ydl:
        info = ydl.extract_info(safe_url, download=False)
    if not isinstance(info, dict):
        raise RuntimeError("Metadata video tidak dapat dibaca.")
    return _clean_info(info, safe_url)


def download_youtube(url: str, destination: Path) -> tuple[Path, dict[str, Any]]:
    from yt_dlp import YoutubeDL

    safe_url = validate_youtube_url(url)
    with YoutubeDL(_ydl_options(download=True, destination=destination)) as ydl:
        info = ydl.extract_info(safe_url, download=True)

    if not isinstance(info, dict):
        raise RuntimeError("YouTube tidak memulangkan maklumat video.")

    metadata = _clean_info(info, safe_url)
    candidates = [
        path
        for path in destination.glob("source.*")
        if path.suffix.lower() in {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
    ]
    if not candidates:
        raise RuntimeError("Fail video YouTube tidak dijumpai selepas download.")

    return max(candidates, key=lambda path: path.stat().st_size), metadata
