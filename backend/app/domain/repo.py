"""
Domain layer – Repo entity and value objects.
Pure Python, zero framework dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4


class RepoStatus(str, Enum):
    PENDING = "pending"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


@dataclass
class Repo:
    """Core Repo entity – owns business rules."""

    id: UUID
    user_id: UUID
    url: str
    name: str
    status: RepoStatus
    created_at: datetime
    updated_at: datetime
    error_message: str | None = None
    chunk_count: int = 0

    @staticmethod
    def create(user_id: UUID, url: str, name: str) -> "Repo":
        now = datetime.utcnow()
        return Repo(
            id=uuid4(),
            user_id=user_id,
            url=url,
            name=name,
            status=RepoStatus.PENDING,
            created_at=now,
            updated_at=now,
        )

    def mark_indexing(self) -> None:
        self.status = RepoStatus.INDEXING
        self.updated_at = datetime.utcnow()

    def mark_ready(self, chunk_count: int) -> None:
        self.status = RepoStatus.READY
        self.chunk_count = chunk_count
        self.updated_at = datetime.utcnow()

    def mark_failed(self, reason: str) -> None:
        self.status = RepoStatus.FAILED
        self.error_message = reason
        self.updated_at = datetime.utcnow()

    def is_queryable(self) -> bool:
        return self.status == RepoStatus.READY


@dataclass
class RepoChunk:
    """Value object – a single indexed chunk of code."""

    id: UUID = field(default_factory=uuid4)
    repo_id: UUID = field(default_factory=uuid4)
    file_path: str = ""
    start_line: int = 0
    end_line: int = 0
    content: str = ""
    language: str = "unknown"
