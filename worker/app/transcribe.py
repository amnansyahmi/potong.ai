import os
from pathlib import Path
from threading import Lock
from typing import Any

_model = None
_model_lock = Lock()


def _configure_writable_runtime() -> Path | None:
    """Point model and cache writers at Vercel's writable scratch space."""
    if not os.getenv("VERCEL"):
        return None

    cache_root = Path(os.getenv("POTONG_CACHE_DIR", "/tmp/potong-ai-cache"))
    paths = {
        "XDG_CACHE_HOME": cache_root,
        "HF_HOME": cache_root / "huggingface",
        "HF_HUB_CACHE": cache_root / "huggingface" / "hub",
        "HF_ASSETS_CACHE": cache_root / "huggingface" / "assets",
        "HF_XET_CACHE": cache_root / "huggingface" / "xet",
    }
    for key, path in paths.items():
        path.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(path)

    os.environ["HF_HUB_DISABLE_XET"] = "1"
    return cache_root


# huggingface_hub reads cache variables when it is imported. Configure them
# before the deferred faster-whisper import in _get_model.
_CACHE_ROOT = _configure_writable_runtime()


def _get_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel
            default_model = "tiny" if os.getenv("VERCEL") else "small"
            download_root = os.getenv("WHISPER_DOWNLOAD_ROOT", "").strip()
            if not download_root and _CACHE_ROOT is not None:
                download_root = str(_CACHE_ROOT / "whisper-models")
            if download_root:
                Path(download_root).mkdir(parents=True, exist_ok=True)
            _model = WhisperModel(
                os.getenv("WHISPER_MODEL", default_model),
                device=os.getenv("WHISPER_DEVICE", "cpu"),
                compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
                download_root=download_root or None,
            )
    return _model


def transcribe_video(path: Path, language: str = "auto") -> tuple[list[dict[str, Any]], str]:
    model = _get_model()
    requested_language = None if language == "auto" else language
    beam_size = 1 if os.getenv("VERCEL") else 5
    segments, info = model.transcribe(
        str(path), language=requested_language, beam_size=beam_size, vad_filter=True, word_timestamps=False
    )
    items: list[dict[str, Any]] = []
    for segment in segments:
        text = segment.text.strip()
        if text:
            items.append({"start": round(float(segment.start), 3), "end": round(float(segment.end), 3), "text": text})
    detected = getattr(info, "language", None) or requested_language or "unknown"
    return items, detected
