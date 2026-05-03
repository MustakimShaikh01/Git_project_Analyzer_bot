"""
Application use-case – AnalyzeRepo.
Orchestrates: clone → filter → chunk → embed → index → persist.
This is called by the Celery worker (async).
"""
from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path
from uuid import UUID

from app.application.chunk_text import chunk_code_file
from app.domain.repo import Repo, RepoChunk, RepoStatus

logger = logging.getLogger(__name__)

# File extensions we care about
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go",
    ".rs", ".cpp", ".c", ".h", ".cs", ".rb", ".php",
    ".md", ".txt", ".yaml", ".yml", ".json", ".toml",
}

MAX_FILE_SIZE_BYTES = 500_000  # 500 KB per file


class AnalyzeRepoUseCase:
    """
    Coordinates repo ingestion.

    Dependencies injected at construction time (testable).
    """

    def __init__(self, repo_repository, vector_store, embedding_service, storage_service):
        self.repo_repo = repo_repository
        self.vector_store = vector_store
        self.embedder = embedding_service
        self.storage = storage_service

    def execute(self, repo_id: UUID) -> None:
        repo: Repo = self.repo_repo.get_by_id(repo_id)
        if repo is None:
            raise ValueError(f"Repo {repo_id} not found")

        if not repo.is_queryable() and repo.status != RepoStatus.PENDING:
            logger.warning("Repo %s already being processed: %s", repo_id, repo.status)
            return

        repo.mark_indexing()
        self.repo_repo.save(repo)

        try:
            t0 = time.monotonic()
            with tempfile.TemporaryDirectory() as tmpdir:
                self._clone_repo(repo.url, tmpdir)
                chunks = self._extract_chunks(Path(tmpdir))

            embeddings = self.embedder.embed_batch([c["content"] for c in chunks])

            repo_chunks = [
                RepoChunk(
                    repo_id=repo.id,
                    file_path=c["file_path"],
                    start_line=c["start_line"],
                    end_line=c["end_line"],
                    content=c["content"],
                    language=c["language"],
                )
                for c in chunks
            ]

            self.vector_store.upsert(repo.id, repo_chunks, embeddings)
            self.storage.upload_chunks(repo.id, chunks)

            elapsed = (time.monotonic() - t0) * 1000
            repo.mark_ready(chunk_count=len(chunks))
            self.repo_repo.save(repo)
            logger.info("Indexed repo %s: %d chunks in %.0fms", repo_id, len(chunks), elapsed)

        except Exception as exc:  # noqa: BLE001
            repo.mark_failed(str(exc))
            self.repo_repo.save(repo)
            logger.error("Indexing failed for %s: %s", repo_id, exc)
            raise

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _clone_repo(self, url: str, target_dir: str) -> None:
        import subprocess
        result = subprocess.run(
            ["git", "clone", "--depth=1", url, target_dir],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git clone failed: {result.stderr[:500]}")

    def _extract_chunks(self, root: Path) -> list[dict]:
        all_chunks: list[dict] = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in CODE_EXTENSIONS:
                continue
            if path.stat().st_size > MAX_FILE_SIZE_BYTES:
                continue
            try:
                source = path.read_text(errors="replace")
                relative = str(path.relative_to(root))
                file_chunks = chunk_code_file(source, language=path.suffix.lstrip("."))
                for chunk in file_chunks:
                    chunk["file_path"] = relative
                all_chunks.extend(file_chunks)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping %s: %s", path, exc)
        return all_chunks
