"""
Infrastructure – PostgreSQL repository implementations.
Uses SQLAlchemy Core (not ORM) for fine-grained control.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.engine import Engine

metadata = MetaData()

users_table = Table(
    "users",
    metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    Column("email", String(255), unique=True, nullable=False),
    Column("hashed_password", Text, nullable=False),
    Column("is_active", Boolean, default=True),
    Column("created_at", DateTime, nullable=False),
)

repos_table = Table(
    "repos",
    metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    Column("user_id", PG_UUID(as_uuid=True), nullable=False),
    Column("url", Text, nullable=False),
    Column("name", String(255), nullable=False),
    Column("status", String(50), nullable=False, default="pending"),
    Column("chunk_count", Integer, default=0),
    Column("error_message", Text),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)

queries_table = Table(
    "queries",
    metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True),
    Column("user_id", PG_UUID(as_uuid=True), nullable=False),
    Column("repo_id", PG_UUID(as_uuid=True), nullable=False),
    Column("question", Text, nullable=False),
    Column("answer", Text, nullable=False),
    Column("latency_ms", Float, nullable=False),
    Column("created_at", DateTime, nullable=False),
)


def create_tables(engine: Engine) -> None:
    metadata.create_all(engine)


# --------------------------------------------------------------------------- #
# Repository implementations                                                  #
# --------------------------------------------------------------------------- #

from app.domain.repo import Repo, RepoStatus
from app.domain.user import User
from app.domain.query import QueryRecord


class PostgresRepoRepository:
    def __init__(self, engine: Engine):
        self.engine = engine

    def get_by_id(self, repo_id: UUID) -> Repo | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                repos_table.select().where(repos_table.c.id == repo_id)
            ).fetchone()
        if row is None:
            return None
        return self._map(row)

    def list_by_user(self, user_id: UUID) -> list[Repo]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                repos_table.select().where(repos_table.c.user_id == user_id)
            ).fetchall()
        return [self._map(r) for r in rows]

    def save(self, repo: Repo) -> None:
        with self.engine.begin() as conn:
            existing = conn.execute(
                repos_table.select().where(repos_table.c.id == repo.id)
            ).fetchone()
            if existing:
                conn.execute(
                    repos_table.update()
                    .where(repos_table.c.id == repo.id)
                    .values(
                        status=repo.status.value,
                        chunk_count=repo.chunk_count,
                        error_message=repo.error_message,
                        updated_at=repo.updated_at,
                    )
                )
            else:
                conn.execute(
                    repos_table.insert().values(
                        id=repo.id,
                        user_id=repo.user_id,
                        url=repo.url,
                        name=repo.name,
                        status=repo.status.value,
                        chunk_count=repo.chunk_count,
                        error_message=repo.error_message,
                        created_at=repo.created_at,
                        updated_at=repo.updated_at,
                    )
                )

    @staticmethod
    def _map(row) -> Repo:
        return Repo(
            id=row.id,
            user_id=row.user_id,
            url=row.url,
            name=row.name,
            status=RepoStatus(row.status),
            chunk_count=row.chunk_count or 0,
            error_message=row.error_message,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class PostgresUserRepository:
    def __init__(self, engine: Engine):
        self.engine = engine

    def get_by_email(self, email: str) -> User | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                users_table.select().where(users_table.c.email == email.lower())
            ).fetchone()
        if row is None:
            return None
        return User(
            id=row.id,
            email=row.email,
            hashed_password=row.hashed_password,
            is_active=row.is_active,
            created_at=row.created_at,
        )

    def get_by_id(self, user_id: UUID) -> User | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                users_table.select().where(users_table.c.id == user_id)
            ).fetchone()
        if row is None:
            return None
        return User(
            id=row.id,
            email=row.email,
            hashed_password=row.hashed_password,
            is_active=row.is_active,
            created_at=row.created_at,
        )

    def save(self, user: User) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                users_table.insert().values(
                    id=user.id,
                    email=user.email,
                    hashed_password=user.hashed_password,
                    is_active=user.is_active,
                    created_at=user.created_at,
                )
            )


class PostgresQueryRepository:
    def __init__(self, engine: Engine):
        self.engine = engine

    def save(self, record: QueryRecord) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                queries_table.insert().values(
                    id=record.id,
                    user_id=record.user_id,
                    repo_id=record.repo_id,
                    question=record.question,
                    answer=record.answer,
                    latency_ms=record.latency_ms,
                    created_at=record.created_at,
                )
            )

    def list_by_user_repo(self, user_id: UUID, repo_id: UUID) -> list[QueryRecord]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                queries_table.select()
                .where(queries_table.c.user_id == user_id)
                .where(queries_table.c.repo_id == repo_id)
                .order_by(queries_table.c.created_at.desc())
                .limit(50)
            ).fetchall()
        return [
            QueryRecord(
                id=r.id,
                user_id=r.user_id,
                repo_id=r.repo_id,
                question=r.question,
                answer=r.answer,
                latency_ms=r.latency_ms,
                created_at=r.created_at,
            )
            for r in rows
        ]
