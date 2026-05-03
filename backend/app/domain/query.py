"""
Domain layer – Query entity and search result value object.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4


@dataclass
class QueryRecord:
    id: UUID
    user_id: UUID
    repo_id: UUID
    question: str
    answer: str
    latency_ms: float
    created_at: datetime

    @staticmethod
    def create(
        user_id: UUID,
        repo_id: UUID,
        question: str,
        answer: str,
        latency_ms: float,
    ) -> "QueryRecord":
        return QueryRecord(
            id=uuid4(),
            user_id=user_id,
            repo_id=repo_id,
            question=question,
            answer=answer,
            latency_ms=latency_ms,
            created_at=datetime.utcnow(),
        )


@dataclass
class SearchResult:
    """Value object returned by vector search."""

    chunk_id: UUID
    file_path: str
    start_line: int
    end_line: int
    content: str
    score: float
    language: str = "unknown"
    citations: list[str] = field(default_factory=list)
