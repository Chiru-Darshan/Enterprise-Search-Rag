"""Environment-driven settings (FR-05/06/08 knobs)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    opensearch_url: str = "http://localhost:9200"
    opensearch_index: str = "searchunify_chunks"

    # Defaults are the small/dev models (fast on CPU). Override in .env for the
    # multilingual production models (intfloat/multilingual-e5-large,
    # BAAI/bge-reranker-v2-m3) - no code change needed, dimension is read
    # dynamically from whichever model loads.
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    reranker_model: str = "BAAI/bge-reranker-base"

    llm_provider: str = "ollama"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    # Ollama runs natively on the host, not as a container. This default suits
    # running the api directly on the host (e.g. `uvicorn app.main:app`);
    # compose.yaml overrides it to http://host.docker.internal:11434 for the
    # containerized api to reach the same host-native Ollama.
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma4"
    # Default Ollama context window (4096) is too small once ~5 reranked chunks are
    # packed into the prompt (~3-4K tokens) - it leaves so little room for the answer
    # that generation hits the context limit mid-sentence and langchain_ollama surfaces
    # that truncation as an EMPTY .content instead of the partial text. Raise it so a
    # full prompt + citation-laden answer both fit.
    ollama_num_ctx: int = 8192

    retrieval_top_k: int = 20
    rerank_top_k: int = 5

    # Corrective retrieval (CRAG-style): if the answer isn't grounded in the
    # retrieved context, fan out multi-query variants and retry once.
    max_retries: int = 1
    multi_query_variants: int = 3

    # Verification Agent: beyond checking citation numbers are valid, ask the LLM
    # whether each cited sentence is actually supported by its source chunk's text.
    # Costs one extra LLM call per query; disable for lower latency (e.g. slow CPU LLMs).
    enable_semantic_verification: bool = True
    verification_evidence_max_chars: int = 1200

    langsmith_api_key: str = ""
    langsmith_tracing: bool = False
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_project: str = "Enterprise Search with Agentic RAG support"


settings = Settings()
