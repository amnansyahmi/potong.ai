import json
import os
from pathlib import Path
from typing import Any

import httpx


def blob_enabled() -> bool:
    return bool(os.getenv("BLOB_READ_WRITE_TOKEN", "").strip())


def put_file(pathname: str, source: Path, content_type: str) -> str:
    if not blob_enabled():
        raise RuntimeError("BLOB_READ_WRITE_TOKEN belum tersedia pada worker.")

    from vercel.blob import BlobClient

    client = BlobClient()
    result = client.put(
        pathname,
        source.read_bytes(),
        access="public",
        content_type=content_type,
        overwrite=True,
        multipart=source.stat().st_size > 10 * 1024 * 1024,
    )
    return str(result.url)


def put_json(pathname: str, payload: dict[str, Any]) -> str:
    if not blob_enabled():
        raise RuntimeError("BLOB_READ_WRITE_TOKEN belum tersedia pada worker.")

    from vercel.blob import BlobClient

    client = BlobClient()
    result = client.put(
        pathname,
        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        access="public",
        content_type="application/json; charset=utf-8",
        overwrite=True,
    )
    return str(result.url)


def read_json(pathname: str) -> dict[str, Any] | None:
    if not blob_enabled():
        return None

    from vercel.blob import list_objects

    page = list_objects(prefix=pathname, limit=1)
    match = next((item for item in page.blobs if item.pathname == pathname), None)
    if match is None:
        return None

    response = httpx.get(str(match.url), timeout=20, follow_redirects=True)
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else None
