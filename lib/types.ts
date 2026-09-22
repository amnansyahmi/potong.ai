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
  social_caption: string;
  url: string;
  subtitle_url: string;
}

export interface JobResult {
  id: string;
  status: JobStatus;
  progress: number;
  stage: string;
  filename: string;
  source_type: "youtube" | "upload";
  platform: "tiktok" | "reels" | "shorts";
  transcript_url?: string | null;
  bundle_url?: string | null;
  error?: string | null;
  clips: ClipResult[];
}

export interface SourceInfo {
  url: string;
  title: string;
  channel: string;
  thumbnail: string;
  duration: number;
  webpage_url: string;
}
