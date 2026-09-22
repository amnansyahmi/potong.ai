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
import { createJob, getJob, workerHealth } from "@/lib/api";
import type { JobResult } from "@/lib/types";

const MAX_BROWSER_FILE_BYTES = 8 * 1024 * 1024 * 1024;

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

export function Studio() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [clipCount, setClipCount] = useState(5);
  const [durationPreset, setDurationPreset] = useState("30-60");
  const [language, setLanguage] = useState("auto");
  const [job, setJob] = useState<JobResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [online, setOnline] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  const jobId = job?.id;
  const jobStatus = job?.status;

  async function checkWorker() {
    setOnline(null);
    setOnline(await workerHealth());
  }

  useEffect(() => {
    void checkWorker();
  }, []);

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

  const busy = submitting || jobStatus === "queued" || jobStatus === "processing";
  const statusLabel = useMemo(() => {
    if (submitting) return "Uploading video";
    if (!job) return "Belum mula";
    return job.stage || job.status;
  }, [job, submitting]);

  function acceptFile(next: File | null) {
    if (!next) return;

    if (!next.type.startsWith("video/") && !next.name.toLowerCase().endsWith(".mkv")) {
      setError("Pilih fail video: MP4, MOV, WebM atau MKV.");
      return;
    }

    if (next.size > MAX_BROWSER_FILE_BYTES) {
      setError("Fail melebihi 8 GB. Guna fail yang lebih kecil untuk MVP ini.");
      return;
    }

    setError(null);
    setFile(next);
    setJob(null);
  }

  function onInput(event: ChangeEvent<HTMLInputElement>) {
    acceptFile(event.target.files?.[0] ?? null);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    acceptFile(event.dataTransfer.files?.[0] ?? null);
  }

  function clearFile() {
    setFile(null);
    setJob(null);
    setError(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file || busy) return;

    if (online === false) {
      setError("Worker belum hidup. Start FastAPI worker dulu, kemudian tekan Semak semula.");
      return;
    }

    const [minDuration, maxDuration] = durationPreset.split("-").map(Number);
    const body = new FormData();
    body.append("file", file);
    body.append("clip_count", String(clipCount));
    body.append("min_duration", String(minDuration));
    body.append("max_duration", String(maxDuration));
    body.append("language", language);

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

  return (
    <main className="appShell">
      <header className="topbar">
        <a className="wordmark" href="/" aria-label="potong.ai home">
          <span>potong</span>
          <span className="slash">/</span>
          <span>ai</span>
        </a>

        <div className="workerState" aria-live="polite">
          <span
            className={"workerDot " + (online === true ? "isOnline" : online === false ? "isOffline" : "")}
            aria-hidden="true"
          />
          <span>{online === null ? "Semak worker" : online ? "Local worker hidup" : "Local worker offline"}</span>
          {online === false && (
            <button className="textButton" type="button" onClick={() => void checkWorker()}>
              Semak semula
            </button>
          )}
        </div>
      </header>

      <div className="workspace">
        <section className="workArea" aria-labelledby="studio-title">
          <div className="sectionHeading">
            <p className="sectionIndex">NEW CUT</p>
            <h1 id="studio-title">Potong video panjang jadi clip yang boleh terus semak.</h1>
            <p className="lede">
              Upload satu video. Worker akan transcribe, cari bahagian yang lengkap dan render versi 9:16 siap subtitle.
            </p>
          </div>

          <form onSubmit={submit}>
            <div
              className={"dropzone " + (dragging ? "isDragging" : "") + (file ? " hasFile" : "")}
              onDragOver={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
            >
              <input
                ref={inputRef}
                className="srOnly"
                type="file"
                accept="video/mp4,video/quicktime,video/webm,video/x-matroska,.mkv"
                onChange={onInput}
                id="video-file"
              />

              {!file ? (
                <div className="dropEmpty">
                  <p className="dropTitle">Letak video di sini</p>
                  <p className="dropNote">MP4, MOV, WebM atau MKV. Video kekal pada worker yang anda jalankan.</p>
                  <button
                    className="primaryButton fileButton"
                    type="button"
                    onClick={() => inputRef.current?.click()}
                  >
                    Pilih video
                  </button>
                </div>
              ) : (
                <div className="selectedFile">
                  <div>
                    <p className="fileLabel">VIDEO DIPILIH</p>
                    <p className="fileName">{file.name}</p>
                    <p className="fileMeta">{formatBytes(file.size)}</p>
                  </div>
                  {!busy && (
                    <button className="secondaryButton" type="button" onClick={clearFile}>
                      Tukar video
                    </button>
                  )}
                </div>
              )}
            </div>

            {error && (
              <div className="errorBox" role="alert">
                <strong>Tak dapat teruskan.</strong>
                <span>{error}</span>
              </div>
            )}

            <div className="mobileControls">
              <Controls
                clipCount={clipCount}
                setClipCount={setClipCount}
                durationPreset={durationPreset}
                setDurationPreset={setDurationPreset}
                language={language}
                setLanguage={setLanguage}
                disabled={busy}
              />
            </div>

            <button className="runButton" type="submit" disabled={!file || busy || online === false}>
              {busy ? statusLabel : "Cari dan potong clip"}
            </button>
          </form>

          {job && <JobPanel job={job} onReset={clearFile} />}
        </section>

        <aside className="controlRail" aria-label="Tetapan potongan">
          <Controls
            clipCount={clipCount}
            setClipCount={setClipCount}
            durationPreset={durationPreset}
            setDurationPreset={setDurationPreset}
            language={language}
            setLanguage={setLanguage}
            disabled={busy}
          />

          <div className="railNote">
            <p>RM0 local mode</p>
            <span>Transcription dan rendering dibuat pada komputer sendiri. AI endpoint hanya digunakan jika anda isi URL-nya.</span>
          </div>
        </aside>
      </div>

      <footer className="footer">
        <span>potong.ai MVP</span>
        <a href="https://github.com/amnansyahmi/potong.ai" target="_blank" rel="noreferrer">
          Source
        </a>
      </footer>
    </main>
  );
}

interface ControlsProps {
  clipCount: number;
  setClipCount: (value: number) => void;
  durationPreset: string;
  setDurationPreset: (value: string) => void;
  language: string;
  setLanguage: (value: string) => void;
  disabled: boolean;
}

function Controls({
  clipCount,
  setClipCount,
  durationPreset,
  setDurationPreset,
  language,
  setLanguage,
  disabled,
}: ControlsProps) {
  return (
    <div className="controls">
      <div className="controlsHeading">
        <h2>Tetapan</h2>
        <span>Boleh ubah sebelum mula.</span>
      </div>

      <label className="field">
        <span>Bilangan clip</span>
        <input
          type="number"
          min={1}
          max={12}
          value={clipCount}
          disabled={disabled}
          onChange={(event) => setClipCount(Math.min(12, Math.max(1, Number(event.target.value) || 1)))}
        />
      </label>

      <label className="field">
        <span>Panjang clip</span>
        <select value={durationPreset} disabled={disabled} onChange={(event) => setDurationPreset(event.target.value)}>
          <option value="20-40">20–40 saat</option>
          <option value="30-60">30–60 saat</option>
          <option value="45-90">45–90 saat</option>
        </select>
      </label>

      <label className="field">
        <span>Bahasa audio</span>
        <select value={language} disabled={disabled} onChange={(event) => setLanguage(event.target.value)}>
          <option value="auto">Auto detect</option>
          <option value="ms">Bahasa Melayu</option>
          <option value="en">English</option>
        </select>
      </label>
    </div>
  );
}

function JobPanel({ job, onReset }: { job: JobResult; onReset: () => void }) {
  return (
    <section className="jobPanel" aria-live="polite">
      <div className="jobHeader">
        <div>
          <p className="sectionIndex">JOB {job.id.slice(0, 8).toUpperCase()}</p>
          <h2>{job.status === "completed" ? "Clip dah siap." : job.status === "failed" ? "Job berhenti." : job.stage}</h2>
        </div>
        <span className="progressNumber">{Math.round(job.progress)}%</span>
      </div>

      <div className="progressTrack" aria-label={"Progress " + Math.round(job.progress) + "%"}>
        <span style={{ width: Math.max(2, job.progress) + "%" }} />
      </div>

      {job.status === "failed" && (
        <div className="errorBox" role="alert">
          <strong>Worker return error.</strong>
          <span>{job.error || "Semak terminal worker untuk detail."}</span>
        </div>
      )}

      {job.status === "completed" && (
        <>
          <div className="resultIntro">
            <p>{job.clips.length} clip dipilih daripada transcript.</p>
            <button className="textButton" type="button" onClick={onReset}>
              Potong video lain
            </button>
          </div>

          <div className="clipList">
            {job.clips.map((clip, index) => (
              <article className="clipRow" key={clip.id}>
                <div className="clipNumber">{String(index + 1).padStart(2, "0")}</div>

                <div className="clipCopy">
                  <div className="clipMeta">
                    <span>{formatTime(clip.start)} → {formatTime(clip.end)}</span>
                    <span>score {clip.score}/100</span>
                  </div>
                  <h3>{clip.title}</h3>
                  <p className="clipHook">{clip.hook}</p>
                  <p className="clipReason">{clip.reason}</p>
                </div>

                <div className="clipMedia">
                  <video controls preload="metadata" src={clip.url}>
                    Browser anda tak boleh preview video ini.
                  </video>
                  <a className="downloadButton" href={clip.url} download>
                    Download MP4
                  </a>
                </div>
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
