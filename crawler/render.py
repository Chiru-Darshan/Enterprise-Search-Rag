"""JavaScript rendering via Crawl4AI, used as a fallback for JS-only pages (FR-02).

Crawl4AI is async and browser-backed; the crawler is threaded and sync, so a single
browser instance is driven from a dedicated event-loop thread.
"""

from __future__ import annotations

import asyncio
import logging
import threading

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

log = logging.getLogger(__name__)


class JsRenderer:
    def __init__(self, user_agent: str, concurrency: int = 2, timeout: float = 45.0) -> None:
        self._user_agent = user_agent
        self._concurrency = concurrency
        self._timeout = timeout
        self._crawler: AsyncWebCrawler | None = None
        self._sem: asyncio.Semaphore | None = None
        self._init_lock = threading.Lock()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="js-renderer", daemon=True)
        self._thread.start()
        self.rendered = 0
        self.failed = 0

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _submit(self, coro, timeout: float):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    async def _start(self) -> None:
        browser = BrowserConfig(
            headless=True,
            verbose=False,
            user_agent=self._user_agent,
            text_mode=True,  # skip images/fonts; we only need the DOM
        )
        self._crawler = AsyncWebCrawler(config=browser)
        await self._crawler.start()
        self._sem = asyncio.Semaphore(self._concurrency)

    def _ensure_started(self) -> None:
        with self._init_lock:
            if self._crawler is None:
                log.info("Starting headless browser for JS rendering")
                self._submit(self._start(), 180)

    async def _render(self, url: str) -> str | None:
        assert self._crawler and self._sem
        async with self._sem:
            config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                page_timeout=int(self._timeout * 1000),
                wait_until="networkidle",
                remove_overlay_elements=True,
                verbose=False,
                stream=False,
            )
            result = await self._crawler.arun(url, config=config)
            return result.html if result.success else None

    def render(self, url: str) -> str | None:
        """Return fully rendered HTML, or None if rendering failed."""
        try:
            self._ensure_started()
            html = self._submit(self._render(url), self._timeout + 60)
        except Exception as exc:
            self.failed += 1
            log.warning("JS render failed %s: %s", url, exc)
            return None
        if html:
            self.rendered += 1
        else:
            self.failed += 1
        return html

    def close(self) -> None:
        try:
            if self._crawler is not None:
                self._submit(self._crawler.close(), 60)
        except Exception as exc:
            log.debug("Browser shutdown error: %s", exc)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=10)
