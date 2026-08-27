"""Streamlit POC UI: hybrid search + agentic RAG answers with citations (FR-07/FR-08/FR-09)."""

import json
import os

import requests
import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:8000")

st.set_page_config(page_title="SearchUnify RAG", page_icon="🔎", layout="wide")
st.title("🔎 SearchUnify Enterprise Search + Agentic RAG")

with st.sidebar:
    st.header("Backend")
    st.code(API_URL, language="text")
    try:
        health = requests.get(f"{API_URL}/health", timeout=5).json()
        st.success(f"OpenSearch: {health.get('opensearch_cluster', 'unknown')}")
    except Exception as exc:
        st.error(f"API unreachable: {exc}")

    try:
        cfg = requests.get(f"{API_URL}/config", timeout=5).json()
        st.caption("Config")
        st.json(cfg)
    except Exception:
        pass

mode = st.radio("Mode", ["Ask (agentic RAG)", "Search (hybrid, no LLM)"], horizontal=True)
query = st.text_input("Ask a question about SearchUnify", placeholder="How do I configure Salesforce search?")

if st.button("Submit", type="primary") and query.strip():
    if mode.startswith("Ask"):
        data = None
        error = None
        with st.status("Running agentic RAG pipeline...", expanded=True) as status:
            try:
                # generous timeout: CPU LLM inference runs answer + verification passes
                resp = requests.post(
                    f"{API_URL}/ask/stream", json={"query": query}, timeout=600, stream=True
                )
                resp.raise_for_status()
                for line in resp.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    event = json.loads(line)
                    if event["type"] == "phase":
                        status.update(label=f"Running: {event['label']}...")
                        st.write(f"**{event['label']}** — {event['detail']}")
                    elif event["type"] == "final":
                        data = event
                    elif event["type"] == "error":
                        error = event["detail"]
            except Exception as exc:
                error = str(exc)

            if error:
                status.update(label=f"Pipeline failed: {error}", state="error", expanded=True)
            else:
                status.update(label="Pipeline complete ✅", state="complete", expanded=False)

        if error:
            st.error(f"Request failed: {error}")

        if data:
            st.subheader("Answer")
            st.write(data["answer"])

            verification = data.get("verification", {})
            confidence = verification.get("confidence", 0)
            badge = "🟢" if confidence >= 0.9 else ("🟡" if confidence >= 0.5 else "🔴")
            st.caption(f"{badge} Confidence: {confidence:.0%} | Grounded: {verification.get('grounded')}")
            if verification.get("unsupported_citations"):
                st.warning(f"Unsupported citation markers: {verification['unsupported_citations']}")
            for claim in verification.get("unsupported_claims", []):
                st.warning(f"Not supported by {', '.join(claim['citations'])}: \"{claim['claim']}\"\n\n{claim.get('reason', '')}")

            if data.get("retry_count", 0) > 0:
                st.info(
                    f"🔁 Corrective retrieval triggered ({data['retry_count']} retry) — "
                    f"widened search with variants: {data.get('query_variants', [])}"
                )

            st.subheader("Citations")
            for c in data.get("citations", []):
                st.markdown(f"**{c['marker']}** [{c.get('title', c.get('url'))}]({c.get('url')}) — _{c.get('section', '')}_")

            st.divider()
            st.subheader("🔬 Pipeline trace — what each agent did")

            with st.expander("1️⃣ Query Agent — normalized/rewritten query"):
                st.markdown(f"**Original query:** {data['query']}")
                st.markdown(f"**Rewritten query sent to retrieval:** `{data.get('rewritten_query', data['query'])}`")

            with st.expander(f"2️⃣ Retrieval Agent — {len(data.get('retrieved_chunks', []))} hits (hybrid BM25 + kNN)"):
                st.caption("Raw hybrid-search results before reranking, in the order OpenSearch returned them.")
                for i, hit in enumerate(data.get("retrieved_chunks", []), start=1):
                    st.markdown(
                        f"**{i}. {hit.get('title', 'untitled')}** — _{hit.get('section', '')}_ "
                        f"(score={hit.get('score', hit.get('_score', 0)):.3f})"
                    )
                    st.caption(hit.get("url", ""))
                    st.text(hit.get("content", "")[:300])
                    st.divider()
                if not data.get("retrieved_chunks"):
                    st.warning("Nothing retrieved for this query.")

            with st.expander(f"3️⃣ Reranking Agent — top {len(data.get('reranked_chunks', []))} after cross-encoder scoring"):
                st.caption("Cross-encoder (bge-reranker-base) re-scored the retrieved chunks; these are what the Answer Agent actually saw, numbered [1][2]... to match citation markers.")
                for i, chunk in enumerate(data.get("reranked_chunks", []), start=1):
                    st.markdown(f"**[{i}] {chunk.get('title')}** — _{chunk.get('section')}_ (rerank_score={chunk.get('rerank_score', 0):.3f})")
                    st.caption(chunk.get("url", ""))
                    st.text(chunk.get("content", "")[:500])
                    st.divider()
                if not data.get("reranked_chunks"):
                    st.warning("No chunks survived reranking (nothing was retrieved).")

            with st.expander("4️⃣ Answer Agent — generated answer + citations"):
                st.caption("LLM answer, generated only from the numbered context shown above.")
                st.write(data["answer"])
                st.json(data.get("citations", []))

            with st.expander("5️⃣ Verification Agent — syntactic + semantic groundedness check"):
                st.caption(
                    "Syntactic: do cited [n] markers point to real chunks? "
                    "Semantic: does the LLM confirm each cited claim is actually supported by its source text?"
                )
                st.json(verification)
                if data.get("retry_count", 0) > 0:
                    st.markdown("**🔁 Retry Gate:** verification failed on the first pass, so the Query Rewriter "
                                f"generated variants and Retrieval + Reranking + Answer + Verification re-ran.")
                    st.markdown(f"**Query variants used on retry:** {data.get('query_variants', [])}")
                else:
                    st.markdown("**🔁 Retry Gate:** answer was grounded on the first pass — no retry needed.")
    else:
        with st.spinner("Hybrid search (BM25 + kNN)..."):
            try:
                resp = requests.post(f"{API_URL}/search", json={"query": query, "top_k": 10}, timeout=30)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                st.error(f"Request failed: {exc}")
                data = None

        if data:
            st.subheader(f"{len(data['results'])} results")
            for hit in data["results"]:
                st.markdown(f"**[{hit.get('title')}]({hit.get('url')})** — _{hit.get('section')}_ (score={hit.get('score', 0):.4f})")
                st.text(hit.get("content", "")[:400])
                st.divider()
