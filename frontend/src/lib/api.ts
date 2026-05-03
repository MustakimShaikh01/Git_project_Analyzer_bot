/**
 * Global API client — wraps all backend calls.
 * Automatically attaches Bearer token from localStorage.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...((options.headers as object) || {}),
  };

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error?.detail ?? "Request failed");
  }
  return res.json();
}

// ── Auth ─────────────────────────────────────────────────────────────────────

export async function register(email: string, password: string) {
  return request<{ user_id: string }>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function login(email: string, password: string) {
  const data = await request<{ access_token: string; token_type: string }>(
    "/auth/login",
    { method: "POST", body: JSON.stringify({ email, password }) }
  );
  localStorage.setItem("token", data.access_token);
  return data;
}

export function logout() {
  localStorage.removeItem("token");
}

// ── Repos ─────────────────────────────────────────────────────────────────────

export interface Repo {
  id: string;
  name: string;
  url: string;
  status: "pending" | "indexing" | "ready" | "failed";
  chunk_count: number;
  created_at: string;
  error_message?: string;
}

export async function createRepo(url: string, name: string) {
  return request<{ repo_id: string; status: string }>("/repos", {
    method: "POST",
    body: JSON.stringify({ url, name }),
  });
}

export async function listRepos() {
  return request<Repo[]>("/repos");
}

export async function getRepo(repoId: string) {
  return request<Repo>(`/repos/${repoId}`);
}

// ── Query ─────────────────────────────────────────────────────────────────────

export interface QueryResult {
  answer: string;
  citations: string[];
  latency_ms: number;
}

export async function queryRepo(repoId: string, question: string) {
  return request<QueryResult>(`/repos/${repoId}/query`, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

export interface HistoryRecord {
  id: string;
  question: string;
  answer: string;
  latency_ms: number;
  created_at: string;
}

export async function getQueryHistory(repoId: string) {
  return request<HistoryRecord[]>(`/repos/${repoId}/history`);
}
