# SearchUnify Corpus Analysis Report

**Generated:** 2026-08-26 (35-minute full crawl)

## Executive Summary

A clean, focused corpus of **2,084 documents** (1.35M words) covering SearchUnify's product, competitive landscape, and company information. Spans marketing content, technical documentation, APIs, and linked PDFs. Strong freshness (86% published 2025–2026) and near-complete coverage of documented content.

---

## Crawl Results

| Metric | Value |
|--------|-------|
| **Documents indexed** | 2,084 (1,973 pages + 111 PDFs) |
| **Total words** | 1,350,420 |
| **Words per page** | Median 533, Max 9,051, Min 0 |
| **Thin pages (<100w)** | 102 (5%) |
| **Languages** | en-US (1,435), en-us (498), en (38), unset (2) |
| **Crawl duration** | 35 minutes |
| **URLs fetched** | 3,811 |
| **URLs indexed** | 1,973 |
| **JS pages rendered** | 461 (Crawl4AI) |

### Fetch Breakdown

| Outcome | Count | Notes |
|---------|-------|-------|
| **Indexed** | 1,973 | Successfully parsed and stored |
| **Redirect (not followed)** | 956 | External or off-scope destinations |
| **Noindex meta tag** | 680 | WordPress `/tag/` and `/author/` archives |
| **Duplicate content** | 50 | Hash collision; first URL kept |
| **HTTP 404** | 40 | Dead links or stale URLs |
| **Skipped (media)** | 5,436 | PNG/JPG/SVG/GIF/MP4/WOFF filtered at enqueue |
| **Skipped (robots.txt)** | 1 | Disallowed in `robots.txt` |
| **Errors (timeout/5xx)** | 40 | Network or server failures |

---

## Coverage by Host

### www.searchunify.com
- **Documents:** 1,581 (75.9% of corpus)
- **Sections:**
  - `/resource-center` — 1,062 pages (blogs, guides, whitepapers, case studies, comparisons)
  - `/press-release` — 245 pages (news, awards, partnerships)
  - `/expert-hub` — 44 pages (Q&A content)
  - `/products`, `/platform`, `/company`, `/solutions` — 65 pages
  - Homepage, legal pages, misc. — 120 pages

### docs.searchunify.com
- **Documents:** 503 (24.1% of corpus)
- **Content:**
  - Product documentation — configuration, user guides, concepts
  - APIs — Java SDK, Analytics API, REST endpoints
  - Release notes — Mamba, Colubridae, Agent Helper versions
  - Content sources, search clients, admin features
  - ML Workbench, Escalation Predictor, Agent Helper

**Coverage completeness:**
- Robots.txt declares `Sitemap-v2.xml` (2,285 URLs, 80% images)
- Real content pages from sitemap: 458
- Pages discovered via link following: ~45 additional
- **Total indexed: 503** ✓

**Note:** An undeclared `/Sitemap.xml` exists with 1,403 content pages, but 926 are versioned archives (`/Q4-25/`, `/Q1-26/`). These are excluded by design to avoid version conflicts in RAG answers.

---

## Content Freshness

| Year | Pages | Trend |
|------|-------|-------|
| 2026 | 923 | Current development |
| 2025 | 779 | Recent updates |
| 2024 | 67 | Legacy content |
| 2023 | 71 | Archived |
| 2022–2019 | 121 | Historical |
| Unknown | 12 | — |

**86% of indexed pages** were last modified in 2025–2026, indicating active content maintenance.

---

## Content Sections (by URL path)

| Path | Pages | % | Content Examples |
|------|-------|---|---|
| `/resource-center` | 1,062 | 53.8% | "15 Best Enterprise Search Software 2026", "Top 5 Coveo Alternatives", whitepapers, case studies |
| `/Content` (docs) | 501 | 25.4% | APIs, SDKs, release notes, config guides |
| `/press-release` | 245 | 12.4% | Announcements, awards, partnerships |
| `/expert-hub` | 44 | 2.2% | Q&A, expert discussions |
| `/su` (short URLs) | 35 | 1.8% | Redirects and promotional pages |
| `/products` | 22 | 1.1% | Product overview pages |
| `/platform` | 20 | 1.0% | Platform feature pages |
| Other | 155 | 7.9% | Company, legal, misc. |

---

## What the Corpus Supports

### 1. Product How-To & Configuration
- **Scope:** 501 docs pages + linked PDFs
- **Topics:**
  - Configuring search clients (Salesforce, Dynamics 365, ServiceNow, etc.)
  - Content source setup (web, databases, file systems)
  - Agent Helper, Escalation Predictor, ML Workbench
  - Authentication, data security, user management
  - Admin console and instance tools
- **Artifacts:** Java SDK, Python SDK references; REST API endpoints; release notes

**Example queries:** "How do I configure Salesforce search?", "What's the Agent Helper API?", "Release notes for Mamba 21"

### 2. Competitive & Evaluation
- **Scope:** 1,062 resource-center pages
- **Topics:**
  - Competitive comparisons (Coveo, Elasticsearch, Typesense, etc.)
  - Industry benchmarks ("Enterprise Search Software 2026", "Customer Service Automation Platforms 2026")
  - Feature differentiation (cognitive search, AI, case deflection)
  - Customer wins and case studies
- **Artifacts:** Datasheet PDFs (text extracted inline)

**Example queries:** "How does SearchUnify compare to Coveo?", "What is cognitive search?", "Customer service automation solutions"

### 3. Conceptual/Educational
- **Scope:** Guides and glossaries (6,437w "Gen AI and LLM Glossary", etc.)
- **Topics:**
  - Enterprise search fundamentals
  - Knowledge management and case deflection strategies
  - Cognitive search, AI/LLM integration
  - Agent automation and escalation prediction
  - Content discovery and relevance

**Example queries:** "What is case deflection?", "How do AI agents help customer support?", "Difference between semantic and keyword search"

### 4. Company/Social Proof
- **Scope:** 245 press releases, awards, partnerships
- **Topics:**
  - G2 rankings (Summer 2020, Winter 2024)
  - Stevie Awards for AI innovation
  - Strategic partnerships and integrations
  - Customer announcements
  - Industry recognition

**Example queries:** "Who is SearchUnify's partner for ABBYY?", "What awards has SearchUnify won?"

### 5. Legal & Policy
- **Scope:** 4 pages
- **Topics:**
  - Privacy policy and data protection
  - Terms & conditions
  - Cookie policy

---

## Top Topics (by bigram frequency)

| Topic | Pages | Context |
|-------|-------|---------|
| customer support | 432 | Core use case |
| enterprise search | 239 | Product category |
| knowledge management | 179 | Business outcome |
| cognitive search | 168 | Differentiation |
| agent helper | 120 | Feature |
| case deflection | 79 | Business benefit |
| contact center | 84 | Vertical |
| search client | 118 | Integration point |

---

## Known Quality Issues

### 1. Footer CTA Leakage (~262 pages)
**Issue:** A site-wide footer call-to-action ("Begin Your Transformation / Discover Resources / Experience Solutions") is extracted into `headings` on many www pages.

**Impact:** Adds repeated noise (~10 tokens/page) to embeddings and bigram rankings. Not corpus-breaking, but affects semantic relevance on margin queries.

**Mitigation:** Worth adding a targeted CSS selector to `extract.py` to exclude `footer` or specific CTA divs:
```python
# In extract.py, expand BOILERPLATE_SELECTORS
BOILERPLATE_SELECTORS = [
    ...,
    "footer .cta-section",  # SearchUnify footer CTA
]
```

### 2. Versioned Archive Coverage
**Excluded:** 926 pages in `/Q4-25/` and `/Q1-26/` version branches (documented but not indexed).

**Reason:** Version-specific content (e.g., "Mamba 21 Release Notes" + "Q4-25 Mamba 21 Release Notes") causes RAG hallucination — the agent cites outdated config for the wrong release.

**If needed:** Include with a version tag in metadata for version-aware retrieval.

### 3. WordPress Archive Pages
**Excluded:** 680 `/tag/` and `/author/` archive pages (marked `noindex` by site).

**Reason:** Boilerplate indices with minimal unique content; archive pages aren't canonical sources.

### 4. Thin Pages
**Count:** 102 pages (<100 words).

**Sources:** Homepage, redirect pages, navigation stubs.

**Impact:** Low — these are typically thin by design, and embeddings handle short text.

---

## Supported Features

### ✅ Crawling & Indexing

| Feature | Status | Notes |
|---------|--------|-------|
| **Sitemap discovery** | ✅ | Crawls `sitemap_index.xml` + child sitemaps; auto-discovers `Sitemap:` in robots.txt |
| **Link following** | ✅ | Discovers new pages within allowed domains |
| **Robots.txt compliance** | ✅ | Respects `Disallow`, `Crawl-delay`, `Sitemap:` directives |
| **Canonical URL handling** | ✅ | Deduplicates by `<link rel="canonical">` when present |
| **JavaScript rendering** | ✅ | Crawl4AI + Playwright for JS-only pages (461 rendered in this crawl) |
| **HTTP redirects** | ✅ | Follows 30x internally; skips external destinations |
| **Content hashing** | ✅ | Incremental crawls skip unchanged pages (ETag + SHA-256 hash) |
| **Incremental crawls** | ✅ | Re-run the crawler to update only changed pages (delta mode) |

### ✅ Content Extraction

| Feature | Status | Notes |
|---------|--------|-------|
| **HTML text extraction** | ✅ | BeautifulSoup + heuristic boilerplate removal |
| **Link discovery** | ✅ | Extracts `href` from `<a>`, `<link>`, `<iframe>` |
| **Metadata** | ✅ | Title, description, publish date, authors, images |
| **Structured data** | ✅ | JSON-LD schema.org (e.g., `Article`, `BlogPosting`) |
| **Language detection** | ✅ | ISO 639-1 language code inference |
| **PDF text extraction** | ✅ | PyPDF for inline PDF links (111 documents in corpus) |
| **Asset discovery** | ✅ | Queues linked PDF/DOCX/PPTX/CSV for extraction |
| **Media filtering** | ✅ | Skips images, video, fonts, CSS/JS, archives (5,436 filtered in crawl) |

### ✅ Output Format

| Feature | Status | Notes |
|---------|--------|-------|
| **JSONL documents** | ✅ | One JSON object per line; per-run delta (unchanged pages skipped) |
| **Schema** | ✅ | `url`, `title`, `text`, `headings`, `links`, `canonical_url`, `content_type`, `language`, `js_rendered`, `crawled_at`, `depth`, `word_count` |
| **Multiple JSONL files** | ✅ | Timestamped to support incremental ingestion |
| **SQLite state** | ✅ | `crawl_state.sqlite` tracks per-URL history for incremental runs |

### ✅ Auditing & Compliance

| Feature | Status | Notes |
|---------|--------|-------|
| **Decision trail** | ✅ | DEBUG-level audit log; every URL decision logged (e.g., `DECISION indexed`, `DECISION noindex`, `DECISION skipped_media`) |
| **Compliance tracking** | ✅ | Robots.txt respect logged; `noindex` honored; redirect handling transparent |
| **Error reporting** | ✅ | Network errors, parsing failures, and timeouts captured with root cause |
| **Performance metrics** | ✅ | Crawl duration, fetched/indexed counts, per-host stats |

### ✅ Configuration & Control

| Feature | Status | Notes |
|---------|--------|-------|
| **YAML config** | ✅ | Sitemaps, seeds, rate limits, render settings, output paths |
| **CLI overrides** | ✅ | `--max-pages`, `--full` (force rebuild), `--no-render`, `--log-file` |
| **Rate limiting** | ✅ | Per-host delay (default 0.5s) configurable; robots.txt `Crawl-delay` honored |
| **Concurrent fetching** | ✅ | Worker pool (default 6) for parallelism across hosts |
| **Incremental mode** | ✅ | Resume where the last run left off; only changed pages re-indexed |
| **Full rebuild mode** | ✅ | Re-emit all pages without deleting old JSONL (useful for extraction logic changes) |

### ❌ Not Yet Supported

| Feature | Status | Rationale |
|---------|--------|-----------|
| Database content crawling | ❌ | Out of scope; requires auth + schema awareness |
| Authentication (login forms) | ❌ | Adds complexity; most SearchUnify content is public |
| Image alt-text extraction | ❌ | Not implemented; images are filtered |
| Optical character recognition (OCR) | ❌ | Scanned PDFs would need external service |
| Real-time feed monitoring | ❌ | Crawl is one-shot; could add RSS support later |

---

## Usage

### First-time crawl (full)
```bash
python -m crawler --config config/searchunify.yaml
```
Outputs: `data/searchunify/documents_<timestamp>.jsonl` + state DB

### Incremental refresh (delta)
```bash
# Crawls again; unchanged pages skip indexing (300x faster)
python -m crawler --config config/searchunify.yaml
```

### Rebuild after extraction changes
```bash
# Forces all pages to be re-emitted (ignores stored hashes)
python -m crawler --config config/searchunify.yaml --full
```

### Audit trail
```bash
# Full DEBUG log with per-URL decisions
data/searchunify/logs/crawl_<timestamp>.log
```

### Corpus analysis
```bash
python analyze_corpus.py data/searchunify --top 20
```

---

## Summary

**Readiness:** ✅ Production-ready  
**Coverage:** ✅ Comprehensive (all public docs, blogs, press, APIs)  
**Freshness:** ✅ Current (86% from 2025–2026)  
**Quality:** ⚠️ Minor (footer CTA noise; versioned archives excluded by design)  

The corpus is suitable for RAG ingestion into OpenSearch, Pinecone, or Weaviate with minimal pre-processing beyond the noted footer-CTA fix.
