"""Crawl state (incremental + dedup) and JSONL document output."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    url            TEXT PRIMARY KEY,
    canonical_url  TEXT,
    status         INTEGER,
    content_hash   TEXT,
    etag           TEXT,
    last_modified  TEXT,
    title          TEXT,
    first_seen     TEXT,
    last_crawled   TEXT,
    last_changed   TEXT,
    error          TEXT
);
CREATE INDEX IF NOT EXISTS idx_pages_hash ON pages(content_hash);
"""


@dataclass(frozen=True)
class PageState:
    url: str
    content_hash: str | None
    etag: str | None
    last_modified: str | None


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()


class CrawlStore:
    def __init__(self, db_path: str | Path, output_dir: str | Path, run_id: str) -> None:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        self._docs_path = out / f"documents_{run_id}.jsonl"
        self._docs = self._docs_path.open("a", encoding="utf-8")
        self.assets_dir = out / "assets"

    @property
    def documents_path(self) -> Path:
        return self._docs_path

    def get(self, url: str) -> PageState | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT url, content_hash, etag, last_modified FROM pages WHERE url = ?", (url,)
            ).fetchone()
        return PageState(*row) if row else None

    def hash_seen(self, digest: str, url: str) -> bool:
        """True if identical content was already stored under a different URL."""
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM pages WHERE content_hash = ? AND url <> ? LIMIT 1", (digest, url)
            ).fetchone()
        return row is not None

    def upsert(self, **fields: Any) -> None:
        url = fields.pop("url")
        columns = ", ".join(fields)
        placeholders = ", ".join("?" for _ in fields)
        updates = ", ".join(f"{c}=excluded.{c}" for c in fields)
        with self._lock:
            self._conn.execute(
                f"INSERT INTO pages (url, {columns}, first_seen) "
                f"VALUES (?, {placeholders}, COALESCE((SELECT first_seen FROM pages WHERE url=?), ?)) "
                f"ON CONFLICT(url) DO UPDATE SET {updates}",
                (url, *fields.values(), url, fields.get("last_crawled")),
            )
            self._conn.commit()

    def write_document(self, doc: dict[str, Any]) -> None:
        line = json.dumps(doc, ensure_ascii=False)
        with self._lock:
            self._docs.write(line + "\n")
            self._docs.flush()

    def save_asset(self, url: str, content: bytes) -> Path:
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        name = hashlib.sha1(url.encode()).hexdigest()[:16]
        suffix = Path(url.split("?")[0]).suffix[:10] or ".bin"
        path = self.assets_dir / f"{name}{suffix}"
        path.write_bytes(content)
        return path

    def close(self) -> None:
        with self._lock:
            self._docs.close()
            self._conn.close()
