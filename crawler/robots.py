"""robots.txt handling: allow/deny rules, crawl-delay, sitemap discovery."""

from __future__ import annotations

import logging
import threading
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from .fetcher import Fetcher
from .urls import registrable_host

log = logging.getLogger(__name__)


class RobotsRegistry:
    """Caches one parsed robots.txt per host and applies its rules."""

    def __init__(self, fetcher: Fetcher, user_agent: str, enabled: bool = True) -> None:
        self._fetcher = fetcher
        self._ua = user_agent
        self._enabled = enabled
        self._parsers: dict[str, RobotFileParser | None] = {}
        self._lock = threading.Lock()

    def _origin(self, url: str) -> str:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, "", "", ""))

    def _parser(self, url: str) -> RobotFileParser | None:
        host = registrable_host(url)
        with self._lock:
            if host in self._parsers:
                return self._parsers[host]
        parser = self._load(f"{self._origin(url)}/robots.txt")
        with self._lock:
            self._parsers[host] = parser
        return parser

    def _load(self, robots_url: str) -> RobotFileParser | None:
        parser = RobotFileParser()
        parser.set_url(robots_url)
        try:
            resp = self._fetcher.get(robots_url)
        except Exception as exc:  # network failure => treat as no restrictions
            log.warning("robots.txt unavailable (%s): %s", robots_url, exc)
            return None
        if resp.status in (401, 403):
            log.warning("robots.txt forbidden at %s; treating site as disallowed", robots_url)
            parser.disallow_all = True
            return parser
        if resp.status >= 400:
            return None
        parser.parse(resp.text().splitlines())
        return parser

    def allowed(self, url: str) -> bool:
        if not self._enabled:
            return True
        parser = self._parser(url)
        return True if parser is None else parser.can_fetch(self._ua, url)

    def crawl_delay(self, url: str) -> float | None:
        parser = self._parser(url)
        if parser is None:
            return None
        delay = parser.crawl_delay(self._ua)
        return float(delay) if delay is not None else None

    def sitemaps(self, url: str) -> list[str]:
        parser = self._parser(url)
        return list(parser.site_maps() or []) if parser else []
