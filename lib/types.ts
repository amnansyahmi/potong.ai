export type JobStatus = "queued" | "processing" | "completed" | "failed";

export interface ClipResult {
  id: string;
  title: string;
  hook: string;
  start: number;
  end: number;
  duration: number;
  score: number;
  reason: string;
  url: string;
}

export interface JobResult {
  id: string;
  status: JobStatus;
  progress: number;
  stage: string;
  filename: string;
  error?: string | null;
  clips: ClipResult[];
}
