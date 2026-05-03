/**
 * Premium streaming chat interface for RepoAnalyzer.
 * Features:
 *  - Server-Sent Events streaming (tokens appear word-by-word)
 *  - Markdown rendering with syntax highlighting
 *  - Citation cards with file + line number
 *  - Copy button on code blocks
 *  - Suggested questions
 *  - Keyboard shortcut (Cmd/Ctrl+Enter)
 *  - Auto-scroll
 *  - Cache hit indicator
 */
"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getRepo, getQueryHistory, logout, type Repo } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ─── Types ───────────────────────────────────────────────────────────────────

interface Citation {
  file: string;
  line: number;
  language: string;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  latency_ms?: number;
  cache_hit?: boolean;
  streaming?: boolean;
}

// ─── Suggested questions per language ────────────────────────────────────────

const SUGGESTIONS = [
  "How is authentication implemented?",
  "What is the main entry point?",
  "How are errors handled?",
  "What does the data model look like?",
  "Where is the database connection configured?",
  "How is routing structured?",
];

// ─── Code block with copy button ─────────────────────────────────────────────

function CodeBlock({ children, className }: { children?: React.ReactNode; className?: string }) {
  const [copied, setCopied] = useState(false);
  const lang = className?.replace("language-", "") ?? "";
  const code = String(children).trim();

  function copy() {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div style={{ position: "relative", margin: "12px 0" }}>
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        background: "#0d0d14",
        borderRadius: "8px 8px 0 0",
        padding: "6px 14px",
        borderBottom: "1px solid rgba(99,102,241,0.2)",
      }}>
        <span style={{ fontSize: "0.72rem", color: "#64748b", fontFamily: "JetBrains Mono, monospace" }}>
          {lang || "code"}
        </span>
        <button
          onClick={copy}
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            color: copied ? "#10b981" : "#64748b",
            fontSize: "0.72rem",
            padding: "2px 8px",
          }}
        >
          {copied ? "✓ Copied" : "Copy"}
        </button>
      </div>
      <pre style={{
        margin: 0,
        padding: "16px",
        background: "#0d0d14",
        borderRadius: "0 0 8px 8px",
        overflowX: "auto",
        fontSize: "0.82rem",
        lineHeight: 1.65,
        fontFamily: "JetBrains Mono, monospace",
        color: "#e2e8f0",
      }}>
        <code>{code}</code>
      </pre>
    </div>
  );
}

// ─── Markdown renderer ────────────────────────────────────────────────────────

function MarkdownContent({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        code({ node, className, children, ...props }: any) {
          const isBlock = className?.startsWith("language-");
          if (isBlock) {
            return <CodeBlock className={className}>{children}</CodeBlock>;
          }
          return (
            <code style={{
              background: "rgba(99,102,241,0.15)",
              color: "#818cf8",
              padding: "2px 6px",
              borderRadius: "4px",
              fontSize: "0.85em",
              fontFamily: "JetBrains Mono, monospace",
            }} {...props}>{children}</code>
          );
        },
        p: ({ children }) => (
          <p style={{ margin: "8px 0", lineHeight: 1.75 }}>{children}</p>
        ),
        h2: ({ children }) => (
          <h2 style={{
            fontSize: "1rem",
            fontWeight: 700,
            margin: "16px 0 8px",
            color: "#f1f5f9",
            borderBottom: "1px solid rgba(99,102,241,0.2)",
            paddingBottom: "4px",
          }}>{children}</h2>
        ),
        h3: ({ children }) => (
          <h3 style={{ fontSize: "0.9rem", fontWeight: 600, margin: "12px 0 6px", color: "#cbd5e1" }}>{children}</h3>
        ),
        strong: ({ children }) => (
          <strong style={{ color: "#e2e8f0", fontWeight: 700 }}>{children}</strong>
        ),
        ul: ({ children }) => (
          <ul style={{ paddingLeft: "20px", margin: "8px 0" }}>{children}</ul>
        ),
        li: ({ children }) => (
          <li style={{ margin: "4px 0", lineHeight: 1.7 }}>{children}</li>
        ),
        blockquote: ({ children }) => (
          <blockquote style={{
            borderLeft: "3px solid var(--accent)",
            paddingLeft: "12px",
            margin: "12px 0",
            color: "#94a3b8",
            fontStyle: "italic",
          }}>{children}</blockquote>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

// ─── Citation card ────────────────────────────────────────────────────────────

function CitationCard({ citation }: { citation: Citation }) {
  const parts = citation.file.split("/");
  const filename = parts[parts.length - 1];
  const dir = parts.slice(0, -1).join("/");

  return (
    <div style={{
      display: "inline-flex",
      alignItems: "center",
      gap: "6px",
      padding: "4px 10px",
      background: "rgba(16,185,129,0.08)",
      border: "1px solid rgba(16,185,129,0.25)",
      borderRadius: "6px",
      cursor: "default",
      transition: "all 0.15s ease",
    }}
      title={citation.file}
    >
      <span style={{ color: "#10b981", fontSize: "0.7rem" }}>📍</span>
      <span style={{
        fontFamily: "JetBrains Mono, monospace",
        fontSize: "0.72rem",
        color: "#94a3b8",
      }}>
        {dir && <span style={{ opacity: 0.6 }}>{dir}/</span>}
        <span style={{ color: "#10b981", fontWeight: 600 }}>{filename}</span>
        <span style={{ color: "#64748b" }}>:{citation.line}</span>
      </span>
    </div>
  );
}

// ─── Message bubble ───────────────────────────────────────────────────────────

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  return (
    <div style={{
      display: "flex",
      gap: "12px",
      alignItems: "flex-start",
      animation: "slideUp 0.2s ease",
    }}>
      {/* Avatar */}
      <div style={{
        width: 36,
        height: 36,
        borderRadius: "50%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: "1rem",
        flexShrink: 0,
        background: isUser
          ? "linear-gradient(135deg, #6366f1, #4f46e5)"
          : "linear-gradient(135deg, #10b981, #059669)",
      }}>
        {isUser ? "👤" : "🤖"}
      </div>

      {/* Content */}
      <div style={{ flex: 1, maxWidth: "820px" }}>
        <div style={{
          padding: "14px 18px",
          borderRadius: "12px",
          fontSize: "0.9rem",
          lineHeight: 1.7,
          background: isUser
            ? "rgba(99,102,241,0.1)"
            : "var(--bg-card)",
          border: `1px solid ${isUser ? "rgba(99,102,241,0.3)" : "var(--border)"}`,
          color: "var(--text-primary)",
        }}>
          {isUser ? (
            <p style={{ margin: 0 }}>{message.content}</p>
          ) : message.streaming ? (
            <div>
              <MarkdownContent content={message.content} />
              <span style={{
                display: "inline-block",
                width: 8,
                height: 16,
                background: "#6366f1",
                borderRadius: 2,
                marginLeft: 2,
                animation: "blink 1s steps(1) infinite",
              }} />
            </div>
          ) : (
            <MarkdownContent content={message.content} />
          )}
        </div>

        {/* Citations */}
        {message.citations && message.citations.length > 0 && !message.streaming && (
          <div style={{
            marginTop: "8px",
            display: "flex",
            flexWrap: "wrap",
            gap: "6px",
          }}>
            {message.citations.map((c, i) => (
              <CitationCard key={i} citation={c} />
            ))}
          </div>
        )}

        {/* Meta row */}
        {!isUser && !message.streaming && (
          <div style={{
            marginTop: "6px",
            display: "flex",
            gap: "12px",
            alignItems: "center",
          }}>
            {message.latency_ms !== undefined && (
              <span style={{ fontSize: "0.72rem", color: "#475569" }}>
                ⚡ {message.latency_ms}ms
              </span>
            )}
            {message.cache_hit && (
              <span style={{
                fontSize: "0.72rem",
                color: "#10b981",
                background: "rgba(16,185,129,0.1)",
                padding: "1px 8px",
                borderRadius: "99px",
              }}>
                ✓ cache
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Typing dots ─────────────────────────────────────────────────────────────
function TypingIndicator() {
  return (
    <div style={{ display: "flex", gap: "12px", alignItems: "flex-start" }}>
      <div style={{
        width: 36, height: 36, borderRadius: "50%",
        background: "linear-gradient(135deg, #10b981, #059669)",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>🤖</div>
      <div style={{
        padding: "14px 18px",
        borderRadius: "12px",
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        display: "flex",
        gap: "5px",
        alignItems: "center",
      }}>
        {[0, 150, 300].map(delay => (
          <span key={delay} style={{
            width: 7, height: 7, borderRadius: "50%",
            background: "#6366f1",
            animation: `bounce 1s ${delay}ms ease infinite`,
            display: "inline-block",
          }} />
        ))}
      </div>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function RepoPage() {
  const router = useRouter();
  const params = useParams();
  const repoId = params?.repoId as string;

  const [repo, setRepo] = useState<Repo | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Load repo + history
  useEffect(() => {
    async function init() {
      try {
        const r = await getRepo(repoId);
        setRepo(r);
        const history = await getQueryHistory(repoId);
        const msgs: Message[] = history.flatMap<Message>(h => [
          { id: `h-q-${h.id}`, role: "user", content: h.question },
          {
            id: `h-a-${h.id}`,
            role: "assistant",
            content: h.answer,
            latency_ms: h.latency_ms,
          },
        ]);
        setMessages(msgs);
      } catch {
        router.push("/dashboard");
      }
    }
    init();
  }, [repoId]);

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  // Streaming send
  const send = useCallback(async (q: string) => {
    if (!q.trim() || streaming) return;
    setStreaming(true);
    setError(null);

    const userMsg: Message = { id: `u-${Date.now()}`, role: "user", content: q };
    const assistantId = `a-${Date.now()}`;
    const assistantMsg: Message = {
      id: assistantId,
      role: "assistant",
      content: "",
      streaming: true,
    };

    setMessages(prev => [...prev, userMsg, assistantMsg]);
    setQuestion("");

    const token = localStorage.getItem("token");

    try {
      const res = await fetch(`${API_URL}/repos/${repoId}/query/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ question: q }),
      });

      if (!res.ok) {
        throw new Error(`Error ${res.status}`);
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let citations: Citation[] = [];
      let latency_ms: number | undefined;
      let cache_hit = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value, { stream: true });
        const lines = text.split("\n");

        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          const payload = line.slice(5).trim();
          if (!payload || payload === "[DONE]") continue;

          try {
            const chunk = JSON.parse(payload);

            if (chunk.type === "token") {
              setMessages(prev =>
                prev.map(m =>
                  m.id === assistantId
                    ? { ...m, content: m.content + chunk.text }
                    : m
                )
              );
            } else if (chunk.type === "citations") {
              citations = chunk.citations;
            } else if (chunk.type === "answer") {
              // cache hit — full answer at once
              cache_hit = true;
              setMessages(prev =>
                prev.map(m =>
                  m.id === assistantId ? { ...m, content: chunk.text } : m
                )
              );
            } else if (chunk.type === "done") {
              latency_ms = chunk.latency_ms;
            } else if (chunk.type === "error") {
              setError(chunk.message);
            }
          } catch {
            // non-JSON line
          }
        }
      }

      // Finalise message
      setMessages(prev =>
        prev.map(m =>
          m.id === assistantId
            ? { ...m, streaming: false, citations, latency_ms, cache_hit }
            : m
        )
      );
    } catch (err: any) {
      setError(err.message ?? "Request failed");
      setMessages(prev => prev.filter(m => m.id !== assistantId));
    } finally {
      setStreaming(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [repoId, streaming]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    send(question);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      send(question);
    }
  }

  if (!repo) {
    return (
      <div className="layout">
        <Sidebar onLogout={() => { logout(); router.push("/"); }} />
        <main className="main-content">
          <div className="empty-state"><span className="spinner" style={{ margin: "0 auto" }} /></div>
        </main>
      </div>
    );
  }

  const isReady = repo.status === "ready";

  return (
    <div className="layout">
      <Sidebar onLogout={() => { logout(); router.push("/"); }} />

      <main className="main-content" style={{ display: "flex", flexDirection: "column", padding: "24px 32px" }}>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20, flexShrink: 0 }}>
          <Link href="/dashboard" style={{ color: "var(--text-muted)", fontSize: "0.85rem", textDecoration: "none" }}>
            ← Dashboard
          </Link>
          <span style={{ color: "var(--border)" }}>/</span>
          <span style={{ fontWeight: 700, color: "var(--text-primary)" }}>{repo.name}</span>
          <span className={`badge badge-${repo.status}`} style={{ marginLeft: 4 }}>{repo.status}</span>
          {isReady && (
            <span style={{ marginLeft: "auto", fontSize: "0.78rem", color: "var(--text-muted)" }}>
              {repo.chunk_count.toLocaleString()} chunks indexed
            </span>
          )}
        </div>

        {!isReady ? (
          <div className="empty-state">
            <div className="icon">{repo.status === "failed" ? "❌" : "⏳"}</div>
            <p>
              {repo.status === "failed"
                ? `Indexing failed: ${repo.error_message}`
                : "Repository is being indexed — this may take a few minutes…"}
            </p>
            {repo.status !== "failed" && (
              <div style={{ marginTop: 24 }}>
                <span className="spinner" style={{ margin: "0 auto" }} />
              </div>
            )}
          </div>
        ) : (

          <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>

            {/* Messages */}
            <div style={{
              flex: 1,
              overflowY: "auto",
              paddingRight: "4px",
              display: "flex",
              flexDirection: "column",
              gap: "20px",
              paddingBottom: "16px",
            }}>
              {messages.length === 0 && (
                <div style={{ textAlign: "center", paddingTop: "48px" }}>
                  <div style={{ fontSize: "2.5rem", marginBottom: "12px" }}>💬</div>
                  <p style={{ color: "var(--text-secondary)", marginBottom: "24px", fontSize: "0.95rem" }}>
                    Ask anything about <strong>{repo.name}</strong>
                  </p>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", justifyContent: "center", maxWidth: "640px", margin: "0 auto" }}>
                    {SUGGESTIONS.map(s => (
                      <button
                        key={s}
                        className="btn btn-ghost"
                        style={{ fontSize: "0.8rem", padding: "8px 14px" }}
                        onClick={() => send(s)}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map(msg => (
                <MessageBubble key={msg.id} message={msg} />
              ))}

              {streaming && messages[messages.length - 1]?.role !== "assistant" && (
                <TypingIndicator />
              )}

              <div ref={bottomRef} />
            </div>

            {/* Error */}
            {error && (
              <div className="error-msg" style={{ marginBottom: "12px", flexShrink: 0 }}>
                {error}
              </div>
            )}

            {/* Input */}
            <div style={{
              flexShrink: 0,
              borderTop: "1px solid var(--border)",
              paddingTop: "16px",
            }}>
              <form onSubmit={handleSubmit}>
                <div style={{
                  display: "flex",
                  gap: "10px",
                  alignItems: "flex-end",
                  background: "var(--bg-card)",
                  border: "1px solid var(--border)",
                  borderRadius: "14px",
                  padding: "10px 14px",
                  transition: "border-color 0.2s ease",
                }}>
                  <textarea
                    id="chat-input"
                    ref={inputRef}
                    rows={1}
                    placeholder="Ask about this codebase…   (⌘+Enter to send)"
                    value={question}
                    onChange={e => {
                      setQuestion(e.target.value);
                      // Auto-resize
                      e.target.style.height = "auto";
                      e.target.style.height = Math.min(e.target.scrollHeight, 140) + "px";
                    }}
                    onKeyDown={handleKeyDown}
                    disabled={streaming}
                    style={{
                      flex: 1,
                      background: "none",
                      border: "none",
                      color: "var(--text-primary)",
                      fontSize: "0.9rem",
                      fontFamily: "Inter, sans-serif",
                      lineHeight: 1.6,
                      resize: "none",
                      outline: "none",
                      overflowY: "hidden",
                    }}
                  />
                  <button
                    id="chat-send"
                    type="submit"
                    disabled={streaming || !question.trim()}
                    style={{
                      width: 38,
                      height: 38,
                      borderRadius: "10px",
                      border: "none",
                      background: streaming || !question.trim()
                        ? "rgba(99,102,241,0.3)"
                        : "linear-gradient(135deg, #6366f1, #4f46e5)",
                      color: "#fff",
                      cursor: streaming || !question.trim() ? "not-allowed" : "pointer",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: "1rem",
                      transition: "all 0.2s ease",
                      flexShrink: 0,
                    }}
                  >
                    {streaming ? <span className="spinner" /> : "↑"}
                  </button>
                </div>
                <p style={{
                  textAlign: "center",
                  marginTop: "8px",
                  fontSize: "0.72rem",
                  color: "var(--text-muted)",
                }}>
                  Answers grounded in your codebase · Citations show exact files + lines
                </p>
              </form>
            </div>
          </div>
        )}
      </main>

      <style>{`
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
        @keyframes bounce {
          0%,100%{transform:translateY(0)}
          50%{transform:translateY(-6px)}
        }
        @keyframes slideUp {
          from{opacity:0;transform:translateY(6px)}
          to{opacity:1;transform:translateY(0)}
        }
      `}</style>
    </div>
  );
}

function Sidebar({ onLogout }: { onLogout: () => void }) {
  return (
    <nav className="sidebar">
      <div className="sidebar-logo">
        <h1>⚡ RepoAnalyzer</h1>
        <p>AI Code Intelligence</p>
      </div>
      <Link href="/dashboard" className="nav-item">🏠 Dashboard</Link>
      <div style={{ flex: 1 }} />
      <button
        className="nav-item"
        onClick={onLogout}
        style={{ border: "none", background: "none", width: "100%", textAlign: "left" }}
      >
        🚪 Sign Out
      </button>
    </nav>
  );
}
