# Website Crawler for Enterprise Search RAG

A polite, production-ready Python website crawler that respects `robots.txt`, discovers URLs from `sitemap.xml`, extracts clean content, and outputs JSONL documents optimized for RAG (Retrieval-Augmented Generation) pipelines.

**Status**: Scoped to website crawling (FR-01 to FR-09 of [Website_Crawl_RAG_Requirements.md](Website_Crawl_RAG_Requirements.md)).

---

## Features

✅ **Sitemap-driven discovery** — crawls `sitemap_index.xml` and child sitemaps; falls back to seed URLs  
✅ **JavaScript rendering** — Crawl4AI + Playwright fallback for JS-only pages (FR-02)  
✅ **Robots.txt compliance** — respects `Disallow`, `Crawl-delay`, and `Sitemap:` directives  
✅ **Incremental crawling** — tracks ETag and content hash; re-indexes only changed pages  
✅ **Deduplication** — avoids storing identical content under multiple URLs  
✅ **Off-domain redirect blocking** — follows only in-scope redirects; rejects external hops  
✅ **Main-content extraction** — strips nav, headers, footers, cookie banners, boilerplate  
✅ **Metadata extraction** — title, description, canonical URL, breadcrumbs, keywords, dates  
✅ **Charset auto-detection** — handles UTF-8, cp1252, and declared charsets  
✅ **Linked document discovery** — queues PDF/DOCX/PPTX for extraction (stored locally)  
✅ **Threaded fetching** — configurable worker pool with per-host rate limiting  
✅ **Conditional requests** — If-None-Match (ETag), If-Modified-Since headers  
✅ **Retry strategy** — exponential backoff on 429/5xx; respects Retry-After  
✅ **JSONL output** — one enriched document per line, ready for indexing  

---

## Quick Start

### 1. Install

```bash
python -m venv .venv
.\.venv\Scripts\activate          # Windows
# source .venv/bin/activate       # macOS/Linux

pip install -r requirements.txt
python -m playwright install chromium   # browser used for JS rendering
```

### Hybrid fetch strategy

The crawler uses a **two-tier fetcher**, because a browser is 20x slower than an HTTP request:

| Tier | Used for | Speed |
|------|----------|-------|
| `requests` + BeautifulSoup | Server-rendered pages (most WordPress/marketing sites) | ~0.2s/page |
| Crawl4AI + Playwright | Pages whose static HTML yields < `render_min_words` words, or hosts listed in `render_hosts` | ~4s/page |

This matters: `docs.searchunify.com` serves an **877-byte JS shell with zero text**. Static fetching
indexed it as empty documents; with rendering it yields ~550 words/page. Set `render_js: off` to
disable the browser entirely, or `always` to render every page.

### 2. Configure

Edit `config/searchunify.yaml` to add your site(s):

```yaml
name: mysite

sitemaps:
  - https://mysite.com/sitemap_index.xml
seeds:
  - https://mysite.com/

allowed_domains:
  - mysite.com
  - staging.mysite.com

exclude_patterns:
  - "/admin/"
  - "/private/"
  - "\\?utm_source="

user_agent: "MyBot/1.0 (+https://mysite.com; contact=bot@mysite.com)"
obey_robots: true
max_workers: 4
request_delay: 1.0
max_pages: null
output_dir: data/mysite
```

### 3. Run

```bash
# Full crawl (discovers from sitemaps, follows links)
python -m crawler --config config/searchunify.yaml

# Smoke test (10 pages, sitemaps only)
python -m crawler --config config/searchunify.yaml --max-pages 10 --no-links

# Force re-crawl everything (ignore cached hashes)
python -m crawler --config config/searchunify.yaml --full

# Verbose logging
python -m crawler --config config/searchunify.yaml -v
```

### 4. Output

```
data/searchunify/
├── documents_20260826T135111Z.jsonl  # RAG documents (one per line)
├── crawl_state.sqlite                # State DB (URLs, ETags, hashes)
└── assets/                           # Downloaded PDFs, DOCX, etc.
    ├── a1b2c3d4e5f6.pdf
    └── f5e4d3c2b1a0.docx
```

One document sample:

```json
{
  "id": "a3c7f9e1d2b4c5a8",
  "url": "https://mysite.com/blog/hello-world",
  "canonical_url": "https://mysite.com/blog/hello-world",
  "source_type": "web_page",
  "content_type": "text/html",
  "title": "Hello World | My Site",
  "description": "A first post about...",
  "language": "en",
  "headings": ["Hello World", "Getting Started", "Next Steps"],
  "breadcrumbs": ["Home", "Blog", "Hello World"],
  "keywords": ["blog", "tutorial", "hello"],
  "text": "Welcome to our blog... [full clean text]",
  "word_count": 1247,
  "published_at": "2025-06-01T10:00:00Z",
  "modified_at": "2025-06-05T14:30:00Z",
  "http_status": 200,
  "content_hash": "7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c",
  "crawled_at": "2026-08-26T13:51:11+00:00",
  "depth": 1
}
```

---

## Configuration Reference

### URL Discovery

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `name` | str | — | Crawl name (appears in logs) |
| `sitemaps` | list[str] | `[]` | Sitemap index or sitemap URLs to crawl |
| `seeds` | list[str] | `[]` | Root URLs to discover from (if no sitemaps) |
| `allowed_domains` | list[str] | `[]` | **Required.** Restrict crawl to these domains; subdomains allowed |
| `include_patterns` | list[str] | `[]` | Regex allowlist (if set, only URLs matching ≥1 pattern are crawled) |
| `exclude_patterns` | list[str] | `[]` | Regex blocklist (URLs matching any pattern are skipped) |

### Rate Limiting & Politeness

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `user_agent` | str | — | HTTP User-Agent; used to query robots.txt rules for your bot |
| `obey_robots` | bool | `true` | Honor `robots.txt` rules; set to `false` only for testing |
| `obey_noindex` | bool | `true` | Skip pages with `<meta name="robots" content="noindex">` or `X-Robots-Tag: noindex` |
| `request_delay` | float | `1.0` | Minimum seconds between requests to the same host; robots.txt `Crawl-delay` overrides this |
| `request_timeout` | float | `30.0` | HTTP timeout (seconds) per request |
| `max_retries` | int | `2` | Retry 429/5xx up to N times with exponential backoff |

### Crawl Strategy

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `max_workers` | int | `4` | Concurrent fetcher threads |
| `max_depth` | int | `5` | Max hops from seed/sitemap URL when `follow_links: true` |
| `follow_links` | bool | `true` | Extract and crawl `<a href>` links (vs. sitemap-only) |
| `max_pages` | int \| null | `null` | Stop after N pages (null = unlimited); useful for smoke tests |
| `max_content_bytes` | int | 20×10⁶ | Truncate responses larger than this (20 MB default) |

### Assets & Incremental

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `render_js` | str | `"auto"` | `off` \| `auto` (render only thin pages) \| `always` |
| `render_min_words` | int | `60` | Under `auto`, re-fetch with a browser if static extraction yields fewer words |
| `render_hosts` | list[str] | `[]` | Hosts always rendered regardless of word count (e.g. a JS docs portal) |
| `render_concurrency` | int | `2` | Concurrent browser tabs |
| `render_timeout` | float | `45.0` | Per-page browser timeout (seconds) |
| `fetch_assets` | bool | `true` | Queue PDF/DOCX/PPTX/TXT/CSV links for download & extraction |
| `asset_extensions` | list[str] | `[".pdf", ".docx", ...]` | File types to treat as assets |
| `save_assets` | bool | `true` | Write assets to `output_dir/assets/`; set to `false` if using Tika externally |
| `output_dir` | str | `"data/searchunify"` | JSONL documents and assets output folder |
| `state_db` | str | `"data/searchunify/crawl_state.sqlite"` | Incremental crawl state database |
| `incremental` | bool | `true` | Check ETag/content hash before re-indexing; set to `false` with `--full` flag |

---

## Workflow

### Phase 1: Frontier Setup
1. Load config (domains, patterns, rate limits).
2. Discover URLs from `sitemaps` → walk sitemap index → collect `<loc>` + `lastmod` from all child sitemaps.
3. Enqueue discovered URLs into the crawl frontier (max depth 0).
4. Optionally fetch `robots.txt` from each host and extract `Crawl-delay` (overrides config floor).
5. Add `seeds` to frontier if no sitemaps provided.

### Phase 2: Crawl Workers
Each of N workers:
1. Dequeue next URL (FIFO from thread-safe queue).
2. Check if already seen (in-memory set); skip duplicates.
3. Enforce rate limit (wait if host was fetched within `request_delay` seconds).
4. Fetch URL with:
   - Conditional headers: `If-None-Match` (ETag), `If-Modified-Since`.
   - User-Agent matching robots.txt.
   - Manual redirect following: only in-scope targets accepted.
5. If HTTP 304 (Not Modified) → mark unchanged, skip processing.
6. If redirected out-of-scope → skip (count as `skipped_redirect`).
7. If error/4xx → record error state, continue.

### Phase 3: Content Extraction
For each successful fetch:
1. Detect content type (HTML vs. asset).
2. If **HTML**:
   - Extract via BeautifulSoup: title, description, canonical URL, meta tags.
   - Scrub: remove scripts, styles, nav, headers, footers, boilerplate (cookie banners, sidebars).
   - Extract: clean main text, headings (h1–h3), breadcrumbs, links, keywords.
   - Check `noindex` meta tag + X-Robots-Tag; skip if present.
   - Compute SHA256 hash of text.
   - Check for duplicate hashes; mark as `duplicates` if seen before.
   - Extract href targets; enqueue links (if `follow_links: true`).
   - Enqueue asset links (PDF/DOCX/etc.) separately.
   - Write JSONL document: url, title, text, breadcrumbs, metadata, hash, crawl timestamp.

3. If **Asset** (PDF/DOCX/etc.):
   - Try inline extraction (PDF → text via `pypdf`; TXT/CSV → raw).
   - Save binary to `data/assets/<hash>.<ext>`.
   - Write JSONL doc: url, title, local_path, `needs_extraction: true` (for external Tika).

### Phase 4: State Persistence
After processing each URL:
- Upsert SQLite row: `url`, `content_hash`, `etag`, `last_modified`, `first_seen`, `last_crawled`, `last_changed`.
- On second crawl: compare hash → if unchanged, skip re-indexing (mark as `unchanged`).

---

## State Management

### SQLite Schema (`crawl_state.sqlite`)

```sql
CREATE TABLE pages (
    url             TEXT PRIMARY KEY,
    canonical_url   TEXT,
    status          INTEGER,
    content_hash    TEXT,
    etag            TEXT,
    last_modified   TEXT,
    title           TEXT,
    first_seen      TEXT,
    last_crawled    TEXT,
    last_changed    TEXT,
    error           TEXT
);
```

**Incremental Logic**:
- First run: all URLs are new → indexed.
- Second run: fetch with `If-None-Match` + `If-Modified-Since` from DB.
  - Server returns 304 → unchanged → skip re-indexing.
  - Server returns new content → compare hash:
    - Same hash as before → `unchanged` (page refetched but content identical).
    - Different hash → `indexed` (content changed, stored as new doc).
    - Hash matches a different URL → `duplicates` (mark both, index only first).

---

## Robots.txt Compliance

The crawler enforces:

1. **Per-User-Agent Rules**: Only rules matching your `user_agent` (and `*` group) apply.
   ```robots.txt
   User-agent: MyBot
   Disallow: /admin/
   
   User-agent: *
   Disallow: /temp/
   ```
   MyBot is disallowed from both `/admin/` and `/temp/`.

2. **Crawl-delay**: If `Crawl-delay: 5` is set, overrides your `request_delay` config.

3. **Sitemap Directive**: Automatically discovered and prioritized:
   ```robots.txt
   Sitemap: https://mysite.com/sitemap_index.xml
   ```

4. **Noindex Meta + X-Robots-Tag**: Pages are fetched but not indexed if `obey_noindex: true`.

5. **Live Enforcement**: Applied at fetch time, not just URL matching. Off-domain redirects are blocked even if targets are crawlable.

---

## Logging & Monitoring

### Log Levels

- **INFO** (default): crawl progress, stats, sitemap discovery.
- **DEBUG** (`-v` flag): individual URL decisions, rate limits, hash comparisons.
- **WARNING**: network errors, robots.txt failures, encoding issues, oversized content.

### Stats Printed to Stdout

```json
{
  "queued": 1664,
  "fetched": 15,
  "indexed": 8,
  "unchanged": 0,
  "duplicates": 0,
  "skipped_robots": 0,
  "skipped_noindex": 3,
  "skipped_scope": 77,
  "skipped_redirect": 7,
  "assets": 2,
  "errors": 0,
  "started_at": "2026-08-26T13:51:11+00:00"
}
```

- **queued** — URLs enqueued to crawl (dedup'd).
- **fetched** — Successful HTTP responses.
- **indexed** — Documents written to JSONL.
- **unchanged** — ETag/hash match; content not re-indexed.
- **duplicates** — Hash collision; only first URL indexed.
- **rendered** — Pages re-fetched through the headless browser.
- **skipped_robots** — Blocked by robots.txt.
- **skipped_noindex** — Blocked by `noindex` meta/header.
- **skipped_scope** — Out-of-domain or excluded by patterns.
- **skipped_redirect** — Redirect to out-of-scope URL; response not followed.
- **assets** — Linked documents (PDF/DOCX) stored.
- **errors** — Network failures, timeouts, parse errors.

---

## Examples

### Example 1: Crawl a Staging Site (Small)

```yaml
# config/staging.yaml
name: staging
sitemaps:
  - https://staging.acme.com/sitemap.xml
allowed_domains:
  - staging.acme.com
user_agent: "AcmeCrawler/1.0 (+https://staging.acme.com)"
obey_robots: true
max_workers: 2
request_delay: 2.0
max_pages: 500
output_dir: data/acme_staging
```

```bash
python -m crawler --config config/staging.yaml --no-links
# Crawl 500 pages from the sitemap, no link following.
# Output: data/acme_staging/documents_*.jsonl
```

### Example 2: Full Crawl with Incremental Updates

```yaml
# config/docs.yaml
name: docs
seeds:
  - https://docs.example.com/
allowed_domains:
  - docs.example.com
exclude_patterns:
  - "/admin/"
  - "/search"
follow_links: true
incremental: true
max_workers: 8
request_delay: 0.5
output_dir: data/docs
```

**First run** (day 1):
```bash
python -m crawler --config config/docs.yaml
# Crawl all pages → data/docs/documents_20260801T120000Z.jsonl
# State saved to data/docs/crawl_state.sqlite
```

**Second run** (day 2):
```bash
python -m crawler --config config/docs.yaml
# Checks ETags & hashes from day 1:
#   - 95% unchanged → skipped
#   - 5% changed → re-indexed into new JSONL
#   - Total crawl time reduced by ~80%
```

### Example 3: Smoke Test Before Production

```bash
python -m crawler --config config/searchunify.yaml --max-pages 20 -v
# Crawl 20 pages only, full logging, stop after 20 fetches.
# Validates config, robots.txt compliance, extraction quality.
```

---

## Troubleshooting

### "HTTPSConnectionPool: Max retries exceeded"
- **Cause**: Server SSL misconfiguration or very restrictive client policies.
- **Fix**: Check if the site is accessible in a browser. If so, skip the URL or report to site admin. The crawler continues past network errors.

### "robots.txt forbidden at <url>; treating site as disallowed"
- **Cause**: robots.txt returned 403.
- **Fix**: Check your User-Agent is not blocked. Contact the site; your bot may be on a blacklist.

### "Too few pages indexed vs. queued"
- **Cause**: Many URLs skipped due to `exclude_patterns`, `noindex`, redirects.
- **Fix**: Check logs with `-v`; review your config patterns. Use `include_patterns` to be more permissive if needed.

### "Garbled text in output (mojibake)"
- **Cause**: Server sent no charset in Content-Type; page had no HTML meta charset.
- **Fix**: Crawler falls back to UTF-8 validation, then cp1252. Rare; file an issue if a site breaks.

### "Crawl is very slow"
- **Cause**: `request_delay` too high, or robots.txt set a large `Crawl-delay`.
- **Fix**: Lower `request_delay` or reduce `max_workers` to avoid rate-limit 429 responses. Check robots.txt with `-v`.

---

## Integration with RAG Pipelines

The JSONL output is shaped for OpenSearch/Vespa/Milvus indexing:

```python
import json

with open("data/searchunify/documents_*.jsonl") as f:
    for line in f:
        doc = json.loads(line)
        # Index doc["text"] + embeddings
        # Store doc["url"] as source for citations
        # Use doc["headings"] + doc["breadcrumbs"] for re-ranking
        # Track doc["crawled_at"] for freshness boosting
        index_rag_doc(doc)
```

See [Website_Crawl_RAG_Requirements.md](Website_Crawl_RAG_Requirements.md) for FR-04 (chunking), FR-05 (embeddings), FR-06 (indexing).

---

## Performance & Scalability

- **Typical throughput**: 200–500 pages/minute (depending on site speed + `request_delay`).
- **Memory**: ~10 MB + URL dedup set (O(n) in crawled pages).
- **Disk**: JSONL ≈ 1–2 KB per page; assets separate; SQLite ≈ 1 KB per URL.
- **Scalability**: 4–8 workers handle most sites. 16+ workers for very fast hosting.

**Example**: 10,000 pages @ 1 second delay/host ≈ 3–5 hours single-machine.

---

## Development & Testing

### Run Tests
```bash
pytest tests/ -v
# (No tests yet; PR welcome!)
```

### Add a New Site

1. Create `config/mysite.yaml` (copy from template).
2. Set `seeds` or `sitemaps`, `allowed_domains`.
3. Dry-run with `--max-pages 10 -v` to validate config + extraction.
4. Full crawl: `python -m crawler --config config/mysite.yaml`.

### Extend the Crawler

Key modules:
- `crawler/extract.py` — add custom boilerplate removal, metadata extraction.
- `crawler/crawler.py` — add custom pre/post-processing in `_handle_html()`.
- `crawler/fetcher.py` — modify retry logic, add custom headers.

---

## License & Support

Built for the Enterprise Search RAG platform. See [Website_Crawl_RAG_Requirements.md](Website_Crawl_RAG_Requirements.md) for functional requirements.

Questions? File an issue or contact the team.
