"""
Infrastructure – Embedding service adapters.

Provides:
  - SentenceTransformerEmbedder (local, free, good quality)
  - OllamaEmbedder (local LLM server)

Both implement the same interface so they're swappable.
"""
from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class EmbeddingService(Protocol):
    def embed_single(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerEmbedder:
    """
    Uses `sentence-transformers` (all-MiniLM-L6-v2 by default).
    384-dim vectors, fast, runs on CPU.
    """

    MODEL_NAME = "all-MiniLM-L6-v2"
    BATCH_SIZE = 256

    def __init__(self, model_name: str = MODEL_NAME):
        # Lazy-load to keep import time low
        self._model = None
        self._model_name = model_name

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading embedding model: %s", self._model_name)
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed_single(self, text: str) -> list[float]:
        return self.model.encode([text])[0].tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        results = []
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]
            vecs = self.model.encode(batch, show_progress_bar=False)
            results.extend(v.tolist() for v in vecs)
        return results


class OllamaEmbedder:
    """
    Uses Ollama's local embedding endpoint.
    Good for experimenting with nomic-embed-text or mxbai-embed-large.
    """

    def __init__(self, model: str = "nomic-embed-text", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def embed_single(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        import httpx
        results = []
        for text in texts:
            response = httpx.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=30,
            )
            response.raise_for_status()
            results.append(response.json()["embedding"])
        return results
