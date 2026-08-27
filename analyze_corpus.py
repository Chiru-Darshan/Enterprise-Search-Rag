"""Summarize a crawled JSONL corpus: coverage, sections, topics, freshness.

Usage: python analyze_corpus.py data/searchunify [--top 30]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from email.utils import parsedate_to_datetime
from pathlib import Path
from statistics import median
from urllib.parse import urlsplit

STOPWORDS = set(
    """a an the and or but if then than that this these those of in on at to for with from by as is are was
    were be been being it its it's you your we our us they their he she his her i me my what which who whom
    how when where why can could should would will shall may might must do does did done have has had not no
    yes so such about into over under more most less least other others new all any each few many much some
    own same very just now also there here get got make made use used using via per vs top best need needs
    way ways thing things one two three know knows help helps let lets don't doesn't isn't you're it’s –
    searchunify""".split()
)
WORD = re.compile(r"[a-z][a-z0-9'\-]{2,}")


def load_documents(path: Path) -> list[dict]:
    files = sorted(path.glob("documents_*.jsonl")) if path.is_dir() else [path]
    docs: list[dict] = []
    skipped = 0
    for file in files:
        with file.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    docs.append(json.loads(line))
                except json.JSONDecodeError:
                    skipped += 1  # partial trailing line while a crawl is still writing
    if skipped:
        print(f"(skipped {skipped} incomplete line(s) - crawl may still be running)\n")
    return docs


def section_of(url: str) -> str:
    parts = [p for p in urlsplit(url).path.split("/") if p]
    return parts[0] if parts else "(home)"


def year_of(doc: dict) -> str:
    """Documents carry either ISO 8601 or HTTP-date (RFC 7231) timestamps."""
    raw = (doc.get("modified_at") or doc.get("published_at") or "").strip()
    if not raw:
        return "(unknown)"
    if raw[:4].isdigit():
        return raw[:4]
    try:
        return str(parsedate_to_datetime(raw).year)
    except (TypeError, ValueError):
        return "(unknown)"


def tokens(text: str) -> list[str]:
    return [w for w in WORD.findall(text.lower()) if w not in STOPWORDS]


def phrase_counts(docs: list[dict], n: int) -> Counter[str]:
    """Bigrams over titles + headings, which carry the topical signal."""
    counts: Counter[str] = Counter()
    for doc in docs:
        surface = " . ".join([doc.get("title", "")] + doc.get("headings", []))
        words = tokens(surface)
        counts.update(f"{a} {b}" for a, b in zip(words, words[1:]))
    return counts


def crawl_state_summary(db_path: Path) -> dict[str, int]:
    if not db_path.exists():
        return {}
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT COALESCE(error, 'ok'), COUNT(*) FROM pages GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
    finally:
        conn.close()
    return dict(rows)


def bar(value: int, peak: int, width: int = 28) -> str:
    return "#" * max(1, round(value / peak * width)) if value else ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze a crawled document corpus")
    parser.add_argument("path", help="Output directory or a single .jsonl file")
    parser.add_argument("--top", type=int, default=25, help="How many entries per ranking")
    args = parser.parse_args()

    root = Path(args.path)
    docs = load_documents(root)
    if not docs:
        print(f"No documents found in {root}")
        return 1

    pages = [d for d in docs if d.get("source_type") == "web_page"]
    assets = [d for d in docs if d.get("source_type") == "linked_document"]
    words = [d.get("word_count", 0) for d in pages]
    sections = Counter(section_of(d["url"]) for d in pages)
    languages = Counter(d.get("language") or "(unset)" for d in pages)
    years = Counter(year_of(d) for d in pages)

    print("=" * 74)
    print("CRAWL CORPUS REPORT".center(74))
    print("=" * 74)
    print(f"\nSource            : {root}")
    print(f"Documents         : {len(docs)}  ({len(pages)} pages, {len(assets)} linked documents)")
    print(f"Total words       : {sum(words):,}")
    if words:
        print(f"Words per page    : median {median(words):,.0f} | max {max(words):,} | min {min(words):,}")
        print(f"Thin pages (<100w): {sum(1 for w in words if w < 100)}")
    print(f"Languages         : {', '.join(f'{k} ({v})' for k, v in languages.most_common(5))}")

    state = crawl_state_summary(root / "crawl_state.sqlite")
    if state:
        print("\nCRAWL OUTCOMES (URLs seen)")
        print("-" * 74)
        for label, count in state.items():
            print(f"  {label:<24} {count:>6}")

    print(f"\nCONTENT SECTIONS (top {args.top} URL paths)")
    print("-" * 74)
    peak = sections.most_common(1)[0][1]
    for name, count in sections.most_common(args.top):
        share = count / len(pages) * 100
        print(f"  /{name:<28} {count:>5} ({share:4.1f}%) {bar(count, peak)}")

    print("\nCONTENT FRESHNESS (by last-modified year)")
    print("-" * 74)
    peak = max(years.values())
    for year, count in sorted(years.items(), reverse=True)[:12]:
        print(f"  {year:<10} {count:>5} {bar(count, peak)}")

    hosts = Counter(urlsplit(d["url"]).hostname or "?" for d in docs)
    print("\nDOCUMENTS BY HOST")
    print("-" * 74)
    for host, count in hosts.most_common():
        print(f"  {host:<34} {count:>5} ({count / len(docs) * 100:4.1f}%)")

    print(f"\nTOP TOPICS (bigrams in titles & headings, top {args.top})")
    print("-" * 74)
    for phrase, count in phrase_counts(docs, args.top).most_common(args.top):
        print(f"  {phrase:<38} {count:>5}")

    print(f"\nTOP TERMS (body text, top {args.top})")
    print("-" * 74)
    terms: Counter[str] = Counter()
    for doc in docs:
        terms.update(set(tokens(doc.get("text", "")[:20000])))
    for term, count in terms.most_common(args.top):
        print(f"  {term:<38} {count:>5} pages")

    print("\nLARGEST DOCUMENTS")
    print("-" * 74)
    for doc in sorted(pages, key=lambda d: d.get("word_count", 0), reverse=True)[:10]:
        print(f"  {doc['word_count']:>6}w  {doc['title'][:60]}")

    print("\nSAMPLE CONTENT BY SECTION (what the corpus can answer)")
    print("-" * 74)
    for name, count in sections.most_common(10):
        print(f"\n  /{name}  ({count} pages)")
        samples = [d for d in pages if section_of(d["url"]) == name]
        samples.sort(key=lambda d: d.get("word_count", 0), reverse=True)
        for doc in samples[:5]:
            print(f"    - {doc['title'][:66]}")

    if assets:
        print("\nLINKED DOCUMENTS")
        print("-" * 74)
        types = Counter(a.get("content_type", "unknown") for a in assets)
        for content_type, count in types.most_common():
            pending = sum(
                1 for a in assets if a.get("content_type") == content_type and a.get("needs_extraction")
            )
            print(f"  {content_type:<40} {count:>5}  ({pending} need external extraction)")

    print("\n" + "=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
