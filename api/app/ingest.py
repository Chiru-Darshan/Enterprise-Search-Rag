"""Bulk-load chunks_*.jsonl into OpenSearch. Usage: python -m app.ingest /data/chunks_x.jsonl"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from .opensearch_client import bulk_index, get_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger("ingest")


def load_chunks(path: Path) -> list[dict]:
    files = sorted(path.glob("chunks_*.jsonl")) if path.is_dir() else [path]
    chunks = []
    for file in files:
        # split on "\n" only: str.splitlines() also breaks on U+2028/U+2029,
        # which can appear unescaped inside JSON string values (not record separators)
        for line in file.read_text(encoding="utf-8").split("\n"):
            if line.strip():
                chunks.append(json.loads(line))
    return chunks


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m app.ingest <chunks.jsonl or directory>")
        return 1

    path = Path(sys.argv[1])
    chunks = load_chunks(path)
    if not chunks:
        log.error("No chunks found at %s", path)
        return 1

    client = get_client()
    batch_size = 500
    total_ok, total_err = 0, 0
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        ok, err = bulk_index(client, batch)
        total_ok += ok
        total_err += err
        log.info("Indexed batch %d-%d (%d ok, %d errors)", i, i + len(batch), ok, err)

    log.info("Done: %d indexed, %d errors, total input %d", total_ok, total_err, len(chunks))
    return 0 if total_err == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
