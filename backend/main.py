"""
Backend entrypoint.
Run: uvicorn main:app --reload
"""
import logging
import os

from sqlalchemy import create_engine

from app.infrastructure.db.postgres import (
    PostgresQueryRepository,
    PostgresRepoRepository,
    PostgresUserRepository,
    create_tables,
)
from app.infrastructure.cache.redis_cache import RedisCache
from app.infrastructure.llm.ollama import OllamaLLM
from app.infrastructure.vector.embeddings import SentenceTransformerEmbedder
from app.infrastructure.vector.faiss_store import FAISSVectorStore
from app.interfaces.routes import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/repoanalyzer")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
FAISS_DIR = os.getenv("FAISS_DIR", "/tmp/faiss_indexes")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

engine = create_engine(DATABASE_URL)
create_tables(engine)

repo_repository = PostgresRepoRepository(engine)
user_repository = PostgresUserRepository(engine)
query_repository = PostgresQueryRepository(engine)
vector_store = FAISSVectorStore(FAISS_DIR)
embedder = SentenceTransformerEmbedder()
llm = OllamaLLM(model=OLLAMA_MODEL, base_url=OLLAMA_URL)
cache = RedisCache(REDIS_URL)

app = create_app(
    repo_repository=repo_repository,
    user_repository=user_repository,
    query_repository=query_repository,
    vector_store=vector_store,
    embedding_service=embedder,
    llm_service=llm,
    cache=cache,
)

