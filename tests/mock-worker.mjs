import http from "node:http";

const jobs = new Map();

function cors(res) {
  res.setHeader("Access-Control-Allow-Origin", "http://127.0.0.1:3000");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
}

function json(res, status, body) {
  cors(res);
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

const server = http.createServer((req, res) => {
  if (req.method === "OPTIONS") {
    cors(res);
    res.writeHead(204);
    res.end();
    return;
  }

  if (req.method === "GET" && req.url === "/health") {
    json(res, 200, { status: "ok" });
    return;
  }

  if (req.method === "POST" && req.url === "/api/jobs") {
    req.resume();
    req.on("end", () => {
      const job = {
        id: "demo1234",
        status: "queued",
        progress: 2,
        stage: "Dalam queue",
        filename: "demo.mp4",
        error: null,
        clips: [],
        polls: 0,
      };
      jobs.set(job.id, job);
      const { polls, ...publicJob } = job;
      json(res, 200, publicJob);
    });
    return;
  }

  if (req.method === "GET" && req.url === "/api/jobs/demo1234") {
    const job = jobs.get("demo1234");
    if (!job) {
      json(res, 404, { detail: "Job not found" });
      return;
    }

    job.polls += 1;
    if (job.polls >= 1) {
      Object.assign(job, {
        status: "completed",
        progress: 100,
        stage: "Siap",
        clips: [
          {
            id: "clip-01",
            title: "Ramai silap dekat bahagian ini",
            hook: "Ramai sebenarnya buat benda ini tanpa sedar.",
            start: 12,
            end: 48,
            duration: 36,
            score: 88,
            reason: "Bahagian ini cukup lengkap untuk berdiri sendiri.",
            url: "/outputs/demo1234/clip-01.mp4",
          },
        ],
      });
    }

    const { polls, ...publicJob } = job;
    json(res, 200, publicJob);
    return;
  }

  if (req.method === "GET" && req.url === "/outputs/demo1234/clip-01.mp4") {
    cors(res);
    res.writeHead(200, { "Content-Type": "video/mp4", "Content-Length": "0" });
    res.end();
    return;
  }

  json(res, 404, { detail: "Not found" });
});

server.listen(8787, "127.0.0.1");
