"""Crawl orchestration: frontier, workers, incremental change detection."""

from __future__ import annotations

import io
import logging
import queue
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

import requests

from .config import CrawlConfig
from .extract import extract, utc_now
from .fetcher import Fetcher, RateLimiter
from .render import JsRenderer
from .robots import RobotsRegistry
from .sitemap import discover as discover_sitemaps
from .store import CrawlStore, content_hash
from .urls import in_allowed_domains, normalize_url, path_extension, registrable_host

log = logging.getLogger(__name__)

HTML_TYPES = {"text/html", "application/xhtml+xml", ""}
REDIRECT_STATUS = {301, 302, 303, 307, 308}
# Content types worth keeping as linked documents; everything else is media noise.
DOCUMENT_TYPES = (
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument",
    "application/vnd.ms-",
    "application/rtf",
    "text/",
)


@dataclass
class CrawlStats:
    queued: int = 0
    fetched: int = 0
    indexed: int = 0
    unchanged: int = 0
    duplicates: int = 0
    skipped_robots: int = 0
    skipped_noindex: int = 0
    skipped_scope: int = 0
    skipped_redirect: int = 0
    skipped_media: int = 0
    rendered: int = 0
    assets: int = 0
    errors: int = 0
    started_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class Task:
    url: str
    depth: int
    lastmod: str | None = None
    is_asset: bool = False


class Crawler:
    def __init__(self, config: CrawlConfig) -> None:
        self.config = config
        self.stats = CrawlStats()
        self.limiter = RateLimiter(config.request_delay)
        self.fetcher = Fetcher(
            user_agent=config.user_agent,
            timeout=config.request_timeout,
            max_retries=config.max_retries,
            limiter=self.limiter,
            max_content_bytes=config.max_content_bytes,
            pool_size=max(8, config.max_workers * 2),
        )
        self.robots = RobotsRegistry(self.fetcher, config.user_agent, config.obey_robots)
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        self.store = CrawlStore(config.state_db, config.output_dir, run_id)
        self.renderer: JsRenderer | None = (
            JsRenderer(config.user_agent, config.render_concurrency, config.render_timeout)
            if config.render_js != "off"
            else None
        )

        self._queue: queue.Queue[Task] = queue.Queue()
        self._seen: set[str] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()

    # ---------------------------------------------------------------- frontier

    def _enqueue(self, url: str, depth: int, lastmod: str | None = None, is_asset: bool = False) -> None:
        normalized = normalize_url(url)
        if not normalized or depth > self.config.max_depth:
            return
        if path_extension(normalized) in self.config.skip_extensions:
            with self._lock:
                self.stats.skipped_media += 1
            return
        if not in_allowed_domains(normalized, self.config.allowed_domains):
            return
        if not self.config.url_allowed(normalized):
            with self._lock:
                self.stats.skipped_scope += 1
            return
        with self._lock:
            if normalized in self._seen:
                return
            self._seen.add(normalized)
            self.stats.queued += 1
        self._queue.put(Task(normalized, depth, lastmod, is_asset))

    def _seed(self) -> None:
        sitemaps = list(self.config.sitemaps)
        for seed in self.config.seeds or self.config.sitemaps[:1]:
            sitemaps.extend(s for s in self.robots.sitemaps(seed) if s not in sitemaps)

        entries = discover_sitemaps(self.fetcher, sitemaps) if sitemaps else []
        log.info("Discovered %d URLs from %d sitemap root(s)", len(entries), len(sitemaps))
        for entry in entries:
            self._enqueue(entry.url, depth=0, lastmod=entry.lastmod)
        for seed in self.config.seeds:
            self._enqueue(seed, depth=0)

        for host in {registrable_host(u) for u in self.config.seeds + sitemaps if u}:
            delay = self.robots.crawl_delay(f"https://{host}/")
            if delay:
                log.info("robots.txt crawl-delay for %s: %ss", host, delay)
                self.limiter.set_delay(host, delay)

    # ------------------------------------------------------------------- run

    def run(self) -> CrawlStats:
        started = time.monotonic()
        try:
            self._seed()
            workers = [
                threading.Thread(target=self._worker, name=f"crawl-{i}", daemon=True)
                for i in range(self.config.max_workers)
            ]
            for worker in workers:
                worker.start()
            self._queue.join()
            self._stop.set()
            for worker in workers:
                worker.join(timeout=5)
        finally:
            self.fetcher.close()
            if self.renderer is not None:
                self.renderer.close()
            self.store.close()
        log.info(
            "Crawl finished in %.1fs: %s",
            time.monotonic() - started,
            {k: v for k, v in asdict(self.stats).items() if k != "started_at"},
        )
        return self.stats

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                task = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                if not self._budget_available():
                    continue
                self._process(task)
            except requests.RequestException as exc:
                with self._lock:
                    self.stats.errors += 1
                log.warning("Fetch failed %s: %s", task.url, exc.__class__.__name__)
                self.store.upsert(
                    url=task.url, status=0, last_crawled=utc_now(), error="network_error"
                )
            except Exception:
                with self._lock:
                    self.stats.errors += 1
                log.exception("Failed to process %s", task.url)
                self.store.upsert(
                    url=task.url, status=0, last_crawled=utc_now(), error="processing_error"
                )
            finally:
                self._queue.task_done()

    def _budget_available(self) -> bool:
        limit = self.config.max_pages
        if limit is None:
            return True
        with self._lock:
            return self.stats.fetched < limit

    # --------------------------------------------------------------- pipeline

    def _in_scope(self, url: str) -> bool:
        normalized = normalize_url(url)
        return bool(
            normalized
            and in_allowed_domains(normalized, self.config.allowed_domains)
            and self.config.url_allowed(normalized)
            and self.robots.allowed(normalized)
        )

    def _process(self, task: Task) -> None:
        if not self.robots.allowed(task.url):
            with self._lock:
                self.stats.skipped_robots += 1
            log.debug("robots.txt disallows %s", task.url)
            return

        state = self.store.get(task.url) if self.config.incremental else None
        resp = self.fetcher.get(
            task.url,
            etag=state.etag if state else None,
            last_modified=state.last_modified if state else None,
            redirect_filter=self._in_scope,
        )
        with self._lock:
            self.stats.fetched += 1
            fetched = self.stats.fetched
        if fetched % 100 == 0:
            log.info(
                "Progress: %d fetched, %d indexed, %d queued (%d pending)",
                fetched,
                self.stats.indexed,
                self.stats.queued,
                self._queue.qsize(),
            )

        if resp.status in REDIRECT_STATUS:
            with self._lock:
                self.stats.skipped_redirect += 1
            log.debug("DECISION redirect_not_followed %s -> %s", task.url, resp.headers.get("Location"))
            self.store.upsert(
                url=task.url,
                status=resp.status,
                last_crawled=utc_now(),
                error="redirect_not_followed",
            )
            return
        if resp.status == 304:
            with self._lock:
                self.stats.unchanged += 1
            log.debug("DECISION unchanged_304 %s", task.url)
            self.store.upsert(url=task.url, status=304, last_crawled=utc_now(), error=None)
            return
        if resp.status >= 400:
            with self._lock:
                self.stats.errors += 1
            log.debug("DECISION http_error_%s %s", resp.status, task.url)
            self.store.upsert(
                url=task.url, status=resp.status, last_crawled=utc_now(), error=f"http_{resp.status}"
            )
            return

        if task.is_asset or resp.content_type not in HTML_TYPES:
            self._handle_asset(task, resp)
            return
        self._handle_html(task, resp)

    def _handle_html(self, task: Task, resp) -> None:
        page = extract(resp.text(), resp.url, self.config.asset_extensions)
        with self._lock:
            self._seen.add(resp.url)  # avoid refetching the redirect target later

        rendered = False
        if self._needs_render(resp.url, page.word_count):
            html = self.renderer.render(resp.url) if self.renderer else None
            if html:
                page = extract(html, resp.url, self.config.asset_extensions)
                rendered = True
                with self._lock:
                    self.stats.rendered += 1

        if self.config.obey_noindex and (
            page.noindex or "noindex" in resp.headers.get("X-Robots-Tag", "").lower()
        ):
            with self._lock:
                self.stats.skipped_noindex += 1
            log.debug("DECISION noindex %s", task.url)
            self.store.upsert(url=task.url, status=resp.status, last_crawled=utc_now(), error="noindex")
            return

        if self.config.follow_links and not page.nofollow:
            for link in page.links:
                self._enqueue(link, task.depth + 1)
            if self.config.fetch_assets:
                for asset in page.assets:
                    self._enqueue(asset, task.depth + 1, is_asset=True)

        digest = content_hash(page.text)
        state = self.store.get(task.url) if self.config.incremental else None
        now = utc_now()

        if state and state.content_hash == digest:
            with self._lock:
                self.stats.unchanged += 1
            log.debug("DECISION unchanged_hash %s", task.url)
            self.store.upsert(url=task.url, status=resp.status, last_crawled=now, error=None)
            return
        if page.text and self.store.hash_seen(digest, task.url):
            with self._lock:
                self.stats.duplicates += 1
            log.debug("DECISION duplicate_content %s", task.url)
            self.store.upsert(
                url=task.url,
                status=resp.status,
                content_hash=digest,
                last_crawled=now,
                error="duplicate",
            )
            return

        canonical = page.canonical_url or resp.url
        self.store.write_document(
            {
                "id": digest[:32],
                "url": resp.url,
                "requested_url": task.url,
                "canonical_url": canonical,
                "source_type": "web_page",
                "content_type": resp.content_type or "text/html",
                "title": page.title,
                "description": page.description,
                "language": page.language,
                "headings": page.headings,
                "breadcrumbs": page.breadcrumbs,
                "keywords": page.keywords,
                "text": page.text,
                "sections": [asdict(s) for s in page.sections],
                "word_count": page.word_count,
                "published_at": page.published_at,
                "modified_at": page.modified_at or resp.headers.get("Last-Modified", "") or (task.lastmod or ""),
                "sitemap_lastmod": task.lastmod or "",
                "http_status": resp.status,
                "content_hash": digest,
                "crawled_at": now,
                "depth": task.depth,
                "js_rendered": rendered,
            }
        )
        with self._lock:
            self.stats.indexed += 1
        log.debug(
            "DECISION indexed %s (words=%d, rendered=%s, depth=%d)",
            resp.url,
            page.word_count,
            rendered,
            task.depth,
        )
        self.store.upsert(
            url=task.url,
            canonical_url=canonical,
            status=resp.status,
            content_hash=digest,
            etag=resp.headers.get("ETag"),
            last_modified=resp.headers.get("Last-Modified"),
            title=page.title,
            last_crawled=now,
            last_changed=now,
            error=None,
        )

    def _needs_render(self, url: str, word_count: int) -> bool:
        if self.renderer is None:
            return False
        if self.config.render_js == "always":
            return True
        host = registrable_host(url)
        if any(host == h.lower() or host.endswith("." + h.lower()) for h in self.config.render_hosts):
            return True
        return word_count < self.config.render_min_words

    def _handle_asset(self, task: Task, resp) -> None:
        if not self.config.fetch_assets:
            return
        extension = path_extension(task.url)
        content_type = resp.content_type
        if not (content_type.startswith(DOCUMENT_TYPES) or extension in self.config.asset_extensions):
            with self._lock:
                self.stats.skipped_media += 1
            log.debug("DECISION skipped_media %s (%s)", resp.url, content_type or "unknown")
            self.store.upsert(
                url=task.url, status=resp.status, last_crawled=utc_now(), error="unsupported_media"
            )
            return
        text = _asset_text(resp.content, resp.content_type, task.url)
        digest = content_hash(text or resp.url)
        now = utc_now()
        saved = str(self.store.save_asset(resp.url, resp.content)) if self.config.save_assets else ""

        self.store.write_document(
            {
                "id": digest[:32],
                "url": resp.url,
                "requested_url": task.url,
                "canonical_url": resp.url,
                "source_type": "linked_document",
                "content_type": resp.content_type,
                "title": task.url.rstrip("/").split("/")[-1],
                "text": text,
                "word_count": len(text.split()),
                "local_path": saved,
                "modified_at": resp.headers.get("Last-Modified", ""),
                "http_status": resp.status,
                "content_hash": digest,
                "crawled_at": now,
                "depth": task.depth,
                "needs_extraction": not text,
            }
        )
        with self._lock:
            self.stats.assets += 1
        log.debug("DECISION asset %s (%s, words=%d)", resp.url, resp.content_type, len(text.split()))
        self.store.upsert(
            url=task.url,
            status=resp.status,
            content_hash=digest,
            etag=resp.headers.get("ETag"),
            last_modified=resp.headers.get("Last-Modified"),
            last_crawled=now,
            last_changed=now,
            error=None,
        )


def _asset_text(content: bytes, content_type: str, url: str) -> str:
    """Best-effort inline text extraction; richer formats are left to Tika/Unstructured."""
    if content_type.startswith("text/") or path_extension(url) in (".txt", ".csv"):
        return content.decode("utf-8", errors="replace").strip()
    if content_type == "application/pdf" or path_extension(url) == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(content))
            return "\n\n".join((p.extract_text() or "") for p in reader.pages).strip()
        except Exception as exc:
            log.debug("PDF extraction failed for %s: %s", url, exc)
    return ""
