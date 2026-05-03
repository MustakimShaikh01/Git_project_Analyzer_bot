"""
Application use-case – QueryRepo (RAG) v2.
Improvements over v1:
  1. Redis answer cache (exact match) → sub-ms repeated answers
  2. Query rewriting — expand abbreviations before embedding
  3. Better context compression with MMR (Max Marginal Relevance)
  4. Richer prompt template — forces structured output
  5. Streaming support via generator
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Generator
from uuid import UUID

from app.domain.query import QueryRecord, SearchResult
from app.domain.repo import Repo

logger = logging.getLogger(__name__)

TOP_K = 12          # retrieve more, compress later
COMPRESS_TO = 6     # keep top 6 after MMR
CACHE_TTL = 3600    # 1 hour answer cache


class QueryRepoUseCase:
    def __init__(
        self,
        repo_repository,
        query_repository,
        vector_store,
        embedding_service,
        llm_service,
        cache=None,           # optional Redis cache
    ):
        self.repo_repo = repo_repository
        self.query_repo = query_repository
        self.vector_store = vector_store
        self.embedder = embedding_service
        self.llm = llm_service
        self.cache = cache

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def execute(self, user_id: UUID, repo_id: UUID, question: str) -> dict:
        """Full RAG pipeline. Returns answer + citations + latency."""
        repo = self._get_verified_repo(user_id, repo_id)
        t0 = time.monotonic()

        # 1. Cache lookup
        cache_key = self._cache_key(repo_id, question)
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                logger.info("Cache HIT for repo=%s question=%r", repo_id, question[:50])
                return json.loads(cached)

        # 2. Query rewriting (expand → richer embedding)
        expanded_query = self._rewrite_query(question)

        # 3. Embed + search
        query_vec = self.embedder.embed_single(expanded_query)
        results: list[SearchResult] = self.vector_store.search(
            repo_id=repo_id, query_embedding=query_vec, top_k=TOP_K
        )

        # 4. MMR-based compression (diversity + relevance)
        compressed = self._mmr_compress(results, query_vec)

        # 5. Build context blocks with language hints
        context_blocks = self._build_context_blocks(compressed)
        context = "\n\n".join(context_blocks)

        # 6. Structured prompt
        prompt = self._build_prompt(question, context, repo.name)

        # 7. LLM
        answer = self.llm.generate(prompt)
        answer = self._postprocess_answer(answer)

        # 8. Citations (file + line)
        citations = [
            {"file": r.file_path, "line": r.start_line, "language": r.language}
            for r in compressed
        ]

        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        result = {
            "answer": answer,
            "citations": citations,
            "latency_ms": latency_ms,
            "chunks_used": len(compressed),
            "cache_hit": False,
        }

        # 9. Persist query record
        record = QueryRecord.create(
            user_id=user_id,
            repo_id=repo_id,
            question=question,
            answer=answer,
            latency_ms=latency_ms,
        )
        self.query_repo.save(record)

        # 10. Cache result
        if self.cache:
            self.cache.setex(cache_key, CACHE_TTL, json.dumps(result))

        return result

    def stream(
        self, user_id: UUID, repo_id: UUID, question: str
    ) -> Generator[str, None, None]:
        """
        Streaming version — yields SSE-compatible data chunks.
        LLM must support stream() method (OllamaLLM does).
        """
        repo = self._get_verified_repo(user_id, repo_id)

        cache_key = self._cache_key(repo_id, question)
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                data = json.loads(cached)
                yield f"data: {json.dumps({'type': 'answer', 'text': data['answer']})}\n\n"
                yield f"data: {json.dumps({'type': 'citations', 'citations': data['citations']})}\n\n"
                yield "data: [DONE]\n\n"
                return

        expanded_query = self._rewrite_query(question)
        query_vec = self.embedder.embed_single(expanded_query)
        results = self.vector_store.search(repo_id=repo_id, query_embedding=query_vec, top_k=TOP_K)
        compressed = self._mmr_compress(results, query_vec)

        context_blocks = self._build_context_blocks(compressed)
        context = "\n\n".join(context_blocks)
        prompt = self._build_prompt(question, context, repo.name)

        citations = [
            {"file": r.file_path, "line": r.start_line, "language": r.language}
            for r in compressed
        ]

        # Stream citations first so UI can show them immediately
        yield f"data: {json.dumps({'type': 'citations', 'citations': citations})}\n\n"

        # Then stream tokens
        full_answer = ""
        t0 = time.monotonic()
        for token in self.llm.stream(prompt):
            full_answer += token
            yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"

        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        yield f"data: {json.dumps({'type': 'done', 'latency_ms': latency_ms})}\n\n"

        # Persist + cache
        record = QueryRecord.create(
            user_id=user_id, repo_id=repo_id,
            question=question, answer=full_answer, latency_ms=latency_ms,
        )
        self.query_repo.save(record)
        if self.cache:
            result = {"answer": full_answer, "citations": citations, "latency_ms": latency_ms}
            self.cache.setex(cache_key, CACHE_TTL, json.dumps(result))

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _get_verified_repo(self, user_id: UUID, repo_id: UUID) -> Repo:
        repo: Repo = self.repo_repo.get_by_id(repo_id)
        if repo is None or repo.user_id != user_id:
            raise PermissionError("Repo not found or access denied")
        if not repo.is_queryable():
            raise ValueError(f"Repo not ready for querying. Status: {repo.status}")
        return repo

    def _rewrite_query(self, question: str) -> str:
        """
        Expand shorthand and add semantic context.
        Simple rule-based rewriting — no LLM call needed.
        """
        expansions = {
            "auth":     "authentication authorization",
            "db":       "database",
            "api":      "API endpoint route handler",
            "config":   "configuration settings environment",
            "test":     "test unit test integration test",
            "util":     "utility helper function",
            "middleware": "middleware decorator interceptor",
        }
        words = question.lower().split()
        extras = []
        for word in words:
            stripped = word.strip("?.,!:")
            if stripped in expansions:
                extras.append(expansions[stripped])

        if extras:
            return f"{question} {' '.join(extras)}"
        return question

    def _mmr_compress(
        self, results: list[SearchResult], query_vec: list[float]
    ) -> list[SearchResult]:
        """
        Max Marginal Relevance: balance relevance vs diversity.
        Avoids returning 5 chunks from the same function.
        """
        import numpy as np

        if not results:
            return []

        selected: list[SearchResult] = []
        candidates = sorted(results, key=lambda r: r.score, reverse=True)
        qv = np.array(query_vec)

        while candidates and len(selected) < COMPRESS_TO:
            if not selected:
                selected.append(candidates.pop(0))
                continue

            # Score = relevance - max_similarity_to_already_selected
            best_idx, best_score = 0, -999.0
            for i, cand in enumerate(candidates):
                relevance = cand.score
                # Penalise if same file + close lines
                max_sim = max(
                    self._overlap_penalty(cand, sel) for sel in selected
                )
                mmr_score = 0.7 * relevance - 0.3 * max_sim
                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = i

            selected.append(candidates.pop(best_idx))

        return selected

    @staticmethod
    def _overlap_penalty(a: SearchResult, b: SearchResult) -> float:
        """Returns 1.0 if chunks overlap, 0.0 if different files."""
        if a.file_path != b.file_path:
            return 0.0
        overlap = min(a.end_line, b.end_line) - max(a.start_line, b.start_line)
        return max(0.0, overlap / max(a.end_line - a.start_line + 1, 1))

    def _build_context_blocks(self, results: list[SearchResult]) -> list[str]:
        """Build fenced code blocks with file path header."""
        blocks = []
        for r in results:
            lang = r.language if r.language and r.language != "unknown" else ""
            block = (
                f"### `{r.file_path}` (lines {r.start_line}–{r.end_line})\n"
                f"```{lang}\n{r.content.strip()}\n```"
            )
            blocks.append(block)
        return blocks

    def _build_prompt(self, question: str, context: str, repo_name: str) -> str:
        return f"""You are an expert software engineer analyzing the `{repo_name}` codebase.

INSTRUCTIONS:
- Answer ONLY based on the code context provided below
- Be specific: mention exact function names, class names, file paths, and line numbers
- If the code shows a bug or bad practice, point it out
- Use markdown formatting: **bold** for emphasis, `code` for identifiers
- If you cannot answer from the context, say "The relevant code is not in the provided context"
- End your answer with a "## Summary" section (2 sentences max)

{context}

---

## Question
{question}

## Answer""".strip()

    def _postprocess_answer(self, answer: str) -> str:
        """Clean up LLM output artifacts."""
        # Remove leading/trailing whitespace
        answer = answer.strip()
        # Remove any accidental "## Answer" prefix the LLM might repeat
        if answer.startswith("## Answer"):
            answer = answer[len("## Answer"):].strip()
        return answer

    @staticmethod
    def _cache_key(repo_id: UUID, question: str) -> str:
        h = hashlib.sha256(f"{repo_id}:{question.lower().strip()}".encode()).hexdigest()[:16]
        return f"ra:answer:{h}"
