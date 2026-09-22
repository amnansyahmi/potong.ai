# potong.ai

potong.ai turns a long video into short vertical clips with a free-first local workflow.

## What works

- Paste a YouTube, YouTube Shorts or youtu.be URL
- Inspect the title, channel, thumbnail and duration before processing
- Upload MP4, MOV, WebM or MKV
- Choose TikTok, Instagram Reels or YouTube Shorts as the target
- Choose 1–12 clips, duration, audio language and subtitle treatment
- Transcribe locally with faster-whisper
- Build candidate moments from the transcript
- Optionally ask ai-nonymauz-cloud to rerank and title candidates
- Fall back to local scoring if the AI endpoint is unavailable
- Render 9:16 MP4 clips with FFmpeg
- Burn clean, bold or minimal subtitles into each clip
- Preview and download results from the browser
- Copy a generated social caption for each result
- Download individual MP4/SRT files, the transcript JSON or one ZIP bundle
- Reopen recent jobs stored in the same browser
- Bahasa Melayu Malaysia UI and prompts

## Architecture

```text
Next.js web app
      |
      | upload + polling
      v
FastAPI local worker
  |- yt-dlp (YouTube URL ingestion)
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
MAX_SOURCE_DURATION_SECONDS=14400
YOUTUBE_COOKIES_BASE64=
# Optional writable data path. Vercel automatically uses /tmp/potong-ai.
POTONG_DATA_DIR=
```

`MAX_SOURCE_DURATION_SECONDS` defaults to four hours. URL ingestion only accepts
HTTPS links from known YouTube hosts, disables playlists and limits downloads to
1080p to keep local processing practical.

### YouTube on cloud workers

YouTube may block anonymous requests from data-centre IP addresses such as
Vercel. Uploading a video file is the most reliable option. If URL ingestion is
required, export a Netscape-format `cookies.txt` from a dedicated YouTube
account, Base64-encode the complete file and store the result only as the
`YOUTUBE_COOKIES_BASE64` worker secret. Never commit cookies or expose them as a
`NEXT_PUBLIC_*` variable. Cookies can expire or be rotated, so this remains a
best-effort integration rather than a guaranteed public download service.

## Where to paste a YouTube URL

Open the app and keep **URL YouTube** selected. Paste the link into the large URL
field, choose **Semak video** to verify its metadata, then select the clip settings
and press **Analisis dan potong clip**.

## Deployment

- Deploy the Next.js app to Vercel with `NEXT_PUBLIC_WORKER_URL` pointing to the worker.
- Run the worker on a machine or CPU service with persistent storage, FFmpeg and enough
  RAM for the selected Whisper model.
- Add every deployed web origin to `CORS_ORIGINS`, separated by commas.
- Keep `AI_API_KEY` on the worker only. Never expose it as a `NEXT_PUBLIC_*` variable.

The FastAPI health and metadata routes can run on Vercel. Vercel deployments use
ephemeral `/tmp` storage, so completed jobs and output files are not persistent
across function instances. The full transcription/rendering pipeline still needs
durable object storage and a long-running job runner for reliable public use.

## Current limitation

The renderer currently uses a centered 9:16 crop. Face-aware reframing, multi-speaker
layouts and direct publishing require additional video/social integrations and are
not presented as completed features.

For a fully hosted public SaaS, the video worker needs a reachable CPU/GPU service. Vercel is suitable for the web app, not long FFmpeg/transcription jobs.
