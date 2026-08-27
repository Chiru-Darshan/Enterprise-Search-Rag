"""OpenSearch index mapping + hybrid search (FR-06/FR-07)."""

from __future__ import annotations

import logging
from typing import Any

from opensearchpy import OpenSearch, helpers

from .config import settings
from .embeddings import get_embedder

log = logging.getLogger(__name__)


def get_client() -> OpenSearch:
    return OpenSearch(hosts=[settings.opensearch_url], timeout=30, max_retries=3, retry_on_timeout=True)


def ensure_index(client: OpenSearch, dimension: int) -> None:
    """Create the index with BM25 text fields + a kNN vector field (FR-06)."""
    if client.indices.exists(index=settings.opensearch_index):
        return
    body = {
        "settings": {
            "index": {"knn": True, "number_of_shards": 1, "number_of_replicas": 0},
            "analysis": {"analyzer": {"default": {"type": "english"}}},
        },
        "mappings": {
            "properties": {
                "chunk_id": {"type": "keyword"},
                "parent_id": {"type": "keyword"},
                "chunk_index": {"type": "integer"},
                "url": {"type": "keyword"},
                "canonical_url": {"type": "keyword"},
                "title": {"type": "text"},
                "section": {"type": "text"},
                "content": {"type": "text"},
                "content_embedding": {
                    "type": "knn_vector",
                    "dimension": dimension,
                    "method": {
                        "name": "hnsw",
                        "engine": "faiss",
                        # faiss hnsw only supports l2/innerproduct; cosinesimil is nmslib/lucene-only
                        "space_type": "innerproduct",
                        "parameters": {"ef_construction": 128, "m": 16},
                    },
                },
                "token_count": {"type": "integer"},
                "source_type": {"type": "keyword"},
                "content_type": {"type": "keyword"},
                "published_at": {"type": "date", "ignore_malformed": True},
                "modified_at": {"type": "date", "ignore_malformed": True},
                "crawled_at": {"type": "date", "ignore_malformed": True},
                "breadcrumbs": {"type": "keyword"},
            }
        },
    }
    client.indices.create(index=settings.opensearch_index, body=body)
    log.info("Created index %s (dim=%d)", settings.opensearch_index, dimension)


def bulk_index(client: OpenSearch, chunks: list[dict[str, Any]]) -> tuple[int, int]:
    """Embed + upsert chunks. Returns (success_count, error_count)."""
    embedder = get_embedder()
    ensure_index(client, embedder.dimension)

    vectors = embedder.embed_passages([c["content"] for c in chunks])
    actions = [
        {
            "_op_type": "index",
            "_index": settings.opensearch_index,
            "_id": chunk["chunk_id"],
            "_source": {**chunk, "content_embedding": vector},
        }
        for chunk, vector in zip(chunks, vectors)
    ]
    success, errors = helpers.bulk(client, actions, raise_on_error=False, chunk_size=200)
    return success, len(errors)


def reciprocal_rank_fusion(rank_lists: list[list[dict[str, Any]]], key: str = "chunk_id", k: int = 60) -> list[dict[str, Any]]:
    """Merge N ranked hit lists (from BM25, kNN, or multiple query variants) by RRF.

    RRF only needs each list's rank order, not comparable score scales, which is
    why it composes cleanly across both BM25-vs-kNN fusion and multi-query fusion.
    """
    scores: dict[str, float] = {}
    docs: dict[str, dict[str, Any]] = {}
    for rank_list in rank_lists:
        for rank, doc in enumerate(rank_list):
            doc_id = doc[key]
            docs[doc_id] = doc
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [{**docs[doc_id], "score": score} for doc_id, score in ranked]


def hybrid_search(client: OpenSearch, query: str, top_k: int = 20) -> list[dict[str, Any]]:
    """BM25 + kNN, combined client-side via Reciprocal Rank Fusion (FR-07).

    RRF (rather than OpenSearch's server-side hybrid search pipeline) keeps this
    portable across OpenSearch versions/plugins for a dev/POC deployment.
    """
    embedder = get_embedder()
    query_vector = embedder.embed_query(query)

    bm25 = client.search(
        index=settings.opensearch_index,
        body={
            "size": top_k,
            "query": {"multi_match": {"query": query, "fields": ["content^2", "title^1.5", "section"]}},
        },
    )
    knn = client.search(
        index=settings.opensearch_index,
        body={"size": top_k, "query": {"knn": {"content_embedding": {"vector": query_vector, "k": top_k}}}},
    )

    rank_lists = [
        [{**hit["_source"], "chunk_id": hit["_id"]} for hit in result["hits"]["hits"]]
        for result in (bm25, knn)
    ]
    return reciprocal_rank_fusion(rank_lists)[:top_k]
