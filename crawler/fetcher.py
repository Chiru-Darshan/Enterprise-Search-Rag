"""Polite HTTP fetching: per-host rate limiting, retries, conditional requests."""

from __future__ import annotations

import logging
import random
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter

from .urls import normalize_url, registrable_host

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}
REDIRECT_STATUS = {301, 302, 303, 307, 308}


def _header_charset(content_type: str) -> str | None:
    match = re.search(r"charset=[\"']?([\w\-]+)", content_type, re.I)
    return match.group(1) if match else None


@dataclass
class Response:
    url: str
    status: int
    headers: dict[str, str]
    content: bytes
    encoding: str | None
    elapsed: float

    @property
    def content_type(self) -> str:
        return self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()

    def text(self) -> str:
        return self.content.decode(self.encoding or self._sniff_encoding(), errors="replace")

    def _sniff_encoding(self) -> str:
        """Servers often omit charset; trust the document, then UTF-8, then cp1252."""
        head = self.content[:4096].decode("ascii", "ignore")
        match = re.search(r"charset=[\"']?([\w\-]+)", head, re.I)
        if match:
            return match.group(1)
        try:
            self.content.decode("utf-8")
            return "utf-8"
        except UnicodeDecodeError:
            return "cp1252"


class RateLimiter:
    """Enforces a minimum interval between requests to the same host."""

    def __init__(self, default_delay: float) -> None:
        self._default = default_delay
        self._delays: dict[str, float] = {}
        self._next_free: dict[str, float] = {}
        self._lock = threading.Lock()

    def set_delay(self, host: str, delay: float) -> None:
        with self._lock:
            self._delays[host] = max(delay, self._default)

    def acquire(self, host: str) -> None:
        while True:
            with self._lock:
                delay = self._delays.get(host, self._default)
                now = time.monotonic()
                ready_at = self._next_free.get(host, 0.0)
                if now >= ready_at:
                    self._next_free[host] = now + delay
                    return
                wait = ready_at - now
            time.sleep(wait)


class Fetcher:
    def __init__(
        self,
        user_agent: str,
        timeout: float,
        max_retries: int,
        limiter: RateLimiter,
        max_content_bytes: int,
        pool_size: int = 8,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.limiter = limiter
        self.max_content_bytes = max_content_bytes
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        adapter = HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def get(
        self,
        url: str,
        etag: str | None = None,
        last_modified: str | None = None,
        redirect_filter: Callable[[str], bool] | None = None,
        max_redirects: int = 5,
    ) -> Response:
        """Fetch a URL, following redirects only to targets accepted by redirect_filter."""
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        current = url
        for _ in range(max_redirects + 1):
            resp = self._get_once(current, headers)
            location = resp.headers.get("Location")
            if resp.status not in REDIRECT_STATUS or not location:
                return resp
            target = normalize_url(urljoin(current, location))
            if not target:
                return resp
            if target == current:  # self-redirect after normalization
                return resp
            if redirect_filter and not redirect_filter(target):
                log.debug("Blocked out-of-scope redirect %s -> %s", current, target)
                return resp
            current = target
            headers.pop("If-None-Match", None)
            headers.pop("If-Modified-Since", None)
        log.warning("Too many redirects starting at %s", url)
        return resp

    def _get_once(self, url: str, headers: dict[str, str]) -> Response:
        host = registrable_host(url)
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self.limiter.acquire(host)
            started = time.monotonic()
            try:
                with self.session.get(
                    url, headers=headers, timeout=self.timeout, stream=True, allow_redirects=False
                ) as resp:
                    if resp.status_code in RETRY_STATUS and attempt < self.max_retries:
                        self._backoff(resp, attempt)
                        continue
                    body = self._read_capped(resp)
                    return Response(
                        url=str(resp.url),
                        status=resp.status_code,
                        headers=dict(resp.headers),
                        content=body,
                        encoding=_header_charset(resp.headers.get("Content-Type", "")),
                        elapsed=time.monotonic() - started,
                    )
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(2**attempt + random.random())
                    continue
                raise
        raise last_error or RuntimeError(f"failed to fetch {url}")

    def _read_capped(self, resp: requests.Response) -> bytes:
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_content(64 * 1024):
            chunks.append(chunk)
            total += len(chunk)
            if total >= self.max_content_bytes:
                log.warning("Truncated oversized response: %s", resp.url)
                break
        return b"".join(chunks)

    @staticmethod
    def _backoff(resp: requests.Response, attempt: int) -> None:
        retry_after = resp.headers.get("Retry-After")
        wait = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
        time.sleep(min(wait, 60) + random.random())

    def close(self) -> None:
        self.session.close()
