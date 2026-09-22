import os
from pathlib import Path
from threading import Lock
from typing import Any

_model = None
_model_lock = Lock()


def _get_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel
            default_model = "tiny" if os.getenv("VERCEL") else "small"
            _model = WhisperModel(
                os.getenv("WHISPER_MODEL", default_model),
                device=os.getenv("WHISPER_DEVICE", "cpu"),
                compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
                download_root="/tmp/whisper-cache" if os.getenv("VERCEL") else None,
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
