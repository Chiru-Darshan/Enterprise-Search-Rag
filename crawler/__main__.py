"""CLI entry point: python -m crawler --config config/searchunify.yaml"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from .config import load_config
from .crawler import Crawler


def _setup_logging(log_file: Path, console_verbose: bool) -> None:
    """Console stays readable; the file keeps a full DEBUG trail for audit."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if console_verbose else logging.INFO)
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root.addHandler(console)

    audit = logging.FileHandler(log_file, encoding="utf-8")
    audit.setLevel(logging.DEBUG)
    audit.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s")
    )
    root.addHandler(audit)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def _warn_if_partial_corpus(config, log: logging.Logger) -> None:
    """JSONL output is a per-run delta: unchanged pages are never re-emitted.

    If prior state exists but no documents remain on disk, an incremental run would
    silently produce an almost-empty corpus.
    """
    state_db = Path(config.state_db)
    if not (config.incremental and state_db.exists()):
        return
    try:
        with sqlite3.connect(str(state_db)) as conn:
            known = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    except sqlite3.Error:
        return
    if not known:
        return

    existing_docs = sum(
        1
        for f in Path(config.output_dir).glob("documents_*.jsonl")
        if f.stat().st_size > 0
    )
    log.info("Resuming: %d URLs already in crawl state; unchanged pages will be skipped", known)
    if not existing_docs:
        log.warning(
            "Crawl state has %d URLs but no non-empty documents_*.jsonl exists. "
            "An incremental run will skip them and produce a near-empty corpus. "
            "Use --full to rebuild, or delete %s to start clean.",
            known,
            state_db,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="crawler", description="Website crawler for RAG ingestion")
    parser.add_argument("-c", "--config", required=True, help="Path to a YAML crawl config")
    parser.add_argument("--max-pages", type=int, help="Override max_pages (useful for smoke tests)")
    parser.add_argument("--full", action="store_true", help="Ignore stored hashes and recrawl everything")
    parser.add_argument("--no-links", action="store_true", help="Sitemap URLs only, do not follow links")
    parser.add_argument("--no-render", action="store_true", help="Disable JS rendering for this run")
    parser.add_argument("--log-file", help="Audit log path (default: <output_dir>/logs/crawl_<ts>.log)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Also print DEBUG to console")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    if args.max_pages is not None:
        config.max_pages = args.max_pages
    if args.full:
        config.incremental = False
    if args.no_links:
        config.follow_links = False
    if args.no_render:
        config.render_js = "off"

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log_file = Path(args.log_file) if args.log_file else Path(config.output_dir) / "logs" / f"crawl_{run_id}.log"
    _setup_logging(log_file, args.verbose)

    log = logging.getLogger("crawler.run")
    log.info("Audit log: %s", log_file)
    _warn_if_partial_corpus(config, log)
    log.info(
        "Scope: domains=%s | sitemaps=%d | seeds=%d | delay=%ss | workers=%d | render=%s | incremental=%s",
        config.allowed_domains,
        len(config.sitemaps),
        len(config.seeds),
        config.request_delay,
        config.max_workers,
        config.render_js,
        config.incremental,
    )

    stats = Crawler(config).run()
    summary = asdict(stats)
    log.info("Run summary: %s", summary)
    print(json.dumps(summary, indent=2))
    print(f"Audit log: {log_file}")
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
