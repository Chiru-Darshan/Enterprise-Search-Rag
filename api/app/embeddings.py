"""Embedding + reranking models (FR-05, FR-08 Reranking Agent)."""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from sentence_transformers import CrossEncoder, SentenceTransformer

from .config import settings


class Embedder:
    """Wraps sentence-transformer models; different families need different
    query/passage prefixing to hit their trained retrieval accuracy:
      - e5 (e.g. multilingual-e5-large): "query: "/"passage: " on both sides.
      - bge *-en-v1.5 (e.g. bge-small-en-v1.5): an instruction on the query only.
      - bge-m3 and others: no prefix needed.
    """

    _BGE_INSTRUCTION = "Represent this sentence for searching relevant passages: "

    def __init__(self, model_name: str) -> None:
        self.model = SentenceTransformer(model_name)
        name = model_name.lower()
        self._is_e5 = "e5" in name
        self._is_bge_v15 = "bge" in name and "v1.5" in name

    def _prefix_query(self, text: str) -> str:
        if self._is_e5:
            return f"query: {text}"
        if self._is_bge_v15:
            return f"{self._BGE_INSTRUCTION}{text}"
        return text

    def _prefix_passages(self, texts: list[str]) -> list[str]:
        return [f"passage: {t}" for t in texts] if self._is_e5 else texts

    def embed_query(self, text: str) -> list[float]:
        vec = self.model.encode([self._prefix_query(text)], normalize_embeddings=True)[0]
        return vec.tolist()

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        vecs = self.model.encode(self._prefix_passages(texts), normalize_embeddings=True)
        return np.asarray(vecs).tolist()

    @property
    def dimension(self) -> int:
        return self.model.get_sentence_embedding_dimension()


class Reranker:
    """Cross-encoder reranker (bge-reranker-v2-m3) for the Reranking Agent."""

    def __init__(self, model_name: str) -> None:
        self.model = CrossEncoder(model_name, max_length=512)

    def score(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        pairs = [(query, p) for p in passages]
        return [float(s) for s in self.model.predict(pairs)]


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    return Embedder(settings.embedding_model)


@lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    return Reranker(settings.reranker_model)
