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
            _model = WhisperModel(
                os.getenv("WHISPER_MODEL", "small"),
                device=os.getenv("WHISPER_DEVICE", "cpu"),
                compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
            )
    return _model


def transcribe_video(path: Path, language: str = "auto") -> tuple[list[dict[str, Any]], str]:
    model = _get_model()
    requested_language = None if language == "auto" else language
    segments, info = model.transcribe(
        str(path), language=requested_language, beam_size=5, vad_filter=True, word_timestamps=False
    )
    items: list[dict[str, Any]] = []
    for segment in segments:
        text = segment.text.strip()
        if text:
            items.append({"start": round(float(segment.start), 3), "end": round(float(segment.end), 3), "text": text})
    detected = getattr(info, "language", None) or requested_language or "unknown"
    return items, detected
