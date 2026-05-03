"""
Integration tests – FastAPI routes with in-memory fakes (no DB/Redis required).
Run: pytest tests/test_integration.py -v
"""
import unittest.mock as mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.domain.query import SearchResult
from app.domain.repo import Repo, RepoStatus
from app.interfaces.routes import create_app, limiter


# ─── In-memory fakes ──────────────────────────────────────────────────────────

class InMemoryUserRepo:
    def __init__(self):
        self._users: dict = {}

    def get_by_email(self, email):
        return self._users.get(email.lower())

    def get_by_id(self, user_id):
        return next((u for u in self._users.values() if u.id == user_id), None)

    def save(self, user):
        self._users[user.email] = user


class InMemoryRepoRepo:
    def __init__(self):
        self._repos: dict = {}

    def get_by_id(self, repo_id):
        return self._repos.get(str(repo_id))

    def list_by_user(self, user_id):
        return [r for r in self._repos.values() if r.user_id == user_id]

    def save(self, repo):
        self._repos[str(repo.id)] = repo


class InMemoryQueryRepo:
    def __init__(self):
        self._records = []

    def save(self, record):
        self._records.append(record)

    def list_by_user_repo(self, user_id, repo_id):
        return [r for r in self._records if r.user_id == user_id and r.repo_id == repo_id]


class FakeVectorStore:
    def search(self, repo_id, query_embedding, top_k):
        return [
            SearchResult(
                chunk_id=uuid4(),
                file_path="src/app.py",
                start_line=5,
                end_line=20,
                content="def handler(): ...",
                score=0.9,
            )
        ]

    def upsert(self, *_): pass


class FakeEmbedder:
    def embed_single(self, text): return [0.0] * 384
    def embed_batch(self, texts): return [[0.0] * 384 for _ in texts]


class FakeLLM:
    def generate(self, prompt): return "The answer is 42"


# ─── Fixture ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client_and_deps():
    """Fresh app + stores per test. Rate limiter reset between tests."""
    user_repo = InMemoryUserRepo()
    repo_repo = InMemoryRepoRepo()
    query_repo = InMemoryQueryRepo()

    app = create_app(
        repo_repository=repo_repo,
        user_repository=user_repo,
        query_repository=query_repo,
        vector_store=FakeVectorStore(),
        embedding_service=FakeEmbedder(),
        llm_service=FakeLLM(),
    )

    with mock.patch("app.interfaces.routes._dispatch_index"):
        limiter.reset()  # clear rate-limit counters between tests
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client, user_repo, repo_repo, query_repo


def _uniq_email(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:6]}@test.com"


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_health_ok(self, client_and_deps):
        client, *_ = client_and_deps
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestAuthEndpoints:
    def test_register_and_login(self, client_and_deps):
        client, *_ = client_and_deps
        email = _uniq_email("alice")
        r = client.post("/auth/register", json={"email": email, "password": "secret"})
        assert r.status_code == 200
        assert "user_id" in r.json()

        r = client.post("/auth/login", json={"email": email, "password": "secret"})
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_login_wrong_password(self, client_and_deps):
        client, *_ = client_and_deps
        email = _uniq_email("bob")
        client.post("/auth/register", json={"email": email, "password": "correct"})
        r = client.post("/auth/login", json={"email": email, "password": "wrong"})
        assert r.status_code == 401

    def test_duplicate_register(self, client_and_deps):
        client, *_ = client_and_deps
        email = _uniq_email("dup")
        client.post("/auth/register", json={"email": email, "password": "pass"})
        r = client.post("/auth/register", json={"email": email, "password": "pass"})
        assert r.status_code == 400


class TestRepoEndpoints:
    def _auth_headers(self, client, prefix="dev"):
        email = _uniq_email(prefix)
        client.post("/auth/register", json={"email": email, "password": "pass"})
        r = client.post("/auth/login", json={"email": email, "password": "pass"})
        token = r.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_create_repo(self, client_and_deps):
        client, *_ = client_and_deps
        headers = self._auth_headers(client, "cr")
        r = client.post("/repos", json={"url": "https://github.com/x/y", "name": "y"}, headers=headers)
        assert r.status_code == 202
        assert "repo_id" in r.json()

    def test_list_repos(self, client_and_deps):
        client, *_ = client_and_deps
        headers = self._auth_headers(client, "lr")
        client.post("/repos", json={"url": "https://github.com/x/y", "name": "y"}, headers=headers)
        r = client.get("/repos", headers=headers)
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_get_repo_not_found(self, client_and_deps):
        client, *_ = client_and_deps
        headers = self._auth_headers(client, "gnf")
        r = client.get(f"/repos/{uuid4()}", headers=headers)
        assert r.status_code == 404

    def test_unauthorized_access(self, client_and_deps):
        client, *_ = client_and_deps
        r = client.get("/repos")
        assert r.status_code == 403


class TestQueryEndpoint:
    def _setup(self, client, prefix, repo_repo):
        from uuid import UUID
        email = _uniq_email(prefix)
        client.post("/auth/register", json={"email": email, "password": "pass"})
        r = client.post("/auth/login", json={"email": email, "password": "pass"})
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        cr = client.post("/repos", json={"url": "https://github.com/x/y", "name": "y"}, headers=headers)
        repo_id = cr.json()["repo_id"]
        repo = repo_repo.get_by_id(UUID(repo_id))
        repo.mark_ready(50)
        return headers, repo_id

    def test_query_ready_repo(self, client_and_deps):
        client, _, repo_repo, _ = client_and_deps
        headers, repo_id = self._setup(client, "qr", repo_repo)
        r = client.post(f"/repos/{repo_id}/query", json={"question": "what does main do?"}, headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert body["answer"] == "The answer is 42"
        assert "citations" in body

    def test_query_history(self, client_and_deps):
        client, _, repo_repo, _ = client_and_deps
        headers, repo_id = self._setup(client, "qh", repo_repo)
        client.post(f"/repos/{repo_id}/query", json={"question": "Q1?"}, headers=headers)
        r = client.get(f"/repos/{repo_id}/history", headers=headers)
        assert r.status_code == 200
        assert len(r.json()) == 1
