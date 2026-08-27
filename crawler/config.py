"""Crawl configuration loading and validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_USER_AGENT = (
    "EnterpriseSearchRAGBot/1.0 (+https://www.verint.com; contact=search-rag@example.com)"
)


@dataclass
class CrawlConfig:
    name: str = "crawl"
    seeds: list[str] = field(default_factory=list)
    sitemaps: list[str] = field(default_factory=list)
    allowed_domains: list[str] = field(default_factory=list)
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)

    user_agent: str = DEFAULT_USER_AGENT
    obey_robots: bool = True
    obey_noindex: bool = True
    request_delay: float = 1.0  # per-domain floor, seconds
    max_workers: int = 4
    request_timeout: float = 30.0
    max_retries: int = 2
    max_pages: int | None = None
    max_depth: int = 5
    follow_links: bool = True
    max_content_bytes: int = 20 * 1024 * 1024

    fetch_assets: bool = True  # linked PDF/DOCX/PPTX etc. (FR-01)
    asset_extensions: list[str] = field(
        default_factory=lambda: [".pdf", ".docx", ".doc", ".pptx", ".ppt", ".txt", ".csv"]
    )
    save_assets: bool = True
    # Media/static files that are never useful as RAG documents.
    skip_extensions: list[str] = field(
        default_factory=lambda: [
            ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico", ".tif", ".tiff",
            ".css", ".js", ".json", ".xml", ".rss", ".atom",
            ".mp4", ".webm", ".mov", ".avi", ".mp3", ".wav", ".ogg",
            ".zip", ".gz", ".tar", ".rar", ".7z", ".exe", ".dmg",
            ".woff", ".woff2", ".ttf", ".eot", ".otf",
        ]
    )

    # JavaScript rendering via Crawl4AI: off | auto (only thin pages) | always
    render_js: str = "auto"
    render_min_words: int = 60
    render_hosts: list[str] = field(default_factory=list)
    render_concurrency: int = 2
    render_timeout: float = 45.0

    output_dir: str = "data/searchunify"
    state_db: str = "data/searchunify/crawl_state.sqlite"
    incremental: bool = True

    # Compiled at load time.
    include_re: list[re.Pattern[str]] = field(default_factory=list, repr=False)
    exclude_re: list[re.Pattern[str]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self.include_re = [re.compile(p, re.I) for p in self.include_patterns]
        self.exclude_re = [re.compile(p, re.I) for p in self.exclude_patterns]
        if not self.allowed_domains:
            raise ValueError("allowed_domains must not be empty")
        if not self.seeds and not self.sitemaps:
            raise ValueError("provide at least one seed URL or sitemap")
        if self.render_js not in ("off", "auto", "always"):
            raise ValueError("render_js must be one of: off, auto, always")
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        Path(self.state_db).parent.mkdir(parents=True, exist_ok=True)

    def url_allowed(self, url: str) -> bool:
        if self.include_re and not any(p.search(url) for p in self.include_re):
            return False
        return not any(p.search(url) for p in self.exclude_re)


def load_config(path: str | Path) -> CrawlConfig:
    raw: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    known = {f.name for f in CrawlConfig.__dataclass_fields__.values()}
    unknown = set(raw) - known
    if unknown:
        raise ValueError(f"unknown config keys: {sorted(unknown)}")
    return CrawlConfig(**raw)
