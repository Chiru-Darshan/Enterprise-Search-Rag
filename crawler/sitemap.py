"""Sitemap and sitemap-index parsing (FR-02: URL discovery from sitemap.xml)."""

from __future__ import annotations

import gzip
import logging
from dataclasses import dataclass
from xml.etree import ElementTree

from .fetcher import Fetcher
from .urls import normalize_url

log = logging.getLogger(__name__)

SM_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


@dataclass(frozen=True)
class SitemapEntry:
    url: str
    lastmod: str | None = None


def _decode(content: bytes, url: str) -> bytes:
    if url.endswith(".gz") or content[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(content)
        except OSError:
            pass
    return content


def parse_sitemap(content: bytes, url: str) -> tuple[list[str], list[SitemapEntry]]:
    """Return (child sitemap URLs, page entries) for one sitemap document."""
    try:
        root = ElementTree.fromstring(_decode(content, url))
    except ElementTree.ParseError as exc:
        log.warning("Invalid sitemap XML at %s: %s", url, exc)
        return [], []

    children: list[str] = []
    entries: list[SitemapEntry] = []
    tag = root.tag.split("}")[-1]

    if tag == "sitemapindex":
        for node in root.findall(f"{SM_NS}sitemap"):
            loc = node.findtext(f"{SM_NS}loc")
            normalized = normalize_url(loc or "", base=url)
            if normalized:
                children.append(normalized)
    elif tag == "urlset":
        for node in root.findall(f"{SM_NS}url"):
            loc = normalize_url(node.findtext(f"{SM_NS}loc") or "", base=url)
            if loc:
                entries.append(SitemapEntry(loc, node.findtext(f"{SM_NS}lastmod")))
    return children, entries


def discover(fetcher: Fetcher, sitemap_urls: list[str], max_sitemaps: int = 500) -> list[SitemapEntry]:
    """Walk a sitemap index tree and return every page entry found."""
    queue = list(dict.fromkeys(sitemap_urls))
    seen: set[str] = set()
    entries: dict[str, SitemapEntry] = {}

    while queue and len(seen) < max_sitemaps:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            resp = fetcher.get(url)
        except Exception as exc:
            log.warning("Sitemap fetch failed %s: %s", url, exc)
            continue
        if resp.status >= 400:
            log.warning("Sitemap %s returned HTTP %s", url, resp.status)
            continue
        children, page_entries = parse_sitemap(resp.content, url)
        queue.extend(c for c in children if c not in seen)
        for entry in page_entries:
            entries.setdefault(entry.url, entry)
        log.info("Sitemap %s -> %d children, %d urls", url, len(children), len(page_entries))

    return list(entries.values())
