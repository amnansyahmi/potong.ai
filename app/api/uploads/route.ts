import { handleUpload, type HandleUploadBody } from "@vercel/blob/client";

const MAX_UPLOAD_BYTES = 500 * 1024 * 1024;

export async function POST(request: Request): Promise<Response> {
  const requestOrigin = request.headers.get("origin");
  const ownOrigin = new URL(request.url).origin;

  if (requestOrigin && requestOrigin !== ownOrigin) {
    return Response.json({ error: "Origin upload tidak dibenarkan." }, { status: 403 });
  }

  let body: HandleUploadBody;
  try {
    body = (await request.json()) as HandleUploadBody;
  } catch {
    return Response.json({ error: "Permintaan upload tidak sah." }, { status: 400 });
  }

  try {
    const result = await handleUpload({
      body,
      request,
      onBeforeGenerateToken: async () => {
        return {
          allowedContentTypes: [
            "video/mp4",
            "video/quicktime",
            "video/webm",
            "video/x-matroska",
            "application/octet-stream",
          ],
          maximumSizeInBytes: MAX_UPLOAD_BYTES,
          addRandomSuffix: true,
          tokenPayload: JSON.stringify({ source: "potong-ai-web" }),
        };
      },
      onUploadCompleted: async () => {
        // The worker receives the returned Blob URL when the user starts a job.
      },
    });

    return Response.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Upload gagal.";
    return Response.json({ error: message }, { status: 400 });
  }
}
