import json
import os
import re
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .clips import choose_clips
from .blob_storage import blob_enabled, put_file, put_json, read_json
from .render import render_clip, write_srt
from .sources import (
    download_blob_upload,
    download_youtube,
    inspect_youtube,
    validate_blob_upload_url,
    validate_youtube_url,
)
from .transcribe import transcribe_video

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]


def _data_dir() -> Path:
    configured = os.getenv("POTONG_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()

    # Vercel's deployed application filesystem is read-only. Its writable
    # scratch space lives under /tmp and is intentionally ephemeral.
    if os.getenv("VERCEL"):
        return Path("/tmp/potong-ai")

    return ROOT / "data"


DATA_DIR = _data_dir()
JOBS_DIR = DATA_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024

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
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(status_code=404, detail="Job not found.")
    path = _status_path(job_id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        stored = read_json(f"jobs/{job_id}/status.json")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Status job tidak dapat dibaca: {exc}") from exc
    if stored is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return stored


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
        "source_type": job.get("source_type", "upload"),
        "platform": job.get("platform", "tiktok"),
        "transcript_url": job.get("transcript_url"),
        "bundle_url": job.get("bundle_url"),
        "error": job.get("error"),
        "clips": job.get("clips", []),
    }


def _persist_job(job_id: str) -> None:
    if not blob_enabled():
        return
    job = json.loads(_status_path(job_id).read_text(encoding="utf-8"))
    put_json(f"jobs/{job_id}/status.json", job)


def _process_job(
    job_id: str,
    source: Path | None,
    source_url: str,
    upload_url: str,
    upload_filename: str,
    clip_count: int,
    min_duration: int,
    max_duration: int,
    language: str,
    platform: str,
    caption_style: str,
) -> None:
    try:
        if source_url:
            _write_job(job_id, status="processing", progress=5, stage="Download video YouTube")
            source, metadata = download_youtube(source_url, _job_dir(job_id))
            _write_job(job_id, filename=metadata["title"], source_metadata=metadata)

        if upload_url:
            _write_job(job_id, status="processing", progress=8, stage="Ambil video upload")
            extension = Path(upload_filename).suffix.lower()
            source = download_blob_upload(
                upload_url,
                _job_dir(job_id) / ("source" + extension),
                MAX_UPLOAD_BYTES,
            )

        if source is None:
            raise RuntimeError("Sumber video tidak dijumpai.")

        _write_job(job_id, status="processing", progress=18, stage="Transcribe audio")
        segments, detected_language = transcribe_video(source, language)

        if not segments:
            raise RuntimeError("Tiada dialog dapat dikesan dalam video.")

        transcript_path = _job_dir(job_id) / "transcript.json"
        transcript_path.write_text(
            json.dumps({"language": detected_language, "segments": segments}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        _write_job(job_id, progress=46, stage="Nilai momen terbaik")
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
                progress=54 + int(((index - 1) / total) * 42),
                stage=f"Render clip {index}/{total}",
            )

            clip_id = f"clip-{index:02}"
            output = _job_dir(job_id) / f"{clip_id}.mp4"
            subtitle = _job_dir(job_id) / f"{clip_id}.srt"

            write_srt(segments, float(pick["start"]), float(pick["end"]), subtitle)
            render_clip(
                source,
                output,
                subtitle,
                float(pick["start"]),
                float(pick["end"]),
                caption_style,
            )

            clips.append({
                "id": clip_id,
                "title": pick["title"],
                "hook": pick["hook"],
                "start": pick["start"],
                "end": pick["end"],
                "duration": pick["duration"],
                "score": pick["score"],
                "reason": pick["reason"],
                "social_caption": pick["social_caption"],
                "url": f"/outputs/{job_id}/{output.name}",
                "subtitle_url": f"/outputs/{job_id}/{subtitle.name}",
            })

        bundle = _job_dir(job_id) / "potong-ai-clips.zip"
        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(transcript_path, "transcript.json")
            for clip in clips:
                archive.write(_job_dir(job_id) / Path(clip["url"]).name, Path(clip["url"]).name)
                archive.write(
                    _job_dir(job_id) / Path(clip["subtitle_url"]).name,
                    Path(clip["subtitle_url"]).name,
                )

        transcript_url = f"/outputs/{job_id}/{transcript_path.name}"
        bundle_url = f"/outputs/{job_id}/{bundle.name}"
        if blob_enabled():
            transcript_url = put_file(
                f"jobs/{job_id}/{transcript_path.name}", transcript_path, "application/json"
            )
            bundle_url = put_file(
                f"jobs/{job_id}/{bundle.name}", bundle, "application/zip"
            )
            for clip in clips:
                clip_name = Path(clip["url"]).name
                subtitle_name = Path(clip["subtitle_url"]).name
                clip["url"] = put_file(
                    f"jobs/{job_id}/{clip_name}", _job_dir(job_id) / clip_name, "video/mp4"
                )
                clip["subtitle_url"] = put_file(
                    f"jobs/{job_id}/{subtitle_name}",
                    _job_dir(job_id) / subtitle_name,
                    "application/x-subrip",
                )

        _write_job(
            job_id,
            status="completed",
            progress=100,
            stage="Siap",
            clips=clips,
            transcript_url=transcript_url,
            bundle_url=bundle_url,
            error=None,
        )
        _persist_job(job_id)
    except Exception as exc:
        _write_job(job_id, status="failed", stage="Gagal", error=str(exc))
        try:
            _persist_job(job_id)
        except Exception:
            # Keep the original pipeline error visible to the caller.
            pass


@app.get("/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "runtime": "vercel" if os.getenv("VERCEL") else "local",
        "blob": blob_enabled(),
    }


@app.get("/api/source-info")
def source_info(url: str) -> dict[str, Any]:
    try:
        return inspect_youtube(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Tak dapat baca video YouTube: {exc}") from exc


@app.post("/api/jobs")
def create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile | None = File(None),
    source_url: str = Form(""),
    upload_url: str = Form(""),
    upload_filename: str = Form(""),
    clip_count: int = Form(5),
    min_duration: int = Form(30),
    max_duration: int = Form(60),
    language: str = Form("auto"),
    platform: str = Form("tiktok"),
    caption_style: str = Form("clean"),
) -> dict[str, Any]:
    source_url = source_url.strip()
    upload_url = upload_url.strip()
    source_count = sum((bool(file), bool(source_url), bool(upload_url)))
    if source_count == 0:
        raise HTTPException(status_code=400, detail="Pilih fail video atau masukkan URL YouTube.")
    if source_count > 1:
        raise HTTPException(status_code=400, detail="Hantar satu sumber video sahaja.")

    extension = Path((file.filename if file else upload_filename) or "").suffix.lower()

    if (file or upload_url) and extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported video format.")
    if source_url:
        try:
            source_url = validate_youtube_url(source_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if upload_url:
        try:
            upload_url = validate_blob_upload_url(upload_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if clip_count < 1 or clip_count > 12:
        raise HTTPException(status_code=400, detail="clip_count must be between 1 and 12.")
    if min_duration < 10 or max_duration > 120 or min_duration >= max_duration:
        raise HTTPException(status_code=400, detail="Invalid clip duration range.")
    if language not in {"auto", "ms", "en"}:
        raise HTTPException(status_code=400, detail="Unsupported language option.")
    if platform not in {"tiktok", "reels", "shorts"}:
        raise HTTPException(status_code=400, detail="Unsupported platform option.")
    if caption_style not in {"clean", "bold", "minimal"}:
        raise HTTPException(status_code=400, detail="Unsupported caption style.")

    job_id = uuid.uuid4().hex
    folder = _job_dir(job_id)
    folder.mkdir(parents=True, exist_ok=False)

    source: Path | None = None
    if file:
        source = folder / ("source" + extension)
        written = 0

        with source.open("wb") as destination:
            while chunk := file.file.read(1024 * 1024):
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    destination.close()
                    shutil.rmtree(folder, ignore_errors=True)
                    raise HTTPException(status_code=413, detail="Video melebihi had 500 MB.")
                destination.write(chunk)

    job = _write_job(
        job_id,
        id=job_id,
        status="queued",
        progress=2,
        stage="Dalam queue",
        filename=(file.filename if file else upload_filename or source_url) or "Video YouTube",
        source_type="youtube" if source_url else "upload",
        platform=platform,
        error=None,
        clips=[],
    )

    task_args = (
        job_id,
        source,
        source_url,
        upload_url,
        upload_filename,
        clip_count,
        min_duration,
        max_duration,
        language,
        platform,
        caption_style,
    )

    if os.getenv("VERCEL"):
        if not blob_enabled():
            shutil.rmtree(folder, ignore_errors=True)
            raise HTTPException(
                status_code=503,
                detail="Sambungkan satu public Vercel Blob store kepada project API dahulu.",
            )
        _process_job(*task_args)
        return _public_job(_read_job(job_id))

    background_tasks.add_task(_process_job, *task_args)
    return _public_job(job)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    return _public_job(_read_job(job_id))
