import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .clips import choose_clips
from .render import render_clip, write_srt
from .transcribe import transcribe_video

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
JOBS_DIR = DATA_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024 * 1024

app = FastAPI(title="potong.ai worker", version="0.1.0")

origins = [
    item.strip()
    for item in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if item.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.mount("/outputs", StaticFiles(directory=str(JOBS_DIR)), name="outputs")


def _job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id


def _status_path(job_id: str) -> Path:
    return _job_dir(job_id) / "status.json"


def _read_job(job_id: str) -> dict[str, Any]:
    path = _status_path(job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Job not found.")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_job(job_id: str, **changes: Any) -> dict[str, Any]:
    path = _status_path(job_id)
    current: dict[str, Any] = {}
    if path.exists():
        current = json.loads(path.read_text(encoding="utf-8"))

    current.update(changes)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    return current


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": job["id"],
        "status": job["status"],
        "progress": job.get("progress", 0),
        "stage": job.get("stage", ""),
        "filename": job.get("filename", ""),
        "error": job.get("error"),
        "clips": job.get("clips", []),
    }


def _process_job(
    job_id: str,
    source: Path,
    clip_count: int,
    min_duration: int,
    max_duration: int,
    language: str,
) -> None:
    try:
        _write_job(job_id, status="processing", progress=8, stage="Transcribe audio")
        segments, detected_language = transcribe_video(source, language)

        if not segments:
            raise RuntimeError("Tiada dialog dapat dikesan dalam video.")

        transcript_path = _job_dir(job_id) / "transcript.json"
        transcript_path.write_text(
            json.dumps({"language": detected_language, "segments": segments}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        _write_job(job_id, progress=44, stage="Cari moment yang lengkap")
        picks = choose_clips(
            segments=segments,
            clip_count=clip_count,
            min_duration=min_duration,
            max_duration=max_duration,
            language=detected_language,
        )

        if not picks:
            raise RuntimeError("Tak jumpa segment yang cukup panjang untuk dijadikan clip.")

        clips: list[dict[str, Any]] = []
        total = len(picks)

        for index, pick in enumerate(picks, start=1):
            _write_job(
                job_id,
                progress=50 + int(((index - 1) / total) * 44),
                stage=f"Render clip {index}/{total}",
            )

            clip_id = f"clip-{index:02}"
            output = _job_dir(job_id) / f"{clip_id}.mp4"
            subtitle = _job_dir(job_id) / f"{clip_id}.srt"

            write_srt(segments, float(pick["start"]), float(pick["end"]), subtitle)
            render_clip(source, output, subtitle, float(pick["start"]), float(pick["end"]))

            clips.append({
                "id": clip_id,
                "title": pick["title"],
                "hook": pick["hook"],
                "start": pick["start"],
                "end": pick["end"],
                "duration": pick["duration"],
                "score": pick["score"],
                "reason": pick["reason"],
                "url": f"/outputs/{job_id}/{output.name}",
            })

        _write_job(
            job_id,
            status="completed",
            progress=100,
            stage="Siap",
            clips=clips,
            error=None,
        )
    except Exception as exc:
        _write_job(job_id, status="failed", stage="Gagal", error=str(exc))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/jobs")
def create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    clip_count: int = Form(5),
    min_duration: int = Form(30),
    max_duration: int = Form(60),
    language: str = Form("auto"),
) -> dict[str, Any]:
    extension = Path(file.filename or "").suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported video format.")
    if clip_count < 1 or clip_count > 12:
        raise HTTPException(status_code=400, detail="clip_count must be between 1 and 12.")
    if min_duration < 10 or max_duration > 120 or min_duration >= max_duration:
        raise HTTPException(status_code=400, detail="Invalid clip duration range.")
    if language not in {"auto", "ms", "en"}:
        raise HTTPException(status_code=400, detail="Unsupported language option.")

    job_id = uuid.uuid4().hex
    folder = _job_dir(job_id)
    folder.mkdir(parents=True, exist_ok=False)

    source = folder / ("source" + extension)
    written = 0

    with source.open("wb") as destination:
        while chunk := file.file.read(1024 * 1024):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                destination.close()
                shutil.rmtree(folder, ignore_errors=True)
                raise HTTPException(status_code=413, detail="Video exceeds the 8 GB MVP limit.")
            destination.write(chunk)

    job = _write_job(
        job_id,
        id=job_id,
        status="queued",
        progress=2,
        stage="Dalam queue",
        filename=file.filename or source.name,
        error=None,
        clips=[],
    )

    background_tasks.add_task(
        _process_job,
        job_id,
        source,
        clip_count,
        min_duration,
        max_duration,
        language,
    )

    return _public_job(job)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    return _public_job(_read_job(job_id))
