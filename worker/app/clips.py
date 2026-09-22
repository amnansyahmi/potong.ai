import json
import os
import re
from typing import Any

import httpx

HOOK_TERMS = {
    "bm": [
        "sebenarnya",
        "ramai",
        "jangan",
        "cara",
        "kenapa",
        "kalau",
        "masalah",
        "silap",
        "tips",
        "paling",
        "tak perlu",
        "tak ramai tahu",
    ],
    "en": [
        "actually",
        "most people",
        "don't",
        "how to",
        "why",
        "problem",
        "mistake",
        "tip",
        "best",
        "worst",
        "nobody",
        "here's",
    ],
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _window_text(parts: list[dict[str, Any]]) -> str:
    return _clean(" ".join(str(part["text"]) for part in parts))


def _local_score(text: str, duration: float, min_duration: int, max_duration: int) -> int:
    lower = text.lower()
    words = text.split()
    score = 42

    target = (min_duration + max_duration) / 2
    distance = abs(duration - target)
    score += max(0, int(18 - distance * 0.6))

    if 55 <= len(words) <= 180:
        score += 10
    elif len(words) >= 35:
        score += 5

    score += min(15, sum(3 for term in HOOK_TERMS["bm"] + HOOK_TERMS["en"] if term in lower))

    if "?" in text:
        score += 5

    if any(mark in text for mark in [":", "!", "."]):
        score += 4

    if text.endswith((".", "?", "!")):
        score += 4

    opening = " ".join(words[:7]).lower()
    if any(opening.startswith(term) for term in ["dan ", "tapi ", "so ", "then ", "because ", "sebab "]):
        score -= 8

    filler_count = len(re.findall(r"\b(?:erm+|uh+|hmm+|aa+|okay so|macam tu)\b", lower))
    score -= min(12, filler_count * 3)

    if any(char.isdigit() for char in text):
        score += 3

    return max(1, min(100, score))


def _candidate_windows(
    segments: list[dict[str, Any]],
    min_duration: int,
    max_duration: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    if not segments:
        return candidates

    for start_index in range(0, len(segments), 2):
        selected: list[dict[str, Any]] = []
        start = float(segments[start_index]["start"])

        for end_index in range(start_index, len(segments)):
            segment = segments[end_index]
            selected.append(segment)
            duration = float(segment["end"]) - start

            if duration < min_duration:
                continue

            if duration > max_duration:
                selected.pop()
                break

            text = _window_text(selected)
            if len(text.split()) < 28:
                continue

            candidates.append(
                {
                    "id": f"c{len(candidates) + 1}",
                    "start": round(start, 3),
                    "end": round(float(selected[-1]["end"]), 3),
                    "duration": round(float(selected[-1]["end"]) - start, 3),
                    "text": text,
                    "score": _local_score(
                        text,
                        float(selected[-1]["end"]) - start,
                        min_duration,
                        max_duration,
                    ),
                }
            )
            break

    return sorted(candidates, key=lambda item: item["score"], reverse=True)[:24]


def _first_title(text: str) -> str:
    words = re.sub(r"[\n\r]+", " ", text).strip().split()
    title = " ".join(words[:10]).strip(" ,.!?:;-")
    if len(words) > 10:
        title += "…"
    return title or "Clip pilihan"


def _fallback_result(candidate: dict[str, Any]) -> dict[str, Any]:
    text = str(candidate["text"])
    first_sentence = re.split(r"(?<=[.!?])\s+", text)[0].strip()

    return {
        **candidate,
        "title": _first_title(text),
        "hook": first_sentence[:220] or text[:220],
        "reason": "Bahagian ini cukup lengkap untuk berdiri sendiri dan mempunyai aliran dialog yang padat.",
        "social_caption": f"{_first_title(text)}\n\n#potongai #videotips",
    }


def _chat_url(base_url: str) -> str:
    value = base_url.rstrip("/")
    if value.endswith("/chat/completions"):
        return value
    if value.endswith("/v1"):
        return value + "/chat/completions"
    return value + "/v1/chat/completions"


def _parse_json(text: str) -> Any:
    cleaned = text.strip()
    cleaned = re.sub(r"^\x60\x60\x60(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*\x60\x60\x60$", "", cleaned)
    return json.loads(cleaned)


def _ai_rerank(candidates: list[dict[str, Any]], clip_count: int, language: str) -> list[dict[str, Any]] | None:
    base_url = os.getenv("AI_BASE_URL", "").strip()
    if not base_url:
        return None

    compact = [
        {
            "id": candidate["id"],
            "start": candidate["start"],
            "end": candidate["end"],
            "local_score": candidate["score"],
            "text": candidate["text"][:900],
        }
        for candidate in candidates[:16]
    ]

    system = (
        "You are selecting short-form clips from a transcript. "
        "Return only valid JSON. Do not invent facts that are not in the transcript. "
        "Prefer moments that start clearly, make sense without missing context, contain a useful hook, "
        "and finish a thought. Titles must be specific, not clickbait. "
        "For Malay content use natural Bahasa Melayu Malaysia, never Indonesian."
    )

    user = {
        "task": f"Choose up to {clip_count} non-overlapping clips and rank them.",
        "audio_language": language,
        "schema": [
            {
                "id": "candidate id",
                "score": "integer 1-100",
                "title": "short specific title",
                "hook": "one sentence from or faithful to the clip",
                "reason": "short explanation",
                "social_caption": "a faithful post caption with up to 3 relevant hashtags",
            }
        ],
        "candidates": compact,
    }

    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("AI_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": os.getenv("AI_MODEL", "auto"),
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
    }

    try:
        with httpx.Client(timeout=45) as client:
            response = client.post(_chat_url(base_url), headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()

        content = body["choices"][0]["message"]["content"]
        parsed = _parse_json(content)
        if not isinstance(parsed, list):
            return None

        by_id = {candidate["id"]: candidate for candidate in candidates}
        result: list[dict[str, Any]] = []

        for item in parsed:
            candidate = by_id.get(str(item.get("id", "")))
            if not candidate:
                continue

            result.append(
                {
                    **candidate,
                    "score": max(1, min(100, int(item.get("score", candidate["score"])))),
                    "title": _clean(str(item.get("title") or _first_title(candidate["text"])))[:90],
                    "hook": _clean(str(item.get("hook") or candidate["text"][:220]))[:240],
                    "reason": _clean(str(item.get("reason") or "Dipilih berdasarkan aliran dan konteks."))[:260],
                    "social_caption": _clean(
                        str(item.get("social_caption") or f"{_first_title(candidate['text'])} #potongai")
                    )[:500],
                }
            )

        return result or None
    except Exception:
        return None


def _overlaps(a: dict[str, Any], b: dict[str, Any]) -> bool:
    intersection = max(0.0, min(float(a["end"]), float(b["end"])) - max(float(a["start"]), float(b["start"])))
    shortest = min(float(a["duration"]), float(b["duration"]))
    return shortest > 0 and intersection / shortest > 0.35


def choose_clips(
    segments: list[dict[str, Any]],
    clip_count: int,
    min_duration: int,
    max_duration: int,
    language: str,
) -> list[dict[str, Any]]:
    candidates = _candidate_windows(segments, min_duration, max_duration)
    if not candidates:
        return []

    ranked = _ai_rerank(candidates, clip_count, language)
    if ranked is None:
        ranked = [_fallback_result(candidate) for candidate in candidates]

    ranked = sorted(ranked, key=lambda item: int(item["score"]), reverse=True)

    selected: list[dict[str, Any]] = []
    for candidate in ranked:
        if any(_overlaps(candidate, existing) for existing in selected):
            continue
        selected.append(candidate)
        if len(selected) >= clip_count:
            break

    return selected
