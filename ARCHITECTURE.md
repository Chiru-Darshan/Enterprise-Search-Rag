# Crawler Architecture & Design

A detailed technical guide to the crawler's internals, design patterns, and implementation.

---

## Table of Contents

1. [High-Level Architecture](#high-level-architecture)
2. [Module Breakdown](#module-breakdown)
3. [Concurrency & Threading](#concurrency--threading)
4. [URL Normalization & Deduplication](#url-normalization--deduplication)
5. [Rate Limiting](#rate-limiting)
6. [Robots.txt Compliance](#robotstxt-compliance)
7. [Content Extraction Pipeline](#content-extraction-pipeline)
8. [Incremental Crawling](#incremental-crawling)
9. [Error Handling & Resilience](#error-handling--resilience)
10. [Performance Considerations](#performance-considerations)

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Crawler.run()                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. Setup Frontier                                                  │
│     ├─ Load config (seeds, sitemaps, allow/exclude patterns)       │
│     ├─ Discover URLs from sitemaps → sitemap_index.xml            │
│     ├─ Walk child sitemaps, collect loc + lastmod                 │
│     ├─ Enqueue all discovered URLs (depth=0)                      │
│     ├─ Fetch robots.txt from each host, extract Crawl-delay       │
│     └─ Add seeds if no sitemaps provided                          │
│                                                                     │
│  2. Spawn Worker Threads (max_workers)                             │
│     ├─ Each worker: while queue not empty:                         │
│     │  ├─ Dequeue task (url, depth)                               │
│     │  ├─ Check robots.txt allowed                                │
│     │  ├─ Enforce rate limit (per-host)                           │
│     │  ├─ Fetch with conditional headers (ETag/If-Modified)      │
│     │  ├─ Handle redirects (in-scope only)                        │
│     │  ├─ Process content (extract or asset save)                 │
│     │  ├─ Enqueue child URLs                                      │
│     │  └─ Update state DB                                         │
│     └─ Workers exit when queue empty + stop signal                │
│                                                                     │
│  3. Write Output                                                    │
│     ├─ JSONL documents: one per line, ready for indexing          │
│     ├─ SQLite state: URL → hash, ETag, last-crawled               │
│     └─ Assets: PDF/DOCX saved to disk                             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Module Breakdown

### 1. `config.py` — Configuration Loading

**Purpose**: Parse YAML, validate, compile regex patterns, define defaults.

**Key Types**:
- `CrawlConfig` — dataclass with all knobs (domains, patterns, rate limits, output paths).

**Responsibilities**:
- Load YAML via `load_config(path)`.
- Validate: `allowed_domains` non-empty, seeds or sitemaps provided.
- Compile include/exclude regex patterns → `config.include_re`, `config.exclude_re`.
- Create output directories.
- Provide `url_allowed(url)` predicate for scope checks.

**Example**:
```python
config = load_config("config/searchunify.yaml")
if config.url_allowed("https://searchunify.com/blog"):
    # True: matches allowed_domains + not in exclude_patterns
    pass
```

---

### 2. `urls.py` — URL Normalization & Scope

**Purpose**: Canonical URL form, domain extraction, extension detection, tracking-param removal.

**Key Functions**:
- `normalize_url(url, base)` — absolute URL, remove fragment, strip tracking params, collapse slashes, fix trailing slashes on root dirs.
  - Returns `None` if non-HTTP(S), relative link in href without base, or data: URI.
- `registrable_host(url)` — lowercase hostname (second-level domain).
- `in_allowed_domains(url, allowed)` — check if URL's host is in allowed list (allows subdomains).
- `path_extension(url)` — extract `.pdf`, `.docx` etc.

**Deduplication**:
- Tracking params removed: `utm_*`, `gclid`, `fbclid`, `_hs*`, `ref`, `mc_*`, `gtm_latency`, etc.
- Fragment + query normalization → same content different anchors treated as one URL.

**Example**:
```python
normalize_url("https://searchunify.com/blog?utm_source=twitter&utm_medium=social#section2")
# → "https://searchunify.com/blog"

in_allowed_domains("https://staging.searchunify.com/", ["searchunify.com"])
# → True (subdomain allowed)
```

---

### 3. `fetcher.py` — HTTP Client with Politeness

**Purpose**: Rate limiting, retries, conditional requests, charset sniffing, manual redirect handling.

**Key Classes**:

#### `RateLimiter`
```python
limiter = RateLimiter(default_delay=1.0)
limiter.set_delay("example.com", 5.0)  # robots.txt Crawl-delay override
limiter.acquire("example.com")          # Block until ready
```
- Per-host tracking of "next free time" with thread-safe lock.
- `acquire()` sleeps if necessary, ensuring minimum delay between requests to same host.

#### `Fetcher`
```python
fetcher = Fetcher(
    user_agent="MyBot/1.0",
    timeout=30,
    max_retries=2,
    limiter=limiter,
    max_content_bytes=20*1024*1024,
    pool_size=8
)
resp = fetcher.get(
    url,
    etag="...",
    last_modified="...",
    redirect_filter=lambda u: in_allowed_domains(u, [...])
)
```

**Response object**:
```python
@dataclass
class Response:
    url: str                # Final URL (after redirects)
    status: int             # HTTP status
    headers: dict[str, str]
    content: bytes
    encoding: str | None    # Detected charset
    elapsed: float          # Request time (seconds)
```

**Retry Strategy**:
- Retryable: 429 (rate limit), 500/502/503/504 (server error).
- Backoff: `2^attempt + random()` seconds (capped at 60s).
- Respects `Retry-After` header if present.
- Network errors (timeout, DNS, SSL) are retried once then raised.

**Redirect Handling** (manual, in-scope only):
- Follows up to 5 redirects.
- Checks redirect target with `redirect_filter()` — blocks out-of-scope hops.
- Removes conditional headers on redirect (fresh fetch).

**Charset Detection**:
```python
def _sniff_encoding(self) -> str:
    # 1. Extract charset from Content-Type header
    # 2. Try to decode as UTF-8; if valid, use UTF-8
    # 3. Fall back to cp1252 (Windows-1252)
```
Solves mojibake by detecting encoding from server, document, or best guess.

---

### 4. `robots.py` — Robots.txt Parser Cache

**Purpose**: Load, cache, and query `robots.txt` rules per host.

**Key Class**:
```python
registry = RobotsRegistry(fetcher, user_agent="MyBot/1.0", enabled=True)
allowed = registry.allowed(url)           # Can I fetch this URL?
delay = registry.crawl_delay(url)         # robots.txt Crawl-delay
sitemaps = registry.sitemaps(url)         # Extract Sitemap: directives
```

**Caching**:
- One `RobotFileParser` per host (from urllib.robotparser).
- Cached on first query for that host; subsequent queries use cached version.
- If fetch fails (network error), treat as no restrictions (permissive).
- If 403 Forbidden, treat as disallow-all (conservative).

**Compliance**:
- Applies only rules matching your `user_agent` or `*` (wildcard).
- `Crawl-delay` from robots.txt overrides config `request_delay`.
- `Sitemap:` directives automatically discovered and integrated into crawl frontier.

---

### 5. `sitemap.py` — Sitemap Index & XML Parsing

**Purpose**: Walk sitemap index, collect all page URLs.

**Key Functions**:
```python
entries = discover(fetcher, ["https://mysite.com/sitemap_index.xml"])
# Returns list[SitemapEntry] with url + lastmod
```

**Behavior**:
1. Fetch sitemap URL.
2. Parse XML (handles gzip-compressed `.gz` files).
3. If `<sitemapindex>` → extract child sitemap URLs, add to queue.
4. If `<urlset>` → extract `<url>` entries (loc + lastmod).
5. Recurse until all sitemaps visited or max_sitemaps limit hit.

**Robustness**:
- Gzip decompression (auto-detect).
- XML parse errors logged but don't crash.
- Deduplication via dict keyed by URL.

---

### 6. `extract.py` — Main Content & Metadata Extraction

**Purpose**: Clean HTML, extract text/metadata, identify boilerplate.

**Key Functions**:

#### `extract(html, url, asset_extensions) → Page`

```python
page = extract(html_string, base_url, [".pdf", ".docx", ...])

@dataclass
class Page:
    url: str
    canonical_url: str | None
    title: str
    description: str
    language: str
    text: str                    # Clean main text (no boilerplate)
    headings: list[str]          # h1, h2, h3
    breadcrumbs: list[str]
    keywords: list[str]
    published_at: str            # article:published_time meta
    modified_at: str             # article:modified_time meta
    noindex: bool
    nofollow: bool
    links: list[str]             # Unique href targets
    assets: list[str]            # PDF/DOCX/etc. links
    word_count: int
```

**Extraction Steps**:

1. **Metadata**:
   - Title: `<title>` or `og:title` meta.
   - Description: `name=description` or `og:description`.
   - Keywords: comma-separated from `name=keywords`.
   - Dates: `article:published_time`, `article:modified_time`.
   - Canonical: `<link rel=canonical>`.
   - Language: `<html lang>`.
   - Robots directives: `name=robots` + `name=googlebot` meta tags + `X-Robots-Tag` header.

2. **Main Content Extraction**:
   - Try priority selectors: `main`, `article`, `[role=main]`, `#main`, `#content`, `.entry-content`, `.post-content`.
   - Pick the selector with most text (≥200 chars).
   - Fall back to `<body>` if no selector found.

3. **Boilerplate Removal**:
   - Delete tags: `<script>`, `<style>`, `<noscript>`, `<template>`, `<svg>`, `<iframe>`, `<form>`, `<button>`.
   - Delete containers (nav, header, footer, aside).
   - Delete by class/ID hint: `class|id` matching breadcrumb|navbar|sidebar|footer|cookie|banner|popup|modal|promo|related|comment|social|share patterns.
   - Delete `aria-hidden="true"` regions.

4. **Link Extraction**:
   - All `<a href>` targets; separate assets (`.pdf`, `.docx`, etc.) from HTML pages.
   - Deduplicate.

5. **Text Cleaning**:
   - Collapse multiple spaces → single space.
   - Collapse 3+ newlines → double newline.
   - Encode properly (UTF-8).

**Example**:
```python
page = extract(html, "https://mysite.com/blog/post123", [".pdf"])
# → Page with .text = "Welcome to our blog... [clean]"
# → page.links = ["https://mysite.com/blog/post456", ...]
# → page.assets = ["https://mysite.com/guides/guide.pdf", ...]
```

---

### 6b. `render.py` — JavaScript Rendering (Crawl4AI)

**Purpose**: Render JS-only pages with a real browser when static HTML yields nothing useful.

**Why it exists**: `requests` sees only the server response. Single-page apps (docs portals,
community forums) ship an empty shell and build the DOM client-side. `docs.searchunify.com`
returns 877 bytes with 5 script tags and zero text; rendered, the same URL yields ~119 KB and
250+ words plus 55 links for frontier expansion.

**Bridging async → threaded**: Crawl4AI is `asyncio`-based; the crawler is thread-based. `JsRenderer`
owns a dedicated event-loop thread and a single shared browser, and submits work with
`asyncio.run_coroutine_threadsafe`. An `asyncio.Semaphore` caps concurrent tabs, so browser
memory stays bounded regardless of `max_workers`.

```python
renderer = JsRenderer(user_agent, concurrency=3, timeout=45.0)
html = renderer.render(url)   # blocking call, returns rendered DOM or None
renderer.close()
```

**Lazy startup**: the browser launches on first render request, so crawls of fully
server-rendered sites never pay the ~500 MB / 2s startup cost.

**Trigger policy** (`Crawler._needs_render`):
1. `render_js: off` → never.
2. `render_js: always` → every HTML page.
3. Host in `render_hosts` → always render that host.
4. Otherwise → render only if static extraction produced `< render_min_words` words.

Rendered HTML is fed back through the same `extract()` pipeline, so metadata, link discovery,
hashing, and dedup behave identically for static and rendered pages. Documents carry a
`js_rendered` boolean for downstream debugging.

---

### 7. `store.py` — State & JSONL Writer

**Purpose**: Persist crawl state (incremental dedup), write JSONL docs.

**Key Class**:
```python
store = CrawlStore("data/crawl_state.sqlite", "data/", run_id="20260826T135111Z")
store.write_document({...})            # Append to JSONL
store.upsert(url=..., status=..., ...)  # Update SQLite
store.save_asset(url, content)         # Write binary
store.get(url) → PageState | None      # Fetch prior crawl record
store.hash_seen(digest, url) → bool    # Duplicate detection
```

**SQLite Schema**:
```sql
CREATE TABLE pages (
    url            TEXT PRIMARY KEY,
    canonical_url  TEXT,
    status         INTEGER,
    content_hash   TEXT,
    etag           TEXT,
    last_modified  TEXT,
    title          TEXT,
    first_seen     TEXT,
    last_crawled   TEXT,
    last_changed   TEXT,
    error          TEXT
);
CREATE INDEX idx_pages_hash ON pages(content_hash);
```

**JSONL Format** (one document per line):
```json
{
  "id": "a3c7f9e1d2b4c5a8",
  "url": "https://...",
  "requested_url": "https://... (before redirect)",
  "canonical_url": "https://...",
  "source_type": "web_page" or "linked_document",
  "content_type": "text/html",
  "title": "...",
  "description": "...",
  "language": "en",
  "headings": ["h1", "h2"],
  "breadcrumbs": ["Home", "Blog"],
  "keywords": ["tag1", "tag2"],
  "text": "... [full clean text] ...",
  "word_count": 1247,
  "published_at": "2025-06-01T10:00:00Z",
  "modified_at": "2025-06-05T14:30:00Z",
  "sitemap_lastmod": "2025-06-05",
  "http_status": 200,
  "content_hash": "7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c",
  "crawled_at": "2026-08-26T13:51:11+00:00",
  "depth": 1
}
```

---

### 8. `crawler.py` — Main Orchestration

**Purpose**: Tie together all modules; manage frontier, workers, state.

**Key Class**:
```python
crawler = Crawler(config)
stats = crawler.run()  # Blocking; returns CrawlStats

@dataclass
class CrawlStats:
    queued: int
    fetched: int
    indexed: int
    unchanged: int
    duplicates: int
    skipped_robots: int
    skipped_noindex: int
    skipped_scope: int
    skipped_redirect: int
    assets: int
    errors: int
    started_at: str
```

**Workflow**:

#### `_seed()` — Frontier Setup
1. Discover sitemaps from `config.sitemaps`.
2. Walk sitemap index → collect all page entries.
3. Enqueue discovered URLs (depth=0).
4. Fetch robots.txt from each host; extract `Crawl-delay` → update `RateLimiter`.
5. Enqueue seed URLs (depth=0).

#### `_enqueue(url, depth, lastmod, is_asset)` — Add to Frontier
1. Normalize URL.
2. Check domain scope (`allowed_domains`).
3. Check pattern scope (include/exclude regex).
4. Check robots.txt (thread-safe lookup).
5. Check in-memory dedup set.
6. Enqueue if all pass.

#### `run()` — Main Loop
1. Call `_seed()`.
2. Spawn N worker threads.
3. Wait for queue to empty (`queue.join()`).
4. Set stop flag; wait for workers to exit.
5. Close fetcher, store; return stats.

#### `_worker()` — Fetch & Process Loop
```python
while not stop_signal:
    task = queue.get(timeout=0.5)
    try:
        if budget_available():
            self._process(task)
    except RequestException:
        # Network error; log compact, increment stats
        store.upsert(url=task.url, error="network_error")
    except Exception:
        # Unexpected error; log + increment
        store.upsert(url=task.url, error="processing_error")
    finally:
        queue.task_done()
```

#### `_process(task)` — Fetch & Route
1. Check `robots.txt` allowed.
2. Fetch URL with conditional headers + redirect filter.
3. Handle redirect (blocked out-of-scope).
4. Handle 304 Not Modified (mark unchanged).
5. Handle 4xx/5xx (record error).
6. Route to `_handle_html()` or `_handle_asset()`.

#### `_handle_html(task, resp)` — Extract & Enqueue
1. Extract via `extract()`.
2. Check `noindex`; skip if present.
3. Extract & enqueue links (if `follow_links`).
4. Extract & enqueue assets (if `fetch_assets`).
5. Compute content hash.
6. Check duplicate hash (same content, new URL).
7. Check state DB for unchanged content (same URL, same hash).
8. Write JSONL document.
9. Update SQLite state.

#### `_handle_asset(task, resp)` — Extract Text & Save
1. Try text extraction (PDF via pypdf, TXT/CSV raw).
2. Save binary to `assets/<hash>.<ext>`.
3. Write JSONL document with `needs_extraction: true` for external processors (Tika).

---

## Concurrency & Threading

### Design

- **Producer**: Main thread orchestrates frontend (sitemap discovery, seed enqueuing).
- **Consumers**: N worker threads consume frontier queue, fetch URLs, extract content.
- **Synchronization**:
  - `queue.Queue` (thread-safe FIFO).
  - `threading.Lock` for in-memory dedup set, rate limiter, stats.
  - `RateLimiter` uses per-host event loop (lock + sleep).

### Worker Pool

```python
for i in range(config.max_workers):
    t = threading.Thread(target=self._worker, daemon=True)
    t.start()
self._queue.join()  # Blocks until all tasks processed
```

### Rate Limiting (Per-Host)

```
Host A          Host B          Host C
├─ time: 0s     ├─ time: 0s     ├─ time: 0s
│
W1 fetches A@0s
├─ next_free[A] = 0 + 1.0 = 1.0s

W2 fetches B@0s
├─ next_free[B] = 0 + 1.0 = 1.0s

W1 @ 0.5s tries A again
├─ now < next_free[A]; sleep 0.5s
├─ retry @ 1.0s → next_free[A] = 2.0s

W3 @ 1.0s tries A
├─ now >= next_free[A]; fetch
└─ next_free[A] = 2.0s
```

---

## URL Normalization & Deduplication

### Canonical Form

```python
"https://example.com:443/path/index.html?page=1&utm_source=social#anchor"
→ "https://example.com/path/"  # https default port omitted, index.html dropped, tracking param removed, anchor removed
```

### Tracking Params Removed

- `utm_*` (Google Analytics)
- `gclid`, `gclsrc` (Google Ads)
- `dclid` (DoubleClick)
- `fbclid` (Facebook)
- `msclkid` (Microsoft)
- `mc_*` (Mailchimp)
- `_hs*` (HubSpot)
- `ref`, `ref_src` (referrer)
- `gtm_latency` (GTM debug)
- `igshid` (Instagram)

### In-Memory Dedup

- `_seen` set: normalized URL → bool.
- Only populated during a single crawl run.
- Survives crashes/restarts via SQLite.

### Hash-Based Dedup

- SHA256 hash of page text.
- Stored in SQLite.
- Used to detect identical content under different URLs (even after redirects).

---

## Rate Limiting

### Per-Host Floor

```python
RateLimiter(default_delay=1.0)
```

All fetches to the same host wait 1.0s minimum (by hostname).

### Robots.txt Override

```python
delay = registry.crawl_delay(url)
if delay:
    limiter.set_delay(host, max(delay, default_delay))
```

robots.txt `Crawl-delay` can increase the floor but never decrease it.

### Implementation

```python
class RateLimiter:
    _next_free: dict[str, float] = {}  # host → unix timestamp
    _lock: threading.Lock
    
    def acquire(self, host: str):
        while True:
            with self._lock:
                now = time.monotonic()
                ready_at = self._next_free.get(host, 0.0)
                if now >= ready_at:
                    self._next_free[host] = now + self._delays[host]
                    return
                wait = ready_at - now
            time.sleep(wait)
```

---

## Robots.txt Compliance

### Checking Rules

```python
RobotFileParser.can_fetch(user_agent, url)
```

Applied at fetch time, not just URL matching:

1. Parse robots.txt at host origin.
2. Filter to rules matching your user_agent or `*`.
3. Check if URL matches any `Disallow` rule → false.
4. Return true if allowed.

### Example

```robots.txt
User-agent: MyBot
Disallow: /admin/

User-agent: *
Disallow: /temp/
Crawl-delay: 2
```

MyBot:
- Disallowed: `/admin/*`, `/temp/*`
- Crawl-delay: 2s

OtherBot:
- Disallowed: `/temp/*`
- No crawl-delay (default applies)

### Sitemap Discovery

```python
sitemaps = registry.sitemaps(url)
# Extract Sitemap: directives from robots.txt
```

Sitemaps are automatically prioritized in the frontier.

---

## Content Extraction Pipeline

### Step 1: Detect Content Type

```
Content-Type: text/html; charset=utf-8
↓
Is HTML? YES → Extract.Page
             NO (PDF/DOCX/etc.) → Save asset + basic extraction
```

### Step 2: Parse HTML

```python
soup = BeautifulSoup(html, "lxml")  # Tolerant parser
```

### Step 3: Metadata Extraction

```
<title>My Page</title>
<meta name="description" content="...">
<meta name="keywords" content="a,b,c">
<meta property="og:title" content="...">
<meta property="article:published_time" content="2025-06-01T...">
<link rel="canonical" href="...">
<html lang="en">
```

### Step 4: Main Content Selection

**Priority selectors** (most specific → most generic):
1. `<main>`
2. `<article>`
3. `[role=main]`
4. `#main`, `#content`
5. `.entry-content`, `.post-content`
6. Fall back to `<body>`

Pick the selector with the most text (≥200 chars).

### Step 5: Boilerplate Removal

Delete:
- Tags: script, style, noscript, template, svg, iframe, form, button.
- Containers: nav, header, footer, aside.
- By class/ID: breadcrumb, navbar, sidebar, footer, cookie, banner, popup, modal, subscribe, newsletter, social, share, related, comment, advert, promo, skip-link.
- aria-hidden="true" regions.

### Step 6: Link & Asset Extraction

All `<a href>` targets:
- If ends in `.pdf`, `.docx`, `.pptx`, `.doc`, `.ppt`, `.txt`, `.csv` → assets list.
- Else → links list.

### Step 7: Text Cleaning

```python
text = "Hello  World   \n\n\n   Foo Bar"
text = WHITESPACE.sub(" ", text)  # Collapse spaces
text = BLANK_LINES.sub("\n\n", text)  # Collapse newlines
# → "Hello World\n\nFoo Bar"
```

---

## Incremental Crawling

### Design

Two-tier change detection:

1. **Server-side** (ETag/Last-Modified):
   - Fetch with `If-None-Match` + `If-Modified-Since` from prior crawl.
   - Server returns 304 → content unchanged.
   - Skip processing; count as `unchanged`.

2. **Content-side** (Hash):
   - Fetch new content.
   - SHA256 hash of clean text.
   - Compare to prior hash in SQLite.
   - Same hash → `unchanged` (content refetched but identical).
   - Different hash → re-index (new document).

### Workflow

**First Crawl**:
```
1. Fetch https://example.com/page1
2. Extract text; hash = "abc123"
3. Write JSONL; insert SQLite:
   INSERT INTO pages (url, content_hash, last_crawled, ...)
   VALUES ("https://example.com/page1", "abc123", now, ...)
```

**Second Crawl** (24 hours later):
```
1. Fetch https://example.com/page1 WITH If-None-Match: "etag-val"
2. Server returns 304 → Skip extraction; update SQLite:
   UPDATE pages SET last_crawled = now WHERE url = "..."
   
   OR
   
   Server returns 200 with content → Extract; hash = "abc123"
   Hash matches DB → Skip re-indexing; mark as unchanged
   
   OR
   
   Hash differs → New document; index again
```

### Benefits

- **Speed**: 80–90% of pages unchanged on typical sites → skip re-indexing.
- **Freshness**: Only changed pages re-processed → no stale data in index.
- **Storage**: No duplicate documents in output.

### State Tracking

```sql
first_seen      2026-08-26T13:51:00Z     (never changes)
last_crawled    2026-08-26T13:52:30Z     (updated each run)
last_changed    2026-08-26T13:52:30Z     (only if hash differs)
content_hash    "7f8a9b0c..."           (SHA256 of text)
etag            "W/\"abc-123\""         (HTTP ETag)
last_modified   "Tue, 26 Aug 2026..."   (HTTP Last-Modified)
```

---

## Error Handling & Resilience

### Network Errors

| Error | Retry? | Action |
|-------|--------|--------|
| Connection timeout | Yes (2x backoff) | Log, re-fetch, store `network_error` |
| DNS failure | Yes (2x backoff) | Log, re-fetch, store `network_error` |
| SSL/TLS error | Yes (2x backoff) | Log, re-fetch, store `network_error` |
| Max retries exceeded | No | Log warning, store `network_error`, continue |

### HTTP Errors

| Status | Action |
|--------|--------|
| 301/302/303/307/308 | Follow if in-scope; record as `skipped_redirect` if out-of-scope |
| 304 Not Modified | Mark as `unchanged`; skip extraction |
| 4xx (400, 404, 410, 403) | Record error; increment `errors`; continue |
| 5xx (500, 502, 503, 504) | Retry with backoff; if exhausted, record `error` |

### Parse Errors

| Error | Action |
|-------|--------|
| Malformed HTML | BeautifulSoup tolerates; extract best-effort |
| Malformed XML (sitemap) | Log warning; skip that sitemap |
| Encoding error | Fall back to `errors="replace"` (lossy but safe) |
| PDF extraction fails | Log debug; store `needs_extraction: true` |

### Graceful Degradation

- Oversized response (>20 MB) → truncate with warning.
- Missing metadata → use defaults ("", [], etc.).
- robots.txt fetch fails → assume permissive (no restrictions).
- robots.txt returns 403 → assume disallow-all (conservative).

---

## Performance Considerations

### Throughput Tuning

```yaml
request_delay: 1.0       # ↓ fewer errors, ↓ speed
request_delay: 0.1       # ↑ faster, ↑ risk of 429
max_workers: 4           # Good balance
max_workers: 16          # For very fast hosting
max_workers: 1           # Serial crawl (slow, safe)
```

### Memory Footprint

- URL dedup set: O(n crawled) ≈ 100 bytes/URL → 1M URLs ≈ 100 MB.
- Fetcher session pools: O(max_workers) ≈ 1 MB.
- SQLite in-memory caches: ≈10 MB.
- Typical: <500 MB for 1M-page crawl.

### Disk Space

- JSONL: 1–2 KB per page → 1M pages ≈ 1–2 GB.
- SQLite: 1 KB per URL → 1M URLs ≈ 1 GB.
- Assets: varies (PDFs, DOCX can be large).

### Network Efficiency

- Conditional requests (ETag/Last-Modified) save bandwidth.
- Deflate/gzip supported by requests library.
- Per-host rate limiting prevents 429 rate-limit errors.

### Parallel Fetch Strategies

**Thread Pool Size Recommendation**:
- 4 workers: safe default, 200–500 pages/min (1s delay).
- 8 workers: moderate, 400–1000 pages/min (0.5s delay).
- 16+ workers: aggressive, 1000+ pages/min (0.1s delay), risk of overwhelming server.

---

## Extension Points

### Custom Boilerplate Removal

Edit `extract.py::_strip_boilerplate()`:
```python
def _strip_boilerplate(root: Tag) -> None:
    for tag in root.find_all("aside", class_="sidebar-custom"):
        tag.decompose()
    # Add your site-specific selectors
```

### Custom Metadata Extraction

Edit `extract.py::extract()`:
```python
custom_field = soup.find("meta", attrs={"property": "custom:author"})
page.author = custom_field.get("content") if custom_field else ""
```

### Custom Retry Logic

Edit `fetcher.py::Fetcher._backoff()`:
```python
@staticmethod
def _backoff(resp: requests.Response, attempt: int) -> None:
    # Your custom backoff strategy
    time.sleep(...)
```

### Custom Charset Detection

Edit `fetcher.py::Response._sniff_encoding()`:
```python
def _sniff_encoding(self) -> str:
    # Your site-specific encoding logic
    return "..."
```

---

## Future Enhancements

- [ ] JavaScript rendering (Playwright/Puppeteer) for JS-heavy sites (FR-02).
- [ ] Advanced DOCX/PPTX extraction via Tika.
- [ ] Feed-based crawling (Atom/RSS for blogs).
- [ ] Session/login support (cookies, forms).
- [ ] Duplicate content detection (fuzzy hash).
- [ ] Structured data extraction (JSON-LD, microdata).
- [ ] Performance metrics dashboard.

---

## References

- [README.md](README.md) — User guide.
- [Website_Crawl_RAG_Requirements.md](Website_Crawl_RAG_Requirements.md) — Product requirements.
- `config/searchunify.yaml` — Example config.
- `urllib.robotparser` — Python stdlib.
- `BeautifulSoup4` — HTML parsing docs.
- RFC 9309 (robots.txt spec).
