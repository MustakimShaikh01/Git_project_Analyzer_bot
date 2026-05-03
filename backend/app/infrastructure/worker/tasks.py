"""
Infrastructure – Celery worker configuration and task definitions.
"""
from __future__ import annotations

import logging
import os
from uuid import UUID

from celery import Celery

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "repoanalyzer",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_track_started=True,
    task_acks_late=True,           # tasks re-queued on worker crash
    worker_prefetch_multiplier=1,  # one task at a time per worker (CPU-bound)
    task_routes={
        "repoanalyzer.tasks.index_repo": {"queue": "indexing"},
    },
)


@celery_app.task(
    name="repoanalyzer.tasks.index_repo",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def index_repo_task(self, repo_id: str) -> dict:
    """
    Celery task: asynchronously index a repository.
    Retry up to 3 times on transient failures.
    """
    from app.infrastructure.db.postgres import (
        PostgresRepoRepository,
        PostgresQueryRepository,
        create_engine,
    )
    from app.infrastructure.vector.faiss_store import FAISSVectorStore
    from app.infrastructure.vector.embeddings import SentenceTransformerEmbedder
    from app.application.analyze_repo import AnalyzeRepoUseCase

    engine = create_engine(os.getenv("DATABASE_URL", "postgresql://localhost/repoanalyzer"))
    repo_repo = PostgresRepoRepository(engine)
    vector_store = FAISSVectorStore(os.getenv("FAISS_DIR", "/tmp/faiss_indexes"))
    embedder = SentenceTransformerEmbedder()

    use_case = AnalyzeRepoUseCase(
        repo_repository=repo_repo,
        vector_store=vector_store,
        embedding_service=embedder,
        storage_service=_noop_storage(),
    )

    try:
        use_case.execute(UUID(repo_id))
        return {"status": "done", "repo_id": repo_id}
    except Exception as exc:
        logger.error("index_repo_task failed for %s: %s", repo_id, exc)
        raise self.retry(exc=exc)


class _noop_storage:
    """Placeholder storage adapter (replace with S3 implementation)."""
    def upload_chunks(self, repo_id, chunks):
        pass
