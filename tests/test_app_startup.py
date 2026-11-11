import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.main import _lifespan


class AppStartupTest(unittest.IsolatedAsyncioTestCase):
    async def test_embedding_is_ready_before_startup_completes(self):
        backend = Mock()
        with patch.dict("os.environ", {"EMBEDDING_PRELOAD": "1", "RERANKER_PRELOAD": "0"}), \
                patch("core.embeddings.embedding_service._load_backend", return_value=backend):
            async with _lifespan(FastAPI()):
                from core.embeddings import EmbeddingService
                from core.embeddings.embedding_service import _load_backend

                _load_backend.assert_called_once()
                self.assertIs(EmbeddingService()._backend, backend)

    async def test_embedding_failure_prevents_accepting_requests(self):
        with patch.dict("os.environ", {"EMBEDDING_PRELOAD": "1", "RERANKER_PRELOAD": "0"}), \
                patch("core.embeddings.embedding_service._load_backend", side_effect=RuntimeError("model unavailable")):
            with self.assertRaisesRegex(RuntimeError, "model unavailable"):
                async with _lifespan(FastAPI()):
                    self.fail("Startup accepted requests without its embedding model")


if __name__ == "__main__":
    unittest.main()
