"""HTML main-content and metadata extraction (FR-03)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from bs4 import BeautifulSoup, Tag

from .urls import normalize_url

BOILERPLATE_TAGS = ["script", "style", "noscript", "template", "svg", "iframe", "form", "button"]
BOILERPLATE_CONTAINERS = ["nav", "header", "footer", "aside"]
BOILERPLATE_HINT = re.compile(
    r"(nav|menu|breadcrumb|sidebar|side-bar|footer|header|cookie|consent|banner|popup|modal|"
    r"subscribe|newsletter|social|share|related-post|comment|advert|promo|skip-link)",
    re.I,
)
MAIN_SELECTORS = ["main", "article", "[role=main]", "#main", "#content", ".entry-content", ".post-content"]
WHITESPACE = re.compile(r"[ \t\u00a0]+")
BLANK_LINES = re.compile(r"\n{3,}")
HEADING_LEVELS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
BLOCK_TAGS = {"p", "li", "pre", "blockquote", "td", "th", "figcaption", "dd", "dt"}


@dataclass
class Section:
    """A heading and the block text that follows it, before the next heading."""

    heading: str
    level: int
    text: str


@dataclass
class Page:
    url: str
    canonical_url: str | None = None
    title: str = ""
    description: str = ""
    language: str = ""
    text: str = ""
    sections: list[Section] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    breadcrumbs: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    published_at: str = ""
    modified_at: str = ""
    noindex: bool = False
    nofollow: bool = False
    links: list[str] = field(default_factory=list)
    assets: list[str] = field(default_factory=list)
    word_count: int = 0


def _meta(soup: BeautifulSoup, attrs: dict[str, str]) -> str:
    tag = soup.find("meta", attrs=attrs)
    return (tag.get("content") or "").strip() if isinstance(tag, Tag) else ""


def _robots_directives(soup: BeautifulSoup) -> tuple[bool, bool]:
    directives = " ".join(_meta(soup, {"name": name}) for name in ("robots", "googlebot")).lower()
    return "noindex" in directives, "nofollow" in directives


def _strip_boilerplate(root: Tag) -> None:
    for tag in root.find_all(BOILERPLATE_TAGS + BOILERPLATE_CONTAINERS):
        tag.decompose()
    for tag in root.find_all(attrs={"class": BOILERPLATE_HINT}):
        tag.decompose()
    for tag in root.find_all(attrs={"id": BOILERPLATE_HINT}):
        tag.decompose()
    for tag in root.find_all(attrs={"aria-hidden": "true"}):
        tag.decompose()


def _pick_main(soup: BeautifulSoup) -> Tag:
    best: Tag | None = None
    best_len = 0
    for selector in MAIN_SELECTORS:
        for node in soup.select(selector):
            length = len(node.get_text(" ", strip=True))
            if length > best_len:
                best, best_len = node, length
    if best is not None and best_len >= 200:
        return best
    return soup.body or soup


def _clean_text(node: Tag) -> str:
    text = node.get_text("\n", strip=True)
    text = WHITESPACE.sub(" ", text)
    return BLANK_LINES.sub("\n\n", text).strip()


def _split_sections(root: Tag) -> list[Section]:
    """Group block text under its nearest preceding heading (FR-04 semantic chunking input)."""
    sections: list[Section] = []
    heading, level, buffer = "Overview", 0, []

    def flush() -> None:
        text = WHITESPACE.sub(" ", "\n".join(buffer)).strip()
        text = BLANK_LINES.sub("\n\n", text)
        if text:
            sections.append(Section(heading, level, text))
        buffer.clear()

    for el in root.find_all(True):
        if el.name in HEADING_LEVELS:
            flush()
            heading = el.get_text(" ", strip=True) or heading
            level = HEADING_LEVELS[el.name]
        elif el.name in BLOCK_TAGS and el.find_parent(BLOCK_TAGS) is None:
            text = el.get_text(" ", strip=True)
            if text:
                buffer.append(text)
    flush()
    return sections


def extract(html: str, url: str, asset_extensions: list[str]) -> Page:
    soup = BeautifulSoup(html, "lxml")
    page = Page(url=url)

    if soup.title and soup.title.string:
        page.title = soup.title.string.strip()
    page.title = page.title or _meta(soup, {"property": "og:title"})
    page.description = _meta(soup, {"name": "description"}) or _meta(
        soup, {"property": "og:description"}
    )
    page.keywords = [k.strip() for k in _meta(soup, {"name": "keywords"}).split(",") if k.strip()]
    page.published_at = _meta(soup, {"property": "article:published_time"})
    page.modified_at = _meta(soup, {"property": "article:modified_time"})
    page.noindex, page.nofollow = _robots_directives(soup)

    html_tag = soup.find("html")
    if isinstance(html_tag, Tag):
        page.language = (html_tag.get("lang") or "").strip()

    canonical = soup.find("link", rel=lambda v: bool(v) and "canonical" in v)
    if isinstance(canonical, Tag):
        page.canonical_url = normalize_url(canonical.get("href") or "", base=url)

    page.breadcrumbs = [
        crumb.get_text(" ", strip=True)
        for crumb in soup.select('[class*=breadcrumb] a, [id*=breadcrumb] a, nav[aria-label*="readcrumb"] a')
        if crumb.get_text(strip=True)
    ]

    for anchor in soup.find_all("a", href=True):
        target = normalize_url(anchor["href"], base=url)
        if not target:
            continue
        if any(target.lower().split("?")[0].endswith(ext) for ext in asset_extensions):
            page.assets.append(target)
        else:
            page.links.append(target)
    page.links = list(dict.fromkeys(page.links))
    page.assets = list(dict.fromkeys(page.assets))

    main = _pick_main(soup)
    _strip_boilerplate(main)
    page.headings = [h.get_text(" ", strip=True) for h in main.find_all(["h1", "h2", "h3"])][:50]
    page.sections = _split_sections(main)
    page.text = _clean_text(main)
    page.word_count = len(page.text.split())
    return page


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
