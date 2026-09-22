# potong.ai

potong.ai turns a long video into short vertical clips with a free-first local workflow.

## What works in this MVP

- Upload MP4, MOV, WebM or MKV
- Transcribe locally with faster-whisper
- Build candidate moments from the transcript
- Optionally ask ai-nonymauz-cloud to rerank and title candidates
- Fall back to local scoring if the AI endpoint is unavailable
- Render 9:16 MP4 clips with FFmpeg
- Burn subtitles into each clip
- Preview and download results from the browser
- Bahasa Melayu Malaysia UI and prompts

## Architecture

```text
Next.js web app
      |
      | upload + polling
      v
FastAPI local worker
  |- faster-whisper
  |- ai-nonymauz-cloud (optional)
  |- FFmpeg
  '- local job/output storage
```

The RM0 path keeps the expensive work on your own computer. No paid transcription or video API is required.

## Run locally

### 1. Web app

```bash
npm install
cp .env.example .env.local
npm run dev
```

Open http://localhost:3000.

### 2. Video worker

Install FFmpeg first, then:

```bash
cd worker
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8787
```

The first transcription can take longer because faster-whisper downloads the selected model.

Or run the worker with Docker:

```bash
docker compose up --build worker
```

Health check: http://localhost:8787/health

## ai-nonymauz-cloud

Set `AI_BASE_URL` in `worker/.env` to your OpenAI-compatible endpoint.

```env
AI_BASE_URL=https://your-endpoint.example/v1
AI_MODEL=auto
AI_API_KEY=
```

If the endpoint is blank, times out or returns invalid JSON, the job continues with local clip scoring.

## Environment

Web:

```env
NEXT_PUBLIC_WORKER_URL=http://localhost:8787
```

Worker:

```env
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
AI_BASE_URL=
AI_MODEL=auto
AI_API_KEY=
CORS_ORIGINS=http://localhost:3000
```

## Current limitation

The first renderer uses a centered 9:16 crop. Face-aware reframing is the next rendering milestone.

For a fully hosted public SaaS, the video worker needs a reachable CPU/GPU service. Vercel is suitable for the web app, not long FFmpeg/transcription jobs.
