"""LangGraph agentic RAG pipeline (FR-08).

Linear path: Query -> Retrieval -> Reranking -> Answer -> Verification.
Corrective loop (CRAG/Active-Retrieval + Multi-Query/RAG-Fusion, bounded by
`max_retries`): if Verification finds the answer isn't grounded, or nothing was
retrieved, fan out reworded query variants, re-retrieve with RRF fusion across
all of them, and re-run Reranking -> Answer -> Verification.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from .config import settings
from .embeddings import get_reranker
from .opensearch_client import get_client, hybrid_search, reciprocal_rank_fusion

log = logging.getLogger(__name__)


class RagState(TypedDict, total=False):
    query: str
    rewritten_query: str
    query_variants: list[str]
    retrieved: list[dict[str, Any]]
    reranked: list[dict[str, Any]]
    answer: str
    citations: list[dict[str, Any]]
    verification: dict[str, Any]
    retry_count: int


def _llm() -> BaseChatModel:
    """Answer Agent's LLM. `ollama` runs fully local/offline (default); `groq`
    trades local compute for a hosted API and needs GROQ_API_KEY."""
    if settings.llm_provider == "groq":
        from langchain_groq import ChatGroq

        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not set; add it to .env")
        return ChatGroq(model=settings.groq_model, api_key=settings.groq_api_key, temperature=0.1)

    if settings.llm_provider == "ollama":
        from langchain_ollama import ChatOllama

        # CPU inference on larger models (e.g. gemma4 8B) can take minutes per call.
        # num_ctx must be raised beyond Ollama's 4096 default, else long contexts (several
        # reranked chunks) leave no room to generate a full answer - see ollama_num_ctx docstring.
        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=0.1,
            timeout=300,
            num_ctx=settings.ollama_num_ctx,
        )

    raise RuntimeError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r} (expected 'ollama' or 'groq')")


def query_agent(state: RagState) -> RagState:
    """Normalize/expand the user's question (FR-08 Query Agent)."""
    query = state["query"].strip()
    # Cheap heuristic expansion; a full implementation could call the LLM to
    # rewrite ambiguous queries, but that adds latency for the common case.
    rewritten = query if len(query.split()) > 2 else f"{query} SearchUnify"
    return {"rewritten_query": rewritten}


def retrieval_agent(state: RagState) -> RagState:
    """Hybrid BM25 + kNN retrieval (FR-08 Retrieval Agent, FR-07 Hybrid Search)."""
    client = get_client()
    hits = hybrid_search(client, state["rewritten_query"], top_k=settings.retrieval_top_k)
    return {"retrieved": hits}


def multi_query_agent(state: RagState) -> RagState:
    """Fan out reworded query variants (Multi-Query/RAG-Fusion) for the retry pass.

    Only runs after Verification signals the first attempt wasn't grounded -
    the extra LLM call is worth paying for on a retry, not on every request.
    """
    system = (
        "Generate alternate phrasings of the user's question to widen search "
        "recall over a product documentation and marketing corpus. Return each "
        "variant on its own line, no numbering, no extra commentary."
    )
    prompt = f"Original question: {state['query']}\n\nGenerate {settings.multi_query_variants} variants:"
    response = _llm().invoke([SystemMessage(content=system), HumanMessage(content=prompt)])
    variants = [line.strip("-* \t") for line in response.content.splitlines() if line.strip()]
    variants = variants[: settings.multi_query_variants] or [state["rewritten_query"]]
    return {"query_variants": variants, "retry_count": state.get("retry_count", 0) + 1}


def fusion_retrieval_agent(state: RagState) -> RagState:
    """Retrieve for the original query + every variant, fused by RRF (RAG-Fusion)."""
    client = get_client()
    queries = [state["rewritten_query"], *state.get("query_variants", [])]
    rank_lists = [hybrid_search(client, q, top_k=settings.retrieval_top_k) for q in queries]
    fused = reciprocal_rank_fusion(rank_lists)[: settings.retrieval_top_k]
    return {"retrieved": fused}


def reranking_agent(state: RagState) -> RagState:
    """Cross-encoder rerank down to the top-N most relevant chunks (FR-08)."""
    hits = state.get("retrieved", [])
    if not hits:
        return {"reranked": []}
    reranker = get_reranker()
    scores = reranker.score(state["query"], [h["content"] for h in hits])
    ranked = sorted(zip(hits, scores), key=lambda hs: hs[1], reverse=True)
    top = [{**h, "rerank_score": float(s)} for h, s in ranked[: settings.rerank_top_k]]
    return {"reranked": top}


def _build_context(chunks: list[dict[str, Any]]) -> str:
    parts = []
    for i, c in enumerate(chunks, start=1):
        parts.append(f"[{i}] ({c.get('title', '')} — {c.get('section', '')})\n{c['content']}")
    return "\n\n".join(parts)


def answer_agent(state: RagState) -> RagState:
    """Generate a grounded answer with numbered citations (FR-08 Answer Agent, FR-09)."""
    chunks = state.get("reranked", [])
    if not chunks:
        return {
            "answer": "I couldn't find anything in the indexed corpus to answer that.",
            "citations": [],
        }

    context = _build_context(chunks)
    system = (
        "You are a support assistant. Answer ONLY using the numbered context below. "
        "Cite sources inline like [1], [2]. If the context doesn't contain the answer, "
        "say so explicitly instead of guessing."
    )
    prompt = f"Context:\n{context}\n\nQuestion: {state['query']}\n\nAnswer with citations:"
    response = _llm().invoke([SystemMessage(content=system), HumanMessage(content=prompt)])

    citations = [
        {"marker": f"[{i}]", "url": c.get("url"), "title": c.get("title"), "section": c.get("section")}
        for i, c in enumerate(chunks, start=1)
    ]
    if not response.content.strip():
        # Usually means num_ctx was exhausted (prompt + partial generation hit the context
        # window) and langchain_ollama collapsed the truncated stream to "" - see
        # settings.ollama_num_ctx. Surfacing this in logs makes future truncation visible
        # instead of silently shipping a blank answer that verification just flags as ungrounded.
        log.warning(
            "answer_agent got empty LLM content (done_reason=%s, prompt≈%d chars, %d context chunks) - "
            "likely context-window truncation; consider raising ollama_num_ctx or lowering rerank_top_k",
            response.response_metadata.get("done_reason"),
            len(prompt),
            len(chunks),
        )
    return {"answer": response.content, "citations": citations}


_CITED_SENTENCE_RE = re.compile(r"[^.!?\n]*\[\d+\][^.!?\n]*[.!?]?")
_VERDICT_RE = re.compile(r"^\s*(\d+)\s*:\s*(SUPPORTED|UNSUPPORTED)\s*-?\s*(.*)$", re.IGNORECASE)


def _split_cited_sentences(answer: str) -> list[tuple[str, list[str]]]:
    """Pull out (sentence, [citation markers]) pairs for every sentence that cites a source."""
    pairs = []
    for sentence in _CITED_SENTENCE_RE.findall(answer):
        markers = [f"[{m}]" for m in re.findall(r"\[(\d+)\]", sentence)]
        if markers:
            pairs.append((sentence.strip(), markers))
    return pairs


def _semantic_groundedness_check(
    cited_sentences: list[tuple[str, list[str]]], chunks_by_marker: dict[str, str]
) -> list[dict[str, Any]]:
    """LLM fact-check: is each cited sentence actually supported by its source chunk's
    text, not just does its citation number exist? Catches paraphrase drift/hallucination
    that syntactic marker-checking (does [n] point to a real chunk) can't see - e.g. an
    answer confidently attributing a claim to a source that says something different.
    """
    if not cited_sentences:
        return []

    max_chars = settings.verification_evidence_max_chars
    items = []
    for i, (sentence, markers) in enumerate(cited_sentences, start=1):
        evidence = "\n---\n".join(chunks_by_marker.get(m, "") for m in markers)[:max_chars]
        items.append(f"Claim {i}: {sentence}\nEvidence {i}:\n{evidence}")

    system = (
        "You are a strict fact-checker. For each numbered claim, decide if it is fully "
        "supported by its evidence text - not just topically related, but actually stated. "
        "Respond with exactly one line per claim in the format 'N: SUPPORTED' or "
        "'N: UNSUPPORTED - <short reason>'. Output nothing else."
    )
    prompt = "\n\n".join(items)
    response = _llm().invoke([SystemMessage(content=system), HumanMessage(content=prompt)])
    lines = {m.group(1): m for line in response.content.splitlines() if (m := _VERDICT_RE.match(line))}

    verdicts = []
    for i, (sentence, markers) in enumerate(cited_sentences, start=1):
        match = lines.get(str(i))
        # fail-open on unparseable output: don't let a formatting slip block a valid answer
        supported = True if match is None else match.group(2).upper() == "SUPPORTED"
        reason = "" if match is None else match.group(3).strip()
        verdicts.append({"claim": sentence, "citations": markers, "supported": supported, "reason": reason})
    return verdicts


def verification_agent(state: RagState) -> RagState:
    """Check citation validity (syntactic) and claim-level groundedness (semantic) (FR-08 Verification Agent)."""
    answer = state.get("answer", "")
    citations = state.get("citations", [])
    valid_markers = {c["marker"] for c in citations}
    used_markers = {f"[{m}]" for m in re.findall(r"\[(\d+)\]", answer)}

    unsupported_citations = sorted(used_markers - valid_markers)
    markers_valid = bool(used_markers) and not unsupported_citations

    claim_checks: list[dict[str, Any]] = []
    if markers_valid and settings.enable_semantic_verification:
        chunks_by_marker = {c["marker"]: chunk.get("content", "") for c, chunk in zip(citations, state.get("reranked", []))}
        claim_checks = _semantic_groundedness_check(_split_cited_sentences(answer), chunks_by_marker)
    unsupported_claims = [c for c in claim_checks if not c["supported"]]

    grounded = markers_valid and not unsupported_claims
    if not markers_valid:
        confidence = 0.5 if used_markers else 0.2
    elif claim_checks:
        confidence = round(1 - len(unsupported_claims) / len(claim_checks), 2)
    else:
        confidence = 1.0

    return {
        "verification": {
            "grounded": grounded,
            "citations_used": sorted(used_markers),
            "unsupported_citations": unsupported_citations,
            "unsupported_claims": [
                {"claim": c["claim"], "citations": c["citations"], "reason": c["reason"]} for c in unsupported_claims
            ],
            "confidence": confidence,
        }
    }


def should_retry(state: RagState) -> Literal["retry", "end"]:
    """Corrective-retrieval gate: retry once (max_retries) if nothing was
    retrieved, or the answer wasn't grounded in what was retrieved."""
    if state.get("retry_count", 0) >= settings.max_retries:
        return "end"
    verification = state.get("verification", {})
    weak_context = not state.get("reranked")
    ungrounded = not verification.get("grounded", False)
    return "retry" if (weak_context or ungrounded) else "end"


def build_graph():
    graph = StateGraph(RagState)
    graph.add_node("query_agent", query_agent)
    graph.add_node("retrieval_agent", retrieval_agent)
    graph.add_node("multi_query_agent", multi_query_agent)
    graph.add_node("fusion_retrieval_agent", fusion_retrieval_agent)
    graph.add_node("reranking_agent", reranking_agent)
    graph.add_node("answer_agent", answer_agent)
    graph.add_node("verification_agent", verification_agent)

    graph.set_entry_point("query_agent")
    graph.add_edge("query_agent", "retrieval_agent")
    graph.add_edge("retrieval_agent", "reranking_agent")
    graph.add_edge("reranking_agent", "answer_agent")
    graph.add_edge("answer_agent", "verification_agent")
    graph.add_conditional_edges(
        "verification_agent",
        should_retry,
        {"retry": "multi_query_agent", "end": END},
    )
    graph.add_edge("multi_query_agent", "fusion_retrieval_agent")
    graph.add_edge("fusion_retrieval_agent", "reranking_agent")
    return graph.compile()


_compiled_graph = None


def _get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def run_pipeline(query: str) -> RagState:
    return _get_graph().invoke({"query": query})


_NODE_LABELS = {
    "query_agent": "Query Agent",
    "retrieval_agent": "Retrieval Agent",
    "multi_query_agent": "Query Rewrite Agent (CRAG)",
    "fusion_retrieval_agent": "Retrieval Agent (RRF fusion, retry)",
    "reranking_agent": "Reranking Agent",
    "answer_agent": "Answer Agent",
    "verification_agent": "Verification Agent",
}


def _summarize_node(node: str, output: dict[str, Any]) -> str:
    """Human-readable one-liner describing what a node just produced, for live UI display."""
    if node == "query_agent":
        return f"Rewrote query to: \u201c{output.get('rewritten_query', '')}\u201d"
    if node in ("retrieval_agent", "fusion_retrieval_agent"):
        n = len(output.get("retrieved", []))
        return f"Found {n} candidate chunk{'s' if n != 1 else ''} via hybrid search (BM25 + kNN)"
    if node == "multi_query_agent":
        variants = output.get("query_variants", [])
        preview = "; ".join(variants[:3])
        return f"Generated {len(variants)} alternate phrasing(s): {preview}"
    if node == "reranking_agent":
        chunks = output.get("reranked", [])
        if not chunks:
            return "No chunks survived reranking (empty retrieval)"
        best = max(c.get("rerank_score", 0) for c in chunks)
        return f"Kept top {len(chunks)} chunk(s) after cross-encoder rerank (best score {best:.3f})"
    if node == "answer_agent":
        answer = output.get("answer", "")
        citations = output.get("citations", [])
        return f"Drafted a {len(answer)}-char answer citing {len(citations)} source(s)"
    if node == "verification_agent":
        v = output.get("verification", {})
        status = "grounded ✅" if v.get("grounded") else "NOT fully grounded ⚠️"
        return f"Verdict: {status} (confidence {v.get('confidence', 0):.0%})"
    return "done"


def run_pipeline_events(query: str):
    """Stream (phase, detail) events as the graph executes, then a final full-state event.

    Powers the UI's live "what is the agent doing right now" panel: LangGraph's
    `stream(..., stream_mode="updates")` yields one dict per node as soon as it
    finishes, keyed by node name -> its partial state update.
    """
    graph = _get_graph()
    state: RagState = {"query": query}

    for update in graph.stream({"query": query}, stream_mode="updates"):
        for node, output in update.items():
            state.update(output)
            yield {
                "type": "phase",
                "node": node,
                "label": _NODE_LABELS.get(node, node),
                "detail": _summarize_node(node, output),
            }

    yield {
        "type": "final",
        "query": query,
        "rewritten_query": state.get("rewritten_query", ""),
        "retrieved_chunks": state.get("retrieved", []),
        "answer": state.get("answer", ""),
        "citations": state.get("citations", []),
        "verification": state.get("verification", {}),
        "reranked_chunks": state.get("reranked", []),
        "retry_count": state.get("retry_count", 0),
        "query_variants": state.get("query_variants", []),
    }
