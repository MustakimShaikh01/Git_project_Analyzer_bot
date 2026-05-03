"use client";
import { useEffect, useState } from "react";
import { listRepos, createRepo, type Repo, logout } from "@/lib/api";
import { useRouter } from "next/navigation";
import Link from "next/link";

export default function DashboardPage() {
  const router = useRouter();
  const [repos, setRepos] = useState<Repo[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const data = await listRepos();
      setRepos(data);
    } catch {
      router.push("/");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  // Poll pending/indexing repos every 5s
  useEffect(() => {
    const pending = repos.some(r => r.status === "pending" || r.status === "indexing");
    if (!pending) return;
    const t = setTimeout(() => load(), 5000);
    return () => clearTimeout(t);
  }, [repos]);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setAdding(true);
    setError(null);
    try {
      await createRepo(url, name);
      setUrl(""); setName(""); setShowAdd(false);
      await load();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setAdding(false);
    }
  }

  const stats = {
    total: repos.length,
    ready: repos.filter(r => r.status === "ready").length,
    totalChunks: repos.reduce((s, r) => s + r.chunk_count, 0),
  };

  return (
    <div className="layout">
      <Sidebar active="dashboard" onLogout={() => { logout(); router.push("/"); }} />

      <main className="main-content">
        <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h2>Dashboard</h2>
            <p>Manage your indexed repositories</p>
          </div>
          <button id="add-repo-btn" className="btn btn-primary" onClick={() => setShowAdd(true)}>
            + Add Repository
          </button>
        </div>

        {/* Stats row */}
        <div style={{ display: "flex", gap: 16, marginBottom: 32 }}>
          {[
            { label: "Repositories", value: stats.total },
            { label: "Ready",       value: stats.ready },
            { label: "Chunks Indexed", value: stats.totalChunks.toLocaleString() },
          ].map(s => (
            <div key={s.label} className="card" style={{ flex: 1 }}>
              <div className="stat-chip">
                <span className="value">{s.value}</span>
                <span className="label">{s.label}</span>
              </div>
            </div>
          ))}
        </div>

        {/* Add repo form */}
        {showAdd && (
          <div className="card" style={{ marginBottom: 24 }}>
            <h3 style={{ marginBottom: 16, fontSize: "1rem", fontWeight: 600 }}>Add Repository</h3>
            <form onSubmit={handleAdd} style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <input id="repo-url" className="input" style={{ flex: 2, minWidth: 200 }} placeholder="https://github.com/user/repo" value={url} onChange={e => setUrl(e.target.value)} required />
              <input id="repo-name" className="input" style={{ flex: 1, minWidth: 140 }} placeholder="Repo name" value={name} onChange={e => setName(e.target.value)} required />
              <button id="repo-submit" className="btn btn-primary" type="submit" disabled={adding}>{adding ? <span className="spinner" /> : "Index →"}</button>
              <button className="btn btn-ghost" type="button" onClick={() => setShowAdd(false)}>Cancel</button>
            </form>
            {error && <div className="error-msg" style={{ marginTop: 12 }}>{error}</div>}
          </div>
        )}

        {/* Repo grid */}
        {loading ? (
          <div className="empty-state"><span className="spinner" style={{ margin: "0 auto" }} /></div>
        ) : repos.length === 0 ? (
          <div className="empty-state">
            <div className="icon">📁</div>
            <p>No repositories yet. Add your first one above.</p>
          </div>
        ) : (
          <div className="repo-grid">
            {repos.map(repo => (
              <Link key={repo.id} href={`/repos/${repo.id}`} style={{ textDecoration: "none" }}>
                <div className="card" style={{ cursor: "pointer" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                    <h3 style={{ fontSize: "0.95rem", fontWeight: 600, color: "var(--text-primary)" }}>{repo.name}</h3>
                    <StatusBadge status={repo.status} />
                  </div>
                  <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: 12, wordBreak: "break-all" }}>{repo.url}</p>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.78rem", color: "var(--text-secondary)" }}>
                    <span>{repo.chunk_count.toLocaleString()} chunks</span>
                    <span>{new Date(repo.created_at).toLocaleDateString()}</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

function StatusBadge({ status }: { status: Repo["status"] }) {
  const icons: Record<Repo["status"], string> = { pending: "⏳", indexing: "🔄", ready: "✅", failed: "❌" };
  return (
    <span className={`badge badge-${status}`}>
      {icons[status]} {status}
    </span>
  );
}

function Sidebar({ active, onLogout }: { active: string; onLogout: () => void }) {
  return (
    <nav className="sidebar">
      <div className="sidebar-logo">
        <h1>⚡ RepoAnalyzer</h1>
        <p>AI Code Intelligence</p>
      </div>
      <Link href="/dashboard" className={`nav-item ${active === "dashboard" ? "active" : ""}`}>🏠 Dashboard</Link>
      <div style={{ flex: 1 }} />
      <button className="nav-item" onClick={onLogout} style={{ border: "none", background: "none", width: "100%", textAlign: "left" }}>
        🚪 Sign Out
      </button>
    </nav>
  );
}
