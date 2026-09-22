import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.transcribe import _configure_writable_runtime


class TranscribeRuntimeTests(unittest.TestCase):
    def test_vercel_caches_are_redirected_to_writable_scratch_space(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {"VERCEL": "1", "POTONG_CACHE_DIR": directory},
                clear=False,
            ):
                root = _configure_writable_runtime()

                self.assertEqual(root, Path(directory))
                self.assertEqual(os.environ["XDG_CACHE_HOME"], directory)
                self.assertTrue(Path(os.environ["HF_HUB_CACHE"]).is_dir())
                self.assertTrue(Path(os.environ["HF_ASSETS_CACHE"]).is_dir())
                self.assertTrue(Path(os.environ["HF_XET_CACHE"]).is_dir())
                self.assertEqual(os.environ["HF_HUB_DISABLE_XET"], "1")

    def test_local_runtime_keeps_existing_cache_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(_configure_writable_runtime())


if __name__ == "__main__":
    unittest.main()
