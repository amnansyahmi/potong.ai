import type { JobResult, SourceInfo } from "@/lib/types";

const WORKER_URL = (process.env.NEXT_PUBLIC_WORKER_URL || "http://localhost:8787").replace(/\/$/, "");

function normalize(job: JobResult): JobResult {
  return {
    ...job,
    transcript_url: job.transcript_url
      ? job.transcript_url.startsWith("http") ? job.transcript_url : WORKER_URL + job.transcript_url
      : null,
    bundle_url: job.bundle_url
      ? job.bundle_url.startsWith("http") ? job.bundle_url : WORKER_URL + job.bundle_url
      : null,
    clips: job.clips.map((clip) => ({
      ...clip,
      url: clip.url.startsWith("http") ? clip.url : WORKER_URL + clip.url,
      subtitle_url: clip.subtitle_url.startsWith("http") ? clip.subtitle_url : WORKER_URL + clip.subtitle_url,
    })),
  };
}

async function errorMessage(response: Response, fallback: string) {
  try {
    const body = await response.json();
    return typeof body.detail === "string" ? body.detail : fallback;
  } catch {
    return fallback;
  }
}

export async function createJob(formData: FormData): Promise<JobResult> {
  const response = await fetch(WORKER_URL + "/api/jobs", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await errorMessage(response, "Tak dapat mula proses video."));
  }

  return normalize(await response.json());
}

export async function getSourceInfo(url: string): Promise<SourceInfo> {
  const response = await fetch(WORKER_URL + "/api/source-info?url=" + encodeURIComponent(url), {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(await errorMessage(response, "Tak dapat baca URL YouTube."));
  }

  return response.json();
}

export async function getJob(jobId: string): Promise<JobResult> {
  const response = await fetch(WORKER_URL + "/api/jobs/" + jobId, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("Tak dapat baca status job.");
  }

  return normalize(await response.json());
}

export async function workerHealth(): Promise<boolean> {
  try {
    const response = await fetch(WORKER_URL + "/health", { cache: "no-store" });
    return response.ok;
  } catch {
    return false;
  }
}
