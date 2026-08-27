"""Structure-aware chunking for crawled documents (FR-04).

Strategy (per docs/CHUNKING_STRATEGY.md):
  1. Chunk by heading/section first, not by raw character offsets.
  2. Target ~700 tokens per chunk with 100 token overlap.
  3. Oversized sections are token-windowed with overlap; undersized adjacent
     sections are packed together so citations stay meaningful.
  4. Every chunk keeps a parent_id back to the source document, plus enough
     metadata (url, title, section, dates) to cite and re-expand to the parent.
"""

from __future__ import annotations

from dataclasses import dataclass, field

try:
    import tiktoken

    _ENCODING = tiktoken.get_encoding("cl100k_base")
except Exception:  # offline / package missing: fall back to a word-based estimate
    _ENCODING = None

DEFAULT_CHUNK_SIZE = 700
DEFAULT_OVERLAP = 100


def count_tokens(text: str) -> int:
    if _ENCODING is not None:
        return len(_ENCODING.encode(text, disallowed_special=()))
    return max(1, round(len(text.split()) * 1.3))  # rough English tokens-per-word


def _encode(text: str) -> list[int] | list[str]:
    return _ENCODING.encode(text, disallowed_special=()) if _ENCODING else text.split()


def _decode(tokens: list[int] | list[str]) -> str:
    return _ENCODING.decode(tokens) if _ENCODING else " ".join(tokens)


@dataclass
class Section:
    heading: str
    level: int
    text: str


@dataclass
class Chunk:
    chunk_id: str
    parent_id: str
    chunk_index: int
    url: str
    canonical_url: str
    title: str
    section: str
    content: str
    token_count: int
    source_type: str
    content_type: str
    published_at: str = ""
    modified_at: str = ""
    crawled_at: str = ""
    breadcrumbs: list[str] = field(default_factory=list)


def _window_tokens(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split one block of text into overlapping token windows."""
    tokens = _encode(text)
    if len(tokens) <= chunk_size:
        return [text] if text.strip() else []

    step = max(1, chunk_size - overlap)
    windows = []
    for start in range(0, len(tokens), step):
        window = tokens[start : start + chunk_size]
        if not window:
            break
        windows.append(_decode(window))
        if start + chunk_size >= len(tokens):
            break
    return windows


def _pack_sections(
    sections: list[Section], chunk_size: int, overlap: int
) -> list[tuple[str, str]]:
    """Greedily merge small adjacent sections; token-window oversized ones.

    Returns (section_label, content) pairs. The label is the heading the
    chunk starts with, so a citation can point at the right subsection.
    """
    packed: list[tuple[str, str]] = []
    buf_heading, buf_parts, buf_tokens = None, [], 0

    def flush() -> None:
        if buf_parts:
            packed.append((buf_heading or "Overview", "\n\n".join(buf_parts)))
        buf_parts.clear()

    for section in sections:
        tokens = count_tokens(section.text)
        if tokens > chunk_size:
            flush()
            buf_heading, buf_tokens = None, 0
            for window in _window_tokens(section.text, chunk_size, overlap):
                packed.append((section.heading, window))
            continue

        if buf_parts and buf_tokens + tokens > chunk_size:
            flush()
            buf_heading, buf_tokens = None, 0
        if not buf_parts:
            buf_heading = section.heading
        buf_parts.append(f"{section.heading}\n{section.text}" if section.heading else section.text)
        buf_tokens += tokens
    flush()
    return packed


def chunk_document(
    doc: dict,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[Chunk]:
    """Chunk one crawled JSONL document into citation-ready pieces."""
    parent_id = doc.get("id") or doc.get("content_hash", "")[:32]
    raw_sections = doc.get("sections") or []

    if raw_sections:
        sections = [Section(s.get("heading", ""), s.get("level", 0), s.get("text", "")) for s in raw_sections]
        pairs = _pack_sections(sections, chunk_size, overlap)
    else:
        # No structural data (older crawls, or non-HTML assets): fall back to plain windowing.
        text = doc.get("text", "")
        pairs = [(doc.get("title", ""), w) for w in _window_tokens(text, chunk_size, overlap)]

    chunks: list[Chunk] = []
    for index, (section_label, content) in enumerate(pairs):
        if not content.strip():
            continue
        chunks.append(
            Chunk(
                chunk_id=f"{parent_id}_{index}",
                parent_id=parent_id,
                chunk_index=index,
                url=doc.get("url", ""),
                canonical_url=doc.get("canonical_url", "") or doc.get("url", ""),
                title=doc.get("title", ""),
                section=section_label,
                content=content,
                token_count=count_tokens(content),
                source_type=doc.get("source_type", "web_page"),
                content_type=doc.get("content_type", ""),
                published_at=doc.get("published_at", ""),
                modified_at=doc.get("modified_at", ""),
                crawled_at=doc.get("crawled_at", ""),
                breadcrumbs=doc.get("breadcrumbs", []),
            )
        )
    return chunks
