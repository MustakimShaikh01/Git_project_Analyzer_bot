"""
Infrastructure – FAISS vector store adapter.
Keeps a per-repo index on disk; metadata maps vector IDs to chunk data.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import UUID

import numpy as np

logger = logging.getLogger(__name__)


class FAISSVectorStore:
    """
    On-disk FAISS index per repo.

    Production upgrade path: swap for Pinecone / Weaviate adapter
    that satisfies the same interface without changing use-cases.
    """

    def __init__(self, index_dir: str, dimension: int = 384):
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.dimension = dimension
        self._cache: dict[str, object] = {}  # repo_id → faiss.Index

    def upsert(self, repo_id: UUID, chunks, embeddings: list[list[float]]) -> None:
        import faiss  # lazy import — prod has it, tests mock it

        index_path = self._index_path(repo_id)
        meta_path = self._meta_path(repo_id)

        vectors = np.array(embeddings, dtype="float32")
        faiss.normalize_L2(vectors)

        index = faiss.IndexFlatIP(self.dimension)
        index.add(vectors)
        faiss.write_index(index, str(index_path))

        metadata = [
            {
                "chunk_id": str(chunk.id),
                "file_path": chunk.file_path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "language": chunk.language,
                "content": chunk.content,
            }
            for chunk in chunks
        ]
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False))
        self._cache.pop(str(repo_id), None)
        logger.info("Upserted %d vectors for repo %s", len(embeddings), repo_id)

    def search(self, repo_id: UUID, query_embedding: list[float], top_k: int = 8):
        import faiss
        from app.domain.query import SearchResult
        from uuid import UUID as _UUID

        index = self._load_index(repo_id)
        meta = self._load_meta(repo_id)

        vec = np.array([query_embedding], dtype="float32")
        faiss.normalize_L2(vec)
        scores, indices = index.search(vec, top_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(meta):
                continue
            m = meta[idx]
            results.append(
                SearchResult(
                    chunk_id=_UUID(m["chunk_id"]),
                    file_path=m["file_path"],
                    start_line=m["start_line"],
                    end_line=m["end_line"],
                    content=m["content"],
                    score=float(score),
                    language=m.get("language", "unknown"),
                )
            )
        return results

    def delete(self, repo_id: UUID) -> None:
        self._index_path(repo_id).unlink(missing_ok=True)
        self._meta_path(repo_id).unlink(missing_ok=True)
        self._cache.pop(str(repo_id), None)

    # ------------------------------------------------------------------ #

    def _index_path(self, repo_id: UUID) -> Path:
        return self.index_dir / f"{repo_id}.faiss"

    def _meta_path(self, repo_id: UUID) -> Path:
        return self.index_dir / f"{repo_id}.meta.json"

    def _load_index(self, repo_id: UUID):
        import faiss
        key = str(repo_id)
        if key not in self._cache:
            path = self._index_path(repo_id)
            if not path.exists():
                raise FileNotFoundError(f"No index for repo {repo_id}")
            self._cache[key] = faiss.read_index(str(path))
        return self._cache[key]

    def _load_meta(self, repo_id: UUID) -> list[dict]:
        path = self._meta_path(repo_id)
        if not path.exists():
            return []
        return json.loads(path.read_text())
