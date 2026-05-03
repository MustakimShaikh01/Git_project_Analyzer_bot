"""
Interfaces layer – FastAPI application + routes.
Auth: JWT (HS256). Multi-tenant: all data scoped by user_id from token.

Architecture note: do NOT use `from __future__ import annotations` here.
Pydantic v2 on Python <3.11 can't resolve forward-ref strings for schemas
defined inside nested function scopes (FastAPI route decorator closures).
"""

import logging
import os
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("JWT_SECRET", "change-me-in-production")
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 60 * 24

limiter = Limiter(key_func=get_remote_address)
security = HTTPBearer()


# ─── Pydantic schemas ─────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class CreateRepoRequest(BaseModel):
    url: str
    name: str

class QueryRequest(BaseModel):
    question: str


# ─── JWT helpers ──────────────────────────────────────────────────────────────

def _create_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": user_id, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def _require_auth(token: str) -> UUID:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str = payload.get("sub")
        if user_id_str is None:
            raise HTTPException(401, "Invalid token")
        return UUID(user_id_str)
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")


def _dispatch_index(repo_id: str) -> None:
    """Seam for testing: patch this instead of the celery task."""
    from app.infrastructure.worker.tasks import index_repo_task
    index_repo_task.delay(repo_id)


def _make_use_case(request: Request):
    from app.application.query_repo import QueryRepoUseCase
    return QueryRepoUseCase(
        repo_repository=request.app.state.repo_repository,
        query_repository=request.app.state.query_repository,
        vector_store=request.app.state.vector_store,
        embedding_service=request.app.state.embedding_service,
        llm_service=request.app.state.llm_service,
        cache=getattr(request.app.state, "cache", None),
    )


# ─── App factory ──────────────────────────────────────────────────────────────

def create_app(
    repo_repository,
    user_repository,
    query_repository,
    vector_store,
    embedding_service,
    llm_service,
    cache=None,
) -> FastAPI:
    app = FastAPI(
        title="RepoAnalyzer API",
        description="Multi-tenant AI code intelligence platform",
        version="2.0.0",
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.repo_repository = repo_repository
    app.state.user_repository = user_repository
    app.state.query_repository = query_repository
    app.state.vector_store = vector_store
    app.state.embedding_service = embedding_service
    app.state.llm_service = llm_service
    app.state.cache = cache

    register_routes(app)
    return app


def register_routes(app: FastAPI) -> None:

    # ── Health ───────────────────────────────────────────────────────────────
    @app.get("/health", tags=["ops"])
    def health():
        return {"status": "ok", "ts": datetime.utcnow().isoformat()}

    # ── Auth ─────────────────────────────────────────────────────────────────
    @app.post("/auth/register", tags=["auth"])
    @limiter.limit("10/minute")
    def register(request: Request, body: RegisterRequest):
        from app.domain.user import User
        existing = request.app.state.user_repository.get_by_email(body.email)
        if existing:
            raise HTTPException(400, "Email already registered")
        user = User.create(body.email, body.password)
        request.app.state.user_repository.save(user)
        return {"user_id": str(user.id)}

    @app.post("/auth/login", tags=["auth"])
    @limiter.limit("20/minute")
    def login(request: Request, body: LoginRequest):
        user = request.app.state.user_repository.get_by_email(body.email)
        if not user or not user.verify_password(body.password):
            raise HTTPException(401, "Invalid credentials")
        token = _create_token(str(user.id))
        return {"access_token": token, "token_type": "bearer"}

    # ── Repos ─────────────────────────────────────────────────────────────────
    @app.post("/repos", status_code=202, tags=["repos"])
    @limiter.limit("30/minute")
    def create_repo(
        request: Request,
        body: CreateRepoRequest,
        creds: HTTPAuthorizationCredentials = Depends(security),
    ):
        user_id = _require_auth(creds.credentials)
        from app.domain.repo import Repo
        repo = Repo.create(user_id=user_id, url=body.url, name=body.name)
        request.app.state.repo_repository.save(repo)
        _dispatch_index(str(repo.id))
        return {"repo_id": str(repo.id), "status": repo.status}

    @app.get("/repos", tags=["repos"])
    def list_repos(
        request: Request,
        creds: HTTPAuthorizationCredentials = Depends(security),
    ):
        user_id = _require_auth(creds.credentials)
        repos = request.app.state.repo_repository.list_by_user(user_id)
        return [
            {
                "id": str(r.id),
                "name": r.name,
                "url": r.url,
                "status": r.status,
                "chunk_count": r.chunk_count,
                "created_at": r.created_at.isoformat(),
            }
            for r in repos
        ]

    @app.get("/repos/{repo_id}", tags=["repos"])
    def get_repo(
        request: Request,
        repo_id: UUID,
        creds: HTTPAuthorizationCredentials = Depends(security),
    ):
        user_id = _require_auth(creds.credentials)
        repo = request.app.state.repo_repository.get_by_id(repo_id)
        if repo is None or repo.user_id != user_id:
            raise HTTPException(404, "Repo not found")
        return {
            "id": str(repo.id),
            "name": repo.name,
            "url": repo.url,
            "status": repo.status,
            "chunk_count": repo.chunk_count,
            "error_message": repo.error_message,
        }

    # ── Query: blocking ───────────────────────────────────────────────────────
    @app.post("/repos/{repo_id}/query", tags=["query"])
    @limiter.limit("60/minute")
    def query_repo(
        request: Request,
        repo_id: UUID,
        body: QueryRequest,
        creds: HTTPAuthorizationCredentials = Depends(security),
    ):
        user_id = _require_auth(creds.credentials)
        use_case = _make_use_case(request)
        try:
            return use_case.execute(user_id, repo_id, body.question)
        except PermissionError as e:
            raise HTTPException(403, str(e))
        except ValueError as e:
            raise HTTPException(400, str(e))

    # ── Query: streaming SSE ──────────────────────────────────────────────────
    @app.post("/repos/{repo_id}/query/stream", tags=["query"])
    @limiter.limit("60/minute")
    def query_repo_stream(
        request: Request,
        repo_id: UUID,
        body: QueryRequest,
        creds: HTTPAuthorizationCredentials = Depends(security),
    ):
        """Server-Sent Events — tokens streamed word-by-word."""
        import json as _json
        user_id = _require_auth(creds.credentials)
        use_case = _make_use_case(request)

        def event_stream():
            try:
                yield from use_case.stream(user_id, repo_id, body.question)
            except PermissionError as e:
                yield f"data: {_json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            except ValueError as e:
                yield f"data: {_json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    # ── History ───────────────────────────────────────────────────────────────
    @app.get("/repos/{repo_id}/history", tags=["query"])
    def query_history(
        request: Request,
        repo_id: UUID,
        creds: HTTPAuthorizationCredentials = Depends(security),
    ):
        user_id = _require_auth(creds.credentials)
        records = request.app.state.query_repository.list_by_user_repo(user_id, repo_id)
        return [
            {
                "id": str(r.id),
                "question": r.question,
                "answer": r.answer,
                "latency_ms": r.latency_ms,
                "created_at": r.created_at.isoformat(),
            }
            for r in records
        ]
