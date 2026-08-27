# Development Guide

Local dev stack for the Enterprise Search + Agentic RAG platform: **OpenSearch**
(hybrid search index, FR-06/FR-07) + **OpenSearch Dashboards**, a **FastAPI** backend
running the **LangGraph** agentic pipeline (FR-08), and a **Streamlit** UI (FR frontend,
POC per the requirements doc).

The **crawler and chunker stay host-side** (they already work as a venv-based CLI — see
[README.md](README.md) and [docs/CHUNKING_STRATEGY.md](docs/CHUNKING_STRATEGY.md)) and
write into `./data/`, which is mounted read-only into the `api` container so you can
ingest without re-architecting anything.

```
┌────────────┐   crawl/chunk (host venv)   ┌──────────────┐
│  crawler   │ ──────────────────────────► │ ./data/*.jsonl│
└────────────┘                             └──────┬───────┘
                                                   │ mounted read-only
                                                   ▼
┌────────────┐   /ask, /search   ┌─────────────────────────┐   bulk index   ┌────────────┐
│ Streamlit  │ ────────────────► │ FastAPI + LangGraph      │ ─────────────► │ OpenSearch │
│  (ui)      │ ◄──────────────── │ (embeddings + reranker)  │ ◄───────────── │ (+Dashboards)
└────────────┘                  └───────────┬─────────────┘   hybrid search └────────────┘
                                             │ generate answer (host.docker.internal:11434)
                                             ▼
                                   ┌───────────────────────┐
                                   │ Ollama (native, host)  │
                                   │ already running, gemma4│
                                   │ already pulled          │
                                   └───────────────────────┘
```

---

## Prerequisites

- **Podman** ≥ 4.0 with `podman compose` (or Docker Desktop — the compose file is
  spec-standard and works with either)
- ~4 GB free RAM for OpenSearch + the embedding/reranker models
- A free [Groq API key](https://console.groq.com/keys) for the Answer/Verification agents
  (POC LLM per the requirements doc)

Check your setup:

```powershell
podman --version
podman compose version   # or: podman-compose --version
```

If you only have `podman-compose` (the Python tool) instead of the built-in `podman
compose`, replace `podman compose` with `podman-compose` in every command below.

---

## 1. Configure secrets

```powershell
Copy-Item .env.example .env
notepad .env   # only needed if you switch LLM_PROVIDER to groq (set GROQ_API_KEY)
```

## 2. Start the stack

```powershell
podman compose up -d --build
```

First start downloads:
- OpenSearch + Dashboards images (~1 GB)
- The embedding model (`BAAI/bge-small-en-v1.5`, ~130 MB) and reranker
  (`BAAI/bge-reranker-base`, ~280 MB) into the `hf-cache` volume, on the **first**
  `/ask` or ingest call. These are the fast CPU-friendly defaults for local dev; see
  [Model choice](#model-choice--dev-speed-tradeoff) below to switch to the
  production-grade multilingual models.

Nothing is pulled for the LLM — Ollama and `gemma4` are already on the host.

Check everything is healthy:

```powershell
podman compose ps
curl http://localhost:9200/_cluster/health
curl http://localhost:8000/health
curl http://localhost:11434/api/tags   # host-native Ollama; should list gemma4
```

- OpenSearch: http://localhost:9200
- OpenSearch Dashboards: http://localhost:5601
- API docs (Swagger): http://localhost:8000/docs
- Streamlit UI: http://localhost:8501

## 3. Crawl + chunk (host-side, unchanged workflow)

```powershell
.\.venv\Scripts\Activate.ps1
python -m crawler --config config/searchunify.yaml
python chunk_corpus.py data/searchunify --chunk-size 700 --overlap 100
```

This produces `data/searchunify/chunks_<timestamp>.jsonl`.

## 4. Ingest chunks into OpenSearch

The `api` container mounts `./data` read-only at `/data`, so run the ingest script
inside the container (it already has the embedding model loaded):

```powershell
podman compose exec api python -m app.ingest /data/searchunify/chunks_<timestamp>.jsonl
```

Watch it index (this also triggers the embedding model download if it hasn't happened
yet):

```
2026-08-26 ... INFO ingest: Indexed batch 0-500 (500 ok, 0 errors)
2026-08-26 ... INFO ingest: Indexed batch 500-1000 (500 ok, 0 errors)
...
2026-08-26 ... INFO ingest: Done: 3889 indexed, 0 errors, total input 3889
```

Verify in OpenSearch directly:

```powershell
curl "http://localhost:9200/searchunify_chunks/_count"
```

Or browse in **OpenSearch Dashboards** → Discover → `searchunify_chunks`.

## 5. Query it

**Streamlit UI** (http://localhost:8501) — easiest way to try it, has both a plain
hybrid-search mode and the full agentic "Ask" mode with citations + confidence.

**Or via curl:**

```powershell
# Hybrid search only (BM25 + kNN via RRF), no LLM call
curl -X POST http://localhost:8000/search `
  -H "Content-Type: application/json" `
  -d '{"query": "how do I configure Salesforce search", "top_k": 5}'

# Full agentic pipeline: Query -> Retrieval -> Reranking -> Answer -> Verification
curl -X POST http://localhost:8000/ask `
  -H "Content-Type: application/json" `
  -d '{"query": "How do I enable escalation prediction?"}'
```

---

## Architecture notes

### Why RRF instead of OpenSearch's native hybrid search pipeline
`opensearch_client.hybrid_search()` runs a BM25 query and a kNN query separately, then
combines them client-side with Reciprocal Rank Fusion. This avoids provisioning an
OpenSearch search pipeline/normalization processor, which varies across OpenSearch
versions and plugin availability — one less moving part for a POC. Swap in the native
`hybrid` query + search pipeline later if you need server-side fusion at scale.

### The five FR-08 agents (`api/app/graph.py`)
| Agent | Node | What it does |
|---|---|---|
| Query Agent | `query_agent` | Normalizes/expands the raw question |
| Retrieval Agent | `retrieval_agent` | Hybrid search (FR-07) via OpenSearch |
| Reranking Agent | `reranking_agent` | Cross-encoder rerank (bge-reranker-base by default) to top-5 |
| Answer Agent | `answer_agent` | LLM (Ollama `gemma4` by default, or Groq) answers only from the retrieved context, with `[n]` citations |
| Verification Agent | `verification_agent` | Checks every citation marker in the answer maps to a real retrieved chunk; assigns a confidence score |

This is a LangGraph `StateGraph` — a linear chain for the POC, but structured so you can
later add conditional edges (e.g., re-retrieve if verification fails).

### Model choice / dev speed tradeoff
Defaults are **`BAAI/bge-small-en-v1.5`** (384-dim) + **`BAAI/bge-reranker-base`** —
fast on CPU (~410 MB total), English-only, good enough to validate the pipeline end to
end. The requirements doc's exact picks, **`intfloat/multilingual-e5-large`** (1024-dim)
and **`BAAI/bge-reranker-v2-m3`**, are multilingual and more accurate but ~4.4 GB and
noticeably slower on CPU. Switch by uncommenting in `.env`:

```
EMBEDDING_MODEL=intfloat/multilingual-e5-large
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
```

then delete the OpenSearch index (`curl -X DELETE localhost:9200/searchunify_chunks`)
and re-ingest, since the vector dimension changes (384 → 1024). No other code changes
are needed — `opensearch_client.ensure_index()` reads the dimension from whichever
model is loaded.

**Why not just drop the prefix logic for the small model?** `bge-*-en-v1.5` and
`e5-*` models are trained with different query/passage conventions, and skipping them
silently costs retrieval accuracy rather than erroring:

| Family | Query gets | Passage gets |
|---|---|---|
| `e5-*` (e.g. `multilingual-e5-large`) | `"query: " + text` | `"passage: " + text` |
| `bge-*-v1.5` (e.g. `bge-small-en-v1.5`) | `"Represent this sentence for searching relevant passages: " + text` | unmodified |
| `bge-m3`, others | unmodified | unmodified |

`api/app/embeddings.py::Embedder` detects the family from the model name and applies
the right convention automatically — this is why switching models is just an `.env`
change.

### GPU
The `api` Dockerfile installs CPU-only PyTorch. If you have an NVIDIA GPU available to
Podman (`--device nvidia.com/gpu=all` / CDI), swap the `torch` line in
`api/requirements.txt` for a CUDA wheel and add the appropriate `deploy.resources`
block to the `api` service in `compose.yaml`.

---

## Common tasks

**Rebuild after changing API code:**
```powershell
podman compose up -d --build api
```

**Tail logs:**
```powershell
podman compose logs -f api
```

**Reset the OpenSearch index (e.g., after a chunking or embedding-model change):**
```powershell
curl -X DELETE "http://localhost:9200/searchunify_chunks"
podman compose exec api python -m app.ingest /data/searchunify/chunks_<timestamp>.jsonl
```

**Full teardown (including data volumes):**
```powershell
podman compose down -v
```

**Stop without deleting data:**
```powershell
podman compose down
```

---

## Troubleshooting

**`GROQ_API_KEY is not set`** — edit `.env`, then `podman compose up -d --build api`
(env changes require a restart, not just a file edit).

**OpenSearch container exits immediately / `max virtual memory areas too low`** —
OpenSearch needs `vm.max_map_count >= 262144`. On Podman Desktop (WSL2), run inside the
podman machine:
```powershell
podman machine ssh
sudo sysctl -w vm.max_map_count=262144
```

**First `/ask` call times out** — the embedding + reranker models download on first use
(~4 GB total). Watch `podman compose logs -f api` for download progress; subsequent
calls are fast because `hf-cache` is a persistent volume.

**`/search` returns nothing** — check the index has data: `curl
localhost:9200/searchunify_chunks/_count`. If it's 0, run the ingest step (§4).
