# Documentation Index

Reference guide for the SearchUnify RAG corpus analysis and crawl infrastructure.

## 📊 Corpus Analysis

### [CORPUS_ANALYSIS.md](CORPUS_ANALYSIS.md)
**Complete breakdown of the crawled corpus**

- Crawl results and metrics (2,084 documents, 1.35M words, 35-minute run)
- Coverage by host (1,581 www + 503 docs pages)
- Content sections and freshness (86% from 2025–2026)
- Crawl outcomes (indexed, redirects, noindex, duplicates, errors)
- Known quality issues and mitigations
- Supported features (sitemaps, link following, robots.txt, JavaScript rendering, PDFs, incremental crawls)

**Read this if:** You need full metrics, audit details, or want to understand what was excluded and why.

---

### [CAPABILITIES.md](CAPABILITIES.md)
**What queries the corpus can answer**

- Query categories with examples
  - Product configuration & how-to
  - API & developer questions
  - Competitive analysis
  - Business outcomes & use cases
  - Concepts & education
  - Product news & announcements
- Partially supported (version-specific, legal)
- Not supported (internal knowledge, real-time, external content)
- Content quality notes and recommendations for embedding
- Coverage summary by category

**Read this if:** You're building a RAG application and want to understand query coverage and limitations upfront.

---

## 🔧 Crawl Infrastructure

### [../ARCHITECTURE.md](../ARCHITECTURE.md)
**System design and implementation details**

- Module breakdown (`crawler/`, `config.py`, `sitemap.py`, `extract.py`, `render.py`, `store.py`)
- Incremental crawling design
- JS rendering pipeline
- Extraction and deduplication logic
- State management (SQLite)

**Read this if:** You're maintaining or extending the crawler, or want to understand the technical architecture.

---

### [../README.md](../README.md)
**Quick start and usage**

- Setup and dependencies
- Configuration guide
- Basic crawl commands
- Output format and schema

**Read this if:** You're getting started or running a crawl for the first time.

---

## 📋 Quick Reference

### Run a Crawl

**Full crawl (first time):**
```bash
python -m crawler --config config/searchunify.yaml
```

**Delta crawl (refresh only changed pages):**
```bash
python -m crawler --config config/searchunify.yaml
```

**Rebuild all (after changing extraction logic):**
```bash
python -m crawler --config config/searchunify.yaml --full
```

### Analyze Results

```bash
python analyze_corpus.py data/searchunify --top 20
```

### View Audit Log

```bash
tail -f data/searchunify/logs/crawl_*.log
```

---

## 📊 Key Metrics (Latest Crawl)

| Metric | Value |
|--------|-------|
| Documents | 2,084 |
| Words | 1,350,420 |
| Hosts | 2 (www, docs) |
| Fetched | 3,811 |
| Indexed | 1,973 |
| Duration | 35 minutes |
| Freshness | 86% (2025–2026) |

---

## 🎯 Use Cases

### "I want to embed this corpus into my RAG system"
1. Read [CAPABILITIES.md](CAPABILITIES.md) to understand query coverage
2. Check [CORPUS_ANALYSIS.md](CORPUS_ANALYSIS.md) for quality notes
3. Review the footer CTA mitigation if using embeddings
4. Ingest `data/searchunify/documents_*.jsonl` into your vector store

### "I need to update the corpus (e.g., new product pages)"
1. Run `python -m crawler --config config/searchunify.yaml` (delta mode)
2. Ingest new `documents_*.jsonl` into your vector store (upsert by URL)
3. See [../ARCHITECTURE.md](../ARCHITECTURE.md) for incremental design details

### "I want to change how content is extracted"
1. Edit `crawler/extract.py` (e.g., add footer CTA selector)
2. Run with `--full` flag to re-emit all pages
3. Ingest the new JSONL to update embeddings

### "I need to debug a crawl issue"
1. Check the audit log: `tail data/searchunify/logs/crawl_*.log | grep DECISION`
2. Search for specific URLs or error patterns
3. Review [../ARCHITECTURE.md](../ARCHITECTURE.md) for the decision pipeline

---

## 📦 Output Files

After a crawl completes:

| File | Purpose |
|------|---------|
| `data/searchunify/documents_<ts>.jsonl` | Main corpus (one JSON object per line) |
| `data/searchunify/crawl_state.sqlite` | State DB (URL history, hashes, ETags) |
| `data/searchunify/logs/crawl_<ts>.log` | DEBUG audit trail (per-URL decisions) |
| `console_last_run.log` | Human-readable progress output |

**For RAG ingestion:** Use only `documents_*.jsonl`

**For debugging:** Use `logs/crawl_*.log`

**For resuming:** Keep `crawl_state.sqlite` (remove to start fresh)

---

## ❓ FAQ

**Q: How long does a crawl take?**  
A: ~35 minutes for a full 3,811 URL crawl. Incremental deltas take 2–5 minutes.

**Q: Can I crawl private/authenticated content?**  
A: Not yet. Would require session management (out of scope currently).

**Q: What about archived content (e.g., older release notes)?**  
A: 926 versioned pages in `/Q4-25/`, `/Q1-26/` are excluded to avoid version confusion in RAG answers. Can be included separately with version tags if needed.

**Q: How do I handle the footer CTA noise?**  
A: Add a selector to `BOILERPLATE_SELECTORS` in `crawler/extract.py`:
```python
"footer .cta-section",  # SearchUnify footer CTA
```
Then run with `--full` to re-emit.

**Q: Can I run multiple crawls concurrently?**  
A: Not recommended; they share `crawl_state.sqlite`. Use one machine per site or separate config directories.

**Q: How do I know what's new in a delta crawl?**  
A: Check the audit log for `DECISION indexed` (newly indexed) vs. `DECISION unchanged_304` (skipped).

---

## 📝 Metadata Schema

Each document in `documents_*.jsonl` includes:

```json
{
  "url": "https://...",
  "title": "...",
  "text": "...",
  "headings": ["...", "..."],
  "links": [{"href": "...", "text": "..."}, ...],
  "canonical_url": "...",
  "content_type": "text/html",
  "language": "en-US",
  "published_at": "2026-08-20T...",
  "modified_at": "2026-08-25T...",
  "image": "...",
  "js_rendered": false,
  "source_type": "page",
  "crawled_at": "2026-08-26T22:27:56+00:00",
  "word_count": 533,
  "depth": 1
}
```

See [../README.md](../README.md) for full schema details.

---

**Last updated:** 2026-08-26  
**Corpus version:** Full crawl (fresh, 2,084 documents)
