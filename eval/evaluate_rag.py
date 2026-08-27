"""RAG evaluation harness.

Computes the metrics called out in the requirements doc's "Evaluation Requirements"
section, split into the same three layers:

  Search/Retrieval : Precision@5, Recall@10, MRR, NDCG@10   (needs /search + golden urls)
  RAG/Answer       : Faithfulness, Citation Accuracy, Answer Non-Emptiness
                     (Context Precision/Recall + Answer Relevance are LLM-judged, see below)
  Agent            : Retrieval Success Rate, Verification Success Rate, Task Completion Rate

Faithfulness and citation accuracy are read straight from the pipeline's own
verification_agent() output (api/app/graph.py) rather than re-implemented here - that
agent already does per-claim LLM fact-checking, so re-scoring it independently would
just be a second, weaker copy of the same check.

Usage:
    python eval/evaluate_rag.py
    python eval/evaluate_rag.py --testset eval/testset.yaml --api http://localhost:8000
    python eval/evaluate_rag.py --skip-ask          # retrieval metrics only, much faster
    python eval/evaluate_rag.py --output eval/results.json
"""

from __future__ import annotations

import argparse
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests
import yaml

DEFAULT_API = "http://localhost:8000"
DEFAULT_TESTSET = Path(__file__).parent / "testset.yaml"
NO_ANSWER_MARKER = "couldn't find anything in the indexed corpus"


def _normalize_url(url: str) -> str:
    """Strip fragment/trailing slash so '#section' variants of the same doc match."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _dedupe_by_url(hits: list[dict[str, Any]]) -> list[str]:
    """Collapse multiple chunks from the same document into one ranked list of URLs."""
    seen: list[str] = []
    for hit in hits:
        u = _normalize_url(hit.get("url", ""))
        if u and u not in seen:
            seen.append(u)
    return seen


def precision_at_k(ranked_urls: list[str], relevant: set[str], k: int) -> float:
    if k == 0:
        return 0.0
    top_k = ranked_urls[:k]
    hits = sum(1 for u in top_k if u in relevant)
    return hits / k


def recall_at_k(ranked_urls: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 1.0  # nothing to find, and nothing expected -> trivially satisfied
    top_k = ranked_urls[:k]
    found = sum(1 for u in relevant if u in top_k)
    return found / len(relevant)


def reciprocal_rank(ranked_urls: list[str], relevant: set[str]) -> float:
    for i, u in enumerate(ranked_urls, start=1):
        if u in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked_urls: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 1.0
    dcg = sum(1.0 / math.log2(i + 1) for i, u in enumerate(ranked_urls[:k], start=1) if u in relevant)
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0


def load_testset(path: Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        cases = yaml.safe_load(f) or []
    for c in cases:
        c.setdefault("expected_urls", [])
        c.setdefault("expect_answer", bool(c["expected_urls"]))
    return cases


def evaluate(api: str, cases: list[dict[str, Any]], top_k: int, skip_ask: bool) -> dict[str, Any]:
    per_query: list[dict[str, Any]] = []

    for case in cases:
        query = case["query"]
        relevant = {_normalize_url(u) for u in case["expected_urls"]}
        row: dict[str, Any] = {"query": query, "expected_urls": sorted(relevant)}

        # --- Retrieval metrics via /search (no LLM, fast, cheap to run every time) ---
        t0 = time.time()
        try:
            resp = requests.post(f"{api}/search", json={"query": query, "top_k": top_k}, timeout=30)
            resp.raise_for_status()
            hits = resp.json().get("results", [])
        except Exception as exc:
            row["error"] = f"/search failed: {exc}"
            per_query.append(row)
            continue
        ranked_urls = _dedupe_by_url(hits)

        row["retrieval_latency_s"] = round(time.time() - t0, 2)
        row["precision_at_5"] = round(precision_at_k(ranked_urls, relevant, 5), 3)
        row["recall_at_10"] = round(recall_at_k(ranked_urls, relevant, 10), 3)
        row["mrr"] = round(reciprocal_rank(ranked_urls, relevant), 3)
        row["ndcg_at_10"] = round(ndcg_at_k(ranked_urls, relevant, 10), 3)
        row["retrieval_success"] = bool(hits)

        # --- RAG + Agent metrics via /ask (slow: LLM answer + verification passes) ---
        if not skip_ask:
            t0 = time.time()
            try:
                resp = requests.post(f"{api}/ask", json={"query": query}, timeout=600)
                resp.raise_for_status()
                ask = resp.json()
            except Exception as exc:
                row["error"] = f"/ask failed: {exc}"
                per_query.append(row)
                continue

            verification = ask.get("verification", {})
            answer = ask.get("answer", "")
            said_no_answer = NO_ANSWER_MARKER in answer

            row["ask_latency_s"] = round(time.time() - t0, 2)
            row["retry_count"] = ask.get("retry_count", 0)
            row["grounded"] = verification.get("grounded", False)
            row["confidence"] = verification.get("confidence", 0.0)  # faithfulness proxy
            row["citation_accuracy"] = not verification.get("unsupported_citations")
            row["said_no_answer"] = said_no_answer
            row["task_completed"] = (
                (not said_no_answer and row["grounded"]) if case["expect_answer"] else said_no_answer
            )

        per_query.append(row)

    return {"per_query": per_query, "summary": summarize(per_query, skip_ask)}


def _avg(rows: list[dict[str, Any]], key: str) -> float:
    values = [r[key] for r in rows if key in r]
    return round(statistics.mean(values), 3) if values else 0.0


def _rate(rows: list[dict[str, Any]], key: str) -> float:
    values = [bool(r[key]) for r in rows if key in r]
    return round(sum(values) / len(values), 3) if values else 0.0


def summarize(rows: list[dict[str, Any]], skip_ask: bool) -> dict[str, Any]:
    ok_rows = [r for r in rows if "error" not in r]
    summary = {
        "total_queries": len(rows),
        "errored_queries": len(rows) - len(ok_rows),
        "search_metrics": {
            "precision_at_5": _avg(ok_rows, "precision_at_5"),
            "recall_at_10": _avg(ok_rows, "recall_at_10"),
            "mrr": _avg(ok_rows, "mrr"),
            "ndcg_at_10": _avg(ok_rows, "ndcg_at_10"),
            "avg_retrieval_latency_s": _avg(ok_rows, "retrieval_latency_s"),
        },
        "agent_metrics": {
            "retrieval_success_rate": _rate(ok_rows, "retrieval_success"),
        },
    }
    if not skip_ask:
        summary["rag_metrics"] = {
            "faithfulness_avg_confidence": _avg(ok_rows, "confidence"),
            "citation_accuracy_rate": _rate(ok_rows, "citation_accuracy"),
        }
        summary["agent_metrics"].update(
            {
                "verification_success_rate": _rate(ok_rows, "grounded"),
                "task_completion_rate": _rate(ok_rows, "task_completed"),
                "avg_retry_count": _avg(ok_rows, "retry_count"),
                "avg_ask_latency_s": _avg(ok_rows, "ask_latency_s"),
            }
        )
    return summary


def print_report(result: dict[str, Any]) -> None:
    summary = result["summary"]
    print("\n" + "=" * 60)
    print("RAG EVALUATION REPORT")
    print("=" * 60)
    print(f"Queries evaluated: {summary['total_queries']} (errors: {summary['errored_queries']})")

    print("\n--- Search / Retrieval Metrics ---")
    for k, v in summary["search_metrics"].items():
        print(f"  {k:30s} {v}")

    if "rag_metrics" in summary:
        print("\n--- RAG / Answer Metrics ---")
        for k, v in summary["rag_metrics"].items():
            print(f"  {k:30s} {v}")

    print("\n--- Agent Metrics ---")
    for k, v in summary["agent_metrics"].items():
        print(f"  {k:30s} {v}")

    print("\n--- Per-query breakdown ---")
    for row in result["per_query"]:
        if "error" in row:
            print(f"  [ERROR] {row['query']!r}: {row['error']}")
            continue
        flags = []
        if not skip_ask_flag(row):
            flags.append("grounded" if row.get("grounded") else "UNGROUNDED")
            if row.get("retry_count"):
                flags.append(f"retried x{row['retry_count']}")
            if not row.get("task_completed"):
                flags.append("TASK-FAILED")
        print(
            f"  P@5={row['precision_at_5']:.2f} R@10={row['recall_at_10']:.2f} "
            f"MRR={row['mrr']:.2f} NDCG@10={row['ndcg_at_10']:.2f} "
            f"[{', '.join(flags) if flags else 'retrieval-only'}]  {row['query']!r}"
        )
    print("=" * 60 + "\n")


def skip_ask_flag(row: dict[str, Any]) -> bool:
    return "grounded" not in row


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the Agentic RAG pipeline against a golden test set.")
    parser.add_argument("--api", default=DEFAULT_API, help="Base URL of the running FastAPI backend")
    parser.add_argument("--testset", type=Path, default=DEFAULT_TESTSET, help="Path to testset YAML file")
    parser.add_argument("--top-k", type=int, default=10, help="How many search results to fetch per query")
    parser.add_argument("--skip-ask", action="store_true", help="Only run /search metrics; skip slow /ask calls")
    parser.add_argument("--limit", type=int, help="Only run the first N test cases (quick sanity check)")
    parser.add_argument("--output", type=Path, help="Optional path to write full JSON results")
    args = parser.parse_args()

    try:
        requests.get(f"{args.api}/health", timeout=5).raise_for_status()
    except Exception as exc:
        print(f"API not reachable at {args.api}: {exc}", file=sys.stderr)
        return 1

    cases = load_testset(args.testset)
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        print(f"No test cases found in {args.testset}", file=sys.stderr)
        return 1

    print(f"Running {len(cases)} test queries against {args.api} (skip_ask={args.skip_ask})...")
    result = evaluate(args.api, cases, args.top_k, args.skip_ask)
    print_report(result)

    if args.output:
        import json

        args.output.write_text(json.dumps(result, indent=2))
        print(f"Full results written to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
