import os
import sys
import types
import unittest
from unittest.mock import patch

try:
    import httpx  # noqa: F401
except ModuleNotFoundError:
    # These validation tests do not make network requests. The deployed worker
    # installs httpx from requirements.txt.
    sys.modules["httpx"] = types.ModuleType("httpx")

from app.sources import _ydl_options, validate_blob_upload_url, validate_youtube_url


class SourceValidationTests(unittest.TestCase):
    def test_accepts_known_youtube_hosts(self):
        self.assertEqual(
            validate_youtube_url("https://youtu.be/abc123"),
            "https://youtu.be/abc123",
        )

    def test_rejects_lookalike_youtube_host(self):
        with self.assertRaises(ValueError):
            validate_youtube_url("https://youtube.com.example.test/watch?v=abc")

    def test_accepts_only_public_vercel_blob_urls(self):
        value = "https://store.public.blob.vercel-storage.com/inputs/video.mp4"
        self.assertEqual(validate_blob_upload_url(value), value)
        with self.assertRaises(ValueError):
            validate_blob_upload_url("https://example.com/video.mp4")

    def test_youtube_options_include_configured_clients_and_proxy(self):
        environment = {
            "YOUTUBE_COOKIES_BASE64": "",
            "YOUTUBE_PLAYER_CLIENTS": "mweb,web_embedded",
            "YOUTUBE_PROXY_URL": "http://proxy.example:8080",
        }
        with patch.dict(os.environ, environment, clear=False):
            options = _ydl_options(download=False)
        self.assertEqual(options["proxy"], "http://proxy.example:8080")
        self.assertEqual(
            options["extractor_args"]["youtube"]["player_client"],
            ["mweb", "web_embedded"],
        )


if __name__ == "__main__":
    unittest.main()
