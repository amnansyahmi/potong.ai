import base64
import binascii
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx


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


def _youtube_cookiefile() -> str | None:
    encoded = os.getenv("YOUTUBE_COOKIES_BASE64", "").strip()
    if not encoded:
        return None

    try:
        compact = "".join(encoded.split())
        content = base64.b64decode(compact, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError(
            "YOUTUBE_COOKIES_BASE64 tidak sah. Gunakan fail cookies.txt "
            "format Netscape yang telah dikodkan sebagai Base64."
        ) from exc

    if "youtube.com" not in content.lower() or "\t" not in content:
        raise ValueError(
            "Cookie YouTube tidak dapat dikenal pasti. Export cookies.txt "
            "dalam format Netscape sebelum menukarnya kepada Base64."
        )

    cookie_path = Path(tempfile.gettempdir()) / "potong-ai-youtube-cookies.txt"
    cookie_path.write_text(content, encoding="utf-8")
    cookie_path.chmod(0o600)
    return str(cookie_path)


def _friendly_youtube_error(exc: Exception) -> RuntimeError:
    message = str(exc)
    lowered = message.lower()
    if "confirm you’re not a bot" in lowered or "confirm you're not a bot" in lowered:
        return RuntimeError(
            "YouTube meminta pengesahan akaun untuk sambungan worker ini. "
            "Kemas kini YOUTUBE_COOKIES_BASE64 menggunakan cookies.txt daripada akaun "
            "YouTube khas, kemudian redeploy API. Jangan gunakan akaun Google utama."
        )
    return RuntimeError(message)


def _ydl_options(download: bool, destination: Path | None = None) -> dict[str, Any]:
    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 2,
    }

    cookiefile = _youtube_cookiefile()
    if cookiefile:
        options["cookiefile"] = cookiefile

    proxy_url = os.getenv("YOUTUBE_PROXY_URL", "").strip()
    if proxy_url:
        options["proxy"] = proxy_url

    configured_clients = [
        value.strip()
        for value in os.getenv("YOUTUBE_PLAYER_CLIENTS", "").split(",")
        if value.strip()
    ]
    if configured_clients:
        options["extractor_args"] = {"youtube": {"player_client": configured_clients}}

    if download:
        if destination is None:
            raise ValueError("Destination is required for downloads.")
        options.update({
            # 720p keeps the source comfortably below Vercel's 500 MB /tmp limit
            # while remaining more than sufficient for a 9:16 social crop.
            "format": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
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
    try:
        with YoutubeDL(_ydl_options(download=False)) as ydl:
            info = ydl.extract_info(safe_url, download=False)
    except Exception as exc:
        # YouTube oEmbed is intentionally metadata-only. It lets the UI confirm
        # a valid public video even when the download endpoint challenges the
        # worker's data-centre IP. The actual job still uses authenticated yt-dlp.
        try:
            response = httpx.get(
                "https://www.youtube.com/oembed",
                params={"url": safe_url, "format": "json"},
                timeout=15,
                follow_redirects=True,
            )
            response.raise_for_status()
            embedded = response.json()
            return {
                "url": safe_url,
                "title": str(embedded.get("title") or "Video YouTube")[:240],
                "channel": str(embedded.get("author_name") or "")[:160],
                "thumbnail": str(embedded.get("thumbnail_url") or ""),
                "duration": 0,
                "webpage_url": safe_url,
                "metadata_only": True,
            }
        except Exception:
            raise _friendly_youtube_error(exc) from exc
    if not isinstance(info, dict):
        raise RuntimeError("Metadata video tidak dapat dibaca.")
    return _clean_info(info, safe_url)


def download_youtube(url: str, destination: Path) -> tuple[Path, dict[str, Any]]:
    from yt_dlp import YoutubeDL

    safe_url = validate_youtube_url(url)
    try:
        with YoutubeDL(_ydl_options(download=True, destination=destination)) as ydl:
            info = ydl.extract_info(safe_url, download=True)
    except Exception as exc:
        raise _friendly_youtube_error(exc) from exc

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


def validate_blob_upload_url(value: str) -> str:
    url = value.strip()
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not hostname.endswith(".public.blob.vercel-storage.com")
        or not parsed.path.strip("/")
    ):
        raise ValueError("URL upload Vercel Blob tidak sah.")
    return url


def download_blob_upload(url: str, destination: Path, max_bytes: int) -> Path:
    safe_url = validate_blob_upload_url(url)
    written = 0
    try:
        with httpx.stream("GET", safe_url, timeout=120, follow_redirects=False) as response:
            response.raise_for_status()
            content_length = int(response.headers.get("content-length") or 0)
            if content_length > max_bytes:
                raise ValueError("Video melebihi had upload 500 MB.")
            with destination.open("wb") as output:
                for chunk in response.iter_bytes(1024 * 1024):
                    written += len(chunk)
                    if written > max_bytes:
                        raise ValueError("Video melebihi had upload 500 MB.")
                    output.write(chunk)
    except ValueError:
        destination.unlink(missing_ok=True)
        raise
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"Worker gagal mengambil video daripada Vercel Blob: {exc}") from exc
    return destination
