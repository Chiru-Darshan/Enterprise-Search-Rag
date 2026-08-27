"""FastAPI backend: hybrid search (FR-07) + agentic RAG (FR-08)."""

from __future__ import annotations

import json
import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .config import settings
from .graph import run_pipeline, run_pipeline_events
from .opensearch_client import get_client, hybrid_search

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
log = logging.getLogger("app")
if os.getenv("LANGSMITH_TRACING") == "true":
    log.info("LangSmith tracing enabled → project: %s", os.getenv("LANGSMITH_PROJECT"))

app = FastAPI(title="SearchUnify RAG API", version="1.0")


class SearchRequest(BaseModel):
    query: str
    top_k: int = 10


class AskRequest(BaseModel):
    query: str


@app.get("/health")
def health() -> dict:
    try:
        info = get_client().info()
        return {"status": "ok", "opensearch_cluster": info.get("cluster_name")}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"OpenSearch unreachable: {exc}") from exc


@app.post("/search")
def search(req: SearchRequest) -> dict:
    """Hybrid search only (FR-07), no LLM — fast path for a search-results UI."""
    hits = hybrid_search(get_client(), req.query, top_k=req.top_k)
    return {"query": req.query, "results": hits}


@app.post("/ask")
def ask(req: AskRequest) -> dict:
    """Full agentic pipeline (FR-08): retrieve, rerank, answer, verify."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")
    try:
        result = run_pipeline(req.query)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "query": req.query,
        "rewritten_query": result.get("rewritten_query", ""),
        "retrieved_chunks": result.get("retrieved", []),
        "answer": result.get("answer", ""),
        "citations": result.get("citations", []),
        "verification": result.get("verification", {}),
        "reranked_chunks": result.get("reranked", []),
        "retry_count": result.get("retry_count", 0),
        "query_variants": result.get("query_variants", []),
    }


@app.post("/ask/stream")
def ask_stream(req: AskRequest) -> StreamingResponse:
    """Same pipeline as /ask, but emits one NDJSON line per agent phase as it
    completes, so a UI can show live progress instead of waiting on one big call.
    Each line is `{"type": "phase", "node": ..., "label": ..., "detail": ...}`;
    the last line is `{"type": "final", ...}` with the same payload shape as /ask."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    def event_gen():
        try:
            for event in run_pipeline_events(req.query):
                yield json.dumps(event) + "\n"
        except RuntimeError as exc:
            yield json.dumps({"type": "error", "detail": str(exc)}) + "\n"

    return StreamingResponse(event_gen(), media_type="application/x-ndjson")


@app.get("/config")
def config() -> dict:
    return {
        "opensearch_index": settings.opensearch_index,
        "embedding_model": settings.embedding_model,
        "reranker_model": settings.reranker_model,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.ollama_model if settings.llm_provider == "ollama" else settings.groq_model,
    }
