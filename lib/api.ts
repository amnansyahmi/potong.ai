import type { JobResult } from "@/lib/types";

const WORKER_URL = (process.env.NEXT_PUBLIC_WORKER_URL || "http://localhost:8787").replace(/\/$/, "");

function normalize(job: JobResult): JobResult {
  return {
    ...job,
    clips: job.clips.map((clip) => ({
      ...clip,
      url: clip.url.startsWith("http") ? clip.url : WORKER_URL + clip.url,
    })),
  };
}

export async function createJob(formData: FormData): Promise<JobResult> {
  const response = await fetch(WORKER_URL + "/api/jobs", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || "Upload gagal.");
  }

  return normalize(await response.json());
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
