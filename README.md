# potong.ai

potong.ai turns a long video into short vertical clips. It supports a local workflow and a two-project Vercel deployment with Vercel Blob for durable inputs and results.

## What works

- Paste a YouTube, YouTube Shorts or youtu.be URL
- Inspect the title, channel, thumbnail and duration before processing
- Upload MP4, MOV, WebM or MKV up to 500 MB directly to Vercel Blob
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
Browser -> potong.ai (Next.js) -> public Vercel Blob
                              |
                              v
                     potong.ai-api (FastAPI)
                       |- yt-dlp
                       |- faster-whisper
                       |- FFmpeg
                       '- clips/status -> Vercel Blob
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
UPLOAD_ACCESS_KEY=
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
YOUTUBE_PLAYER_CLIENTS=
YOUTUBE_PROXY_URL=
BLOB_READ_WRITE_TOKEN=
# Optional writable data path. Vercel automatically uses /tmp/potong-ai.
POTONG_DATA_DIR=
```

`MAX_SOURCE_DURATION_SECONDS` defaults to four hours. URL ingestion only accepts
HTTPS links from known YouTube hosts, disables playlists and limits downloads to
720p to keep Vercel `/tmp` usage practical.

### YouTube on cloud workers

YouTube may challenge requests from data-centre IP addresses such as Vercel.
Metadata inspection falls back to YouTube oEmbed, but downloading the video still
requires yt-dlp to be accepted by YouTube. Export a Netscape-format `cookies.txt`
from a dedicated YouTube account, Base64-encode the complete file and store the
result only as the `YOUTUBE_COOKIES_BASE64` API secret. Never commit cookies,
reuse a primary Google account, or expose this value as `NEXT_PUBLIC_*`.

`YOUTUBE_PROXY_URL` is an optional standard HTTP/SOCKS proxy setting for a network
you are authorised to use. Cookies and network routes can expire or be challenged;
there is no legitimate code-only switch that can guarantee bypassing YouTube's
anti-bot checks.

## Where to paste a YouTube URL

Open the app and keep **URL YouTube** selected. Paste the link into the large URL
field, choose **Semak video** to verify its metadata, then select the clip settings
and press **Analisis dan potong clip**.

## Deploy both projects on Vercel

Use the same Git repository with two Vercel projects:

1. `potong.ai`: repository root, Next.js framework.
2. `potong.ai-api`: Root Directory `worker`, FastAPI framework.
3. Create one **Public** Vercel Blob store and connect it to both projects. Vercel adds `BLOB_READ_WRITE_TOKEN` automatically.
4. In `potong.ai`, set `NEXT_PUBLIC_WORKER_URL=https://potong-ai-api.vercel.app` and a private `UPLOAD_ACCESS_KEY` value.
5. In `potong.ai-api`, set `CORS_ORIGINS=https://potong-ai.vercel.app`, `WHISPER_MODEL=tiny`, and the YouTube variables above.
6. Redeploy both projects after changing environment variables.

The browser uploads directly to Blob, avoiding Vercel's small Function request-body
limit. The API downloads the Blob into `/tmp`, processes it, then uploads clips,
subtitles, transcript, ZIP and final status back to Blob. `worker/vercel.json` sets
the Hobby-compatible 300-second maximum duration.

`UPLOAD_ACCESS_KEY` is intentionally required on the public site until proper user
authentication/rate limiting is added; it prevents strangers from consuming the
Blob quota. Give this code only to trusted users.

## Current limitation

The renderer currently uses a centered 9:16 crop. Face-aware reframing, multi-speaker
layouts and direct publishing require additional video/social integrations and are
not presented as completed features.

Vercel Hobby still limits a function invocation to 300 seconds and `/tmp` to 500 MB.
Shorter videos can run entirely on Vercel with the `tiny` Whisper model. Long videos
that exceed the time limit still need a queue and long-running CPU/GPU worker; this
cannot be removed by application code.
