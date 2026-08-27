# SearchUnify Corpus Capabilities

Quick reference for what queries the RAG corpus can answer, organized by use case.

## ✅ Fully Supported Query Categories

### Product Configuration & How-To
- "How do I set up Salesforce search integration?"
- "What are the authentication options for Agent Helper?"
- "How do I configure ML Workbench for case classification?"
- "What content sources does SearchUnify support?"
- "How do I enable escalation prediction?"
- "Configuration best practices for multi-language support"

**Source:** 501 docs pages + API references

---

### API & Developer Questions
- "What is the Java SDK endpoint for analytics?"
- "How do I authenticate REST API calls?"
- "What are the rate limits for the Analytics API?"
- "Document the search API request/response schema"
- "Java SDK dependency management"

**Source:** Java SDK docs, Analytics API docs, release notes

---

### Competitive Analysis & Evaluation
- "How does SearchUnify compare to Coveo?"
- "Why choose SearchUnify over Elasticsearch?"
- "What makes cognitive search different?"
- "Feature comparison: SearchUnify vs Typesense"
- "Is SearchUnify better for customer service automation?"

**Source:** 1,062 comparison pages, benchmarks, case studies

---

### Business Outcomes & Use Cases
- "How does SearchUnify reduce support ticket volume?"
- "What is case deflection and why does it matter?"
- "ROI of enterprise search implementations"
- "How do AI agents improve first-contact resolution?"
- "Reducing customer service costs with intelligent search"

**Source:** Resource center, whitepapers, case studies

---

### Concepts & Education
- "What is cognitive search?"
- "Difference between semantic and keyword search"
- "How do LLMs enhance search results?"
- "Explain knowledge management in enterprise context"
- "What is escalation prediction?"

**Source:** Gen AI/LLM Glossary (6,437 words), concept guides

---

### Product News & Announcements
- "When was SearchUnify named a G2 Leader?"
- "Which strategic partners does SearchUnify have?"
- "Recent AI feature announcements"
- "Mamba release notes and upgrade guide"
- "Customer success stories and wins"

**Source:** 245 press releases, 461 rendered marketing pages

---

## ⚠️ Partially Supported

### Version-Specific Questions
- "Configuration in Mamba 21 vs Colubridae 21" ✅ **covered**
- "Migration guide from Mamba 20 to Mamba 21" ✅ **covered**
- "Q4-25 release features" ❌ **archived (not indexed)**

Note: Current release versions are fully documented; historical releases are archived separately to avoid version confusion.

---

### Legal/Policy Questions
- "What is SearchUnify's privacy policy?"
- "Do you comply with GDPR?"
- "Data retention policies"
- "Cookie usage and consent"

**Source:** 4 legal pages (limited detail)

---

## ❌ Not Supported (Out of Scope)

### Internal/Proprietary Knowledge
- Customer-specific configurations
- Internal pricing details
- Private roadmap items
- Sales enablement materials

**Reason:** Not publicly crawled; would require authenticated access

---

### Real-Time Information
- Current stock price
- Live system status
- Real-time customer metrics
- Today's schedule

**Reason:** Crawl is snapshot-based; no continuous monitoring

---

### External Content
- Competitor product docs (only comparisons to SearchUnify)
- General industry news (only SearchUnify news indexed)
- Academic papers (not in scope)

**Reason:** Crawler limited to `www.searchunify.com` and `docs.searchunify.com`

---

### Unsupported Media Types
- Videos (marketing videos on site not transcribed)
- Podcasts (referenced but not indexed)
- Archived release recordings

**Reason:** Text-based extraction only

---

## Content Quality Notes

### Strengths ✅
- **86% fresh** (2025–2026 modifications)
- **1.35M words** (substantial coverage)
- **Median 533 words/page** (substantial documents)
- **Structured metadata** (titles, dates, authors extracted)
- **Link context** (related pages discoverable)

### Known Issues ⚠️
- **Footer CTA noise:** ~262 pages include site-wide footer text in headings (fixable with CSS selector)
- **Tag/author archives:** WordPress `/tag/` and `/author/` pages excluded (by design; minimal unique content)
- **102 thin pages:** <100 words each (edge cases; mostly navigation)

### Recommendations for Use
1. **Embed with cleanup:** Apply the footer CTA selector before vectorizing to reduce noise
2. **Chunk by section:** Large pages (max 9,051 words) benefit from hierarchical chunking on headings
3. **Language filtering:** 97% English; 2% unset language (minor; apply language tag in metadata if needed)
4. **Version awareness:** Prefix version in queries ("Mamba 21") for release-specific accuracy

---

## Coverage Summary

| Category | Pages | Coverage |
|----------|-------|----------|
| Product docs | 501 | ✅ Complete |
| Marketing/blogs | 1,062 | ✅ Complete |
| Press/news | 245 | ✅ Complete |
| APIs | 111 | ✅ Complete (PDFs) |
| Educational | ~100 | ✅ Complete |
| Legal | 4 | ✅ Basic |

**Total:** 2,084 documents across 2 hosts, 3,811 URLs crawled, 35-minute crawl cycle

---

For detailed metrics, freshness timeline, and audit logs, see **[CORPUS_ANALYSIS.md](CORPUS_ANALYSIS.md)**.
