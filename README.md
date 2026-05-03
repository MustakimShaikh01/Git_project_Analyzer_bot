# RepoAnalyzer 🧠

> **Multi-tenant AI code intelligence platform** — ingest GitHub repositories, index them with FAISS, and query them with RAG + local LLMs.

[![CI](https://github.com/you/repoanalyzer/actions/workflows/ci.yml/badge.svg)](https://github.com/you/repoanalyzer/actions)

---

## Architecture

```
Client (Next.js)
    ↓
FastAPI (JWT Auth + Rate Limiting)
    ↓
Use Cases (Clean Architecture)
    ├── AnalyzeRepo  → Celery Worker → clone → chunk → embed → FAISS
    └── QueryRepo    → embed query → FAISS search → compress → LLM → citations
    ↓
Storage
    ├── PostgreSQL  (metadata, users, query history)
    ├── FAISS       (per-repo vector indexes on disk)
    └── Redis       (Celery broker + result backend)
```

## Quick Start

```bash
# 1. Start infrastructure
docker-compose up -d db redis

# 2. Backend
cd backend
cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload

# 3. Worker (separate terminal)
celery -A app.infrastructure.worker.tasks.celery_app worker -l info -Q indexing

# 4. Frontend
cd frontend
npm install
npm run dev
```

## Run Tests (TDD)

```bash
cd backend
source .venv/bin/activate
pip install -r requirements-test.txt
pytest tests/ -v
```

**35 tests, 0 failures.**

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://localhost/repoanalyzer` | PostgreSQL URL |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL |
| `FAISS_DIR` | `/tmp/faiss_indexes` | Where FAISS indexes are stored |
| `JWT_SECRET` | *(required in prod)* | JWT signing key |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server |
| `OLLAMA_MODEL` | `llama3` | Model for RAG answers |

## Project Structure

```
repoanalyzer/
├── backend/
│   ├── app/
│   │   ├── domain/          # Pure business rules (Repo, User, Query)
│   │   ├── application/     # Use cases (AnalyzeRepo, QueryRepo, chunk_text)
│   │   ├── infrastructure/  # DB, FAISS, Embeddings, LLM, Celery
│   │   └── interfaces/      # FastAPI routes
│   ├── tests/
│   │   ├── test_unit.py         # 25 unit tests (no I/O)
│   │   └── test_integration.py  # 10 HTTP integration tests
│   └── main.py              # Composition root
├── frontend/                # Next.js App Router
│   └── src/app/
│       ├── page.tsx         # Auth (login/register)
│       ├── dashboard/       # Repo list + stats
│       └── repos/[repoId]/  # Chat UI with citations
└── docker-compose.yml
```

## API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/auth/register` | Create account |
| `POST` | `/auth/login` | Get JWT token |
| `POST` | `/repos` | Add + index repo (async) |
| `GET` | `/repos` | List your repos |
| `GET` | `/repos/{id}` | Repo status + chunk count |
| `POST` | `/repos/{id}/query` | RAG query |
| `GET` | `/repos/{id}/history` | Query history |

## Key Design Decisions

| Decision | Choice | Why |
|---|---|---|
| Vector DB | FAISS (local) | Free, fast, swappable to Pinecone |
| Embeddings | sentence-transformers | 384-dim, runs on CPU, no API key |
| LLM | Ollama (local) | Free, private, swappable |
| Queue | Celery + Redis | Async ingestion, crash-safe |
| Auth | JWT HS256 | Stateless, scalable |
| Architecture | Clean/DDD | Testable, domain isolated |
# Git_project_Analyzer_bot
