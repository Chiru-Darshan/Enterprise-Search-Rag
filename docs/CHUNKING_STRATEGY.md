# Chunking Strategy (FR-04)

Implements structure-aware, heading-based chunking with parent-child metadata, per the
recommended enterprise pattern (Glean/Elastic AI Search/Copilot-style RAG).

## Why not fixed-size chunking

Splitting by raw character/token count (e.g. every 1000 characters) ignores document
structure: `Section A | Section B | Section C` can land in one chunk, or one section can be
split mid-sentence across two. Retrieval becomes noisy and citations point at the wrong
subsection. Heading-aware chunking keeps "How do I export data to Tableau?" mapped to the
*Export Procedure* section, not the whole page.

## Pipeline

```
Web Page → HTML Cleanup → Heading Extraction → Sections → Pack/Window → Chunks → Embeddings
```

1. **`crawler/extract.py`** walks the cleaned main content in document order and groups
   block text (`p`, `li`, `td`, `th`, `blockquote`, ...) under its nearest preceding
   heading (`h1`–`h6`), producing `Page.sections: list[Section(heading, level, text)]`.
   This is written to each crawled document as `"sections"`.
2. **`crawler/chunking.py`** consumes `sections` and:
   - **Packs** small adjacent sections together up to `chunk_size` tokens, so a chunk isn't
     wastefully small (e.g. a 3-line "Find Account Information" section).
   - **Token-windows** any section that exceeds `chunk_size` on its own, using a sliding
     window with `chunk_overlap` tokens of overlap (via `tiktoken`, `cl100k_base`).
   - Falls back to plain token-windowing over `text` when a document has no `sections`
     (older crawls, or non-HTML assets like extracted PDFs).
3. **`chunk_corpus.py`** is the CLI that reads `documents_*.jsonl`, chunks every document,
   and writes `chunks_<timestamp>.jsonl`.

## Settings

```yaml
chunking:
  strategy: structure-aware
  chunk_size: 700     # tokens
  chunk_overlap: 100  # tokens
```

`700/100` was chosen to keep each chunk large enough to be self-contained (a full
"how-to" subsection) while staying well under typical embedding context limits, with
overlap sized to avoid losing a sentence that straddles a window boundary.

## Chunk schema

```json
{
  "chunk_id": "44e1a5f4564a835cff8ca1e0261b136f_0",
  "parent_id": "44e1a5f4564a835cff8ca1e0261b136f",
  "chunk_index": 0,
  "url": "https://docs.searchunify.com/Content/AB_Test/A-B_Test.htm",
  "canonical_url": "https://docs.searchunify.com/Content/AB_Test/A-B_Test.htm",
  "title": "A/B Test Overview",
  "section": "A/B Test Overview",
  "content": "A/B Test Overview\nA/B Testing is a controlled...",
  "token_count": 290,
  "source_type": "web_page",
  "content_type": "text/html",
  "published_at": "",
  "modified_at": "2026-06-05T14:30:00Z",
  "crawled_at": "2026-08-26T22:27:56+00:00",
  "breadcrumbs": ["Home", "Docs", "A/B Test"]
}
```

`parent_id` + `chunk_index` support parent-document expansion at retrieval time (find the
best chunk, then optionally pull sibling chunks or the full parent for extra context).
`section`, `url`, and `modified_at` are what citations are built from.

## Usage

```bash
# Chunk everything under data/searchunify/documents_*.jsonl
python chunk_corpus.py data/searchunify --chunk-size 700 --overlap 100

# Output: data/searchunify/chunks_<timestamp>.jsonl
```

## Important: existing corpus needs a re-crawl

`sections` is new. Documents crawled **before** this change have no `"sections"` field, so
`chunk_corpus.py` falls back to plain token-windowing for them (still correct, just not
heading-aware — verified: 2,076 docs / 3,889 chunks, median 652 tokens, all fallback).

To get structure-aware chunks for the whole corpus, re-crawl with `--full`:

```bash
python -m crawler --config config/searchunify.yaml --full
python chunk_corpus.py data/searchunify --chunk-size 700 --overlap 100
```

## Validated behavior

- Short docs-portal pages (5 sections, ~290 tokens total) pack into a **single** chunk
  instead of being split unnecessarily.
- A 1,225-token conceptual page with 10 sections split into **7 chunks** at
  `chunk_size=250`, each chunk's `section` label matching its true heading
  ("What is A/B Test", "Benefits of A/B Test", "Creating a new A/B Test", ...).
