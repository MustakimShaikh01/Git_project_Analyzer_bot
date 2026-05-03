"""
=== UNIT TESTS — TDD first, implementation follows ===

Run: pytest tests/ -v
"""
import pytest
from uuid import uuid4
from datetime import datetime

from app.domain.repo import Repo, RepoStatus
from app.domain.user import User
from app.domain.query import QueryRecord, SearchResult
from app.application.chunk_text import chunk_text, chunk_code_file


# ─────────────────────────────────────────────────────────────
# Domain: Repo entity
# ─────────────────────────────────────────────────────────────

class TestRepoDomain:
    def test_create_sets_pending_status(self):
        repo = Repo.create(uuid4(), "https://github.com/foo/bar", "bar")
        assert repo.status == RepoStatus.PENDING

    def test_mark_indexing(self):
        repo = Repo.create(uuid4(), "https://github.com/foo/bar", "bar")
        repo.mark_indexing()
        assert repo.status == RepoStatus.INDEXING

    def test_mark_ready(self):
        repo = Repo.create(uuid4(), "https://github.com/foo/bar", "bar")
        repo.mark_ready(chunk_count=42)
        assert repo.status == RepoStatus.READY
        assert repo.chunk_count == 42
        assert repo.is_queryable() is True

    def test_mark_failed(self):
        repo = Repo.create(uuid4(), "https://github.com/foo/bar", "bar")
        repo.mark_failed("connection refused")
        assert repo.status == RepoStatus.FAILED
        assert repo.error_message == "connection refused"
        assert repo.is_queryable() is False

    def test_pending_not_queryable(self):
        repo = Repo.create(uuid4(), "https://github.com/foo/bar", "bar")
        assert repo.is_queryable() is False


# ─────────────────────────────────────────────────────────────
# Domain: User entity
# ─────────────────────────────────────────────────────────────

class TestUserDomain:
    def test_create_user(self):
        user = User.create("Test@Example.com", "SuperSecret123")
        assert user.email == "test@example.com"  # normalized
        assert user.is_active is True

    def test_verify_correct_password(self):
        user = User.create("user@example.com", "password123")
        assert user.verify_password("password123") is True

    def test_reject_wrong_password(self):
        user = User.create("user@example.com", "password123")
        assert user.verify_password("wrong") is False

    def test_different_users_different_hashes(self):
        u1 = User.create("a@b.com", "same")
        u2 = User.create("c@d.com", "same")
        assert u1.hashed_password != u2.hashed_password  # different salts


# ─────────────────────────────────────────────────────────────
# Application: chunk_text  ← THE KEY TDD EXAMPLE
# ─────────────────────────────────────────────────────────────

class TestChunkText:
    def test_empty_string_returns_empty_list(self):
        assert chunk_text("") == []

    def test_short_text_single_chunk(self):
        text = "hello world"
        chunks = chunk_text(text, max_size=400)
        assert chunks == ["hello world"]

    def test_large_text_multiple_chunks(self):
        """THE example from the spec."""
        text = "a" * 1000
        chunks = chunk_text(text)
        assert len(chunks) > 1
        assert all(len(c) <= 400 for c in chunks)

    def test_overlap_maintained(self):
        text = "a" * 800
        chunks = chunk_text(text, max_size=400, overlap=50)
        # At boundary: chunk 0 ends at 400, chunk 1 starts at 350
        # → they share 50 characters
        assert chunks[0][-50:] == chunks[1][:50]

    def test_idempotent(self):
        text = "x" * 500
        assert chunk_text(text) == chunk_text(text)

    def test_exact_max_size_no_split(self):
        text = "b" * 400
        chunks = chunk_text(text, max_size=400)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_code_file_returns_line_info(self):
        source = "def foo():\n    pass\n" * 50
        chunks = chunk_code_file(source)
        assert all("start_line" in c for c in chunks)
        assert all("end_line" in c for c in chunks)
        assert all(c["start_line"] >= 1 for c in chunks)


# ─────────────────────────────────────────────────────────────
# Application: QueryRepo use case (unit, mock dependencies)
# ─────────────────────────────────────────────────────────────

class TestQueryRepoUseCase:
    def _make_use_case(self, repo, answer="TEST_ANSWER"):
        from app.application.query_repo import QueryRepoUseCase
        from app.domain.query import SearchResult
        from uuid import uuid4

        class FakeRepoRepo:
            def get_by_id(self, _id):
                return repo

        class FakeQueryRepo:
            def __init__(self):
                self.saved = []
            def save(self, record):
                self.saved.append(record)
            def list_by_user_repo(self, *_):
                return self.saved

        class FakeVectorStore:
            def search(self, repo_id, query_embedding, top_k):
                return [
                    SearchResult(
                        chunk_id=uuid4(),
                        file_path="src/main.py",
                        start_line=1,
                        end_line=10,
                        content="def main(): pass",
                        score=0.95,
                    )
                ]

        class FakeEmbedder:
            def embed_single(self, text):
                return [0.1] * 384

        class FakeLLM:
            def generate(self, prompt):
                return answer

        fake_query_repo = FakeQueryRepo()
        uc = QueryRepoUseCase(
            repo_repository=FakeRepoRepo(),
            query_repository=fake_query_repo,
            vector_store=FakeVectorStore(),
            embedding_service=FakeEmbedder(),
            llm_service=FakeLLM(),
        )
        return uc, fake_query_repo

    def test_query_returns_answer(self):
        user_id = uuid4()
        repo = Repo.create(user_id, "https://github.com/x/y", "y")
        repo.mark_ready(100)
        uc, _ = self._make_use_case(repo, answer="42 is the answer")
        result = uc.execute(user_id, repo.id, "What is the answer?")
        assert result["answer"] == "42 is the answer"

    def test_query_returns_citations(self):
        user_id = uuid4()
        repo = Repo.create(user_id, "https://github.com/x/y", "y")
        repo.mark_ready(100)
        uc, _ = self._make_use_case(repo)
        result = uc.execute(user_id, repo.id, "anything")
        assert len(result["citations"]) > 0
        assert "src/main.py" == result["citations"][0]["file"]

    def test_query_persists_record(self):
        user_id = uuid4()
        repo = Repo.create(user_id, "https://github.com/x/y", "y")
        repo.mark_ready(100)
        uc, query_repo = self._make_use_case(repo)
        uc.execute(user_id, repo.id, "anything")
        assert len(query_repo.saved) == 1

    def test_query_raises_on_non_ready_repo(self):
        user_id = uuid4()
        repo = Repo.create(user_id, "https://github.com/x/y", "y")
        # status stays PENDING
        uc, _ = self._make_use_case(repo)
        with pytest.raises(ValueError, match="not ready"):
            uc.execute(user_id, repo.id, "anything")

    def test_query_raises_on_wrong_user(self):
        owner_id = uuid4()
        attacker_id = uuid4()
        repo = Repo.create(owner_id, "https://github.com/x/y", "y")
        repo.mark_ready(100)
        uc, _ = self._make_use_case(repo)
        with pytest.raises(PermissionError):
            uc.execute(attacker_id, repo.id, "anything")

    def test_latency_ms_in_result(self):
        user_id = uuid4()
        repo = Repo.create(user_id, "https://github.com/x/y", "y")
        repo.mark_ready(100)
        uc, _ = self._make_use_case(repo)
        result = uc.execute(user_id, repo.id, "?")
        assert "latency_ms" in result
        assert result["latency_ms"] >= 0


# ─────────────────────────────────────────────────────────────
# Application: AnalyzeRepo use case (unit, mock dependencies)
# ─────────────────────────────────────────────────────────────

class TestAnalyzeRepoUseCase:
    def _make_use_case(self, repo, clone_fails=False):
        from app.application.analyze_repo import AnalyzeRepoUseCase

        class FakeRepoRepo:
            def __init__(self):
                self._repo = repo
                self.saved = []
            def get_by_id(self, _id):
                return self._repo
            def save(self, r):
                self.saved.append(r.status)

        class FakeVectorStore:
            def __init__(self):
                self.upserted = False
            def upsert(self, *_):
                self.upserted = True

        class FakeEmbedder:
            def embed_batch(self, texts):
                return [[0.1] * 384 for _ in texts]

        class FakeStorage:
            def upload_chunks(self, *_):
                pass

        fake_repo_repo = FakeRepoRepo()
        fake_vector_store = FakeVectorStore()

        uc = AnalyzeRepoUseCase(
            repo_repository=fake_repo_repo,
            vector_store=fake_vector_store,
            embedding_service=FakeEmbedder(),
            storage_service=FakeStorage(),
        )
        # Monkey-patch clone so the test doesn't hit the network
        if clone_fails:
            uc._clone_repo = lambda url, d: (_ for _ in ()).throw(
                RuntimeError("git clone failed: no network")
            )
        else:
            import tempfile, os, pathlib
            def fake_clone(url, target_dir):
                # Create a small synthetic repo
                p = pathlib.Path(target_dir) / "main.py"
                p.write_text("def hello():\n    print('hi')\n")
            uc._clone_repo = fake_clone

        return uc, fake_repo_repo, fake_vector_store

    def test_successful_indexing_marks_ready(self):
        user_id = uuid4()
        repo = Repo.create(user_id, "https://github.com/x/y", "y")
        uc, repo_repo, _ = self._make_use_case(repo)
        uc.execute(repo.id)
        assert RepoStatus.READY in repo_repo.saved

    def test_failure_marks_failed(self):
        user_id = uuid4()
        repo = Repo.create(user_id, "https://github.com/x/y", "y")
        uc, repo_repo, _ = self._make_use_case(repo, clone_fails=True)
        with pytest.raises(RuntimeError):
            uc.execute(repo.id)
        assert RepoStatus.FAILED in repo_repo.saved

    def test_vector_store_called_on_success(self):
        user_id = uuid4()
        repo = Repo.create(user_id, "https://github.com/x/y", "y")
        uc, _, vector_store = self._make_use_case(repo)
        uc.execute(repo.id)
        assert vector_store.upserted is True
