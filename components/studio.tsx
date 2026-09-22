"use client";

import {
  ChangeEvent,
  DragEvent,
  FormEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { upload } from "@vercel/blob/client";
import { createJob, getJob, getSourceInfo, workerHealth } from "@/lib/api";
import type { JobResult, SourceInfo } from "@/lib/types";

const MAX_BROWSER_FILE_BYTES = 500 * 1024 * 1024;
const YOUTUBE_HOSTS = new Set(["youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"]);

function formatTime(seconds: number) {
  const value = Math.max(0, Math.round(seconds));
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const secs = value % 60;

  if (hours > 0) {
    return [hours, minutes, secs].map((part) => String(part).padStart(2, "0")).join(":");
  }

  return [minutes, secs].map((part) => String(part).padStart(2, "0")).join(":");
}

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return Math.max(1, Math.round(bytes / 1024)) + " KB";
  if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + " MB";
  return (bytes / 1024 / 1024 / 1024).toFixed(2) + " GB";
}

function isYouTubeUrl(value: string) {
  try {
    const url = new URL(value.trim());
    return url.protocol === "https:" && YOUTUBE_HOSTS.has(url.hostname.toLowerCase());
  } catch {
    return false;
  }
}

type SourceMode = "youtube" | "upload";
type RecentJob = Pick<JobResult, "id" | "filename" | "status" | "platform">;

export function Studio() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [sourceMode, setSourceMode] = useState<SourceMode>("youtube");
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [sourceInfo, setSourceInfo] = useState<SourceInfo | null>(null);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [hosted, setHosted] = useState(false);
  const [uploadConfirmed, setUploadConfirmed] = useState(false);
  const [uploadedUrl, setUploadedUrl] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [clipCount, setClipCount] = useState(5);
  const [durationPreset, setDurationPreset] = useState("30-60");
  const [language, setLanguage] = useState("auto");
  const [platform, setPlatform] = useState("tiktok");
  const [captionStyle, setCaptionStyle] = useState("clean");
  const [job, setJob] = useState<JobResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [online, setOnline] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recentJobs, setRecentJobs] = useState<RecentJob[]>([]);

  const jobId = job?.id;
  const jobStatus = job?.status;

  async function checkWorker() {
    setOnline(null);
    setOnline(await workerHealth());
  }

  useEffect(() => {
    setHosted(!["localhost", "127.0.0.1"].includes(window.location.hostname));
    void checkWorker();
    try {
      const saved = window.localStorage.getItem("potong-ai-recent-jobs");
      if (saved) setRecentJobs(JSON.parse(saved));
    } catch {
      // A blocked localStorage should not stop the editor.
    }
  }, []);

  useEffect(() => {
    if (!job) return;
    setRecentJobs((current) => {
      const next = [
        { id: job.id, filename: job.filename, status: job.status, platform: job.platform },
        ...current.filter((item) => item.id !== job.id),
      ].slice(0, 6);
      try {
        window.localStorage.setItem("potong-ai-recent-jobs", JSON.stringify(next));
      } catch {
        // Keep the in-memory history when storage is unavailable.
      }
      return next;
    });
  }, [job?.filename, job?.id, job?.platform, job?.status]);

  useEffect(() => {
    if (!jobId || jobStatus === "completed" || jobStatus === "failed") return;

    const timer = window.setInterval(async () => {
      try {
        setJob(await getJob(jobId));
      } catch {
        // Polling retries on the next interval if the worker briefly drops.
      }
    }, 1800);

    return () => window.clearInterval(timer);
  }, [jobId, jobStatus]);

  const busy = submitting || uploading || jobStatus === "queued" || jobStatus === "processing";
  const sourceReady = sourceMode === "youtube"
    ? isYouTubeUrl(youtubeUrl)
    : Boolean(file && uploadConfirmed);
  const statusLabel = useMemo(() => {
    if (uploading) return `Upload ${Math.round(uploadProgress)}%`;
    if (submitting) return sourceMode === "youtube" ? "Hantar URL ke worker" : "Upload video";
    if (!job) return "Belum mula";
    return job.stage || job.status;
  }, [job, sourceMode, submitting, uploadProgress, uploading]);

  function acceptFile(next: File | null) {
    if (!next) return;

    if (!next.type.startsWith("video/") && !next.name.toLowerCase().endsWith(".mkv")) {
      setError("Pilih fail video: MP4, MOV, WebM atau MKV.");
      return;
    }

    if (next.size > MAX_BROWSER_FILE_BYTES) {
      setError("Fail melebihi 500 MB. Had ini memastikan video muat dalam ruang kerja Vercel.");
      return;
    }

    setError(null);
    setFile(next);
    setUploadConfirmed(false);
    setUploadedUrl(null);
    setUploadProgress(0);
    setJob(null);
  }

  async function finishUpload() {
    if (!file || uploading) return;

    if (!hosted) {
      setUploadConfirmed(true);
      setError(null);
      return;
    }

    const safeName = file.name.replace(/[^a-zA-Z0-9._-]+/g, "-").slice(-120);
    setUploading(true);
    setUploadProgress(0);
    setError(null);

    try {
      const blob = await upload(`inputs/${Date.now()}-${safeName}`, file, {
        access: "public",
        handleUploadUrl: "/api/uploads",
        multipart: file.size > 10 * 1024 * 1024,
        onUploadProgress: ({ percentage }) => setUploadProgress(percentage),
      });
      setUploadedUrl(blob.url);
      setUploadConfirmed(true);
      setUploadProgress(100);
    } catch (reason) {
      setUploadConfirmed(false);
      setUploadedUrl(null);
      const message = reason instanceof Error ? reason.message : "Upload gagal.";
      setError(message.includes("Load failed")
        ? "Sambungan ke Vercel Blob gagal. Pastikan Blob Storage sudah disambungkan kepada project potong.ai."
        : message);
    } finally {
      setUploading(false);
    }
  }

  function onInput(event: ChangeEvent<HTMLInputElement>) {
    acceptFile(event.target.files?.[0] ?? null);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    acceptFile(event.dataTransfer.files?.[0] ?? null);
  }

  function resetWorkspace() {
    setFile(null);
    setUploadConfirmed(false);
    setUploadedUrl(null);
    setUploadProgress(0);
    setYoutubeUrl("");
    setSourceInfo(null);
    setJob(null);
    setError(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  function switchSource(mode: SourceMode) {
    if (busy) return;
    setSourceMode(mode);
    setJob(null);
    setError(null);
  }

  async function inspectSource() {
    if (!isYouTubeUrl(youtubeUrl)) {
      setError("Masukkan URL YouTube yang lengkap, contoh https://youtu.be/...");
      return;
    }
    if (online === false) {
      setError("Worker belum hidup. Start FastAPI worker dahulu untuk baca metadata video.");
      return;
    }

    setSourceLoading(true);
    setError(null);
    try {
      setSourceInfo(await getSourceInfo(youtubeUrl.trim()));
      setOnline(true);
    } catch (reason) {
      setSourceInfo(null);
      setError(reason instanceof Error ? reason.message : "Tak dapat baca video YouTube.");
    } finally {
      setSourceLoading(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!sourceReady || busy) return;

    if (online === false) {
      setError("Worker belum hidup. Start FastAPI worker dulu, kemudian tekan Semak semula.");
      return;
    }

    const [minDuration, maxDuration] = durationPreset.split("-").map(Number);
    const body = new FormData();
    if (sourceMode === "youtube") {
      body.append("source_url", youtubeUrl.trim());
    } else if (uploadedUrl && file) {
      body.append("upload_url", uploadedUrl);
      body.append("upload_filename", file.name);
    } else if (file) {
      body.append("file", file);
    }
    body.append("clip_count", String(clipCount));
    body.append("min_duration", String(minDuration));
    body.append("max_duration", String(maxDuration));
    body.append("language", language);
    body.append("platform", platform);
    body.append("caption_style", captionStyle);

    setSubmitting(true);
    setError(null);

    try {
      const created = await createJob(body);
      setJob(created);
      setOnline(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Tak dapat mula job.");
      await checkWorker();
    } finally {
      setSubmitting(false);
    }
  }

  async function openRecentJob(id: string) {
    if (busy) return;
    setError(null);
    try {
      setJob(await getJob(id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Job lama tak dapat dibuka.");
    }
  }

  return (
    <main className="appShell">
      <header className="topbar">
        <a className="wordmark" href="/" aria-label="potong.ai home">
          <span>potong</span><span className="slash">/</span><span>ai</span>
        </a>

        <div className="workerState" aria-live="polite">
          <span className={"workerDot " + (online === true ? "isOnline" : online === false ? "isOffline" : "")} aria-hidden="true" />
          <span>{online === null ? "Semak worker" : online ? (hosted ? "Worker online" : "Local worker hidup") : (hosted ? "Worker offline" : "Local worker offline")}</span>
          {online === false && (
            <button className="textButton" type="button" onClick={() => void checkWorker()}>Semak semula</button>
          )}
        </div>
      </header>

      <div className="workspace">
        <section className="workArea" aria-labelledby="studio-title">
          <div className="sectionHeading">
            <p className="sectionIndex">NEW CUT</p>
            <h1 id="studio-title">Satu video panjang. Beberapa clip yang layak disimpan.</h1>
            <p className="lede">Tampal URL YouTube atau upload video. Worker akan transcribe, nilai momen dan render versi 9:16 siap subtitle.</p>
          </div>

          <form onSubmit={submit}>
            <div className="sourceTabs" aria-label="Pilih sumber video">
              <button className={sourceMode === "youtube" ? "isActive" : ""} type="button" onClick={() => switchSource("youtube")} disabled={busy}>URL YouTube</button>
              <button className={sourceMode === "upload" ? "isActive" : ""} type="button" onClick={() => switchSource("upload")} disabled={busy}>Upload fail</button>
            </div>

            {sourceMode === "youtube" ? (
              <div className="youtubeSource">
                <label htmlFor="youtube-url">URL YouTube</label>
                <div className="urlRow">
                  <input
                    id="youtube-url"
                    type="url"
                    inputMode="url"
                    placeholder="https://www.youtube.com/watch?v=..."
                    value={youtubeUrl}
                    disabled={busy}
                    onChange={(event) => {
                      setYoutubeUrl(event.target.value);
                      setSourceInfo(null);
                      setJob(null);
                      setError(null);
                    }}
                  />
                  <button className="secondaryButton" type="button" onClick={() => void inspectSource()} disabled={!isYouTubeUrl(youtubeUrl) || sourceLoading || busy}>
                    {sourceLoading ? "Membaca…" : "Semak video"}
                  </button>
                </div>
                <p className="sourceHint">Sokong youtube.com, YouTube Shorts dan youtu.be. Playlist tidak akan diproses.</p>

                {sourceInfo && (
                  <article className="sourcePreview">
                    {sourceInfo.thumbnail && <img src={sourceInfo.thumbnail} alt="" />}
                    <div>
                      <p className="fileLabel">VIDEO DIJUMPAI</p>
                      <h2>{sourceInfo.title}</h2>
                      <p>{sourceInfo.channel || "YouTube"} · {sourceInfo.duration > 0 ? formatTime(sourceInfo.duration) : "durasi disemak semasa proses"}</p>
                    </div>
                  </article>
                )}
              </div>
            ) : (
              <div className={"dropzone " + (dragging ? "isDragging" : "") + (file ? " hasFile" : "")} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={onDrop}>
                <input ref={inputRef} className="srOnly" type="file" accept="video/mp4,video/quicktime,video/webm,video/x-matroska,.mkv" onChange={onInput} id="video-file" />

                {!file ? (
                  <div className="dropEmpty">
                    <p className="dropTitle">Letak video di sini</p>
                    <p className="dropNote">MP4, MOV, WebM atau MKV sehingga 500 MB. Di Vercel, fail dihantar terus ke Blob supaya tidak terkena had request API.</p>
                    <button className="primaryButton fileButton" type="button" onClick={() => inputRef.current?.click()}>Pilih video</button>
                  </div>
                ) : (
                  <div className="selectedFile">
                    <div>
                      <p className="fileLabel">{uploadConfirmed ? "PILIHAN DISAHKAN · UPLOAD SELESAI" : uploading ? `SEDANG UPLOAD ${Math.round(uploadProgress)}%` : "VIDEO DIPILIH · BELUM DISAHKAN"}</p>
                      <p className="fileName">{file.name}</p>
                      <p className="fileMeta">{formatBytes(file.size)}</p>
                      {!uploadConfirmed && !uploading && <p className="sourceHint">Tekan “Selesai pilih video” untuk sahkan pilihan dan mula upload.</p>}
                      {uploading && <div className="uploadTrack" aria-label={`Upload ${Math.round(uploadProgress)}%`}><span style={{ width: `${uploadProgress}%` }} /></div>}
                    </div>
                    <div className="fileActions">
                      {!uploadConfirmed && <button className="primaryButton" type="button" onClick={() => void finishUpload()} disabled={uploading}>{uploading ? "Mengupload…" : "Selesai pilih video"}</button>}
                      {!busy && <button className="secondaryButton" type="button" onClick={() => { setFile(null); setUploadConfirmed(false); setUploadedUrl(null); setUploadProgress(0); setJob(null); if (inputRef.current) inputRef.current.value = ""; }}>Tukar video</button>}
                    </div>
                  </div>
                )}
              </div>
            )}

            {error && <div className="errorBox" role="alert"><strong>Tak dapat teruskan.</strong><span>{error}</span></div>}

            <div className="mobileControls">
              <Controls clipCount={clipCount} setClipCount={setClipCount} durationPreset={durationPreset} setDurationPreset={setDurationPreset} language={language} setLanguage={setLanguage} platform={platform} setPlatform={setPlatform} captionStyle={captionStyle} setCaptionStyle={setCaptionStyle} disabled={busy} />
            </div>

            <button className="runButton" type="submit" disabled={!sourceReady || busy || online === false}>
              {busy ? statusLabel : "Analisis dan potong clip"}
            </button>
          </form>

          {job && <JobPanel job={job} onReset={resetWorkspace} />}
          <div className="mobileRecent">
            <RecentJobs jobs={recentJobs} currentId={job?.id} disabled={busy} onOpen={openRecentJob} />
          </div>
        </section>

        <aside className="controlRail" aria-label="Tetapan potongan">
          <Controls clipCount={clipCount} setClipCount={setClipCount} durationPreset={durationPreset} setDurationPreset={setDurationPreset} language={language} setLanguage={setLanguage} platform={platform} setPlatform={setPlatform} captionStyle={captionStyle} setCaptionStyle={setCaptionStyle} disabled={busy} />
          <div className="railNote"><p>{hosted ? "Vercel hosted mode" : "RM0 local mode"}</p><span>{hosted ? "Upload dan hasil disimpan dalam Vercel Blob. Proses video berjalan pada API worker." : "Download, transcription dan rendering dibuat pada worker sendiri. AI endpoint kekal optional."}</span></div>
          <RecentJobs jobs={recentJobs} currentId={job?.id} disabled={busy} onOpen={openRecentJob} />
        </aside>
      </div>

      <footer className="footer"><span>potong.ai · video clipping desk</span><a href="https://github.com/amnansyahmi/potong.ai" target="_blank" rel="noreferrer">Source</a></footer>
    </main>
  );
}

function RecentJobs({ jobs, currentId, disabled, onOpen }: { jobs: RecentJob[]; currentId?: string; disabled: boolean; onOpen: (id: string) => Promise<void> }) {
  if (jobs.length === 0) return null;

  return (
    <section className="recentJobs" aria-labelledby="recent-jobs-title">
      <div className="recentHeading"><h2 id="recent-jobs-title">Job terbaru</h2><span>Disimpan pada browser ini.</span></div>
      <ul>
        {jobs.map((item) => (
          <li key={item.id}>
            <button type="button" onClick={() => void onOpen(item.id)} disabled={disabled || item.id === currentId}>
              <span>{item.filename}</span>
              <small>{item.status === "completed" ? "Siap" : item.status === "failed" ? "Gagal" : "Sedang proses"}</small>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

interface ControlsProps {
  clipCount: number;
  setClipCount: (value: number) => void;
  durationPreset: string;
  setDurationPreset: (value: string) => void;
  language: string;
  setLanguage: (value: string) => void;
  platform: string;
  setPlatform: (value: string) => void;
  captionStyle: string;
  setCaptionStyle: (value: string) => void;
  disabled: boolean;
}

function Controls({ clipCount, setClipCount, durationPreset, setDurationPreset, language, setLanguage, platform, setPlatform, captionStyle, setCaptionStyle, disabled }: ControlsProps) {
  return (
    <div className="controls">
      <div className="controlsHeading"><h2>Tetapan</h2><span>Boleh ubah sebelum mula.</span></div>

      <label className="field"><span>Platform</span><select value={platform} disabled={disabled} onChange={(event) => setPlatform(event.target.value)}><option value="tiktok">TikTok</option><option value="reels">Instagram Reels</option><option value="shorts">YouTube Shorts</option></select></label>
      <label className="field"><span>Bilangan clip</span><input type="number" min={1} max={12} value={clipCount} disabled={disabled} onChange={(event) => setClipCount(Math.min(12, Math.max(1, Number(event.target.value) || 1)))} /></label>
      <label className="field"><span>Panjang clip</span><select value={durationPreset} disabled={disabled} onChange={(event) => setDurationPreset(event.target.value)}><option value="15-30">15–30 saat</option><option value="20-40">20–40 saat</option><option value="30-60">30–60 saat</option><option value="45-90">45–90 saat</option></select></label>
      <label className="field"><span>Bahasa audio</span><select value={language} disabled={disabled} onChange={(event) => setLanguage(event.target.value)}><option value="auto">Auto detect</option><option value="ms">Bahasa Melayu</option><option value="en">English</option></select></label>
      <label className="field"><span>Gaya subtitle</span><select value={captionStyle} disabled={disabled} onChange={(event) => setCaptionStyle(event.target.value)}><option value="clean">Clean</option><option value="bold">Bold kuning</option><option value="minimal">Minimal box</option></select></label>
    </div>
  );
}

const PIPELINE_STEPS = [
  { label: "Sumber", at: 5 },
  { label: "Transcribe", at: 18 },
  { label: "Pilih momen", at: 46 },
  { label: "Render", at: 54 },
  { label: "Siap", at: 100 },
];

function JobPanel({ job, onReset }: { job: JobResult; onReset: () => void }) {
  const [copied, setCopied] = useState<string | null>(null);

  async function copyCaption(id: string, caption: string) {
    await navigator.clipboard.writeText(caption);
    setCopied(id);
    window.setTimeout(() => setCopied((current) => current === id ? null : current), 1800);
  }

  return (
    <section className="jobPanel" aria-live="polite">
      <div className="jobHeader">
        <div><p className="sectionIndex">JOB {job.id.slice(0, 8).toUpperCase()}</p><h2>{job.status === "completed" ? "Clip dah siap." : job.status === "failed" ? "Job berhenti." : job.stage}</h2><p className="jobSource">{job.filename}</p></div>
        <span className="progressNumber">{Math.round(job.progress)}%</span>
      </div>

      <div className="progressTrack" aria-label={"Progress " + Math.round(job.progress) + "%"}><span style={{ width: Math.max(2, job.progress) + "%" }} /></div>
      <ol className="pipelineSteps">{PIPELINE_STEPS.map((step) => <li className={job.progress >= step.at ? "isDone" : ""} key={step.label}>{step.label}</li>)}</ol>

      {job.status === "failed" && <div className="errorBox" role="alert"><strong>Worker melaporkan ralat.</strong><span>{job.error || "Semak terminal worker untuk butiran lanjut."}</span></div>}

      {job.status === "completed" && (
        <>
          <div className="resultIntro"><p>{job.clips.length} clip dipilih untuk {job.platform === "reels" ? "Instagram Reels" : job.platform === "shorts" ? "YouTube Shorts" : "TikTok"}.</p><button className="textButton" type="button" onClick={onReset}>Potong video lain</button></div>
          <div className="resultDownloads">
            {job.bundle_url && <a className="primaryButton" href={job.bundle_url} download>Download semua (.zip)</a>}
            {job.transcript_url && <a className="secondaryButton" href={job.transcript_url} download>Transcript JSON</a>}
          </div>

          <div className="clipList">
            {job.clips.map((clip, index) => (
              <article className="clipRow" key={clip.id}>
                <div className="clipNumber">{String(index + 1).padStart(2, "0")}</div>
                <div className="clipCopy">
                  <div className="clipMeta"><span>{formatTime(clip.start)} → {formatTime(clip.end)}</span><span>{Math.round(clip.duration)} saat</span><span className="scoreTag">clip score {clip.score}/100</span></div>
                  <h3>{clip.title}</h3>
                  <p className="clipHook">{clip.hook}</p>
                  <p className="clipReason">{clip.reason}</p>
                  <div className="captionBox"><p>{clip.social_caption}</p><button type="button" onClick={() => void copyCaption(clip.id, clip.social_caption)}>{copied === clip.id ? "Dah salin" : "Salin caption"}</button></div>
                </div>
                <div className="clipMedia">
                  <video controls preload="metadata" src={clip.url}>Browser anda tak boleh preview video ini.</video>
                  <div className="downloadGroup"><a className="downloadButton" href={clip.url} download>Download MP4</a><a className="downloadButton" href={clip.subtitle_url} download>Download SRT</a></div>
                </div>
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
