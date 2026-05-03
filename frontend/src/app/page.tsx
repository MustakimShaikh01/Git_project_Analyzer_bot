"use client";
import { useState } from "react";
import { login, register } from "@/lib/api";
import { useRouter } from "next/navigation";

export default function AuthPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      if (mode === "register") {
        await register(email, password);
        setMode("login");
        setError(null);
        return;
      }
      await login(email, password);
      router.push("/dashboard");
    } catch (err: any) {
      setError(err.message ?? "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-box">
        <div className="auth-logo">
          <h1>⚡ RepoAnalyzer</h1>
          <p>AI-powered code intelligence platform</p>
        </div>

        <div className="card">
          <div style={{ display: "flex", gap: 8, marginBottom: 24 }}>
            {(["login", "register"] as const).map((m) => (
              <button
                key={m}
                className={`btn ${mode === m ? "btn-primary" : "btn-ghost"}`}
                style={{ flex: 1 }}
                onClick={() => { setMode(m); setError(null); }}
              >
                {m === "login" ? "Sign In" : "Create Account"}
              </button>
            ))}
          </div>

          <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div>
              <label style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: 6, display: "block" }}>
                Email
              </label>
              <input
                id="auth-email"
                className="input"
                type="email"
                placeholder="dev@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
            </div>

            <div>
              <label style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: 6, display: "block" }}>
                Password
              </label>
              <input
                id="auth-password"
                className="input"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete={mode === "login" ? "current-password" : "new-password"}
              />
            </div>

            {error && <div className="error-msg">{error}</div>}

            <button id="auth-submit" className="btn btn-primary" type="submit" disabled={loading} style={{ marginTop: 8 }}>
              {loading ? <span className="spinner" /> : mode === "login" ? "Sign In →" : "Create Account →"}
            </button>
          </form>
        </div>

        <p style={{ textAlign: "center", marginTop: 20, fontSize: "0.8rem", color: "var(--text-muted)" }}>
          Multi-tenant · Secure · RAG-powered
        </p>
      </div>
    </main>
  );
}
