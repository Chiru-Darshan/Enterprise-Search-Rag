"""Chunk a crawled JSONL corpus for embedding/indexing (FR-04).

Usage:
    python chunk_corpus.py data/searchunify --chunk-size 700 --overlap 100
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import median

from crawler.chunking import DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP, chunk_document


def load_documents(path: Path) -> list[dict]:
    files = sorted(path.glob("documents_*.jsonl")) if path.is_dir() else [path]
    docs: list[dict] = []
    skipped = 0
    for file in files:
        # split on "\n" only: str.splitlines() also breaks on U+2028/U+2029,
        # which can appear unescaped inside JSON string values (not record separators)
        for line in file.read_text(encoding="utf-8").split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                docs.append(json.loads(line))
            except json.JSONDecodeError:
                skipped += 1
    if skipped:
        print(f"(skipped {skipped} incomplete line(s))")
    return docs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Directory with documents_*.jsonl, or a single file")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="Target tokens/chunk")
    parser.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP, help="Token overlap between windows")
    parser.add_argument("--output", help="Output .jsonl path (default: <dir>/chunks_<timestamp>.jsonl)")
    args = parser.parse_args()

    root = Path(args.path)
    docs = load_documents(root)
    if not docs:
        print(f"No documents found in {root}")
        return 1

    out_dir = root if root.is_dir() else root.parent
    out_path = Path(args.output) if args.output else out_dir / f"chunks_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.jsonl"

    structure_aware, fallback = 0, 0
    token_counts: list[int] = []
    by_source: Counter[str] = Counter()

    with out_path.open("w", encoding="utf-8") as out:
        for doc in docs:
            if doc.get("sections"):
                structure_aware += 1
            else:
                fallback += 1
            for chunk in chunk_document(doc, args.chunk_size, args.overlap):
                out.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")
                token_counts.append(chunk.token_count)
                by_source[chunk.source_type] += 1

    print(f"Documents chunked      : {len(docs)}")
    print(f"  structure-aware      : {structure_aware} (had 'sections' from a fresh crawl)")
    print(f"  fallback (windowed)  : {fallback} (older crawl or non-HTML asset)")
    print(f"Chunks written         : {len(token_counts)}")
    if token_counts:
        print(f"Tokens/chunk           : median {median(token_counts):.0f} | max {max(token_counts)} | min {min(token_counts)}")
    print(f"By source_type         : {dict(by_source)}")
    print(f"Output                 : {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
