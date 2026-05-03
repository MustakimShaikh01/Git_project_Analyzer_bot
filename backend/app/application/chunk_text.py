"""
Application service – Text chunking utility.
CRITICAL: Tested first (TDD), then implemented.
"""
from __future__ import annotations


def chunk_text(text: str, max_size: int = 400, overlap: int = 50) -> list[str]:
    """
    Split *text* into overlapping chunks of at most *max_size* characters.

    Design rationale:
    - overlap keeps semantic continuity across chunk boundaries
    - deterministic: same input → same output (idempotent)
    - no external dependencies
    """
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    length = len(text)

    while start < length:
        end = min(start + max_size, length)
        chunks.append(text[start:end])
        if end == length:
            break
        start = end - overlap  # slide back for overlap

    return chunks


def chunk_code_file(source: str, language: str = "python") -> list[dict]:
    """
    Higher-level chunker that preserves line information.
    Returns list of dicts with content, start_line, end_line.
    """
    lines = source.splitlines(keepends=True)
    raw = "".join(lines)
    text_chunks = chunk_text(raw)

    result = []
    cumulative = 0
    for chunk in text_chunks:
        start_char = raw.find(chunk, cumulative)
        before = raw[:start_char]
        start_line = before.count("\n") + 1
        end_line = start_line + chunk.count("\n")
        result.append(
            {
                "content": chunk,
                "start_line": start_line,
                "end_line": end_line,
                "language": language,
            }
        )
        cumulative = start_char + len(chunk) - 50  # account for overlap

    return result
