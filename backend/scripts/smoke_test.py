"""
Smoke test — End-to-End Flow Verification (Backend).
This script bypasses external deps (Postgres/Redis/Ollama) using in-memory mocks
to verify the logic, routing, and SSE streaming work correctly as a system.
"""
import json
import time
from uuid import uuid4
from fastapi.testclient import TestClient

# Mock Infrastructure
class FakeDB:
    def __init__(self): self.data = {}
    def save(self, obj): self.data[str(obj.id)] = obj
    def get_by_id(self, _id): return self.data.get(str(_id))
    def list_by_user(self, uid): return [o for o in self.data.values() if getattr(o, 'user_id', None) == uid]
    def get_by_email(self, email): return next((o for o in self.data.values() if getattr(o, 'email', None) == email), None)
    def list_by_user_repo(self, uid, rid): return [o for o in self.data.values() if getattr(o, 'user_id', None) == uid and getattr(o, 'repo_id', None) == rid]

class FakeVector:
    def search(self, **kwargs):
        from app.domain.query import SearchResult
        return [SearchResult(chunk_id=uuid4(), file_path="main.py", start_line=1, end_line=5, content="print('hello')", score=0.99, language="python")]

class FakeEmbed:
    def embed_single(self, t): return [0.1]*384

class FakeLLM:
    def generate(self, p): return "This is a mock answer."
    def stream(self, p):
        for word in ["This", "is", "a", "streaming", "answer."]:
            yield word + " "

# Setup App
from app.interfaces import routes
routes._dispatch_index = lambda x: None  # Mock celery dispatch

from app.interfaces.routes import create_app
db = FakeDB()
app = create_app(
    repo_repository=db,
    user_repository=db,
    query_repository=db,
    vector_store=FakeVector(),
    embedding_service=FakeEmbed(),
    llm_service=FakeLLM(),
    cache=None
)
client = TestClient(app)

def run_smoke_test():
    print("🚀 Starting Smoke Test: Whole Flow Verification\n")

    # 1. Register
    print("Step 1: Registration...", end=" ")
    email = f"user_{int(time.time())}@example.com"
    res = client.post("/auth/register", json={"email": email, "password": "password123"})
    assert res.status_code == 200
    print("✅")

    # 2. Login
    print("Step 2: Login...", end=" ")
    res = client.post("/auth/login", json={"email": email, "password": "password123"})
    assert res.status_code == 200
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("✅")

    # 3. Create Repo
    print("Step 3: Create Repo...", end=" ")
    res = client.post("/repos", json={"url": "https://github.com/test/test", "name": "test-repo"}, headers=headers)
    assert res.status_code == 202
    repo_id = res.json()["repo_id"]
    print(f"✅ (ID: {repo_id[:8]}...)")

    # 4. Mock Indexing (Force mark as READY)
    print("Step 4: Indexing (Simulated)...", end=" ")
    repo = db.get_by_id(repo_id)
    repo.mark_ready(chunk_count=10)
    db.save(repo)
    print("✅ (Status: READY)")

    # 5. Query (Blocking)
    print("Step 5: Blocking Query...", end=" ")
    res = client.post(f"/repos/{repo_id}/query", json={"question": "What is this?"}, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert len(data["citations"]) > 0
    print("✅")

    # 6. Query (Streaming - THE COOL PART)
    print("Step 6: Streaming SSE Query...", end=" ")
    with client.stream("POST", f"/repos/{repo_id}/query/stream", json={"question": "How it works?"}, headers=headers) as sse:
        assert sse.status_code == 200
        full_text = ""
        citation_found = False
        for line in sse.iter_lines():
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                if payload["type"] == "token":
                    full_text += payload["text"]
                if payload["type"] == "citations":
                    citation_found = True
        assert len(full_text) > 0
        assert citation_found
    print("✅ (Answer received token-by-token)")

    print("\n🎉 SMOKE TEST PASSED: WHOLE FLOW VERIFIED")

if __name__ == "__main__":
    run_smoke_test()
