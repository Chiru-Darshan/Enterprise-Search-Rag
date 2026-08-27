# Website Search + Agentic RAG Platform
## Requirements Specification (Scoped: Website Crawl Only)

### Version
1.0 (Scoped from Enterprise Agentic RAG Requirements v1.0)

### Author
Darshan

### Objective

Build a search platform that ingests content **exclusively from websites** (corporate sites, product sites, knowledge portals, documentation portals) and enables users to search across that content and receive:

- Relevant search results
- AI-generated answers
- Source citations
- Hybrid search (Keyword + Semantic)
- Agentic retrieval and validation

Enterprise system connectors (SharePoint, OneDrive, Teams, Confluence, Jira, ServiceNow, network shares) and identity/ACL integrations (Entra ID, RBAC, group-based authorization) are **out of scope** for this phase, since there is no enterprise-system content to protect. They can be reintroduced later if the platform expands beyond website content.

---

# Business Goals

## Primary Goals
- Unified search across one or more websites
- Reduce information discovery time for site content
- Improve search relevance using AI
- Provide grounded answers with citations
- Eliminate hallucinated responses

## Success Criteria
- Search relevance greater than existing site search (if any)
- AI answers generated only from crawled website content
- Responses include citations back to source URLs
- Search latency < 5 seconds

---

# Functional Requirements

## FR-01 Content Ingestion (Website Only)

System shall ingest content from:
- Corporate websites
- Product websites
- Knowledge portals
- Documentation portals

Document formats encountered on these sites:
- HTML
- PDF (linked documents)
- DOCX / PPTX / TXT / CSV (linked downloadable files, if present)

## FR-02 Website Crawling

System shall:
- Crawl websites recursively, respecting `robots.txt`
- Discover URLs from `sitemap.xml`
- Support JavaScript-rendered pages
- Support incremental crawling (recrawl on schedule)
- Detect changed pages (via hash/last-modified) to avoid re-processing unchanged content
- Avoid duplicate crawling (URL normalization, canonical tag handling)
- Respect crawl-delay / rate limits per domain
- Support configurable include/exclude URL patterns (scope crawl to specific paths or subdomains)

## FR-03 Document Processing

System shall:
- Extract main content from HTML pages
- Remove navigation, header, footer, cookie-banner, and boilerplate content
- Normalize text (encoding, whitespace, HTML entities)
- Extract metadata (title, meta description, canonical URL, last-modified date, breadcrumb/path)
- Enrich content with keywords, entities, and tags
- Extract and process linked documents (PDF, DOCX, PPTX, etc.) discovered during crawl

## FR-04 Chunking

### Standard Chunking
- Chunk Size: 1000 tokens
- Overlap: 150 tokens

### Semantic Chunking
- Headings
- Sections
- Topics

## FR-05 Embedding Generation

Supported Models:
- multilingual-e5-large
- bge-large-en-v1.5
- Azure OpenAI Embeddings

## FR-06 Search Indexing

Store:
- BM25 Search Data
- Embeddings
- Metadata (source URL, title, last crawled/modified date, content type)

*(No ACL/permission data required — website content is public.)*

## FR-07 Hybrid Search

Combine:
- Keyword Search (BM25)
- Semantic Search (Vector)
- Metadata Boosting
- Freshness Boosting (recently crawled/updated pages ranked higher)

## FR-08 Agentic Retrieval

Agents:
- Query Agent
- Retrieval Agent
- Reranking Agent
- Answer Agent
- Verification Agent (checks answer is grounded in crawled site content, flags unsupported claims)

## FR-09 Source Attribution

System shall:
- Cite the source URL(s) for every AI-generated answer
- Link citations to the specific page/section retrieved
- Indicate crawl/last-updated date alongside citations, so users can judge freshness

---

# Non-Functional Requirements

## Performance
- Search Response < 3 Seconds
- RAG Response < 5 Seconds

## Availability
- POC: 95%
- Production: 99.9%

## Scalability
- Up to 1M+ crawled pages/documents (adjustable based on site size)
- 5000+ Concurrent Users

## Compliance / Crawl Etiquette
- Honor `robots.txt` and `noindex` directives
- Configurable user-agent string and crawl rate to avoid overloading source sites

---

# Evaluation Requirements

## Search Metrics
- Precision@5
- Recall@10
- MRR
- NDCG@10

## RAG Metrics
- Faithfulness
- Context Recall
- Context Precision
- Answer Relevance
- Citation Accuracy

## Agent Metrics
- Tool Selection Accuracy
- Retrieval Success Rate
- Verification Success Rate
- Task Completion Rate

## Crawl Metrics
- Crawl Coverage (% of discoverable URLs successfully crawled)
- Crawl Freshness (avg. age of indexed content vs. live site)
- Duplicate/Near-Duplicate Rate

---

# Recommended Technology Stack

## Ingestion (Website Only)
- Crawl4AI (crawling + JS rendering)
- Apache Tika / Unstructured.io (for linked PDFs, DOCX, PPTX)

## Search Platform
- OpenSearch

## Embeddings
- multilingual-e5-large

## Reranking
- bge-reranker-v2-m3

## Agent Framework
- LangGraph

## LLM
### POC
- Groq / Qwen / Llama

### Enterprise
- Azure OpenAI GPT-4o
- Claude

## Backend
- Python
- FastAPI

## Frontend
### POC
- Streamlit

### Enterprise
- React
- Next.js
- TypeScript

## Observability
- OpenTelemetry
- Grafana
- OpenSearch Dashboards

---

# Deployment Architecture

## POC
- Oracle Cloud Free Tier
- Docker
- OpenSearch
- FastAPI
- Streamlit
- LangGraph Services

## Enterprise
- Kubernetes (AKS/EKS)
- OpenSearch Cluster
- Agent Services
- API Services
- Monitoring Stack

---

# Project Phases

## Phase 1
- Website Crawling
- Content Extraction
- OpenSearch Indexing
- Search UI

## Phase 2
- Hybrid Search
- Embedding Generation
- Reranking

## Phase 3
- RAG Answers
- Citations

## Phase 4
- Agentic Retrieval
- Verification Agent
- Confidence Scoring

## Phase 5 (Future — Out of Current Scope)
- Enterprise system integrations (SharePoint, OneDrive, Confluence, Jira, ServiceNow)
- Identity/security integration (Entra ID, RBAC, ACL filtering)
- Production hardening at enterprise scale

---

# Removed From Original Scope

For reference, the following items from the original Enterprise Agentic RAG spec are **excluded** here since they don't apply to a website-only crawl:

- Enterprise system connectors: SharePoint Online, OneDrive, Teams Files, Confluence, Jira, ServiceNow, Network File Shares
- Security/identity: Microsoft Entra ID, Azure AD, RBAC, ACL Filtering, Group-based Authorization
- Permission-aware response filtering
- ACL Information in the search index
- 10M+ document scalability target (reduced to reflect typical website corpus size — adjust upward if needed)
